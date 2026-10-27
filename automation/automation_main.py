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
    """Upload the built site over SFTP. Returns a human-readable result line.

    Delegates to automation/deploy/publish_sftp.py, which uploads only changed
    files and prunes pages the build no longer emits. A missing credential
    skips the upload rather than failing the run, so a config problem cannot
    take the live site down.

    TOOLSUMMARY_PUBLISH_MODE=verify|dry-run puts the publisher into a read-only
    mode, which is how a new server gets tested without writing to it.
    """
    publisher = ROOT / "deploy" / "publish_sftp.py"
    if not publisher.exists():
        return "publish: skipped (deploy/publish_sftp.py not found)"

    cmd = [sys.executable, str(publisher)]
    mode = os.environ.get("TOOLSUMMARY_PUBLISH_MODE", "").strip()
    if mode in ("verify", "dry-run"):
        cmd.append(f"--{mode}")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        return "publish: FAILED (timed out after 1800s)"

    out = (r.stdout or "").strip()
    tail = out.splitlines()[-1] if out else ""
    if r.returncode != 0:
        return f"publish: FAILED ({tail or (r.stderr or '').strip()[:300]})"
    return f"publish: {tail}"


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
