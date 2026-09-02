# Architecture decision records

An ADR records **one decision, why it was made, and what it costs**. It is not a
design document and not a tutorial. It exists so that someone can tell in thirty
seconds whether they are allowed to change something, and what breaks if they do.

Several of these exist specifically because a plausible-looking change would
destroy the corpus in a way that is not obvious and not recoverable.

## The records

| | Decision | Reverse it and |
|---|---|---|
| [ADR-001](ADR-001-audio-capture.md) | AudioWorklet, 48 kHz PCM, DSP off | the audio is lossy at capture, forever |
| [ADR-002](ADR-002-storage-and-formats.md) | 48 kHz masters, derived sets on export | you can never restore what you did not keep |
| [ADR-003](ADR-003-consent-model.md) | Server-computed consent hash, scoped permissions | consent becomes unprovable and cannot be retro-fitted |
| [ADR-004](ADR-004-repository-structure.md) | Concern-based packages, two files in `app/` root | churn with no benefit before the pilot |
| [ADR-005](ADR-005-speaker-identifiers.md) | ULIDs, not sequential IDs | corpus size leaks and records become enumerable |
| [ADR-006](ADR-006-same-origin-deployment.md) | One origin for UI and API | CORS ambiguity enters every call, not just one |
| [ADR-007](ADR-007-quality-gate-and-review.md) | Layered QC, ASR pre-filter, human review | clean misreads reach the training set |

## Where they disagree with the roadmap

ADRs 001, 002, 005 and 006 contradict specific sections of the long-range
planning document. Each says which section and why the code is right.

`docs/roadmap/reconciliation.md` maps this in the other direction: roadmap
section → built, deviated, or deferred.

**Check reconciliation before implementing anything from the roadmap.**

## Adding one

Number it sequentially. Keep it to two pages. Use the same four headings:

```markdown
# ADR-00N — Title

**Status:** Proposed | Accepted | Superseded by ADR-00M

## Context
What situation forced a choice. Not the whole system — just the pressure.

## Decision
What was chosen, in the present tense. Name the files.

## Consequences
What this costs, including the things that are now harder.
Be honest here; an ADR that lists only benefits is marketing.

## Enforced by
Tests, guards, or CI that make the decision hard to reverse by accident.
```

A decision defended only by a document gets reversed. Where a decision can be
pinned by a test, pin it — that is why `test_app_root_holds_only_the_entry_point`
exists, and why the backup prefix allow-list is asserted rather than commented.

Superseding is normal. Write a new ADR, mark the old one superseded, and leave
it in place. Deleting the record of a decision deletes the reason nobody should
try it again.
