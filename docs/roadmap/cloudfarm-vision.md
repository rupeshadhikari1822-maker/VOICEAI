# CloudFARM Voice Studio — long-range plan

> **This file is a placeholder. The document is not here yet.**
>
> The 72-section planning document was not available in the repository or in the
> session that created this folder, so it could not be stored verbatim. Nothing
> below is a summary of it — inventing section content would be worse than
> leaving it empty, because a fabricated §23 is indistinguishable from a real
> one once it is committed.

## To fill this in

Paste the document here, unedited, exactly as written. Do not paraphrase, tidy
or reorder it. The value of storing it verbatim is that
`docs/roadmap/reconciliation.md` can cite section numbers that mean something,
and that a future reader can see what was actually proposed rather than someone's
recollection of it.

Then work through it and complete the reconciliation table — one row per section
that touches the code. Roughly sixty sections are currently unreviewed.

## What this document is, and is not

It is a **two-year plan**, not a task list, and not a specification of the
current system.

Parts of it describe approaches that were considered and deliberately rejected
during implementation. Following those literally would damage the corpus in ways
that are not obvious from the section text:

- **§3** specifies MediaRecorder. It produces lossy Opus at capture. Adopting it
  makes the audio permanently unsuitable for TTS training.
- **§16** names 16 kHz as the archival format. Downsampling is reversible only
  in one direction.

Both look like ordinary specification compliance. Neither is recoverable after
the fact.

**Read `docs/roadmap/reconciliation.md` before implementing anything from this
document.** It maps each reviewed section to Built, Deviated, Deferred or Gap,
with an ADR for every deviation and a trigger condition for every deferral.

## Where the plan is ahead of the code

Two sections describe things that genuinely should exist and do not: per-speaker
contribution quotas (§49) and corpus balance targets (§50). Both are recorded as
**Gap** in the reconciliation table, with "after the 50-speaker pilot" as the
trigger.
