#!/usr/bin/env python3
"""Run every SFTP test suite and summarise.

No credentials, no sandbox, no network: each suite starts its own local
paramiko SFTP server. Safe to run before dispatching a publish automation.

    python3 tests/sftp/run_all.py
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

SUITES = [
    ("guards", "test_guards.py", "socket timeout, symlink loop, worker bound"),
    ("upload logic", "test_upload_logic.py", "retry, hardening, error reporting"),
    ("integration", "test_integration.py", "verify, dry-run, publish, prune"),
    ("stall & scale", "test_stall_and_scale.py", "stalled host, 1000 files"),
]


def main() -> int:
    results = []
    for label, script, desc in SUITES:
        print(f"\n{'=' * 70}\n{label}: {desc}\n{'=' * 70}", flush=True)
        r = subprocess.run([sys.executable, "-u", str(HERE / script)],
                           cwd=HERE.parents[1])
        results.append((label, r.returncode))

    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    for label, rc in results:
        print(f"  {'PASS' if rc == 0 else 'FAIL'}  {label}")
    failed = [l for l, rc in results if rc != 0]
    print(f"\n{'all suites passed' if not failed else 'FAILED: ' + ', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
