/**
 * Audio playback with prefetch.
 *
 * The reviewer must never wait on the network. Clips arrive as a batch of
 * short-lived presigned URLs, and this keeps the next few decoded and ready so
 * that pressing a key plays instantly. At ~1.2x realtime listening, a 300 ms
 * stall on every clip is a tax of several minutes per hour of reviewing.
 *
 * Audio is fetched straight from object storage. It never passes through the
 * API server.
 */

const PREFETCH = 3;

export class Player {
  constructor(element) {
    this.el = element;
    this.cache = new Map(); // clip_id -> object URL
    this.onEnded = null;
    this.el.addEventListener('ended', () => {
      if (this.onEnded) this.onEnded();
    });
  }

  /** Warm the cache for the next few clips without blocking. */
  prefetch(clips) {
    for (const clip of clips.slice(0, PREFETCH)) {
      if (this.cache.has(clip.clip_id)) continue;
      // Mark immediately so a slow fetch is not started twice.
      this.cache.set(clip.clip_id, null);
      fetch(clip.audio_url)
        .then((res) => (res.ok ? res.blob() : null))
        .then((blob) => {
          if (blob) this.cache.set(clip.clip_id, URL.createObjectURL(blob));
        })
        .catch(() => this.cache.delete(clip.clip_id));
    }
  }

  async load(clip) {
    const cached = this.cache.get(clip.clip_id);
    this.el.src = cached || clip.audio_url;
    this.el.currentTime = 0;
  }

  play() {
    // Autoplay can be refused until the page has been interacted with; the
    // reviewer's first keypress counts, so this is safe to swallow.
    return this.el.play().catch(() => {});
  }

  toggle() {
    if (this.el.paused) this.play();
    else this.el.pause();
  }

  replay() {
    this.el.currentTime = 0;
    this.play();
  }

  release(clipId) {
    const url = this.cache.get(clipId);
    if (url) URL.revokeObjectURL(url);
    this.cache.delete(clipId);
  }
}
