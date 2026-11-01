import test from 'node:test';
import assert from 'node:assert/strict';
import { createWorker } from './worker.mjs';

const origin = 'https://private-site.example';
const env = { CONSENSUS_BACKEND_ORIGIN: 'https://backend.example', CONSENSUS_GATEWAY_KEY: 'test-only-' + 'x'.repeat(32), CONSENSUS_ADMISSION_MODE:'public' };
const request = (path, options = {}) => {
  const headers = new Headers(options.headers);
  headers.set('oai-authenticated-user-id', 'authorized-test-visitor');
  return new Request(origin + path, { ...options, headers });
};

test('admission fails closed for missing, invalid, closed, canary and expired settings without any upstream call',async()=>{
  const worker=createWorker({},()=>assert.fail('Closed admission reached backend'));
  for(const mode of [undefined,'closed','false','canary']) {
    const configured={...env,CONSENSUS_ADMISSION_MODE:mode};
    assert.equal((await worker.fetch(request('/api/missions',{method:'POST',body:'{}'}),configured)).status,503);
    assert.equal((await worker.fetch(request('/api/missions/token/ws',{headers:{Upgrade:'websocket',Origin:origin}}),configured)).status,503);
    assert.deepEqual(await (await worker.fetch(request('/api/access'),configured)).json(),{signedIn:true});
  }
  assert.equal((await worker.fetch(request('/api/release-probe'),{...env,CONSENSUS_ADMISSION_MODE:'canary',CONSENSUS_SECURITY_CANARY_UNTIL:String(Date.now()-1)})).status,404);
});

test('canary is time-limited, logs only scoped operator fingerprints and never sends a game request',async()=>{
  const worker=createWorker({},()=>assert.fail('Canary reached backend'));
  const configured={...env,CONSENSUS_ADMISSION_MODE:'canary',CONSENSUS_SECURITY_CANARY_UNTIL:String(Date.now()+600000)};
  const entries=[];const log=console.log;console.log=value=>entries.push(JSON.parse(value));
  try {
    const anon=await worker.fetch(new Request(origin+'/api/release-probe?case=a-http-base'),configured);
    assert.equal(anon.status,401);
    for(const [path,headers] of [['/api/release-probe?case=a-http-base',{}],
      ['/api/release-probe/ws?case=a-ws-base',{Upgrade:'websocket',Origin:origin}]]) {
      const r=await worker.fetch(request(path,{headers}),configured);assert.equal(r.status,503);
      const body=await r.text();assert.ok(!body.includes('authorized-test-visitor')&&!body.includes('fingerprint'));
    }
    assert.equal(entries[0].idFingerprint,null);
    assert.equal(entries[1].idFingerprint,entries[2].idFingerprint);
    assert.match(entries[1].idFingerprint,/^[a-f0-9]{64}$/);
    assert.ok(!JSON.stringify(entries).includes(env.CONSENSUS_GATEWAY_KEY));
    assert.equal((await worker.fetch(request('/api/release-probe?case=a-ws-base',{headers:{Upgrade:'websocket',Origin:'https://foreign.example'}}),configured)).status,403);
    assert.equal((await worker.fetch(request('/api/release-probe?case=arbitrary-untrusted-log-value'),configured)).status,400);
    assert.equal(entries.length,3);
  } finally {console.log=log;}
});

test('access status is relay-local, no-store and boolean only, including anonymous visitors', async () => {
  const worker = createWorker({}, () => assert.fail('Access status must not reach Render'));
  for (const [headers, expected] of [[{}, false], [{'oai-authenticated-user-email':'display@example.test'}, false],
    [{'oai-authenticated-user-id':'site-scoped-fixture'},true], [{'oai-authenticated-user-id':'x'.repeat(257)},false]]) {
    const response=await worker.fetch(new Request(origin+'/api/access?identity=ignored',{headers}),{});
    assert.equal(response.status,200);
    assert.equal(response.headers.get('Cache-Control'),'no-store');
    assert.deepEqual(await response.json(),{signedIn:expected});
  }
  assert.equal((await worker.fetch(request('/api/access',{method:'POST'}),env)).status,405);
  assert.equal((await worker.fetch(request('/api/access',{headers:{Upgrade:'websocket'}}),env)).status,405);
  assert.equal((await worker.fetch(request('/api/access',{headers:{Origin:'https://foreign.example'}}),env)).status,403);
});

test('fixture dispatch strips caller identity before injecting its authenticated context (not hosted-dispatch proof)', async () => {
  const seen=[];
  const worker=createWorker({},async (_url,options)=>{seen.push(options.headers);return Response.json({});});
  const dispatch=async (identity,options={})=>{
    const headers=new Headers(options.headers);
    for(const name of ['oai-authenticated-user-id','oai-authenticated-user-email','oai-authenticated-user-full-name'])headers.delete(name);
    if(identity)headers.set('oai-authenticated-user-id',identity);
    return worker.fetch(new Request(origin+'/api/capabilities',{...options,headers}),env);
  };
  const spoof={headers:{'oai-authenticated-user-id':'victim','oai-authenticated-user-email':'victim@example.test',
    'X-Consensus-Visitor':'b'.repeat(64),'X-Forwarded-For':'spoofed'}};
  assert.equal((await dispatch(null,spoof)).status,401);assert.equal(seen.length,0);
  assert.equal((await dispatch('real-account',spoof)).status,200);
  assert.equal((await dispatch('real-account')).status,200);
  assert.equal(seen[0].get('X-Consensus-Visitor'),seen[1].get('X-Consensus-Visitor'));
  for(const name of ['oai-authenticated-user-id','oai-authenticated-user-email','X-Forwarded-For'])assert.equal(seen[0].get(name),null);
});

test('anonymous create, join and WSS all fail before upstream; auth paths remain dispatch-owned', async()=>{
  const worker=createWorker({},()=>assert.fail());
  for(const path of ['/api/missions','/api/missions/invite/join']) {
    assert.equal((await worker.fetch(new Request(origin+path,{method:'POST',body:'{}'}),env)).status,401);
  }
  assert.equal((await worker.fetch(new Request(origin+'/api/missions/invite/ws',{headers:{Upgrade:'websocket',Origin:origin}}),env)).status,401);
  for(const path of ['/signin-with-chatgpt','/signout-with-chatgpt','/callback']) {
    assert.equal((await worker.fetch(new Request(origin+path),env)).status,404); // Hosting dispatch intercepts these before the Worker.
  }
});

test('serves the retained frontend assets, including HEAD, without backend calls', async () => {
  const worker = createWorker({ '/': { body: btoa('<h1>Consensus Engine</h1>'), type: 'text/html' } }, () => assert.fail());
  assert.equal(await (await worker.fetch(request('/?mission=invite'), {})).text(), '<h1>Consensus Engine</h1>');
  assert.equal(await (await worker.fetch(request('/', { method: 'HEAD' }), {})).text(), '');
  assert.equal((await worker.fetch(request('/missing'), {})).status, 404);
});

test('forwards intents and credentials only to the configured backend, without visitor cookies or identity headers', async () => {
  const worker = createWorker({}, async (url, options) => {
    assert.equal(url, 'https://backend.example/api/missions');
    assert.equal(options.headers.get('X-Consensus-Gateway-Key'), env.CONSENSUS_GATEWAY_KEY);
    assert.equal(options.headers.get('Origin'), origin);
    assert.equal(options.headers.get('X-Mission-Session'), 'seat-secret');
    for (const name of ['Cookie', 'Authorization', 'oai-authenticated-user-id']) assert.equal(options.headers.get(name), null);
    assert.equal(options.redirect, 'manual');
    assert.deepEqual(await new Response(options.body).json(), { callsign: 'Host', mode: 'authored' });
    return Response.json({ token: 'invite', credential: 'seat-secret' }, {
      status: 201, headers: { 'Set-Cookie': 'upstream-cookie', 'X-Internal': 'private' },
    });
  });
  const result = await worker.fetch(request('/api/missions?key=never-forward', {
    method: 'POST', headers: { Origin: origin, Cookie: 'sites-session', Authorization: 'private',
      'oai-authenticated-user-id': 'visitor', 'Content-Type': 'application/json', 'X-Mission-Session': 'seat-secret' },
    body: JSON.stringify({ callsign: 'Host', mode: 'authored' }),
  }), env);
  assert.equal(result.status, 201);
  assert.equal(result.headers.get('Cache-Control'), 'no-store');
  assert.equal(result.headers.get('Set-Cookie'), null);
  assert.equal(result.headers.get('X-Internal'), null);
  assert.equal((await result.json()).credential, 'seat-secret');
});

test('rejects cross-origin requests and unconfigured or unsafe upstreams without contacting backend', async () => {
  const worker = createWorker({}, () => assert.fail());
  assert.equal((await worker.fetch(new Request(origin + '/api/capabilities'), env)).status, 401);
  assert.equal((await worker.fetch(request('/api/missions', { method: 'POST', headers: { Origin: 'https://other.example' } }), env)).status, 403);
  assert.equal((await worker.fetch(request('/api/capabilities'), {})).status, 503);
  for (const upstream of ['http://backend.example', 'https://user:pass@backend.example', 'https://backend.example/path', 'https://backend.example?key=x']) {
    assert.equal((await worker.fetch(request('/api/capabilities'), { ...env, CONSENSUS_BACKEND_ORIGIN: upstream })).status, 503);
  }
  assert.equal((await worker.fetch(request('/api/unknown'), env)).status, 404);
  assert.equal((await worker.fetch(request('/api/missions/token/ws'), env)).status, 404);
});

test('passes the runtime WebSocket upgrade response through unchanged', async () => {
  // Node cannot construct status 101: this sentinel checks object identity.
  // Cloudflare/Sites hosted upgrade behavior still needs remote verification.
  const upgrade = { status: 101, webSocket: {} };
  const worker = createWorker({}, async (url, options) => {
    assert.equal(url, 'https://backend.example/api/missions/token/ws');
    assert.equal(options.headers.get('Upgrade'), 'websocket');
    return upgrade;
  });
  const result = await worker.fetch(request('/api/missions/token/ws', {
    headers: { Upgrade: 'websocket', Origin: origin },
  }), env);
  assert.equal(result, upgrade);
  assert.equal((await worker.fetch(request('/api/missions/token/ws', { headers: { Upgrade: 'websocket' } }), env)).status, 403);
});

test('does not follow backend redirects and returns sanitized connection errors', async () => {
  const redirected = createWorker({}, async () => new Response(null, { status: 307, headers: { Location: 'https://other.example' } }));
  assert.equal((await redirected.fetch(request('/api/capabilities'), env)).status, 502);
  const failed = createWorker({}, async () => { throw new Error(env.CONSENSUS_GATEWAY_KEY); });
  const result = await failed.fetch(request('/api/capabilities'), env);
  assert.equal(result.status, 502);
  assert.ok(!(await result.text()).includes(env.CONSENSUS_GATEWAY_KEY));
});

test('gateway visitor identity is stable per account, differs across accounts, and ignores spoofed forwarding headers', async () => {
  const seen = [];
  const worker = createWorker({}, async (_url, options) => {
    seen.push(options.headers.get('X-Consensus-Visitor'));
    for (const name of ['X-Forwarded-For', 'X-Real-IP', 'Forwarded', 'oai-authenticated-user-id']) {
      assert.equal(options.headers.get(name), null);
    }
    return Response.json({ generated_missions: false });
  });
  for (const ip of ['first', 'second']) {
    await worker.fetch(request('/api/capabilities', { headers: { 'X-Consensus-Visitor': 'spoofed', 'X-Forwarded-For': ip } }), env);
  }
  const other = new Request(origin + '/api/capabilities', { headers: { 'oai-authenticated-user-id': 'different-account' } });
  await worker.fetch(other, env);
  assert.match(seen[0], /^[a-f0-9]{64}$/);
  assert.equal(seen[0], seen[1]);
  assert.notEqual(seen[0], seen[2]);
  assert.ok(!seen[0].includes('authorized-test-visitor'));
});

test('relay rejects declared and streamed oversize bodies in bytes without contacting backend', async () => {
  const worker = createWorker({}, () => assert.fail());
  for (const body of ['x'.repeat(4097), '\u00e9'.repeat(2049)]) {
    assert.equal((await worker.fetch(request('/api/missions', { method: 'POST', body }), env)).status, 413);
  }
  assert.equal((await worker.fetch(request('/api/missions', { method: 'POST', headers: { 'Content-Length': '999999999' } }), env)).status, 413);
});

test('relay preserves sanitized retry guidance for backend rate limiting', async () => {
  const worker = createWorker({}, async () => Response.json({ code: 'rate_limited' }, {
    status: 429, headers: { 'Retry-After': '15' },
  }));
  const response = await worker.fetch(request('/api/capabilities'), env);
  assert.equal(response.status, 429);
  assert.equal(response.headers.get('Retry-After'), '15');
});

test('dual diagnostics separate emails despite a shared ID; both transports resist spoofing under a modeled sanitizing dispatch ONLY', async () => {
  const worker=createWorker({},()=>assert.fail('Diagnostic must not reach Render'));
  const configured={...env,CONSENSUS_ADMISSION_MODE:'canary',CONSENSUS_SECURITY_CANARY_UNTIL:String(Date.now()+300000)};
  const attacks=[[],[['oai-authenticated-user-id','forged-id']],
    [['oai-authenticated-user-email','forged@invalid.test'],['oai-authenticated-user-full-name','Forged']],
    [['oai-authenticated-user-email','first@invalid.test'],['oai-authenticated-user-email','second@invalid.test']],
    [['OaI-AuThEnTiCaTeD-UsEr-EmAiL','first@invalid.test'],['oai-authenticated-user-email','second@invalid.test']],
    [['X-Consensus-Visitor','f'.repeat(64)],['X-Consensus-Gateway-Key','forged'],['Forwarded','for=192.0.2.1']]];
  const entries=[];const log=console.log;console.log=value=>entries.push(JSON.parse(value));
  try {
    const groups={a:[],b:[]};let authenticated=0,anonymous=0;
    for(const who of ['a','b',null])for(const transport of ['http','ws'])for(const attack of attacks) {
      const headers=new Headers(attack);headers.set('Origin',origin);if(transport==='ws')headers.set('Upgrade','websocket');
      // This is a deliberately modeled contract, NOT evidence about Sites.
      for(const name of [...headers.keys()])if(name.startsWith('oai-authenticated-user-'))headers.delete(name);
      if(who){headers.set('oai-authenticated-user-id','shared-workspace-fixture');headers.set('oai-authenticated-user-email',who+'@example.test');}
      const response=await worker.fetch(new Request(origin+'/api/release-probe'+(transport==='ws'?'/ws':'')+'?case='+(who||'a')+'-'+transport+'-base',{headers}),configured);
      assert.equal(response.status,who?503:401);assert.equal(response.headers.get('Cache-Control'),'no-store');
      const body=await response.text();assert.ok(!body.includes('@')&&!body.includes('Fingerprint')&&!body.includes(env.CONSENSUS_GATEWAY_KEY));
      const event=entries.at(-1);assert.equal(event.diagnosticVersion,2);assert.equal(event.transport,transport);
      assert.equal(event.idPresent,Boolean(who));assert.equal(event.emailValid,Boolean(who));
      if(who){groups[who].push(event);authenticated++;}else{assert.equal(event.idFingerprint,null);assert.equal(event.emailFingerprint,null);anonymous++;}
    }
    assert.equal(authenticated,24);assert.equal(anonymous,12);
    for(const group of Object.values(groups))for(const field of ['idFingerprint','emailFingerprint']) {
      assert.equal(new Set(group.map(x=>x[field])).size,1);assert.match(group[0][field],/^[a-f0-9]{64}$/);
    }
    assert.equal(groups.a[0].idFingerprint,groups.b[0].idFingerprint);
    assert.notEqual(groups.a[0].emailFingerprint,groups.b[0].emailFingerprint);
    const serialized=JSON.stringify(entries);
    for(const secret of ['shared-workspace-fixture','a@example.test','b@example.test',env.CONSENSUS_GATEWAY_KEY,'forged@invalid.test'])assert.ok(!serialized.includes(secret));
    // A new diagnostic window gets new pseudonyms; never compare across windows.
    await worker.fetch(request('/api/release-probe?case=a-http-base',{headers:{'oai-authenticated-user-email':'a@example.test'}}),{...configured,CONSENSUS_SECURITY_CANARY_UNTIL:String(Number(configured.CONSENSUS_SECURITY_CANARY_UNTIL)+1)});
    assert.notEqual(entries.at(-1).emailFingerprint,groups.a[0].emailFingerprint);
  } finally {console.log=log;}
});

test('diagnostic email validation rejects ambiguity; HMAC namespaces differ; unsanitized headers remain forgeable',async()=>{
  const worker=createWorker({},()=>assert.fail());
  const configured={...env,CONSENSUS_ADMISSION_MODE:'canary',CONSENSUS_SECURITY_CANARY_UNTIL:String(Date.now()+300000)};
  const entries=[];const log=console.log;console.log=value=>entries.push(JSON.parse(value));
  const probe=async headers=>worker.fetch(new Request(origin+'/api/release-probe?case=a-http-base',{headers}),configured);
  try {
    for(const email of ['', 'not-an-email','a@example.test,b@example.test','a @example.test','a@example..test','a@-example.test','.a@example.test','a.@example.test','a'.repeat(65)+'@example.test','a@'+'b'.repeat(64)+'.test']) {
      assert.equal((await probe({'oai-authenticated-user-email':email})).status,401);assert.equal(entries.at(-1).emailFingerprint,null);
    }
    for(const secondName of ['oai-authenticated-user-email','OaI-AuThEnTiCaTeD-UsEr-EmAiL']) {
      const headers=new Headers();headers.append('oai-authenticated-user-email','a@example.test');headers.append(secondName,'b@example.test');
      assert.equal((await probe(headers)).status,401);assert.equal(entries.at(-1).emailValid,false);
    }
    // Domain normalization is stable; local-part case/aliases are not collapsed.
    await probe({'oai-authenticated-user-email':'A@EXAMPLE.TEST'});const first=entries.at(-1).emailFingerprint;
    await probe({'oai-authenticated-user-email':'A@example.test'});assert.equal(entries.at(-1).emailFingerprint,first);
    await probe({'oai-authenticated-user-email':'a@example.test'});assert.notEqual(entries.at(-1).emailFingerprint,first);
    await probe({'oai-authenticated-user-id':'a@example.test','oai-authenticated-user-email':'a@example.test'});
    assert.notEqual(entries.at(-1).idFingerprint,entries.at(-1).emailFingerprint);
    // Negative control: direct invocation with caller email produces a pseudonym.
    // HMAC does not authenticate the input. Dispatch sanitization is indispensable.
    assert.equal((await probe({'oai-authenticated-user-email':'forged@example.test'})).status,503);
    assert.equal(entries.at(-1).emailValid,true);
    // Diagnostics do not silently change access-status or gameplay authorization.
    const onlyEmail=new Request(origin+'/api/access',{headers:{'oai-authenticated-user-email':'a@example.test'}});
    assert.deepEqual(await (await worker.fetch(onlyEmail,env)).json(),{signedIn:false});
    assert.equal((await worker.fetch(new Request(origin+'/api/capabilities',{headers:{'oai-authenticated-user-email':'a@example.test'}}),env)).status,401);
    assert.equal((await worker.fetch(request('/api/missions',{method:'POST',body:'{}'}),configured)).status,503);
    assert.equal((await worker.fetch(request('/api/missions/token/ws',{headers:{Upgrade:'websocket',Origin:origin}}),configured)).status,503);
  } finally {console.log=log;}
});
