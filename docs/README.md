# Documentation

## Start here

**New to the codebase?** [onboarding.md](onboarding.md) — running in ten
minutes, then the three ADRs to read before changing anything.

**Deploying or on call?** [operations/runbook.md](operations/runbook.md) is
symptom-first. [operations/deployment.md](operations/deployment.md) is the
ordered runbook for a fresh box.

**Handed a task from the planning document?**
[roadmap/reconciliation.md](roadmap/reconciliation.md) **first.** Several
sections describe approaches that were deliberately rejected, and implementing
them looks exactly like doing your job.

**Running a collection round?** [collection/pilot-plan.md](collection/pilot-plan.md).

## By audience

### Developers

| | |
|---|---|
| [onboarding.md](onboarding.md) | First day: clone, run, record, review, read |
| [architecture/](architecture/) | Seven ADRs — what was decided and what it costs |
| [architecture/README.md](architecture/README.md) | What an ADR is; how to add one |

### Operators

| | |
|---|---|
| [operations/deployment.md](operations/deployment.md) | DNS → VPS → CORS → verify → phone → link |
| [operations/runbook.md](operations/runbook.md) | Symptom first. Written for 2am. |
| [operations/backup-and-restore.md](operations/backup-and-restore.md) | What is irreplaceable and how to get it back |

### Collection

| | |
|---|---|
| [collection/recording-guide.md](collection/recording-guide.md) | What contributors are told. Nepali-first. |
| [collection/pilot-plan.md](collection/pilot-plan.md) | The first 50 speakers |
| [collection/README.md](collection/README.md) | Why the consent text is not filed here |
| [consent-ne.md](consent-ne.md) | **Application input.** Do not move or edit casually. |

### Planning

| | |
|---|---|
| [roadmap/reconciliation.md](roadmap/reconciliation.md) | Section → Built / Deviated / Deferred / Gap |
| [roadmap/cloudfarm-vision.md](roadmap/cloudfarm-vision.md) | The long-range plan (placeholder — not yet pasted in) |

## Two files that are not documentation

**[`consent-ne.md`](consent-ne.md)** is read at runtime by
`app/services/consent.py` to compute the hash stored against every speaker.
Moving it breaks registration; changing a byte invalidates every existing
consent record. It sits in `docs/` root for that reason —
[collection/README.md](collection/README.md) explains it.

**`../CLAUDE.md`** is context for AI coding sessions, and it carries the list of
decisions that must not be silently reversed. If you change something load-bearing,
change it there too.

## The shape of this

Decisions live in ADRs, not in code comments and not in commit messages. A
comment explains what a line does; an ADR explains why an alternative was
rejected, which is the thing a future reader actually needs and the thing that is
hardest to reconstruct.

Where a decision can be defended by a test rather than a document, it is —
`architecture/README.md` lists which. Documents drift. Tests fail.
