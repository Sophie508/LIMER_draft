"""Posthoc timing description only; never retune frozen validation rules."""
from pathlib import Path
import json

ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
metrics=json.loads((ROOT/'logs/m7_validation_v3_metrics.json').read_text())
rows=[]
for r in metrics['rows']:
    if not r['configured_loss_pct'] or r['within100ms']:
        continue
    previous=None;first_delta=None;feedback=[];idle=[];fault=None
    with (ROOT/'mininet_results'/r['name']/'events.jsonl').open() as stream:
        for line in stream:
            e=json.loads(line)
            if e['event']=='FAULT_APPLIED':fault=e['record']['t_after_ns']
            if e['event']!='HOST_TCP_SAMPLE' or e['rank']!=2 or e['fabric']!='A' or e['status']!='ok':
                continue
            if fault is not None:
                t=(e['sample_t_monotonic_ns']-fault)/1e6
                if previous is not None and e['total_retrans']>previous['total_retrans'] and first_delta is None:
                    first_delta=t
                if t <= r['confirmation_ms'] and previous is not None:
                    dsack=e['dsack_dups']-previous['dsack_dups']
                    reorder=e['reord_seen']-previous['reord_seen']
                    if dsack>0 or reorder>0:feedback.append(dict(t_ms=t,dsack_delta=dsack,reorder_delta=reorder))
                    if e['unacked']==0:idle.append(t)
            previous=e
    rows.append(dict(name=r['name'],confirmation_ms=r['confirmation_ms'],
                     first_new_retrans_ms=first_delta,first_nonzero_kernel_lost_ms=r['first_kernel_lost_ms'],
                     feedback_before_decision=feedback,idle_samples_before_decision=len(idle),
                     sample_max_gap_ms=r['sample_interval_max_ms']))
out=dict(boundary='Posthoc trace description; no frozen-rule retuning or causal proof of physical loss/delay.',rows=rows)
(ROOT/'logs/m7_tail_diagnostics.json').write_text(json.dumps(out,indent=2)+'\n')
for row in rows:print(row['name'],row['first_new_retrans_ms'],row['first_nonzero_kernel_lost_ms'],row['confirmation_ms'],row['feedback_before_decision'][:5])
