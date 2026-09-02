# ADR-004 — Repository structure

**Status:** Accepted. Roadmap §7 is deferred, not rejected.

## Context

The first version put everything in flat modules: `app/main.py` held all twelve
routes at 407 lines, and a single flat storage module held two backends plus key
naming. Adding
the review pass on top of that would have made every change risk breaking
something unrelated.

## Decision

Group by concern. One folder per area of responsibility, one file per table, per
route group, per storage backend.

```
app/
  main.py                 app factory and wiring only — 55 lines
  core/                   config, db session, ids, security
  models/                 one module per table
  schemas/                one module per resource
  api/deps.py + routes/   one module per resource
  services/               domain logic; no FastAPI imports
    audio_qc/             metrics (physics) | thresholds (policy) | gate (messages)
    storage/              base | keys | local | s3
    review/               queue | verdicts | normalize | asr_prefilter | reasons | stats
```

**`app/` root holds `main.py` and `__init__.py` and nothing else.** Every module
belongs to one of the five packages. A file loose in `app/` means someone could
not decide which concern it served; the fix is to decide then, not defer.

That rule is enforced by `test_app_root_holds_only_the_entry_point`, not by
convention. The previous stray — a compatibility shim from the restructure,
since deleted — survived two jobs of work precisely because it was only
written down. A markdown rule is advice; a failing test is a rule.

Target: no file over ~250 lines, no file mixing two concerns. `audio_qc` was
split three ways because measurement, policy and contributor-facing messages
change for different reasons and at different times.

### Differs from roadmap §7

§7 proposes `frontend/ backend/ audio_pipeline/ ml/`.

That is a reasonable monorepo shape — **later**. It assumes those are four
things maintained by different people. Right now there is no `ml/` code in the
repo at all, the "audio pipeline" is one 164-line module, and the frontend is
five dependency-free files.

Migrating now costs days of import churn and buys nothing before the pilot.

**Deferred, with a trigger:** revisit when ML training code actually exists in
this repository. At that point `ml/` stops being a hypothetical folder and the
split starts paying for itself.

## Consequences

- Import from the package, not the module: `from app.models import Clip`,
  `from app.services.storage import get_storage, raw_key`.
- `__init__.py` re-exports keep those paths stable when files move underneath.
- Adding a resource means one module in `api/routes/` and one line in
  `api/routes/__init__.py`. `main.py` never changes.
- Schema changes go through Alembic. `create_all()` adds missing tables but
  never adds a column to an existing one — see
  [ADR-007](ADR-007-quality-gate-and-review.md) for what that nearly cost.

## Enforced by

- `tests/test_deploy_guard.py::test_app_root_holds_only_the_entry_point`
- `CLAUDE.md` layout section
