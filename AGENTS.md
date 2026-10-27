# Toolsummary — agent notes

LLM API pricing comparison site (toolsummary.com). Free model/comparison pages
are the acquisition surface; the paid product is the API/MCP price-history feed.

## Layout

- `automation/mvp/` — the pipeline. Pure stdlib, no third-party packages.
  `run_pipeline.py` runs fetch → quality gate → price history → build → QA and
  exits non-zero if QA fails. `track_history.py` is the stage that writes the
  append-only price log.
- `automation/cron/main.py` — the scheduled entrypoint. Clones the repo, runs
  the pipeline, commits the regenerated data to `main`, pushes.
- `automation/deploy/package_site.py` — packages the generated site into
  `deploy/toolsummary-site.tar.gz` plus a manifest. The host is not reachable
  over SFTP from the sandbox, so a human downloads the artifact and uploads it.
  See `docs/deploy.md`.
- `.github/workflows/build-site.yml` — builds and packages the site at 06:00
  UTC (after the 04:30 pricing refresh) and uploads it as a downloadable
  artifact. It does not push to `main` or deploy.
- `automation/automation_main.py` — legacy entrypoint that also publishes over
  SFTP. Unused; SFTP auth is rejected by the host (see `docs/publishing.md`).

## Irreplaceable data

`automation/mvp/data/price_history.jsonl` and `price_changes.jsonl` are the one
thing that cannot be regenerated. A day not recorded is gone forever. Never
gitignore them, never delete them to "clean up", and treat a failed push as a
real incident — the sandbox is discarded, so an unpushed snapshot is a lost day.

## Running locally

```bash
cd automation/mvp && python3 run_pipeline.py
```

The site is written to `automation/mvp/site/` (gitignored).

## Scheduled automation

"Toolsummary pricing refresh" — cron `30 4 * * *` UTC, entrypoint
`python3 main.py`, tarball uploaded from `automation/cron/`. It is
deterministic: no LLM is called, so there is no token cost per run.

To change it, edit `automation/cron/main.py`, package it, upload it, and PATCH
the automation's `tarball_path`. Test with `python3 main.py --dry-run` first —
that runs the real clone, pipeline and commit, and only the push is a no-op.

## Secret lookup gotcha

The automation sandbox exposes a different secret set than an interactive
conversation, and it contains more than one token-shaped secret that are **not**
equivalent. `github_token` authenticates; `GITHUB_TOKEN` returns 401. Presence
is not validity, so `automation/cron/main.py` verifies each candidate against
the GitHub API before trusting it. Do not simplify that back to a single
hardcoded name — it has already caused one silent push failure.

## Failure signatures

- `HTTP Error 404` from the secret lookup → the secret name does not exist in
  the automation sandbox. List names via the sandbox secrets endpoint; never
  print values.
- `Invalid username or token` on push → a present-but-invalid token was picked.
- `history not persisted` → the run succeeded up to the push; the day is not
  saved. Re-dispatch after fixing.
- `Timed out: Sandbox not available` → the run never started; no sandbox was
  allocated. Not a code fault, and not worth debugging the automation over.
  Re-dispatch later. Check this string before reading anything into a
  `RUNNING` run that has not moved for 30 minutes.
- `status: SKIPPED` with `daily_sandbox_limit` → the account's daily cap of 20
  sandboxes is spent. Nothing ran, no code is at fault, and re-dispatching will
  skip again until the quota resets or is raised. **Every debug dispatch costs
  one of the 20**, which is why this is easy to exhaust while chasing a bug.
  Prefer one long-lived sandbox and running commands inside it over repeatedly
  dispatching an automation.

## Testing SFTP code without spending sandboxes

Dispatching an automation to test an SFTP change is the slow, quota-burning
path. Get a sandbox once, then run the real code inside it:

```bash
# 1. Dispatch anything that will stay alive, and take its sandbox_id from the run.
# 2. Resolve the agent server URL and session key for that sandbox.
# 3. Run commands through the agent server's bash API:
curl -s -H "X-Session-API-Key: $KEY" -H "Content-Type: application/json" \
  -X POST "$URL/api/bash/execute_bash_command" \
  -d '{"command": "...", "timeout": 120}'
```

Two traps in this that cost real time:

- **The secret lookup only works inside an automation run.** A hand-run process
  has no `OPENHANDS_CLOUD_API_URL` / `SANDBOX_ID`, so `get_secret` returns
  `None` and the script reports "missing configuration" for secrets that are
  in fact set. Export both, plus `SESSION_API_KEY`, before concluding a secret
  is missing.
- **Run unbuffered and redirect to a file.** `execute_bash_command` returns
  only what the process flushed before it ended, so a script that hangs prints
  nothing and looks like it failed before its first line. Use `python3 -u ...
  > /tmp/out 2>&1; echo exit=$?; cat /tmp/out`.

## Publish hang: the real cause

The first publishes stalled at "Starting automation" and expired with no output.
It was not the network, the credentials, or throttling: TCP connected, the SSH
handshake completed, and `stat`/`listdir` answered in under a second.

Only the upload pool's SFTP sessions had a socket timeout. The **main session**
is opened separately in `sftp_worker.main()`, and both the recursive remote
listing and the orphan scan run on it, so one stalled request blocked forever
until the automation's wall clock killed the run. All sessions now go through
`harden_session`, the recursive walk guards against symlink loops, and the
worker subprocess has its own timeout below the automation's.

Two further holes were found and closed while testing the fix:

- The retry path in `upload_parallel` opened its session with a bare
  `client.open_sftp()`, bypassing `harden_session`. A stall in a retry would
  therefore still hang the run — the fix had left one unbounded session behind.
- `remote_files` tracked visited directories by *relative path*. A directory
  symlink to an ancestor appends a path segment at every level, so the path is
  always new and the set never matches. It is now bounded by depth as well as
  by inode, which is the guard that actually terminates the loop.

### Verifying SFTP changes without a sandbox

`tests/sftp/` (see `tests/README.md`) runs the real worker against a local
paramiko SFTP server. It needs no credentials, no sandbox, and no network, and
it reproduces both failure modes that matter: a server that never answers
`listdir` (must fail in bounded time, not hang) and a ~1000-file publish (must
finish well inside the automation wall clock). Run it before dispatching any
SFTP automation:

```bash
python3 tests/sftp/run_all.py
```

The mocks are easy to get subtly wrong in ways that look like production bugs.
Three that cost time: `SFTPHandle` takes only `flags` and needs `readfile` /
`writefile` assigned as attributes; files must be opened in **binary** mode or
every write fails with "write() argument must be str"; and overriding
`check_channel_subsystem_request` stops paramiko's SFTP handler from starting,
so `open_sftp()` hangs on the client side.


## Pushing a commit when the workspace has no GitHub token

The interactive workspace has no `GITHUB_TOKEN`, so `git push` from here prompts
for a password and hangs. The token exists only in the automation sandbox.
`automation/push-run/` is a temporary automation that closes that gap: it ships
a patch in its tarball, clones the repo, applies it, commits, and pushes.

Two things to know before reusing it:

- **The patch must be a plain `git diff` against the remote head**, not
  `git format-patch`. A format-patch header duplicates commits already on the
  remote, so it fails to apply the moment the branch has moved — which it will
  have. Generate with `git diff origin/dev-branch HEAD -- <paths>`, and ship the
  commit subject in `message.txt`.
- **The tarball is frozen at upload.** Editing `fix.patch` locally changes
  nothing until the tarball is re-uploaded and the automation's `tarball_path`
  is PATCHed:

  ```bash
  tar -czf /tmp/push-run.tar.gz -C automation/push-run .
  curl -s -X POST "$HOST/api/automation/v1/uploads?name=push-run" \
    -H "Authorization: Bearer $OPENHANDS_API_KEY" \
    -H "Content-Type: application/gzip" --data-binary @/tmp/push-run.tar.gz
  # then PATCH the automation with the returned tarball_path
  ```

The publish and cron automations do not have this problem: both clone the repo
and run the code from it, so a pushed commit takes effect on the next run.

## Publish throughput: ship one tarball, not ~1,100 files

The live site is ~1,100 files (704 model pages, 400 comparisons, plus the root
files). Uploading them one at a time over SFTP costs a full round trip per file
and this host throttles to roughly one request per second, so a file-by-file
publish takes about twenty minutes. That never fit the automation wall clock:
every real run was killed mid-upload, which is why the site stayed empty for
weeks while the pipeline was in fact generating correct pages.

The host allows non-interactive shell commands over the same SSH session, so the
site is packaged once and unpacked with a single `tar -xzf` on the far side.
`automation/deploy/publish_tarball.py` does this and completes in seconds:

```bash
python3 automation/deploy/publish_tarball.py --verify    # connect, report, change nothing
python3 automation/deploy/publish_tarball.py --dry-run   # package, report, upload nothing
python3 automation/deploy/publish_tarball.py             # publish
```

Guards worth knowing before editing it:

- It refuses a remote path that does not contain a known web-root marker
  (`public_html`, `htdocs`, `httpdocs`, `domains/`, `/www`), so a wrong secret
  cannot scatter files across the server. `--allow-any-path` overrides.
- Pruning is manifest-based, not "delete empty dirs". The archive carries a
  `.ts-manifest` of the page directories the current build emits; the far side
  removes any *other* directory under `model/` or `compare/`. Owner files
  elsewhere in the web root are never touched.
- `.htaccess` is generated by the build and must be uploaded — the placeholder
  in the web root carries a `noindex` header, so forgetting it keeps the site
  out of search results.
- The staging archive is written to `.ts-site.tar.gz` inside the web root and
  removed after extraction; both it and `.ts-manifest` are cleaned up, so a
  completed publish leaves no extra files.

`publish_sftp.py` (per-file, resumable, `--verify` / `--dry-run`) is kept for
small change sets and for `tests/sftp/`, but the daily automation uses the
tarball path.

## The automation service can fail before our code runs

Runs that sit at "Starting automation" and then expire with `Timed out: Sandbox
not available` never reached `main.py`. That is a platform-level provisioning
failure (`status_detail.kind == environment_unavailable`), not a bug in the
publish code, and re-dispatching is the only remedy. Distinguish it from a real
failure by reading `status_detail`:

- `environment_unavailable` — the sandbox never came up; our code did not run.
- `execution_error` with an `exit_code` and stdout — our code ran and failed.
- `timeout` in the `execution` phase — our code ran but exceeded the limit.

## Competitive landscape

`docs/market.md` holds the market read. The short version as of 2026-10-26:
llm-cost.io has already shipped this plan (change tracker with 63 daily
snapshots, weekly report, free model list, cheapest-for-coding guides, batch
pricing, direct-vs-router, agent cost, calculator, RSS, `llms.txt`, free Agent
Data API, $9/mo Pro). Our history holds 4 snapshot dates. `models.dev` serves
8,940 models with `cache_read` pricing for free. Do not write a plan that
assumes price history is an open niche without re-checking the SERP first.

