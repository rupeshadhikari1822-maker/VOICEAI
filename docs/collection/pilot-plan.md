# Pilot plan — the first 50 speakers

The goal of the pilot is **not** to collect 50 hours. It is to find out what
breaks when real people use this, while the number of affected people is still
small enough to apologise to individually.

## Before the first contributor

- [ ] `scripts/check_deployment.py https://record.cloudfrm.ai` — clean
- [ ] One sentence recorded on a **real phone over mobile data**, all the way
      through to a QC verdict. Nothing server-side tests bucket CORS, mic
      permission and the AudioWorklet together.
- [ ] Try one Android and one iPhone if both are available. An iPhone-only
      failure isolates to the platform immediately; a single-device failure
      could be anything.
- [ ] `docs/consent-ne.md` reviewed by a Nepali lawyer **if** the dataset may
      ever be licensed commercially. The commercial opt-in cannot be
      retro-fitted.
- [ ] Object versioning on the bucket.
- [ ] Someone named who can action a withdrawal request within a few days.

## Sequence

**First 3 speakers — sit with them.** Watch the screen, do not coach. Where they
hesitate is a UI problem, not a user problem. Expect to change prompt wording.

**Next ~10 — remote, but stay reachable.** This is where device diversity
appears: older Androids, unusual browsers, Bluetooth earbuds nobody mentioned.

**Then open to the rest.** By now the failure modes are known and the runbook
has been used at least once.

## Watch during

```bash
scripts/qc_report.py          # pass rate, failure reasons, per-speaker share
scripts/prompt_health.py      # sentences several people misread
scripts/backup_corpus.py --verify
```

| Signal | Meaning |
|---|---|
| Pass rate below ~70% | The environment guidance is not landing. Read the failure reasons — usually noise floor. |
| One speaker over 50% of audio | `qc_report.py` warns. See §49/§50 in [reconciliation](../roadmap/reconciliation.md) — there is no cap yet, so this needs watching by hand. |
| A prompt rejected by ≥5 speakers | The sentence, not the readers. `prompt_health.py --deactivate`. |
| Preflight blocks appearing | Bucket configuration. Stop and fix before more sessions. |

## Deliberately not automated yet

**Per-speaker quotas (§49)** and **corpus balance targets (§50)** do not exist.
Nothing stops five enthusiastic speakers dominating the corpus.

That is a real gap, recorded as such. It is correct to defer — setting a cap
before seeing a real distribution means guessing, and a wrong cap turns away
willing contributors — but it means **watching the per-speaker share by hand
during the pilot**. The pilot is what produces the data to set those numbers
against.

## What good looks like at the end

- 50 speakers, spread across more than two provinces and both broad age halves
- Pass rate above 70%
- Every failure mode in the runbook has either been seen or ruled out
- The audit runs clean
- At least one withdrawal request tested end to end — ask a friendly contributor
  to request removal, then verify with `--verify`. A withdrawal path that has
  never been exercised is a promise, not a feature.
