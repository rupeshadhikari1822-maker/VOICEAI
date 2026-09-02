# ADR-001 — Audio capture

**Status:** Accepted. Load-bearing. Do not reverse without reading Consequences.

## Context

The corpus exists to train ASR and TTS models. Whatever the browser captures is
the ceiling on everything downstream — no later processing recovers information
that was never recorded.

Browsers offer two routes. `MediaRecorder` is the obvious one, and it is what
most tutorials and the roadmap document reach for. It produces WebM/Opus.

## Decision

Capture raw Float32 PCM through an `AudioWorklet` and encode 48 kHz / 16-bit /
mono WAV in the browser. `static/recorder/pcm-worklet.js` and
`static/recorder/audio.js`.

Disable every browser DSP stage in the `getUserMedia` constraints:

```js
echoCancellation: false,
noiseSuppression: false,
autoGainControl: false,
```

### Contradicts roadmap §3

§3 specifies the MediaRecorder API. **Do not adopt it.**

Opus is a lossy speech codec. It discards exactly the high-frequency detail a
vocoder learns from, and the loss happens at capture — there is no version of
the audio that ever contained it. A corpus recorded through MediaRecorder cannot
be repaired, only re-recorded, and the speakers have gone home.

Auto gain control is the subtler killer. It rides the level between sentences,
so one speaker's clips arrive at inconsistent loudness across a single session.
A TTS model trained on that sounds unstable in a way that is hard to trace back
to its cause.

### The DSP flags are a request, not a guarantee

Browsers may ignore them. That is why `static/recorder/recorder.js` reads
`track.getSettings()` back after the stream opens and reports each flag the
browser refused to honour, on the mic-check screen. A silent override would
otherwise produce a corpus that looks fine and trains badly.

### The iOS keepalive

The worklet node is created with `numberOfOutputs: 1` and routed through a
**zero-gain** node to `context.destination`.

This looks like dead code. It is not.

A capture-only graph with no path to destination is the architecturally honest
shape — we are recording, not playing. It works on Chrome. WebKit has
historically treated such a graph as inactive and stopped calling `process()`,
which produces a uniquely unhelpful failure: permission granted, track live, mic
label and sample rate both displayed correctly, no error anywhere, and a level
meter frozen at silence.

The gain is 0, so nothing is audible and no microphone audio reaches the
speakers. It costs one node.

`recorder.js` also runs a 1.2 s watchdog after the mic opens and fails with
`AUDIO_WORKLET_SILENT` if no audio frame has arrived, because on a phone there
is no console and the alternative is a screen that looks like it is working.

## Consequences

- Clips are large: 48 kHz/16-bit/mono is **345 MB per hour**. Accepted; storage
  is roughly $2.60/month for 500 hours on R2, and speaker recruitment is the
  real cost.
- `AudioWorklet` requires a secure context, so HTTPS is mandatory even for
  testing on a real device. See [ADR-006](ADR-006-same-origin-deployment.md).
- Older browsers without `AudioWorklet` are unsupported. `recorder.js` detects
  this and says so rather than falling back to MediaRecorder — a silent
  downgrade to Opus is worse than a refusal.
- The keepalive node must survive refactoring. Rule 2 in `CLAUDE.md`.

## Enforced by

- `tests/test_audio_qc.py` — a low-sample-rate take is rejected
- `CLAUDE.md` rules 1, 2 and 3
- The mic-check screen, which surfaces overridden DSP flags at collection time
