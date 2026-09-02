# Deploying record.cloudfrm.ai

`voice.cloudfrm.ai` is the landing page. `record.cloudfrm.ai` is this app — the
studio a contributor actually opens. They are separate deployments on purpose:
the landing page is static and lives on Vercel; this is a stateful Python
process that needs a real host.

The ordering below is not arbitrary. Each step removes a way the next one fails.

---

## 1. DNS first, before anything else

```
A    record    <VPS_IP>    (proxy OFF if using Cloudflare)
```

```bash
dig +short record.cloudfrm.ai      # must return your VPS IP
```

Caddy cannot obtain a certificate until this resolves to the box, and ACME
failures back off, so a missing A record turns into a ten-minute wait parked in
the middle of the deploy. Start propagation before you touch the server.

**On Cloudflare, set the record to DNS-only (grey cloud), not proxied.** Proxied
mode terminates TLS at Cloudflare and Caddy's HTTP-01 challenge fails.

## 2. Provision the VPS

Any small box works: 1 vCPU / 1 GB is enough. Audio does not pass through this
process on the S3 backend, so the server is doing very little.

```bash
ssh root@<VPS_IP>
curl -fsSL https://raw.githubusercontent.com/rupeshadhikari1822-maker/VOICEAI/main/deploy/bootstrap.sh -o bootstrap.sh
less bootstrap.sh          # read it before running it as root
sudo bash bootstrap.sh
```

It installs Caddy and PostgreSQL, provisions a `voice` database with a
generated password, creates the systemd unit, and wires `.env`.

It is idempotent — re-run it to deploy a new commit. On the first run it stops
deliberately after writing `/srv/voice/.env`, because the bucket credentials
cannot be guessed:

```bash
sudo nano /srv/voice/.env      # fill in S3_* ; SECRET_KEY is already generated
sudo bash /srv/voice/deploy/bootstrap.sh
```

A public recorder that is up but misconfigured is worse than one that is not up
yet: it collects clips it cannot store.

The app backstops this. With `ENVIRONMENT=production` set, it **refuses to
boot** on local storage, SQLite, a non-https `PUBLIC_BASE_URL`, or the default
`SECRET_KEY`, and reports every problem at once rather than one per restart.
SQLite is allowed for a single-contributor pilot only if you set
`ALLOW_SQLITE_IN_PRODUCTION=true` deliberately.

## 3. Bucket CORS — the step that always bites

The browser PUTs audio **directly** to R2 and the review UI GETs it back the
same way. Without CORS both fail with an opaque network error and nothing
reaches storage. R2 → your bucket → Settings → CORS policy:

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

Keep the bucket **private**. Presigned URLs are the only read and write path.

### 3b. Lifecycle rule for `_preflight/`

The storage preflight writes a 1 KB probe at the start of every session. They
carry no contributor data and are never backed up, but nothing expires them on
its own. Add a lifecycle rule:

| Field | Value |
|---|---|
| Prefix | `_preflight/` |
| Action | Delete object |
| Age | 1 day |

**Confirm the rule is scoped to that prefix and nothing else.** A lifecycle rule
with an empty prefix, or one accidentally pointing at `raw/`, deletes the 48 kHz
masters on a one-day timer — quietly, with no error, and the speakers have gone
home. This is the single most destructive misconfiguration available in the R2
console, and it looks identical to the correct one apart from one field.

After saving it, read it back and check the prefix field is exactly
`_preflight/`. `backup_corpus.py --verify` reports the probe count on every run,
so if the rule is missing or not firing you will see the number climb.

### The preflight is what protects the contributor

`check_deployment.py` cannot test CORS, so the app tests it itself. At session
start — before a single sentence is read — the recorder performs a real
cross-origin PUT of 1 KB. If it fails, the session is blocked with a named
error rather than letting someone record twenty-five clips that cannot upload:

| Code | Meaning | Who can fix it |
|---|---|---|
| `STORAGE_CORS` | Bucket rejected the browser | You. Fix the CORS policy above. |
| `STORAGE_AUTH` | Bucket reached, signature refused | You. Bad credentials, or server clock skew. |
| `STORAGE_NETWORK` | Device has no connectivity | The contributor. Retry button is shown. |

A CORS rejection and a network failure produce the same opaque error in the
fetch API by design. The recorder separates them by asking whether its own
origin is still reachable: if it is, the network is fine and the bucket is the
problem. For `STORAGE_CORS` and `STORAGE_AUTH` the contributor is told plainly
that it is not their fault and not their internet — blaming a reader for our
misconfiguration is how you lose them.

## 4. Verify from outside

From your own machine, not the VPS — half of what this checks looks fine from
localhost and is broken from the outside:

```bash
python scripts/check_deployment.py https://record.cloudfrm.ai
```

It checks DNS, the certificate, the HTTP→HTTPS redirect, that every recorder
asset loads (a 404 on `pcm-worklet.js` breaks recording at the exact moment the
contributor presses record), that the capture spec is still 48 kHz/16-bit/mono,
that the real consent text is deployed and its hash matches this checkout, that
storage is S3 rather than local, that `SECRET_KEY` is not the repo default, and
that `/review` is gated.

`--deep` additionally records a synthetic clip end to end. It writes a real
speaker into the corpus, so it prints the ULID and the `withdraw.py` command to
remove it.

## 5. Record on a real phone. This is not optional.

**`check_deployment.py` cannot verify CORS.** CORS is enforced by the browser;
a presigned PUT from Python succeeds whether or not it is configured. So every
check in step 4 can pass while a real phone fails on its first upload.

Open `https://record.cloudfrm.ai` on an actual phone, **over mobile data rather
than your own wifi**, and record one sentence all the way through. Mobile data
matters: it catches DNS or firewall assumptions that only hold on your network.

Watch for the things only a real device shows:

- the mic permission prompt appears at all (it needs the secure context)
- the mic check passes in a normal room
- the level meter moves
- a clip uploads and comes back with a QC verdict
- if the phone has Bluetooth earbuds connected, the app warns rather than
  silently recording 16 kHz mono

Then confirm it landed:

```bash
sudo -u voice /srv/voice/.venv/bin/python /srv/voice/scripts/qc_report.py
```

## 6. Only now, link the landing page

The CTA on `voice.cloudfrm.ai` points here **last**, once there is something
honest behind it. A link that 502s or fails at the upload costs you the
contributor and their goodwill, and you rarely get a second attempt with the
same person.

---

## Operating it

```bash
systemctl status voice-recorder
journalctl -u voice-recorder -f
journalctl -u caddy -n 50                 # TLS problems show up here

sudo bash /srv/voice/deploy/bootstrap.sh  # deploy a new commit
```

Adding a reviewer:

```bash
python -c "import secrets;print(secrets.token_urlsafe(24))"
sudo nano /srv/voice/.env                 # REVIEWER_TOKENS=alice:<token>
sudo systemctl restart voice-recorder
```

Handling a withdrawal request:

```bash
cd /srv/voice
sudo -u voice .venv/bin/python scripts/withdraw.py <speaker_id> --dry-run
sudo -u voice .venv/bin/python scripts/withdraw.py <speaker_id> --confirm
```

## Backups and audit

R2 alone is not a backup. It protects against a disk failing; it does not
protect against a script deleting the wrong prefix, a leaked credential, or an
account problem. A bad `delete_prefix` removes audio exactly as thoroughly as a
dead drive, and the speakers have gone home.

```bash
# Audit: does every clip row have an object, and every object a row?
sudo -u voice /srv/voice/.venv/bin/python scripts/backup_corpus.py --verify

# Copy down what cannot be regenerated: raw/ masters, consent clips, database.
sudo -u voice /srv/voice/.venv/bin/python scripts/backup_corpus.py --dest /mnt/backup/voice
```

The audit is worth running on its own schedule. It catches rows whose audio is
missing (they fail at export), objects with no row (audio that cannot be tied to
a consent record — a privacy problem, not a storage one), and withdrawn clips
whose objects were never actually deleted (a promise to a contributor left
unkept).

`derived/` is deliberately excluded from the copy; `export_dataset.py` rebuilds
it. Enable object versioning on the bucket, and keep an offsite second copy:

```bash
rclone sync r2:voice-corpus/raw b2:voice-corpus-archive/raw
```
