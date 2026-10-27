# SFTP tests

Runs the real publish code against a local paramiko SFTP server. No
credentials, no sandbox, no network, no third-party packages beyond
`paramiko`, which the deploy code already requires.

```bash
python3 tests/sftp/run_all.py
```

Dispatching a publish automation to test a change costs one of the account's
20 daily sandboxes and takes minutes. This takes seconds and costs nothing, so
run it first.

## What each suite covers

| Suite | Catches |
|---|---|
| `test_guards.py` | A session that is opened without a socket timeout; a directory symlink loop that makes the remote walk run forever; a worker subprocess with no bound |
| `test_upload_logic.py` | A failed upload that does not retry, or retries on an unhardened session; a failure whose reason is discarded; a partial failure that aborts the remaining files |
| `test_integration.py` | Verify/dry-run/publish/prune against a live server; files that go missing or get left behind; a wrong password that hangs instead of failing |
| `test_stall_and_scale.py` | A server that never answers `listdir` (must fail in bounded time, not hang); a ~1000-file publish inside the automation wall clock; a no-change republish that re-uploads everything |

## The mock server is the fragile part

When a suite fails, suspect the mock before the production code. Three bugs
here each looked exactly like a production fault:

- `SFTPHandle(flags, file)` — the constructor takes only `flags`. The file
  objects must be assigned as `readfile` / `writefile` attributes.
- Opening files in text mode. SFTP carries bytes, so every write fails with
  `write() argument must be str`. Use binary modes.
- Overriding `check_channel_subsystem_request` on the `ServerInterface`.
  Paramiko's default is what starts the handler registered by
  `set_subsystem_handler`, so overriding it — even to return `True` — leaves
  the client hanging in `open_sftp()`.

Also note `paramiko` raises `OSError` for most SFTP failures; `IOError` is an
alias of it in Python 3, so catching one catches the other.
