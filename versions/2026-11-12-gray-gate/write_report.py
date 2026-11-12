"""Derive every displayed result from the compact registered campaign summaries."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

ARMS = ('adaptive', 'direct', 'legacy_gate', 'candidate_gate')
LABELS = ('Adaptive only', 'Direct recovery', 'Old gate', 'Candidate gate')


def number(value, places=3):
    return '—' if value is None else f'{value:.{places}f}'


def time_cell(row):
    if row is None:
        return 'not registered'
    if not row['attempted']:
        return 'not run'
    if not row['valid']:
        return 'invalid'
    if not row['completed']:
        return f'unfinished after {row["capped_ms"]:.0f} ms'
    return number(row['communication_ms'])


def control_time_split(directory, row):
    """Split logged control bytes by send time; do not infer latency overhead."""
    status_file, control_file = directory / 'run_status.json', directory / 'control_events.csv'
    if not row['valid'] or not status_file.exists() or not control_file.exists():
        return None
    status = json.loads(status_file.read_text())
    done = status.get('job_done_ns') if row['completed'] else None
    before, after, arriving_after = 0, 0, 0
    with control_file.open(newline='') as stream:
        for item in csv.DictReader(stream):
            amount = int(item['wire_bytes'])
            if done is not None and int(item['sent_ns']) >= done:
                after += amount
            else:
                before += amount
            if done is not None and int(item['arrival_ns']) > done:
                arriving_after += amount
    return dict(before_done=before if done is not None else None,
                after_done=after if done is not None else None,
                arriving_after_done=arriving_after if done is not None else None,
                total=before + after, monitor_end_ns=status.get('monitor_end_ns'))


def write(evidence, out):
    out.mkdir(parents=True, exist_ok=True)
    all_rows, reports, text = [], {}, [
        '# Gray-fault gate: registered simulation results', '',
        'Workload: 16 logical GPUs × 512 chunks × 64 KiB × four phases = 2 GiB',
        'of useful payload per case, in the native CPU network simulator. Each GPU',
        'has two 10-Gb/s access paths. Helper-local links are 2400 Gb/s except for',
        'the explicitly labelled 1-Gb/s boundary controls. See the fixed',
        '`research/EXPERIMENT_PROTOCOL.md` in this version for conditions and seeds.', '',
        'This four-phase / 2-GiB diagnostic does not revalidate the earlier',
        '30-phase / 15-GiB throughput release or its 70%–80% retention target.',
        'Ratios from those workloads must not be compared or pooled: phase count,',
        'payload and fault onset must match for a direct performance comparison.', '',
        'All values below come from the registered summaries. Times are whole-job',
        'communication completion in milliseconds: `(job_done_ns - 1,000,000) / 1e6`.',
        'The fixed 1-ms launch offset is removed from every arm and healthy control.',
        'Each case sends the same useful payload. Invalid and unrun cases',
        'have no performance value; an unfinished horizon is not an exact finish.', '',
        'The 250-ms simulated observation horizon corresponds to 249 ms after job',
        'launch. Monitoring continues after useful work finishes. Whole-horizon',
        'control/probe totals therefore include activity that did not delay this',
        'job. Detection delay instead starts at the configured fault onset.', '',
        'These are four LIMER ablations, not a reproduction of R2CC or a hardware',
        'comparison. The candidate changes its estimator, paid observations and',
        'resource lifecycle together. It is not an estimator-only ablation.', '',
        'The first v1 campaign stopped after an audit false positive. Its one valid',
        'and one invalid attempt, plus all unrun registrations, remain separately',
        'preserved in `evidence-v1`; they are not silently replaced or pooled here.', '']
    for group in ('pilot-v2', 'confirmation-v2'):
        report = json.loads((evidence / group / 'gray_gate_summary.json').read_text())
        reports[group] = report
        text += [f'## {group}', '',
                 f'Registered: {report["registered"]}; attempted: {report["attempted"]}; '
                 f'valid: {report["valid"]}; completed: {report["completed"]}.', '',
                 '| Condition | ' + ' | '.join(LABELS) + ' | Candidate − direct |',
                 '| --- | ---: | ---: | ---: | ---: | ---: |']
        conditions = {}
        for row in report['rows']:
            conditions.setdefault(row['condition'], {})[row['arm']] = row
            all_rows.append(dict(campaign=group, **row))
        for condition, arms in conditions.items():
            c, d = arms.get('candidate_gate'), arms.get('direct')
            delta = c['communication_ms'] - d['communication_ms'] if c and d and c['valid'] and d['valid'] and c['completed'] and d['completed'] else None
            text.append('| ' + condition + ' | ' + ' | '.join(time_cell(arms.get(a)) for a in ARMS)
                        + ' | ' + number(delta) + ' |')
        text += ['', 'Negative difference means the candidate finished sooner. A blank',
                 'difference means that two valid completed runs are unavailable.', '',
                 '### Candidate behavior and detection', '',
                 '| Condition | Completion / detection class | Healthy-normalized useful throughput | Worst affected-path alarm delay from onset, ms | Initial/refresh activations | Fresh relay chunks | Released leases |',
                 '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
        for condition, arms in conditions.items():
            row = arms.get('candidate_gate')
            if not row:
                continue
            ratio = row['healthy_ratio'] if row['valid'] and row['completed'] else None
            costs = row['costs']
            def cost_cell(key):
                value = costs.get(key)
                return str(value) if row['valid'] and value is not None else '—'
            state = ('completed' if row['completed'] else 'unfinished' if row['valid']
                     else 'invalid' if row['attempted'] else 'not run')
            text.append('| ' + ' | '.join((condition, state + ' / ' + row['classification'],
                '—' if ratio is None else f'{ratio*100:.2f}%', number(row['all_paths_delay_ms']) if row['valid'] else '—',
                cost_cell('activations'), cost_cell('new_Bprime_completions'),
                cost_cell('helper_leases_released'))) + ' |')
        text += ['', 'The throughput ratio is matched healthy completion time divided by fault',
                 'completion time for identical useful bytes. It is not instantaneous',
                 'post-recovery link bandwidth. Activation count includes health refreshes.',
                 'Fresh relay work alone does not prove a net time saving.', '',
                 'Detection delay is the maximum over affected paths within one case.',
                 'A miss has no finite all-path delay; it remains in the denominator.',
                 'A valid trace can contain a late/missed/false alarm, and a timely',
                 'alarm does not imply task completion or a beneficial route change.',
                 'Paired arms and deterministic repeats are not independent detection',
                 'trials. This matrix does not establish a population-level 95% target.', '']
        text += ['### Detection accounting for every registered attempt', '',
                 '| Arm | Fault cases registered | Timely | Late | Miss | Other fault outcomes | Healthy clear / registered | Healthy false alarms |',
                 '| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |']
        for arm, label in zip(ARMS, LABELS):
            members = [r for r in report['rows'] if r['arm'] == arm]
            faults = [r for r in members if not r['condition'].startswith('healthy')]
            healthy = [r for r in members if r['condition'].startswith('healthy')]
            counts = Counter(r['classification'] for r in faults)
            other = ', '.join(f'{key}: {value}' for key, value in sorted(counts.items())
                              if key not in ('timely', 'late', 'miss')) or 'none'
            clear = sum(r['valid'] and r['classification'] == 'healthy_clear' for r in healthy)
            false = sum(r['valid'] and r['healthy_false_alarm'] for r in healthy)
            text.append(f'| {label} | {len(faults)} | {counts["timely"]} | {counts["late"]} | {counts["miss"]} | {other} | {clear}/{len(healthy)} | {false} |')
        text += ['', 'Counts pool heterogeneous conditions only to account for registered',
                 'attempts; they are not a pooled acceptance rate or independent',
                 'sample count. Condition-level classifications remain above and in',
                 '`trials.csv`. Error and not-run outcomes are never removed.', '',
                 '### Candidate control cost over the observation horizon', '',
                 '| Condition | Bytes enqueued before job completion | Bytes enqueued at/after completion | Bytes scheduled to arrive after completion | Total logged bytes |',
                 '| --- | ---: | ---: | ---: | ---: |']
        for condition, arms in conditions.items():
            row = arms.get('candidate_gate')
            if row is None:
                continue
            split = control_time_split(evidence / group / 'runs' / row['name'], row)
            values = [split.get(key) if split else None for key in ('before_done', 'after_done', 'arriving_after_done', 'total')]
            text.append('| ' + condition + ' | ' + ' | '.join('—' if v is None else str(v) for v in values) + ' |')
        text += ['', 'The first two columns partition by enqueue time. The arrival column',
                 'can overlap them and must not be added to their sum. It does not convert',
                 'bytes into a causal latency penalty. For unfinished work only the',
                 'whole-horizon total is available. Relay/probe wire-byte totals and',
                 'lease counts in `report.json` also span the observation horizon.', '',
                 '### Completed candidate pairs: adverse and unresolved outcomes', '']
        adverse = []
        for pair in report.get('pairs', []):
            delta = pair.get('candidate_minus_baseline_ms')
            if pair.get('both_valid') and pair.get('both_completed') and delta is not None and delta > 0:
                adverse.append(f'- `{pair["pair_id"]}` versus `{pair["comparator"]}`: candidate slower by **{delta:.6f} ms**.')
        text += adverse or ['No slower candidate pair is present among currently valid completed comparisons.']
        unresolved = [r for r in report['rows'] if not r['completed']]
        if unresolved:
            text += ['', 'Unresolved registrations (including other arms):']
            text += [f'- `{r["name"]}`: {time_cell(r)}; detection `{r["classification"]}`.' for r in unresolved]
        text += ['', 'Exact ties and tiny differences are descriptive; this matrix supplies',
                 'no statistical significance test. An incomplete campaign cannot',
                 'support a final overall gain claim.', '']
    text += ['## Retained limits', '',
             '- The gate controls only initial activation per phase.',
             '- A current-phase forecast is evaluated using whole-job completion.',
             '  Whole-job gain is not a direct measurement of each decision forecast;',
             '  later phases and helper contention can change the result.',
             '- Helper forecasts use outgoing work and recent ACK service; incoming',
             '  competition and other ranks are not separately predicted.',
             '- Stalled-tail persistence and equal-byte helper opportunity cost are',
             '  heuristics, not counterfactual or future-fault information.',
             '- Four phases, one placement, fixed onsets and a small set of rates',
             '  do not establish generality or training-scale performance.',
             '- Only weak-loss repetitions use new random fault streams; repeated',
             '  deterministic scenarios do not add independent statistical evidence.',
             '- See `research/NOVELTY_AUDIT.md` before making novelty claims.', '']
    (out / 'RESULTS.md').write_text('\n'.join(text))
    fields = ('campaign', 'name', 'condition', 'arm', 'seed', 'attempted', 'valid',
              'completed', 'classification', 'communication_ms', 'capped_ms',
              'healthy_ratio', 'all_paths_timely', 'all_paths_delay_ms',
              'healthy_false_alarm', 'error')
    with (out / 'trials.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(all_rows)
    (out / 'report.json').write_text(json.dumps(reports, indent=2) + '\n')
    print(json.dumps(dict(campaigns=len(reports), rows=len(all_rows),
                         attempted=sum(r['attempted'] for r in all_rows),
                         valid=sum(r['valid'] for r in all_rows),
                         completed=sum(r['completed'] for r in all_rows))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    write(args.evidence, args.out)
