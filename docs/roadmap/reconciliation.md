# Roadmap reconciliation

Maps the long-range planning document ("CloudFARM Voice Studio", 72 sections)
against what is actually built.

**Check this table before implementing anything from the roadmap.** Several
sections describe approaches that were considered and deliberately rejected;
following them literally would destroy the corpus in ways that are not obvious
from the section text alone.

## Status meanings

| Status | Meaning |
|---|---|
| **Built** | Implemented. The roadmap and the code agree. |
| **Deviated** | Deliberately done differently. An ADR says why. **Do not "fix" toward the roadmap.** |
| **Deferred** | Not done yet, and correct not to be. A trigger condition names when to revisit. |
| **Gap** | The roadmap is right and the code is missing it. |
| **N/A** | Not applicable to this codebase. |

---

## ⚠ This table is incomplete

The full 72-section document is **not in this repository**, and was not
available when this file was written. `docs/roadmap/cloudfarm-vision.md` is a
placeholder.

The rows below cover only the sections whose content is known from the
engineering discussions that produced these decisions. **Roughly sixty sections
are unreviewed.** Do not read an absent row as "not applicable" — read it as
"nobody has checked".

**To complete this:** paste the full document into
`docs/roadmap/cloudfarm-vision.md`, then work through it section by section and
add a row for each one that touches the code. That is a mechanical job and worth
doing once, properly.

---

## Reviewed sections

| § | Topic | Status | Notes |
|---|---|---|---|
| 3 | MediaRecorder API for capture | **Deviated** | [ADR-001](../architecture/ADR-001-audio-capture.md). MediaRecorder yields WebM/Opus — lossy at capture, unrecoverable. **Do not adopt.** |
| 6 | Split frontend/API subdomains | **Deferred** | [ADR-006](../architecture/ADR-006-same-origin-deployment.md). Adds CORS ambiguity to every call. **Trigger:** a dedicated frontend team, or a second API client. |
| 7 | `frontend/ backend/ audio_pipeline/ ml/` | **Deferred** | [ADR-004](../architecture/ADR-004-repository-structure.md). Reasonable monorepo shape later. **Trigger:** when ML training code actually exists in this repo. |
| 11 | Sequential speaker IDs (`SPK-000001`) | **Deviated** | [ADR-005](../architecture/ADR-005-speaker-identifiers.md). Leaks corpus size, invites enumeration. A display alias solves the readability need without touching the primary key. |
| 16 | 16 kHz as archival format | **Deviated** | [ADR-002](../architecture/ADR-002-storage-and-formats.md). Inverts the priority — you can downsample forever, you can never restore. 48 kHz masters are kept. |
| 30 | Speaker-disjoint splits | **Built** | `assign_splits()` in `scripts/export_dataset.py`; assigns whole speakers, never clips. Asserted in `tests/test_smoke.py`. |
| 49 | Per-speaker contribution quotas | **Gap** | Real gap. Nothing currently caps how much one speaker contributes; five enthusiastic people could dominate the corpus. `qc_report.py` warns when one speaker exceeds 50% of audio, which is detection, not prevention. **Trigger:** build after the 50-speaker pilot, when there is real distribution data to set a cap against. |
| 50 | Corpus balance targets | **Gap** | Real gap. No targets exist for gender, age band, province or mother tongue, and nothing steers recruitment toward under-represented cells. The data to measure it is collected — `Speaker.export_row()` carries all six axes — but nothing acts on it. **Trigger:** after the pilot, alongside §49. |
| 51 | Prometheus / Grafana monitoring | **Deferred** | Pure overhead at zero speakers. `/healthz`, `qc_report.py` and `backup_corpus.py --verify` cover current needs. **Trigger:** more than one VPS, or a second operator. |
| 70 | plan → implement → test → inspect → fix → commit | **Built** | Adopted as a working rule in `CLAUDE.md`. |

---

## On §49 and §50

These are the two places where the roadmap is right and the code is not there
yet. They are recorded as **Gap**, not reframed as unnecessary.

The document is not only wrong where it disagrees with the implementation. A
reconciliation table that marked every difference as a deviation in the code's
favour would be a rationalisation, not a record — and the next person to read it
would learn nothing they could act on.

Both are genuinely correct to defer: setting a per-speaker cap or a balance
target before seeing a real distribution means guessing at numbers, and a wrong
cap turns away willing contributors. But "after the pilot" is a decision with a
date attached. "Later" is forgetting.

## On deferrals generally

Every **Deferred** row above names a trigger. That is the difference between a
decision and an omission. When the trigger fires, the row should be revisited and
either built or re-deferred with a new trigger and a reason — not silently left.
