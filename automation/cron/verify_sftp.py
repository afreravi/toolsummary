"""Verify the SFTP publishing credentials from inside an automation run.

Reads the five secrets, installs paramiko, then opens a real SFTP session and
lists the remote web root. Prints a single summary line and never prints a
secret value, hostname, or password.

    python3 automation/cron/verify_sftp.py

Exit code is 0 when the login succeeds, 1 otherwise.
"""

import os
import subprocess
import sys
import urllib.request

SECRET_NAMES = {
    "host": "TOOLSUMMARY_SFTP_HOST",
    "user": "TOOLSUMMARY_SFTP_USER",
    "password": "TOOLSUMMARY_SFTP_KEY",
    "port": "TOOLSUMMARY_SFTP_PORT",
    "remote": "Remote_Path",
}

CHILD = r'''
import os, paramiko
h, p, u, s, r = (os.environ["VH"], int(os.environ["VP"]), os.environ["VU"],
                 os.environ["VS"], os.environ["VR"])
res = []
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    c.connect(hostname=h, port=p, username=u, password=s, timeout=30,
              allow_agent=False, look_for_keys=False)
except paramiko.AuthenticationException:
    print("SUMMARY AUTH_FAILED wrong user or password"); raise SystemExit(0)
except Exception as e:
    print("SUMMARY CONNECT_FAIL " + type(e).__name__); raise SystemExit(0)
res.append("SSH_AUTH=OK")
try:
    sf = c.open_sftp()
    res.append("SFTP=OK")
    listed = False
    for cand in (r, r.rstrip("/"), "/" + r.strip("/")):
        try:
            entries = sf.listdir(cand)
            res.append("files=%d" % len(entries))
            res.append("html=%d" % len([e for e in entries if e.endswith(".html")]))
            probe = cand.rstrip("/") + "/.ts_write_test"
            with sf.open(probe, "w") as fh:
                fh.write("ok")
            sf.remove(probe)
            res.append("WRITE=OK")
            listed = True
            break
        except IOError:
            pass
    res.append("REMOTE_PATH=" + ("FOUND" if listed else "NOT_FOUND"))
    sf.close(); c.close()
except Exception as e:
    res.append("SFTP_FAIL=" + type(e).__name__)
print("SUMMARY " + " ".join(res))
'''


def secret(name):
    url = (f"{os.environ['OPENHANDS_CLOUD_API_URL'].rstrip('/')}"
           f"/api/v1/sandboxes/{os.environ['SANDBOX_ID']}/settings/secrets/{name}")
    key = os.environ.get("SESSION_API_KEY") or os.environ.get("OH_SESSION_API_KEYS_0", "")
    req = urllib.request.Request(url, headers={"X-Session-API-Key": key})
    return urllib.request.urlopen(req, timeout=20).read().decode().rstrip("\r\n")


def normalise_host(raw):
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("/", 1)[0]
    if ":" in raw and raw.rsplit(":", 1)[1].isdigit():
        raw = raw.rsplit(":", 1)[0]
    return raw


def main():
    try:
        values = {k: secret(v) for k, v in SECRET_NAMES.items()}
    except Exception as e:
        print(f"SUMMARY SECRET_READ_FAIL {type(e).__name__}")
        return 1

    missing = [n for k, n in SECRET_NAMES.items() if not values.get(k)]
    if missing:
        print(f"SUMMARY MISSING_SECRETS {','.join(missing)}")
        return 1

    host = normalise_host(values["host"])
    port = values["port"]

    # paramiko must be installed in one process and imported in another.
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                    "--disable-pip-version-check", "paramiko"], check=False)

    child_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_verify_child.py")
    with open(child_path, "w") as fh:
        fh.write(CHILD)
    try:
        env = dict(os.environ, VH=host, VP=port, VU=values["user"],
                   VS=values["password"], VR=values["remote"])
        proc = subprocess.run([sys.executable, child_path], capture_output=True,
                              text=True, timeout=300, env=env)
        output = (proc.stdout or "") + (proc.stderr or "")
    finally:
        if os.path.exists(child_path):
            os.remove(child_path)

    for line in output.splitlines():
        if line.startswith("SUMMARY "):
            print(line.strip())
            return 0 if "SSH_AUTH=OK" in line and "WRITE=OK" in line else 1
    print("SUMMARY NO_OUTPUT " + " ".join(output.split()[-3:])[:120])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
