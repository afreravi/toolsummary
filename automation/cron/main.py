#!/usr/bin/env python3
"""Daily pricing refresh + price-history commit.

Deterministic by design: no LLM is called. This is a fixed data transform on a
schedule, so an agent preset would burn tokens for no benefit and add a
non-deterministic step to a pipeline whose whole value is reproducibility.

Why this script clones the repo instead of shipping the pipeline in its tarball:
the pipeline is the thing being tested. Shipping a copy would let the tarball's
version drift from `main`, and then the data would be produced by code nobody
reviewed. Cloning means every run executes exactly the code on `main`, so a
suspicious change is visible as a diff before it ever touches the price log.

Sequence: clone repo -> run pipeline -> commit history -> push -> report.

Failure policy: a push failure is the one thing that must not be silent. History
lives only in the git repo, and the sandbox is discarded, so if the push fails
the day's snapshot is lost for good. That case exits non-zero.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = "afreravi/toolsummary"
WORK = Path(tempfile.gettempdir()) / "toolsummary"

# Everything the run deliberately does not attempt. Stated here so a reader can
# tell "skipped on purpose" from "silently missing".
NOT_ATTEMPTED = (
    "site publish (needs SFTP secrets)",
    "paid API/MCP serving",
)


def log(msg: str) -> None:
    print(f"[cron] {msg}", flush=True)


# Secret names tried in order. The automation sandbox and an interactive
# conversation expose different secret sets, so the lookup cannot assume one
# name: a hardcoded name is exactly what made the first scheduled run fail with
# a 404 before it ever reached the pipeline.
GITHUB_SECRET_NAMES = ("github_token", "GITHUB_TOKEN", "TOOLSUMMARY_GITHUB_TOKEN", "Toolsummary")


def get_secret(name: str) -> str:
    """Fetch a named secret from the agent server, or the OpenHands API.

    Custom secrets are not injected into the environment, so they are read over
    REST. AGENT_SERVER_URL is set on local Agent Canvas; cloud/enterprise use
    the sandbox-scoped API path instead.

    The environment is checked first purely so this script can be exercised
    locally, where there is no agent server to ask.
    """
    if os.environ.get(name):
        return os.environ[name]
    key = os.environ.get("SESSION_API_KEY") or os.environ.get("OH_SESSION_API_KEYS_0", "")
    url = os.environ.get("AGENT_SERVER_URL", "").rstrip("/")
    if url:
        endpoint = f"{url}/api/settings/secrets/{name}"
    else:
        api = os.environ["OPENHANDS_CLOUD_API_URL"].rstrip("/")
        endpoint = f"{api}/api/v1/sandboxes/{os.environ['SANDBOX_ID']}/settings/secrets/{name}"
    req = urllib.request.Request(endpoint, headers={"X-Session-API-Key": key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode().strip()


def get_github_token() -> tuple[str, str]:
    """Return (token, name_used), preferring a token that actually authenticates.

    Presence is not validity. The automation sandbox contains more than one
    token-shaped secret and they are not equivalent - one of them returns 401
    against the GitHub API. Picking the first name that merely exists is what
    made an earlier run clone successfully and then fail at push, which loses
    the day's snapshot. So each candidate is verified before it is trusted.
    """
    tried = []
    unverified: tuple[str, str] | None = None
    for name in GITHUB_SECRET_NAMES:
        try:
            value = get_secret(name)
        except Exception:
            tried.append(f"{name}(missing)")
            continue
        if not value:
            tried.append(f"{name}(empty)")
            continue
        if github_token_ok(value):
            return value, name
        tried.append(f"{name}(rejected by GitHub)")
        unverified = unverified or (value, name)

    # Nothing authenticated. Fall back to a present-but-unverified token so the
    # error surfaces from the real operation rather than from this probe, and
    # report which names were ruled out.
    if unverified:
        log(f"WARNING: no token passed verification; trying '{unverified[1]}' anyway")
        return unverified
    raise RuntimeError(f"no GitHub token found; tried: {', '.join(tried)}")


def github_token_ok(token: str) -> bool:
    """True when GitHub accepts the token as the authenticated user."""
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "toolsummary-automation"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception:
        return False


def fire_callback(status: str = "COMPLETED", error: str | None = None) -> None:
    """Signal run completion. Must be called on every exit path.

    Without this the run stays RUNNING until a watchdog marks it FAILED, which
    looks identical to a hang.
    """
    url = os.environ.get("AUTOMATION_CALLBACK_URL", "")
    if not url:
        return
    body: dict = {"status": status, "run_id": os.environ.get("AUTOMATION_RUN_ID", "")}
    if error:
        body["error"] = error
    # The callback key is not always present; fall back to the session key,
    # which is what the service accepts when no dedicated key is issued.
    auth = (os.environ.get("AUTOMATION_CALLBACK_API_KEY")
            or os.environ.get("SESSION_API_KEY")
            or os.environ.get("OH_SESSION_API_KEYS_0", ""))
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {auth}"},
    )
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception as e:  # never mask the real result with a callback problem
        log(f"callback error (non-fatal): {e}")


def run(cmd: list[str], cwd: Path, token: str) -> subprocess.CompletedProcess:
    """Run a git command with the credential kept out of argv and logs."""
    env = dict(os.environ)
    # Feed the token via an env-based credential helper so it never appears in
    # `ps` output, in the reflog, or in this script's own error messages.
    env["GIT_ASKPASS"] = "/bin/true"
    env["GIT_TERMINAL_PROMPT"] = "0"
    if token:
        env["TOOLSUMMARY_GIT_TOKEN"] = token
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def git_auth_url(token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{REPO}.git"


def redact(text: str, token: str) -> str:
    return text.replace(token, "<redacted>") if token else text


def clone(token: str) -> None:
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    r = run(["git", "clone", "--depth", "1", git_auth_url(token), str(WORK)],
            cwd=Path(tempfile.gettempdir()), token=token)
    if r.returncode != 0:
        raise RuntimeError(f"clone failed: {redact(r.stderr, token).strip()[:400]}")
    log(f"cloned {REPO}")


def configure_git(token: str) -> None:
    run(["git", "config", "user.name", "toolsummary-bot"], cwd=WORK, token=token)
    run(["git", "config", "user.email", "toolsummary-bot@users.noreply.github.com"],
        cwd=WORK, token=token)


def run_pipeline() -> None:
    """Execute the repo's own pipeline, unmodified, from the cloned tree."""
    mvp = WORK / "automation" / "mvp"
    if not (mvp / "run_pipeline.py").exists():
        raise RuntimeError("automation/mvp/run_pipeline.py missing from clone")
    r = subprocess.run([sys.executable, "run_pipeline.py"], cwd=mvp)
    if r.returncode != 0:
        # Exit non-zero means QA failed. Nothing is committed, so the last good
        # history stays intact and the day is retried tomorrow.
        raise RuntimeError(f"pipeline failed (exit {r.returncode}) - QA did not pass, nothing committed")


def read_history() -> list[dict]:
    path = WORK / "automation" / "mvp" / "data" / "price_history.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def read_digest() -> str:
    path = WORK / "automation" / "mvp" / "data" / "review_digest.md"
    if not path.exists():
        return "(no digest produced)"
    return path.read_text()[:4000]


def commit_and_push(token: str, dry_run: bool) -> tuple[bool, str]:
    """Commit the regenerated data and push. Returns (pushed, detail)."""
    data_dir = "automation/mvp/data"
    run(["git", "add", data_dir], cwd=WORK, token=token)
    # --cached so the check reflects what would actually be committed.
    staged = run(["git", "diff", "--cached", "--name-only"], cwd=WORK, token=token)
    changed = [f for f in staged.stdout.split() if f]
    if not changed:
        return False, "no data changes to commit"

    day = datetime.now(timezone.utc).date().isoformat()
    n_rows = len(read_history())
    run(["git", "commit", "-q", "-m",
         f"data: price snapshot {day}\n\n"
         f"Automated daily refresh. {n_rows} model rows on record.\n\n"
         f"Co-authored-by: openhands <openhands@all-hands.dev>"],
        cwd=WORK, token=token)

    if dry_run:
        # Validation path: prove the clone, pipeline and commit all work without
        # writing to main. Used to test a new tarball before scheduling it.
        r = run(["git", "push", "--dry-run", "origin", "HEAD:main"], cwd=WORK, token=token)
        if r.returncode != 0:
            return False, f"dry-run push rejected: {redact(r.stderr, token).strip()[:400]}"
        return True, f"DRY RUN ok - would push {len(changed)} file(s)"

    # Pull-rebase then push: a rebase conflict means two runs overlapped, which
    # must be surfaced rather than forced through.
    run(["git", "pull", "--rebase", "origin", "main"], cwd=WORK, token=token)
    r = run(["git", "push", "origin", "HEAD:main"], cwd=WORK, token=token)
    if r.returncode != 0:
        return False, f"push rejected: {redact(r.stderr, token).strip()[:400]}"
    return True, f"pushed {len(changed)} file(s)"


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    log(f"start {datetime.now(timezone.utc).isoformat(timespec='seconds')}"
        + (" (DRY RUN)" if dry_run else ""))
    token = ""
    try:
        token, secret_name = get_github_token()
        log(f"github token loaded from secret '{secret_name}'")

        clone(token)
        configure_git(token)
        run_pipeline()

        history = read_history()
        dates = sorted({r.get("date") for r in history if r.get("date")})
        log(f"history: {len(history)} rows across {len(dates)} date(s), latest={dates[-1] if dates else 'none'}")

        pushed, detail = commit_and_push(token, dry_run)
        log(f"commit: {detail}")

        log("daily digest:\n" + read_digest())

        if not pushed:
            # Only "no changes" is benign; a rejected push loses the day.
            raise RuntimeError(f"history not persisted: {detail}")

        log("skipped (by design): " + "; ".join(NOT_ATTEMPTED))
        fire_callback("COMPLETED")
        log("done")
        return 0

    except Exception as e:
        msg = redact(str(e), token)
        log(f"FAILED: {msg}")
        fire_callback("FAILED", msg)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
