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

It is idempotent — re-run it to deploy a new commit. On the first run it stops
deliberately after writing `/srv/voice/.env`, because the bucket credentials
cannot be guessed:

```bash
sudo nano /srv/voice/.env      # fill in S3_* ; SECRET_KEY is already generated
sudo bash /srv/voice/deploy/bootstrap.sh
```

A public recorder that is up but misconfigured is worse than one that is not up
yet: it collects clips it cannot store.

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

## Backups

The 48 kHz masters under `raw/` are the irreplaceable part — everything under
`derived/` regenerates from them. Enable object versioning on the bucket, and
keep a second copy:

```bash
rclone sync r2:voice-corpus/raw b2:voice-corpus-archive/raw
```

Back up `/srv/voice/voice.db` too. It holds the transcripts, the QC verdicts and
the consent records; audio with no transcript and no consent record is not a
dataset.
