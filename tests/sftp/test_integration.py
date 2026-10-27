"""End-to-end test of the publish uploader against a real SFTP server.

Runs a local paramiko SFTP server backed by a temp directory, then drives the
real worker through verify, dry-run, full publish, and orphan prune. This is
the closest thing to the live host that does not need the production secrets.
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

import paramiko

REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT / "automation/deploy"))

HOST_KEY = paramiko.RSAKey.generate(2048)
USER = "tester"
PASSWORD = "secret"


class Handle(paramiko.SFTPHandle):
    def stat(self):
        f = self.readfile or self.writefile
        try:
            return paramiko.SFTPAttributes.from_stat(os.fstat(f.fileno()))
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)

    def chattr(self, attr):
        return paramiko.SFTP_OP_UNSUPPORTED


class ServerInterface(paramiko.SFTPServerInterface):
    ROOT = None

    def _real(self, path):
        p = os.path.normpath("/" + path).lstrip("/")
        return os.path.join(self.ROOT, p)

    def list_folder(self, path):
        real = self._real(path)
        try:
            out = []
            for fn in os.listdir(real):
                attr = paramiko.SFTPAttributes.from_stat(os.stat(os.path.join(real, fn)))
                attr.filename = fn
                out.append(attr)
            return out
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)

    def stat(self, path):
        try:
            return paramiko.SFTPAttributes.from_stat(os.stat(self._real(path)))
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)

    lstat = stat

    def open(self, path, flags, attr):
        real = self._real(path)
        # Binary modes: the SFTP protocol carries bytes, so a text-mode file
        # object rejects every write with "write() argument must be str".
        mode = "rb"
        if flags & os.O_WRONLY:
            mode = "wb"
        elif flags & os.O_RDWR:
            mode = "r+b"
        if flags & os.O_APPEND:
            mode = "ab"
        try:
            fd = os.open(real, flags, getattr(attr, "st_mode", None) or 0o644)
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)
        f = os.fdopen(fd, mode)
        # SFTPHandle takes only flags; the file objects are set as attributes.
        h = Handle(flags)
        h.filename = real
        h.readfile = f
        h.writefile = f
        return h

    def remove(self, path):
        try:
            os.remove(self._real(path))
            return paramiko.SFTP_OK
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)

    def mkdir(self, path, attr):
        try:
            os.mkdir(self._real(path))
            return paramiko.SFTP_OK
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)

    def rmdir(self, path):
        try:
            os.rmdir(self._real(path))
            return paramiko.SFTP_OK
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)

    def canonicalize(self, path):
        return os.path.normpath("/" + path)


class SSHServer(paramiko.ServerInterface):
    def __init__(self):
        self.event = threading.Event()

    def check_auth_password(self, username, password):
        if username == USER and password == PASSWORD:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return "password"

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED

    # Deliberately no check_channel_subsystem_request override: paramiko's
    # default invokes the handler registered via set_subsystem_handler, and
    # overriding it (even returning True) stops the SFTP server from starting,
    # which shows up as the client hanging in open_sftp().


def handle_conn(conn, root):
    ServerInterface.ROOT = root
    t = paramiko.Transport(conn)
    t.add_server_key(HOST_KEY)
    t.set_subsystem_handler("sftp", paramiko.SFTPServer, ServerInterface)
    try:
        t.start_server(server=SSHServer())
        # The channel must be accepted explicitly, or the client's open_sftp()
        # blocks forever waiting for the subsystem reply.
        chan = t.accept(20)
        if chan is None:
            return
        chan.settimeout(120)
        while t.is_active():
            time.sleep(0.2)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
    finally:
        try:
            t.close()
        except Exception:
            pass


def serve(sock, root, stop):
    while not stop.is_set():
        try:
            sock.settimeout(1.0)
            conn, _ = sock.accept()
        except (socket.timeout, OSError):
            continue
        threading.Thread(target=handle_conn, args=(conn, root), daemon=True).start()


def build_site(root, n_files=40):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "index.html"), "w") as f:
        f.write("<html>home</html>")
    with open(os.path.join(root, "robots.txt"), "w") as f:
        f.write("User-agent: *\n")
    for i in range(n_files):
        d = os.path.join(root, "model", f"g{i % 5}")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"p{i}.html"), "w") as f:
            f.write(f"<html>page {i}</html>")
    return root


def run_worker(mode, env_extra, timeout=180):
    env = dict(os.environ)
    env.update(env_extra)
    argv = [sys.executable, "-u", str(REPO_ROOT / "automation/deploy/publish_sftp.py")]
    if mode:
        argv.append(mode)
    t = time.time()
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
    return p.returncode, p.stdout.strip(), p.stderr.strip(), round(time.time() - t, 1)


def main():
    tmp = tempfile.mkdtemp(prefix="sftp-test-")
    remote_root = os.path.join(tmp, "public_html")
    site = build_site(os.path.join(tmp, "site"))
    os.makedirs(remote_root, exist_ok=True)

    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)
    port = sock.getsockname()[1]

    stop = threading.Event()
    threading.Thread(target=serve, args=(sock, tmp, stop), daemon=True).start()
    time.sleep(0.5)

    # The server canonicalizes to paths under its ROOT, so the remote path is
    # "/public_html" rather than the local filesystem path.
    base = {
        "TOOLSUMMARY_SFTP_HOST": "127.0.0.1", "TOOLSUMMARY_SFTP_USER": USER,
        "TOOLSUMMARY_SFTP_PORT": str(port), "TOOLSUMMARY_SFTP_PASSWORD": PASSWORD,
        "TOOLSUMMARY_SFTP_PATH": "/public_html", "VLOCAL": site,
    }
    failures = []

    def check(name, cond, extra=""):
        print(("PASS  " if cond else "FAIL  ") + name + (f"  {extra}" if extra else ""))
        if not cond:
            failures.append(name)

    try:
        rc, out, err, secs = run_worker("--verify", base)
        check("verify connects and reports writable", rc == 0 and "auth OK" in out, f"rc={rc} {out[:120]}")

        rc, out, err, secs = run_worker("--dry-run", base)
        check("dry-run counts files to upload", rc == 0 and "would upload" in out, f"rc={rc} {out[:160]}")

        rc, out, err, secs = run_worker("", base)
        check("full publish succeeds", rc == 0 and "uploaded" in out, f"rc={rc} {out[:200]}")
        check("publish finishes well inside the wall clock", secs < 120, f"{secs}s")

        local = {os.path.relpath(os.path.join(dp, fn), site)
                 for dp, _, fns in os.walk(site) for fn in fns}
        remote = {os.path.relpath(os.path.join(dp, fn), remote_root)
                  for dp, _, fns in os.walk(remote_root) for fn in fns}
        check("every local file reached the remote", local <= remote,
              f"missing={sorted(local - remote)[:4]}")
        check("no extra files on the remote", not (remote - local),
              f"extra={sorted(remote - local)[:4]}")
        # Orphan prune: a stale remote file should be removed by the next publish.
        stale = os.path.join(remote_root, "model", "g0", "stale.html")
        with open(stale, "w") as f:
            f.write("old")
        rc, out, err, secs = run_worker("", base)
        check("orphan is pruned on republish", rc == 0 and not os.path.exists(stale),
              f"rc={rc} exists={os.path.exists(stale)}")

        # Idempotence: a second identical publish should be cheap and correct.
        rc, out, err, secs = run_worker("", base)
        check("republish with no changes succeeds", rc == 0, f"rc={rc} {out[:140]}")

        # Bad password must be reported as an auth failure, not a hang.
        bad = dict(base, TOOLSUMMARY_SFTP_PASSWORD="wrong")
        rc, out, err, secs = run_worker("--verify", bad, timeout=90)
        check("wrong password fails fast with a clear reason",
              rc == 1 and "AUTH FAILED" in out and secs < 60, f"rc={rc} {secs}s {out[:120]}")
    except subprocess.TimeoutExpired as e:
        check("worker finished within timeout", False, f"timed out: {e}")
    finally:
        stop.set()
        sock.close()
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
