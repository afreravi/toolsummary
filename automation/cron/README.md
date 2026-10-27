# Daily pricing automation

`main.py` is the scheduled entrypoint for the "Toolsummary pricing refresh"
automation (cron `30 4 * * *` UTC).

## What it does

1. Clone `afreravi/toolsummary` at `main`.
2. Run the repo's own `automation/mvp/run_pipeline.py`.
3. Commit the regenerated `automation/mvp/data/` to `main` and push.
4. Publish the built site to the live web root over SFTP.
5. Print the daily review digest.
6. Report completion back to the automation service.

No LLM is called. This is a fixed data transform, so an agent preset would cost
tokens per run and add non-determinism to a pipeline whose value is
reproducibility.

## Why it clones instead of shipping the pipeline

The pipeline is the thing under test. Shipping a copy in the tarball would let
its version drift from `main`, and then the recorded prices would be produced by
code nobody reviewed. Cloning runs exactly the code on `main`, so any change to
the pipeline shows up as a reviewable diff before it touches the price log.

## Failure policy

QA failure means nothing is committed, so the last good history stands and the
day is retried on the next run.

A push failure is different: history exists only in the git repo and the sandbox
is discarded, so an unpushed snapshot is lost permanently. That case exits
non-zero on purpose.

A publish failure is neither. The snapshot is already pushed by the time the
site is uploaded, so a failed publish is reported without failing the run: the
history is the irreplaceable artifact, and the site can be rebuilt tomorrow.
The run exits 0 with a publish warning in that case.

## Testing

```bash
python3 main.py --dry-run
```

Runs the real clone, pipeline, commit and publish; only the push becomes
`--dry-run` and the publish uploads nothing.

## Secrets

Requires a working GitHub token with push access to the repo, plus the SFTP
secrets for the publish step (`TOOLSUMMARY_SFTP_HOST`, `TOOLSUMMARY_SFTP_USER`,
`TOOLSUMMARY_SFTP_PASSWORD`, `TOOLSUMMARY_SFTP_PORT`, `TOOLSUMMARY_SFTP_PATH`).
The sandbox contains several token-shaped secrets that are not equivalent, so
the script verifies each candidate against the GitHub API rather than trusting
the first name that exists. See the "Secret lookup gotcha" section in
`AGENTS.md`.

Paid API/MCP serving is deliberately not attempted.
