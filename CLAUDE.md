# CLAUDE.md

Context for Claude Code working in this repository.

## What this is

A link-based voice recording studio that collects a Nepali (and minority
language) speech corpus for ASR/TTS training. FastAPI backend, vanilla-JS
browser recorder, S3-compatible object storage, SQLAlchemy over SQLite in dev
and Postgres in production.

## Hard rules — do not change these without being asked

1. **Audio stays uncompressed.** The browser must produce 48 kHz / 16-bit /
   mono PCM WAV via `AudioWorklet`. Do not replace this with `MediaRecorder`;
   it yields WebM/Opus and destroys the data.
2. **Browser DSP stays off.** `echoCancellation`, `noiseSuppression` and
   `autoGainControl` must remain `false` in `getUserMedia` constraints
   (`static/audio.js`, `MIC_CONSTRAINTS`).
3. **No PII in object keys, filenames, logs or exports.** Only the opaque
   `speaker_id` ULID. Names, emails, phones and caste live in the `speakers`
   table and nowhere else.
4. **Caste/ethnicity is optional and never exported.** It is sensitive personal
   information under Nepal's Individual Privacy Act 2075 s.27(2). The export
   path goes through `Speaker.export_row()`, which cannot reach it.
5. **Server-side QC is authoritative.** Client metrics are a UX convenience;
   `app/services/audio_qc/` re-reads the stored bytes and decides pass/fail.
6. **Splits are speaker-disjoint.** Never let one voice appear in both train
   and test. `assign_splits()` assigns whole speakers, never individual clips.

The `tests/` suite asserts rules 3, 4, 5 and 6. If you change any of them,
that test should fail — if it doesn't, the test is wrong too.

## Layout

Grouped by concern. One folder per area of responsibility; one file per table,
per resource, per backend. Keep files under ~250 lines and single-concern.

```
app/
  main.py                 app factory + wiring ONLY (no business logic)
  core/                   config, db session, ULIDs, security
  models/                 one module per table; __init__ re-exports them all
  schemas/                one module per resource; common.py for shared shapes
  api/
    deps.py               shared Depends(): get_db, get_thresholds, pagination
    routes/               one module per resource; __init__ builds the parent router
  services/               domain logic, no FastAPI imports
    audio_qc/             metrics.py (physics) | thresholds.py (policy) | gate.py (messages)
    storage/              base.py | keys.py | local.py | s3.py; __init__ picks the backend
    consent.py
static/
  recorder/               the contributor UI
  review/                 the validation UI
  shared/                 helpers used by both
migrations/               Alembic; versions/0001_baseline_schema.py is the baseline
tests/                    pytest; conftest.py sandboxes DB + storage before app import
scripts/                  thin operational entry points
```

Import from the package, not the module: `from app.models import Clip`,
`from app.services.storage import get_storage, raw_key`. `app/storage.py` is a
deprecated shim kept for older references.

## Commands

```bash
python scripts/init_db.py                      # alembic upgrade head
python scripts/init_db.py --stamp              # pre-Alembic DB: mark, don't replay
python scripts/import_prompts.py data/prompts_ne.jsonl
python scripts/smoke_test.py                   # wraps pytest; -k to filter
uvicorn app.main:app --reload
python scripts/qc_report.py
python scripts/export_dataset.py --format asr --sr 16000 --out export_out/asr
```

**Schema changes go through Alembic, never `create_all()`.** `create_all()` adds
missing tables but never adds a column to an existing one, so a new model field
silently does not exist on any database that has already run, and every insert
fails at runtime with `no such column`.

```bash
alembic revision --autogenerate -m "what changed"
alembic upgrade head
```

## Conventions

- Python 3.11+, type hints, `from __future__ import annotations`.
- No ORM lazy loading across request boundaries; query explicitly.
- Frontend is dependency-free vanilla JS modules. Don't add a framework.
- UI copy is Nepali-first. Error messages tell the reader what to physically
  change (move the mic, close the window), not what the code did.
- Scripts print Nepali, so call `use_utf8()` from `scripts/_console.py` at the
  top of `main()` — Windows consoles default to cp1252 and will raise otherwise.
- Route modules stay about their own resource; anything shared goes in
  `app/api/deps.py`. Services never import FastAPI.
- `BASE_DIR` in `app/core/config.py` is `parents[2]`. If that file ever moves,
  fix it — everything resolving `static/` and `docs/` hangs off it.

## Good next tasks

- Validation UI at `/review` for a second person to approve/reject clips. The
  `clips` table already has `verify_status`, `verified_by` and `verified_at`,
  and `export_dataset.py` already honours `--verified-only`. Only the UI and
  two routes are missing. This is the highest-value next task: automated QC
  catches noise and clipping but cannot catch a clean misread.
- Montreal Forced Aligner pass to flag misreads automatically.
- Resumable sessions via a signed link so a speaker can return later.
- Rate limiting and a simple abuse check on `/api/speakers`.
