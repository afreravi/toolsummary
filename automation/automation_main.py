#!/usr/bin/env python3
"""OpenHands automation entrypoint.

Deterministic by design: no LLM is called. This is a fixed data transform on a
daily schedule, so an agent preset would burn tokens for no benefit and add a
non-deterministic step to a pipeline whose whole value is reproducibility.

Sequence: fetch pricing -> quality gate -> build pages -> QA -> publish to the
site over SFTP -> report. The pipeline exits non-zero if QA fails, and nothing
is published in that case, so a bad data day degrades to "yesterday's site
stays up" rather than "garbage goes live".

Daily review is a markdown digest the operator reads; approving it is the 10%
human step (see REVIEW.md).
"""
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PIPELINE = ROOT / "mvp"


def get_secret(name: str) -> str:
    """Fetch a named secret from the agent server."""
    url = os.environ.get("AGENT_SERVER_URL", "").rstrip("/")
    key = os.environ.get("SESSION_API_KEY") or os.environ.get("OH_SESSION_API_KEYS_0", "")
    req = urllib.request.Request(
        f"{url}/api/settings/secrets/{name}", headers={"X-Session-API-Key": key}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode().strip()


def fire_callback(status: str = "COMPLETED", error: str | None = None) -> None:
    """Signal run completion. Must be called on every exit path."""
    url = os.environ.get("AUTOMATION_CALLBACK_URL", "")
    if not url:
        return
    body = {"status": status, "run_id": os.environ.get("AUTOMATION_RUN_ID", "")}
    if error:
        body["error"] = error[:2000]
    try:
        urllib.request.urlopen(urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.environ.get('AUTOMATION_CALLBACK_API_KEY', '')}",
            },
        ), timeout=30)
    except Exception as e:
        print(f"[callback] error: {e}")


def run_pipeline() -> int:
    r = subprocess.run([sys.executable, "run_pipeline.py"], cwd=PIPELINE)
    return r.returncode


def publish(site_dir: Path) -> str:
    """Upload the built site. Returns a human-readable result line.

    Publish target is intentionally explicit: if SFTP credentials are absent
    the run still reports success for the build and skips the upload, so a
    missing secret can never take the live site down.
    """
    host = os.environ.get("TOOLSUMMARY_SFTP_HOST")
    if not host:
        try:
            host = get_secret("TOOLSUMMARY_SFTP_HOST")
        except Exception:
            return "publish: skipped (no SFTP host secret configured) - build artifacts kept in workspace"

    port = os.environ.get("TOOLSUMMARY_SFTP_PORT", "22")
    user = os.environ.get("TOOLSUMMARY_SFTP_USER", "")
    remote = os.environ.get("TOOLSUMMARY_SFTP_PATH", "/public_html")
    for name, var in (("TOOLSUMMARY_SFTP_USER", user),):
        if not var:
            try:
                user = get_secret(name)
            except Exception:
                return "publish: skipped (no SFTP user secret configured)"

    key_path = ROOT / ".sftp_key"
    try:
        key_path.write_text(get_secret("TOOLSUMMARY_SFTP_KEY"))
        key_path.chmod(0o600)
    except Exception:
        return "publish: skipped (no SFTP key secret configured)"

    # rsync over ssh is the safest incremental upload: deleted pages are pruned
    # with --delete so the live sitemap can never list an orphan.
    cmd = [
        "rsync", "-az", "--delete", "--chmod=D755,F644",
        "-e", f"ssh -i {key_path} -p {port} -o StrictHostKeyChecking=accept-new",
        f"{site_dir}/", f"{user}@{host}:{remote}/",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            return f"publish: FAILED (rsync exit {r.returncode}) {r.stderr.strip()[:300]}"
        return f"publish: uploaded {len(list(site_dir.rglob('*.html')))} pages to {remote}"
    finally:
        key_path.unlink(missing_ok=True)


def main() -> int:
    try:
        print(f"[automation] starting {datetime.now(timezone.utc).isoformat()}")
        rc = run_pipeline()
        if rc != 0:
            fire_callback("FAILED", "pipeline QA failed - nothing published")
            return rc

        site = PIPELINE / "site"
        result = publish(site)
        print(f"[automation] {result}")

        digest = (PIPELINE / "data" / "review_digest.md")
        if digest.exists():
            print("\n" + digest.read_text()[:4000])

        fire_callback("COMPLETED")
        return 0
    except Exception as e:
        print(f"[automation] fatal: {e}", file=sys.stderr)
        fire_callback("FAILED", str(e))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
