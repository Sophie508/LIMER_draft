"""Offline scoring only: fault timing/location never enters the worker rule."""
from pathlib import Path
from collections import defaultdict
import json,statistics,math
ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
rows=[]
for folder in sorted((ROOT/'mininet_results').glob('m7_*')):
 if not (folder/'summary.json').exists() or not (folder/'events.jsonl').exists():continue
 config=json.loads((folder/'config.json').read_text()) if (folder/'config.json').exists() else None
 # Normalized config is archived in manifest, or recover it from the run registration.
 manifest=json.loads((folder/'manifest.json').read_text())
 config=manifest.get('config',config)
 if config is None:raise ValueError('missing config '+folder.name)
 samples=[];alarms=[];fault=None;start=None;end=None;per_connection=defaultdict(list)
 with (folder/'events.jsonl').open() as f:
  for line in f:
   e=json.loads(line)
   if e['event']=='FAULT_APPLIED':fault=e['record']['t_after_ns']
   if e['event']=='HOST_TCP_LOSS_CONFIRM':alarms.append(e)
   if e['event']=='HOST_TCP_SAMPLE':
    samples.append(e);per_connection[(e['rank'],e['fabric'],e['connection_generation'])].append(e['sample_t_monotonic_ns'])
 if fault is None:continue
 loss=config.get('fault_loss_pct',0)
 target=next((e for e in alarms if e['rank']==2 and e['fabric']=='A' and e['decision_t_monotonic_ns']>=fault),None) if loss else None
 false=[e for e in alarms if not loss or e['rank']!=2 or e['fabric']!='A' or e['decision_t_monotonic_ns']<fault]
 lat=(target['decision_t_monotonic_ns']-fault)/1e6 if target else None
 gaps=[(b-a)/1e6 for times in per_connection.values() for a,b in zip(times,times[1:])]
 lifetime=(max(e['sample_t_monotonic_ns'] for e in samples)-min(e['sample_t_monotonic_ns'] for e in samples))/1e9 if samples else 0
 connection_seconds=sum((max(times)-min(times))/1e9 for times in per_connection.values())
 summary=json.loads((folder/'summary.json').read_text());correctness=json.loads((folder/'correctness.json').read_text())
 target_samples=[e for e in samples if e['rank']==2 and e['fabric']=='A' and e['sample_t_monotonic_ns']>=fault and e.get('status')=='ok']
 def first(predicate):
  e=next((s for s in target_samples if predicate(s)),None)
  return (e['sample_t_monotonic_ns']-fault)/1e6 if e else None
 row=dict(name=folder.name,status=summary['status'],correctness=correctness['status'],configured_loss_pct=loss,control=config.get('m7_control'),tcp_loss_detector=config.get('tcp_loss_detector'),rule_version=alarms[0]['rule_version'] if alarms else ('tcp-loss-v3' if any(x in folder.name for x in ['rule_v3','val_v3','stress_v3']) else ('tcp-loss-v2' if any(x in folder.name for x in ['rule_v2','val_v2','stress_v2']) else 'tcp-loss-v1')),confirmed=target is not None,confirmation_ms=lat,within100ms=lat is not None and 0<=lat<100,false_alarm_count=len(false),all_alarm_count=len(alarms),alarms=[{k:e.get(k) for k in ['rank','fabric','decision_t_monotonic_ns','evidence_age_ms','evidence']} for e in alarms],samples=len(samples),unavailable_samples=sum(s.get('status')!='ok' for s in samples),observation_seconds=lifetime,connection_seconds=connection_seconds,sample_interval_median_ms=statistics.median(gaps) if gaps else None,sample_interval_max_ms=max(gaps,default=None),gaps_over15ms=sum(g>15 for g in gaps),first_kernel_lost_ms=first(lambda s:s['lost']>0),first_dsack_ms=first(lambda s:s['dsack_dups']>0),baseline_durations_s=summary.get('baseline',{}).get('duration_s'),first_host_log_receipt_ms=(target['received_t_monotonic_ns']-fault)/1e6 if target else None)
 rows.append(row)
(ROOT/'logs/m7_tcp_analysis.json').write_text(json.dumps(rows,indent=2)+'\n')
for r in rows:print(r['name'],r['status'],r['confirmation_ms'],r['false_alarm_count'],r['first_kernel_lost_ms'],r['gaps_over15ms'])
