# Collection

Everything about getting audio from a person into the corpus.

| | |
|---|---|
| [recording-guide.md](recording-guide.md) | What contributors are told: room, mic, delivery. Nepali-first. |
| [pilot-plan.md](pilot-plan.md) | How to run the first 50-speaker round. |
| **Consent text** | Lives at **[`../consent-ne.md`](../consent-ne.md)** — see below. |

## Why the consent text is not in this folder

`docs/consent-ne.md` looks like it belongs here. It is deliberately left where
it is.

**That file is application input, not documentation.** `app/services/consent.py`
reads it at runtime to compute the SHA-256 stored against every speaker record:

```python
CONSENT_FILE = "docs/consent-ne.md"
path = get_settings().base_dir / CONSENT_FILE
```

Two things follow.

**Moving it stops the app.** The loader resolves that literal path from the
repository root, and a missing file now raises `ConsentTextMissing` during
startup rather than substituting placeholder text.

That was not always true. It originally fell back to built-in text, so a
mis-deployed consent file did not crash anything — the app kept collecting and
hashed the placeholder. That is strictly worse than a crash, and it is why the
behaviour changed.

**Changing one byte invalidates every existing record.** Including a trailing
newline. The stored hash is what proves what a contributor agreed to; if the
file changes, every speaker recorded before the change appears to have consented
to text they never saw. There is no way to repair that afterwards — you cannot
go back and re-obtain consent for audio you already hold.

If it ever must move, the move needs: the loader path updated, `sha256sum`
proven byte-identical before and after, `/api/config` returning the same
`consent.sha256`, and a test that fails when the file cannot be found. The
filing benefit is not worth that risk today.

## Editing the consent text

Editing it is a deliberate act with consequences, not a documentation change.

1. Have the new text reviewed by a Nepali lawyer before collection.
2. Bump `CONSENT_VERSION` in `.env`. Old records keep pointing at the old hash,
   which is the point: the change becomes visible rather than silent.
3. Redeploy, then run `scripts/check_deployment.py` — it compares the deployed
   hash against this checkout and warns when they diverge.

Contributors who consented under the old version consented to the old version.
A version bump does not retroactively extend their permission. Commercial
assignment in particular **cannot be retro-fitted**.

See [ADR-003](../architecture/ADR-003-consent-model.md).
