# Backup and restore

## What is actually irreplaceable

| | Recoverable? |
|---|---|
| `raw/` — 48 kHz masters | **No.** The speakers have gone home. |
| The database | **No.** Transcripts, QC verdicts, consent records. |
| `derived/` | Yes — `export_dataset.py` rebuilds it from `raw/`. |
| `_preflight/` | Yes, and worthless. Never backed up. |
| The code | Yes — it is on GitHub. |

Audio without the database is not a dataset. It is a pile of WAVs with no
transcripts and no proof you are allowed to hold them. Back up both or neither.

## R2 alone is not a backup

It protects against a disk failing. It does not protect against a script
deleting the wrong prefix, a leaked credential, or an account problem. A bad
`delete_prefix` removes audio exactly as thoroughly as a dead drive.

Three things, in order of value:

**1. Object versioning on the bucket.** Turn it on before collecting. It is the
only defence against deletion that does not require noticing in time.

**2. An offsite copy.** Different provider, so a compromised account cannot
reach both:

```bash
rclone sync r2:voice-corpus/raw b2:voice-corpus-archive/raw
```

**3. A local copy plus the database:**

```bash
sudo -u voice /srv/voice/.venv/bin/python scripts/backup_corpus.py \
    --dest /mnt/backup/voice
```

Incremental by size, so re-running is cheap. Copies `raw/` and `consent/`,
dumps the database, writes a manifest. Excludes `derived/` and `_preflight/`.

## Audit regularly

```bash
sudo -u voice /srv/voice/.venv/bin/python scripts/backup_corpus.py --verify
```

Cross-checks the database against storage in both directions. It answers
questions neither side can answer alone — see the table in
[runbook.md](runbook.md#corpus-integrity).

Worth running on a schedule, not just when something looks wrong. The failure it
catches is silent: a clip whose upload was interrupted looks fine in the database
and simply disappears at export time.

## Restoring

**Database, Postgres:**

```bash
sudo systemctl stop voice-recorder
sudo -u postgres dropdb voice && sudo -u postgres createdb -O voice voice
sudo -u voice psql "$DATABASE_URL" < /mnt/backup/voice/voice.sql
sudo -u voice /srv/voice/.venv/bin/python scripts/init_db.py   # alembic to head
sudo systemctl start voice-recorder
```

**Database, SQLite:** stop the service, copy `voice.db` back, run `init_db.py`,
start.

**Objects:** `rclone sync` in the other direction, or `aws s3 sync` against the
R2 endpoint. Restore `raw/` and `consent/` only — never restore `derived/`,
regenerate it, so the export always matches the current code.

**Always finish with the audit.** A restore that leaves rows without objects, or
objects without rows, is not a completed restore:

```bash
scripts/backup_corpus.py --verify
```

## After restoring, before collecting again

- `scripts/check_deployment.py https://record.cloudfrm.ai` — particularly the
  consent hash row. A restore from an older backup can quietly reinstate older
  consent text.
- Confirm `CONSENT_VERSION` in `.env` matches the restored `docs/consent-ne.md`.
- Re-run any export that a withdrawal had already been applied to. **Restoring
  from a backup taken before a withdrawal reinstates that speaker's audio.**
  Keep a list of honoured withdrawals outside the database, and re-apply them
  after any restore.

That last point is the one most likely to be missed. A backup is a snapshot of a
promise you had not yet kept.
