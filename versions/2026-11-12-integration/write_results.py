"""Generate the review tables from complete compact scoring receipts."""
import json
from pathlib import Path
import sys

root=Path(sys.argv[1]);groups=['development-v1','lifetime-full-v1','gray-full-v1']
reports=[json.loads((root/g/'report.json').read_text()) for g in groups]
assert all(r['not_run']==0 for r in reports),'registered attempts remain pending'
rows=[x for r in reports for x in r['rows']]
by_name={x['name']:x for x in rows}
fmt=lambda x:'unfinished' if x is None else f'{x:.2f}'
lines=['# Integration development results — 2026-11-12','',
 'These are declared development comparisons, with one shared physical input/seed per matched row. They are not independent repeat cohorts, statistical evidence of a general 95% guarantee, an external-system comparison or numerical AllReduce validation.','',
 f"Registered {len(rows)} attempts; {sum(x['valid'] for x in rows)} passed execution audit and independent observation replay (plus policy replay where applicable); {sum(x['status']=='completed' for x in rows)} communication jobs completed. Valid execution does not mean the job completed.",'',
 '## Matched four-phase module comparison','',
 '16 logical GPUs; 512 × 64 KiB chunks per rank per phase; four phases (2 GiB total logical payload), injection at 40 ms, 400 ms observation horizon. All values are communication ms from business launch, not detection latency. Unfinished jobs remain unfinished rather than receiving a fabricated completion time.','',
 '| Condition | G00 fixed | G10 adaptive | G01 fixed + recovery | G11 direct replacement | G11 benefit gate | A-only |',
 '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for family in ['healthy','blackhole','quarter','weak_loss','delay']:
    names=[f'matrix-{family}-{m}-{p}' for m,p in [('G00','always'),('G10','always'),('G01','always'),('G11','always'),('G11','benefit'),('A_ONLY','always')]]
    lines.append('| '+family+' | '+' | '.join(fmt(by_name[n]['completion_ms']) if by_name[n]['valid'] else 'invalid' for n in names)+' |')
lines+=['','## Full default 30-phase workload','',
 'Same 16-GPU model and 512-chunk phase size, 30 phases (15 GiB logical payload), injection at 40 ms and 2000 ms observation horizon. The separate lifetime and weak-loss follow-ups were registered before their execution; they are not replacements for short negative runs.','',
 '| Case | Completed | Communication ms | Fresh B-prime chunks completed | Phases with fresh B-prime | Fresh B-prime MiB |',
 '| --- | --- | ---: | ---: | ---: | ---: |']
for x in rows:
    if not x['name'].startswith('full-ring'):continue
    lines.append('| {} | {} | {} | {} | {} | {:.2f} |'.format(x['name'],x['status']=='completed',fmt(x['completion_ms']),x['fresh_Bprime_done'],x['fresh_Bprime_phases'],(x.get('fresh_Bprime_bytes') or 0)/1048576))
lines+=['','## Lifecycle/opportunity controls','',
 '| Chunks per phase | Phase count | Lifetime | Communication ms | Fresh B-prime completions |',
 '| ---: | ---: | --- | ---: | ---: |']
for x in rows:
    if x['name'].startswith('pilot'):
        lines.append('| {} | {} | {} | {} | {} |'.format(x['chunks'],x['phases'],x['lifetime'],fmt(x['completion_ms']),x['fresh_Bprime_done']))
faults=[x for x in rows if x['family']!='healthy'];healthy=[x for x in rows if x['family']=='healthy']
lines+=['','## Detection and interpretation','',
 f"{sum(x.get('detected_below_100ms',False) for x in faults)}/{len(faults)} fault-arm checks met the strict all-affected-path <100 ms rule, with no pre-fault or off-path alarm. These checks share seeds and workloads across policy arms and must not be counted as independent statistical trials.",
 f"Healthy-arm classifications: {', '.join(sorted(set(x.get('alarm_classification','invalid') for x in healthy)))} ({len(healthy)} matched/related runs).",'',
 '- Phase mode returns to original A/B eligibility at each existing scheduler barrier, retaining already observed physical-fault evidence. Original B is retired only within a committed phase binding.',
 '- Fresh B-prime completions require new chunk allocation, all three physical legs and the modeled source notification. Rescued suffixes are counted separately. A phase barrier waits for all declared logical work; no gradient values are computed.',
 '- The short control keeps zero fresh B-prime work and a lifecycle cost. Longer workloads create a genuine opportunity without holding A idle. More B-prime bytes alone are not evidence of better completion time.',
 '- Gating can reject a slower route but also delay repair. These tables retain both outcomes. A shorter communication time in a matched case does not establish restored healthy dual-plane throughput.',
 '- The v4 detection rules were unchanged. This is not a replacement for the October independent-cohort validation or a new general gray-fault coverage claim.',
 '- Compact receipts include audits and archive hashes. Raw packet archives are retained on otakotak; recomputing raw replay requires those archives.','']
(root/'RESULTS.md').write_text('\n'.join(lines))
print(json.dumps(dict(registered=len(rows),valid=sum(x['valid'] for x in rows),completed=sum(x['status']=='completed' for x in rows))))
