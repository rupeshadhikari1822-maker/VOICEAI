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
2. **The worklet node keeps a muted path to `destination`.** `audio.js` routes
   the AudioWorkletNode through a zero-gain node to the destination. It looks
   like dead code and is not: WebKit can treat a graph with no route to
   destination as inactive and stop calling `process()`, which presents as a
   frozen level meter with no error anywhere. Do not remove it.
3. **Browser DSP stays off.** `echoCancellation`, `noiseSuppression` and
   `autoGainControl` must remain `false` in `getUserMedia` constraints
   (`static/recorder/audio.js`, `MIC_CONSTRAINTS`).
4. **No PII in object keys, filenames, logs or exports.** Only the opaque
   `speaker_id` ULID. Names, emails, phones and caste live in the `speakers`
   table and nowhere else.
5. **Caste/ethnicity is optional and never exported.** It is sensitive personal
   information under Nepal's Individual Privacy Act 2075 s.27(2). The export
   path goes through `Speaker.export_row()`, which cannot reach it.
6. **Server-side QC is authoritative.** Client metrics are a UX convenience;
   `app/services/audio_qc/` re-reads the stored bytes and decides pass/fail.
7. **Splits are speaker-disjoint.** Never let one voice appear in both train
   and test. `assign_splits()` assigns whole speakers, never individual clips.
8. **The review queue never shows QC metrics or ASR text before a verdict.**
   Showing SNR anchors the reviewer into passing; showing the ASR transcript
   means they review the transcript instead of the audio. Both are returned in
   the verdict response, which is where they help.
9. **The production guard must not be weakened.** With `ENVIRONMENT=production`,
   `app/core/config.py` refuses to boot on local storage, SQLite, a non-https
   base URL, or the default secret. Do not add silent fallbacks to it.
10. **Never let a contributor record before the storage preflight passes.**
   Bucket CORS cannot be tested server-side, so the recorder proves uploads
   work with a real cross-origin PUT at session start. Removing that check
   trades a clear error for twenty-five wasted sentences.
11. **Review history is append-only.** Every verdict writes a `ReviewEvent` as
   well as updating `Clip.verify_status`. Never update or delete an event -- a
   changed verdict is a new row. Undo is scoped to the caller's own last one.

The `tests/` suite (`pytest -q`) asserts rules 4, 5, 6 and 7. If you change any of them,
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
    review/               queue.py | verdicts.py | normalize.py | asr_prefilter.py | reasons.py
    consent.py
static/
  recorder/               the contributor UI
  review/                 the validation UI
  shared/                 helpers used by both
migrations/               Alembic; versions/0001_baseline_schema.py is the baseline
tests/                    pytest; conftest.py sandboxes DB + storage before app import
scripts/                  thin operational entry points
deploy/                   Caddyfile, systemd unit, bootstrap.sh, production env template
```

Import from the package, not the module: `from app.models import Clip`,
`from app.services.storage import get_storage, raw_key`.

**`app/` root contains `main.py` and `__init__.py` and nothing else.** Every
module belongs to `core/`, `api/`, `models/`, `schemas/` or `services/`. A file
loose in `app/` means someone could not decide which concern it served; decide
then, rather than deferring. A test enforces this.

## Commands

```bash
python scripts/init_db.py                      # alembic upgrade head
python scripts/init_db.py --stamp              # pre-Alembic DB: mark, don't replay
python scripts/import_prompts.py data/prompts_ne.jsonl
pytest -q                                      # the test suite (102 tests)
python scripts/smoke_test.py                   # same thing, older entry point
uvicorn app.main:app --reload
python scripts/qc_report.py
python scripts/export_dataset.py --format asr --sr 16000 --out export_out/asr
python scripts/asr_prefilter.py --dry-run       # optional; shrinks the review queue
python scripts/prompt_health.py                 # prompts several people misread
python scripts/check_deployment.py https://record.cloudfrm.ai
python scripts/backup_corpus.py --verify         # rows vs objects audit
```

Deployment target is **record.cloudfrm.ai** (the studio). `voice.cloudfrm.ai` is
the separate static landing page. Runbook: `deploy/README.md`.

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

## Decisions that must not be silently reversed

Each links the record of why. Reversing one of these does not produce a bug that
shows up in a test — it produces a corpus that is quietly unusable, or a consent
record that cannot be defended. Read the ADR before changing any of them.

| Decision | Record |
|---|---|
| AudioWorklet, never MediaRecorder | [ADR-001](docs/architecture/ADR-001-audio-capture.md) |
| 48 kHz masters; derived sets generated on export | [ADR-002](docs/architecture/ADR-002-storage-and-formats.md) |
| `echoCancellation` / `noiseSuppression` / `autoGainControl` all false | [ADR-001](docs/architecture/ADR-001-audio-capture.md) |
| The zero-gain keepalive node to `destination` | [ADR-001](docs/architecture/ADR-001-audio-capture.md) |
| Server computes the consent SHA; the client's is ignored | [ADR-003](docs/architecture/ADR-003-consent-model.md) |
| No PII in object keys, logs or exports | [ADR-002](docs/architecture/ADR-002-storage-and-formats.md), [ADR-003](docs/architecture/ADR-003-consent-model.md) |
| Speaker-disjoint splits | [ADR-007](docs/architecture/ADR-007-quality-gate-and-review.md) |
| ULIDs, not sequential speaker IDs | [ADR-005](docs/architecture/ADR-005-speaker-identifiers.md) |
| `app/` root holds `main.py` and `__init__.py` only | [ADR-004](docs/architecture/ADR-004-repository-structure.md) |

## The long-range roadmap is not a task list

A 72-section planning document exists for this project. It is a **two-year
plan**, and several sections describe approaches that were considered and
deliberately rejected — §3 specifies MediaRecorder, §16 names 16 kHz as the
archival format. Implementing either destroys the corpus, and both look exactly
like following the spec.

**Check [`docs/roadmap/reconciliation.md`](docs/roadmap/reconciliation.md) before
implementing anything from it.** It maps each reviewed section to Built,
Deviated, Deferred or Gap, with an ADR for every deviation and a trigger
condition for every deferral.

That table is incomplete — roughly sixty sections are unreviewed. An absent row
means "nobody has checked", not "not applicable".

## Working rule

Plan, implement, test, inspect, fix, commit, next. One concern per commit.

Run the app and click through it before reporting that something works. Several
bugs here were invisible to a passing suite and obvious within ten seconds of
loading the page.

## Good next tasks

- Montreal Forced Aligner pass, for word-level timing on the clips the ASR
  pre-filter leaves ambiguous. Would let the review UI highlight *where* a
  reading diverged instead of just that it did.
- Inter-reviewer agreement in practice: route a small fixed percentage of
  already-settled clips back into the queue for a second opinion. The
  `ReviewEvent` history already supports measuring it; nothing currently
  creates the overlap.
- Resumable sessions via a signed link so a speaker can return later.
- Rate limiting and a simple abuse check on `/api/speakers`.
