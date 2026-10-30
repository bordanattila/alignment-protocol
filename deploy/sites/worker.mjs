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
      // Supplied by Sites' authenticated access layer, never by app JavaScript.
      // Keep the audience owner-private; this check does not replace its policy.
      if (!request.headers.get('oai-authenticated-user-id')) {
        return failure(401, 'Sign in to the private playtest site.');
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
      try {
        const response = await upstreamFetch(upstream.href, {
          method: request.method, headers, redirect: 'manual',
          body: request.method === 'POST' ? request.body : undefined,
        });
        // Preserve the runtime's WebSocket object by returning the 101 unchanged.
        if (response.status === 101) return response;
        if (response.status >= 300 && response.status < 400) return failure(502, 'Mission server redirected unexpectedly.');
        const output = new Headers({ 'Cache-Control': 'no-store' });
        output.set('Content-Type', response.headers.get('Content-Type') || 'application/json');
        return new Response(response.body, { status: response.status, headers: output });
      } catch { return failure(502, 'Mission server is temporarily unavailable. Reconnect to retry.'); }
    },
  };
}
