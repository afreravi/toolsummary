# Publishing runbook (SFTP)

Phase 3 of the roadmap publishes the generated site over SFTP. It is currently
**not enabled**, and there is a blocker that must be fixed before it can be.

## Blocker: the sandbox has no rsync, ssh, or scp

`publish()` in `automation/automation_main.py` shells out to
`rsync -az --delete -e "ssh -i ..."`. The automation sandbox does not have any
of those binaries:

```
rsync = MISSING
ssh   = MISSING
sftp  = MISSING
scp   = MISSING
git   = /usr/bin/git
python 3.13.15, ftplib available, paramiko/requests MISSING
```

Adding secrets will not fix this. The publish path has to be rewritten to use
Python's stdlib `ftplib`, or `paramiko` has to be added to the tarball. Until
then, a run reports `publish: skipped (no SFTP host secret configured)` and the
site stays in the workspace.

Recommended: rewrite `publish()` to upload over `ftplib.FTP_TLS` (stdlib, no
dependency, works with SFTP-over-FTP hosting like Hostinger's). Keep the
"delete stale files first" behaviour so the live sitemap cannot list orphans.

## The secrets to create

Six names are read by the code. Only the first three are required.

| Secret | Required | Value |
|---|---|---|
| `TOOLSUMMARY_SFTP_HOST` | yes | the server hostname, e.g. `sftp.toolsummary.com` |
| `TOOLSUMMARY_SFTP_USER` | yes | the FTP/SFTP username from the host |
| `TOOLSUMMARY_SFTP_KEY` | yes | the private key or password |
| `TOOLSUMMARY_SFTP_PORT` | no | defaults to `22` |
| `TOOLSUMMARY_SFTP_PATH` | no | defaults to `/public_html` |
| `TOOLSUMMARY_GITHUB_TOKEN` | no | only if you want a dedicated push token |

Note on naming: the code reads `TOOLSUMMARY_SFTP_KEY` and writes it to
`.sftp_key` with mode `600`, then deletes it. That file is gitignored. Never
commit a key; never paste one into a conversation or an issue.

## Where they come from

The host is whichever provider serves toolsummary.com. If it is Hostinger:

1. Log in to hPanel → **Files → FTP Accounts** (or **Advanced → SSH Access**).
2. The host and username are shown on that page. The password is what you set
   when creating the account; it is not shown again, so if it is lost, reset it.
3. If SSH/SFTP keys are available, generate a key pair and upload the public
   key. Keep the private key for the secret below.
4. Confirm the web root — usually `public_html`, sometimes
   `domains/toolsummary.com/public_html`. That goes in `TOOLSUMMARY_SFTP_PATH`.

## How to add them to OpenHands

Custom secrets are stored against the OpenHands account/sandbox and are **not**
inherited from a shell. Adding them to a local shell or a `.env` file will not
make the automation see them.

1. Open the workspace where the automations run (the same account that owns
   "Toolsummary pricing refresh").
2. Go to **Settings → Secrets** (agent-server settings).
3. Add each secret by exact name. Names are case-sensitive:
   `TOOLSUMMARY_SFTP_HOST`, `TOOLSUMMARY_SFTP_USER`, `TOOLSUMMARY_SFTP_KEY`.
4. Do not paste a secret into a chat message, an issue, or a commit.

Verify from inside a run rather than from your shell — the run is what matters:

```python
# in the automation, list names only. Never print values.
import json, os, urllib.request
key = os.environ.get("SESSION_API_KEY") or os.environ.get("OH_SESSION_API_KEYS_0", "")
url = f"{os.environ['OPENHANDS_CLOUD_API_URL']}/api/v1/sandboxes/{os.environ['SANDBOX_ID']}/settings/secrets"
req = urllib.request.Request(url, headers={"X-Session-API-Key": key})
print([s["name"] for s in json.loads(urllib.request.urlopen(req).read())["secrets"]])
```

## Staging target

Staging needs two things before a date can be committed to:

1. `publish()` rewritten to stdlib `ftplib` (the blocker above). ~1 hour.
2. Secrets created and verified from inside a run. ~15 minutes once you have the
   host credentials.

Once those exist, the sequence is: dispatch a manual run with the real
entrypoint, confirm the file count at the destination, check one model page and
one comparison page in a browser, then let the daily schedule take over.

Suggested target: **the first business day after the secrets are in place**,
with a manual dispatch that day rather than waiting for the cron. The blockers
are the two items above, not calendar time.
