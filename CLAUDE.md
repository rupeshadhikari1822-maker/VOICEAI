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
   `app/audio_qc.py` re-reads the stored bytes and decides pass/fail.
6. **Splits are speaker-disjoint.** Never let one voice appear in both train
   and test. `assign_splits()` assigns whole speakers, never individual clips.

`scripts/smoke_test.py` asserts rules 3, 4, 5 and 6. If you change any of them,
that test should fail — if it doesn't, the test is wrong too.

## Layout

```
app/main.py       FastAPI routes
app/models.py     SQLAlchemy schema (privacy boundary lives here)
app/storage.py    S3/local adapter, presigned PUT, key layout
app/audio_qc.py   SNR, peak, clipping, silence analysis — authoritative
app/config.py     env-driven settings
app/consent.py    consent text loading + SHA-256
app/ids.py        ULIDs, no dependency
static/           recorder UI (index.html, recorder.js, audio.js, pcm-worklet.js)
scripts/          init_db, import_prompts, export_dataset, qc_report, withdraw, smoke_test
data/             prompt JSONL files
docs/             recording guide, consent text, deployment
```

`static/audio.js` holds capture + WAV encoding + client QC.
`static/recorder.js` holds only the step flow and API calls.

## Commands

```bash
python scripts/init_db.py
python scripts/import_prompts.py data/prompts_ne.jsonl
python scripts/smoke_test.py
uvicorn app.main:app --reload
python scripts/qc_report.py
python scripts/export_dataset.py --format asr --sr 16000 --out export_out/asr
```

## Conventions

- Python 3.11+, type hints, `from __future__ import annotations`.
- No ORM lazy loading across request boundaries; query explicitly.
- Frontend is dependency-free vanilla JS modules. Don't add a framework.
- UI copy is Nepali-first. Error messages tell the reader what to physically
  change (move the mic, close the window), not what the code did.
- Scripts print Nepali, so call `use_utf8()` from `scripts/_console.py` at the
  top of `main()` — Windows consoles default to cp1252 and will raise otherwise.

## Good next tasks

- Validation UI at `/review` for a second person to approve/reject clips. The
  `clips` table already has `verify_status`, `verified_by` and `verified_at`,
  and `export_dataset.py` already honours `--verified-only`. Only the UI and
  two routes are missing. This is the highest-value next task: automated QC
  catches noise and clipping but cannot catch a clean misread.
- Montreal Forced Aligner pass to flag misreads automatically.
- Resumable sessions via a signed link so a speaker can return later.
- Rate limiting and a simple abuse check on `/api/speakers`.
