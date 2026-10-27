import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import App from '../src/App';
import { CrisisHistoryEntry, MetricsTimeline, MissionReview, MetricDelta, metricChartLayout } from '../src/MissionReview';
import { SnapshotOrder } from '../src/snapshotOrder';
import type { CrisisResult, LobbyState } from '../src/types';

function fixture(defeat=false): LobbyState {
  const before={infrastructure:70,public_trust:70,economy:70,safety:70};
  const after={infrastructure:75,public_trust:67,economy:defeat?0:63,safety:72};
  const decision: CrisisResult['decision']={choice_id:'B',reason:'final_plurality',round_id:'final',totals:{A:1,B:2,C:0},abstentions:0,ai_followed:false};
  const result: CrisisResult={id:'final',crisis_id:'grid-under-pressure',crisis_number:1,crisis_title:'Grid Under Pressure',briefing:'Extreme heat threatens grid stability.',
    choices:[{id:'A',title:'Concentrate cuts',description:'Disconnect selected demand.'},{id:'B',title:'Distribute the Burden',description:'Rotate outages.'},{id:'C',title:'Preserve Service',description:'Use reserves.'}],
    ai_recommendation_choice_id:'A',choice_title:'Distribute the Burden',choice_description:'Rotate outages.',outcome:'Rotating outages spread the burden.',decision,
    before,after,authored_deltas:{infrastructure:5,public_trust:-3,economy:-7,safety:2},applied_deltas:{infrastructure:5,public_trust:-3,economy:defeat?-70:-7,safety:2},
    consensus_window_occurred:true,final_vote_occurred:true,status:defeat?'collapsed':'resolved',
    voting_rounds:[{round_id:'initial',number:1,totals:{A:1,B:1,C:1},abstentions:0,eligible_count:3},{round_id:'final',number:2,totals:{A:1,B:2,C:0},abstentions:0,eligible_count:3}]};
  return {token:'review',revision:20,phase:defeat?'failed':'completed',crisis_number:1,crisis_count:1,result,collapsed_metrics:defeat?['economy']:[],consensus_score:defeat?null:69.25,
    server_now:1000,deadline:null,chat:[],voting:null,closed_rounds:[],decision,roles:['safety'],crisis:null,private_intelligence:{safety:'PRIVATE REPORT MUST NOT RENDER'},
    host_id:'host',you:'guest',metrics:after,players:[],history:[result],metrics_timeline:[{crisis_number:0,metrics:before},{crisis_number:1,metrics:after}],
    summary:{outcome:defeat?'defeat':'victory',crises_completed:1,total_crises:1,final_metrics:after,consensus_score:defeat?53.5:69.25,consensus_windows:1,final_vote_crises:1,
      resolution_breakdown:{initial_plurality:0,final_plurality:1,ai_tie_break:0,no_vote_ai_fallback:0}}};
}
function renderApp(mission: LobbyState) {
  globalThis.__testLobby={mission,status:'Connected',rejected:false,actionError:'',clockSample:null,sendIntent:()=>{throw new Error('Review must not send gameplay intents');}};
  return renderToStaticMarkup(<App />);
}

test('victory review prominently displays authoritative outcome, completion, score and final metrics',()=>{
  const mission=fixture(); mission.summary!.consensus_score=42.25;
  const html=renderApp(mission);
  for(const label of ['Civilization Survived','MISSION COMPLETE','Crises completed:','1 / 1','42.25 / 100','Infrastructure','Public Trust','Economy','Safety']) assert.ok(html.includes(label),label);
  assert.equal((html.match(/Final Consensus Score:/g)||[]).length,1);
  assert.ok(html.indexOf('Final Consensus Score:')<html.indexOf('Civilization performance'));
});
test('defeat review explicitly remains defeat despite a numerical score and preserves zero outcome',()=>{
  const html=renderApp(fixture(true));
  assert.ok(html.includes('Civilization Collapsed') && html.includes('The mission ended in defeat.'));
  assert.ok(html.includes('53.5 / 100') && html.includes('Economy: −70'));
  assert.ok(html.includes('Crisis status: collapsed'));
  assert.ok(!html.includes('Civilization Survived') && !html.includes('MISSION COMPLETE'));
});
test('terminal review has no chat composer, voting or progression controls and retains return navigation',()=>{
  for(const defeat of [false,true]) {
    const html=renderApp(fixture(defeat));
    for(const unwanted of ['<textarea','type="radio"','Submit private vote','Submit Final Vote','Send message','Next crisis','Finish mission','PRIVATE REPORT MUST NOT RENDER']) assert.ok(!html.includes(unwanted),unwanted);
    assert.ok(html.includes('Return to mission creation') && html.includes('href="/"'));
  }
});
test('timeline includes starting snapshot and every recorded point with exact table values and labeled distinct patterns',()=>{
  const html=renderToStaticMarkup(<MetricsTimeline snapshots={fixture().metrics_timeline!}/>);
  assert.ok(html.includes('viewBox="0 0 720 250"'));
  assert.ok(html.includes('Metric progression — exact recorded values'));
  assert.equal((html.match(/<polyline/g)||[]).length,4);
  assert.equal((html.match(/<circle/g)||[]).length,8);
  assert.ok(html.includes('Start') && html.includes('>70</td>') && html.includes('>63</td>'));
  for(const name of ['Infrastructure','Public Trust','Economy','Safety']) assert.ok(html.includes(`aria-label="${name}"`));
  for(const dash of ['9 4','3 4','12 3 2 3']) assert.ok(html.includes(`stroke-dasharray="${dash}"`));
  assert.ok(html.includes('role="region"') && html.includes('tabindex="0"'));
});
test('native collapsed crisis details expose summary and expandable public context without mutating state',()=>{
  const mission=fixture(); const original=JSON.stringify(mission);
  const element=CrisisHistoryEntry({result:mission.history![0]});
  assert.equal(element.type,'details'); assert.equal(element.props.open,undefined);
  const html=renderToStaticMarkup(element);
  assert.ok(html.includes('<summary>') && html.includes('Expand / collapse details'));
  for(const label of ['Grid Under Pressure','B — Distribute the Burden','Extreme heat threatens grid stability.','Concentrate cuts','Preserve Service','AI recommended']) assert.ok(html.includes(label));
  assert.equal(JSON.stringify(mission),original);
});
test('history distinguishes initial and final vote totals, consensus, abstentions and actual applied metric changes',()=>{
  const mission=fixture(true); mission.history![0].voting_rounds![1].abstentions=1;
  const html=renderToStaticMarkup(<CrisisHistoryEntry result={mission.history![0]}/>);
  for(const label of ['Initial vote','Final vote','Choice A: 1','Choice B: 2','Abstentions: 1','Eligible seats: 3','Consensus Window: Yes','Final voting round: Yes','Before and after — actual applied changes','−70']) assert.ok(html.includes(label),label);
  assert.ok(html.indexOf('Initial vote')<html.indexOf('Final vote</h4>'));
});
test('team statistics use the authoritative summary without player rankings',()=>{
  const html=renderApp(fixture());
  for(const label of ['Resolved crises','Consensus windows','Crises with final voting','Initial plurality','Final-vote plurality','AI tie-break after final tie','No-vote AI fallback']) assert.ok(html.includes(label));
  assert.ok(!html.includes('ranking') && !html.includes('Best player'));
});
test('reconnecting after completion renders the same authoritative review',()=>{
  const mission=fixture(); const original=renderApp(mission);
  assert.equal(renderApp(JSON.parse(JSON.stringify(mission))),original);
});
test('missing optional historical context renders unavailable labels, not invented data',()=>{
  const mission=fixture(); const record=mission.history![0];
  delete record.briefing; delete record.choices; delete record.voting_rounds;
  delete record.consensus_window_occurred; delete record.final_vote_occurred; delete record.status;
  const html=renderApp(mission);
  for(const label of ['Original briefing unavailable.','Original choice list unavailable.','Separate round tallies unavailable.','Consensus Window: Not recorded','Deciding vote:','Crisis status: Not recorded']) assert.ok(html.includes(label),label);
  delete mission.history; delete mission.metrics_timeline;
  const missing=renderApp(mission);
  assert.ok(missing.includes('Decision history unavailable.') && missing.includes('Metric timeline unavailable.'));
});
test('historical text is escaped and chronologically ordered using stable records',()=>{
  const mission=fixture();
  mission.history!.push({...mission.history![0],id:'second',crisis_number:2,crisis_title:'Second <script>alert(1)</script>',briefing:'<img src=x onerror=alert(1)>'});
  const html=renderApp(mission);
  assert.ok(html.indexOf('Crisis 1 —')<html.indexOf('Crisis 2 —'));
  assert.ok(html.includes('&lt;script&gt;') && !html.includes('<script>'));
  assert.ok(!html.includes('<img src=x'));
});
test('snapshot ordering rejects duplicate and stale terminal regressions without merging history',()=>{
  const order=new SnapshotOrder(); const final=fixture();
  assert.equal(order.accept({...final,revision:18}),true);
  assert.equal(order.accept(final),true);
  assert.equal(order.accept(JSON.parse(JSON.stringify(final))),false);
  assert.equal(order.accept({...final,revision:19,phase:'discussion',history:[]}),false);
  assert.equal(order.accept({...final,revision:21}),true);
  assert.equal(order.accept({...final,revision:NaN}),false);
  assert.equal(order.accept({...final,revision:undefined}),false);
  assert.equal(new SnapshotOrder().accept({...final,revision:undefined}),true);
});

test('mobile review fits its chart and confines only wide tables to labeled scroll regions', async()=>{
  const {readFileSync}=await import('node:fs');
  const css=readFileSync('src/styles.css','utf8');
  const html=renderApp(fixture());
  assert.ok(html.includes('Metric trend chart; all recorded crisis points'));
  assert.ok(html.includes('Swipe or scroll the table sideways for all columns.'));
  assert.match(css,/\.review-chart\s*\{[^}]*width: 100%;[^}]*min-width: 0;/);
  assert.match(css,/\.metrics-trend\s*\{[^}]*width: 100%;[^}]*min-width: 0;/);
  assert.match(css,/\.review-table\s*\{[^}]*max-width: 100%;[^}]*overflow-x: auto;/);
  assert.match(css,/@media \(max-width: 400px\)\s*\{\s*\.review-final-metrics, \.review-statistics \{ grid-template-columns: minmax\(0, 1fr\);/);
});

test('live victory and defeat snapshots render full review and survive stale snapshot replay', {skip:!process.env.MISSION_REVIEW_FILE}, async()=>{
  const {readFileSync}=await import('node:fs');
  const evidence=JSON.parse(readFileSync(process.env.MISSION_REVIEW_FILE!,'utf8'));
  for(const [label,count] of [['victory',10],['defeat',4]] as const) {
    const mission={...fixture(label==='defeat'),...evidence[label]} as LobbyState;
    const html=renderApp(mission);
    assert.equal((html.match(/class="history-entry"/g)||[]).length,count);
    assert.equal((html.match(/<circle/g)||[]).length,(count+1)*4);
    assert.ok(html.includes(label==='victory'?'55.75 / 100':'54.5 / 100'));
    assert.equal(html,renderApp(JSON.parse(JSON.stringify(mission))));
    assert.ok(!html.includes('<textarea') && !html.includes('type="radio"'));
    const order=new SnapshotOrder();
    assert.ok(order.accept({...mission,revision:100}));
    assert.equal(order.accept({...mission,revision:99,phase:'discussion',history:[]}),false);
  }
});

test('metric deltas retain explicit signs and names with positive, negative and neutral styling',()=>{
  for(const [value,direction,sign] of [[8,'positive','+8'],[-8,'negative','−8'],[0,'neutral','0']] as const) {
    const html=renderToStaticMarkup(<MetricDelta name="Infrastructure" value={value}/>);
    assert.ok(html.includes(`metric-delta--${direction}`));
    assert.ok(html.includes(`aria-label="Infrastructure: ${sign}"`));
    assert.ok(html.includes(`<strong>${sign}</strong>`));
  }
});

test('collapsed and expanded history use identical applied delta badges without changing recorded values',()=>{
  const mission=fixture(); const result=mission.history![0]; result.applied_deltas.safety=0;
  const before=JSON.stringify(mission);
  const html=renderToStaticMarkup(<CrisisHistoryEntry result={result}/>);
  // Four summary badges plus the same four badges in the detailed metric table.
  assert.equal((html.match(/aria-label="Infrastructure: \+5"/g)||[]).length,2);
  assert.equal((html.match(/aria-label="Public Trust: −3"/g)||[]).length,2);
  assert.equal((html.match(/aria-label="Safety: 0"/g)||[]).length,2);
  assert.equal((html.match(/metric-delta--positive/g)||[]).length,2);
  assert.equal((html.match(/metric-delta--negative/g)||[]).length,4);
  assert.equal((html.match(/metric-delta--neutral/g)||[]).length,2);
  assert.equal(JSON.stringify(mission),before);
});

for(const viewport of [320,375,390,430,768,1120]) {
  test(`chart layout fits ${viewport}px viewport model with complete data and readable tick spacing`,()=>{
    // Model the existing main/card padding, not a browser's layout calculation.
    const inner=viewport-(viewport<=700?82:106);
    const count=11; const layout=metricChartLayout(inner,count);
    assert.ok(layout.left>=36 && layout.right<inner);
    const coordinates=Array.from({length:count},(_,i)=>layout.x(i));
    assert.equal(coordinates.length,11);
    assert.ok(coordinates.every((x,i)=>x>=layout.left && x<=layout.right && (i===0 || x>coordinates[i-1])));
    assert.equal(layout.tickIndices[0],0); assert.equal(layout.tickIndices.at(-1),10);
    assert.ok(layout.fontSize>=12);
    if(inner<600) {
      assert.ok(layout.tickIndices.length<11);
      assert.ok(layout.tickIndices.slice(1).every((tick,i)=>layout.x(tick)-layout.x(layout.tickIndices[i])>=48));
    } else assert.equal(layout.tickIndices.length,11);
  });
}

test('responsive chart preserves every series value, point title, order, color and pattern',()=>{
  const snapshots=Array.from({length:11},(_,i)=>({crisis_number:i,metrics:{infrastructure:70+i,public_trust:70-i,economy:70-i*2,safety:70+i*2}}));
  const original=JSON.stringify(snapshots);
  const html=renderToStaticMarkup(<MetricsTimeline snapshots={snapshots}/>);
  assert.equal((html.match(/<circle/g)||[]).length,44);
  assert.equal((html.match(/<polyline/g)||[]).length,4);
  for(const [name,color,dash,key] of [['Infrastructure','#b4d8fa','','infrastructure'],['Public Trust','#dec7f5','9 4','public_trust'],['Economy','#f3d392','3 4','economy'],['Safety','#a7e3d6','12 3 2 3','safety']] as const) {
    assert.ok(html.includes(`stroke="${color}"`)); assert.ok(html.includes(`stroke-dasharray="${dash}"`));
    for(const s of snapshots) { const title=`${name}, ${s.crisis_number===0?'Start':`Crisis ${s.crisis_number}`}: ${s.metrics[key]}`; assert.ok(html.includes(title),`${title} absent; titles: ${html.match(/<title>.*?<\/title>/g)?.slice(0,4).join(' ')}`); }
  }
  assert.equal(JSON.stringify(snapshots),original);
});

test('review tables preserve headings without word splits and align numeric values in their own overflow region', async()=>{
  const {readFileSync}=await import('node:fs'); const css=readFileSync('src/styles.css','utf8');
  const html=renderApp(fixture());
  assert.ok(html.includes('Metric progression values; scroll for all columns'));
  assert.ok(html.includes('Crisis 1 metric changes; scroll for all columns'));
  for(const heading of ['Infrastructure','Public Trust','Economy','Safety']) assert.ok(html.includes(`<th scope="col">${heading}</th>`));
  assert.match(css,/\.review-table th \{[^}]*white-space: nowrap;[^}]*overflow-wrap: normal;/);
  assert.match(css,/\.review-table table \{[^}]*min-width: 36rem;/);
  assert.match(css,/\.review-table th, \.review-table td \{[^}]*text-align: right;[^}]*font-variant-numeric: tabular-nums;/);
});

test('long expanded content and keyboard-native summaries keep wrapping and visible touch/focus affordances', async()=>{
  const {readFileSync}=await import('node:fs'); const css=readFileSync('src/styles.css','utf8');
  const result=fixture().history![0]; result.briefing='VeryLongUnbrokenContext'.repeat(40);
  result.choices![0].description='Long choice details '.repeat(40);
  const html=renderToStaticMarkup(<CrisisHistoryEntry result={result}/>);
  assert.ok(html.includes(result.briefing) && html.includes(result.choices![0].description));
  assert.ok(html.includes('<details') && html.includes('<summary>') && !html.includes('tabindex="-1"'));
  assert.match(css,/\.history-entry summary \{[^}]*min-height: 48px;/);
  assert.match(css,/:focus-visible \{[^}]*outline: 3px solid/);
  assert.match(css,/\.history-context p, \.history-context li, \.history-entry summary \{ overflow-wrap: anywhere;/);
  assert.match(css,/\.history-entry summary \.history-changes \{[^}]*flex-wrap: wrap;/);
});

test('review renders only authoritative narrative outcome and recorded notable decisions', () => {
  const mission=fixture();
  mission.summary!.narrative_outcome='The city survived. Earlier decision — Grid Under Pressure: Distribute the Burden.';
  mission.summary!.notable_decisions=[{crisis_number:1,crisis_title:mission.result!.crisis_title,choice_title:mission.result!.choice_title,outcome:mission.result!.outcome}];
  const html=renderToStaticMarkup(<MissionReview mission={mission} />);
  assert.ok(html.includes('aria-label="Mission narrative outcome"'));
  assert.ok(html.includes(mission.summary!.narrative_outcome));
  assert.ok(html.includes('aria-label="Notable decisions"'));
  assert.ok(html.includes(mission.result!.choice_title)&&html.includes(mission.result!.outcome));
  assert.ok(!html.includes('PRIVATE REPORT MUST NOT RENDER'));
  delete mission.summary!.narrative_outcome;delete mission.summary!.notable_decisions;
  const legacy=renderToStaticMarkup(<MissionReview mission={mission} />);
  assert.ok(!legacy.includes('aria-label="Mission narrative outcome"')&&!legacy.includes('aria-label="Notable decisions"'));
});
test('review narrative escapes authored text without fabricating additional events', () => {
  const mission=fixture(true);mission.summary!.narrative_outcome='Safety failed <script>never execute</script>';
  mission.summary!.notable_decisions=[];
  const html=renderToStaticMarkup(<MissionReview mission={mission} />);
  assert.ok(html.includes('&lt;script&gt;never execute&lt;/script&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('aria-label="Notable decisions"'));
});

test('expanded real-process campaign review matches its authoritative captured history and summary', {skip:!process.env.EXPANSION_REVIEW_FILE}, async()=>{
  const {readFileSync}=await import('node:fs');
  const evidence=JSON.parse(readFileSync(process.env.EXPANSION_REVIEW_FILE!,'utf8'));
  const mission={...fixture(),...evidence};
  const html=renderToStaticMarkup(<MissionReview mission={mission} />);
  assert.equal((html.match(/class="history-entry"/g)||[]).length,10);
  assert.ok(html.includes(renderToStaticMarkup(<p className="outcome-narrative">{evidence.summary.narrative_outcome}</p>)));
  assert.equal(evidence.summary.consensus_score,Object.values(evidence.metrics).reduce((sum:number,value:any)=>sum+value,0)/4);
  for(const highlight of evidence.summary.notable_decisions){
    const record=evidence.history[highlight.crisis_number-1];assert.equal(highlight.outcome,record.outcome);
    assert.ok(html.includes(record.choice_title));
  }
});
