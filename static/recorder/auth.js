/**
 * Accounts: sign in / sign up / Google, backed by Supabase Auth.
 *
 * The recorder flow (recorder.js) requires a signed-in session before it will
 * register a speaker, so `openAuthModal` doubles as that gate. `initAuth` is
 * still a no-op if the server has no Supabase project configured (GET
 * /api/config returns null keys) -- in that mode getAccessToken() simply
 * returns null and the gate in recorder.js has nothing to check against, so
 * treat "accounts not configured" as a deployment error, not a fallback.
 *
 * The Supabase client is the one dependency-on-a-CDN in this app. Reimplementing
 * the OAuth/session-refresh dance by hand is far more code and far easier to get
 * wrong than loading the ~30kB official client; everything else here stays
 * plain DOM.
 */

import { t, onLangChange } from '/static/recorder/i18n.js';

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

let client = null;
let session = null;

export function getAccessToken() {
  return session?.access_token ?? null;
}

// Fired whenever the session becomes signed-in -- on a fresh interactive
// sign-in, but also when a page load restores an existing one (including
// returning from a Google OAuth redirect). recorder.js listens for this both
// to resume a registration that was blocked on signing in, and to retroactively
// link an older, already-in-progress speaker to the account that just signed in.
const signedInListeners = [];
export function onSignedIn(fn) {
  signedInListeners.push(fn);
}
function notifySignedIn() {
  signedInListeners.forEach((fn) => fn());
}

export async function initAuth(config) {
  const url = config?.accounts?.supabase_url;
  const anonKey = config?.accounts?.supabase_anon_key;
  if (!url || !anonKey) return; // accounts not configured server-side

  const { createClient } = await import(
    'https://esm.sh/@supabase/supabase-js@2.115.0'
  );
  client = createClient(url, anonKey);

  wireAuthModal();
  onLangChange(() => renderAuthbar());

  const { data } = await client.auth.getSession();
  session = data.session;
  renderAuthbar();
  if (session?.user) notifySignedIn();

  client.auth.onAuthStateChange((_event, newSession) => {
    const wasSignedIn = !!session?.user;
    session = newSession;
    renderAuthbar();
    if (session?.user && !wasSignedIn) notifySignedIn();
  });
}

function renderAuthbar() {
  const authbar = $('#authbar');
  if (!authbar) return;
  if (session?.user) {
    const label = session.user.email || t('auth.account');
    authbar.innerHTML = `
      <span class="account-chip">${escapeHtml(label)}</span>
      <a href="/profile" class="ghost link-btn">${t('auth.myRecordings')}</a>
      <button type="button" id="auth-signout" class="ghost">${t('auth.signOut')}</button>
    `;
    $('#auth-signout').addEventListener('click', () => client.auth.signOut());
  } else {
    const label = t('auth.signIn');
    authbar.innerHTML = `
      <button type="button" id="auth-open" class="icon-btn" aria-label="${escapeHtml(label)}" title="${escapeHtml(label)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      </button>
    `;
    $('#auth-open').addEventListener('click', openAuthModal);
  }
}

// --- sign in / sign up modal ---------------------------------------------

export function openAuthModal() {
  setTab('signin');
  setAuthStatus('');
  $('#auth-modal-backdrop').classList.remove('hidden');
}

function closeAuthModal() {
  $('#auth-modal-backdrop').classList.add('hidden');
}

function setTab(tab) {
  $$('.auth-tab').forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === tab));
  $('#auth-submit').textContent = tab === 'signup' ? t('auth.signUpTab') : t('auth.signInSubmit');
  $('#auth-form').dataset.mode = tab;
}

function setAuthStatus(message, kind = '') {
  const el = $('#auth-status');
  el.textContent = message;
  el.className = `status ${kind}`;
}

function wireAuthModal() {
  $('#auth-modal-close').addEventListener('click', closeAuthModal);
  $('#auth-modal-backdrop').addEventListener('click', (e) => {
    if (e.target.id === 'auth-modal-backdrop') closeAuthModal();
  });
  $$('.auth-tab').forEach((btn) => btn.addEventListener('click', () => setTab(btn.dataset.tab)));

  $('#auth-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const mode = event.target.dataset.mode || 'signin';
    const form = new FormData(event.target);
    const email = (form.get('email') || '').toString().trim();
    const password = (form.get('password') || '').toString();
    const button = $('#auth-submit');
    button.disabled = true;
    setAuthStatus(mode === 'signup' ? t('auth.creatingAccount') : t('auth.signingIn'));

    try {
      if (mode === 'signup') {
        const { data, error } = await client.auth.signUp({ email, password });
        if (error) throw error;
        if (!data.session) {
          setAuthStatus(t('auth.checkEmail'), 'ok');
          button.disabled = false;
          return;
        }
      } else {
        const { error } = await client.auth.signInWithPassword({ email, password });
        if (error) throw error;
      }
      closeAuthModal();
    } catch (err) {
      setAuthStatus(authErrorMessage(err), 'error');
    } finally {
      button.disabled = false;
    }
  });

  $('#auth-google').addEventListener('click', async () => {
    try {
      const { error } = await client.auth.signInWithOAuth({ provider: 'google' });
      if (error) throw error;
    } catch (err) {
      setAuthStatus(authErrorMessage(err), 'error');
    }
  });
}

function authErrorMessage(err) {
  const msg = err?.message || '';
  if (/invalid login credentials/i.test(msg)) return t('auth.errorBadCredentials');
  if (/user already registered/i.test(msg)) return t('auth.errorAlreadyRegistered');
  if (/provider is not enabled/i.test(msg)) return t('auth.errorGoogleDisabled');
  return msg || t('auth.errorGeneric');
}

function escapeHtml(text) {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}
