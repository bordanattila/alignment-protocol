// Scroll geometry is explicit here: Node/SSR has no layout engine. These tests
// exercise the production controller/handlers, not simulated browser layout.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { ChatScrollController, observeChatHistory } from '../src/chatScroll';
import { UnreadChatMessages } from '../src/Gameplay';
import type { LobbyState } from '../src/types';

const message = (n: number, sender_id = 'peer') => ({id:`m${n}`,sender_id,callsign:sender_id,text:`Message ${n}`,timestamp:n,crisis_number:n < 5 ? 1 : 2});
function setup(messages = [message(1)]) {
  const geometry = {scrollTop:0,scrollHeight:600,clientHeight:200};
  let unread=0;
  const controller = new ChatScrollController(geometry,'you',count => { unread=count; });
  controller.update(messages);
  return {geometry,controller,get unread() { return unread; }};
}
function readEarlier(view: ReturnType<typeof setup>) { view.geometry.scrollTop=100; view.controller.onScroll(); }

test('initial existing history starts at latest without historical unread messages', () => {
  const view=setup(Array.from({length:100},(_,i)=>message(i+1)));
  assert.equal(view.geometry.scrollTop,400); assert.equal(view.unread,0);
});
test('incoming messages auto-follow at bottom and within 40px fractional tolerance', () => {
  for (const distance of [0,39.5,40]) {
    const view=setup(); view.geometry.scrollTop=400-distance; view.controller.onScroll();
    view.geometry.scrollHeight=720; view.controller.update([message(1),message(2)]);
    assert.equal(view.geometry.scrollTop,520); assert.equal(view.unread,0);
  }
});
test('reading earlier preserves scroll position and counts batches and successive arrivals', () => {
  const view=setup(); readEarlier(view);
  view.geometry.scrollHeight=900; view.controller.update([message(1),message(2),message(3)]);
  assert.equal(view.geometry.scrollTop,100); assert.equal(view.unread,2);
  view.controller.update([message(1),message(2),message(3),message(4)]);
  assert.equal(view.geometry.scrollTop,100); assert.equal(view.unread,3);
});
test('jump to latest clears unread and resumes following without outer scrolling', () => {
  const view=setup(); readEarlier(view); view.controller.update([message(1),message(2)]);
  view.controller.jumpToLatest(); assert.equal(view.unread,0); assert.equal(view.geometry.scrollTop,400);
  view.geometry.scrollHeight=750; view.controller.update([message(1),message(2),message(3)]);
  assert.equal(view.geometry.scrollTop,550); assert.equal(view.unread,0);
});
test('manual return to bottom clears unread and resumes auto-follow', () => {
  const view=setup(); readEarlier(view); view.controller.update([message(1),message(2)]);
  view.geometry.scrollTop=399.5; view.controller.onScroll(); assert.equal(view.unread,0);
  view.geometry.scrollHeight=900; view.controller.update([message(1),message(2),message(3)]);
  assert.equal(view.geometry.scrollTop,700);
});
test('own authoritative message confirms send and follows; unconfirmed or rejected send does not', () => {
  const view=setup(); readEarlier(view); view.controller.update([message(1),message(2)]);
  // Local send success/failure does not touch this controller; an unchanged
  // server snapshot is deliberately insufficient confirmation.
  view.controller.update([message(1),message(2)]);
  assert.equal(view.unread,1); assert.equal(view.geometry.scrollTop,100);
  view.geometry.scrollHeight=800;
  view.controller.update([message(1),message(2),message(3,'you')]);
  assert.equal(view.unread,0); assert.equal(view.geometry.scrollTop,600);
});
test('duplicate snapshots, unrelated rerenders, reconnect replay and old backfill never double count', () => {
  const view=setup(); readEarlier(view);
  const messages=[message(1),message(2),message(3)]; view.controller.update(messages);
  for (let i=0;i<5;i++) view.controller.update(JSON.parse(JSON.stringify(messages)));
  view.controller.update([message(1)]); view.controller.update(messages);
  assert.equal(view.unread,2); assert.equal(view.geometry.scrollTop,100);
});
test('equal-timestamp messages use stable IDs, not just timestamps or array length', () => {
  const view=setup(); readEarlier(view);
  const next={...message(2),timestamp:1};
  view.controller.update([message(1),next]); view.controller.update([message(1),next]);
  assert.equal(view.unread,1);
});
test('bounded history rollover detects arrivals even with unchanged list length', () => {
  const initial=Array.from({length:100},(_,i)=>message(i+1));
  const view=setup(initial); readEarlier(view);
  view.controller.update([...initial.slice(1),message(101)]);
  assert.equal(view.unread,1); assert.equal(view.geometry.scrollTop,100);
  for(let n=102;n<350;n++) view.controller.update(Array.from({length:100},(_,i)=>message(n-99+i)));
  assert.equal(view.unread,100);
  view.controller.update(initial); assert.equal(view.unread,100);
});
test('crisis change alone retains history and reading position without false unread; remount starts latest', () => {
  const history: LobbyState['chat']=[message(1),message(2),message(5)];
  const view=setup(history); readEarlier(view); view.controller.update([...history]);
  assert.equal(view.unread,0); assert.equal(view.geometry.scrollTop,100);
  view.controller.update([...history,message(6)]); assert.equal(view.unread,1);
  assert.deepEqual(history.map(m=>m.crisis_number),[1,1,2]);
  const remounted=setup([...history,message(6)]);
  assert.equal(remounted.unread,0); assert.equal(remounted.geometry.scrollTop,400);
});
test('wrapped content/viewport resizing follows only while following latest', () => {
  const view=setup(); view.geometry.scrollHeight=950; view.controller.onResize();
  assert.equal(view.geometry.scrollTop,750);
  readEarlier(view); view.geometry.clientHeight=120; view.controller.onResize();
  assert.equal(view.geometry.scrollTop,100);
  view.controller.jumpToLatest(); assert.equal(view.geometry.scrollTop,830);
});
test('scroll listener and both resize observations are cleaned up; no global listeners', () => {
  const view=setup(); const listeners=new Map(); const observed: unknown[]=[]; let disconnected=false;
  const history={addEventListener:(name:string,fn:unknown)=>listeners.set(name,fn),removeEventListener:(name:string,fn:unknown)=>{ assert.equal(listeners.get(name),fn); listeners.delete(name); }};
  const original=globalThis.ResizeObserver;
  globalThis.ResizeObserver=class { constructor(callback:unknown) { assert.equal(callback,view.controller.onResize); } observe(node:unknown) { observed.push(node); } disconnect() { disconnected=true; } } as unknown as typeof ResizeObserver;
  try {
    const contents={}; const stop=observeChatHistory(history as unknown as HTMLElement,contents as HTMLElement,view.controller);
    assert.equal(listeners.get('scroll'),view.controller.onScroll);
    assert.deepEqual(observed,[history,contents]); stop();
    assert.equal(listeners.size,0); assert.equal(disconnected,true);
  } finally { globalThis.ResizeObserver=original; }
});
test('unread button is counted, accessible and keyboard focus returns to history without page scroll', () => {
  for (const count of [1,3]) {
    let jumped=0; let focusOptions: unknown;
    const history={current:{focus:(options:unknown)=>{ focusOptions=options; }} as HTMLDivElement};
    const element=UnreadChatMessages({count,onJump:()=>{ jumped++; },history});
    const html=renderToStaticMarkup(element);
    assert.ok(html.includes('type="button"')); assert.ok(html.includes(`Show ${count} new message`));
    assert.ok(html.includes('aria-live="polite"')); assert.ok(html.includes('jump to latest'));
    const button=element.props.children;
    const original=globalThis.document;
    globalThis.document={activeElement:button} as unknown as Document;
    try { button.props.onClick({currentTarget:button}); } finally { globalThis.document=original; }
    assert.equal(jumped,1); assert.deepEqual(focusOptions,{preventScroll:true});
  }
  assert.ok(!renderToStaticMarkup(<UnreadChatMessages count={0} onJump={()=>{}} history={{current:null}} />).includes('<button'));
});
test('arrivals and resizes cannot call focus or page scroll APIs', () => {
  const view=setup(); const original=globalThis.document;
  globalThis.document={activeElement:{id:'composer-or-voting-control'}} as unknown as Document;
  try {
    const focus=globalThis.document.activeElement;
    view.controller.update([message(1),message(2)]); view.controller.onResize();
    readEarlier(view); view.controller.update([message(1),message(2),message(3)]);
    assert.equal(globalThis.document.activeElement,focus);
    // Geometry adapter exposes only scrollTop/scrollHeight/clientHeight: any
    // scrollIntoView/focus/window access in these paths would fail this test.
  } finally { globalThis.document=original; }
});

test('three simulated recipients consume captured server snapshots with independent reading positions', {skip:!process.env.CHAT_ACCEPTANCE_FILE}, async () => {
  // Optional cross-layer acceptance run; the ordinary suite remains standalone.
  const path=process.env.CHAT_ACCEPTANCE_FILE;
  if (!path) return;
  const {readFileSync}=await import('node:fs');
  const snapshots: LobbyState[][]=JSON.parse(readFileSync(path,'utf8'));
  const views=snapshots[0].map(state=> {
    const geometry={scrollTop:0,scrollHeight:200,clientHeight:200}; let unread=0;
    const controller=new ChatScrollController(geometry,state.you,count=>{unread=count;});
    controller.update(state.chat);
    return {geometry,controller,get unread(){return unread;}};
  });
  for (const [index,frames] of snapshots.entries()) {
    for (const [player,frame] of frames.entries()) {
      const view=views[player]; view.geometry.scrollHeight=200+frame.chat.length*80;
      view.controller.update(frame.chat);
    }
    // After three arrivals B looks back; A and C stay at the latest messages.
    if(index===3) {views[1].geometry.scrollTop=0;views[1].controller.onScroll();}
    if(index===7) {
      assert.equal(views[1].geometry.scrollTop,0); assert.equal(views[1].unread,4);
      assert.equal(views[2].unread,0); assert.equal(views[2].geometry.scrollTop,560);
      views[1].controller.jumpToLatest(); assert.equal(views[1].unread,0);
    }
  }
  assert.equal(views[1].geometry.scrollTop,640);
  assert.equal(views[1].unread,0);
  assert.deepEqual(snapshots.at(-1)![1].chat.map(m=>m.crisis_number),[1,1,1,1,1,1,1,2]);
});
