# ADR-007 — Quality gate and human review

**Status:** Accepted.

## Context

You cannot listen to 40,000 clips. But automated measurement cannot catch the
failure that matters most for training: a **clean misread** — someone saying the
wrong word, clearly, at a good level, in a quiet room. Every meter says that
clip is perfect.

## Decision

Three layers, each catching what the one before it cannot.

### 1. Client-side QC — speed

`static/recorder/audio.js` computes SNR, peak dBFS, clipping ratio, noise floor
and silence padding immediately after each take. The contributor gets an answer
in milliseconds and can re-record on the spot.

### 2. Server-side QC — authority

`app/services/audio_qc/` re-reads the bytes that actually landed in storage and
decides. Client numbers are recorded but never trusted.

This is not paranoia about malice; it is about drift. Browsers differ, and a
client whose measurement is subtly wrong would otherwise silently admit bad
clips. The client metrics are stored alongside the server's precisely so a
divergence is visible.

The SNR definition matters: RMS is taken across the **whole speech span**, not
only frames above threshold. Measuring only the loud frames flatters a recording
whose noise is audible between syllables — which is exactly the recording you
want to reject.

Failure messages name the physical thing to change — move the mic, close the
window, turn the fan off — not what the code measured. A contributor cannot act
on "SNR 22 dB".

### 3. ASR pre-filter — leverage

The target text is already known, so this is far easier than open transcription.
Transcribe, compute character error rate against `prompt_text`, then:

- CER < 0.10 → auto-verify
- CER > 0.40 → auto-reject as a misread
- between → a human, ordered by uncertainty

Typically removes 60–80% of the human queue.

**Empty ASR output routes to a human, never to auto-reject.** A model with no
Tharu, Magar or Newar training data returns nothing at all. Auto-rejecting on
empty output would silently delete every clip in exactly the minority languages
this project exists to serve, and it would look like the filter working. The CER
of an empty hypothesis against a real prompt is 1.0, which is above the reject
threshold — so the empty case is handled explicitly rather than falling through
the banding.

**Numeral mismatches are flagged, not scored.** `२०७५` and `2075` are the same
utterance; the normaliser maps Devanagari digits to ASCII so they compare equal.
A model that writes numbers differently from the prompt should not be treated as
having heard a misread.

The normaliser is the most dangerous code in the system: it decides which clips
a human never sees. A normaliser that is slightly wrong auto-rejects good clips
in bulk, and nobody notices, because the entire point of the pre-filter is that
no human looks at what it decided. It is therefore implemented in-repo and
tested — `jiwer` is not a dependency — so the code deciding auto-reject is
testable in a base install.

### 4. Human review — the misread

`/review`, keyboard-driven, batch-prefetched. Queue policy samples rather than
reviewing everything: 100% of a speaker's first 20 clips, then 10% for a clean
speaker, snapping back to 100% if their rejection rate climbs. Speaker quality is
strongly autocorrelated.

**QC metrics and the ASR transcript are withheld until after the verdict.**
Showing "SNR 42 dB" beside the play button anchors the reviewer into passing;
showing the ASR text means they review the transcript rather than the audio, and
inherit whatever the model got wrong. Both appear immediately afterwards, where
they help audit the call instead of making it.

Verdicts are append-only: `Clip.verify_status` is current state, `ReviewEvent`
is how it got there. A column that gets overwritten cannot answer "who rejected
this and when", nor support inter-reviewer agreement.

## Consequences

- `faster-whisper` is optional. Without it every QC-passing clip goes to a human
  and `/review` works unchanged. The human path never depends on the optional
  path.
- Structured reject reasons enable `scripts/prompt_health.py`: five different
  speakers misreading one sentence means the sentence is ambiguous, not the
  speakers. Requires ≥5 distinct speakers before acting.
- Schema for the review pass was added by Alembic migration `0002_review_pass`,
  not `create_all()`. Autogenerate emitted `review_priority` as `NOT NULL` with
  no server default, which fails outright on Postgres against a non-empty table.
  Caught before deployment; the migration carries `server_default="0"`.
- Inter-reviewer agreement returns `None` until something creates two-human
  overlap on a clip. The plumbing exists; nothing generates the overlap yet.

## Enforced by

- `tests/test_audio_qc.py` — clean passes at ~47 dB, noisy rejected at ~10 dB
- `tests/test_review.py` — CER normalisation, queue policy, verdict trail,
  metrics withheld before verdict
- `CLAUDE.md` rules 6, 8 and 11
