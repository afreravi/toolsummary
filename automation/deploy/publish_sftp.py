#!/usr/bin/env python3
"""Publish the generated site over SFTP, with safe defaults.

    python3 automation/deploy/publish_sftp.py --verify
    python3 automation/deploy/publish_sftp.py --dry-run
    python3 automation/deploy/publish_sftp.py

--verify  connect and report what is at the remote path. Changes nothing.
--dry-run connect, diff local against remote, report what would change.
(default) connect, upload changed files, prune orphaned managed files.

Refuses to publish to a path that does not look like a web root, so a wrong
secret cannot scatter files across the server. Never prints a credential.

Secrets are read from the agent-server secret store, falling back to the
environment so the script is testable locally.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "automation" / "mvp" / "site"
WORKER = Path(__file__).resolve().parent / "sftp_worker.py"

# Name in the secret store -> name the worker reads.
SECRETS = {
    "TOOLSUMMARY_SFTP_HOST": "VHOST",
    "TOOLSUMMARY_SFTP_USER": "VUSER",
    "TOOLSUMMARY_SFTP_PORT": "VPORT",
    "TOOLSUMMARY_SFTP_PATH": "VREMOTE",
    "Remote_Path": "VREMOTE_FALLBACK",
}

# Credential secret names, most specific first. TOOLSUMMARY_SFTP_KEY is named
# like a private key but has held a password, so it is tried as a password
# fallback rather than assumed to be a key.
CREDENTIAL_SECRETS = (
    "TOOLSUMMARY_SFTP_PASSWORD",
    "TOOLSUMMARY_SFTP_KEY",
    "TOOLSUMMARY_SFTP_PASS",
)

# A wrong remote path is the failure that does real damage, so require one of
# these markers before writing anything. "domains/" covers Hostinger's
# per-site layout, which has no public_html at the top level.
SAFE_PATH_MARKERS = ("public_html", "htdocs", "httpdocs", "domains/", "/www")


def get_secret(name: str) -> str | None:
    """Fetch a named secret, or None if it is not configured.

    Two endpoint shapes exist and both are needed. Local Agent Canvas sets
    AGENT_SERVER_URL and serves secrets under /api/settings/secrets. A cloud
    sandbox does not set it, and serves them under the sandbox-scoped path
    instead. Handling only the first shape silently finds no secrets in the
    scheduled run, which looks like "not configured" rather than a bug.
    """
    if os.environ.get(name):
        return os.environ[name]

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
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None


def resolve(names: dict[str, str]) -> dict[str, str]:
    """Read each secret once, preferring the environment over the store."""
    out = {}
    for secret_name, var in names.items():
        value = os.environ.get(var) or get_secret(secret_name)
        if value:
            out[var] = value
    return out


def resolve_credential() -> tuple[str, str]:
    """Find the credential and decide whether it is a key or a password.

    Returns (value, description). The description names the source that
    actually supplied the value, so a stale environment variable cannot
    masquerade as a stored secret.
    """
    value = os.environ.get("VSECRET")
    if value:
        source = "VSECRET"
    else:
        source = ""
        for secret_name in CREDENTIAL_SECRETS:
            value = os.environ.get(secret_name) or get_secret(secret_name)
            if value:
                source = secret_name
                break
    if not value:
        return "", "missing"
    kind = "key" if is_private_key(value) else "password"
    return value, f"{kind} (from {source})"


def looks_like_web_root(path: str) -> bool:
    low = path.lower()
    return any(m in low for m in SAFE_PATH_MARKERS)


def is_private_key(value: str) -> bool:
    return value.lstrip().startswith("-----BEGIN")


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--verify", action="store_true",
                   help="connect and report only; changes nothing")
    g.add_argument("--dry-run", action="store_true",
                   help="report what would be uploaded, upload nothing")
    ap.add_argument("--allow-any-path", action="store_true",
                    help="skip the web-root path check (not recommended)")
    a = ap.parse_args()

    mode = "verify" if a.verify else "dry-run" if a.dry_run else "publish"

    cfg = resolve(SECRETS)
    remote = cfg.get("VREMOTE") or cfg.get("VREMOTE_FALLBACK")
    secret, auth = resolve_credential()

    missing = [n for n in ("VHOST", "VUSER") if not cfg.get(n)]
    if not remote:
        missing.append("TOOLSUMMARY_SFTP_PATH (or Remote_Path)")
    if not secret:
        missing.append("TOOLSUMMARY_SFTP_PASSWORD or TOOLSUMMARY_SFTP_KEY")
    if missing:
        print("missing configuration: " + ", ".join(missing))
        return 2

    # The remote path secret has been named two different things. Say which one
    # was used rather than silently picking one.
    if "VREMOTE" in cfg:
        print("remote path source: TOOLSUMMARY_SFTP_PATH")
    else:
        print("remote path source: Remote_Path (TOOLSUMMARY_SFTP_PATH is unset)")

    if not looks_like_web_root(remote) and not a.allow_any_path:
        print(f"refusing: remote path does not look like a web root "
              f"(length {len(remote)}). Expected one of {SAFE_PATH_MARKERS}. "
              f"Pass --allow-any-path to override.")
        return 2

    if mode == "publish" and not SITE.is_dir():
        print(f"refusing: no built site at {SITE}. Run build_pages.py first.")
        return 2

    # paramiko must be installed in this process and imported in the worker's.
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-warn-script-location",
                    "--disable-pip-version-check", "paramiko"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    env = dict(os.environ)
    env["VHOST"] = cfg["VHOST"]
    env["VUSER"] = cfg["VUSER"]
    env["VPORT"] = cfg.get("VPORT", "22")
    env["VREMOTE"] = remote
    env["VMODE"] = mode
    env["VLOCAL"] = str(SITE)
    if auth.startswith("key"):
        env["VKEY"] = secret
    else:
        env["VPASS"] = secret

    print(f"mode: {mode} | auth: {auth} | port: {env['VPORT']}")

    proc = subprocess.run([sys.executable, str(WORKER)], capture_output=True,
                          text=True, timeout=900, env=env)
    output = (proc.stdout or "").strip()
    line = output.splitlines()[-1] if output else ""

    try:
        result = json.loads(line)
    except Exception:
        print("worker produced no readable result")
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[-3:]
        for t in tail:
            print("  " + t[:200])
        return 1

    if result.get("auth") == "FAILED":
        print("RESULT: AUTH FAILED - " + result.get("error", ""))
        return 1
    if not result.get("ok"):
        print("RESULT: FAILED - " + str(result.get("error", "unknown")))
        return 1

    if mode == "verify":
        print(f"RESULT: auth OK | remote root exists: "
              f"{result.get('remote_root_exists')} | "
              f"writable: {result.get('writable')} | "
              f"existing files: {result.get('remote_files')} "
              f"({result.get('remote_html')} html)")
        return 0

    if mode == "dry-run":
        print(f"RESULT: would upload {result.get('to_upload')} of "
              f"{result.get('local_files')} files, prune {result.get('orphans')} "
              f"orphans (remote has {result.get('remote_files_before')})")
        for s in result.get("sample_uploads", []):
            print("  upload " + s)
        for s in result.get("sample_orphans", []):
            print("  prune  " + s)
        return 0

    print(f"RESULT: uploaded {result.get('uploaded')} files, "
          f"pruned {result.get('pruned')} orphans")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
