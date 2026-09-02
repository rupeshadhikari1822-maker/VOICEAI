/**
 * Storage preflight: prove the browser can actually upload, before recording.
 *
 * The failure this prevents: bucket CORS is misconfigured, every server-side
 * check passes, and the contributor discovers it after reading twenty-five
 * sentences aloud. What they see is a failed upload, which looks exactly like
 * bad wifi — so they blame their connection or themselves, and you lose the
 * session and the person.
 *
 * So: do one real cross-origin PUT of ~1 KB at session start and refuse to
 * continue if it fails.
 *
 * Classifying the failure is the interesting part. The fetch API deliberately
 * gives a CORS rejection and a network failure the *same* opaque TypeError with
 * no status — the spec hides the difference to avoid leaking cross-origin
 * information. So we disambiguate with a control request to our own origin:
 *
 *   PUT throws + control request also fails  -> the network is down
 *   PUT throws + control request succeeds    -> the network is fine, so the
 *                                               bucket rejected the preflight,
 *                                               i.e. CORS
 *   PUT returns 401/403                      -> reached the bucket, credentials
 *                                               or clock skew
 *
 * That last case matters: an HTTP status means CORS *worked*. A signature
 * rejection is a different problem with a different fix.
 */

export const StorageError = {
  CORS: 'STORAGE_CORS',
  AUTH: 'STORAGE_AUTH',
  NETWORK: 'STORAGE_NETWORK',
  UNKNOWN: 'STORAGE_UNKNOWN',
};

// Contributor-facing copy. For CORS and AUTH the contributor cannot do
// anything, so the message must say so plainly rather than sending them off to
// restart their router. Blaming the reader for our misconfiguration is how you
// lose them.
const MESSAGES = {
  [StorageError.CORS]:
    'सर्भरको सेटिङमा समस्या छ — यो तपाईंको इन्टरनेटको समस्या होइन। ' +
    'कृपया hello@cloudfrm.ai मा खबर गर्नुहोस्। अहिले रेकर्ड गर्न मिल्दैन।',
  [StorageError.AUTH]:
    'सर्भरको अनुमतिमा समस्या छ — यो तपाईंको गल्ती होइन। ' +
    'कृपया hello@cloudfrm.ai मा खबर गर्नुहोस्।',
  [StorageError.NETWORK]:
    'इन्टरनेट जोडिएन। सम्पर्क जाँचेर फेरि प्रयास गर्नुहोस्।',
  [StorageError.UNKNOWN]:
    'अपलोड जाँच असफल भयो। फेरि प्रयास गर्नुहोस्, नभए hello@cloudfrm.ai मा खबर गर्नुहोस्।',
};

// Operator-facing. Shown small, under the contributor message, so a screenshot
// from the field is enough to diagnose it.
const HINTS = {
  [StorageError.CORS]:
    'Bucket CORS is rejecting the browser. Allow PUT and GET from this origin.',
  [StorageError.AUTH]:
    'Bucket reached but the presigned URL was refused: bad credentials, or ' +
    'server clock skew invalidating the signature.',
  [StorageError.NETWORK]: 'The device could not reach the network at all.',
  [StorageError.UNKNOWN]: 'Unclassified upload failure.',
};

function result(codeOrNull, detail = '') {
  if (!codeOrNull) return { ok: true };
  return {
    ok: false,
    code: codeOrNull,
    message: MESSAGES[codeOrNull],
    hint: HINTS[codeOrNull],
    detail,
  };
}

/**
 * @returns {Promise<{ok: boolean, code?: string, message?: string,
 *                     hint?: string, detail?: string, sameOrigin?: boolean}>}
 */
export async function runPreflight(apiBase = '') {
  let config;
  try {
    const res = await fetch(`${apiBase}/api/storage/preflight`);
    if (!res.ok) return result(StorageError.UNKNOWN, `preflight config HTTP ${res.status}`);
    config = await res.json();
  } catch (err) {
    // Our own API is unreachable, so this is not a storage problem at all.
    return result(StorageError.NETWORK, `preflight config: ${err.message}`);
  }

  const body = new Uint8Array(config.probe_bytes || 1024);

  let response;
  try {
    response = await fetch(config.url, {
      method: config.method || 'PUT',
      headers: config.headers || {},
      body,
    });
  } catch (err) {
    // Opaque by design. Ask our own origin whether the network is up.
    const networkUp = await controlReachable(apiBase, config.control_url);
    const code = networkUp ? StorageError.CORS : StorageError.NETWORK;
    return { ...result(code, err.message), sameOrigin: config.same_origin };
  }

  if (response.ok) {
    return { ok: true, sameOrigin: config.same_origin, backend: config.backend };
  }

  // A status at all means CORS let the response through.
  const code =
    response.status === 401 || response.status === 403
      ? StorageError.AUTH
      : StorageError.UNKNOWN;
  return {
    ...result(code, `PUT returned ${response.status}`),
    sameOrigin: config.same_origin,
  };
}

async function controlReachable(apiBase, controlUrl) {
  try {
    const res = await fetch(`${apiBase}${controlUrl || '/healthz'}`, {
      cache: 'no-store',
    });
    return res.ok;
  } catch (_) {
    return false;
  }
}
