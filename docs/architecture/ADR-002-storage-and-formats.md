# ADR-002 — Storage layout and audio formats

**Status:** Accepted. The archival format decision is irreversible in one
direction only — see Consequences.

## Context

Two different consumers want two different sample rates. ASR models
(Whisper, wav2vec2, MMS) train at 16 kHz. TTS models (VITS, Piper, XTTS) train
at 22.05 kHz. Storing at either rate is cheaper than storing at 48 kHz.

## Decision

Keep **48 kHz / 16-bit / mono masters** under `raw/`, immutable, forever.
Generate everything else on demand:

```
raw/{lang}/{speaker_id}/{session_id}/{clip_id}.wav      48k master, never modified
derived/16k/{lang}/{speaker_id}/{clip_id}.wav           ASR
derived/22k/{lang}/{speaker_id}/{clip_id}.wav           TTS, −23 LUFS
consent/{speaker_id}/consent_{version}.wav              spoken consent
_preflight/{ulid}.bin                                   1 KB CORS probe
```

`scripts/export_dataset.py` produces the derived sets. Nothing else writes to
`raw/`.

### Contradicts roadmap §16

§16 names 16 kHz as the archival format. **That inverts the priority.**

You can downsample forever. You can never restore. Choosing 16 kHz as the
archive saves storage — which is not the binding constraint at roughly
$2.60/month for 500 hours — at the cost of permanently foreclosing TTS work,
any future model that wants more bandwidth, and any re-derivation with better
resampling.

The asymmetry is the whole argument: a wrong choice toward more data costs
money, a wrong choice toward less data costs the corpus.

### On 24-bit

Not useful here. Browsers deliver Float32 from the audio graph, and 16-bit is
the honest endpoint for speech recorded on consumer microphones in domestic
rooms. The noise floor of the room is far above the 16-bit floor. Bit depth is
not where quality is won; the room and the mic distance are.

## No PII in object keys

Keys carry the opaque speaker ULID and nothing else. Not a name, not an email,
not a phone number, not caste.

An object key is effectively published to anyone with bucket access, and it is
baked into every backup from the moment it is written. A name in a key cannot be
recalled from a backup taken before you noticed.

`app/services/storage/keys.py` is the only module that builds keys, so there is
exactly one place to audit that claim.

## `_preflight/` sits outside everything

The CORS probe objects written at session start are excluded from both export
and backup. `BACKUP_PREFIXES` in `scripts/backup_corpus.py` is an **allow-list**
(`raw/`, `consent/`) rather than a skip-list, so any future prefix is excluded by
default rather than silently replicating to the offsite archive forever.

A bucket lifecycle rule should expire `_preflight/` after one day. That rule
must be scoped to that prefix and nothing else — a lifecycle rule with an empty
prefix, or one pointed at `raw/`, deletes the masters on a one-day timer,
quietly, with no error.

## Consequences

- Storage is dominated by `raw/`; `derived/` is regenerable and excluded from
  backup.
- Re-running an export after a threshold change is cheap and safe.
- Object versioning on the bucket is strongly recommended: it is the only
  defence against a bad `delete_prefix`.
- `scripts/backup_corpus.py --verify` audits rows against objects in both
  directions.

## Enforced by

- `tests/test_storage.py` — key layout, and that no PII string reaches a key
- `tests/test_deploy_guard.py` — backup prefixes exclude `_preflight/` and
  `derived/`
- `CLAUDE.md` rule 4
