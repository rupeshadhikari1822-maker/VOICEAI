# ADR-003 — Consent model

**Status:** Accepted. This is the one decision with no remedy if it is wrong.

## Context

The project collects, from the same person at the same moment: a voice
biometric, optionally a name, email and phone, and optionally caste or
ethnicity.

Under Nepal's Individual Privacy Act 2075 (2018), biometric data is protected
personal information (s. 2(c)), and **caste and ethnicity are explicitly
sensitive personal information (s. 27(2))**. Collection requires informed,
specific, documented consent, and the data may be used only for the stated
purpose.

## Decision

### The server computes the consent hash, not the client

`app/services/consent.py` reads `docs/consent-ne.md` at runtime, computes its
SHA-256, and stores that hash on the `ConsentRecord` alongside a version string.

The client submits only the version. Any SHA the client sends is ignored.

A client-supplied hash proves nothing — it attests to what the client claims it
displayed. The server's hash attests to what the server actually served. If the
wording is ever changed, old records still point at the old hash, and the change
becomes visible rather than hidden. That is what turns a consent record from a
boolean into evidence.

> **`docs/consent-ne.md` is read at runtime and is deliberately not filed under
> `docs/collection/`.** Moving it breaks speaker registration at boot. Changing
> a single byte — including the trailing newline — makes every previously
> recorded speaker appear to have consented to different text than they did.

### Separate scopes, asked before recording

Commercial use is a separate opt-in checkbox, not bundled into general consent.
It is asked before the first recording because **it cannot be retro-fitted**.
There is no mechanism to go back to fifty contributors and obtain a permission
you did not ask for, and using the audio without it is not an option.

Declining commercial use does not exclude a contributor from participating.

### Caste and ethnicity

Optional, with an explicit "prefer not to say". Stored on the `speakers` table,
separate from any recording metadata. **Never exported** — not in a filename,
not in an object key, not in a manifest.

`Speaker.export_row()` is an allow-list of seven non-identifying fields. It is
an allow-list rather than a deny-list on purpose: a deny-list leaks any column
somebody adds later.

### Region, not address

Province / district / municipality / ward. That gives the dialect-region signal
the corpus actually needs for coverage. A house number gives liability and
nothing else.

### Withdrawal actually deletes

`scripts/withdraw.py` deletes the objects from storage, tombstones the clip rows,
and scrubs the PII columns — in that order, so a crash never leaves data more
exposed than it started.

Clip rows survive as tombstones carrying no personal data and no audio, so a
dataset already exported can be diffed against the current corpus to see what
must be pulled.

`scripts/backup_corpus.py --verify` independently confirms this works: it reports
tombstoned rows whose objects still exist. On the development corpus it shows six
tombstoned rows holding nothing, which is evidence rather than faith.

## Consequences

- `docs/consent-ne.md` is load-bearing application input, not documentation.
- `CONSENT_VERSION` in `.env` must match the deployed text.
  `scripts/check_deployment.py` compares the served hash against the repo's copy
  and warns when they diverge.
- Serving the built-in fallback text — which happens if the file is missing — is
  a **failure**, and `check_deployment.py` treats it as one.
- A dataset intended for commercial licensing needs a Nepali lawyer to review
  `docs/consent-ne.md` before the first session, not after.

## Enforced by

- `tests/test_smoke.py` — consent required, stale version refused, hash matches
  served text, export rows carry no PII
- `scripts/check_deployment.py` — deployed consent hash vs. this checkout
- `CLAUDE.md` rules 4 and 5
