# Publishing runbook (SFTP)

## Validation status (re-checked 2026-10-11, inside the automation sandbox)

All five secrets are now configured and were tested with real connections.

| Check | Result |
|---|---|
| `TOOLSUMMARY_SFTP_HOST` | present, 13 chars, **bare hostname** (no scheme, no path, no port) |
| `TOOLSUMMARY_SFTP_USER` | present, 34 chars, no `@` |
| `TOOLSUMMARY_SFTP_KEY` | present, 10 chars — a **password**, not a key |
| `TOOLSUMMARY_SFTP_PORT` | present, `65002` |
| `Remote_Path` | present, 52 chars, leading `/`, contains `public_html` |

**Verdict: the host, port, and protocol are correct; the login is rejected.**

The earlier reading of this host was wrong. It is not FTPS on port 21. Reading
the banner settles it:

```
SSH-2.0-OpenSSH_8.0        <- port 65002 is an SSH server
IS_SSH_SERVER = True
```

This is the standard shared-host shape: SSH/SFTP on a high port, with the
web root reachable through the SFTP session.

### 1. Resolved: the host is now a bare hostname

The previous value was a URL (`scheme://host:port/path`), which failed to
resolve with `gaierror EAI_NONAME`. The current value is a clean hostname and
resolves fine. Keep it that way; `publish()` should still normalise defensively
so a URL-shaped value cannot silently break a run again.

### 2. Resolved: the port points at SSH, not FTP

`TOOLSUMMARY_SFTP_PORT=65002` is correct for this host. Connecting to it with
FTP times out because it is not an FTP port; an SSH handshake succeeds
immediately.

### 3. Open: the credentials are rejected

Using a real SSH client (`paramiko`) against port 65002:

```
bare      = AUTH_FAIL
user@host = AUTH_FAIL
user@domain = AUTH_FAIL
```

Every realistic username form fails, and no FTP path on 21 accepts either. So
the password in `TOOLSUMMARY_SFTP_KEY` is wrong, or the username is not an
account that may log in over SSH. On cPanel-style hosts SSH access must usually
be enabled per account in the panel before the same password will work.

Fix, in order:

1. In the host panel, confirm SSH access is enabled for this account.
2. Reset the account password there.
3. Re-add `TOOLSUMMARY_SFTP_KEY` with the new password.

Then re-run the verification below. Nothing else is blocking.

### 4. Note: `TOOLSUMMARY_SFTP_KEY` is not a key

A length of 10 with no `-----BEGIN` marker means it holds a password. That is
fine for this host — it just means the name is misleading, and that a PEM key
will not be needed unless SSH key auth is set up instead.

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
apt-get = present but not root (dpkg lock denied); pip install works
```

Adding secrets will not fix this. The publish path has to be rewritten to use
`paramiko` over SFTP, or stdlib `ftplib` if a plain FTPS endpoint is ever used.
`pip install paramiko` succeeds inside a run, so the SFTP route is viable:

```
PIP_RC    = 0
IMPORT_RC = 0
IMPORT_VER = 5.0.0
```

Important: install `paramiko` in a subprocess and import it in a **separate**
process. A module installed during a run is not importable by the process that
installed it, which makes a single-process script report a false "unavailable".

Recommended: rewrite `publish()` to open an SFTP session on
`TOOLSUMMARY_SFTP_PORT` and write into `Remote_Path`. Keep the "delete stale
files first" behaviour so the live sitemap cannot list orphans.

## The secrets to create

| Secret | Required | Value |
|---|---|---|
| `TOOLSUMMARY_SFTP_HOST` | yes | bare hostname only, no `ftp://` prefix, no path |
| `TOOLSUMMARY_SFTP_USER` | yes | SSH account name from the host panel |
| `TOOLSUMMARY_SFTP_KEY` | yes | password for that account (not a key, despite the name) |
| `TOOLSUMMARY_SFTP_PORT` | yes | `65002` for this host — SSH lives on a high port |
| `Remote_Path` | yes | remote web root, e.g. `.../domains/<domain>/public_html` |
| `TOOLSUMMARY_GITHUB_TOKEN` | no | only if you want a dedicated push token |

Naming note: the code reads `TOOLSUMMARY_SFTP_PATH`, but the secret added is
named `Remote_Path`. Either rename the secret or update the code — as written,
the run silently falls back to `/public_html`.


Note on naming: the code writes `TOOLSUMMARY_SFTP_KEY` to `.sftp_key` with mode
`600`, then deletes it. That file is gitignored. Never commit a credential;
never paste one into a conversation or an issue.

## Where they come from

The host panel (cPanel-style) shows the SSH account name, the SSH port, and the
password. SSH access must be enabled for the account before the password will be
accepted — a common reason for `AUTH_FAIL` even when the password is correct.

The remote path is the account's web root, typically
`domains/<domain>/public_html`. That goes in `Remote_Path`.

The host is whichever provider serves toolsummary.com. On a cPanel-style panel:

1. Log in to the panel → **Files → FTP Accounts**, or **Advanced → SSH Access**.
2. The host and SSH account name are shown there. The password is what you set
   when creating the account; it is not shown again, so if it is lost, reset it.
3. Enable SSH access for the account. Until this is on, the same password fails
   over port `65002`.
4. Confirm the web root — usually `public_html`, sometimes
   `domains/toolsummary.com/public_html`. That goes in `Remote_Path`.

## How to add them to OpenHands

Custom secrets are stored against the OpenHands account/sandbox and are **not**
inherited from a shell. Adding them to a local shell or a `.env` file will not
make the automation see them.

1. Open the workspace where the automations run (the same account that owns
   "Toolsummary pricing refresh").
2. Go to **Settings → Secrets** (agent-server settings).
3. Add each secret by exact name. Names are case-sensitive:
   `TOOLSUMMARY_SFTP_HOST`, `TOOLSUMMARY_SFTP_USER`, `TOOLSUMMARY_SFTP_KEY`,
   `TOOLSUMMARY_SFTP_PORT`, `Remote_Path`.
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

1. `publish()` rewritten to SFTP via `paramiko` (the blocker above). ~1 hour.
2. SSH access enabled and the account password corrected in the host panel, then
   verified from inside a run. ~15 minutes once the panel is open.

Once those exist, the sequence is: dispatch a manual run with the real
entrypoint, confirm the file count at the destination, check one model page and
one comparison page in a browser, then let the daily schedule take over.

Suggested target: **the first business day after the login succeeds**, with a
manual dispatch that day rather than waiting for the cron. The blockers are the
two items above, not calendar time.
