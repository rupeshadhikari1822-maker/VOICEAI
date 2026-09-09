/**
 * Accounts: sign in / sign up / Google, backed by Supabase Auth.
 *
 * The actual sign-in/sign-up UI lives on its own page (`/login`,
 * static/auth/), not in a modal here -- recorder.js redirects there itself if
 * it boots without a session. `initAuth` is still a no-op if the server has
 * no Supabase project configured (GET /api/config returns null keys) -- in
 * that mode getAccessToken() simply returns null, so treat "accounts not
 * configured" as a deployment error, not a fallback.
 *
 * The Supabase client is the one dependency-on-a-CDN in this app. Reimplementing
 * the OAuth/session-refresh dance by hand is far more code and far easier to get
 * wrong than loading the ~30kB official client; everything else here stays
 * plain DOM.
 */

import { t, onLangChange } from '/static/recorder/i18n.js';

const $ = (sel) => document.querySelector(sel);

let client = null;
let session = null;

export function getAccessToken() {
  return session?.access_token ?? null;
}

// Fired whenever the session becomes signed-in -- on a fresh interactive
// sign-in, but also when a page load restores an existing one (including
// returning from a Google OAuth redirect). recorder.js listens for this to
// retroactively link an older, already-in-progress speaker to the account
// that just signed in.
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
      <a href="/login?next=${encodeURIComponent(window.location.pathname)}" id="auth-open" class="icon-btn" aria-label="${escapeHtml(label)}" title="${escapeHtml(label)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      </a>
    `;
  }
}

// --- sign in / sign up / Google, used by the /login page -------------------
//
// These throw on failure (with a message already run through
// authErrorMessage) and simply return on success -- the caller reacts to the
// `onSignedIn` notification above rather than a return value here, since
// Google's redirect-based flow never returns to the caller at all.

export async function signInWithPassword(email, password) {
  if (!client) throw new Error(t('auth.errorGeneric'));
  const { error } = await client.auth.signInWithPassword({ email, password });
  if (error) throw new Error(authErrorMessage(error));
}

/** Returns true if a session was created immediately, false if email
 * confirmation is required before one exists. */
export async function signUpWithPassword(email, password, fullName) {
  if (!client) throw new Error(t('auth.errorGeneric'));
  const { data, error } = await client.auth.signUp({
    email,
    password,
    options: fullName ? { data: { full_name: fullName } } : undefined,
  });
  if (error) throw new Error(authErrorMessage(error));
  return !!data.session;
}

export async function signInWithGoogle(redirectTo) {
  if (!client) throw new Error(t('auth.errorGeneric'));
  const { error } = await client.auth.signInWithOAuth({ provider: 'google', options: { redirectTo } });
  if (error) throw new Error(authErrorMessage(error));
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
