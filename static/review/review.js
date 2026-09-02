/**
 * The review loop.
 *
 * Throughput is the whole design constraint. Listening end to end runs about
 * 1.2x realtime, so 50 hours of corpus is 60+ hours of human labour, and that
 * is the wall these projects hit. Everything here exists to shave seconds:
 * keyboard-only operation, prefetched audio, no mouse, no page transitions.
 *
 * Two things are deliberately withheld until after a verdict is committed:
 * the QC metrics and the ASR transcript. Showing "SNR 42 dB" next to the play
 * button anchors the reviewer into passing; showing the ASR text means they
 * review the transcript instead of the audio.
 */

import { minutes, percent, seconds } from '/static/shared/format.js';
import { Player } from '/static/review/player.js';
import { ReviewQueue } from '/static/review/queue.js';

const $ = (sel) => document.querySelector(sel);

const state = {
  queue: null,
  player: null,
  reasons: [],
  config: null,
  shownAt: 0,
  sessionStart: Date.now(),
  done: 0,
  rejected: 0,
  rejecting: false,
  busy: false,
  fatigueWarned: false,
};

function token() {
  const fromUrl = new URLSearchParams(location.search).get('token');
  if (fromUrl) {
    try {
      sessionStorage.setItem('review_token', fromUrl);
    } catch (_) { /* private mode */ }
    return fromUrl;
  }
  try {
    return sessionStorage.getItem('review_token') || '';
  } catch (_) {
    return '';
  }
}

function setNote(message, kind = '') {
  const el = $('#note');
  el.textContent = message;
  el.className = `note ${kind}`;
}

// --- rendering ----------------------------------------------------------

function renderReasons() {
  $('#reasons').innerHTML = state.reasons
    .map(
      (r) =>
        `<li><kbd>${r.key}</kbd><span>${r.label}</span><em>${r.reason}</em></li>`,
    )
    .join('');
}

function renderClip() {
  const clip = state.queue.current();

  if (!clip) {
    $('#prompt').textContent = state.queue.exhausted
      ? 'सबै सकियो — अहिले जाँच्न बाँकी छैन।'
      : 'लोड हुँदैछ…';
    $('#clip-meta').textContent = '';
    $('#verdict-panel').classList.add('hidden');
    return;
  }

  $('#prompt').textContent = clip.prompt_text;
  $('#clip-meta').textContent = `${seconds(clip.duration_s)} · ${clip.clip_id}`;
  $('#verdict-panel').classList.add('hidden');
  $('#reject-panel').classList.remove('open');
  state.rejecting = false;

  state.player.load(clip).then(() => state.player.play());
  state.player.prefetch(state.queue.upcoming());
  state.shownAt = Date.now();
  setNote('');
  renderProgress();
}

function renderProgress() {
  $('#done-count').textContent = state.done;
  $('#reject-rate').textContent = state.done
    ? percent(state.rejected / state.done)
    : '—';
  $('#queue-depth').textContent = state.queue.items.length;

  const elapsed = Date.now() - state.sessionStart;
  $('#session-time').textContent = minutes(elapsed);

  const limitMs = (state.config?.session_minutes || 45) * 60000;
  if (elapsed > limitMs && !state.fatigueWarned) {
    state.fatigueWarned = true;
    setNote(
      `${state.config.session_minutes} मिनेट भयो — ब्रेक लिनुहोस्। ` +
        'थकाइले गलत निर्णय बढाउँछ।',
      'warn',
    );
  }
}

/** Only after a verdict: what the meters and the model said. */
function renderVerdict(result, elapsedMs) {
  const panel = $('#verdict-panel');
  const bits = [
    `<div><span>निर्णय</span><strong>${result.verify_status}</strong></div>`,
    `<div><span>समय</span><strong>${(elapsedMs / 1000).toFixed(1)}s</strong></div>`,
  ];
  if (result.snr_db != null) {
    bits.push(`<div><span>SNR</span><strong>${result.snr_db.toFixed(0)} dB</strong></div>`);
  }
  if (result.asr_cer != null) {
    bits.push(`<div><span>ASR CER</span><strong>${result.asr_cer.toFixed(2)}</strong></div>`);
  }
  panel.innerHTML =
    `<div class="verdict-metrics">${bits.join('')}</div>` +
    (result.asr_text
      ? `<p class="asr"><span>ASR ले सुनेको:</span> ${result.asr_text}</p>`
      : '');
  panel.classList.remove('hidden');

  if (elapsedMs < (state.config?.too_fast_ms || 2000)) {
    setNote('२ सेकेन्डभन्दा छिटो — सुनेर मात्र निर्णय गर्नुहोस्।', 'warn');
  }
}

// --- actions ------------------------------------------------------------

async function verdict(action, reason = null) {
  if (state.busy) return;
  const clip = state.queue.current();
  if (!clip) return;

  state.busy = true;
  const elapsed = Date.now() - state.shownAt;

  try {
    const result = await state.queue.submit(clip.clip_id, {
      action,
      reason,
      time_spent_ms: elapsed,
    });

    if (action === 'verified' || action === 'rejected') {
      state.done++;
      if (action === 'rejected') state.rejected++;
      renderVerdict(result, elapsed);
    }

    state.player.release(clip.clip_id);
    state.queue.advance();

    // Let the reviewer glance at the revealed metrics before moving on.
    const pause = action === 'skipped' || action === 'unsure' ? 0 : 550;
    setTimeout(renderClip, pause);
  } catch (err) {
    setNote(`पठाउन सकिएन: ${err.message}`, 'error');
  } finally {
    state.busy = false;
  }
}

async function undo() {
  if (state.busy) return;
  state.busy = true;
  try {
    const res = await state.queue.undo();
    if (res.undone) {
      state.done = Math.max(0, state.done - 1);
      setNote(`फिर्ता लियो: ${res.clip_id}`, 'ok');
      renderProgress();
    } else {
      setNote('फिर्ता लिन केही छैन।', 'warn');
    }
  } catch (err) {
    setNote(`फिर्ता लिन सकिएन: ${err.message}`, 'error');
  } finally {
    state.busy = false;
  }
}

function openReject() {
  state.rejecting = true;
  $('#reject-panel').classList.add('open');
  setNote('कारण छान्नुहोस् (१–९), वा Esc ले रद्द।');
}

function closeReject() {
  state.rejecting = false;
  $('#reject-panel').classList.remove('open');
  setNote('');
}

// --- keyboard -----------------------------------------------------------

document.addEventListener('keydown', (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const key = event.key;

  if (state.rejecting) {
    if (key === 'Escape') {
      event.preventDefault();
      closeReject();
      return;
    }
    const index = parseInt(key, 10) - 1;
    if (index >= 0 && index < state.reasons.length) {
      event.preventDefault();
      const reason = state.reasons[index].reason;
      closeReject();
      verdict('rejected', reason);
    }
    return;
  }

  switch (key) {
    case ' ':
      event.preventDefault();
      state.player.toggle();
      break;
    case 'r':
    case 'R':
      event.preventDefault();
      state.player.replay();
      break;
    case 'Enter':
      event.preventDefault();
      verdict('verified');
      break;
    case 's':
    case 'S':
      event.preventDefault();
      verdict('skipped');
      break;
    case 'u':
    case 'U':
      event.preventDefault();
      verdict('unsure');
      break;
    case 'z':
    case 'Z':
      event.preventDefault();
      undo();
      break;
    default:
      // 1-9 open the reject panel pre-selected on that reason.
      if (/^[1-9]$/.test(key)) {
        const index = parseInt(key, 10) - 1;
        if (index < state.reasons.length) {
          event.preventDefault();
          verdict('rejected', state.reasons[index].reason);
        }
      }
  }
});

$('#btn-verify').addEventListener('click', () => verdict('verified'));
$('#btn-reject').addEventListener('click', openReject);
$('#btn-skip').addEventListener('click', () => verdict('skipped'));
$('#btn-undo').addEventListener('click', undo);
$('#reject-panel').addEventListener('click', (event) => {
  const button = event.target.closest('[data-reason]');
  if (!button) return;
  closeReject();
  verdict('rejected', button.dataset.reason);
});

// --- boot ---------------------------------------------------------------

async function boot() {
  const tok = token();
  if (!tok) {
    setNote(
      'टोकन चाहिन्छ। लिंकमा ?token=... थप्नुहोस्। (reviewer token required)',
      'error',
    );
    return;
  }

  state.queue = new ReviewQueue(tok);
  state.player = new Player($('#audio'));
  // Auto-advance on playback end is deliberately NOT wired: the reviewer
  // decides when to move on, so a clip is never skipped past unjudged.

  try {
    state.config = await state.queue.config();
  } catch (err) {
    setNote(`${err.message}`, 'error');
    return;
  }

  state.reasons = state.config.reasons;
  $('#reviewer').textContent = state.config.reviewer;
  renderReasons();
  $('#reject-panel').innerHTML = state.reasons
    .map(
      (r, i) =>
        `<button data-reason="${r.reason}"><kbd>${i + 1}</kbd> ${r.label}</button>`,
    )
    .join('');

  await state.queue.fill();
  renderClip();
  setInterval(renderProgress, 1000);
}

boot();
