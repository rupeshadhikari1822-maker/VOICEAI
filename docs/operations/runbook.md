# Runbook

For someone who did not build this, at a bad hour. Symptom first.

Two commands answer most questions:

```bash
systemctl status voice-recorder
journalctl -u voice-recorder -n 50 --no-pager
```

And from your own machine, not the server:

```bash
python scripts/check_deployment.py https://record.cloudfrm.ai
```

---

## A contributor says "पठाउन सकिएन" (could not send)

**Ask what the screen said underneath.** The recorder blocks with a named code
in monospace, sized to be screenshotted. Get that first — it splits the problem
in one step.

If they got as far as recording and the failure was on send, the preflight
passed, so storage was reachable at session start. Suspect the network or a
single bad clip, not configuration.

## `STORAGE_CORS` on the block screen

The bucket is rejecting the browser. **Not the contributor's internet** — the
app already proved its own origin was reachable before showing this.

R2 → your bucket → Settings → CORS policy:

```json
[
  {
    "AllowedOrigins": ["https://record.cloudfrm.ai"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedHeaders": ["content-type"],
    "ExposeHeaders": ["etag"],
    "MaxAgeSeconds": 3600
  }
]
```

Common causes, in order:

1. `AllowedMethods` has `PUT` but not `GET`. Uploads work, review playback does
   not.
2. `AllowedOrigins` has a trailing slash, or `http://`, or the wrong subdomain.
   It must match the origin exactly.
3. The policy was saved on the wrong bucket.

No restart needed — R2 applies it immediately. Reload the recorder page.

## `STORAGE_AUTH` on the block screen

The bucket was reached and the presigned URL was refused. CORS is fine; the
signature is not.

- Credentials wrong or revoked → check `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY`
- Token scoped to a different bucket, or read-only → needs **Object Read & Write**
- **Server clock skew.** Signatures embed a timestamp; a drifted clock
  invalidates them. `timedatectl` — if NTP is off, `timedatectl set-ntp true`.

## `AUDIO_WORKLET_SILENT` on the mic check

The microphone opened and no audio arrived within 1.2 s. Permission is granted,
the track is live, the label and sample rate display correctly, and the meter is
frozen.

This is the WebKit graph-inactive failure. The zero-gain keepalive node in
`static/recorder/audio.js` exists to prevent it — see
[ADR-001](../architecture/ADR-001-audio-capture.md).

- Ask them to try Chrome. If Chrome works and Safari does not, it is the
  platform, not the deployment.
- In a desktop console: `state.recorder.context.state` should be `running`. If
  it is `suspended`, the resume-after-gesture path failed.
- **Do not remove the keepalive node** in response to this. It is what makes
  the case rarer, not what causes it.

## The app will not start

Read the message. The production guard names the setting:

```
refusing to start: ENVIRONMENT=production with an unsafe configuration
  1. STORAGE_BACKEND is not 's3'...
  2. DATABASE_URL is SQLite...
```

It reports **every** problem at once, so fix them all before restarting.

`S3_ENDPOINT_URL` has its own guard. The most common failure is pasting the
endpoint straight from the R2 console with the bucket appended:

```
✗ https://abc123.r2.cloudflarestorage.com/voice-corpus
✓ https://abc123.r2.cloudflarestorage.com
```

The app adds the bucket name itself.

## Certificate will not issue or renew

```bash
journalctl -u caddy -n 50 --no-pager
```

In order of likelihood:

1. **Port 80 closed.** ACME's HTTP-01 challenge needs it, and people close it
   assuming HTTPS only needs 443. `ufw status` — and check
   **Networking → Firewalls** in the DigitalOcean panel, which is a separate
   layer from `ufw` and blocks independently of it.
2. **Cloudflare proxy is on (orange cloud).** Proxied mode terminates TLS at
   Cloudflare and the challenge never reaches Caddy. Set the record to
   **DNS-only (grey cloud)**.
3. **DNS moved.** `dig +short record.cloudfrm.ai` must still be this box's
   `curl ifconfig.me`.

Diagnostic worth knowing: a **connection refused** on port 80 means packets
reach the host and nothing is listening — Caddy is down. A **timeout** means
something is dropping them — a firewall. Same blank screen, different cause.

## Disk filling up

Audio is not on this box. `raw/` and `derived/` live in R2, and clip bytes never
pass through the server on the S3 backend.

What actually grows:

```bash
du -sh /var/log/caddy /var/lib/postgresql /srv/voice
journalctl --disk-usage
```

- Caddy access logs — rotation is configured, verify it is working
- Postgres — small; the database holds text and metadata, no audio
- `journalctl` — `journalctl --vacuum-time=14d`
- `/srv/voice/storage_local/` — should be **empty** in production. If it is not,
  `STORAGE_BACKEND` is wrong and clips are landing on this disk.

## `check_deployment.py` failures, row by row

| Row | Means |
|---|---|
| `<host> resolves` | DNS gone or never propagated. Nothing else can pass. |
| `TLS certificate is valid` | Caddy has no cert. See the certificate section. |
| `HTTP redirects to HTTPS` | Warning only, but a contributor typing the bare host gets no microphone. |
| `all recorder assets load` | A 404 here breaks recording at the moment they press record. Usually a bad deploy. |
| `real consent text is deployed` | Serving the built-in fallback. `docs/consent-ne.md` is missing from the deploy. **Stop collecting.** |
| `deployed consent matches this checkout` | The server's consent text differs from this branch. Establish which is correct before recording anything else. |
| `storage backend is S3/R2` | Running on local storage: one disk, no versioning. |
| `SECRET_KEY has been changed` | Repo default in use; upload URLs are forgeable. |
| `storage preflight is live` | Deployed code predates the preflight; a CORS problem would surface only after someone records. |
| `ENVIRONMENT=production` | Guard is off. The four checks above are unenforced. |
| `/review is gated` | If this fails, the review UI is open. |

## Corpus integrity

```bash
sudo -u voice /srv/voice/.venv/bin/python scripts/backup_corpus.py --verify
```

| Finding | Meaning |
|---|---|
| **Missing objects** | Rows with no audio. They fail at export. Usually an interrupted upload. |
| **Withdrawn but still stored** | A withdrawal did not complete. Re-run `withdraw.py` for that speaker. This is a promise left unkept — fix it first. |
| **Orphaned objects** | Audio with no row. It cannot be tied to a consent record, so you cannot prove you may hold it and cannot honour a withdrawal against it. Investigate before the next export. |
| **Preflight probes climbing** | The `_preflight/` lifecycle rule is missing or not firing. Harmless but check the rule is scoped to that prefix — one pointed at `raw/` deletes the masters. |

## Withdrawal request

```bash
cd /srv/voice
sudo -u voice .venv/bin/python scripts/withdraw.py <speaker_id> --dry-run
sudo -u voice .venv/bin/python scripts/withdraw.py <speaker_id> --confirm
sudo -u voice .venv/bin/python scripts/backup_corpus.py --verify   # confirm
```

Then re-run any export that included them. A dataset already distributed cannot
be recalled — say so honestly if asked.

## Rolling back

```bash
cd /srv/voice
sudo -u voice git log --oneline -10
sudo -u voice git checkout <commit>
sudo systemctl restart voice-recorder
```

**Migrations do not roll back automatically.** If the bad deploy included one,
check `alembic history` and downgrade deliberately, or restore the database from
backup. Rolling code back under a newer schema usually works — extra columns are
ignored — but do not assume it.
