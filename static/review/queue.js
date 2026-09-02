/**
 * Client-side queue: fetching batches, submitting verdicts, undo.
 *
 * Kept apart from the UI so the ordering and refill logic can be reasoned about
 * without reading DOM code. The server decides *which* clips; this only decides
 * when to ask for more.
 */

const REFILL_AT = 3; // fetch the next batch while this many remain

export class ReviewQueue {
  constructor(token) {
    this.token = token;
    this.items = [];
    this.exhausted = false;
    this.fetching = null;
  }

  get headers() {
    return {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${this.token}`,
    };
  }

  async api(path, options = {}) {
    const res = await fetch(path, { headers: this.headers, ...options });
    if (res.status === 401) throw new Error('unauthorised — check your token');
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        detail = (await res.json()).detail || detail;
      } catch (_) { /* non-JSON error body */ }
      throw new Error(detail);
    }
    return res.json();
  }

  async fill(count = 10) {
    if (this.fetching) return this.fetching;
    this.fetching = this.api(`/api/review/next?count=${count}`)
      .then((batch) => {
        const seen = new Set(this.items.map((c) => c.clip_id));
        const fresh = batch.filter((c) => !seen.has(c.clip_id));
        this.items.push(...fresh);
        if (fresh.length === 0) this.exhausted = true;
        return fresh;
      })
      .finally(() => {
        this.fetching = null;
      });
    return this.fetching;
  }

  current() {
    return this.items[0] || null;
  }

  upcoming() {
    return this.items.slice(1);
  }

  /** Drop the current clip and top up if we are running low. */
  advance() {
    const done = this.items.shift();
    if (this.items.length <= REFILL_AT && !this.exhausted) {
      this.fill().catch(() => {});
    }
    return done;
  }

  /** Put a clip back at the front (used when a submit fails). */
  restore(clip) {
    if (clip) this.items.unshift(clip);
  }

  submit(clipId, body) {
    return this.api(`/api/review/${clipId}/verdict`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  undo() {
    return this.api('/api/review/undo', { method: 'POST' });
  }

  stats() {
    return this.api('/api/review/stats');
  }

  config() {
    return this.api('/api/review/config');
  }
}
