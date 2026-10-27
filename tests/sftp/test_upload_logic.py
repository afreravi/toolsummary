"""Test the upload retry and hardening paths with a fake paramiko client.

No network: the point is to prove the changed logic in upload_parallel, which a
mock SFTP server can obscure. Specifically that a failed put retries on a fresh
session, that the fresh session is hardened, that the failure reason survives,
and that a partial failure does not abandon the remaining files.
"""
import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("VHOST", "h")
os.environ.setdefault("VUSER", "u")
os.environ.setdefault("VREMOTE", "/root")
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


class Chan:
    def __init__(self):
        self.timeout = None

    def settimeout(self, t):
        self.timeout = t

    def get_transport(self):
        outer = self

        class T:
            def set_keepalive(self, n):
                outer.keepalive = n
        return T()


class Session:
    """Records puts. `fails` names always fail; `flaky` names fail once.

    `fails`/`flaky` are the shared sets held by the owning Client, so a retry
    on a fresh session sees the same state rather than a private copy.
    """

    def __init__(self, sink, fails=(), flaky=(), hardened=True):
        self.sink = sink
        self.fails = fails
        self.flaky = flaky
        self.chan = Chan()
        self.closed = False
        self.hardened = hardened

    def put(self, local, remote):
        name = remote.rsplit("/", 1)[-1]
        if name in self.fails:
            raise IOError("permanent failure")
        if name in self.flaky:
            self.flaky.discard(name)
            raise IOError("transient failure")
        self.sink.append(name)

    def close(self):
        self.closed = True

    def get_channel(self):
        return self.chan


class Client:
    def __init__(self, fails=(), flaky=()):
        self.sink = []
        self.fails = set(fails)
        self.flaky = set(flaky)
        self.opened = []

    def open_sftp(self):
        s = Session(self.sink, fails=self.fails, flaky=self.flaky)
        self.opened.append(s)
        return s


LOCAL = {n: "/local/" + n for n in ["a.html", "b.html", "c.html", "d.html"]}

# 1. Happy path: every file uploaded, all sessions hardened.
c = Client()
uploaded, errors = w.upload_parallel(c, "/root", LOCAL, sorted(LOCAL), workers=3, result={})
check("happy path uploads everything", sorted(c.sink) == sorted(LOCAL), f"got={sorted(c.sink)}")
check("happy path records no errors", errors == [], f"errors={errors}")
check("every opened session is hardened",
      all(s.chan.timeout == w.SOCKET_TIMEOUT for s in c.opened),
      f"timeouts={[s.chan.timeout for s in c.opened]}")

# 2. A transient failure is retried on a fresh, hardened session.
c = Client(flaky=["b.html"])
res = {}
uploaded, errors = w.upload_parallel(c, "/root", LOCAL, sorted(LOCAL), workers=2, result=res)
check("transient failure is retried successfully", "b.html" in c.sink, f"sink={sorted(c.sink)}")
check("transient failure is not reported as an error", errors == [], f"errors={errors}")
check("retry sessions are hardened too",
      all(s.chan.timeout == w.SOCKET_TIMEOUT for s in c.opened),
      f"timeouts={[s.chan.timeout for s in c.opened]}")

# 3. A permanent failure is recorded with a reason, and other files still land.
c = Client(fails=["c.html"])
res = {}
uploaded, errors = w.upload_parallel(c, "/root", LOCAL, sorted(LOCAL), workers=2, result=res)
check("permanent failure is reported", errors == ["c.html"], f"errors={errors}")
check("other files still upload after a failure",
      {"a.html", "b.html", "d.html"} <= set(c.sink), f"sink={sorted(c.sink)}")
check("failure reason is recorded for diagnosis",
      "permanent failure" in res.get("upload_error_reason", ""),
      f"reason={res.get('upload_error_reason')!r}")

# 4. Partial success must not raise the "every upload failed" error.
res = {}
c = Client(fails=["c.html"])
w.upload_parallel(c, "/root", LOCAL, sorted(LOCAL), workers=2, result=res)
res["uploaded"] = 3
check("partial success does not look like total failure", res["uploaded"] > 0)

# 5. If opening extra sessions fails, work continues on the ones that opened.
class FlakyOpen(Client):
    def open_sftp(self):
        if len(self.opened) >= 2:
            raise IOError("throttled")
        return super().open_sftp()


c = FlakyOpen()
res = {}
uploaded, errors = w.upload_parallel(c, "/root", LOCAL, sorted(LOCAL), workers=6, result=res)
check("partial session pool still uploads everything", sorted(c.sink) == sorted(LOCAL),
      f"sink={sorted(c.sink)}")
check("session open failures are counted", res.get("session_open_failures", 0) > 0,
      f"res={res.get('session_open_failures')}")

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
