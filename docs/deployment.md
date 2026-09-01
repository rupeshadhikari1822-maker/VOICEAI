# Deployment

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

Schema changes are applied with `create_all()`, which only ever adds tables. For
column changes on a live corpus, add Alembic before you need it.

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

## 4. Before the first real session

- [ ] `SECRET_KEY` set to a real value — `python -c "import secrets;print(secrets.token_hex(32))"`
- [ ] `PUBLIC_BASE_URL` matches the HTTPS URL contributors will open
- [ ] `STORAGE_BACKEND=s3` and CORS tested with a real upload
- [ ] `docs/consent-ne.md` reviewed by a Nepali lawyer if you intend to license
      the dataset commercially — the commercial-use opt-in **cannot** be
      retro-fitted
- [ ] `CONSENT_VERSION` matches the consent text actually in the repo
- [ ] `python scripts/smoke_test.py` passes on the deployed machine
- [ ] Bucket versioning or a second copy in B2, so a bad script cannot delete
      the masters
- [ ] A named person who can action `scripts/withdraw.py` within a few days

## 5. Testing over HTTPS without deploying

```bash
uvicorn app.main:app --reload
cloudflared tunnel --url http://localhost:8000
```

Set `PUBLIC_BASE_URL` to the tunnel URL it prints, then restart uvicorn. Good
enough to hand the link to a few people; not for a real collection round, since
the tunnel URL changes every restart.

## 6. Backups

The 48 kHz masters under `raw/` are the irreplaceable part. Everything under
`derived/` regenerates from them with `scripts/export_dataset.py`, and the
database can be rebuilt far more cheaply than the audio can be re-recorded.

```bash
rclone sync r2:voice-corpus/raw b2:voice-corpus-archive/raw
```

Back up the database too — it holds the transcripts, QC verdicts and consent
records. Audio with no transcript and no consent record is not a dataset.
