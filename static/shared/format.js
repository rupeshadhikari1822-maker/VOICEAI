/** Formatting helpers shared by the recorder and the review UI. */

const EPS = 1e-12;

export function dbfs(value) {
  return 20 * Math.log10(Math.max(value, EPS));
}

export function seconds(value) {
  if (value == null || !isFinite(value)) return '—';
  return `${value.toFixed(1)}s`;
}

export function minutes(ms) {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function percent(value) {
  if (value == null || !isFinite(value)) return '—';
  return `${Math.round(value * 100)}%`;
}
