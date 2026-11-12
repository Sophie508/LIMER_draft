"""Generate the research-facing report from verified compact summaries."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def fmt(value, digits=2):
    return '—' if value is None else f'{value:.{digits}f}'


def main():
    reports = {group: read(ROOT / 'results' / group / 'report.json')
               for group in ('pilot-v1', 'pilot-v2', 'policy-pilot-v2', 'full-v2')}
    full = reports['full-v2']['rows']
    all_rows = [row for report in reports.values() for row in report['rows']]
    assert all(row['status'] != 'not_run' for row in all_rows)
    prior = ROOT.parent / '2026-11-12-integration/results'
    old_rows = [row for group in ('development-v1', 'gray-full-v1')
                for row in read(prior / group / 'report.json')['rows']]
    old = {row['family']: row for row in old_rows
           if row['name'].startswith('full-ring-') and row['method'] == 'G11'
           and row['policy'] == 'always'}
    candidate = {row['family']: row for row in full
                 if row['seed'] == 111210016 and row['helper_mode'] == 'shared'}
    text = [
        '# Recovery throughput results — 2026-11-12', '',
        'This report is generated from the retained compact evidence. Results are',
        'simulated whole-job useful throughput, not physical GPU throughput.', '',
        '## Target and fixed workload', '',
        'For equal payload, healthy-normalized throughput is `T_healthy / T_fault`.',
        'The healthy reference is 480.178448 ms. Retaining 70–80% therefore means',
        'approximately 600.22–685.97 ms for the same job; faster is also acceptable.',
        'The detection deadline of 100 ms is separate from job completion.', '',
        'All full cases use 16 logical GPUs, four per server, two 10-Gb/s access',
        'planes, 2400-Gb/s intra-server links, 64-KiB chunks, 512 chunks per rank',
        'per phase and 30 phases: 245,760 chunks / 15 GiB total useful payload.',
        'Fault onset is 40 ms; observation horizon is 2 s. Blackhole removes',
        'delivery on node 0\'s B access link. Weak loss drops 0.5% of packets on',
        'that link. Both directions are affected, hence logical sources 0 and 15.',
        'These physical fault definitions and detector rules are unchanged.', '',
        '## Matched original-seed comparison', '',
        '| Condition | Prior direct recovery (ms) | Candidate direct recovery (ms) | Candidate / healthy throughput | Fresh B′ chunks |',
        '|---|---:|---:|---:|---:|',
    ]
    for family in ('healthy', 'blackhole', 'weak_loss'):
        row = candidate[family]
        old_ms = 480.178448 if family == 'healthy' else old[family]['completion_ms']
        text.append(f"| {family} | {old_ms:.2f} | {fmt(row['communication_ms'])} | {fmt(row['healthy_normalized_percent'])}% | {row.get('fresh_Bprime_chunks', '—')} |")
    text += ['',
        'Candidate rows use pipelined resource release, shared helpers and disjoint',
        'helper selection. Both old fault rows use `policy=always`; this comparison',
        'does not replace the old method with its slower benefit-gated variant.',
        'The matched healthy candidate is identical to the old denominator.', '',
        '![Matched original-seed throughput comparison](figures/throughput-comparison.png)', '',
        '## All seven full-size attempts', '',
        '| Seed | Condition | Helper mode | Status | Job ms | Healthy reference % | Detection ms | Fresh B′ chunks / phases |',
        '|---|---|---|---|---:|---:|---:|---:|',
    ]
    for row in full:
        percent = row['healthy_normalized_percent']
        if percent is None:
            percent = row['old_healthy_normalized_percent']
        text.append(f"| {row['seed']} | {row['family']} | {row['helper_mode']} | {row['status']} | {fmt(row['communication_ms'])} | {fmt(percent)} | {fmt(row.get('detection_ms'))} | {row.get('fresh_Bprime_chunks', '—')} / {row.get('fresh_Bprime_phases', '—')} |")
    text += ['',
        'Shared-helper rows use their matched healthy seed. The idle-only control',
        'uses the unchanged 480.178448-ms original healthy reference; it has no',
        'separately registered full-size idle-mode healthy run. The v1 pilot checks',
        'all three modes against the identical 63.965513-ms short healthy run.',
        'The fresh seed is one development recheck, not a statistical guarantee.', '',
        'The seed controls fault-loss sampling. Healthy and complete-blackhole',
        'conditions are deterministic here; matching them across seeds does not',
        'provide independent stochastic replication. The weak-loss pair is the',
        'meaningful new random-loss check.', '',
        '## Why the execution became faster', '',
        '1. The final data leg releases physical relay resources; final logical',
        '   completion still waits for the same charged notification. A bounded',
        '   32-chunk confirmation window allows data to continue during that wait.',
        '2. A helper can lend one of its four NIC admission credits before its own',
        '   work finishes. Its own new admissions use at most three. Existing',
        '   links, bandwidth, buffer limits and contention remain simulated.',
        '3. Concurrent recoveries select disjoint helper GPUs, avoiding two relay',
        '   jobs competing for one helper\'s buffer pool.', '',
        '**Shared helpers extend the collaborator\'s idle-only architecture.** The',
        'improvement must not be described as a pure implementation correction of',
        'that earlier assumption. The final timing includes all helpers\' own work.',
        'The control FIFO, 1-ms propagation, full representative probe, health',
        'report, PREPARE/READY/COMMIT, health TTL and final ACK are unchanged.', '',
        'In the original-seed blackhole run, post-fault phases 3–29 average',
        f"{candidate['blackhole']['phase3_onward_mean_ms']:.3f} ms. The retained logical-event",
        'diagnosis finds helper rank 1 critical in 20 phases and helper rank 12',
        'critical in seven. Their own outgoing work, rather than an unaccounted',
        'free backup link, sets the remaining job tail. The source confirmation',
        'window covers at most 2 MiB of unconfirmed logical payload per rank',
        'instead of 512 KiB; this is a payload bound, not measured memory use.', '',
        '## Development history and failures', '',
        '| Version | Condition | Completion mode / helper | Status | Job ms |',
        '|---|---|---|---|---:|',
    ]
    for group in ('pilot-v1', 'pilot-v2'):
        for row in reports[group]['rows']:
            text.append(f"| {group} | {row['family']} | {row['relay_completion']} / {row['helper_mode']} | {row['status']} | {fmt(row['communication_ms'], 3)} |")
    text += ['',
        'The historical `no_idle_helpers` condition blackholes all four B links',
        'of one server. It leaves no healthy local B helper and remains unfinished',
        'at 400 ms. A fast alarm does not imply successful recovery. No automatic',
        'migration of outstanding B work back onto A is validated here.', '',
        'v2 improved the blackhole pilot but slightly worsened the weak-loss pilot',
        '(85.773350 → 86.900553 ms). The selection is therefore checked on the full',
        'registered workload and a fresh seed; the adverse pilot is retained.', '',
        'Earlier integration failures also remain untouched. In particular, the',
        'old benefit gate took 975.894384 ms under weak loss, compared with',
        '694.962340 ms for direct recovery. This revision does not certify that',
        'estimator or claim an optimal switching decision.', '',
        '## Supplementary gate diagnostic on the frozen candidate', '',
        'These two additional four-phase cases change only `policy=always` to',
        '`policy=benefit`. They were registered after the original-seed full',
        'direct-recovery results and before executing the diagnostic. The aim is',
        'to check compatibility of the existing estimator with the new resource',
        'model, not to pool extra attempts into throughput acceptance.', '',
        '| Condition | Direct recovery ms | Benefit gate ms | Gated fresh B′ chunks | Gate execution status |',
        '|---|---:|---:|---:|---|',
    ]
    direct_pilot = {row['family']: row for row in reports['pilot-v2']['rows']}
    for row in reports['policy-pilot-v2']['rows']:
        text.append(f"| {row['family']} | {fmt(direct_pilot[row['family']]['communication_ms'], 3)} | {fmt(row['communication_ms'], 3)} | {row.get('fresh_Bprime_chunks', '—')} | {row['status']} |")
    text += ['',
        'The direct-recovery throughput result must not be attributed to the',
        'benefit gate. These short diagnostics do not establish a full-size',
        'gate benefit. The candidate estimator still models relay parallelism',
        'using four credits with the final-notification delay and has no',
        'separate per-chunk stalled-tail model.', '',
        'Lending admission remains active while the rejected gate waits to retry,',
        'until the phase reset. This cost is included in measured job completion',
        'but not separately represented in the estimator. The policy contrast',
        'demonstrates a regression; it does not isolate the contribution of each',
        'estimation or admission-state issue.', '',
        'A concrete counterexample remains in `diagnostics/gate-counterexample.json`:',
        'at 88.417750 ms, source 0 predicted that 288 remaining B bytes would',
        'finish in 572 ns and refused recovery. At 94.517750 ms, the same 288',
        'bytes remained; the gate finally switched after the recent-service',
        'estimate dropped to zero. Source 15 shows the same pattern with 432',
        'bytes. Both native decisions and their inputs pass independent replay.', '',
        '## Correctness and evidence limits', '',
        f"All {len(all_rows)} registered attempts are retained: "
        f"{sum(row['valid'] for row in all_rows)} pass execution/observation auditing.",
        f"Communication outcomes: {sum(row['status']=='completed' for row in all_rows)} completed, "
        f"{sum(row['valid'] and row['status']!='completed' for row in all_rows)} unfinished.",
        'An execution-valid unfinished job remains a performance failure.', '',
        'Audit checks include exact logical payload accounting, final target',
        'notification, phase barriers and reset, causal lending/probe/control',
        'delivery, four-credit physical NIC limits and four helper buffers.',
        'Detector alarms are independently replayed from packet-derived',
        'observations. The 152-test regression suite also passes.', '',
        'This small development cohort does not independently establish the',
        '95%-within-100-ms detection target, general fault coverage, scale-out',
        'performance, numerical AllReduce correctness, or physical GPU results.',
        'The healthy helper assumption, fixed topology/control latency and',
        'additional bounded confirmation state remain part of the model.', '',
        'Evidence: `results/*/trials.csv`, `evidence/*/registration.json`,',
        '`verification/final-check.json`, and `review/throughput-v2.patch`.',
        'Reproduce table derivation with `python3 verify_compact.py`. Raw packet',
        'archives remain under `otakotak:/home/suliu/data/LIMER_THROUGHPUT_2026-11-12`.',
        'No commit, push, or Overleaf update is part of this revision.', '',
    ]
    (ROOT / 'RESULTS.md').write_text('\n'.join(text))


if __name__ == '__main__':
    main()
