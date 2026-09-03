/**
 * Flow controller: consent -> profile -> mic check -> record.
 *
 * Dependency-free ES modules on purpose. The whole point of this page is that a
 * contributor on a mid-range Android phone over a slow connection can open a
 * link and start recording; a framework bundle works against that.
 */

import { Recorder, encodeWav, analyze, gate, dbfs } from '/static/recorder/audio.js';
import { runPreflight } from '/static/recorder/preflight.js';

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
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
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

function showStep(name) {
  $$('.step').forEach((el) => el.classList.toggle('active', el.dataset.step === name));
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function setStatus(el, message, kind = '') {
  el.textContent = message;
  el.className = `status ${kind}`;
}

// --- boot ---------------------------------------------------------------

async function boot() {
  try {
    state.config = await api('/api/config');
  } catch (err) {
    setStatus($('#consent-status'), `सेटिङ लोड हुन सकेन: ${err.message}`, 'error');
    return;
  }

  $('#consent-text').innerHTML = renderConsentMarkdown(state.config.consent.text);
  $('#consent-version').textContent = state.config.consent.version;
  $('#spec-sr').textContent = `${state.config.audio.sample_rate / 1000} kHz`;
  $('#spec-snr').textContent = `${state.config.qc.min_snr_db} dB`;

  if (!navigator.mediaDevices || !window.AudioWorkletNode) {
    setStatus(
      $('#consent-status'),
      'यो ब्राउजरले रेकर्डिङ समर्थन गर्दैन — Chrome वा Firefox प्रयोग गर्नुहोस्।',
      'error',
    );
  }
  if (!window.isSecureContext) {
    setStatus(
      $('#consent-status'),
      'माइक चलाउन HTTPS चाहिन्छ। (microphone requires a secure context)',
      'error',
    );
  }
}

// --- step 1: consent ----------------------------------------------------

$('#consent-agree').addEventListener('change', (e) => {
  $('#to-profile').disabled = !e.target.checked;
});

$('#to-profile').addEventListener('click', () => showStep('profile'));

// --- step 2: profile ----------------------------------------------------

$('#profile-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = $('#profile-status');
  const button = $('#profile-submit');
  button.disabled = true;
  setStatus(status, 'पठाइँदै…');

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
    consent: {
      version: state.config.consent.version,
      accepted: $('#consent-agree').checked,
      commercial_use: true,
    },
  };

  try {
    const speaker = await api('/api/speakers', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    state.speakerId = speaker.speaker_id;

    const session = await api('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({
        speaker_id: state.speakerId,
        lang: value('lang') || 'ne',
        device_hint: navigator.userAgent.slice(0, 300),
      }),
    });
    state.sessionId = session.session_id;

    // Prove uploads work BEFORE anyone reads a sentence aloud. A CORS
    // misconfiguration is invisible to every server-side check, and without
    // this it surfaces only after twenty minutes of recording.
    setStatus(status, 'अपलोड जाँच गर्दै…');
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
    setStatus(status, `पठाउन सकिएन: ${err.message}`, 'error');
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

// --- step 3: mic check --------------------------------------------------

// Both the mic-check step and the recording step show a level meter.
const meterFills = [$('#meter-fill'), $('#meter-fill-2')].filter(Boolean);
const meterLabel = $('#meter-label');

function onLevel({ peak }) {
  const db = dbfs(peak);
  // Map -60..0 dBFS onto the bar.
  const pct = Math.max(0, Math.min(100, ((db + 60) / 60) * 100));
  for (const fill of meterFills) {
    fill.style.width = `${pct}%`;
    fill.classList.toggle('hot', db > -1);
    fill.classList.toggle('good', db >= -12 && db <= -1);
  }
  meterLabel.textContent = `${db.toFixed(0)} dBFS`;
}

$('#mic-start').addEventListener('click', async () => {
  const status = $('#mic-status');
  try {
    setStatus(status, 'माइक खोल्दै…');
    state.recorder.onLevel = onLevel;
    await state.recorder.init();
    await state.recorder.resume();

    const info = state.recorder.trackInfo();
    const rate = state.recorder.sampleRate;
    $('#mic-name').textContent = info.label || 'अज्ञात माइक';
    $('#mic-rate').textContent = `${rate} Hz`;

    const problems = [];
    if (rate < 32000) {
      problems.push(`यो माइक ${rate} Hz मा मात्र चल्छ — ब्लुटुथ हेडसेट हटाएर तार भएको माइक प्रयोग गर्नुहोस्।`);
    }
    if (/bluetooth|hands-?free|airpod|buds/i.test(info.label || '')) {
      problems.push('ब्लुटुथ माइक पत्ता लाग्यो — यसले आवाज ८/१६ kHz मा झार्छ। तार भएको हेडसेट प्रयोग गर्नुहोस्।');
    }
    // Chrome reports what it actually applied; if DSP is on, the constraints
    // were overridden and the corpus would get auto-gained audio.
    for (const [key, label] of [
      ['echoCancellation', 'echo cancellation'],
      ['noiseSuppression', 'noise suppression'],
      ['autoGainControl', 'auto gain control'],
    ]) {
      if (info[key] === true) problems.push(`ब्राउजरले ${label} बन्द गर्न मानेन।`);
    }

    // Watchdog for a failure with no error attached to it.
    //
    // If the audio graph is not being scheduled, process() never runs: the mic
    // permission is granted, the track is live, the label and sample rate
    // display correctly, and the level meter sits frozen at silence with
    // nothing in the console. On a phone there IS no console, so without this
    // the contributor and the operator both see "it just doesn't work".
    //
    // The worklet posts a level message roughly every 20 ms, so a second of
    // nothing is decisive rather than a slow start.
    await new Promise((r) => setTimeout(r, 1200));
    if (!state.recorder.workletAlive) {
      $('#mic-problems').innerHTML = '';
      setStatus(
        status,
        'माइक खुल्यो तर आवाज आइरहेको छैन। यो तपाईंको गल्ती होइन — ' +
          'यो यन्त्र/ब्राउजरको समस्या हो। सम्भव भए Chrome प्रयोग गर्नुहोस्, ' +
          'नभए hello@cloudfrm.ai मा खबर गर्नुहोस्। (AUDIO_WORKLET_SILENT)',
        'error',
      );
      console.error(
        '[mic] AUDIO_WORKLET_SILENT: process() produced no frames in 1.2s. ' +
          'The AudioWorklet is not being scheduled — the graph is likely ' +
          'considered inactive by this browser.',
        { sampleRate: rate, label: info.label, state: state.recorder.context.state },
      );
      return;
    }

    $('#mic-problems').innerHTML = problems.map((p) => `<li>${p}</li>`).join('');
    setStatus(status, problems.length ? 'चेतावनी हेर्नुहोस्।' : 'माइक तयार छ। अब ५ सेकेन्ड चुप बस्नुहोस्।', problems.length ? 'warn' : 'ok');

    $('#mic-start').disabled = true;
    $('#mic-quiet').disabled = false;
  } catch (err) {
    setStatus(status, `माइक खोल्न सकिएन: ${err.message}`, 'error');
  }
});

// Room-tone test: record silence and measure the floor. This is the single
// most useful check, because a noisy room fails every clip that follows.
$('#mic-quiet').addEventListener('click', async () => {
  const status = $('#mic-status');
  const button = $('#mic-quiet');
  button.disabled = true;
  setStatus(status, 'चुप बस्नुहोस्… ५ सेकेन्ड मापन गर्दै।');

  state.recorder.start();
  await new Promise((r) => setTimeout(r, 5000));
  const samples = await state.recorder.stop();
  const m = analyze(samples, state.recorder.sampleRate);
  const limit = state.config.qc.max_noise_floor_dbfs;

  $('#room-floor').textContent = `${m.noiseFloorDbfs.toFixed(0)} dBFS`;

  if (m.noiseFloorDbfs > limit) {
    setStatus(
      status,
      `कोठाको आवाज धेरै छ (${m.noiseFloorDbfs.toFixed(0)} dBFS, चाहिने ${limit} भन्दा कम) — पंखा, AC, TV बन्द गर्नुहोस् र झ्याल–ढोका थुन्नुहोस्, अनि फेरि जाँच्नुहोस्।`,
      'error',
    );
    button.disabled = false;
    return;
  }

  setStatus(status, `कोठा राम्रो छ (${m.noiseFloorDbfs.toFixed(0)} dBFS)। रेकर्डिङ सुरु गर्न सकिन्छ।`, 'ok');
  $('#to-record').disabled = false;
});

$('#to-record').addEventListener('click', async () => {
  await loadPrompts();
  showStep('record');
  renderPrompt();
});

// --- step 4: recording --------------------------------------------------

async function loadPrompts() {
  state.prompts = await api(`/api/prompts?session_id=${state.sessionId}&limit=50`);
  state.index = 0;
}

function renderPrompt() {
  const prompt = state.prompts[state.index];
  if (!prompt) {
    showStep('done');
    $('#done-count').textContent = state.stats.passed;
    $('#done-speaker').textContent = state.speakerId;
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
  state.samples = null;
}

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
    recordButton.textContent = 'रोक्नुहोस्';
    recordButton.classList.add('recording');
    setStatus($('#record-status'), 'रेकर्ड हुँदैछ… वाक्य पढ्नुहोस्।');
    timerHandle = setInterval(() => {
      $('#timer').textContent = `${((Date.now() - startedAt) / 1000).toFixed(1)}s`;
    }, 100);
    return;
  }

  isRecording = false;
  clearInterval(timerHandle);
  recordButton.textContent = 'रेकर्ड गर्नुहोस्';
  recordButton.classList.remove('recording');

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

  if (verdict.passed) {
    setStatus($('#record-status'), 'राम्रो छ। सुनेर पठाउनुहोस्।', 'ok');
    $('#accept').disabled = false;
  } else {
    setStatus($('#record-status'), verdict.reasons.join(' '), 'error');
    // Deliberately still allowed: the server decides. A client false-negative
    // should not be able to block a usable take.
    $('#accept').disabled = false;
  }
});

function renderMetrics(m) {
  const cells = [
    ['अवधि', `${m.durationS.toFixed(1)} s`],
    ['स्तर (peak)', `${m.peakDbfs.toFixed(1)} dBFS`],
    ['SNR', `${m.snrDb.toFixed(0)} dB`],
    ['कोठाको आवाज', `${m.noiseFloorDbfs.toFixed(0)} dBFS`],
  ];
  return cells.map(([k, v]) => `<div><span>${k}</span><strong>${v}</strong></div>`).join('');
}

$('#retake').addEventListener('click', () => {
  state.samples = null;
  $('#playback').classList.add('hidden');
  $('#metrics').innerHTML = '';
  $('#retake').disabled = true;
  $('#accept').disabled = true;
  setStatus($('#record-status'), '');
});

$('#accept').addEventListener('click', async () => {
  const status = $('#record-status');
  const button = $('#accept');
  button.disabled = true;
  $('#retake').disabled = true;
  setStatus(status, 'पठाइँदै…');

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
    if (!put.ok) throw new Error(`अपलोड असफल (${put.status})`);

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
      state.index++;
      renderPrompt();
    } else {
      state.stats.failed++;
      setStatus(status, verdict.reasons.join(' '), 'error');
      $('#retake').disabled = false;
      button.disabled = true;
    }
  } catch (err) {
    setStatus(status, `पठाउन सकिएन: ${err.message}`, 'error');
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
