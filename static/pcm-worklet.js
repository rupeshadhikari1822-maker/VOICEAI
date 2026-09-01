/**
 * Raw PCM capture.
 *
 * This exists instead of MediaRecorder because MediaRecorder gives you
 * WebM/Opus. Opus is a lossy speech codec: it throws away exactly the
 * high-frequency detail a vocoder needs to learn from, and no amount of
 * post-processing gets it back. Here we take the Float32 samples the audio
 * graph is already carrying and hand them to the main thread untouched.
 *
 * Blocks arrive 128 samples at a time (375 per second at 48 kHz), which is far
 * too chatty for postMessage, so we accumulate into 4096-sample buffers and
 * transfer them rather than copying.
 */

const BUFFER_SIZE = 4096;

class PCMRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.recording = false;
    this.buffer = new Float32Array(BUFFER_SIZE);
    this.offset = 0;
    // Level meter updates are throttled independently of capture, so the
    // meter keeps moving during the mic check while nothing is recorded.
    this.meterAcc = 0;
    this.meterPeak = 0;
    this.meterCount = 0;

    this.port.onmessage = (event) => {
      const type = event.data && event.data.type;
      if (type === 'start') {
        this.recording = true;
        this.offset = 0;
      } else if (type === 'stop') {
        this.flush();
        this.recording = false;
      }
    };
  }

  flush() {
    if (this.offset === 0) return;
    const chunk = this.buffer.slice(0, this.offset);
    this.port.postMessage({ type: 'chunk', data: chunk }, [chunk.buffer]);
    this.offset = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel) return true;

    for (let i = 0; i < channel.length; i++) {
      const sample = channel[i];
      const abs = sample < 0 ? -sample : sample;
      if (abs > this.meterPeak) this.meterPeak = abs;
      this.meterAcc += sample * sample;
      this.meterCount++;

      if (this.recording) {
        this.buffer[this.offset++] = sample;
        if (this.offset === BUFFER_SIZE) this.flush();
      }
    }

    // ~20 ms of meter resolution, independent of block size.
    if (this.meterCount >= sampleRate / 50) {
      this.port.postMessage({
        type: 'level',
        peak: this.meterPeak,
        rms: Math.sqrt(this.meterAcc / this.meterCount),
      });
      this.meterAcc = 0;
      this.meterPeak = 0;
      this.meterCount = 0;
    }

    return true;
  }
}

registerProcessor('pcm-recorder', PCMRecorder);
