/**
 * /login: the front door to the studio. Nobody reaches consent (recorder.js)
 * without an account -- this page is where that account gets created or
 * signed into, then hands off to wherever `?next=` says (default /studio).
 *
 * Reuses the recorder's auth.js and i18n.js rather than duplicating the
 * Supabase client -- same convention as static/profile/profile.js.
 */

import { initAuth, getAccessToken, onSignedIn, signInWithPassword, signUpWithPassword, signInWithGoogle } from '/static/recorder/auth.js';
import { t } from '/static/recorder/i18n.js';

const $ = (sel) => document.querySelector(sel);

function nextUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get('next') || '/studio';
}

function goToNext() {
  window.location.href = nextUrl();
}

// --- tab switching ----------------------------------------------------------

const ACTIVE_TAB = 'flex-1 py-2 rounded-lg font-label-md text-label-md font-semibold transition-all duration-200 bg-surface-container-high text-primary shadow-inner';
const INACTIVE_TAB = 'flex-1 py-2 rounded-lg font-label-md text-label-md font-medium text-text-secondary hover:text-text-primary transition-all duration-200';

function switchTab(mode) {
  const signinForm = $('#signin-form');
  const signupForm = $('#signup-form');
  const signinBtn = $('#tab-signin-btn');
  const signupBtn = $('#tab-signup-btn');
  const title = $('#auth-title');
  const subtitle = $('#auth-subtitle');

  setStatus('');
  if (mode === 'signin') {
    signinForm.classList.remove('hidden');
    signupForm.classList.add('hidden');
    signinBtn.className = ACTIVE_TAB;
    signupBtn.className = INACTIVE_TAB;
    title.textContent = 'Welcome back to Voice Studio';
    subtitle.textContent = 'Enter credentials to connect your synthetic voice models.';
  } else {
    signinForm.classList.add('hidden');
    signupForm.classList.remove('hidden');
    signupBtn.className = ACTIVE_TAB;
    signinBtn.className = INACTIVE_TAB;
    title.textContent = 'Deploy Your Neural Identity';
    subtitle.textContent = 'Create an enterprise account to synthesize, watermark, and monetize vocal clones.';
  }
}

$('#tab-signin-btn').addEventListener('click', () => switchTab('signin'));
$('#tab-signup-btn').addEventListener('click', () => switchTab('signup'));

// --- password visibility toggles --------------------------------------------

document.querySelectorAll('[data-toggle-password]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const input = $(`#${btn.dataset.togglePassword}`);
    const icon = btn.querySelector('.material-symbols-outlined');
    const showing = input.type === 'text';
    input.type = showing ? 'password' : 'text';
    icon.textContent = showing ? 'visibility' : 'visibility_off';
  });
});

// --- signup password strength meter (a length-based hint, not a real
// entropy measurement) ------------------------------------------------------

const STRENGTH_LEVELS = [
  { min: 0, bars: 0, label: 'AWAITING INPUT', labelClass: 'text-text-muted font-semibold' },
  { min: 1, bars: 1, label: 'LOW ENTROPY', labelClass: 'text-error font-semibold', barClass: 'bg-error' },
  { min: 6, bars: 2, label: 'STANDARD SECURE', labelClass: 'text-primary font-semibold', barClass: 'bg-primary-container' },
  { min: 10, bars: 4, label: '256-BIT HIGH ENTROPY', labelClass: 'text-glow-cyan font-semibold', barClass: 'bg-glow-cyan' },
];

function updateStrength(value) {
  const bars = [1, 2, 3, 4].map((n) => $(`#bar-${n}`));
  const label = $('#entropy-label');
  const level = [...STRENGTH_LEVELS].reverse().find((l) => value.length >= l.min);

  bars.forEach((bar, i) => {
    const filled = i < level.bars;
    bar.className = `rounded-full h-full ${filled ? level.barClass || 'bg-primary' : 'bg-surface-container-highest'}`;
  });
  label.textContent = level.label;
  label.className = level.labelClass;
}

$('#signup-password').addEventListener('input', (e) => updateStrength(e.target.value));

// --- status line -------------------------------------------------------------

function setStatus(message, kind = '') {
  const el = $('#auth-status');
  el.textContent = message;
  el.classList.toggle('hidden', !message);
  el.className = `font-body-sm text-body-sm mb-4 ${message ? '' : 'hidden'} ${
    kind === 'error' ? 'text-error' : kind === 'ok' ? 'text-primary' : 'text-text-secondary'
  }`.trim();
}

// --- form submissions ---------------------------------------------------------

$('#signin-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const email = $('#signin-email').value.trim();
  const password = $('#signin-password').value;
  const button = event.target.querySelector('button[type=submit]');
  button.disabled = true;
  setStatus(t('auth.signingIn'));
  try {
    await signInWithPassword(email, password);
    // onSignedIn below handles the redirect once Supabase confirms the session.
  } catch (err) {
    setStatus(err.message, 'error');
    button.disabled = false;
  }
});

$('#signup-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const fullName = $('#signup-name').value.trim();
  const email = $('#signup-email').value.trim();
  const password = $('#signup-password').value;
  const button = event.target.querySelector('button[type=submit]');
  button.disabled = true;
  setStatus(t('auth.creatingAccount'));
  try {
    const hasSession = await signUpWithPassword(email, password, fullName);
    if (!hasSession) {
      setStatus(t('auth.checkEmail'), 'ok');
      button.disabled = false;
    }
    // Otherwise onSignedIn below handles the redirect.
  } catch (err) {
    setStatus(err.message, 'error');
    button.disabled = false;
  }
});

$('#auth-google-btn').addEventListener('click', async () => {
  try {
    const redirectTo = `${window.location.origin}/login?next=${encodeURIComponent(nextUrl())}`;
    await signInWithGoogle(redirectTo);
    // Full-page redirect to Google now; nothing more happens on this page load.
  } catch (err) {
    setStatus(err.message, 'error');
  }
});

// --- boot ---------------------------------------------------------------

onSignedIn(goToNext);

async function boot() {
  let config;
  try {
    config = await fetch('/api/config').then((r) => r.json());
  } catch (err) {
    setStatus(t('error.configLoadFailed', { error: err.message }), 'error');
    return;
  }

  try {
    await initAuth(config);
  } catch (err) {
    console.warn('[auth] failed to initialize', err);
  }

  // Already signed in (a restored session, or someone who bookmarked /login) --
  // no need to show the form at all.
  if (getAccessToken()) goToNext();
}

boot();
