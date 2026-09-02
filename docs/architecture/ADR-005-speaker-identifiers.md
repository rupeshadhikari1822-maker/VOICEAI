# ADR-005 — Speaker identifiers

**Status:** Accepted.

## Context

Every clip, object key and export row refers to a speaker. That identifier
travels further than any other field in the system: into object keys, into
published datasets, into filenames on other people's machines.

## Decision

**ULIDs.** 26 characters, Crockford base32, 48-bit millisecond timestamp plus
80 bits of entropy. `app/core/ids.py`, no dependency.

```
01M1F1KXR887839JSBEAFGXYT7
```

They sort by creation time, which is occasionally useful, and carry no other
information.

### Differs from roadmap §11

§11 proposes sequential identifiers of the form `SPK-000001`.

Two problems, both structural rather than stylistic:

**They leak corpus size.** `SPK-000042` tells anyone holding one clip that the
project has roughly forty-two speakers. That is a number you may want to
control, and it is disclosed by every filename you ever publish.

**They invite enumeration.** Given `SPK-000042`, an attacker with any read path
knows `SPK-000041` and `SPK-000043` exist. With ULIDs there is nothing to guess
— 80 bits of randomness per identifier.

The counter-argument is real: sequential IDs are easier to say out loud in a
research conversation. "Speaker forty-two had a lot of background noise" is
easier than reading 26 characters.

**That is a display problem, not a primary-key problem.** If human-readable
identifiers are wanted, add a display alias in an admin UI, mapped one-to-one to
the ULID and never written into an object key or an export. Do not change the
primary key to solve a conversational inconvenience.

## Consequences

- Object keys are long. Irrelevant.
- Identifiers are opaque to contributors, so the done screen shows the ULID and
  tells them to keep it — it is what they need to quote for a withdrawal request.
- Nothing else about a speaker leaves the system.
  `Speaker.export_row()` returns the ULID plus six coarse non-identifying
  attributes.

## Enforced by

- `tests/test_smoke.py::test_export_row_contains_no_pii`
- `tests/test_storage.py::test_keys_contain_only_the_opaque_id`
