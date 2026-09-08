/**
 * Staff dashboard: corpus health at a glance. Same reviewer-token trust
 * boundary as /review (and reuses its sessionStorage key, so a reviewer who
 * already opened /review?token=... doesn't have to paste it again here).
 */

const $ = (sel) => document.querySelector(sel);

const PAGE_SIZE = 25;
let offset = 0;
let total = 0;

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

async function api(path) {
  const res = await fetch(path, {
    headers: { Authorization: `Bearer ${token()}` },
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

function setLoadStatus(message, kind = '') {
  const el = $('#load-status');
  el.textContent = message;
  el.className = `status ${kind}`;
}

async function loadOverview() {
  const o = await api('/api/admin/overview');

  $('#stat-speakers-total').textContent = o.speakers.total;
  $('#stat-speakers-sub').textContent = `${o.speakers.withdrawn} withdrawn`;
  $('#stat-speakers-linked').textContent = o.speakers.linked_to_account;

  $('#stat-sessions-total').textContent = o.sessions.total;

  $('#stat-clips-passed').textContent = o.clips.passed;
  $('#stat-clips-sub').textContent = `${o.clips.failed} failed, ${o.clips.pending} pending of ${o.clips.total} total`;

  $('#stat-avg-snr').textContent = o.quality.avg_snr_db != null ? `${o.quality.avg_snr_db} dB` : '';

  $('#stat-prompts-active').textContent = o.prompts.active;
  $('#stat-prompts-sub').textContent = `${o.prompts.inactive_pending_review} inactive / pending review`;
  $('#stat-prompts-uncovered').textContent = o.prompts.active_uncovered;

  $('#stat-review-pending').textContent = o.review.pending;
}

function renderSpeakersTable(rows) {
  $('#speakers-tbody').innerHTML = rows
    .map(
      (s) => `
    <tr>
      <td><code>${s.speaker_id}</code></td>
      <td>${new Date(s.created_at).toLocaleDateString()}</td>
      <td>${escapeHtml(s.name || '')}</td>
      <td>${escapeHtml(s.email || '')}</td>
      <td>${escapeHtml(s.phone || '')}</td>
      <td>${escapeHtml(s.province || '')}</td>
      <td>${escapeHtml(s.mother_tongue || '')}</td>
      <td>${s.linked_account ? '✓' : ''}</td>
      <td>${s.passed_clips}</td>
      <td>${s.withdrawn ? '✓' : ''}</td>
    </tr>`,
    )
    .join('');
}

async function loadSpeakers() {
  const data = await api(`/api/admin/speakers?limit=${PAGE_SIZE}&offset=${offset}`);
  total = data.total;
  renderSpeakersTable(data.speakers);

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  $('#page-label').textContent = `Page ${page} of ${pages} (${total} speakers)`;
  $('#prev-page').disabled = offset === 0;
  $('#next-page').disabled = offset + PAGE_SIZE >= total;
}

$('#prev-page').addEventListener('click', () => {
  offset = Math.max(0, offset - PAGE_SIZE);
  loadSpeakers();
});
$('#next-page').addEventListener('click', () => {
  offset += PAGE_SIZE;
  loadSpeakers();
});

// --- export dataset ------------------------------------------------------
//
// A GET that streams a zip back, same trust boundary as everything else here
// (Authorization: Bearer <reviewer token>). fetch()+blob rather than a plain
// navigation so a failure (e.g. no clips matched) shows an error in place
// instead of navigating the whole dashboard away to a bare JSON error body.

const FORMAT_DEFAULT_SR = { asr: 16000, tts: 22050, ljspeech: 22050, hf: 16000 };

function updateExportSrPlaceholder() {
  const format = $('#export-format').value;
  $('#export-sr').placeholder = `${FORMAT_DEFAULT_SR[format]} (format default)`;
}
$('#export-format').addEventListener('change', updateExportSrPlaceholder);
updateExportSrPlaceholder();

$('#export-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = $('#export-status');
  const button = $('#export-submit');
  const form = new FormData(event.target);

  const params = new URLSearchParams({ format: form.get('format') });
  const sr = (form.get('sr') || '').toString().trim();
  if (sr) params.set('sr', sr);
  const minSnr = (form.get('min_snr') || '').toString().trim();
  if (minSnr) params.set('min_snr', minSnr);
  if (form.get('verified_only')) params.set('verified_only', 'true');

  button.disabled = true;
  status.textContent = 'Preparing download… this can take a while for a large corpus.';
  status.className = 'status';

  try {
    const res = await fetch(`/api/admin/export?${params.toString()}`, {
      headers: { Authorization: `Bearer ${token()}` },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `${res.status}`);
    }

    const disposition = res.headers.get('content-disposition') || '';
    const match = /filename="?([^"]+)"?/.exec(disposition);
    const filename = match ? match[1] : `voiceai-${form.get('format')}-export.zip`;

    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(blobUrl);

    status.textContent = '';
  } catch (err) {
    status.textContent = `Export failed: ${err.message}`;
    status.className = 'status error';
  } finally {
    button.disabled = false;
  }
});

function escapeHtml(text) {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

async function boot() {
  if (!token()) {
    setLoadStatus('A reviewer token is required. Add ?token=... to the link.', 'error');
    return;
  }
  try {
    await Promise.all([loadOverview(), loadSpeakers()]);
    setLoadStatus('');
    $('#dashboard').classList.remove('hidden');
  } catch (err) {
    setLoadStatus(`Could not load dashboard: ${err.message}`, 'error');
  }
}

boot();
