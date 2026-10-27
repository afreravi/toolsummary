# Deploying the site

Deployment is automatic. The daily "Toolsummary pricing refresh" run publishes
the site itself, after the day's snapshot is committed and pushed. This document
covers how that works and the manual fallback if it ever fails.

## Automatic (the normal path)

`automation/deploy/publish_tarball.py` packages `automation/mvp/site/` into one
tarball, uploads it, and extracts it on the host with a single `tar -xzf`. The
cron entrypoint runs it as the last step of the daily job.

| Step | Who |
|---|---|
| Fetch prices, gate, record history | Automation, 04:30 UTC |
| Commit `automation/mvp/data/` to `main` | Automation |
| Build pages + QA | Automation |
| Publish the built site | Automation |

A publish failure does not fail the run: the snapshot is already pushed, so a
stale site is recoverable tomorrow and a lost snapshot is not.

## Manual fallback

If a publish fails and you do not want to wait for the next run, publish by hand
from a checkout of `main`:

```bash
cd automation/mvp && python3 build_pages.py && python3 tests.py
cd ../.. && python3 automation/deploy/publish_tarball.py --verify   # check the host first
python3 automation/deploy/publish_tarball.py                        # publish
```

`--dry-run` packages and reports without uploading.

## The downloadable archive (optional)

`automation/deploy/package_site.py` produces `deploy/toolsummary-site.tar.gz`
plus a `manifest.json` (file count, page counts, `data_generated_at`). The
`Build deployable site` GitHub Action runs it at 06:00 UTC and uploads the
archive as a downloadable artifact. This is for inspection — the automation does
not use it. Extract it into the web root if you ever need to deploy by hand:

```bash
tar -xzf toolsummary-site.tar.gz -C /path/to/public_html
```

The archive contains `index.html`, `sitemap.xml`, `llms.txt`, `robots.txt`,
`model/`, and `compare/` at its top level — extract it directly into the web
root, not into a subdirectory.

## Why the archive is small

The site is ~13 MB uncompressed but ~300 KB compressed, because the pages are
highly repetitive HTML.

## Verify after deploy

```bash
curl -s https://toolsummary.com/robots.txt
curl -s https://toolsummary.com/sitemap.xml | head -c 300
python3 automation/deploy/publish_tarball.py --verify
```

Then load one model page and one comparison page in a browser.

## Why not commit the generated site

The site is ~13 MB across ~1,104 files and is regenerated from scratch on every
refresh (`build_pages.py` wipes the output directory first). Committing it would
mean a thousand-file diff every day that buries the one change that matters: the
price data. The generated site stays gitignored; the *archive* is the artifact.

## Confirming which build is live

Compare the remote root files' mtime against the run's `started_at` /
`completed_at` — an mtime inside that window is direct evidence the publish
happened. `manifest.json` from the Action also records the file count, page
counts, and `data_generated_at`; if that timestamp is not today's date, the
pricing refresh did not commit and you would be looking at stale pages.

To confirm a locally built archive matches what you intend to ship:

```bash
sha256sum toolsummary-site.tar.gz
```

## Doing it without GitHub Actions

The Action is a convenience, not a dependency. The same artifact builds locally:

```bash
cd automation/mvp && python3 build_pages.py && python3 tests.py
cd ../.. && python3 automation/deploy/package_site.py
```
