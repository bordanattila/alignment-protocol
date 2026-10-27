import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MissionConnection } from '../src/missionConnection';
import { restoreSession, saveSession } from '../src/session';
import type { LobbyState } from '../src/types';

class Socket {
  readyState = 0;
  onopen: any; onmessage: any; onerror: any; onclose: any;
  sent: any[] = [];
  close() { this.readyState = 3; }
  send(text: string) { if (this.readyState !== 1) throw Error('closed'); this.sent.push(JSON.parse(text)); }
  open() { this.readyState = 1; this.onopen?.({}); }
  message(mission: LobbyState) { this.onmessage?.({data:JSON.stringify({type:'state',mission})}); }
  fail() { this.onerror?.({}); } // Actual regression: error with no close event.
  disconnect(code = 1006) { this.readyState = 3; this.onclose?.({code}); }
}
function fixture() {
  let now=0, id=0;
  const timers=new Map<number,{at:number;callback:()=>void}>();
  const sockets: Socket[]=[]; const statuses: string[]=[]; const frames: LobbyState[]=[];
  const errors: string[]=[];
  let constructFailures=0;
  const runtime={
    socket: () => { if (constructFailures-- > 0) throw Error('constructor'); const socket=new Socket(); sockets.push(socket); return socket as unknown as WebSocket; },
    later: (callback:()=>void,delay:number) => { timers.set(++id,{at:now+delay,callback}); return id as any; },
    cancel: (timer:any) => {timers.delete(timer);}, random:()=>0.5,
  };
  const connection=new MissionConnection({token:'mission',credential:'saved-secret'},'ws://example/api/missions/mission/ws',{
    status:value=>statuses.push(value),snapshot:value=>frames.push(value),error:value=>errors.push(value),
  },runtime);
  const next=()=>{
    const [key,timer]=[...timers].sort((a,b)=>a[1].at-b[1].at)[0];
    timers.delete(key);now=timer.at;timer.callback();
  };
  return {connection,sockets,statuses,frames,errors,timers,next,runtime,
    get now(){return now;}, failConstruction(){constructFailures=1;}};
}
const snapshot=(revision:number,extra:Partial<LobbyState>={})=>({token:'mission',revision,phase:'discussion',chat:[],voting:null,...extra} as LobbyState);
function ready(f:ReturnType<typeof fixture>,revision=1){const socket=f.sockets.at(-1)!;socket.open();socket.message(snapshot(revision));return socket;}

test('OPEN authenticates with the saved credential but gameplay waits for snapshot',()=>{
  const f=fixture();f.connection.start();const socket=f.sockets[0];socket.open();
  assert.deepEqual(socket.sent,[{type:'authenticate',credential:'saved-secret'}]);
  assert.equal(f.connection.send({type:'chat',text:'stale'}),false);
  assert.ok(!f.statuses.includes('Connected'));
  socket.message(snapshot(1));assert.equal(f.statuses.at(-1),'Connected');assert.equal(f.timers.size,0);
  assert.equal(f.connection.send({type:'chat',text:'valid'}),true);
});
test('unexpected close retries and fresh snapshot restores connectivity',()=>{
  const f=fixture();f.connection.start();ready(f).disconnect();
  assert.equal(f.statuses.at(-1),'Connection lost — reconnecting');
  assert.equal(f.connection.send({type:'chat',text:'offline'}),false);
  f.next();ready(f,2);assert.equal(f.statuses.at(-1),'Reconnected');assert.equal(f.timers.size,0);
});
test('regression: initial error without close retires CONNECTING and schedules retry',()=>{
  const f=fixture();f.connection.start();f.sockets[0].fail();
  assert.equal(f.sockets[0].readyState,3);assert.equal(f.timers.size,1);
  f.next();ready(f);assert.equal(f.sockets.length,2);assert.equal(f.statuses.at(-1),'Reconnected');
});
test('silent CONNECTING and OPEN without authentication snapshot both time out',()=>{
  for(const open of [false,true]){
    const f=fixture();f.connection.start();if(open)f.sockets[0].open();
    f.next();assert.equal(f.now,15000);assert.equal(f.sockets[0].readyState,3);
    f.next();ready(f);assert.equal(f.statuses.at(-1),'Reconnected');
  }
});
test('repeated failures continue with bounded exponential jitter then succeed',()=>{
  const f=fixture();f.connection.start();const delays=[];
  for(let i=0;i<10;i++){f.sockets.at(-1)!.fail();const before=f.now;f.next();delays.push(f.now-before);}
  assert.deepEqual(delays.slice(0,5),[750,1500,3000,6000,7500]);
  assert.ok(delays.every(d=>d<=10000));assert.ok(f.statuses.includes('Connection unavailable — continuing to retry'));
  ready(f);assert.equal(f.timers.size,0);
});
test('constructor failure retries instead of escaping React effect',()=>{
  const f=fixture();f.failConstruction();f.connection.start();assert.equal(f.sockets.length,0);f.next();ready(f);
});
test('obsolete close/error/open/message callbacks cannot affect the new socket',()=>{
  const f=fixture();f.connection.start();const old=f.sockets[0];
  const callbacks={open:old.onopen,message:old.onmessage,error:old.onerror,close:old.onclose};
  old.fail();f.next();ready(f,5);const count=f.frames.length;
  callbacks.open();callbacks.error();callbacks.close({code:1008});callbacks.message({data:JSON.stringify({type:'state',mission:snapshot(100)})});
  assert.equal(f.frames.length,count);assert.equal(f.statuses.at(-1),'Reconnected');assert.equal(f.timers.size,0);
});
test('one error followed by close cannot schedule duplicate connections',()=>{
  const f=fixture();f.connection.start();const socket=f.sockets[0];const close=socket.onclose;
  socket.fail();close({code:1006});f.connection.start();assert.equal(f.timers.size,1);f.next();
  assert.equal(f.sockets.filter(s=>s.readyState!==3).length,1);assert.equal(f.sockets.length,2);
});
test('intentional leave cancels retry, watchdog, and late callbacks',()=>{
  for(const retrying of [false,true]){
    const f=fixture();f.connection.start();const late=f.sockets[0].onerror;if(retrying)f.sockets[0].fail();
    f.connection.stop();late();assert.equal(f.timers.size,0);assert.equal(f.sockets.length,1);
    assert.equal(f.connection.send({type:'chat',text:'no'}),false);
  }
});
test('1008 invalid/unavailable session stops retry and preserves credential',()=>{
  const f=fixture();f.connection.start();f.sockets[0].open();f.sockets[0].disconnect(1008);
  assert.equal(f.statuses.at(-1),'Session no longer recoverable');assert.equal(f.timers.size,0);
  assert.equal(f.sockets[0].sent[0].credential,'saved-secret');
});
test('revision order remains monotonic across sockets and duplicate snapshots ignored',()=>{
  const f=fixture();f.connection.start();ready(f,10).disconnect();f.next();f.sockets[1].open();
  f.sockets[1].message(snapshot(9));f.sockets[1].message(snapshot(10));assert.equal(f.frames.length,1);
  assert.equal(f.connection.send({type:'chat',text:'unrestored'}),false);
  f.sockets[1].message(snapshot(11));f.sockets[1].message(snapshot(11));assert.deepEqual(f.frames.map(s=>s.revision),[10,11]);
});
test('reconnect restores full chat and your saved vote without replaying intents',()=>{
  const f=fixture();f.connection.start();const socket=ready(f);
  f.connection.send({type:'vote',round_id:'round',choice_id:'B'});socket.disconnect();f.next();
  const restored=snapshot(2,{chat:[{id:'new',sender_id:'peer',callsign:'Peer',text:'While away',timestamp:1}],voting:{round_id:'round',number:1,eligible_count:3,submitted_count:2,your_vote:'B'},deadline:123});
  f.sockets[1].open();f.sockets[1].message(restored);assert.deepEqual(f.frames.at(-1),restored);
  assert.deepEqual(f.sockets[1].sent,[{type:'authenticate',credential:'saved-secret'}]);
});
test('terminal post-game snapshot and review recover on the same connection loop',()=>{
  const f=fixture();f.connection.start();ready(f,3).disconnect();f.next();f.sockets[1].open();
  const terminal=snapshot(4,{phase:'completed',summary:{outcome:'victory',consensus_score:70} as any,history:[]});
  f.sockets[1].message(terminal);assert.deepEqual(f.frames.at(-1),terminal);assert.equal(f.statuses.at(-1),'Reconnected');
});
test('malformed frame retries without applying an event; wrong mission snapshot is ignored',()=>{
  const f=fixture();f.connection.start();f.sockets[0].open();f.sockets[0].message(snapshot(1,{token:'other'}));assert.equal(f.frames.length,0);
  f.sockets[0].onmessage({data:'not json'});assert.equal(f.timers.size,1);
});
test('browser session storage retains the original reconnect credential',()=>{
  const entries=new Map<string,string>();
  Object.assign(globalThis,{localStorage:{getItem:(k:string)=>entries.get(k)??null,setItem:(k:string,v:string)=>entries.set(k,v)}});
  const session={token:'mission',credential:'saved-secret'};saveSession(session);
  const f=fixture();f.connection.start();ready(f).disconnect();f.next();ready(f,2);f.connection.stop();
  assert.deepEqual(restoreSession('mission'),session);assert.equal(entries.size,1);
});
test('synchronous send failure disables actions and retries without resending',()=>{
  const f=fixture();f.connection.start();const socket=ready(f);socket.send=()=>{throw Error('transport');};
  assert.equal(f.connection.send({type:'chat',text:'uncertain'}),false);f.next();ready(f,2);
  assert.equal(f.sockets[1].sent.length,1);
});
