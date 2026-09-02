/**
 * Capture, WAV encoding and client-side QC.
 *
 * The metrics here mirror app/audio_qc.py so the contributor gets an answer in
 * milliseconds instead of after a round trip. They are a UX convenience only --
 * the server re-measures the stored bytes and its verdict is the one that
 * counts. If the two ever disagree, that is a bug worth chasing, which is why
 * the client numbers are posted along with the clip.
 */

export const TARGET_SAMPLE_RATE = 48000;

/** getUserMedia constraints with every browser DSP stage switched off.
 *
 * Chrome enables echo cancellation, noise suppression and auto gain by default.
 * Auto gain is the worst of the three for this use case: it rides the level
 * between sentences, so a voice recorded across one session arrives at
 * inconsistent loudness and a TTS model trained on it sounds unstable.
 */
export const MIC_CONSTRAINTS = {
  audio: {
    echoCancellation: false,
    noiseSuppression: false,
    autoGainControl: false,
    channelCount: 1,
    sampleRate: TARGET_SAMPLE_RATE,
  },
  video: false,
};

const EPS = 1e-12;

export function dbfs(value) {
  return 20 * Math.log10(Math.max(value, EPS));
}

export class Recorder {
  constructor() {
    this.stream = null;
    this.context = null;
    this.node = null;
    this.source = null;
    this.chunks = [];
    this.recording = false;
    this.onLevel = null;
    this.sampleRate = TARGET_SAMPLE_RATE;
    this.keepalive = null;
    // Set on the first 'level' message. If this stays false, process() is not
    // running and no amount of recording will produce audio.
    this.workletAlive = false;
  }

  get ready() {
    return this.node !== null;
  }

  async init() {
    if (this.node) return;

    this.stream = await navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS);

    // Ask for 48 kHz explicitly. If the device refuses we surface the real rate
    // rather than silently resampling -- the server rejects below 32 kHz.
    this.context = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: TARGET_SAMPLE_RATE,
    });
    this.sampleRate = this.context.sampleRate;

    await this.context.audioWorklet.addModule('/static/recorder/pcm-worklet.js');

    this.source = this.context.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.context, 'pcm-recorder', {
      numberOfInputs: 1,
      // One output, connected below through a MUTED gain node to destination.
      //
      // DO NOT "clean this up". A capture-only worklet with no path to
      // destination is the architecturally honest graph -- we are recording,
      // not playing -- and it works on Chrome. But WebKit has historically
      // treated a graph with no route to destination as inactive and stopped
      // calling process(), which produces a uniquely confusing failure: mic
      // permission granted, track live, label and sample rate correct, no
      // error anywhere, and a level meter frozen at silence.
      //
      // The gain is 0, so nothing is ever audible and no mic audio reaches the
      // speakers. This costs one node and removes a whole class of
      // device-specific silence.
      numberOfOutputs: 1,
      outputChannelCount: [1],
      channelCount: 1,
    });

    // Muted sink. Keeps the graph alive without producing sound.
    this.keepalive = this.context.createGain();
    this.keepalive.gain.value = 0;

    this.node.port.onmessage = (event) => {
      const msg = event.data;
      if (msg.type === 'chunk') {
        this.chunks.push(msg.data);
      } else if (msg.type === 'level') {
        this.workletAlive = true;
        if (this.onLevel) this.onLevel(msg);
      }
    };

    this.source.connect(this.node);
    this.node.connect(this.keepalive);
    this.keepalive.connect(this.context.destination);
  }

  /** Actual hardware track settings, for the mic check and device_hint. */
  trackInfo() {
    if (!this.stream) return {};
    const track = this.stream.getAudioTracks()[0];
    if (!track) return {};
    const settings = track.getSettings ? track.getSettings() : {};
    return { label: track.label || '', ...settings };
  }

  async resume() {
    if (this.context && this.context.state === 'suspended') {
      await this.context.resume();
    }
  }

  start() {
    this.chunks = [];
    this.recording = true;
    this.node.port.postMessage({ type: 'start' });
  }

  /** Stops capture and returns the concatenated Float32 samples. */
  stop() {
    this.recording = false;
    this.node.port.postMessage({ type: 'stop' });
    return new Promise((resolve) => {
      // One turn of the event loop lets the worklet's final flush land.
      setTimeout(() => resolve(concat(this.chunks)), 60);
    });
  }

  close() {
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    if (this.node) this.node.disconnect();
    if (this.keepalive) this.keepalive.disconnect();
    if (this.context) this.context.close();
    this.stream = null;
    this.context = null;
    this.node = null;
    this.keepalive = null;
  }
}

function concat(chunks) {
  let total = 0;
  for (const c of chunks) total += c.length;
  const out = new Float32Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}

/** Float32 [-1,1] -> 16-bit PCM RIFF/WAV. Mono, uncompressed, no metadata. */
export function encodeWav(samples, sampleRate) {
  const bytesPerSample = 2;
  const buffer = new ArrayBuffer(44 + samples.length * bytesPerSample);
  const view = new DataView(buffer);

  const writeString = (offset, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };

  const dataBytes = samples.length * bytesPerSample;
  writeString(0, 'RIFF');
  view.setUint32(4, 36 + dataBytes, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // format 1 = uncompressed PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true); // byte rate
  view.setUint16(32, bytesPerSample, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeString(36, 'data');
  view.setUint32(40, dataBytes, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    // Clamp before scaling so an out-of-range sample wraps to full scale
    // instead of overflowing into the opposite polarity.
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }

  return new Blob([view], { type: 'audio/wav' });
}

/** Same measurements as app/audio_qc.py, for instant feedback. */
export function analyze(samples, sampleRate) {
  const n = samples.length;
  if (n === 0) {
    return { empty: true, durationS: 0, snrDb: 0, peakDbfs: -120, rmsDbfs: -120,
             noiseFloorDbfs: -120, clippingRatio: 0, leadSilenceMs: 0, trailSilenceMs: 0 };
  }

  let peak = 0;
  let sumSq = 0;
  let clipped = 0;
  for (let i = 0; i < n; i++) {
    const v = samples[i];
    const a = v < 0 ? -v : v;
    if (a > peak) peak = a;
    sumSq += v * v;
    if (a >= 32767 / 32768) clipped++;
  }

  const frame = Math.max(1, Math.round(sampleRate * 0.02));
  const hop = Math.max(1, Math.round(sampleRate * 0.01));
  const frameDb = [];
  for (let start = 0; start + frame <= n; start += hop) {
    let acc = 0;
    for (let i = start; i < start + frame; i++) acc += samples[i] * samples[i];
    frameDb.push(dbfs(Math.sqrt(acc / frame)));
  }
  if (frameDb.length === 0) frameDb.push(dbfs(Math.sqrt(sumSq / n)));

  const sorted = [...frameDb].sort((a, b) => a - b);
  const noiseFloor = sorted[Math.floor(sorted.length * 0.1)];

  const threshold = noiseFloor + 10;
  let first = -1;
  let last = -1;
  for (let i = 0; i < frameDb.length; i++) {
    if (frameDb[i] > threshold) {
      if (first < 0) first = i;
      last = i;
    }
  }

  const base = {
    durationS: n / sampleRate,
    peakDbfs: dbfs(peak),
    rmsDbfs: dbfs(Math.sqrt(sumSq / n)),
    noiseFloorDbfs: noiseFloor,
    clippingRatio: clipped / n,
    sampleRate,
  };

  if (first < 0) {
    return { ...base, noSpeech: true, snrDb: 0,
             leadSilenceMs: base.durationS * 1000, trailSilenceMs: 0 };
  }

  // RMS across the whole speech span, not only the frames above threshold --
  // measuring only the loud frames would flatter a noisy take.
  const spanStart = first * hop;
  const spanEnd = Math.min(n, last * hop + hop);
  let spanSq = 0;
  for (let i = spanStart; i < spanEnd; i++) spanSq += samples[i] * samples[i];
  const speechDb = dbfs(Math.sqrt(spanSq / Math.max(1, spanEnd - spanStart)));

  return {
    ...base,
    snrDb: speechDb - noiseFloor,
    leadSilenceMs: (spanStart / sampleRate) * 1000,
    trailSilenceMs: ((n - spanEnd) / sampleRate) * 1000,
  };
}

/** Nepali-first verdict. Says what to physically change, not what failed. */
export function gate(m, qc) {
  const reasons = [];
  if (m.empty || m.noSpeech) {
    reasons.push('कुनै आवाज पत्ता लागेन — माइक नजिक ल्याएर फेरि बोल्नुहोस्।');
    return { passed: false, reasons };
  }
  if (m.durationS < qc.min_duration_s) {
    reasons.push(`रेकर्डिङ धेरै छोटो छ (${m.durationS.toFixed(1)}s) — पूरा वाक्य पढ्नुहोस्।`);
  }
  if (m.durationS > qc.max_duration_s) {
    reasons.push(`रेकर्डिङ धेरै लामो छ (${m.durationS.toFixed(1)}s) — वाक्य सकिनेबित्तिकै रोक्नुहोस्।`);
  }
  if (m.clippingRatio > qc.max_clipping_ratio) {
    reasons.push('आवाज बिग्रिएको छ — माइक अलि टाढा सार्नुहोस् वा बिस्तारै बोल्नुहोस्।');
  }
  if (m.peakDbfs > qc.max_peak_dbfs) {
    reasons.push('आवाज धेरै ठूलो छ — माइक मुखबाट १५–२० सेमी टाढा राख्नुहोस्।');
  } else if (m.peakDbfs < qc.min_peak_dbfs) {
    reasons.push('आवाज धेरै सानो छ — माइक नजिक ल्याउनुहोस् र अलि ठूलो स्वरमा बोल्नुहोस्।');
  }
  if (m.noiseFloorDbfs > qc.max_noise_floor_dbfs) {
    reasons.push('पछाडिको आवाज धेरै छ — पंखा/झ्याल बन्द गर्नुहोस्।');
  }
  if (m.snrDb < qc.min_snr_db) {
    reasons.push('पछाडिको आवाज धेरै छ — पंखा/झ्याल बन्द गरेर शान्त कोठामा फेरि रेकर्ड गर्नुहोस्।');
  }
  return { passed: reasons.length === 0, reasons };
}
