/**
 * Flow controller: consent -> profile -> mic check -> record.
 *
 * Dependency-free ES modules on purpose. The whole point of this page is that a
 * contributor on a mid-range Android phone over a slow connection can open a
 * link and start recording; a framework bundle works against that.
 */

import { Recorder, encodeWav, analyze, gate, dbfs } from '/static/recorder/audio.js';
import { runPreflight } from '/static/recorder/preflight.js';
import { initAuth, getAccessToken, onSignedIn } from '/static/recorder/auth.js';
import { t, applyStaticTranslations, initLangSelector, onLangChange } from '/static/recorder/i18n.js';
import { Waveform } from '/static/recorder/waveform.js';

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  config: null,
  speakerId: null,
  sessionId: null,
  prompts: [],
  index: 0,
  recorder: new Recorder(),
  samples: null,
  metrics: null,
  lastBlob: null,
  stats: { passed: 0, failed: 0 },
};

// --- helpers ------------------------------------------------------------

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (_) { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

// --- resume across a reload -----------------------------------------------
//
// A refresh mid-session used to send the contributor all the way back to
// consent -- re-creating a speaker, a new session, and losing their place in
// the prompt list. The mic itself can never survive a reload (getUserMedia
// always needs a fresh grant), so a reload still lands on mic-check, not
// straight back into recording -- but everything before that (consent,
// speaker, session, storage preflight) shouldn't have to happen twice.

const SESSION_STORAGE_KEY = 'voiceai.session';

function persistSession() {
  try {
    localStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify({ speakerId: state.speakerId, sessionId: state.sessionId }),
    );
  } catch (_) {
    /* private browsing / storage disabled: recording still works, just won't resume */
  }
}

function loadPersistedSession() {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    return data.speakerId && data.sessionId ? data : null;
  } catch (_) {
    return null;
  }
}

function clearPersistedSession() {
  try {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch (_) { /* nothing to clear */ }
}

/** Resumes a persisted speaker+session: re-checks storage, restores the
 * sent/failed counters from the server, and skips straight to mic check.
 * Returns false (and clears the stale entry) if anything about it no longer
 * works, so the contributor falls through to a normal fresh start. */
async function resumeSession({ speakerId, sessionId }) {
  state.speakerId = speakerId;
  state.sessionId = sessionId;

  try {
    const progress = await api(`/api/sessions/${sessionId}/progress`);
    state.stats.passed = progress.passed;
    state.stats.failed = progress.failed;

    const preflight = await runPreflight();
    if (!preflight.ok) {
      blockOnStorage(preflight);
      return true; // handled: the blocked screen, not consent, is now showing
    }

    $('#speaker-id').textContent = state.speakerId;
    showStep('miccheck');
    return true;
  } catch (err) {
    console.warn('[resume] stale session, starting fresh instead', err);
    clearPersistedSession();
    return false;
  }
}

function showStep(name) {
  $$('.step').forEach((el) => el.classList.toggle('active', el.dataset.step === name));
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function setStatus(el, message, kind = '') {
  el.textContent = message;
  el.className = `status ${kind}`;
}

/** Same as setStatus, plus a pulsing dot for "something is actively capturing". */
function setStatusWithDot(el, message, dotOn, kind = '') {
  el.innerHTML = (dotOn ? '<span class="rec-dot"></span>' : '') + escapeHtml(message);
  el.className = `status ${kind}`;
}

// --- i18n -----------------------------------------------------------------

initLangSelector();
applyStaticTranslations();
onLangChange(() => {
  applyStaticTranslations();
  // Static translation alone would clobber this button's state-dependent
  // label (Record vs Stop), so re-derive it from current recording state.
  recordButton.textContent = isRecording ? t('record.stop') : t('record.start');
});

// --- accounts: retroactively link an in-progress speaker on sign-in --------
//
// Consent creates an anonymous speaker before anyone has a chance to sign in,
// so "sign in partway through to make sure this is saved" -- the whole point
// of accounts here -- does nothing on its own. This is what actually makes
// it stick. Registered before initAuth() runs, so it's already listening for
// the very first sign-in notification, including one from a restored session.
onSignedIn(async () => {
  if (!state.speakerId) return; // nothing recorded yet in this browser tab
  try {
    await api(`/api/speakers/${state.speakerId}/link-account`, { method: 'POST' });
  } catch (err) {
    console.warn('[auth] could not link this session to your account', err);
  }
});

// --- boot ---------------------------------------------------------------

async function boot() {
  try {
    state.config = await api('/api/config');
  } catch (err) {
    setStatus($('#consent-status'), t('error.configLoadFailed', { error: err.message }), 'error');
    return;
  }

  // Resume BEFORE initAuth: the onSignedIn hook above only links a speaker
  // that's already set in state, and initAuth's very first check ("is this
  // browser already signed in?") fires immediately, before anything async
  // here would otherwise have set it. Resuming first means a page reload
  // while already signed in still links correctly, not just a fresh sign-in.
  const persisted = loadPersistedSession();
  let resumed = false;
  if (persisted) {
    resumed = await resumeSession(persisted);
  }

  try {
    await initAuth(state.config);
  } catch (err) {
    // Accounts are a convenience layer on top of recording, never a blocker.
    console.warn('[auth] failed to initialize', err);
  }

  if (resumed) return;

  // Signing in now happens on its own page (/login) before the contributor
  // ever reaches consent, not as a modal gate partway through it -- so a
  // fresh (non-resumed) visit with no session shouldn't render consent at
  // all, it should bounce straight to /login and come back once signed in.
  if (!getAccessToken()) {
    window.location.href = `/login?next=${encodeURIComponent('/studio')}`;
    return;
  }

  $('#consent-text').innerHTML = renderConsentMarkdown(state.config.consent.text);
  $('#consent-version').textContent = state.config.consent.version;
  $('#spec-sr').textContent = `${state.config.audio.sample_rate / 1000} kHz`;
  $('#spec-snr').textContent = `${state.config.qc.min_snr_db} dB`;

  if (!navigator.mediaDevices || !window.AudioWorkletNode) {
    setStatus($('#consent-status'), t('error.unsupportedBrowser'), 'error');
  }
  if (!window.isSecureContext) {
    setStatus($('#consent-status'), t('error.httpsRequired'), 'error');
  }
}

// --- step 1: consent -> sign in -> register (consent-only) -> preflight -> mic check ---
//
// The profile form (name, demographics) is deliberately NOT here: it comes
// after recording, as a "save your contribution" step. But a Speaker row has
// to exist before recording can start at all -- clips FK to it and object
// keys are namespaced by speaker_id -- so consenting creates a bare speaker
// (consent only, every profile field left null) immediately.
//
// Registering that speaker requires a signed-in account (enforced again by
// the server, which is the real gate): the commercial rights assignment in
// the consent above has to be traceable to a real account from the moment
// it's made, and recording must not be reachable at all without one.

$('#consent-agree').addEventListener('change', (e) => {
  $('#consent-continue').disabled = !e.target.checked;
});

$('#consent-continue').addEventListener('click', async () => {
  const consentAccepted = $('#consent-agree').checked;
  // boot() already redirected to /login if there was never a session; this
  // only catches the rare case of the token expiring in the gap between
  // page load and clicking Continue.
  if (!getAccessToken()) {
    window.location.href = `/login?next=${encodeURIComponent('/studio')}`;
    return;
  }
  await registerAndProceed(consentAccepted);
});

async function registerAndProceed(consentAccepted) {
  const status = $('#consent-status');
  const button = $('#consent-continue');
  button.disabled = true;
  setStatus(status, t('status.settingUp'));

  try {
    const speaker = await api('/api/speakers', {
      method: 'POST',
      body: JSON.stringify({
        consent: {
          version: state.config.consent.version,
          accepted: consentAccepted,
          commercial_use: true,
        },
      }),
    });
    state.speakerId = speaker.speaker_id;

    // Only one recording language exists today; this is not a choice the
    // contributor makes, so it is not part of any form.
    const session = await api('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({
        speaker_id: state.speakerId,
        lang: 'ne',
        device_hint: navigator.userAgent.slice(0, 300),
      }),
    });
    state.sessionId = session.session_id;
    persistSession();

    // Prove uploads work BEFORE anyone reads a sentence aloud. A CORS
    // misconfiguration is invisible to every server-side check, and without
    // this it surfaces only after twenty minutes of recording.
    setStatus(status, t('status.uploadChecking'));
    const preflight = await runPreflight();
    if (!preflight.ok) {
      blockOnStorage(preflight);
      return;
    }
    if (preflight.sameOrigin) {
      // Local backend: the PUT never crossed an origin, so it proved nothing
      // about a bucket. Do not let a green check imply otherwise.
      console.warn(
        '[preflight] local storage backend: CORS was not exercised. ' +
          'This check only means something against S3/R2.',
      );
    }

    setStatus(status, '');
    $('#speaker-id').textContent = state.speakerId;
    showStep('miccheck');
  } catch (err) {
    setStatus(status, t('error.sendFailed', { error: err.message }), 'error');
    button.disabled = false;
  }
}

// --- final step: save profile (after recording) ----------------------------

$('#save-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = $('#save-status');
  const button = $('#save-submit');
  button.disabled = true;
  setStatus(status, t('status.sending'));

  const form = new FormData(event.target);
  const value = (k) => {
    const v = (form.get(k) || '').toString().trim();
    return v === '' ? null : v;
  };

  const payload = {
    name: value('name'),
    email: value('email'),
    phone: value('phone'),
    age_band: value('age_band'),
    gender: value('gender'),
    province: value('province'),
    district: value('district'),
    municipality: value('municipality'),
    ward: value('ward'),
    mother_tongue: value('mother_tongue'),
    language_variety: value('language_variety'),
    education: value('education'),
    // "prefer not to say" is the default; it posts as null and stays null.
    caste_ethnicity: value('caste_ethnicity'),
  };

  try {
    await api(`/api/speakers/${state.speakerId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    clearPersistedSession(); // this contribution is complete; a reload should start a new one
    $('#done-count').textContent = state.stats.passed;
    $('#done-speaker').textContent = state.speakerId;
    showStep('done');
  } catch (err) {
    setStatus(status, t('error.sendFailed', { error: err.message }), 'error');
    button.disabled = false;
  }
});

/** Stop the session. The contributor cannot fix CORS or credentials. */
function blockOnStorage(preflight) {
  showStep('blocked');
  $('#blocked-message').textContent = preflight.message;
  $('#blocked-code').textContent = preflight.code;
  $('#blocked-hint').textContent = `${preflight.hint} (${preflight.detail})`;
  // Network problems are the one case worth retrying from the device.
  $('#blocked-retry').hidden = preflight.code !== 'STORAGE_NETWORK';
  console.error('[preflight]', preflight.code, preflight.detail);
}

$('#blocked-retry').addEventListener('click', async () => {
  const again = await runPreflight();
  if (again.ok) {
    $('#speaker-id').textContent = state.speakerId;
    showStep('miccheck');
  } else {
    blockOnStorage(again);
  }
});

// --- step 2: mic check ---------------------------------------------------
//
// One button. Click it and everything else happens automatically: open the
// mic, check the device, run an 8-second room-noise test, then go straight
// into recording. Three separate buttons here used to make the contributor
// figure out the sequence themselves; the sequence is fixed, so the UI
// shouldn't pretend otherwise.

const SILENCE_TEST_MS = 8000;

const COPY_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
const CHECK_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';

$('#copy-speaker-id').addEventListener('click', async () => {
  const button = $('#copy-speaker-id');
  try {
    await navigator.clipboard.writeText(state.speakerId || '');
  } catch (_) {
    /* clipboard API unavailable; the ID is still visible to copy by hand */
  }
  button.innerHTML = CHECK_ICON;
  setTimeout(() => { button.innerHTML = COPY_ICON; }, 1200);
});

// Both the mic-check step and the recording step show the same live waveform.
const micWaveform = new Waveform($('#mic-waveform'));
const recordWaveform = new Waveform($('#record-waveform'));
const meterLabel = $('#meter-label');
const techLiveLevel = $('#tech-live-level');
const techLiveSize = $('#tech-live-size');

function onLevel({ peak }) {
  micWaveform.push(peak);
  recordWaveform.push(peak);
  meterLabel.textContent = `${dbfs(peak).toFixed(0)} dBFS`;
  techLiveLevel.textContent = `${dbfs(peak).toFixed(0)} dBFS`;
}

/** Bytes -> human-readable, for the technical box's live/final size estimate. */
function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

/** Opens the mic and runs the device checks. Returns false on a hard failure. */
async function openMicAndCheckDevice() {
  const status = $('#mic-status');
  setStatus(status, t('status.openingMic'));
  state.recorder.onLevel = onLevel;
  await state.recorder.init();
  await state.recorder.resume();

  const info = state.recorder.trackInfo();
  const rate = state.recorder.sampleRate;
  $('#mic-name').textContent = info.label || t('mic.unknownLabel');
  $('#mic-rate').textContent = `${rate} Hz`;
  $('#tech-rate').textContent = `${rate / 1000} kHz`;

  const problems = [];
  if (rate < 32000) {
    problems.push(t('mic.problemLowRate', { rate }));
  }
  if (/bluetooth|hands-?free|airpod|buds/i.test(info.label || '')) {
    problems.push(t('mic.problemBluetooth'));
  }
  // Chrome reports what it actually applied; if DSP is on, the constraints
  // were overridden and the corpus would get auto-gained audio.
  for (const [key, labelKey] of [
    ['echoCancellation', 'mic.dspEchoCancellation'],
    ['noiseSuppression', 'mic.dspNoiseSuppression'],
    ['autoGainControl', 'mic.dspAutoGainControl'],
  ]) {
    if (info[key] === true) problems.push(t('mic.problemDspNotDisabled', { label: t(labelKey) }));
  }

  // Watchdog for a failure with no error attached to it.
  //
  // If the audio graph is not being scheduled, process() never runs: the mic
  // permission is granted, the track is live, the label and sample rate
  // display correctly, and the waveform sits frozen flat. On a phone there IS
  // no console, so without this the contributor and the operator both see
  // "it just doesn't work".
  //
  // The worklet posts a level message roughly every 20 ms, so a second of
  // nothing is decisive rather than a slow start.
  await new Promise((r) => setTimeout(r, 1200));
  if (!state.recorder.workletAlive) {
    $('#mic-problems').innerHTML = '';
    setStatus(status, t('error.workletSilent'), 'error');
    console.error(
      '[mic] AUDIO_WORKLET_SILENT: process() produced no frames in 1.2s. ' +
        'The AudioWorklet is not being scheduled — the graph is likely ' +
        'considered inactive by this browser.',
      { sampleRate: rate, label: info.label, state: state.recorder.context.state },
    );
    return false;
  }

  $('#mic-problems').innerHTML = problems.map((p) => `<li>${p}</li>`).join('');
  if (problems.length) setStatus(status, t('mic.seeWarnings'), 'warn');
  return true;
}

/** Room-tone test: record silence and measure the floor, with a visible
 * countdown -- this is the single most useful check, because a noisy room
 * fails every clip that follows. Returns whether the room passed. */
async function runSilenceTest() {
  const status = $('#mic-status');
  const progress = $('#mic-test-progress');
  const progressFill = $('#mic-test-progress-fill');

  progress.classList.remove('hidden');
  progressFill.style.transition = 'none';
  progressFill.style.width = '0%';
  void progressFill.offsetWidth; // force reflow, or the transition below won't animate
  progressFill.style.transition = `width ${SILENCE_TEST_MS}ms linear`;
  progressFill.style.width = '100%';

  let secondsLeft = Math.round(SILENCE_TEST_MS / 1000);
  setStatusWithDot(status, t('mic.testingRoom', { seconds: secondsLeft }), true);
  const tickHandle = setInterval(() => {
    secondsLeft -= 1;
    if (secondsLeft > 0) setStatusWithDot(status, t('mic.testingRoom', { seconds: secondsLeft }), true);
  }, 1000);

  state.recorder.start();
  await new Promise((r) => setTimeout(r, SILENCE_TEST_MS));
  clearInterval(tickHandle);
  const samples = await state.recorder.stop();
  const m = analyze(samples, state.recorder.sampleRate);
  const limit = state.config.qc.max_noise_floor_dbfs;

  $('#room-floor').textContent = `${m.noiseFloorDbfs.toFixed(0)} dBFS`;
  progress.classList.add('hidden');

  if (m.noiseFloorDbfs > limit) {
    setStatus(status, t('status.roomTooLoud', { level: m.noiseFloorDbfs.toFixed(0), limit }), 'error');
    return false;
  }

  setStatusWithDot(status, t('mic.roomGoodStarting'), false, 'ok');
  return true;
}

$('#mic-begin').addEventListener('click', async () => {
  const button = $('#mic-begin');
  const status = $('#mic-status');
  button.disabled = true;
  micWaveform.reset();

  try {
    // Only open the mic once; a retry after a noisy room re-runs just the test.
    if (!state.recorder.ready) {
      const ok = await openMicAndCheckDevice();
      if (!ok) {
        button.disabled = false;
        return;
      }
    }

    // Keep retrying automatically until the room passes -- the contributor
    // can turn off a fan or close a door between attempts without having to
    // find and click a button again.
    let passed = false;
    while (!passed) {
      passed = await runSilenceTest();
      if (!passed) {
        await new Promise((r) => setTimeout(r, 1500)); // let them read why, then retry
      }
    }

    await new Promise((r) => setTimeout(r, 700)); // let the "good ✓" register before moving on
    // Re-enabled here, not just on failure: a discarded session comes back to
    // this same screen to redo the check, and the button must be clickable
    // again when it does.
    button.disabled = false;
    showStep('method');
  } catch (err) {
    setStatus(status, t('error.micOpenFailed', { error: err.message }), 'error');
    button.disabled = false;
  }
});

// --- step 2b: choose recording method (after the mic/silence check passes) --
//
// Guided recording is the existing sentence-by-sentence flow. Free recording
// (uploading your own audio) is not built yet, so its card is disabled --
// no click handler for it, nothing to wire up.

$('#method-guided').addEventListener('click', async () => {
  const button = $('#method-guided');
  const status = $('#method-status');
  button.disabled = true;
  setStatus(status, t('status.settingUp'));
  try {
    await loadPrompts();
    setStatus(status, '');
    // Re-enabled here too: a later discard comes back through this same
    // screen, and the button must be clickable again next time.
    button.disabled = false;
    showStep('record');
    renderPrompt();
  } catch (err) {
    setStatus(status, t('error.sendFailed', { error: err.message }), 'error');
    button.disabled = false;
  }
});

// --- step 4: recording --------------------------------------------------

async function loadPrompts() {
  state.prompts = await api(`/api/prompts?session_id=${state.sessionId}&limit=50`);
  state.index = 0;
}

function renderPrompt() {
  const prompt = state.prompts[state.index];
  if (!prompt) {
    // Recording is complete; the profile form (optional) comes now, not before.
    showStep('save');
    return;
  }
  $('#prompt-text').textContent = prompt.text;
  $('#prompt-counter').textContent = `${state.index + 1} / ${state.prompts.length}`;
  $('#pass-count').textContent = state.stats.passed;
  setStatus($('#record-status'), '');
  $('#metrics').innerHTML = '';
  $('#playback').classList.add('hidden');
  $('#retake').disabled = true;
  $('#accept').disabled = true;
  techLiveLevel.textContent = '';
  techLiveSize.textContent = '';
  state.samples = null;
}

// Leaving mid-set is a normal, expected thing to do -- every sentence sent so
// far is already durably saved (uploaded the moment it passed), so this is
// just an honest, reassuring exit rather than an implicit "I guess closing
// the tab is safe?". Resuming (elsewhere in this file) already picks the
// remaining prompts back up on this same device.
$('#save-later').addEventListener('click', () => {
  $('#paused-count').textContent = state.stats.passed;
  $('#paused-total').textContent = state.prompts.length;
  $('#paused-speaker').textContent = state.speakerId;
  showStep('paused');
});

$('#paused-continue').addEventListener('click', () => {
  showStep('record');
  renderPrompt();
});

// Cancels the whole session, not just the clips in it: deletes every clip
// already sent (server-side, object then tombstone -- see
// /api/sessions/{id}/discard, which also closes the session out), then opens
// a fresh session for the same speaker and sends the contributor back to the
// mic-check screen to start it, exactly like a brand new visit would. A
// confirm() guards it: the audio is actually gone, not just hidden, so a
// misclick shouldn't be able to do this silently.
$('#discard-session').addEventListener('click', async () => {
  if (!window.confirm(t('record.discardConfirm'))) return;

  const button = $('#discard-session');
  const status = $('#record-status');
  button.disabled = true;
  setStatus(status, t('status.discarding'));

  try {
    await api(`/api/sessions/${state.sessionId}/discard`, { method: 'POST' });

    const session = await api('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({
        speaker_id: state.speakerId,
        lang: 'ne',
        device_hint: navigator.userAgent.slice(0, 300),
      }),
    });
    state.sessionId = session.session_id;
    state.stats.passed = 0;
    state.stats.failed = 0;
    persistSession();

    showStep('miccheck');
  } catch (err) {
    setStatus(status, t('error.sendFailed', { error: err.message }), 'error');
  } finally {
    button.disabled = false;
  }
});

const recordButton = $('#record-toggle');
let isRecording = false;
let startedAt = 0;
let timerHandle = null;

recordButton.addEventListener('click', async () => {
  if (!isRecording) {
    await state.recorder.resume();
    state.recorder.start();
    isRecording = true;
    startedAt = Date.now();
    recordButton.textContent = t('record.stop');
    recordButton.classList.add('recording');
    // Don't leave mid-take, and don't let a discard race an in-flight upload.
    $('#save-later').disabled = true;
    $('#discard-session').disabled = true;
    setStatusWithDot($('#record-status'), t('status.recording'), true);
    timerHandle = setInterval(() => {
      const elapsedS = (Date.now() - startedAt) / 1000;
      const timerEl = $('#timer');
      timerEl.textContent = `${elapsedS.toFixed(1)}s`;
      // A sentence should take a few seconds; nothing told a contributor who
      // left it running that they'd gone way past that, so it could run
      // unnoticed for a minute or more with no visible sign anything was wrong.
      timerEl.classList.toggle('over-limit', elapsedS > state.config.qc.max_duration_s);
      // 16-bit mono PCM: 2 bytes/sample. Same math as encodeWav's data chunk.
      techLiveSize.textContent = formatBytes(Math.round(elapsedS * state.recorder.sampleRate * 2));
    }, 100);
    return;
  }

  isRecording = false;
  clearInterval(timerHandle);
  $('#timer').classList.remove('over-limit');
  recordButton.textContent = t('record.start');
  recordButton.classList.remove('recording');
  $('#save-later').disabled = false;
  $('#discard-session').disabled = false;

  const samples = await state.recorder.stop();
  const sampleRate = state.recorder.sampleRate;
  const metrics = analyze(samples, sampleRate);
  const verdict = gate(metrics, state.config.qc);

  state.samples = samples;
  state.metrics = metrics;
  state.lastBlob = encodeWav(samples, sampleRate);

  $('#playback').classList.remove('hidden');
  $('#playback-audio').src = URL.createObjectURL(state.lastBlob);
  $('#metrics').innerHTML = renderMetrics(metrics);
  $('#retake').disabled = false;
  // Exact size now that the WAV is encoded, replacing the running estimate.
  techLiveSize.textContent = formatBytes(state.lastBlob.size);

  if (verdict.passed) {
    setStatus($('#record-status'), t('status.goodListenSend'), 'ok');
    $('#accept').disabled = false;
  } else {
    setStatus($('#record-status'), renderReasons(verdict.reasons), 'error');
    // Deliberately still allowed: the server decides. A client false-negative
    // should not be able to block a usable take.
    $('#accept').disabled = false;
  }
});

/** Client-side gate() (audio.js) reasons: [{code, params}], already in the
 * app's own naming and ready for t() directly. */
function renderReasons(reasons) {
  return reasons.map((r) => t(`qc.${r.code}`, r.params)).join(' ');
}

// The server's snake_case QC codes (audio_qc/gate.py) don't share the
// client's camelCase key names one-for-one, so this maps between them.
const SERVER_CODE_TO_KEY = {
  sample_rate_low: 'sampleRateLow',
  too_short: 'tooShort',
  too_long: 'tooLong',
  clipping: 'clipped',
  too_loud: 'tooLoud',
  too_quiet: 'tooQuiet',
  noise_floor_high: 'noisy',
  snr_low: 'lowSnr',
  lead_silence_long: 'leadSilenceLong',
  trail_silence_long: 'trailSilenceLong',
};

/** Server verdict (POST /api/clips/{id}/complete): translate from
 * verdict.codes, NOT verdict.reasons -- the server's `reasons` are already
 * rendered into fixed Nepali text server-side, with no structure for t() to
 * use and no way to respect whatever language the UI is currently in. */
function renderServerReasons(verdict) {
  const params = { duration: verdict.duration_s?.toFixed(1) };
  return verdict.codes
    .map((code) => SERVER_CODE_TO_KEY[code])
    .filter(Boolean)
    .map((key) => t(`qc.${key}`, params))
    .join(' ');
}

function renderMetrics(m) {
  const cells = [
    [t('metric.duration'), `${m.durationS.toFixed(1)} s`],
    [t('metric.peak'), `${m.peakDbfs.toFixed(1)} dBFS`],
    [t('metric.snr'), `${m.snrDb.toFixed(0)} dB`],
    [t('metric.roomNoise'), `${m.noiseFloorDbfs.toFixed(0)} dBFS`],
  ];
  return cells.map(([k, v]) => `<div><span>${k}</span><strong>${v}</strong></div>`).join('');
}

$('#next').addEventListener('click', () => {
  state.index++;
  $('#next').classList.add('hidden');
  $('#accept').classList.remove('hidden');
  $('#retake').classList.remove('hidden');
  renderPrompt();
});

$('#retake').addEventListener('click', () => {
  state.samples = null;
  $('#playback').classList.add('hidden');
  $('#metrics').innerHTML = '';
  $('#retake').disabled = true;
  $('#accept').disabled = true;
  techLiveLevel.textContent = '';
  techLiveSize.textContent = '';
  setStatus($('#record-status'), '');
});

$('#accept').addEventListener('click', async () => {
  const status = $('#record-status');
  const button = $('#accept');
  button.disabled = true;
  $('#retake').disabled = true;
  setStatus(status, t('status.sending'));

  const prompt = state.prompts[state.index];

  try {
    const init = await api('/api/clips/init', {
      method: 'POST',
      body: JSON.stringify({ session_id: state.sessionId, prompt_id: prompt.id }),
    });

    // Straight to storage. The API server never sees these bytes.
    const put = await fetch(init.upload.url, {
      method: init.upload.method,
      headers: init.upload.headers,
      body: state.lastBlob,
    });
    if (!put.ok) throw new Error(t('error.uploadFailed', { status: put.status }));

    const verdict = await api(`/api/clips/${init.clip_id}/complete`, {
      method: 'POST',
      body: JSON.stringify({
        client_metrics: {
          snr_db: state.metrics.snrDb,
          peak_dbfs: state.metrics.peakDbfs,
          noise_floor_dbfs: state.metrics.noiseFloorDbfs,
          duration_s: state.metrics.durationS,
          clipping_ratio: state.metrics.clippingRatio,
          sample_rate: state.metrics.sampleRate,
        },
      }),
    });

    if (verdict.passed) {
      state.stats.passed++;
      $('#pass-count').textContent = state.stats.passed;
      // Stay on this screen: the audio above is still the exact take just
      // saved, so the contributor can replay it before moving on.
      setStatus(status, t('status.savedListenConfirm'), 'ok');
      $('#accept').classList.add('hidden');
      $('#retake').classList.add('hidden');
      $('#next').classList.remove('hidden');
    } else {
      state.stats.failed++;
      setStatus(status, renderServerReasons(verdict), 'error');
      $('#retake').disabled = false;
      button.disabled = true;
    }
  } catch (err) {
    setStatus(status, t('error.sendFailed', { error: err.message }), 'error');
    button.disabled = false;
    $('#retake').disabled = false;
  }
});

boot();

function escapeHtml(text) {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function inlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>');
}

function renderConsentMarkdown(markdown) {
  const lines = markdown.split(/\r?\n/);
  const html = [];
  let paragraph = [];
  let list = [];
  let quote = [];
  let table = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${inlineMarkdown(paragraph.join(' '))}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (!list.length) return;
    html.push(`<ul>${list.map((item) => `<li>${inlineMarkdown(item)}</li>`).join('')}</ul>`);
    list = [];
  };
  const flushQuote = () => {
    if (!quote.length) return;
    html.push(`<blockquote>${quote.map((line) => `<p>${inlineMarkdown(line)}</p>`).join('')}</blockquote>`);
    quote = [];
  };
  const flushTable = () => {
    if (!table.length) return;
    const rows = table.filter((row) => !/^\|\s*-+\s*\|/.test(row));
    html.push(`<table><tbody>${rows.map((row) => {
      const cells = row.slice(1, -1).split('|').map((cell) => `<td>${inlineMarkdown(cell.trim())}</td>`).join('');
      return `<tr>${cells}</tr>`;
    }).join('')}</tbody></table>`);
    table = [];
  };
  const flushAll = () => {
    flushParagraph();
    flushList();
    flushQuote();
    flushTable();
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushAll();
      continue;
    }
    if (line === '---') {
      flushAll();
      html.push('<hr>');
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      flushAll();
      const level = heading[1].length + 2;
      html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    if (/^\|.*\|$/.test(line)) {
      flushParagraph();
      flushList();
      flushQuote();
      table.push(line);
      continue;
    }
    if (line.startsWith('- ')) {
      flushParagraph();
      flushQuote();
      flushTable();
      list.push(line.slice(2));
      continue;
    }
    if (line.startsWith('>')) {
      flushParagraph();
      flushList();
      flushTable();
      quote.push(line.replace(/^>\s?/, ''));
      continue;
    }
    flushList();
    flushQuote();
    flushTable();
    paragraph.push(line);
  }
  flushAll();

  return html.join('');
}
