"""Descriptive counter analysis, no fitted trigger or held-out efficacy claim."""
from collections import Counter,defaultdict
import json
from pathlib import Path
import statistics

ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')


def analyze(folder):
    samples=[];fault=None;events=Counter();periods=[]
    for line in (folder/'events.jsonl').open():
        e=json.loads(line);events[e['event']]+=1
        if e['event']=='FAULT_APPLIED':fault=e['record']['t_after_ns']
        if e['event']=='HOST_RETRANS_SAMPLE':samples.append(e)
        if e['event']=='ROUND_COMMAND':periods.append((e['round_id'],e['period']))
    result={'name':folder.name,'event_counts':dict(events),'fault_after_ns':fault,
            'sample_count':len(samples),'round_commands':periods,
            'note':'Raw positive deltas are signal observations, not a validated fault detector.'}
    result['unavailable_samples']=sum(s['status']!='ok' for s in samples)
    grouped=defaultdict(list)
    for s in samples:grouped[s['rank'],s['fabric']].append(s)
    details={}
    for (rank,fabric),rows in grouped.items():
        available=[s for s in rows if s['status']=='ok']
        positive=[s for s in available if (s['retrans_delta'] or 0)>0]
        intervals=[s['sample_interval_ns']/1e6 for s in available if s['sample_interval_ns'] is not None]
        first=next((s for s in positive if fault is not None and s['sample_t_monotonic_ns']>=fault),None)
        pre=[s for s in positive if fault is not None and s['sample_t_monotonic_ns']<fault]
        details[f'{rank}:{fabric}']={'samples':len(rows),'available':len(available),
            'positive_delta_samples':len(positive),'summed_retrans_delta':sum(s['retrans_delta'] or 0 for s in available),
            'pre_episode_positive_samples':len(pre),'first_post_positive_delta_ms':
                 (first['sample_t_monotonic_ns']-fault)/1e6 if first else None,
            'first_post_interval_overlaps_injection':bool(first and first['sample_interval_ns'] is not None and
                first['sample_t_monotonic_ns']-first['sample_interval_ns']<fault),
            'sample_interval_median_ms':statistics.median(intervals) if intervals else None,
            'sample_interval_max_ms':max(intervals) if intervals else None,
            'observation_seconds':(rows[-1]['sample_t_monotonic_ns']-rows[0]['sample_t_monotonic_ns'])/1e9}
    result['connections']=details
    summary_path=folder/'summary.json'
    if summary_path.exists():
        summary=json.loads(summary_path.read_text());result['run_status']=summary.get('status')
        result['error']=summary.get('error');result['existing_detector']=summary.get('switch_detection')
    return result


results=[]
for folder in sorted((ROOT/'mininet_results').glob('m5_signal_*')):
    if (folder/'summary.json').exists():results.append(analyze(folder))
(ROOT/'logs/signal_pilot_descriptive.json').write_text(json.dumps(results,indent=2)+'\n')
print('completed folders',len(results),'raw signal samples',sum(r['sample_count'] for r in results))
for result in results:
    print(result['name'],result.get('run_status'),result['unavailable_samples'],
          result['connections'].get('2:A',{}).get('first_post_positive_delta_ms'))
