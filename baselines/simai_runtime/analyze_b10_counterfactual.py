"""Read-only episode accounting; failed arms have no finite completion value."""
import json
from pathlib import Path
ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
rows=[]
for folder in sorted((ROOT/'mininet_results').glob('m5_b10_fixed_*')):
    if not (folder/'summary.json').exists():continue
    summary=json.loads((folder/'summary.json').read_text())
    events=[json.loads(x) for x in (folder/'events.jsonl').read_text().splitlines()]
    fault=next(e['record']['t_after_ns'] for e in events if e['event']=='FAULT_APPLIED')
    rounds=[e for e in events if e['event']=='ROUND_AGGREGATED' and e['period']=='post_fault']
    done=summary['status']=='complete'
    correctness=json.loads((folder/'correctness.json').read_text())
    status=json.loads((ROOT/'logs'/f'{folder.name}.status.json').read_text())
    rows.append(dict(name=folder.name,status=summary['status'],error=summary.get('error'),
        exit_code=status.get('exit_code'),post_rounds=len(rounds),expected_post_rounds=8,
        post_bytes=sum(e['bytes_completed'] for e in rounds),
        episode_completion_s=(rounds[-1]['orchestrator_command_end_ns']-fault)/1e9 if done else None,
        last_observed_after_fault_s=max(e.get('t_monotonic_ns',fault) for e in events)/1e9-fault/1e9,
        correctness=correctness,latency=summary.get('latency'),
        changed_slots=summary.get('routing',{}).get('changed_slots'),
        source_hashes=status.get('hashes'),image_id=status.get('image_id')))
(ROOT/'logs/b10_counterfactual_analysis.json').write_text(json.dumps(rows,indent=2)+'\n')
for r in rows:print(r['name'],r['status'],r['post_rounds'],r['episode_completion_s'],r['correctness']['status'])
