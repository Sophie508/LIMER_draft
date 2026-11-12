"""Derive bottleneck observations from frozen evidence without rerunning simulation."""
from pathlib import Path
import csv
import hashlib
import json
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
EVIDENCE = ROOT / 'evidence'
inputs = {}


def read(path, fmt='json'):
    data = path.read_bytes()
    inputs[str(path.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()
    if fmt == 'json':
        return json.loads(data)
    if fmt == 'csv':
        return list(csv.DictReader(data.decode().splitlines()))
    return [json.loads(line) for line in data.decode().splitlines()]


cases = {}
for group in ('development-v1', 'lifetime-full-v1', 'gray-full-v1'):
    for path in sorted((EVIDENCE / group / 'runs').glob('full-*')):
        perf = read(path / 'performance.json')
        phases = read(path / 'phase_metrics.csv', 'csv')
        controls = read(path / 'control_events.csv', 'csv')
        status = read(path / 'run_status.json')
        cases[path.name] = dict(
            communication_ms=perf['communication_ms'],
            completed=status['status'] == 'completed',
            phases_3_to_29_mean_ms=mean(int(p['duration_ns']) / 1e6 for p in phases[3:]),
            detector_delays_ms=perf['detector_delays_ms'],
            fresh_proxy_costs=perf['fresh_proxy_costs'],
            fresh_Bprime_completed=perf['new_Bprime_completions'],
            health_probes=status['health_probe_routes'],
        )
        if path.name != 'full-ring-blackhole-G11-always':
            continue
        steady = [p for p in perf['phase_route_lifecycles'] if p['phase'] >= 3]
        waits, setups = [], []
        for p in steady:
            prepare = next(c for c in controls if c['event'] == 'M13_REPLACEMENT_PREPARE'
                           and int(c['rank']) == p['src'] and int(c['phase']) == p['phase'])
            waits.append((int(prepare['sent_ns']) - p['reset_to_AB_ns']) / 1e6)
            setups.append((p['activation_ns'] - int(prepare['sent_ns'])) / 1e6)
        denominator = sum(p['A_new_bytes'] + p['B_new_bytes'] + p.get('Bprime_new_bytes', 0)
                          for p in steady)
        cases[path.name].update(
            helper_wait_mean_ms=mean(waits),
            probe_and_setup_mean_ms=mean(setups),
            activation_elapsed_mean_ms=mean(w + s for w, s in zip(waits, setups)),
            affected_new_allocation_fraction={lane: sum(p.get(lane + '_new_bytes', 0)
                                                      for p in steady) / denominator
                                              for lane in ('A', 'B', 'Bprime')},
            phase3=dict(start_ns=int(phases[3]['start_ns']), end_ns=int(phases[3]['end_ns']),
                        source0_prepare_ns=int(next(c['sent_ns'] for c in controls
                                                   if c['event'] == 'M13_REPLACEMENT_PREPARE'
                                                   and c['rank'] == '0' and c['phase'] == '3')),
                        source0_activate_ns=next(p['activation_ns'] for p in steady
                                                 if p['phase'] == 3 and p['src'] == 0)),
        )

healthy = cases['full-ring-healthy-G11-benefit']['communication_ms']
for case in cases.values():
    case['whole_job_healthy_normalized_goodput_percent'] = 100 * healthy / case['communication_ms']

gate_path = EVIDENCE / 'gray-full-v1/runs/full-ring-weak_loss-G11-benefit/policy_decisions.jsonl'
decisions = read(gate_path, 'jsonl')
before = next(d for d in decisions if d['timestamp_ns'] == 118828640 and d['src'] == 15)
after = next(d for d in decisions if d['timestamp_ns'] == 124928640 and d['src'] == 15)
assert before['input']['b_bytes'] == after['input']['b_bytes'] == 15072
assert before['input']['pending_bytes'] == after['input']['pending_bytes'] == 0

result = dict(
    scope='Post hoc analysis of archived development runs; no new simulation or acceptance cohort.',
    cases=cases,
    gate_prediction_counterexample=dict(
        phase=4, source=15, prediction_ns=before['timestamp_ns'],
        predicted_stay_remaining_ms=before['stay_ns'] / 1e6,
        subsequent_observation_ns=after['timestamp_ns'],
        observed_wait_ms=(after['timestamp_ns'] - before['timestamp_ns']) / 1e6,
        outstanding_B_bytes_at_both_observations=15072,
        interpretation='The aggregate recent ACK rate did not predict this stalled tail.'),
    analytical_credit_ceiling=dict(
        credits_per_helper_nic=4, chunk_bytes=65536,
        minimum_final_notification_ns=1007680,
        gbps=4 * 65536 * 8 / 1007680,
        scope='Upper bound for a fixed four-credit helper route under the current reservation and final-notification model. It excludes data transfer time, contention and idle-helper waiting. It is not a measured link rate.'),
    limitations=[
        'Healthy-normalized goodput uses equal logical payload divided by whole-job communication time. It is not instantaneous NIC bandwidth.',
        'Phases 3 through 29 are a post hoc descriptive window, not a preregistered acceptance metric.',
        'A_ONLY moves business traffic from all ranks onto A. Its comparison does not isolate proxy benefit on affected ranks.',
        'The gate counterexample demonstrates a prediction failure, not the causal allocation of the entire total-time gap.',
        'Helpers must finish their own current-phase incoming and outgoing work. A phase reset does not heal the physical fault.',
    ],
    input_sha256=inputs,
)
(OUT / 'analysis.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(dict(cases=len(cases), input_files=len(inputs),
                     retained_healthy_percent=cases['full-ring-blackhole-G11-always']['whole_job_healthy_normalized_goodput_percent'],
                     helper_wait_ms=cases['full-ring-blackhole-G11-always']['helper_wait_mean_ms'],
                     setup_ms=cases['full-ring-blackhole-G11-always']['probe_and_setup_mean_ms'],
                     credit_ceiling_gbps=result['analytical_credit_ceiling']['gbps'])))
