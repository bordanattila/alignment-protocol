// Real processes/network and production client controller; not a browser test.
// Run: node --experimental-websocket frontend/tests/smokeReconnection.mjs
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtemp, writeFile, rename, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { createServer } from 'vite';
const root=fileURLToPath(new URL('../../',import.meta.url));
const directory=await mkdtemp(tmpdir()+'/ce-7-2-network-');
const base='http://127.0.0.1:18772';
let backend, proxy;
const clients=[];
let clock=1700000000;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(predicate,label,timeout=20000){
  const end=Date.now()+timeout;
  while(Date.now()<end){if(await predicate())return;await pause(30);}
  throw Error('Timeout: '+label);
}
async function setClock(value){clock=value;await writeFile(directory+'/clock.new',String(clock));await rename(directory+'/clock.new',directory+'/clock');}
async function start(){
  backend=spawn(root+'.venv/bin/python',['-c',
    "from app.main import create_app; from pathlib import Path; import sys,uvicorn; p=Path(sys.argv[2]); uvicorn.run(create_app(clock=lambda:float(p.read_text()),database_path=sys.argv[1]),host='127.0.0.1',port=18772,log_level='warning')",
    directory+'/missions.sqlite3',directory+'/clock'],{cwd:root+'backend',stdio:'ignore'});
  await until(async()=>{if(backend.exitCode!==null)throw Error('Backend exited');try{return (await fetch(base+'/api/health')).ok;}catch{return false;}},'backend startup');
}
async function kill(){const process=backend;if(!process||process.exitCode!==null)return;const exited=new Promise(resolve=>process.once('exit',resolve));process.kill('SIGKILL');await exited;}
async function post(path,body,credential){
  const response=await fetch(base+path,{method:'POST',headers:{'content-type':'application/json',...(credential?{'X-Mission-Session':credential}:{})},body:body===undefined?undefined:JSON.stringify(body)});
  assert.ok(response.ok,'HTTP '+response.status);return response.json();
}
function all(predicate){return clients.every(c=>c.state&&predicate(c.state));}
async function synced(predicate,label){await until(()=>all(predicate),label);}
try{
  await setClock(clock);
  await build({entryPoints:[root+'frontend/src/missionConnection.ts'],bundle:true,platform:'node',format:'esm',outfile:directory+'/connection.mjs'});
  const {MissionConnection}=await import(pathToFileURL(directory+'/connection.mjs'));
  // Match the shipped development ws proxy while keeping user ports/data alone.
  proxy=await createServer({configFile:false,root:root+'frontend',server:{host:'127.0.0.1',port:18773,strictPort:true,proxy:{'/api':{target:base,ws:true}}},logLevel:'silent'});await proxy.listen();
  await start();
  const host=await post('/api/missions',{callsign:'Network Host'});
  const sessions=[host];for(let i=1;i<3;i++)sessions.push(await post(`/api/missions/${host.token}/join`,{callsign:'Network '+i}));
  for(const session of sessions){
    const client={state:null,status:'Connecting',blocked:false,socket:null,revisions:[],errors:[],sends:[],credential:session.credential};
    client.connection=new MissionConnection(session,`ws://127.0.0.1:18773/api/missions/${host.token}/ws`,{
      status:s=>client.status=s,error:e=>client.errors.push(e),snapshot:s=>{client.state=s;client.revisions.push(s.revision);},
    },{socket:url=>{
      if(client.blocked)throw Error('Isolated client offline');
      const socket=new WebSocket(url);client.socket=socket;
      const send=socket.send.bind(socket);socket.send=text=>{client.sends.push(JSON.parse(text));send(text);};return socket;
    },later:(f,ms)=>setTimeout(f,ms),cancel:clearTimeout,random:()=>0});
    clients.push(client);client.connection.start();
  }
  const action=async(name,body)=>post(`/api/missions/${host.token}/${name}`,body,host.credential);
  await synced(s=>s.players.every(p=>p.connected),'all three connected');
  await action('start');await synced(s=>s.phase==='briefing','start');
  const identities=clients.map(c=>({you:c.state.you,roles:c.state.roles,private:c.state.private_intelligence}));
  await action('discussion');await synced(s=>s.phase==='discussion','discussion');
  const a=clients[0];a.blocked=true;a.socket.close();
  await until(()=>a.status.includes('reconnecting'),'A detects interruption');
  await until(()=>clients.slice(1).every(c=>!c.state.players.find(p=>p.id===identities[0].you).connected),'B/C receive offline presence');
  assert.ok(clients[1].connection.send({type:'chat',text:'Intelligence while A offline'}));
  await until(()=>clients.slice(1).every(c=>c.state.chat.some(m=>m.text==='Intelligence while A offline')),'B/C live chat');
  await setClock(clients[1].state.deadline);
  await until(()=>clients.slice(1).every(c=>c.state.phase==='voting'),'B/C receive timer transition');
  assert.ok(clients[1].connection.send({type:'vote',round_id:clients[1].state.voting.round_id,choice_id:'B'}));
  await until(()=>clients[1].state.voting.submitted_count===1,'B vote');
  const deadline=clients[1].state.deadline;
  a.blocked=false;await synced(s=>s.phase==='voting'&&s.voting.submitted_count===1,'A automatically restores vote progress');
  assert.equal(a.state.deadline,deadline);assert.ok(a.state.chat.some(m=>m.text==='Intelligence while A offline'));
  assert.deepEqual(a.state.roles,identities[0].roles);assert.equal(a.state.you,identities[0].you);
  assert.deepEqual(a.state.private_intelligence,identities[0].private);
  assert.ok(a.connection.send({type:'vote',round_id:a.state.voting.round_id,choice_id:'B'}));
  await synced(s=>s.voting.submitted_count===2,'A vote accepted');
  a.blocked=true;a.socket.close();
  await until(()=>clients.slice(1).every(c=>!c.state.players.find(p=>p.id===identities[0].you).connected),'A disconnects after voting');
  assert.ok(clients[2].connection.send({type:'vote',round_id:clients[2].state.voting.round_id,choice_id:'B'}));
  await until(()=>clients.slice(1).every(c=>c.state.phase==='decision_locked'),'B/C resolve without duplicating A vote');
  a.blocked=false;
  await synced(s=>s.phase==='decision_locked','A restores Crisis 1 resolution');
  assert.ok(all(s=>s.history.length===1&&s.decision.totals.B===3));
  console.log('PASS individual interruption: B/C chat, timer transition and vote stay live; A automatically restores identity, roles, intelligence, chat and original deadline; exactly three votes');
  await action('continue',{result_id:a.state.result.id});await synced(s=>s.crisis_number===2&&s.phase==='briefing','Crisis 2');
  await action('discussion');await synced(s=>s.phase==='discussion','second discussion');
  assert.ok(clients[2].connection.send({type:'chat',text:'Saved before restart'}));
  await synced(s=>s.chat.some(m=>m.text==='Saved before restart'),'saved chat');
  const before=clients.map(c=>structuredClone(c.state));
  await kill();await until(()=>clients.every(c=>c.status.includes('reconnecting')||c.status.includes('continuing to retry')),'all clients detect backend loss');
  assert.ok(clients.every(c=>!c.connection.send({type:'chat',text:'Must not queue'})));
  await pause(4500);await start(); // Clients/controllers remain mounted throughout.
  await until(()=>clients.every(c=>c.status==='Reconnected'&&c.state.phase==='discussion'&&c.state.players.every(p=>p.connected)),'automatic restart recovery');
  for(let i=0;i<3;i++){
    const current=clients[i].state;for(const key of ['you','roles','private_intelligence','crisis','metrics','history','chat','deadline'])assert.deepEqual(current[key],before[i][key],key);
    assert.ok(clients[i].revisions.every((r,n,rows)=>n===0||r>rows[n-1]));
    assert.equal(clients[i].sends.filter(m=>m.type==='vote').length,1);
    assert.ok(!clients[i].sends.some(m=>m.text==='Must not queue'));
  }
  await setClock(a.state.deadline);await synced(s=>s.phase==='voting','post-restart voting');
  for(const client of clients){assert.ok(client.connection.send({type:'vote',round_id:client.state.voting.round_id,choice_id:'B'}));await pause(100);}
  await synced(s=>s.phase==='decision_locked'&&s.history.length===2,'second exactly-once resolution');
  const metrics=structuredClone(a.state.metrics),result=a.state.result.id;
  await action('continue',{result_id:result});await synced(s=>s.crisis_number===3,'continue after restart');await action('continue',{result_id:result});
  assert.ok(all(s=>s.history.length===2));assert.deepEqual(a.state.metrics,metrics);
  console.log('PASS restart: three held-open production controllers reconnect through Vite automatically without remount/refresh; identity, roles, private intelligence, crisis, metrics, history, chat and deadline retained; gameplay continues with exactly-once resolution');
  // Presence UX acceptance uses actual snapshots rendered by production React
  // components in Node. This verifies markup, not browser layout or a11y speech.
  await build({stdin:{contents:`import {renderToStaticMarkup} from 'react-dom/server';
    import {ConnectionNotice,PlayerPresence} from './src/MissionPresence';
    import {ConsequenceOutcome} from './src/ConsequenceOutcome';
    export const notice=(status,connected)=>renderToStaticMarkup(<ConnectionNotice status={status} connected={connected}/>);
    export const presence=(mission,connected)=>renderToStaticMarkup(<PlayerPresence mission={mission} connected={connected}/>);
    export const outcome=(mission)=>renderToStaticMarkup(<ConsequenceOutcome mission={mission} connected={true} continuing={false} onContinue={()=>{}}/>);`,
    loader:'tsx',resolveDir:root+'frontend'},jsx:'automatic',bundle:true,platform:'node',format:'cjs',outfile:directory+'/presence-ui.cjs'});
  const ui=createRequire(import.meta.url)(directory+'/presence-ui.cjs');
  await action('discussion');await synced(s=>s.phase==='discussion','presence discussion');
  await setClock(a.state.deadline);await synced(s=>s.phase==='voting','presence voting');
  const c=clients[2];const cIdentity={id:c.state.you,roles:c.state.roles};
  c.blocked=true;c.socket.close();
  await until(()=>clients.slice(0,2).every(peer=>!peer.state.players.find(p=>p.id===cIdentity.id).connected),'A/B see C disconnected');
  assert.ok(ui.notice(c.status,false).includes('Connection lost — reconnecting automatically.'));
  for(const peer of clients.slice(0,2)){
    const html=ui.presence(peer.state,true);
    assert.ok(html.includes('<strong>2 of 3</strong>'));
    assert.ok(html.includes('Network 2')&&html.includes('<strong>Disconnected</strong>'));
    assert.ok(peer.connection.send({type:'vote',round_id:peer.state.voting.round_id,choice_id:'B'}));
  }
  await until(()=>clients.slice(0,2).every(peer=>peer.state.voting.submitted_count===2),'two votes while C absent');
  const expiredRound=a.state.voting.round_id;
  await setClock(a.state.deadline);
  await until(()=>clients.slice(0,2).every(peer=>peer.state.phase==='decision_locked'),'vote expires with C absent');
  assert.equal(a.state.closed_rounds.at(-1).abstentions,1);
  assert.deepEqual(a.state.decision.totals,{A:0,B:2,C:0});
  const blocked=ui.outcome(a.state);
  assert.ok(blocked.includes('Waiting for Network 2 to reconnect before continuing. Players connected: 2 of 3.'));
  assert.match(blocked,/<button aria-describedby="continue-status" disabled="">Next crisis<\/button>/);
  const rejected=await fetch(base+`/api/missions/${host.token}/continue`,{method:'POST',headers:{'content-type':'application/json','X-Mission-Session':host.credential},body:JSON.stringify({result_id:a.state.result.id})});
  assert.equal(rejected.status,409);
  c.blocked=false;await synced(s=>s.phase==='decision_locked'&&s.players.every(p=>p.connected),'C restores presence after expiry');
  assert.equal(c.state.you,cIdentity.id);assert.deepEqual(c.state.roles,cIdentity.roles);
  assert.ok(!ui.notice(c.status,true).includes('Displayed mission state may be outdated'));
  assert.ok(ui.presence(a.state,true).includes('<strong>3 of 3</strong>'));
  assert.match(ui.outcome(a.state),/<button aria-describedby="continue-status">Next crisis<\/button>/);
  // An expired vote can never change the resolved result, even if sent manually.
  assert.ok(c.connection.send({type:'vote',round_id:expiredRound,choice_id:'C'}));
  await until(()=>c.errors.length>0,'expired vote rejected');
  assert.deepEqual(a.state.decision.totals,{A:0,B:2,C:0});
  await action('continue',{result_id:a.state.result.id});await synced(s=>s.crisis_number===4&&s.phase==='briefing','continue after C returns');
  console.log('PASS presence UX: real three-client snapshots show C disconnected, 2/3 connected and a local loss notice; deadline records one nonresponse; HTTP 409 and disabled Next crisis name C; reconnect clears warning, shows 3/3, enables Next crisis; stale vote rejected and Crisis 4 opens');
  console.log('NETWORK SMOKE PASS (Node WebSocket + server-rendered UI, not browser acceptance)');
} finally {
  for(const client of clients)client.connection.stop();
  await kill();await proxy?.close();await rm(directory,{recursive:true,force:true});
}
