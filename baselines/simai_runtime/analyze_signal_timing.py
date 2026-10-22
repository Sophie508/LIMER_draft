"""Separate observer timing from reconstructed application activity, without fitting."""
from pathlib import Path
import csv,json
ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
rows=[]
for folder in sorted((ROOT/'mininet_results').glob('m5_signal_l*_r*')):
    events=[json.loads(l) for l in (folder/'events.jsonl').open()]
    fault=next(e['record']['t_after_ns'] for e in events if e['event']=='FAULT_APPLIED')
    steps=[e for e in events if e['event']=='STEP_DONE' and e['rank']==2 and e['send_route']=='A' and e['t_monotonic_ns']>=fault]
    active=min((e['t_monotonic_ns']-e['duration_ns'] for e in steps),default=None)
    samples=[e for e in events if e['event']=='HOST_RETRANS_SAMPLE' and e['rank']==2 and e['fabric']=='A' and e['sample_t_monotonic_ns']>=fault]
    positive=next((e for e in samples if (e.get('retrans_delta') or 0)>0),None)
    ports=list(csv.DictReader((folder/'switch_timeseries.csv').open()))
    before=[e for e in ports if e['interface']=='sA-eth3' and int(e['t_ns'])<=fault]
    early=[e for e in ports if e['interface']=='sA-eth3' and fault<int(e['t_ns'])<=fault+100_000_000]
    delta={key:int(early[-1][key])-int(before[-1][key]) for key in ['rx_bytes','rx_packets']} if before and early else {}
    row=dict(name=folder.name,first_affected_step_start_ms=(active-fault)/1e6 if active else None,
        first_positive_ms=(positive['sample_t_monotonic_ns']-fault)/1e6 if positive else None,
        positive_from_active_ms=(positive['sample_t_monotonic_ns']-active)/1e6 if positive and active else None,
        positive_log_emit_delay_ms=(positive['t_monotonic_ns']-positive['sample_t_monotonic_ns'])/1e6 if positive else None,
        positive_log_receipt_delay_ms=(positive['received_t_monotonic_ns']-positive['sample_t_monotonic_ns'])/1e6 if positive else None,
        positive_poll_interval_ms=positive['sample_interval_ns']/1e6 if positive else None,
        first100ms_switch_counter_deltas=delta,
        counted_bytes_per_received_packet=delta['rx_bytes']/delta['rx_packets'] if delta.get('rx_packets') else None,
        limitation='Step start reconstructed from completion; interface counts include segmentation/coalescing and are not wire-packet counts.')
    rows.append(row)
(ROOT/'logs/signal_timing_decomposition.json').write_text(json.dumps(rows,indent=2)+'\n')
for r in rows:print(r['name'],round(r['first_affected_step_start_ms'] or 0,3),round(r['first_positive_ms'] or 0,3),round(r['positive_poll_interval_ms'] or 0,3),round(r['counted_bytes_per_received_packet'] or 0,1))
