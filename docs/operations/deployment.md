# Deployment

> **For record.cloudfrm.ai specifically, follow [`deploy/README.md`](../../deploy/README.md).**
> It has the ordered runbook, a bootstrap script, and the Caddy/systemd files.
> This page is the background: what the pieces are and why.

One Python process plus a bucket. No queue, no orchestration — the bottleneck in
this project is recruiting speakers, not scaling servers, and every piece of
infrastructure you add is one more thing to keep running while you do the hard
part.

Microphone access requires a secure context, so **HTTPS is not optional** in any
setup a real contributor will touch.

---

## 1. Storage: Cloudflare R2

R2 is the default because you will download this dataset many times during
training, and R2 charges nothing for egress.

| Provider | Storage | Egress | Use when |
|---|---|---|---|
| **Cloudflare R2** | ~$0.015/GB-mo, 10 GB free | **$0** | Default. |
| Backblaze B2 | ~$0.006/GB-mo | Free via Cloudflare CDN | Cold archive copy. |
| AWS S3 | ~$0.023/GB-mo | ~$0.09/GB | Only if already on AWS. |
| Supabase Storage | Bundled | Bundled | If you want Postgres + Auth too. |

48 kHz / 16-bit / mono WAV is **345 MB per hour**. 500 hours ≈ 173 GB ≈
**$2.60/month on R2**. Storage will not be your cost problem.

### Create the bucket

1. Cloudflare dashboard → R2 → *Create bucket* → `voice-corpus`.
2. R2 → *Manage API tokens* → create a token with **Object Read & Write**,
   scoped to that bucket only.
3. Your endpoint is `https://<account_id>.r2.cloudflarestorage.com` — the account
   ID is in the dashboard URL.

```bash
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
S3_BUCKET=voice-corpus
S3_REGION=auto
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
```

### CORS — the step that always bites

The browser PUTs audio **directly** to the bucket. Without CORS the upload fails
with an opaque network error and nothing reaches storage. In R2 → your bucket →
Settings → CORS policy:

```json
[
  {
    "AllowedOrigins": ["https://voice.cloudfrm.ai"],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["content-type"],
    "ExposeHeaders": ["etag"],
    "MaxAgeSeconds": 3600
  }
]
```

Keep the bucket **private**. Presigned URLs are how the browser writes; nothing
needs public read.

## 2. Database

SQLite is fine for a pilot with one recording session at a time. Beyond that,
use Postgres — concurrent writes are where SQLite starts returning
`database is locked`.

```bash
pip install "psycopg[binary]"
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/voice
```

Managed options that need no server work: Neon, Supabase, Railway.

```bash
python scripts/init_db.py
python scripts/import_prompts.py data/prompts_ne.jsonl
```

`init_db.py` runs `alembic upgrade head`. Run it on every deploy, not just the
first: `create_all()` would add missing *tables* but never a *column* to an
existing one, so a new field would silently not exist and every insert would
fail with `no such column`.

For a database created before Alembic was added, mark it once rather than
replaying the baseline over live tables:

```bash
python scripts/init_db.py --stamp
```

## 3. Run it

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

Audio never passes through this process — the browser uploads straight to the
bucket — so two workers handle far more contributors than you will have.

### systemd

```ini
[Unit]
Description=voice.cloudfrm.ai
After=network.target

[Service]
User=voice
WorkingDirectory=/srv/voice
EnvironmentFile=/srv/voice/.env
ExecStart=/srv/voice/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

### Caddy (TLS with no extra steps)

```
voice.cloudfrm.ai {
    reverse_proxy 127.0.0.1:8000
    request_body { max_size 50MB }
}
```

`max_size` matters only for the local storage backend; on S3 the bytes bypass
the proxy entirely.

Set `PUBLIC_BASE_URL=https://voice.cloudfrm.ai` to match, or presigned local
uploads will point at the wrong host.

## 4. Reviewer access

The `/review` UI is gated by named staff tokens:

```bash
REVIEWER_TOKENS=alice:tok1,bob:tok2
```

Generate them with `python -c "import secrets;print(secrets.token_urlsafe(24))"`.
Reviewers open `/review?token=tok1`.

**This is staff-grade auth, not a public identity system.** Be clear about what
it does and does not give you:

- It *does* put a name on every verdict, which is the part that matters for the
  data: attribution makes inter-reviewer agreement measurable and lets a bad
  reviewing session be found and reverted.
- It does *not* give you per-user passwords, token rotation, session management,
  or any record of who holds which token. A shared token is exactly as good as
  the people you gave it to.
- Tokens appear in the URL, so they land in browser history and in any proxy
  logs in front of the app. The query form exists because `<audio src>` cannot
  carry a header.

If reviewing is ever opened beyond trusted staff, replace this with real
authentication first. Do not reuse it for anything public-facing.

With `REVIEWER_TOKENS` unset, `/review` returns 401 and the rest of the app is
unaffected -- which is the right posture until you actually have reviewers.

### Playback

The review UI plays audio from short-lived presigned GET URLs
(`PRESIGN_GET_TTL_S`, default 300s), fetched directly from the bucket. Audio is
never streamed through the API process. **Keep the bucket private** -- a review
UI is the easiest place to accidentally make a corpus public.

On R2 this needs `GET` added to the CORS policy alongside `PUT`:

```json
"AllowedMethods": ["PUT", "GET"]
```

## 5. Before the first real session

- [ ] `SECRET_KEY` set to a real value — `python -c "import secrets;print(secrets.token_hex(32))"`
- [ ] `PUBLIC_BASE_URL` matches the HTTPS URL contributors will open
- [ ] `STORAGE_BACKEND=s3` and CORS tested with a real upload
- [ ] `docs/consent-ne.md` reviewed by a Nepali lawyer if you intend to license
      the dataset commercially — the commercial-use opt-in **cannot** be
      retro-fitted
- [ ] `CONSENT_VERSION` matches the consent text actually in the repo
- [ ] `pytest -q` passes on the deployed machine (it sandboxes itself to a
      temp database and storage directory, so it is safe to run there)
- [ ] Bucket versioning or a second copy in B2, so a bad script cannot delete
      the masters
- [ ] A named person who can action `scripts/withdraw.py` within a few days

### Review checklist

- [ ] `REVIEWER_TOKENS` set, one distinct token per person
- [ ] Bucket CORS allows `GET` as well as `PUT`
- [ ] Bucket is still private (presigned URLs are the only read path)

## 6. Testing over HTTPS without deploying

```bash
uvicorn app.main:app --reload
cloudflared tunnel --url http://localhost:8000
```

Set `PUBLIC_BASE_URL` to the tunnel URL it prints, then restart uvicorn. Good
enough to hand the link to a few people; not for a real collection round, since
the tunnel URL changes every restart.

## 7. Backups

The 48 kHz masters under `raw/` are the irreplaceable part. Everything under
`derived/` regenerates from them with `scripts/export_dataset.py`, and the
database can be rebuilt far more cheaply than the audio can be re-recorded.

```bash
rclone sync r2:voice-corpus/raw b2:voice-corpus-archive/raw
```

Back up the database too — it holds the transcripts, QC verdicts and consent
records. Audio with no transcript and no consent record is not a dataset.
