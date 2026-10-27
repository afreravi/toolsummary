"""Two things the real host failure needs: bounded time on a stalled server,
and a full-size publish (~1000 files) inside the automation wall clock.

The original bug was an unbounded block, so the important assertion is that a
server which never answers still produces a clean failure in bounded time.
"""
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests" / "sftp"))
os.chdir(REPO_ROOT)
import test_integration as T


class StallingInterface(T.ServerInterface):
    """Answers auth and stat, then never replies to a directory listing."""

    def list_folder(self, path):
        T.STOP.wait()
        return []


def run_publish(env_extra, site, timeout=300):
    env = dict(os.environ)
    env.update(env_extra)
    env["VLOCAL"] = site
    t = time.time()
    try:
        p = subprocess.run(
            [sys.executable, "-u", str(REPO_ROOT / "automation/deploy/publish_sftp.py")],
            capture_output=True, text=True, env=env, timeout=timeout,
            cwd=str(REPO_ROOT))
        return p.returncode, p.stdout.strip(), round(time.time() - t, 1)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", "", round(time.time() - t, 1)


def start_server(tmp, interface):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)
    port = sock.getsockname()[1]
    stop = threading.Event()

    orig = T.ServerInterface
    T.ServerInterface = interface

    def serve():
        while not stop.is_set():
            try:
                sock.settimeout(1.0)
                conn, _ = sock.accept()
            except (socket.timeout, OSError):
                continue
            threading.Thread(target=T.handle_conn, args=(conn, tmp), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.4)
    return sock, port, stop, orig


failures = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


# ---- Scenario 1: server stalls forever on listdir -------------------------
tmp = tempfile.mkdtemp(prefix="stall-")
remote = os.path.join(tmp, "public_html")
os.makedirs(remote, exist_ok=True)
site = T.build_site(os.path.join(tmp, "site"), n_files=5)

T.STOP = threading.Event()
sock, port, stop, orig = start_server(tmp, StallingInterface)
env = {"TOOLSUMMARY_SFTP_HOST": "127.0.0.1", "TOOLSUMMARY_SFTP_USER": T.USER,
       "TOOLSUMMARY_SFTP_PORT": str(port), "TOOLSUMMARY_SFTP_PASSWORD": T.PASSWORD,
       "TOOLSUMMARY_SFTP_PATH": "/public_html", "VWORKER_TIMEOUT": "90"}
rc, out, secs = run_publish(env, site, timeout=240)
check("stalled server does not hang forever", rc != "TIMEOUT", f"rc={rc} {secs}s")
check("stalled server fails within the socket timeout budget", secs < 200, f"{secs}s")
check("stall is reported, not silent", ("TIMEOUT" in out.upper() or "FAILED" in out.upper()
                                       or "timed out" in out.lower()),
      f"out={out[-160:]!r}")
T.STOP.set()
stop.set(); sock.close()
T.ServerInterface = orig
shutil.rmtree(tmp, ignore_errors=True)

# ---- Scenario 2: ~1000 file publish inside the wall clock -----------------
tmp = tempfile.mkdtemp(prefix="scale-")
remote = os.path.join(tmp, "public_html")
os.makedirs(remote, exist_ok=True)
site = T.build_site(os.path.join(tmp, "site"), n_files=1000)

T.STOP = threading.Event()
sock, port, stop, orig = start_server(tmp, T.ServerInterface)
env = {"TOOLSUMMARY_SFTP_HOST": "127.0.0.1", "TOOLSUMMARY_SFTP_USER": T.USER,
       "TOOLSUMMARY_SFTP_PORT": str(port), "TOOLSUMMARY_SFTP_PASSWORD": T.PASSWORD,
       "TOOLSUMMARY_SFTP_PATH": "/public_html"}
rc, out, secs = run_publish(env, site, timeout=900)
check("1000-file publish succeeds", rc == 0, f"rc={rc} {secs}s out={out[-200:]!r}")
check("1000-file publish fits the wall clock", secs < 600, f"{secs}s")

local = {os.path.relpath(os.path.join(dp, fn), site)
         for dp, _, fns in os.walk(site) for fn in fns}
remote_set = {os.path.relpath(os.path.join(dp, fn), remote)
              for dp, _, fns in os.walk(remote) for fn in fns}
check("every file of the 1000 landed", local <= remote_set,
      f"local={len(local)} remote={len(remote_set)} missing={sorted(local - remote_set)[:3]}")

# Second run with nothing changed should be fast (no re-upload).
rc2, out2, secs2 = run_publish(env, site, timeout=900)
check("no-change republish is quick", rc2 == 0 and secs2 < max(60, secs / 2),
      f"first={secs}s second={secs2}s")

stop.set(); sock.close()
T.ServerInterface = orig
shutil.rmtree(tmp, ignore_errors=True)

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
