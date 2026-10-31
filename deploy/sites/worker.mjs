// Sites controls visitor access. This layer transports existing game requests;
// it never interprets votes, stores mission state, or decides phase transitions.
const token = '[A-Za-z0-9_-]+';
const mission = new RegExp(`^/api/missions/${token}/(join|start|discussion|continue|retry-preparation)$`);
const websocket = new RegExp(`^/api/missions/${token}/ws$`);
const failure = (status, detail) => Response.json({ detail }, {
  status, headers: { 'Cache-Control': 'no-store' },
});

export function createWorker(assets, upstreamFetch = fetch) {
  return {
    async fetch(request, env) {
      const url = new URL(request.url);
      if (!url.pathname.startsWith('/api/')) {
        const asset = assets[url.pathname];
        if (!asset || !['GET', 'HEAD'].includes(request.method)) return new Response('Not found', { status: 404 });
        const bytes = Uint8Array.from(atob(asset.body), char => char.charCodeAt(0));
        return new Response(request.method === 'HEAD' ? null : bytes, { headers: {
          'Content-Type': asset.type,
          'Cache-Control': 'no-store',
          'X-Content-Type-Options': 'nosniff',
          'Referrer-Policy': 'same-origin',
        } });
      }
      // Identity belongs to Sites dispatch, which MUST strip/overwrite caller
      // identity headers. A direct Worker invocation is not an authenticated
      // internet boundary. Public dispatch HTTP/WSS sanitization is a release
      // gate; never deploy this Worker through an untrusted forwarding proxy.
      const account = request.headers.get('oai-authenticated-user-id');
      const signedIn = Boolean(account && account.trim() && account.length <= 256);
      if (url.pathname === '/api/access') {
        if (request.method !== 'GET' || request.headers.get('Upgrade')) return failure(405, 'Use a normal access-status request.');
        const origin = request.headers.get('Origin');
        if (origin && origin !== url.origin) return failure(403, 'Use the game site.');
        return Response.json({ signedIn }, { headers: { 'Cache-Control': 'no-store',
          'X-Content-Type-Options': 'nosniff' } });
      }
      // Supplied by Sites' authenticated access layer, never by app JavaScript.
      // Keep the audience owner-private; this check does not replace its policy.
      if (!signedIn) {
        return failure(401, 'Sign in with ChatGPT to play.');
      }
      const upgrade = request.headers.get('Upgrade')?.toLowerCase() === 'websocket';
      const permitted = (request.method === 'GET' && ['/api/health', '/api/capabilities'].includes(url.pathname))
        || (request.method === 'POST' && (url.pathname === '/api/missions' || mission.test(url.pathname)))
        || (request.method === 'GET' && upgrade && websocket.test(url.pathname));
      if (!permitted) return failure(404, 'Unknown mission endpoint.');
      // Block foreign browser origins before attaching the private upstream key.
      const origin = request.headers.get('Origin');
      if ((origin && origin !== url.origin) || (upgrade && origin !== url.origin)) {
        return failure(403, 'Use the mission site to access this playtest.');
      }
      let upstream;
      try {
        upstream = new URL(env.CONSENSUS_BACKEND_ORIGIN);
        if (upstream.protocol !== 'https:' || upstream.username || upstream.password
            || upstream.pathname !== '/' || upstream.search || upstream.hash
            || !env.CONSENSUS_GATEWAY_KEY || env.CONSENSUS_GATEWAY_KEY.length < 32) throw new Error();
      } catch { return failure(503, 'Mission server is not configured.'); }
      upstream.pathname = url.pathname;
      // No API needs query parameters; do not forward secrets or visitor URLs.
      const headers = new Headers();
      for (const name of ['Content-Type', 'Accept', 'X-Mission-Session', 'Upgrade',
        'Connection', 'Sec-WebSocket-Key', 'Sec-WebSocket-Version', 'Sec-WebSocket-Protocol']) {
        const value = request.headers.get(name);
        if (value !== null) headers.set(name, value);
      }
      if (origin) headers.set('Origin', origin);
      headers.set('X-Consensus-Gateway-Key', env.CONSENSUS_GATEWAY_KEY);
      // Sites supplies this identity after authentication. Never forward a
      // visitor-selected proxy identity or IP header. HMAC prevents exporting
      // the raw account ID and scopes identifiers to this gateway secret.
      const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(env.CONSENSUS_GATEWAY_KEY),
        { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
      const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode('visitor:' + account));
      headers.set('X-Consensus-Visitor', [...new Uint8Array(signature)].map(b => b.toString(16).padStart(2, '0')).join(''));
      let body;
      if (request.method === 'POST') {
        const length = request.headers.get('Content-Length');
        if (length !== null && (!/^\d{1,10}$/.test(length) || Number(length) > 4096)) {
          return failure(413, 'Request body too large.');
        }
        const reader = request.body?.getReader();
        if (reader) {
          const chunks = [];
          let size = 0;
          let timeout;
          try {
            await Promise.race([
              (async () => {
                while (true) {
                  const { value, done } = await reader.read();
                  if (done) break;
                  size += value.byteLength;
                  if (size > 4096) throw new RangeError();
                  chunks.push(value);
                }
              })(),
              new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error()), 5000); }),
            ]);
            body = new Uint8Array(size);
            let offset = 0;
            for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
          } catch (error) {
            void reader.cancel().catch(() => {});
            return failure(error instanceof RangeError ? 413 : 408, 'Request body too large or timed out.');
          } finally { clearTimeout(timeout); }
        }
      }
      try {
        const response = await upstreamFetch(upstream.href, {
          method: request.method, headers, redirect: 'manual',
          body,
        });
        // Preserve the runtime's WebSocket object by returning the 101 unchanged.
        if (response.status === 101) return response;
        if (response.status >= 300 && response.status < 400) return failure(502, 'Mission server redirected unexpectedly.');
        const output = new Headers({ 'Cache-Control': 'no-store' });
        if (response.headers.has('Retry-After')) output.set('Retry-After', response.headers.get('Retry-After'));
        output.set('Content-Type', response.headers.get('Content-Type') || 'application/json');
        return new Response(response.body, { status: response.status, headers: output });
      } catch { return failure(502, 'Mission server is temporarily unavailable. Reconnect to retry.'); }
    },
  };
}
