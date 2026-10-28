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
- `automation/deploy/publish_tarball.py` — the publisher the daily run calls.
  Ships the built site as one tarball and extracts it on the host; see
  "Publish throughput" below.
- `.github/workflows/build-site.yml` — builds and packages the site at 06:00
  UTC (after the 04:30 pricing refresh) and uploads it as a downloadable
  artifact. It does not push to `main` or deploy.

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

## Why the publish is a tarball, not a file walk

An earlier per-file publisher (`publish_sftp.py` + `sftp_worker.py`, since
removed) stalled on the live host. It was not the network, the credentials, or
throttling: TCP connected, the SSH handshake completed, and `stat`/`listdir`
answered in under a second. The failure was that every SFTP session had to be
individually bounded, and one unbounded session — a retry path, or the main
session that ran the recursive walk — blocked forever until the automation's
wall clock killed the run. A ~1,100-file upload also cost a round trip per file,
so it never fit the wall clock anyway.

The tarball publisher replaced all of that with one upload and one `tar -xzf`.
If you ever reintroduce a file-by-file path, bound every session's socket
timeout and every recursive walk by both depth and inode.

### Verifying SFTP changes without a sandbox

The per-file publisher and its local paramiko test suite were removed once the
tarball publisher replaced them. The tarball path is short enough to verify
directly against the live host, which changes nothing:

```bash
python3 automation/deploy/publish_tarball.py --verify
```


## Pushing a commit when the workspace has no GitHub token

The interactive workspace has no working `GITHUB_TOKEN`; `github_token` is the
one that authenticates (see "Secret lookup gotcha" above). Push with it
directly rather than through a helper automation:

```bash
git remote set-url origin "https://${github_token}@github.com/afreravi/toolsummary.git"
git push origin HEAD:main
```

The cron and publish paths clone the repo and run the code from it, so a pushed
commit takes effect on the next run. Only the cron *entrypoint* is frozen in its
tarball (see "The cron tarball ships code" above).

## Publish throughput: ship one tarball, not ~1,100 files

The live site is ~1,100 files (704 model pages, 400 comparisons, plus the root
files and the static pages: `/submit/`, `/contact/`, `/trending/`, `/blog/` and
`/about/`, `/privacy/`, `/api/prices.json`, `/blog/feed.xml`). Uploading them one at a time over SFTP costs a full round trip per file
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
  elsewhere in the web root are never touched. The static pages
  (`submit/`, `contact/`, `trending/`, `blog/`, `about/`, `privacy/`, `api/`)
  are top-level files, so they are replaced in place and never pruned.
- `.htaccess` is generated by the build and must be uploaded — the placeholder
  in the web root carries a `noindex` header, so forgetting it keeps the site
  out of search results.
- The staging archive is written to `.ts-site.tar.gz` inside the web root and
  removed after extraction; both it and `.ts-manifest` are cleaned up, so a
  completed publish leaves no extra files.

`publish_tarball.py` also has `--verify` (connect and report, change nothing)
and `--dry-run` (package and report, upload nothing) for checking a host
without publishing.

## The automation service can fail before our code runs

Runs that sit at "Starting automation" and then expire with `Timed out: Sandbox
not available` never reached `main.py`. That is a platform-level provisioning
failure (`status_detail.kind == environment_unavailable`), not a bug in the
publish code, and re-dispatching is the only remedy. Distinguish it from a real
failure by reading `status_detail`:

- `environment_unavailable` — the sandbox never came up; our code did not run.
- `execution_error` with an `exit_code` and stdout — our code ran and failed.
- `timeout` in the `execution` phase — our code ran but exceeded the limit.

## The daily run publishes the site

The "Toolsummary pricing refresh" cron (`30 4 * * *` UTC) does not stop at the
git push: after the snapshot is safely on `main` it runs
`automation/deploy/publish_tarball.py` to upload the built site. Publishing was
moved here from the standalone publish automation because the daily run is the
thing that regenerates the data, and a site that never reflects its own data is
the failure mode that matters.

Two ordering rules are deliberate and must not be "simplified":

- The snapshot is pushed *before* the site is uploaded. The git history is the
  irreplaceable artifact; the site is rebuildable from it. A publish that ran
  first and hung could lose the day's prices.
- A failed publish does **not** fail the run. It is reported (callback error
  text plus a `done (with publish warning)` line) and the run exits 0, because a
  stale site is recoverable tomorrow and a lost snapshot is not.

A quiet day with no price movement is also success. `commit_and_push` returns
`pushed` / `unchanged` / `failed`; only `failed` is fatal. Collapsing those into
one boolean is what made "no changes" look like a lost snapshot.

### The cron tarball ships code, not a repo checkout of the cron script

The cron tarball contains only `main.py`, so it has no `setup.sh`. Anything the
publish step imports must be installed at runtime, which is why the publisher
pip-installs paramiko itself. The tarball also freezes `main.py`: **editing
`automation/cron/main.py` on `main` changes nothing until the tarball is
re-uploaded and re-attached** to the automation. After any change to that file,
repackage and `PATCH` the automation's `tarball_path`:

```bash
cd automation/cron && tar -czf /tmp/cron.tar.gz main.py
# POST /api/automation/v1/uploads, then PATCH the automation with the new path
```

The cron script clones `main` at run time, so the *pipeline* it runs is always
current; only the entrypoint is frozen.

### One branch: `main`

Everything — the pipeline, the deploy code, and the data — lives on `main`, and
the cron clones `main`. Older sessions kept deploy code on a `dev-branch` whose
data was weeks stale; a publish that cloned it would have overwritten the live
site with old pages. Do not reintroduce that split: keep deploy code and data on
the same branch the automation clones.

### Proving which run published the site

Automation runs expose no stdout over the API (`/runs/{id}` 404s). To prove a
publish actually happened, compare the remote root files' mtime against the run's
`started_at`/`completed_at` — an mtime inside that window is direct evidence, and
it also catches the failure where the run "completed" without uploading.


## Competitive landscape

`docs/market.md` holds the market read. The short version as of 2026-10-26:
llm-cost.io has already shipped this plan (change tracker with 63 daily
snapshots, weekly report, free model list, cheapest-for-coding guides, batch
pricing, direct-vs-router, agent cost, calculator, RSS, `llms.txt`, free Agent
Data API, $9/mo Pro). Our history holds 4 snapshot dates. `models.dev` serves
8,940 models with `cache_read` pricing for free. Do not write a plan that
assumes price history is an open niche without re-checking the SERP first.



## Forms: reCAPTCHA and the mail path

Both public forms (`/submit/`, `/contact/`) POST JSON to Web3Forms over `fetch`
and report the outcome in an in-page dialog. Do not reintroduce a native submit
or a `redirect` field: with either, a `200` and a `400` both look like "the page
went away", and the user cannot be told the difference.

### The captcha is reCAPTCHA v3, and it is a paid Web3Forms feature

hCaptcha was removed. The site now uses Google reCAPTCHA v3, which is invisible
(no checkbox) and attaches a token in the `recaptcha_response` field.

**This is a Web3Forms Pro feature.** On the free plan the token is not verified
server side. Before assuming the captcha is doing anything, confirm the form's
dashboard setting:

1. Web3Forms dashboard -> the form -> Settings
2. Choose `recaptcha` as the captcha provider
3. Paste the **secret** key and save

The secret key is never in this repository and must never be. Only the public
site key belongs in page HTML. `tests.py` fails the build if the secret appears
in any generated file.

- Site key (public, in `build_pages.py`): safe to publish
- Secret key: dashboard only; also available to the build as `RECAPTCHA_SITE_KEY`
  for the public half, and never written out

### Deliverability

Mail landing in spam is a domain-reputation problem, not a form bug. Ranked by
effect: SPF, DKIM and DMARC on the sending domain, then Web3Forms' own sending
reputation, then the recipient's filters. Nothing in the page markup fixes it.
Do not add a `replyto` hidden field: it writes the inbox address into public
HTML where scrapers collect it, and Web3Forms already sets Reply-To from the
visitor's `email` field.
