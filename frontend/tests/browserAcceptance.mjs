// Real headless Chromium, three independent contexts, explicit fake backend.
// No app-state injection, no real provider, no persisted browser storage/traces.
import { spawn } from 'node:child_process';
import { mkdtemp, mkdir, writeFile, readFile, chmod } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';

const root=fileURLToPath(new URL('../../',import.meta.url));
const fastRegression=process.argv.includes('--fast-fake-regression');
const output=resolve(process.argv[2] || 'docs/evidence/milestone_9_7/browser-run');
await mkdir(output,{recursive:false});
const privateDir=await mkdtemp(join(tmpdir(),'ce97-private-'));await chmod(privateDir,0o700);
const base='http://127.0.0.1:18779';const key=randomBytes(32).toString('hex');
const log=[];const defects=[];const screenshots=[];let server,browser;let stage='initialization';
const consoles={errors:0,pageErrors:0};let pages=[],contexts=[];const configuredContexts=new WeakSet();
function check(value,code){if(!value)throw Error(code);}
async function record(name,details={}){log.push({name,...details});await writeFile(join(output,'checks.json'),JSON.stringify(log,null,2)+'\n');}
async function issue(code,details){defects.push({code,...details});await writeFile(join(output,'findings.json'),JSON.stringify(defects,null,2)+'\n');}
async function poll(fn,label,timeout=12000){const end=Date.now()+timeout;while(Date.now()<end){if(await fn())return;await new Promise(r=>setTimeout(r,50));}throw Error(label);}
async function start(){
  server=spawn(root+'.venv/bin/python',['backend/tests/browser_acceptance_server.py',privateDir,'18779'],{cwd:root,env:{...process.env,CE_BROWSER_TEST_KEY:key},stdio:['ignore','pipe','pipe']});
  server.stdout.on('data',d=>writeFile(join(privateDir,'server.log'),d,{flag:'a',mode:0o600}));server.stderr.on('data',d=>writeFile(join(privateDir,'server.log'),d,{flag:'a',mode:0o600}));
  await poll(async()=>{if(server.exitCode!==null)throw Error('fixture_server_exited');try{return (await fetch(base+'/api/health')).ok;}catch{return false;}},'fixture_server_start');
}
async function stop(){if(server&&server.exitCode===null){const done=new Promise(r=>server.once('exit',r));server.kill('SIGTERM');await done;}}
async function control(action,token,extra={}){
  const r=await fetch(base+'/__acceptance/control',{method:'POST',headers:{'Content-Type':'application/json','X-Acceptance-Key':key},body:JSON.stringify({action,token,...extra})});
  check(r.ok,'test_control_failed');return r.json();
}
async function observed(context){
  if(!configuredContexts.has(context)){
  configuredContexts.add(context);
  await context.route('**/*',route=>{const u=new URL(route.request().url());return u.origin===base?route.continue():route.abort();});
  await context.addInitScript(()=>{
    const Old=window.WebSocket;
    window.__acceptance={state:null,events:[],socket:null};
    const a=window.__acceptance;
    document.addEventListener('click',e=>{if(e.target.closest('button')?.textContent==='Next crisis')a.events.push({type:'continue_action',at:performance.now()});},true);
    function rendered(){
      const s=a.state;if(!s)return;
      const k=s.phase+':'+s.crisis_number;
      if(a.lastRender===k)return;
      const title=document.querySelector('.mission-header h1')?.textContent;
      const ready=s.phase==='preparing'?title==='Preparing next crisis':s.phase==='briefing'?title===s.crisis?.title:
        s.phase==='voting'?!!document.querySelector('.active-gameplay input[type=radio]'):
        s.phase==='consensus_window'?!!document.querySelector('[aria-label="Vote deadlock"]'):
        s.phase==='decision_locked'?!!document.querySelector('[aria-label="Final decision"]'):
        ['completed','failed'].includes(s.phase)?!!document.querySelector('.mission-review'):false;
      if(ready){a.lastRender=k;a.events.push({type:'render',phase:s.phase,crisis:s.crisis_number,at:performance.now()});
        if(s.phase==='preparing'&&s.result){const panel=document.querySelector('[aria-label="Recorded outcome during preparation"]'),r=panel?.getBoundingClientRect();if(r&&r.bottom>0&&r.top<innerHeight)a.events.push({type:'previous_result_visible',at:performance.now()});}
      }
    }
    new MutationObserver(()=>requestAnimationFrame(rendered)).observe(document,{childList:true,subtree:true});
    window.WebSocket=class extends Old{
      constructor(...args){super(...args);a.socket=this;this.addEventListener('message',e=>{try{const m=JSON.parse(e.data);if(m.type==='state'){a.state=m.mission;a.events.push({type:'receipt',phase:m.mission.phase,crisis:m.mission.crisis_number,at:performance.now()});requestAnimationFrame(rendered);}}catch{}});}
    };
  });
  }
  const page=await context.newPage();page.on('console',m=>{if(m.type()==='error')consoles.errors++;});
  page.on('pageerror',()=>consoles.pageErrors++);return page;
}
async function state(page){return page.evaluate(()=>window.__acceptance.state);}
async function phase(value,number,targets=pages,timeout=12000){
  await Promise.all(targets.map(p=>p.waitForFunction(([v,n])=>window.__acceptance?.state?.phase===v&&(n===null||window.__acceptance.state.crisis_number===n),[value,number??null],{timeout})));
}
async function snapshots(){return Promise.all(pages.map(state));}
async function common(){
  const states=await snapshots();
  for(const k of ['phase','crisis','metrics','result','deadline','history'])check(states.every(s=>JSON.stringify(s[k])===JSON.stringify(states[0][k])),'public_sync_'+k);
  const all=Object.assign({},...states.map(s=>s.private_intelligence));
  for(let i=0;i<3;i++){
    check(Object.keys(states[i].private_intelligence).sort().join()===[...states[i].roles].sort().join(),'authorized_roles');
    for(const [role,text] of Object.entries(all))if(!states[i].roles.includes(role))check(!JSON.stringify(states[i]).includes(text),'private_ws_isolation');
    const dom=await pages[i].locator('body').innerText();
    for(const [role,text] of Object.entries(all))if(!states[i].roles.includes(role))check(!dom.includes(text),'private_dom_isolation');
  }
  return states;
}
async function shot(page,name,fullPage=true){
  if(fastRegression)return; // Separate quick regression; full 26s runs retain screenshots.
  // Mask all private intelligence, invite tokens, chat, and possible vote state.
  const masks=[page.locator('.private-panel'),page.locator('#invite'),page.locator('.chat-history'),page.locator('textarea')];
  const s=await state(page);
  if(s?.phase==='voting'&&(s.voting?.your_vote||await page.locator('input[type=radio]:checked').count())){masks.push(page.locator('.response-options'),page.locator('.active-gameplay [role=status]'));}
  await page.screenshot({path:join(output,name+'.png'),fullPage,mask:masks,maskColor:'#33434b'});
  screenshots.push({file:name+'.png',redactions:['private panels','invite','chat','submitted voting state']});
  await writeFile(join(output,'screenshots.json'),JSON.stringify(screenshots,null,2)+'\n');
}
async function layouts(page,label){
  for(const [name,width,height] of [['desktop',1440,900],['tablet',768,1024],['mobile',390,844],['narrow',320,640]]){
    await page.setViewportSize({width,height});
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    const m=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,
      panelOverflows:[...document.querySelectorAll('.panel,.active-gameplay,.mission-review')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).length,
      clippedButtons:[...document.querySelectorAll('button')].filter(e=>{const r=e.getBoundingClientRect();return r.width&& (r.right>innerWidth+1||r.left<0);}).length}));
    await record('layout_'+label+'_'+name,m);
    if(m.document>width+1||m.clippedButtons||m.panelOverflows)await issue('horizontal_overflow',{checkpoint:label,viewport:width,...m});
    await shot(page,label+'-'+name);
    if(label==='victory'&&name==='mobile'){
      const table=page.getByRole('region',{name:'Metric progression values; scroll for all columns',exact:true});
      await table.focus();await page.keyboard.press('ArrowRight');
      await poll(async()=>table.evaluate(e=>e.scrollLeft>0),'review_table_keyboard_scroll');
      await record('review_table_keyboard',{horizontal_scroll_accessible:true});
      await table.evaluate(e=>e.scrollTo({left:0,behavior:'instant'}));
    }
    if(label==='voting'){
      if(name==='narrow')await shot(page,'voting-narrow-viewport',false);
      const blocked=await page.locator('input[type=radio]').evaluateAll(radios=>radios.filter(r=>{
        const b=r.getBoundingClientRect(),x=b.x+b.width/2,y=b.y+b.height/2;
        return y>=0&&y<innerHeight&&!r.closest('label').contains(document.elementFromPoint(x,y));
      }).length);
      await record('radio_hit_test_'+name,{blocked_visible_radios:blocked});
      if(blocked)await issue('sticky_submit_covers_radio',{checkpoint:label,viewport:width,blocked_visible_radios:blocked});
      if(name==='narrow'){await page.getByRole('radio').nth(1).check();check(await page.getByRole('radio').nth(1).isChecked(),'narrow_radio_selectable');await page.getByRole('radio').nth(1).press('ArrowUp');}
    }
  }
  await page.setViewportSize({width:1440,height:900});
}
async function accessibility(page,checkpoint){
  const session=await page.context().newCDPSession(page);const tree=await session.send('Accessibility.getFullAXTree');
  const controls=tree.nodes.filter(n=>!n.ignored&&['button','textbox','radio','combobox'].includes(n.role?.value));
  const unnamed=controls.filter(n=>!n.name?.value).length;
  const statuses=tree.nodes.filter(n=>!n.ignored&&n.role?.value==='status').length;
  await record('accessibility_'+checkpoint,{unnamed_controls:unnamed,status_regions:statuses,automated_tree_only:true});
  if(unnamed)await issue('unnamed_controls',{checkpoint,count:unnamed});await session.detach();
  const contrast=await page.evaluate(()=>{
    const rgb=s=>{const v=s.match(/[\d.]+/g)?.map(Number);return v?.length>=3?v:null;};
    const lum=c=>c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
    const ratios=[];let skipped=0;
    for(const e of document.querySelectorAll('body *')){
      if(e.children.length||!e.textContent.trim()||!e.getClientRects().length||e.closest(':disabled')||e.namespaceURI!=='http://www.w3.org/1999/xhtml')continue;
      const style=getComputedStyle(e),fg=rgb(style.color);if(!fg||fg.length===4&&fg[3]!==1){skipped++;continue;}
      let parent=e,bg=null;
      while(parent){const c=rgb(getComputedStyle(parent).backgroundColor);if(c&&(c.length===3||c[3]===1)){bg=c;break;}parent=parent.parentElement;}
      if(!bg){skipped++;continue;}
      const [a,b]=[lum(fg),lum(bg)].sort((x,y)=>y-x),ratio=(a+.05)/(b+.05);
      const large=parseFloat(style.fontSize)>=24||parseFloat(style.fontSize)>=18.66&&parseInt(style.fontWeight)>=700;
      ratios.push({ratio,required:large?3:4.5});
    }
    return {sampled_text_elements:ratios.length,minimum_ratio:Math.min(...ratios.map(x=>x.ratio)),below_size_adjusted_threshold:ratios.filter(x=>x.ratio+.01<x.required).length,unsupported_or_translucent_skipped:skipped,reduced_motion:matchMedia('(prefers-reduced-motion: reduce)').matches};
  });
  await record('computed_contrast_'+checkpoint,contrast);
  if(contrast.below_size_adjusted_threshold)await issue('text_contrast',{checkpoint,count:contrast.below_size_adjusted_threshold});
}
async function clockCheck(name){
  await pages[0].waitForFunction(()=>{
    const a=window.__acceptance,s=a.state,r=a.events.filter(e=>e.type==='receipt').at(-1);
    const text=document.querySelector('.phase-clock strong')?.textContent;if(!text)return false;
    const [m,sec]=text.split(':').map(Number);
    return Math.abs(m*60+sec-Math.ceil(Math.max(0,s.deadline-s.server_now-(performance.now()-r.at)/1000)))<=1;
  });
  const t=await pages[0].evaluate(()=>{
    const a=window.__acceptance,s=a.state,r=a.events.filter(e=>e.type==='receipt').at(-1);
    const text=document.querySelector('.phase-clock strong')?.textContent;
    if(!text)return null;
    const [m,sec]=text.split(':').map(Number);
    return {shown:m*60+sec,expected:Math.ceil(Math.max(0,s.deadline-s.server_now-(performance.now()-r.at)/1000))};
  });
  check(t&&Math.abs(t.shown-t.expected)<=1,'authoritative_countdown_'+name);
  await record('countdown_'+name,{within_one_second:true,shown_seconds:t.shown});
}
async function renderedReview(snapshot){
  for(const page of pages){
    await page.locator('.consensus-score strong').waitFor();
    const shown=parseFloat(await page.locator('.consensus-score strong').innerText());
    check(shown===snapshot.summary.consensus_score,'rendered_consensus_score');
    const metrics=await page.locator('.review-final-metrics dd').allTextContents();
    check(metrics.map(x=>parseInt(x)).join()===Object.values(snapshot.metrics).join(),'rendered_final_metrics');
    const titles=await page.locator('.history-entry summary').allTextContents();
    check(titles.length===snapshot.history.length&&titles.every((s,i)=>s.includes('Crisis '+(i+1)+' —')),'rendered_chronological_history');
  }
}
async function expire(){const s=await state(pages[0]);await control('expire',s.token);}
let unreadChecked=false;
async function openVote(number){
  await pages[0].getByRole('button',{name:'Begin discussion',exact:true}).click();await phase('discussion',number);
  const s=await state(pages[0]);check(s.deadline-s.server_now>58&&s.deadline-s.server_now<=60,'discussion_duration');await clockCheck('discussion');
  if(!unreadChecked){
    unreadChecked=true;
    const message='Synthetic acceptance conversation. '.repeat(10);
    for(let i=0;i<4;i++){
      await control('elapse',s.token,{seconds:1});
      await pages[0].getByLabel('Message your team (500 characters max)').fill(message+i);
      await pages[0].getByRole('button',{name:'Send message',exact:true}).click();
      await pages[1].getByText(message+i,{exact:true}).waitFor();
    }
    await pages[1].locator('.chat-history').evaluate(e=>e.scrollTo({top:0,behavior:'instant'}));
    await poll(async()=>pages[1].locator('.chat-history').evaluate(e=>e.scrollHeight-e.clientHeight>100&&e.scrollTop<10),'chat_reading_position');
    await control('elapse',s.token,{seconds:1});
    await pages[0].getByLabel('Message your team (500 characters max)').fill(message+'new');
    await pages[0].getByRole('button',{name:'Send message',exact:true}).click();
    const unread=pages[1].getByRole('button',{name:/Show 1 new message; jump to latest/});
    await unread.waitFor();await unread.focus();await pages[1].keyboard.press('Enter');
    await poll(async()=>await unread.count()===0,'unread_cleared');
    check(await pages[1].locator('.chat-history').evaluate(e=>document.activeElement===e&&e.scrollHeight-e.clientHeight-e.scrollTop<3),'unread_keyboard_focus');
    await record('browser_chat_unread',{independent_reading_position:true,new_message_control:true,keyboard_jump:true,focus_retained_in_history:true,chat_contents_exported:false});
  }
  await expire();await phase('voting',number);check((await state(pages[0])).deadline-(await state(pages[0])).server_now>28,'vote_duration');await clockCheck('voting');
}
async function vote(choices){
  for(let i=0;i<choices.length;i++)if(choices[i]){
    const radios=pages[i].getByRole('radio');if(i===2)await radios.nth('ABC'.indexOf(choices[i])).tap();else await radios.nth('ABC'.indexOf(choices[i])).check();
    await pages[i].getByRole('button',{name:/^Submit (private|Final) [Vv]ote$/}).click();
    if(i<choices.length-1){
      await pages[i].waitForFunction(()=>window.__acceptance.state.voting?.your_vote!==null);
      for(let j=i+1;j<3;j++){
        const peer=await state(pages[j]);
        if(peer.voting)check(peer.voting.your_vote===null&&!('votes' in peer.voting),'hidden_peer_votes');
      }
    }
  }
}
async function next(number){await pages[0].getByRole('button',{name:'Next crisis',exact:true}).click();await phase('briefing',number,pages,38000);await common();}
async function refresh(index,expectedPhase,number){
  const original=await state(pages[index]);await pages[index].reload();await phase(expectedPhase,number,[pages[index]]);
  const restored=await state(pages[index]);check(restored.you===original.you&&JSON.stringify(restored.roles)===JSON.stringify(original.roles),'refresh_identity_roles');
  check(JSON.stringify(restored.history)===JSON.stringify(original.history),'refresh_history');
  await poll(async()=>(await snapshots()).every(s=>s.players.every(p=>p.connected)),'refresh_presence');
}

try{
  stage='tooling';const pw=await import(process.env.CONSENSUS_PLAYWRIGHT_MODULE||'playwright');
  browser=await pw.chromium.launch({headless:true,...(process.env.CONSENSUS_CHROMIUM?{executablePath:process.env.CONSENSUS_CHROMIUM}:{})});
  await record('browser_environment',{browser:browser.version(),headless:true,isolated_contexts:3,real_provider_requests:0});
  await start();if(fastRegression)await control('profile',null,{profile:'main',delay:5});
  contexts=await Promise.all([0,1,2].map(i=>browser.newContext({viewport:i===2?{width:390,height:844}:{width:1440,height:900},hasTouch:i===2,isMobile:i===2,reducedMotion:'reduce',colorScheme:'dark'})));
  pages=await Promise.all(contexts.map(observed));
  stage='creation';await pages[0].goto(base);await pages[0].getByLabel('Your callsign').fill('Player A');
  await poll(async()=>!(await pages[0].locator('option[value=generated]').isDisabled()),'generated_fixture_available');
  await pages[0].getByLabel('Mission mode').selectOption('generated');await pages[0].getByRole('button',{name:'Create Mission',exact:true}).click();
  await phase('lobby',0,[pages[0]]);const invite=pages[0].url();
  for(let i=1;i<3;i++){
    await pages[i].goto(invite);await pages[i].getByLabel('Your callsign').fill('Player '+String.fromCharCode(65+i));
    await pages[i].getByRole('button',{name:'Join Mission',exact:true}).click();await phase('lobby',0,[pages[i]]);
  }
  await poll(async()=>(await state(pages[0]))?.players.filter(p=>p.connected).length===3,'all_lobby');
  const identities=(await snapshots()).map(s=>({id:s.you,roles:s.roles}));
  check(new Set(identities.map(x=>x.id)).size===3,'independent_identities');
  check(await pages[1].getByRole('button',{name:'Start Mission',exact:true}).count()===0,'host_only_start');
  await shot(pages[0],'three-player-lobby');await accessibility(pages[0],'lobby');
  await record('three_player_lobby',{distinct_identities:3,independent_contexts:true,guest_host_controls_absent:true});
  stage='briefing';await pages[0].getByRole('button',{name:'Start Mission',exact:true}).click();await phase('briefing',1);
  const initial=await common();check(initial.flatMap(s=>s.roles).sort().join()===['community','economy','infrastructure','safety'].join(),'four_role_coverage');
  await refresh(1,'briefing',1);await pages[0].keyboard.press('Tab');check(await pages[0].getByRole('button',{name:'Begin discussion',exact:true}).evaluate(e=>document.activeElement===e),'briefing_tab_to_host_control');await record('native_tab_briefing',{reaches_host_control:true});await shot(pages[0],'initial-briefing');await layouts(pages[0],'briefing');
  await record('briefing_refresh_privacy',{role_coverage:4,role_counts:initial.map(s=>s.roles.length).sort(),common_public:true,authorized_private_only:true});
  stage='plurality';await openVote(1);await pages[0].keyboard.press('Tab');check(await pages[0].evaluate(()=>document.activeElement.matches('input[type=radio]')),'voting_tab_to_radio');await record('native_tab_voting',{reaches_radio_group:true});await shot(pages[0],'individual-voting');await layouts(pages[0],'voting');
  const beforeSpoof=await state(pages[1]);
  await pages[1].evaluate(id=>{const s=window.__acceptance.state;window.__acceptance.socket.send(JSON.stringify({type:'vote',round_id:s.voting.round_id,choice_id:'A',player_id:id}));},beforeSpoof.host_id);
  await pages[1].locator('[role=alert]').waitFor();
  check((await state(pages[1])).voting.submitted_count===0,'spoofed_vote_rejected');
  await record('unauthorized_vote',{extra_player_identity_rejected:true,submitted_count_unchanged:true});
  await pages[0].getByRole('radio').nth(1).focus();await pages[0].keyboard.press('Space');
  const outline=await pages[0].getByRole('radio').nth(1).evaluate(e=>getComputedStyle(e).outlineStyle);
  await record('keyboard_vote',{space_selects:await pages[0].getByRole('radio').nth(1).isChecked(),focus_outline:outline});
  await vote(['B','B','A']);await phase('decision_locked',1);const first=(await common())[0];
  check(first.decision.choice_id==='B'&&first.decision.reason==='initial_plurality'&&first.history.length===1,'plurality_result');
  await shot(pages[0],'decision-result');await record('clear_plurality',{choice:'B',consensus:false,history_count:1});
  stage='preparation';await pages[0].getByRole('button',{name:'Next crisis',exact:true}).click();await phase('preparing',1);
  await pages[0].getByRole('region',{name:'Recorded outcome during preparation'}).waitFor();
  await pages[0].evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  const prepFocus=await pages[0].evaluate(()=>({tag:document.activeElement.tagName,label:document.activeElement.getAttribute('aria-label'),correct_target:document.activeElement.matches('[aria-label=\"Recorded outcome during preparation\"]'),scrollY}));
  await record('preparation_focus',prepFocus);if(!prepFocus.correct_target)await issue('preparation_focus_lost',{checkpoint:'after_host_acknowledgement',...prepFocus});
  check(await pages[0].getByRole('button',{name:'Next crisis',exact:true}).count()===0,'duplicate_progression_unavailable');
  check((await state(pages[0])).crisis===null&&Object.keys((await state(pages[0])).private_intelligence).length===0,'pending_future_content_hidden');
  await accessibility(pages[0],'preparation');await shot(pages[0],'crisis-preparation');await layouts(pages[0],'preparation');
  await pages[0].evaluate(()=>window.__focusBeforePresence=document.activeElement);
  await refresh(1,'preparing',1);
  check(await pages[0].evaluate(()=>document.activeElement===window.__focusBeforePresence),'presence_does_not_steal_focus');
  const cIdentity=identities[2];await pages[2].close();pages[2]=null;
  await phase('briefing',2,pages.slice(0,2),38000);
  pages[2]=await observed(contexts[2]);await pages[2].goto(invite);await phase('briefing',2,[pages[2]]);
  check((await state(pages[2])).you===cIdentity.id,'post_admission_reconnect_identity');await common();
  const events=await pages[0].evaluate(()=>window.__acceptance.events);
  const action=events.find(e=>e.type==='continue_action');
  const prepReceipt=events.find(e=>e.type==='receipt'&&e.phase==='preparing'&&e.at>=action.at);
  const prepRender=events.find(e=>e.type==='render'&&e.phase==='preparing'&&e.at>=action.at);
  const resultVisible=events.find(e=>e.type==='previous_result_visible'&&e.at>=action.at);
  check(resultVisible,'recorded_result_visible_during_wait');
  await pages[0].waitForFunction(()=>window.__acceptance.events.some(e=>e.type==='render'&&e.phase==='briefing'&&e.crisis===2));
  const finalEvents=await pages[0].evaluate(()=>window.__acceptance.events);
  const briefReceipt=finalEvents.find(e=>e.type==='receipt'&&e.phase==='briefing'&&e.crisis===2);
  const briefRender=finalEvents.find(e=>e.type==='render'&&e.phase==='briefing'&&e.crisis===2);
  await record('browser_preparation_timing',{clock:'single browser performance.now, host document unchanged',
    fake_provider_delay_seconds:fastRegression?5:26,action_to_preparation_receipt_ms:prepReceipt.at-action.at,action_to_preparation_render_ms:prepRender.at-action.at,action_to_previous_result_visible_ms:resultVisible.at-action.at,
    action_to_briefing_receipt_ms:briefReceipt.at-action.at,action_to_briefing_render_ms:briefRender.at-action.at,
    briefing_receipt_to_dom_frame_ms:briefRender.at-briefReceipt.at,physical_paint_or_screen_reader_timing:false});
  await pages[0].evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  const briefingFocus=await pages[0].evaluate(()=>({tag:document.activeElement.tagName,label:document.activeElement.getAttribute('aria-label'),correct_target:document.activeElement.matches('.mission-header h1'),scrollY}));
  await record('next_briefing_focus',briefingFocus);
  if(!briefingFocus.correct_target)await issue('briefing_focus_lost',{checkpoint:'after_preparation',...briefingFocus});
  const timingStatus=await control('status',first.token);
  await writeFile(join(output,'preparation-server-lifecycle.json'),JSON.stringify(timingStatus.lifecycle.filter(r=>r.crisis_number===2),null,2)+'\n');
  stage='consensus';await openVote(2);await vote(['A','B','C']);await phase('consensus_window',2);
  check((await state(pages[0])).deadline-(await state(pages[0])).server_now>18,'consensus_duration');await clockCheck('consensus');
  await pages[0].getByLabel('Message your team (500 characters max)').fill('Private acceptance chat canary');
  await pages[0].getByRole('button',{name:'Send message',exact:true}).click();
  await pages[1].getByText('Private acceptance chat canary',{exact:true}).waitFor();
  const cw=await state(pages[1]);await refresh(1,'consensus_window',2);
  check((await state(pages[1])).deadline===cw.deadline&&(await state(pages[1])).chat.length===cw.chat.length,'consensus_refresh_deadline_chat');
  await shot(pages[0],'consensus-discussion');await accessibility(pages[0],'consensus');
  await expire();await phase('voting',2);check((await state(pages[0])).voting.number===2,'final_vote_open');
  check((await state(pages[0])).deadline-(await state(pages[0])).server_now>28,'final_vote_duration');await clockCheck('final');
  await shot(pages[0],'final-voting');await vote(['A','B','C']);await phase('decision_locked',2);
  const tied=(await common())[0];check(tied.decision.reason==='ai_tie_break'&&tied.decision.choice_id===tied.crisis.ai_recommendation_choice_id&&tied.history.length===2,'final_tie_fallback');
  await record('consensus_and_final_tie',{consensus_window_seconds:20,final_vote_seconds:30,reason:'ai_tie_break',history_count:2,chat_restored:true});
  stage='fallback_failure';await next(3);check((await control('status',first.token)).diagnostics[2].category==='unavailable','provider_failure_fallback');
  await openVote(3);await vote(['B','B','B']);await phase('decision_locked',3);
  stage='fallback_timeout_nonresponse';await next(4);check((await control('status',first.token)).diagnostics[3].category==='timeout','provider_timeout_fallback');
  await openVote(4);const oldRound=(await state(pages[0])).voting.round_id;
  await contexts[2].setOffline(true);await pages[2].evaluate(()=>window.__acceptance.socket.close());
  await pages[2].getByText('Connection lost — reconnecting automatically.',{exact:true}).waitFor();
  await poll(async()=>(await state(pages[0])).players.filter(p=>p.connected).length===2,'disconnect_presence');
  await shot(pages[2],'connection-loss');await vote(['B','B']);await expire();await phase('decision_locked',4,pages.slice(0,2));
  const nonresponse=await state(pages[0]);check(nonresponse.decision.abstentions===1&&nonresponse.history.length===4,'nonresponse_once');
  check(await pages[0].getByRole('button',{name:'Next crisis',exact:true}).isDisabled(),'presence_progression_gate');
  await contexts[2].setOffline(false);await phase('decision_locked',4,[pages[2]],15000);
  await poll(async()=>(await state(pages[0])).players.every(p=>p.connected),'presence_restored');
  await pages[2].evaluate(round=>window.__acceptance.socket.send(JSON.stringify({type:'vote',round_id:round,choice_id:'C'})),oldRound);
  await pages[2].locator('[role=alert]').waitFor();check((await state(pages[2])).history.length===4,'late_vote_no_change');
  await record('failure_timeout_nonresponse',{failure_fallback:true,timeout_fallback:true,nonresponses:1,late_vote_rejected:true,presence_gated:true});
  stage='restart';await next(5);await pages[0].getByRole('button',{name:'Begin discussion',exact:true}).click();await phase('discussion',5);const beforeRestart=await snapshots();await stop();await start();
  await phase('discussion',5,pages,15000);await poll(async()=>(await snapshots()).every((s,i)=>s.players.every(p=>p.connected)&&s.revision>beforeRestart[i].revision),'restart_all_presence',15000);
  const restored=await common();
  for(let i=0;i<3;i++)check(restored[i].you===beforeRestart[i].you&&JSON.stringify(restored[i].roles)===JSON.stringify(beforeRestart[i].roles)&&JSON.stringify(restored[i].history)===JSON.stringify(beforeRestart[i].history)&&JSON.stringify(restored[i].chat)===JSON.stringify(beforeRestart[i].chat)&&restored[i].deadline===beforeRestart[i].deadline,'restart_preservation');
  await record('backend_restart',{same_identities:true,same_roles:true,history_preserved:true,chat_preserved:true,current_crisis_preserved:true,discussion_deadline_preserved:true});
  stage='finish_campaign';
  for(let n=5;n<=10;n++){
    if(n===5){await expire();await phase('voting',5);await clockCheck('post_restart_vote');}else await openVote(n);await vote(['B','B','B']);await phase('decision_locked',n);
    if(n===6){
      await contexts[0].setOffline(true);await pages[0].evaluate(()=>window.__acceptance.socket.close());
      await pages[0].getByText('Connection lost — reconnecting automatically.',{exact:true}).waitFor();
      await contexts[0].setOffline(false);await phase('decision_locked',n,[pages[0]],15000);
      await poll(async()=>(await snapshots()).every(s=>s.players.every(p=>p.connected)),'host_reconnect');
      check((await state(pages[0])).you===identities[0].id,'host_identity');
      const tab=await observed(contexts[1]);await tab.goto(invite);await phase('decision_locked',n,[tab]);
      check((await state(tab)).you===identities[1].id&&(await state(tab)).players.length===3,'saved_identity_join');await tab.close();
      await record('host_and_saved_identity_recovery',{host_restored:true,saved_identity_new_tab:true,seats:3});
    }
    if(n<10)await next(n+1);
  }
  await pages[0].getByRole('button',{name:'Finish mission',exact:true}).click();await phase('completed',10);
  await pages[0].getByText('AI-generated interpretation. Statistics and recorded decisions are shown separately.',{exact:true}).waitFor();
  const terminal=(await common())[0];check(terminal.history.length===10,'ten_crisis_history');
  check(terminal.summary.consensus_score===Object.values(terminal.metrics).reduce((a,b)=>a+b,0)/4,'terminal_score');
  check(terminal.history.every((h,i)=>h.crisis_number===i+1),'chronological_history');
  await renderedReview(terminal);
  await shot(pages[0],'endgame-review');await layouts(pages[0],'victory');await accessibility(pages[0],'victory');
  await pages[0].locator('details').first().locator('summary').focus();await pages[0].keyboard.press('Enter');
  check(await pages[0].locator('details').first().evaluate(e=>e.open),'keyboard_history_disclosure');
  await refresh(1,'completed',10);const beforeTerminalRestart=await state(pages[0]);await stop();await start();
  await phase('completed',10,pages,15000);await poll(async()=>(await state(pages[0])).players.every(p=>p.connected)&&(await state(pages[0])).revision>beforeTerminalRestart.revision,'terminal_reconnect',15000);
  check(JSON.stringify((await state(pages[0])).history)===JSON.stringify(beforeTerminalRestart.history),'terminal_restart_history');
  const mainStatus=await control('status',first.token);
  const mainCalls=mainStatus.attempts.filter(x=>x.profile==='main'&&x.operation==='crisis');
  check(mainCalls.length===10&&new Set(mainCalls.map(x=>x.crisis_number)).size===10,'exactly_once_ten_crises');
  await record('victory_review',{crises:10,metrics:terminal.metrics,score:terminal.summary.consensus_score,chronological:true,narrative_rendered:true,terminal_restart_preserved:true,no_extra_crisis_generation:true});
  stage='defeat';await control('profile',null,{profile:'defeat'});
  // Fresh independent identities for the collapse mission, created through UI.
  await Promise.all(contexts.map(c=>c.close()));
  contexts=await Promise.all([0,1,2].map(i=>browser.newContext({viewport:i===2?{width:390,height:844}:{width:1440,height:900},hasTouch:i===2,isMobile:i===2,reducedMotion:'reduce'})));pages=await Promise.all(contexts.map(observed));
  await pages[0].goto(base);await pages[0].getByLabel('Your callsign').fill('Collapse A');
  await poll(async()=>!(await pages[0].locator('option[value=generated]').isDisabled()),'defeat_available');
  await pages[0].getByLabel('Mission mode').selectOption('generated');await pages[0].getByRole('button',{name:'Create Mission',exact:true}).click();await phase('lobby',0,[pages[0]]);
  const defeatInvite=pages[0].url();for(let i=1;i<3;i++){await pages[i].goto(defeatInvite);await pages[i].getByLabel('Your callsign').fill('Collapse '+i);await pages[i].getByRole('button',{name:'Join Mission',exact:true}).click();await phase('lobby',0,[pages[i]]);}
  await poll(async()=>(await state(pages[0])).players.filter(p=>p.connected).length===3,'collapse_lobby');
  await pages[0].getByRole('button',{name:'Start Mission',exact:true}).click();await phase('briefing',1);
  for(let n=1;n<=3;n++){await openVote(n);await vote(['A','A','A']);await phase(n===3?'failed':'decision_locked',n);if(n<3)await next(n+1);}
  const failed=(await common())[0];check(failed.metrics.infrastructure===0&&failed.summary.outcome==='defeat'&&failed.history.length===3,'collapse_at_zero');
  await pages[0].getByText('AI-generated interpretation. Statistics and recorded decisions are shown separately.',{exact:true}).waitFor();
  check(failed.summary.consensus_score===Object.values(failed.metrics).reduce((a,b)=>a+b,0)/4,'defeat_score');
  await renderedReview(failed);
  await shot(pages[0],'early-defeat');await layouts(pages[0],'defeat');
  const endStatus=await control('status',failed.token);check(endStatus.attempts.filter(x=>x.profile==='defeat'&&x.operation==='crisis').length===3,'no_crisis_after_defeat');
  await refresh(1,'failed',3);await record('early_defeat',{crises:3,collapsed_metric:'infrastructure',metrics:failed.metrics,score:failed.summary.consensus_score,no_extra_crisis_generation:true});
  check(consoles.pageErrors===0,'unexpected_page_errors');
  if(process.argv.includes('--require-clean'))check(defects.length===0,'usability_regression_findings');
  await writeFile(join(output,'server-diagnostics.json'),JSON.stringify({main:mainStatus,defeat:endStatus},null,2)+'\n');
  await record('complete',{browser_console_error_count:consoles.errors,uncaught_page_errors:consoles.pageErrors,findings:defects.length,real_provider_requests:0});
  await writeFile(join(output,'result.json'),JSON.stringify({status:'completed',findings:defects.length,headless:true,mode:fastRegression?'fast-fake-regression':'realistic-delay-acceptance',real_provider_requests:0},null,2)+'\n');
  console.log(JSON.stringify({status:'completed',findings:defects.length,evidence:output}));
}catch(error){
  await writeFile(join(privateDir,'failure.txt'),String(error.stack||error),{mode:0o600});
  await writeFile(join(output,'result.json'),JSON.stringify({status:'failed',stage,error_category:error.message?.startsWith('page.')?'browser_operation_failed':String(error.message).split('\n')[0].replace(/https?:\/\/\S+/g,'[redacted-url]'),private_diagnostics_retained:true,real_provider_requests:0},null,2)+'\n');
  console.log(JSON.stringify({status:'failed',stage,private_diagnostics:privateDir}));process.exitCode=1;
}finally{await browser?.close();await stop();}
