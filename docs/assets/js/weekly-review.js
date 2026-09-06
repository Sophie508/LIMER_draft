const campaignNames={results_restore_kpi_v3:'Prior v3 recovery',results_m3a_loss_sweep:'M3a switch cost',results_m4a_detect:'M4a loss detection',results_m4c_lossfast:'M4c faster loss detection',results_m4b_policy_v5:'M4b automatic policy'};
const designs=['Hard, cap, transient × 3','7 settings × 2 arms × 3','6 loss levels × 3','6 loss levels × 3','Switch and stay arms × 3'];
const fmt=(v,d=3)=>v===null||v===undefined?'—':Number(v).toFixed(d);
function row(id,values){const tr=document.createElement('tr');for(const v of values){const td=document.createElement('td');if(v instanceof Node)td.append(v);else td.textContent=String(v);tr.append(td);}document.querySelector(`#${id} tbody`).append(tr);return tr;}
async function load(){
  const response=await fetch('assets/weekly/evidence.json');if(!response.ok)throw new Error('Experiment records could not load.');
  const data=await response.json(),runs=data.records;
  document.getElementById('record-summary').textContent=`${runs.length} runs across these five campaigns, ${runs.filter(r=>r.status==='complete').length} completed. Completion is not the same as meeting a performance target. Older iterations and other repository campaigns are outside this denominator.`;
  data.campaigns.forEach((c,i)=>row('campaign-table',[campaignNames[c.name],designs[i],c.runs,c.complete]));
  runs.filter(r=>r.scenario==='AA7_HARD').forEach((r,i)=>row('hard-table',[i+1,fmt(r.detection_ms),r.detection_ms<1?'Yes':'No']));
  for(const loss of [.5,1,2,5,10,25]){const rs=runs.filter(r=>r.campaign==='results_m4c_lossfast'&&r.loss===loss);row('loss-table',[`${loss}%`,...rs.map(r=>fmt(r.detection_ms,1)),`${rs.filter(r=>r.detection_ms<100).length}/3`]);}
  runs.filter(r=>['AA7_HARD','AA8_GRAYFAST'].includes(r.scenario)).forEach(r=>row('recovery-table',[`${r.scenario==='AA7_HARD'?'Hard':'Rate cap'} / ${r.run.slice(-2)}`,fmt(r.commit_ms),fmt(r.first_step_ms)]));
  for(const r of runs){const link=document.createElement('a');link.href=`https://github.com/Sophie508/LIMER_draft/blob/main/${r.path}/summary.json`;link.textContent=r.path;link.target='_blank';link.rel='noopener';const tr=row('run-table',[link,`${r.loss}%`,`${r.bRate} Mbit/s`,r.status,fmt(r.detection_ms),fmt(r.commit_ms),fmt(r.first_step_ms),r.policy??'—',r.retention===null?'—':`${(r.retention*100).toFixed(2)}%`]);if(r.status==='failed')tr.className='failed';}
}
load().catch(e=>{const out=document.getElementById('load-error');out.hidden=false;out.textContent=e.message;});
