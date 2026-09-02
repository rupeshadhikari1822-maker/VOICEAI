# A first day on this codebase

## Get it running

```bash
git clone https://github.com/rupeshadhikari1822-maker/VOICEAI.git
cd VOICEAI
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

python scripts/init_db.py                            # alembic upgrade head
python scripts/import_prompts.py data/prompts_ne.jsonl
pytest -q                                            # expect 109 passing
uvicorn app.main:app --reload
```

No cloud account needed. `STORAGE_BACKEND=local` writes to `./storage_local/`.

## Record a clip, then review it

Open <http://localhost:8000> and go through it as a contributor would — consent,
profile, mic check, one sentence. Do not skim this; the mic check is where most
of the field failures surface, and you want to know what it looks like working.

Then the other side:

```bash
REVIEWER_TOKENS=me:local-dev-token uvicorn app.main:app --reload
```

<http://localhost:8000/review?token=local-dev-token>

Notice what the review queue does **not** show you before you commit a verdict.
That is deliberate — [ADR-007](architecture/ADR-007-quality-gate-and-review.md).

## Read these three before changing anything

1. **[ADR-001 — Audio capture](architecture/ADR-001-audio-capture.md)**
   Why `AudioWorklet` and not `MediaRecorder`, why the DSP flags are off, and
   why there is a zero-gain node that looks like dead code.
2. **[ADR-003 — Consent model](architecture/ADR-003-consent-model.md)**
   Why `docs/consent-ne.md` is application input rather than documentation, and
   why this is the one mistake with no remedy.
3. **[ADR-002 — Storage and formats](architecture/ADR-002-storage-and-formats.md)**
   Why 48 kHz masters, and why no PII ever reaches an object key.

Then skim [reconciliation.md](roadmap/reconciliation.md). If you are handed a
task from the long-range planning document, check it there first — several
sections describe approaches that were deliberately rejected, and following them
looks exactly like doing your job.

## Rules enforced by tests, not convention

Some constraints here are pinned by tests rather than left in a document:

| Rule | Test |
|---|---|
| `app/` root holds two files | `test_app_root_holds_only_the_entry_point` |
| Exports carry no PII | `test_export_row_contains_no_pii` |
| Splits are speaker-disjoint | `test_splits_are_speaker_disjoint` |
| Backups exclude probes and derived sets | `test_backup_prefixes_exclude_preflight_probes` |
| Production refuses unsafe config | `test_every_problem_is_reported_at_once` |

This is deliberate. The last stray module in `app/` survived two jobs of work
precisely because the rule against it was only written down. **A markdown rule is
advice; a failing test is a rule.**

If you find yourself writing "we should always..." in a comment, ask whether it
can be a test instead.

## A test passing only means nothing checked

Worth internalising early, from this codebase:

Six tests validated the production configuration guard. Their fixture set
`storage_backend: "s3"` and no endpoint URL at all. They passed — green, for
weeks — because nothing validated the endpoint. The moment endpoint validation
was added, all six failed instantly.

They were never testing what they appeared to test. The fixture was incomplete
and the suite could not tell.

So: when you add a guard and existing tests break, the first question is not
"how do I make them pass" — it is "were they ever checking this". Here the fix
was to complete the fixture, not to loosen the guard.

## Where things live

```
app/core/      config, db, ids, security      app/api/       deps + routes
app/models/    one module per table           app/schemas/   one per resource
app/services/  domain logic, no FastAPI       static/        recorder/ review/ shared/
scripts/       operational entry points       migrations/    Alembic
tests/         pytest; conftest sandboxes DB and storage before app import
```

Full layout and the reasoning:
[ADR-004](architecture/ADR-004-repository-structure.md).

## Two things that will bite you

**Schema changes go through Alembic, never `create_all()`.** `create_all()` adds
missing *tables* but never adds a *column* to a table that already exists. On any
database that has already run, a new model field silently does not exist and
every insert fails at runtime with `no such column`.

```bash
alembic revision --autogenerate -m "what changed"
alembic upgrade head
```

Check what autogenerate produced before committing it. It emitted a `NOT NULL`
column with no server default once, which fails outright on Postgres against a
non-empty table.

**Scripts print Nepali.** Call `use_utf8()` from `scripts/_console.py` at the top
of `main()`. Windows consoles default to cp1252 and raise `UnicodeEncodeError` on
Devanagari — which is a poor way for a Nepali-first tool to fail.

## Working rule

Plan, implement, test, inspect, fix, commit, next. One concern per commit.

Run the app and click through it before saying something works. Several bugs in
this codebase's history were invisible to a passing test suite and obvious within
ten seconds of loading the page.
