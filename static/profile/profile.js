/**
 * Account profile: personal details (editable) + the recordings linked to it.
 *
 * Reuses the recorder's auth.js and i18n.js directly rather than duplicating
 * the Supabase client or the string table -- this page needs the same
 * `#authbar` header markup (see index.html) for that module's DOM queries
 * to work, which is why it's duplicated rather than shared as a template.
 */

import { initAuth, getAccessToken, onSignedIn } from '/static/recorder/auth.js';
import { t, applyStaticTranslations, initLangSelector, onLangChange } from '/static/recorder/i18n.js';

const $ = (sel) => document.querySelector(sel);

let lastClips = [];

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    const err = new Error(`${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

function show(id) {
  ['signed-out-notice', 'empty-notice', 'profile-content'].forEach((sid) => {
    $(`#${sid}`).classList.toggle('hidden', sid !== id);
  });
}

initLangSelector();
applyStaticTranslations();
onLangChange(() => {
  applyStaticTranslations();
  renderClips(lastClips);
});

async function boot() {
  // Registered before initAuth(): its very first "already signed in?" check
  // fires synchronously inside that call, same ordering rule as recorder.js.
  onSignedIn(loadProfile);

  let config;
  try {
    config = await fetch('/api/config').then((r) => r.json());
  } catch (err) {
    $('#profile-load-status').textContent = t('error.configLoadFailed', { error: err.message });
    return;
  }

  try {
    await initAuth(config);
  } catch (err) {
    console.warn('[auth] failed to initialize', err);
  }

  if (!getAccessToken()) show('signed-out-notice');
}

async function loadProfile() {
  try {
    const profile = await api('/api/me/profile');
    fillForm(profile);
    lastClips = profile.clips;
    renderClips(profile.clips);
    $('#profile-speaker-id').textContent = profile.speaker_id;
    show('profile-content');
  } catch (err) {
    if (err.status === 404) {
      show('empty-notice');
    } else {
      console.warn('[profile] failed to load', err);
      show('signed-out-notice');
    }
  }
}

function fillForm(profile) {
  const form = $('#profile-form');
  for (const [key, value] of Object.entries(profile)) {
    const field = form.elements.namedItem(key);
    if (field) field.value = value ?? '';
  }
}

$('#profile-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = $('#profile-form-status');
  const button = event.target.querySelector('button[type=submit]');
  button.disabled = true;
  status.textContent = t('status.sending');
  status.className = 'status';

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
    caste_ethnicity: value('caste_ethnicity'),
  };

  try {
    const speakerId = $('#profile-speaker-id').textContent;
    await api(`/api/speakers/${speakerId}`, { method: 'PATCH', body: JSON.stringify(payload) });
    status.textContent = t('profilePage.saved');
    status.className = 'status ok';
  } catch (err) {
    status.textContent = t('error.sendFailed', { error: err.message });
    status.className = 'status error';
  } finally {
    button.disabled = false;
  }
});

function renderClips(clips) {
  const container = $('#recordings-table');
  if (!clips || !clips.length) {
    container.innerHTML = `<li class="fineprint">${t('profilePage.noClipsYet')}</li>`;
    return;
  }
  container.innerHTML = clips
    .map(
      (c) => `
    <li>
      <span class="clip-text">${escapeHtml(c.prompt_text)}</span>
      <span class="clip-status ${c.qc_status}">${statusLabel(c.qc_status)}</span>
      <button type="button" class="ghost listen-btn" data-clip-id="${c.clip_id}">${t('profilePage.listen')}</button>
    </li>`,
    )
    .join('');
  container.querySelectorAll('.listen-btn').forEach((btn) => {
    btn.addEventListener('click', () => listenTo(btn.dataset.clipId, btn));
  });
}

function statusLabel(status) {
  if (status === 'passed') return t('profilePage.statusPassed');
  if (status === 'failed') return t('profilePage.statusFailed');
  return t('profilePage.statusPending');
}

async function listenTo(clipId, button) {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = t('status.sending');
  try {
    const { url } = await api(`/api/me/clips/${clipId}/listen`);
    new Audio(url).play();
  } catch (err) {
    console.warn('[profile] could not play clip', err);
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function escapeHtml(text) {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

boot();
