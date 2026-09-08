/**
 * Live input-level waveform, in the spirit of Voice Memos: a scrolling row of
 * bars, newest on the right, that gives an immediate "yes, it's hearing you"
 * signal -- much more legible at a glance than a single numeric dBFS readout.
 *
 * Deliberately not audio-accurate (it's driven by the same single peak value
 * as the numeric meter, not a real per-band spectrum) -- it's a liveness cue,
 * not a measurement instrument. The measurement is still the dBFS number and
 * the server-side QC gate.
 */

const MIN_HEIGHT_PCT = 10;
const PUSH_INTERVAL_MS = 55; // ~18fps: smooth enough, cheap enough for a phone.

export class Waveform {
  constructor(container, { bars = 40 } = {}) {
    this.container = container;
    this.bars = [];
    container.innerHTML = '';
    container.classList.add('idle');
    for (let i = 0; i < bars; i++) {
      const bar = document.createElement('div');
      bar.className = 'waveform-bar';
      bar.style.height = `${MIN_HEIGHT_PCT}%`;
      container.appendChild(bar);
      this.bars.push(bar);
    }
    this._lastPush = 0;
  }

  /** Feed the latest peak amplitude (0..1, same scale as audio.js peak). */
  push(peak) {
    // A real level has arrived -- stop the idle breathing animation so it
    // doesn't fight with actual mic input.
    this.container.classList.remove('idle');

    const now = performance.now();
    if (now - this._lastPush < PUSH_INTERVAL_MS) return;
    this._lastPush = now;

    // Perceptual-ish curve: sqrt so quiet speech still shows real movement
    // instead of hugging the bottom of the bar.
    const pct = Math.max(MIN_HEIGHT_PCT, Math.min(100, Math.sqrt(peak) * 100));
    const hot = peak > 0.9; // near clipping

    // Scroll: drop the oldest bar's height, shift everyone left, newest on the right.
    for (let i = 0; i < this.bars.length - 1; i++) {
      this.bars[i].style.height = this.bars[i + 1].style.height;
      this.bars[i].classList.toggle('hot', this.bars[i + 1].classList.contains('hot'));
    }
    const last = this.bars[this.bars.length - 1];
    last.style.height = `${pct}%`;
    last.classList.toggle('hot', hot);
  }

  reset() {
    this.container.classList.add('idle');
    for (const bar of this.bars) {
      bar.style.height = `${MIN_HEIGHT_PCT}%`;
      bar.classList.remove('hot');
    }
  }
}
