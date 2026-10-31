// Local UI acceptance only: fake dispatch/cookies, real isolated FastAPI and Chromium.
// No Sites/Render request, real OAuth, provider, persistent browser profile or traces.
import {spawn} from 'node:child_process';
import {mkdtemp,mkdir,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomBytes} from 'node:crypto';
const root=fileURLToPath(new URL('../../',import.meta.url));
const output=resolve(process.argv[2]);await mkdir(output,{recursive:false});
const directory=await mkdtemp(join(tmpdir(),'ce97-private-'));
const base='http://127.0.0.1:18778',key=randomBytes(32).toString('hex');
let server,browser;const checks=[];let stage='start';const consoleErrors=[];
function check(value,label){if(!value)throw Error(label);}
async function record(name){checks.push(name);console.log('PASS '+name);}
async function poll(fn,label,timeout=15000){const end=Date.now()+timeout;while(Date.now()<end){if(await fn())return;await new Promise(r=>setTimeout(r,60));}throw Error(label);}
async function context(cookie=false,mobile=false){
 const c=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:900},hasTouch:mobile,isMobile:mobile,reducedMotion:'reduce'});
 await c.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
 if(cookie)await c.addCookies([{name:'ce-local-account',value:'fixture-b',url:base,httpOnly:true}]);
 await c.addInitScript(()=>{
  const Native=window.WebSocket;window.__accessSockets=[];window.__accessState=null;
  window.WebSocket=class extends Native{constructor(...args){super(...args);window.__accessSockets.push(this);this.addEventListener('message',event=>{try{const data=JSON.parse(event.data);if(data.type==='state')window.__accessState=data.mission;}catch{}});}};
 });return c;
}
async function page(c){const p=await c.newPage();p.on('pageerror',()=>consoleErrors.push('pageerror'));return p;}
async function state(p){return p.evaluate(()=>window.__accessState);}
async function connected(p,n){await poll(async()=>{const s=await state(p);return s&&s.players.length===n&&s.players.every(p=>p.connected);},'players_connected');}
async function layouts(p,label){
 for(const [name,width,height] of [['desktop',1440,900],['mobile',390,844],['narrow',320,640]]){
  await p.setViewportSize({width,height});
  await p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  const okay=await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1&&[...document.querySelectorAll('button,.primary-link,.seat-controls a')].every(e=>{const r=e.getBoundingClientRect();return !r.width||r.left>=0&&r.right<=innerWidth+1&&r.height>=47;}));
  check(okay,'layout_'+label+'_'+name);
  await p.screenshot({path:join(output,label+'-'+name+'.png'),fullPage:true,mask:[p.locator('#invite'),p.locator('.private-panel'),p.locator('.chat-history'),p.locator('textarea')],maskColor:'#33434b'});
 }
 await record(label+' desktop/390px/320px layouts and touch targets');
}
try{
 server=spawn(root+'.venv/bin/python',['backend/tests/browser_acceptance_server.py',directory,'18778'],{cwd:root,env:{...process.env,CE_BROWSER_TEST_KEY:key,CE_BROWSER_ACCESS_TEST:'true'},stdio:['ignore','pipe','pipe']});
 for(const stream of [server.stdout,server.stderr])stream.on('data',data=>writeFile(join(directory,'server.log'),data,{flag:'a',mode:0o600}));
 await poll(async()=>{if(server.exitCode!==null)throw Error('fixture_exited');try{return(await fetch(base+'/api/health',{headers:{Cookie:'ce-local-account=fixture-a'}})).ok;}catch{return false;}},'fixture_ready');
 const pw=await import(process.env.CONSENSUS_PLAYWRIGHT_MODULE||'playwright');
 browser=await pw.chromium.launch({headless:true,...(process.env.CONSENSUS_CHROMIUM?{executablePath:process.env.CONSENSUS_CHROMIUM}:{})});
 const a=await context(),host=await page(a);
 stage='anonymous';await host.goto(base+'/?mission=fixture_invite&credential=never-forward#discard');
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).waitFor();
 check(await host.locator('#callsign').count()===0,'anonymous_form_hidden');
 const denied=await host.evaluate(async()=>Promise.all(['/api/missions','/api/missions/invite/join'].map(path=>fetch(path,{method:'POST',body:'{}',headers:{'Content-Type':'application/json','oai-authenticated-user-id':'forged'}}).then(r=>r.status))));
 check(denied.every(s=>s===401),'anonymous_create_join_denied');
 await layouts(host,'signed-out');
 const focus=[];for(let i=0;i<4;i++){await host.keyboard.press('Tab');focus.push(await host.evaluate(()=>document.activeElement?.textContent?.trim()));}
 check(focus.some(text=>text==='Sign in with ChatGPT')&&focus.some(text=>text==='Data, privacy and saved seats'),'keyboard_tab_order');
 check(await host.evaluate(()=>parseFloat(getComputedStyle(document.activeElement).outlineWidth))>=2,'visible_keyboard_focus');
 const href=await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).getAttribute('href');
 check(new URL(href,base).searchParams.get('return_to')==='/?mission=fixture_invite','safe_return_invite');
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).focus();await host.keyboard.press('Enter');
 await host.getByRole('link',{name:'Cancel sign-in',exact:true}).click();
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).waitFor();check(new URL(host.url()).search==='?mission=fixture_invite','cancel_invite');
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).click();await host.getByRole('link',{name:'Confirm local sign-in',exact:true}).click();
 await host.getByRole('button',{name:'Join Mission',exact:true}).waitFor();
 await record('anonymous gating, keyboard sign-in, cancellation and safe invite callback (local dispatch fixture)');
 stage='two-player';await host.goto(base);await host.locator('#callsign').fill('Access Host');
 await a.clearCookies();await host.getByRole('button',{name:'Create Mission',exact:true}).click();
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).waitFor();
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).click();await host.getByRole('link',{name:'Confirm local sign-in',exact:true}).click();
 await host.locator('#callsign').fill('Access Host');await host.getByRole('button',{name:'Create Mission',exact:true}).click();
 await connected(host,1);const inviteURL=host.url();
 const b=await context(true,true),guest=await page(b);await guest.goto(inviteURL);await guest.locator('#callsign').fill('Access Guest');await guest.getByRole('button',{name:'Join Mission',exact:true}).click();
 await connected(host,2);await connected(guest,2);
 await host.getByRole('button',{name:'Start Mission',exact:true}).click();
 await poll(async()=> (await state(host))?.phase==='briefing','briefing');
 const before=await state(host);const saved=await host.evaluate(token=>localStorage.getItem('consensus.session.'+token),before.token);
 await layouts(host,'signed-in-briefing');
 stage='http-expiry';await a.clearCookies();await host.getByRole('button',{name:'Begin discussion',exact:true}).click();
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).waitFor();
 check(await host.evaluate(token=>localStorage.getItem('consensus.session.'+token),before.token)===saved,'http_expiry_key_preserved');
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).click();await host.getByRole('link',{name:'Confirm local sign-in',exact:true}).click();await connected(host,2);
 check((await state(host)).phase==='briefing','unauthorized_http_did_not_advance_phase');
 await record('expired HTTP create/action prompts reauthentication without seat allocation or phase changes');
 stage='expiry';await a.clearCookies();await host.evaluate(()=>window.__accessSockets.at(-1).close());
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).waitFor({timeout:18000});
 check(await host.locator('.private-panel').count()===0,'expired_private_ui_hidden');
 const attempts=await host.evaluate(()=>window.__accessSockets.length);await host.waitForTimeout(2300);
 check(await host.evaluate(()=>window.__accessSockets.length)===attempts,'no_endless_signedout_reconnect');
 check(await host.evaluate(token=>localStorage.getItem('consensus.session.'+token),before.token)===saved,'expired_saved_seat_retained');
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).click();await host.getByRole('link',{name:'Cancel sign-in',exact:true}).click();
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).waitFor();
 check(new URL(host.url()).searchParams.get('mission')===before.token,'host_created_invite_survives_reauth_cancel');
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).click();await host.getByRole('link',{name:'Confirm local sign-in',exact:true}).click();
 await connected(host,2);const resumed=await state(host);
 check(resumed.you===before.you&&JSON.stringify(resumed.roles)===JSON.stringify(before.roles),'same_seat_roles_after_reauth');
 await record('expired sign-in halts sockets, hides private UI, cancellation retains key, reauthentication restores same two-player seat');
 stage='invalid-seat';await host.evaluate(token=>localStorage.setItem('consensus.session.'+token,'invalid-seat'),before.token);await host.reload();
 await host.getByRole('button',{name:'Return to mission creation',exact:true}).waitFor();
 check(await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).count()===0,'invalid_seat_not_signin_loop');
 await host.evaluate(({token,saved})=>localStorage.setItem('consensus.session.'+token,saved),{token:before.token,saved});await host.reload();await connected(host,2);
 await record('invalid seat distinguished from missing Sites session; valid stored credential recovers after refresh');
 stage='logout-storage-failure';
 await host.evaluate(()=>{const original=Storage.prototype.removeItem;window.__restoreStorage=()=>{Storage.prototype.removeItem=original;};Storage.prototype.removeItem=function(key){if(key.startsWith('consensus.session.'))throw Error('fixture storage failure');return original.call(this,key);};});
 host.once('dialog',dialog=>dialog.accept());await host.getByRole('link',{name:'Sign out and forget saved seats',exact:true}).click();
 await host.getByRole('alert').filter({hasText:'Saved seats could not be cleared'}).waitFor();
 check(await host.evaluate(token=>localStorage.getItem('consensus.session.'+token),before.token)===saved,'storage_failure_does_not_navigate_or_discard');
 await host.evaluate(()=>window.__restoreStorage());
 await record('storage-removal failure prevents sign-out navigation and warns about shared profiles');
 stage='logout';
 host.once('dialog',dialog=>dialog.dismiss());await host.getByRole('link',{name:'Sign out and forget saved seats',exact:true}).click();
 check(await host.evaluate(token=>localStorage.getItem('consensus.session.'+token),before.token)===saved,'canceled_signout_keeps_key');
 const tab=await page(a);await tab.goto(inviteURL);await poll(async()=>!!(await state(tab)),'shared_tab_connected');
 await host.evaluate(()=>{localStorage.setItem('consensus.session.other-fixture','other-secret');localStorage.setItem('unrelated.preference','retain');});
 host.once('dialog',dialog=>dialog.accept());await host.getByRole('link',{name:'Sign out and forget saved seats',exact:true}).click();
 await host.getByRole('link',{name:'Sign in with ChatGPT',exact:true}).waitFor();
 await poll(async()=>await tab.locator('.private-panel').count()===0,'shared_tab_private_ui_closed');
 check(await host.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('consensus.session.')).length)===0,'all_local_seats_forgotten');
 check(await host.evaluate(()=>localStorage.getItem('unrelated.preference'))==='retain','unrelated_storage_retained');
 await a.addCookies([{name:'ce-local-account',value:'fixture-b',url:base,httpOnly:true}]);await host.goto(base);await host.locator('#callsign').waitFor();
 check(await host.locator('.private-panel').count()===0,'switched_account_no_old_private_ui');
 await host.locator('#callsign').fill('Switch Host');await host.getByRole('button',{name:'Create Mission',exact:true}).click();await connected(host,1);
 check((await state(host)).you!==before.you,'switched_account_new_seat');
 await record('canceled/confirmed sign-out, multi-tab forgetting, unrelated storage preservation and clean fixture-account switch');
 stage='forget';host.once('dialog',dialog=>dialog.dismiss());await host.getByRole('button',{name:'Forget this browser’s saved seats',exact:true}).click();
 check(await host.evaluate(()=>Object.keys(localStorage).some(k=>k.startsWith('consensus.session.'))),'cancel_forget_keeps_seat');
 host.once('dialog',dialog=>dialog.accept());await host.getByRole('button',{name:'Forget this browser’s saved seats',exact:true}).click();await host.getByRole('button',{name:'Create Mission',exact:true}).waitFor();
 check(await host.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('consensus.session.')).length)===0,'explicit_forget');
 await host.goto(base+'/?mission=bad%2Finvite');await host.getByRole('heading',{name:'This invitation is not valid'}).waitFor();check(await host.locator('#callsign').count()===0,'invalid_invite_no_allocation');
 await host.locator('#data-privacy summary').focus();await host.keyboard.press('Enter');check(await host.locator('#data-privacy').getAttribute('open')!==null,'keyboard_disclosure');
 await record('explicit forget/cancel, invalid invite rejection and keyboard privacy disclosure');
 check(consoleErrors.length===0,'browser_page_errors');
 await writeFile(join(output,'result.json'),JSON.stringify({status:'passed',checks,production_requests:0,real_provider_requests:0,physical_devices:false,real_sites_authentication:false,limitations:['Local fake dispatch/cookies, not public Sites identity sanitization or real external-account acceptance.','External account switching outside the app is not detectable from boolean-only access state; bearer-seat limits remain documented.']},null,2)+'\n');
}catch(error){await writeFile(join(output,'result.json'),JSON.stringify({status:'failed',stage,error:String(error.message).split('\n')[0],checks,production_requests:0,real_provider_requests:0},null,2)+'\n');console.error('FAILED '+stage);process.exitCode=1;}
finally{if(browser)await browser.close();if(server&&server.exitCode===null){const done=new Promise(r=>server.once('exit',r));server.kill('SIGTERM');await done;}await rm(directory,{recursive:true,force:true});}
