import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { missionInvite, safeReturnPath, signInPath, signOutPath, readAccessStatus } from '../src/access';
import { DataPrivacy, PublicInformation, safeContact } from '../src/PublicInformation';
import { AccessPage } from '../src/AccessExperience';
import { forgetAllSeats, restoreSession, saveSession } from '../src/session';

test('callback keeps only a valid same-origin invite and never credentials or auth routes',()=>{
  assert.equal(safeReturnPath('/?mission=invite_123&credential=secret#private'), '/?mission=invite_123');
  assert.equal(signInPath('/?mission=invite_123'),'/signin-with-chatgpt?return_to=%2F%3Fmission%3Dinvite_123');
  assert.equal(signOutPath('/?mission=invite_123'),'/signout-with-chatgpt?return_to=%2F%3Fmission%3Dinvite_123');
  for(const value of ['https://evil.test','//evil.test','/\\evil.test','/callback','/signin-with-chatgpt?return_to=//evil.test','/signout-with-chatgpt','/?mission=a&mission=b','/?mission=%2Fsecret','/api/missions','/\n/evil.test'])assert.equal(safeReturnPath(value),'/');
  assert.equal(missionInvite('?mission=').invalid,true);
  assert.equal(missionInvite('?mission=a&mission=b').invalid,true);
  assert.deepEqual(missionInvite(''),{token:null,invalid:false});
});

test('access response is exact boolean-only and network failure is distinct from signed out',async()=>{
  for(const signedIn of [false,true]) {
    const result=await readAccessStatus((async(url,options)=>{
      assert.equal(url,'/api/access');assert.equal(options?.cache,'no-store');assert.equal(options?.credentials,'same-origin');
      assert.equal(options?.redirect,'manual');
      return Response.json({signedIn});
    }) as typeof fetch);assert.equal(result,signedIn);
  }
  for(const value of [null,false,0,[], 'signedIn',{signedIn:'true'},{signedIn:true,userId:'leak'},{}])assert.equal(await readAccessStatus((async()=>Response.json(value)) as typeof fetch),null);
  assert.equal(await readAccessStatus((async()=>{throw Error('offline')}) as typeof fetch),null);
  assert.equal(await readAccessStatus((async()=>new Response('',{status:503})) as typeof fetch),null);
  for(const status of [401,403,302])assert.equal(await readAccessStatus((async()=>new Response('',{status})) as typeof fetch),false);
  assert.equal(await readAccessStatus((async()=>({type:'opaqueredirect',status:0})) as typeof fetch),false);
});

test('signed-out and canceled-signin entry have no game form and use a normal top-level anchor',()=>{
  const html=renderToStaticMarkup(<AccessPage state="signedOut" refresh={async()=>false} returnTo="/?mission=invite" />);
  assert.match(html,/Sign in with ChatGPT/);assert.match(html,/target="_top"/);
  assert.match(html,/return_to=%2F%3Fmission%3Dinvite/);
  assert.doesNotMatch(html,/<form|id="callsign"|No account required/);
  assert.match(html,/sign-in is canceled/);
  assert.match(renderToStaticMarkup(<AccessPage state="unavailable" refresh={async()=>null} returnTo="/" />),/saved seat has not been removed/);
});

test('privacy disclosure is accurate and unsafe or missing owner configuration blocks publication readiness',()=>{
  const html=renderToStaticMarkup(<DataPrivacy />);
  for(const copy of ['24 hours','7 days','30 days','not expire while anyone','no self-service','not yet configured','not yet published'])assert.ok(html.includes(copy),copy);
  assert.match(renderToStaticMarkup(<PublicInformation />),/cannot currently be removed/);
  assert.equal(safeContact('javascript:alert(1)'),null);assert.equal(safeContact('https://name:secret@example.test'),null);
  assert.equal(safeContact('mailto:owner@example.test?body=secret'),null);assert.equal(safeContact('mailto:owner%0aBcc:x@example.test'),null);
  assert.equal(safeContact('mailto:owner@example.test'),'mailto:owner@example.test');
  const configured=renderToStaticMarkup(<DataPrivacy contact="https://owner.example.test/contact" backupPolicy="Approved finite policy" />);
  assert.match(configured,/https:\/\/owner.example.test\/contact/);assert.doesNotMatch(configured,/not yet configured|not yet published/);
});

test('forgetting local seats is scoped, irreversible locally, and does not clear unrelated storage',()=>{
  const previous=globalThis.localStorage;
  const storage:any={getItem(key:string){return this[key]??null;},setItem(key:string,value:string){this[key]=value;},removeItem(key:string){delete this[key];}};
  Object.defineProperty(globalThis,'localStorage',{configurable:true,value:storage});
  try {
    saveSession({token:'one',credential:'seat-one'});saveSession({token:'two',credential:'seat-two'});storage.other='retain';
    assert.equal(restoreSession('one')?.credential,'seat-one');forgetAllSeats();
    assert.equal(restoreSession('one'),null);assert.equal(restoreSession('two'),null);assert.equal(storage.other,'retain');
    saveSession({token:'blocked',credential:'keep'});storage.removeItem=()=>{throw Error('blocked');};
    assert.throws(()=>forgetAllSeats());assert.equal(restoreSession('blocked')?.credential,'keep');
  } finally {Object.defineProperty(globalThis,'localStorage',{configurable:true,value:previous});}
});
