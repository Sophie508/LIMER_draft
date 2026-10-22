import json
from pathlib import Path
from collections import defaultdict
ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
out={}
for campaign in ('coverage_development','coverage_validation','adaptive_development','adaptive_validation'):
 d=ROOT/'runs'/f'm13_{campaign}_v1'
 if not (d/'terminal.json').exists():continue
 t=json.loads((d/'terminal.json').read_text());reg=json.loads((d/'registration.json').read_text());groups=defaultdict(list)
 for trial in reg['trials']:
  sub=d/trial['id'];truth=json.loads((sub/'truth.json').read_text());alarms=[json.loads(s) for s in (sub/'baseline_alarms.jsonl').read_text().splitlines()]
  good=[a for a in alarms if trial['kind']=='fault' and a['path']==truth['fault_path'] and a['decision_t_ns']>=truth['fault_time_ns']]
  false=[a for a in alarms if trial['kind']!='fault' or a['path']!=truth['fault_path'] or a['decision_t_ns']<truth['fault_time_ns']]
  delay=(good[0]['decision_t_ns']-truth['fault_time_ns'])/1e6 if good else None
  # Actual bytes divided by the 249-ms source lifecycle; startup and lag included.
  costs=[p['probe_sent']*truth['probe_wire_bytes']*8/.249/1e6 for p in truth['paths']]
  groups[trial['condition']].append(dict(kind=trial['kind'],timely=delay is not None and delay<100,
    false=len(false),delay=delay,probe_min_Mbps=min(costs),probe_max_Mbps=max(costs),
    probe_bytes=sum(p['probe_sent']*truth['probe_wire_bytes'] for p in truth['paths']),
    data_bytes=sum(p['data_sent']*1500 for p in truth['paths'])))
 out[campaign]=dict(summary=t['summary'],matched_baseline={k:dict(n=len(v),timely=sum(x['timely'] for x in v),
   false_alarm_runs=sum(x['false']>0 for x in v),false_alarm_events=sum(x['false'] for x in v),
   probe_min_Mbps=min(x['probe_min_Mbps'] for x in v),probe_max_Mbps=max(x['probe_max_Mbps'] for x in v),
   actual_probe_to_data_bytes=sum(x['probe_bytes'] for x in v)/sum(x['data_bytes'] for x in v)) for k,v in groups.items()})
(ROOT/'logs/m13_new_envelopes_comparison.json').write_text(json.dumps(out,indent=2)+'\n')
for c,result in out.items():
 print(c,result['summary']['timely_faults'],result['summary']['primary_faults'])
 for k,v in result['matched_baseline'].items():print(k,v['timely'],v['n'],v['false_alarm_runs'],round(v['probe_min_Mbps'],2),round(v['probe_max_Mbps'],2))
