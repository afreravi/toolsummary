#!/usr/bin/env python3
"""Publish the built site to the live web root, from inside a sandbox.

Clones the repo at the branch being tested, runs the pipeline to produce
site/, then publishes over SFTP. Publishing is read-only-safe: it uploads only
files that changed and prunes only pages the build no longer emits, so an
unchanged re-run is a no-op.

Mode is controlled by TOOLSUMMARY_PUBLISH_MODE in the environment:
  verify   - connect and report the remote path, change nothing
  dry-run  - report what would change, change nothing
  (unset)  - publish

Prints a JSON summary on one line.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = "afreravi/toolsummary"
BRANCH = os.environ.get("TOOLSUMMARY_BRANCH", "dev-branch")
WORK = Path(tempfile.gettempdir()) / "toolsummary-publish"

SECRET_NAMES = ("github_token", "GITHUB_TOKEN", "TOOLSUMMARY_GITHUB_TOKEN", "Toolsummary")


def log(msg):
    print(f"[publish-run] {msg}", flush=True)


def get_secret(name):
    if os.environ.get(name):
        return os.environ[name]
    import urllib.error
    import urllib.request
    key = os.environ.get("SESSION_API_KEY") or os.environ.get("OH_SESSION_API_KEYS_0", "")
    if not key:
        return None
    url = os.environ.get("AGENT_SERVER_URL", "").rstrip("/")
    if url:
        endpoint = f"{url}/api/settings/secrets/{name}"
    else:
        api = os.environ.get("OPENHANDS_CLOUD_API_URL", "").rstrip("/")
        sandbox = os.environ.get("SANDBOX_ID", "")
        if not api or not sandbox:
            return None
        endpoint = f"{api}/api/v1/sandboxes/{sandbox}/settings/secrets/{name}"
    req = urllib.request.Request(endpoint, headers={"X-Session-API-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode().rstrip("\r\n")
    except Exception:
        return None


def fire_callback(status="COMPLETED", error=None):
    import urllib.request
    url = os.environ.get("AUTOMATION_CALLBACK_URL", "")
    if not url:
        return
    body = {"status": status, "run_id": os.environ.get("AUTOMATION_RUN_ID", "")}
    if error:
        body["error"] = error[:2000]
    bearer = os.environ.get("AUTOMATION_CALLBACK_API_KEY", "")
    session = os.environ.get("SESSION_API_KEY") or os.environ.get("OH_SESSION_API_KEYS_0", "")
    attempts = []
    if bearer:
        attempts.append({"Authorization": f"Bearer {bearer}"})
    if session:
        attempts.append({"X-Session-API-Key": session})
    for headers in attempts:
        try:
            urllib.request.urlopen(urllib.request.Request(
                url, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", **headers}), timeout=30)
            return
        except Exception as e:
            log(f"callback attempt failed (non-fatal): {e}")


def github_token():
    """First token that actually authenticates.

    Presence is not validity: the sandbox holds several token-shaped secrets
    and at least one is rejected by GitHub.
    """
    import urllib.request
    for name in SECRET_NAMES:
        value = get_secret(name)
        if not value:
            continue
        req = urllib.request.Request(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {value}",
                     "Accept": "application/vnd.github+json",
                     "User-Agent": "toolsummary-publish"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200:
                    log(f"github token from '{name}'")
                    return value
        except Exception:
            log(f"token '{name}' rejected by GitHub")
    return ""


def main():
    result = {"ok": False}
    try:
        mode = os.environ.get("TOOLSUMMARY_PUBLISH_MODE", "").strip()
        # The automation API has no env-var field, so the mode can also be
        # pinned by a MODE file shipped in the tarball. Env wins when set.
        mode_file = Path(__file__).resolve().parent / "MODE"
        if not mode and mode_file.exists():
            mode = mode_file.read_text().strip()
        log(f"branch={BRANCH} mode={mode or 'publish'}")

        token = github_token()
        if not token:
            result["error"] = "no working GitHub token"
            log("RESULT " + json.dumps(result))
            fire_callback("FAILED", result["error"])
            return 1

        if WORK.exists():
            import shutil
            shutil.rmtree(WORK, ignore_errors=True)
        url = f"https://x-access-token:{token}@github.com/{REPO}.git"
        r = subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, url, str(WORK)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            result["error"] = f"clone failed: {r.stderr.replace(token, '<redacted>').strip()[:300]}"
            log("RESULT " + json.dumps(result))
            fire_callback("FAILED", result["error"])
            return 1
        log(f"cloned {REPO}@{BRANCH}")

        mvp = WORK / "automation" / "mvp"
        if mode != "verify":
            r = subprocess.run([sys.executable, "run_pipeline.py"], cwd=mvp,
                               capture_output=True, text=True, timeout=1800)
            tail = (r.stdout or "").strip().splitlines()[-3:]
            for line in tail:
                log(f"  {line}")
            if r.returncode != 0:
                result["error"] = f"pipeline failed (exit {r.returncode})"
                log("RESULT " + json.dumps(result))
                fire_callback("FAILED", result["error"])
                return 1
            log("pipeline OK, site built")

        cmd = [sys.executable, str(WORK / "automation" / "deploy" / "publish_tarball.py")]
        if mode in ("verify", "dry-run"):
            cmd.append(f"--{mode}")
        r = subprocess.run(cmd, cwd=WORK, capture_output=True, text=True, timeout=1800)
        out = (r.stdout or "").strip()
        for line in out.splitlines()[-12:]:
            log(f"  {line}")
        result["publish"] = out.splitlines()[-1] if out else ""
        result["ok"] = r.returncode == 0
        if r.returncode != 0:
            result["error"] = (r.stderr or "").strip()[:300] or result["publish"]

        log("RESULT " + json.dumps(result))
        fire_callback("COMPLETED" if result["ok"] else "FAILED", result.get("error"))
        return 0 if result["ok"] else 1
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        log("RESULT " + json.dumps(result))
        fire_callback("FAILED", result["error"])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
