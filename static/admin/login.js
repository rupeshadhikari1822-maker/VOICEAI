/**
 * Admin sign-in: trades an email + password for the reviewer token the rest
 * of the dashboard runs on. Nothing here replaces app/core/security.py's
 * token check -- this is just a friendlier way to get one.
 */

const $ = (sel) => document.querySelector(sel);

function setStatus(message, kind = '') {
  const el = $('#login-status');
  el.textContent = message;
  el.className = `status ${kind}`;
}

$('#login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('#login-submit');
  const form = new FormData(event.target);
  button.disabled = true;
  setStatus('Signing in…');

  try {
    const res = await fetch('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: (form.get('email') || '').toString().trim(),
        password: (form.get('password') || '').toString(),
      }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `${res.status}`);

    // /admin (the page itself, not just its API calls) requires the token
    // via header or query param -- a plain navigation can't carry a header,
    // so the query param is required here, not just a sessionStorage nicety.
    // admin.js reads it from the URL on load and re-stores it for later.
    window.location.href = `/admin?token=${encodeURIComponent(body.token)}`;
  } catch (err) {
    setStatus(`Sign-in failed: ${err.message}`, 'error');
    button.disabled = false;
  }
});
