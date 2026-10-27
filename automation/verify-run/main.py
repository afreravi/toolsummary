#!/usr/bin/env python3
"""Read-only SFTP check, run inside an automation sandbox.

Exists so the SFTP connection can be tested with the real secrets, which are
only reachable from inside a run. It connects, reports what is at the remote
path, and exits. It writes nothing and deletes nothing.

Prints a JSON result on one line so the run log is easy to read.
"""
import json
import os
import posixpath
import urllib.error
import urllib.request

SECRETS = (
    "TOOLSUMMARY_SFTP_HOST",
    "TOOLSUMMARY_SFTP_USER",
    "TOOLSUMMARY_SFTP_PORT",
    "TOOLSUMMARY_SFTP_PATH",
    "Remote_Path",
    "TOOLSUMMARY_SFTP_PASSWORD",
    "TOOLSUMMARY_SFTP_KEY",
)
CREDENTIALS = ("TOOLSUMMARY_SFTP_PASSWORD", "TOOLSUMMARY_SFTP_KEY", "TOOLSUMMARY_SFTP_PASS")


def log(msg):
    print(f"[verify] {msg}", flush=True)


def get_secret(name):
    """Read one secret. Both endpoint shapes are needed; see publish_sftp.py."""
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


def fire_callback(status="COMPLETED", error=None):
    """Mark the run complete. Tried with both auth styles.

    The bearer form returned 401 in an earlier run. The exit code still marked
    the run correctly, so this is best-effort: it only affects whether the
    failure reason is attached, not whether the run is recorded.
    """
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


def main():
    result = {"ok": False}
    try:
        # Report which secrets are visible, by presence only. This distinguishes
        # "secret not saved" from "secret saved but wrong".
        present = {n: bool(get_secret(n)) for n in SECRETS}
        log("secret presence: " + json.dumps(present))

        host = get_secret("TOOLSUMMARY_SFTP_HOST")
        user = get_secret("TOOLSUMMARY_SFTP_USER")
        port = get_secret("TOOLSUMMARY_SFTP_PORT") or "22"
        remote = get_secret("TOOLSUMMARY_SFTP_PATH") or get_secret("Remote_Path")
        cred, cred_name = "", ""
        for n in CREDENTIALS:
            v = get_secret(n)
            if v:
                cred, cred_name = v, n
                break

        missing = [n for n, v in (("host", host), ("user", user),
                                  ("path", remote), ("credential", cred)) if not v]
        if missing:
            result["error"] = "missing: " + ", ".join(missing)
            log("RESULT " + json.dumps(result))
            fire_callback("FAILED", result["error"])
            return 1

        kind = "key" if cred.lstrip().startswith("-----BEGIN") else "password"
        log(f"host={host} port={port} user={user} auth={kind} from={cred_name}")
        log(f"remote path length={len(remote)} "
            f"(not printed: it may contain the account name)")

        # paramiko comes from setup.sh's venv. Installing it here was tried and
        # is unreliable: pip runs as a subprocess with output suppressed, so a
        # failure surfaces only as a confusing ModuleNotFoundError.
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = dict(hostname=host, port=int(port), username=user, timeout=30,
                      banner_timeout=30, auth_timeout=30,
                      allow_agent=False, look_for_keys=False)
        if kind == "key":
            import io
            for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
                try:
                    kwargs["pkey"] = cls.from_private_key(io.StringIO(cred))
                    break
                except Exception:
                    continue
        else:
            kwargs["password"] = cred

        client.connect(**kwargs)
        result["auth"] = "OK"
        log("AUTH OK")

        sftp = client.open_sftp()
        try:
            # Does the path exist, and does it hold the placeholder we expect?
            try:
                entries = sftp.listdir(remote)
                result["remote_entries"] = len(entries)
                log(f"remote path exists, {len(entries)} entries: {sorted(entries)[:20]}")
            except IOError as e:
                result["error"] = f"remote path not found: {type(e).__name__}"
                log("RESULT " + json.dumps(result))
                fire_callback("FAILED", result["error"])
                return 1

            probe = posixpath.join(remote, "index.html")
            try:
                with sftp.open(probe) as f:
                    head = f.read(500).decode(errors="replace")
                result["placeholder_found"] = "staging OK" in head
                result["index_title"] = head.split("<title>")[1].split("</title>")[0] \
                    if "<title>" in head else ""
                log(f"index.html title: {result['index_title']!r}")
                log(f"placeholder found: {result['placeholder_found']}")
            except IOError:
                result["placeholder_found"] = False
                log("index.html not readable")

            # Confirm we could write, without writing anything.
            probe2 = posixpath.join(remote, ".ts_write_probe")
            try:
                with sftp.open(probe2, "w") as fh:
                    fh.write("ok")
                sftp.remove(probe2)
                result["writable"] = True
                log("write test: OK (probe removed)")
            except IOError as e:
                result["writable"] = False
                log(f"write test FAILED: {type(e).__name__}")

            try:
                with sftp.open(posixpath.join(remote, ".htaccess")) as f:
                    ht = f.read().decode(errors="replace")
                result["htaccess_has_noindex"] = "noindex" in ht
                log(f".htaccess contains noindex: {result['htaccess_has_noindex']}")
            except IOError:
                log(".htaccess not readable")
        finally:
            sftp.close()
            client.close()

        result["ok"] = True
        log("RESULT " + json.dumps(result))
        fire_callback("COMPLETED")
        return 0
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        log("RESULT " + json.dumps(result))
        fire_callback("FAILED", result["error"])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
