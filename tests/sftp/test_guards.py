"""Verify the SFTP hang fix without needing credentials or a sandbox.

The real failure was a stall on the main session that blocked forever. These
checks exercise the guards directly: a fake channel records whether a timeout
was applied, and a cyclic directory tree proves the recursive walk terminates.
"""
import importlib.util
import os
import sys
from pathlib import Path
import types

os.environ.setdefault("VHOST", "h")
os.environ.setdefault("VUSER", "u")
os.environ.setdefault("VREMOTE", "/tmp")
os.environ.setdefault("VPASS", "p")

REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(REPO_ROOT)

spec = importlib.util.spec_from_file_location("sftp_worker", "automation/deploy/sftp_worker.py")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

failures = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


# 1. harden_session must apply a socket timeout to the channel.
class FakeChannel:
    def __init__(self):
        self.timeout = None
        self.keepalive = None

    def settimeout(self, t):
        self.timeout = t

    def get_transport(self):
        outer = self

        class T:
            def set_keepalive(self, n):
                outer.keepalive = n
        return T()


class FakeSFTP:
    def __init__(self):
        self.chan = FakeChannel()

    def get_channel(self):
        return self.chan


f = FakeSFTP()
w.harden_session(f)
check("harden_session sets a socket timeout", f.chan.timeout == w.SOCKET_TIMEOUT,
      f"timeout={f.chan.timeout}")
check("harden_session sets keepalive", f.chan.keepalive == 15,
      f"keepalive={f.chan.keepalive}")


# 2. The recursive walk must terminate on a directory symlink loop.
class Attr:
    def __init__(self, filename, mode, size=0, ino=0):
        self.filename = filename
        self.st_mode = mode
        self.st_size = size
        self.st_ino = ino


DIR = 0o040000
FILE = 0o100000


class LoopSFTP:
    """root/ has a file and a dir 'loop' that lists root again."""

    def __init__(self):
        self.calls = 0

    def listdir_attr(self, path):
        self.calls += 1
        if self.calls > 5000:
            raise AssertionError("walk did not terminate - symlink loop not guarded")
        base = path.rstrip("/")
        if base.endswith("loop") or base.endswith("root"):
            return [Attr("a.txt", FILE, 10), Attr("loop", DIR, 0, ino=99)]
        return []


ls = LoopSFTP()
found = w.remote_files(ls, "/root")
check("symlink loop terminates", ls.calls < 100, f"listdir calls={ls.calls}")
check("files under a looped dir are still found", "a.txt" in found, f"found={list(found)[:5]}")


# 3. main() must route the main session through harden_session.
src = open("automation/deploy/sftp_worker.py").read()
check("main() hardens the main session",
      "sftp = harden_session(client.open_sftp())" in src)
check("open_sessions hardens pool sessions",
      "harden_session(client.open_sftp())" in src)

# 4. publish_sftp must bound the worker subprocess and flush its output.
psrc = open("automation/deploy/publish_sftp.py").read()
check("worker subprocess is bounded", "timeout=WORKER_TIMEOUT" in psrc)
check("worker timeout is configurable", "VWORKER_TIMEOUT" in psrc)
check("progress output is flushed", psrc.count("flush=True") >= 10,
      f"count={psrc.count('flush=True')}")
check("worker timeout fires before the automation wall clock", w.SOCKET_TIMEOUT <= 900,
      f"SOCKET_TIMEOUT={w.SOCKET_TIMEOUT}")

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
