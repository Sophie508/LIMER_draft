"""Descriptive independent healthy on/off references; no causal overhead estimate."""
from pathlib import Path
import json
import statistics

ROOT = Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
groups = {}
for label, prefix in [('on', 'm7_val_v3_'), ('off', 'm7_sensor_off_v3_')]:
    rows = []
    for rep in range(1, 6):
        name = f'{prefix}nominal_rep{rep:02d}'
        status = json.loads((ROOT/'logs'/f'{name}.status.json').read_text())
        assert 'exit_code' in status
        durations = status.get('summary', {}).get('baseline', {}).get('duration_s', [])
        rows.append(dict(name=name, exit_code=status['exit_code'],
                         status=status.get('summary', {}).get('status'),
                         correctness=status.get('correctness', {}).get('status'),
                         baseline_duration_s=durations,
                         median_baseline_duration_s=statistics.median(durations) if durations else None))
    finite = [r['median_baseline_duration_s'] for r in rows if r['median_baseline_duration_s'] is not None]
    groups[label] = dict(registered=5, completed_correct=sum(r['exit_code']==0 and r['correctness']=='pass' for r in rows),
                         median_run_baseline_duration_s=statistics.median(finite) if finite else None,
                         min_run_baseline_duration_s=min(finite, default=None),
                         max_run_baseline_duration_s=max(finite, default=None), rows=rows)
out = dict(groups=groups,
           on_to_off_median_ratio=groups['on']['median_run_baseline_duration_s']/groups['off']['median_run_baseline_duration_s'],
           boundary='Five independent unpaired lifecycles per arm; descriptive timing only. No causal CPU/logging overhead or confidence claim.')
(ROOT/'logs/m7_reference_cost.json').write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='groups'}))
