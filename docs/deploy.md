# Deploying the site

The host cannot be reached over SFTP from the automation sandbox, so deployment
is a manual upload. This is the workflow that replaces it.

## Why not commit the generated site

The site is ~13 MB across ~1,000 files and is regenerated from scratch on every
refresh (`build_pages.py` wipes the output directory first). Committing it would
mean a thousand-file diff every day that buries the one change that matters: the
price data. The generated site stays gitignored; the *archive* is the artifact.

## What the automation does vs. what you do

| Step | Who |
|---|---|
| Fetch prices, gate, record history | Automation, 04:30 UTC |
| Commit `automation/mvp/data/` to `main` | Automation |
| Build pages + QA + package archive | GitHub Action, 06:00 UTC |
| Download the archive | You |
| Upload to the host | You |

The Action runs after the pricing refresh so the archive is built from the day's
committed data.

## Deploying

1. Open the repo's **Actions** tab → **Build deployable site** → the latest run.
2. Download the `toolsummary-site` artifact (contains the archive and
   `manifest.json`).
3. Check `manifest.json`: it records the file count, page counts, and the
   `data_generated_at` timestamp. If that timestamp is not today's date, the
   pricing refresh did not commit and you would be uploading stale pages.
4. Extract the archive into the web root on the host, replacing existing files.

```bash
tar -xzf toolsummary-site.tar.gz -C /path/to/public_html
```

The archive contains `index.html`, `sitemap.xml`, `llms.txt`, `robots.txt`,
`model/`, and `compare/` at its top level — extract it directly into the web
root, not into a subdirectory.

## Verify after upload

```bash
curl -s https://toolsummary.com/robots.txt
curl -s https://toolsummary.com/sitemap.xml | head -c 300
```

Then load one model page and one comparison page in a browser. The sitemap is
regenerated with the site, so a successful extract cannot leave orphan pages
listed.

To confirm you uploaded the intended build, compare the archive's sha256 with
`manifest.json`:

```bash
sha256sum toolsummary-site.tar.gz
```

## Why the archive is not huge

The site is ~13 MB uncompressed but ~300 KB compressed, because the pages are
highly repetitive HTML. Download and upload are both fast.

## Doing it without GitHub Actions

The Action is a convenience, not a dependency. The same artifact builds locally:

```bash
cd automation/mvp && python3 build_pages.py && python3 tests.py
cd ../.. && python3 automation/deploy/package_site.py
```

## Later: real CI deployment

Once there is a deployment credential the host accepts (an SSH key with access
enabled, or an API token for the provider), the manual step can be replaced. The
packaging step is already isolated in `automation/deploy/package_site.py`, so
only the upload needs adding.
