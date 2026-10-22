"""Export readable grouped conditions without inventing or dropping trials."""
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT/'handoff/conditions'
    output.mkdir(exist_ok=True)
    campaigns = {
        'm13_adaptive_validation': 'artifacts/m13/runs/m13_adaptive_validation_v1/registration.json',
        'm13_high_controls': 'artifacts/m13/runs/m13_adaptive_high_controls_v1/registration.json',
        'm13_constant_validation': 'artifacts/m13/runs/m13_coverage_validation_v1/registration.json',
        'm13_original_budget_development': 'artifacts/m13/runs/m13_development_v2/registration.json',
        'm13_equal_budget_representative': 'artifacts/m13/runs/m13_representative_v1/registration.json',
        'm12_validation': 'artifacts/m12/m12_validation_v2/registration.json',
        'm12_boundary': 'artifacts/m12/m12_boundary_v2/registration.json',
        'm8_validation': 'artifacts/server/runs/m8_validation_v1/registration.json',
        'm8_stress': 'artifacts/server/runs/m8_stress_v1/registration.json',
        'm9_execution': 'artifacts/server/runs/m9_execution_v1/registration.json',
        'm11_closed_loop': 'artifacts/server/runs/m11_closed_loop_v1/registration.json',
    }
    index = {}
    for name, relative in campaigns.items():
        source = ROOT/relative
        document = json.loads(source.read_text())
        rows = document.get('trials', document.get('cases'))
        groups = defaultdict(list)
        for row in rows:
            groups[row.get('condition', row.get('id'))].append(row)
        summaries = []
        for condition, trials in groups.items():
            # A key is common only if every registered attempt agrees.
            common = {key:value for key,value in trials[0].items() if key not in ('id','runId','faultTimeMs') and all(row.get(key)==value for row in trials)}
            summary = dict(condition=condition, registered=len(trials), **{k:v for k,v in common.items() if k!='condition'})
            ids = [row['runId'] for row in trials if 'runId' in row]
            if ids:summary.update(runId_min=min(ids), runId_max=max(ids))
            summaries.append(summary)
        fields = ['condition','registered'] + sorted(set().union(*(set(s) for s in summaries))-{'condition','registered'})
        with (output/(name+'.tsv')).open('w',newline='') as handle:
            writer = csv.DictWriter(handle,fieldnames=fields,delimiter='\t')
            writer.writeheader()
            writer.writerows({key:json.dumps(value,ensure_ascii=False) if isinstance(value,(list,dict)) else value for key,value in row.items()} for row in summaries)
        index[name] = dict(registration=relative, sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            registered=len(rows), groups=len(groups), kinds=dict(Counter(row.get('kind','engineering_case') for row in rows)))
    cpu_source = ROOT/'artifacts/frozen/limer_source_m7_tcp_v3/configs/m7_validation_v3'
    fields = ['config','fault_loss_pct','m7_control','tcp_delivery_interval_s','post_fault_rounds','tcp_loss_detector']
    cpu_files = sorted(cpu_source.glob('*.json'))
    with (output/'m7_validation_configs.tsv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,delimiter='\t');writer.writeheader()
        for path in cpu_files:
            config=json.loads(path.read_text())
            writer.writerow(dict(config=str(path.relative_to(ROOT)),**{k:config.get(k,'') for k in fields[1:]}))
    index['m7_validation_configs']=dict(source=str(cpu_source.relative_to(ROOT)),configs=len(cpu_files),
        note='Generated input configurations, not a new outcome denominator. See original validation registration and stress ledgers.')
    (output/'index.json').write_text(json.dumps(index,indent=2)+'\n')
    print('Exported',len(index),'condition matrices from frozen registrations.')


if __name__ == '__main__':main()
