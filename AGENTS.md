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
- `automation/automation_main.py` — legacy entrypoint that also publishes over
  SFTP. Unused until the SFTP secrets exist.

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
