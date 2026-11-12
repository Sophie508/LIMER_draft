"""Freeze matched gray-fault gate experiments and preserve every registered attempt.

This module uses the existing frozen-toolchain runner. It does not inject truth
into policy observations, change detector thresholds, or launch remote work.
"""
import argparse
from collections import Counter, defaultdict
import csv
from copy import deepcopy
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from limerlab.config import Scenario
import research_campaign as research

ARMS = {'adaptive': ('G10', 'always'), 'direct': ('G11', 'always'),
        'legacy_gate': ('G11', 'benefit'), 'candidate_gate': ('G11', 'benefit_v2')}
SEEDS = {'pilot': 111213001, 'confirmation': 111213033}
PRIMARY = ('sustained_25_early', 'sustained_25_late', 'transient_25_20ms')


def make_plan(preset='pilot'):
    if preset not in SEEDS:
        raise ValueError('Unknown preset: ' + preset)
    cases = []
    seed = SEEDS[preset]

    def add(condition, family, arms=None, fault_ns=24_000_000,
            duration_ns=0, local_gbps=2400, fraction=.25):
        for arm in arms or ARMS:
            method, policy = ARMS[arm]
            scene = dict(family=family, rounds=1, chunks_per_phase=512,
                         horizon_ns=250_000_000, fault_ns=fault_ns, node=0,
                         seed=seed, local_gbps=local_gbps, detector='service',
                         policy=policy, fault_duration_ns=duration_ns,
                         replacement_lifetime='phase', phases_per_round=4,
                         relay_completion='pipelined', helper_mode='shared')
            # Keep fixed-quarter semantics. Only the explicit new family sweeps rate.
            if family == 'slowdown':
                scene['slowdown_fraction'] = fraction
            scene = Scenario(**scene).dictionary()
            cases.append(dict(name=f'{condition}-{arm}-s{seed}', condition=condition,
                              family=family, arm=arm, method=method, scene=scene,
                              detector='service', trial=0,
                              pair_id=f'{condition}-s{seed}'))

    add('healthy', 'healthy')
    add('sustained_25_early', 'quarter')
    add('sustained_25_late', 'quarter', fault_ns=40_000_000)
    add('transient_25_20ms', 'quarter', duration_ns=20_000_000)
    for family in ('blackhole', 'weak_loss'):
        add(family, family, ('direct', 'candidate_gate'))
    if preset == 'confirmation':
        add('sustained_50_early', 'slowdown', fraction=.5)
        add('no_healthy_helper', 'no_idle_helpers', ('direct', 'candidate_gate'))
        add('healthy_local_1gbps', 'healthy', ('direct', 'candidate_gate'), local_gbps=1)
        add('slow_helper_25', 'quarter', ('direct', 'candidate_gate'), local_gbps=1)
    plan = dict(schema='limer-gray-gate-plan-v1', preset=preset,
                phase='development' if preset == 'pilot' else 'confirmation',
                source_baseline_commit='191f4349da2eb7ed3e7990835792c18d8ade7ec0',
                cases=cases, run_count=len(cases), default_workers=1, maximum_workers=2,
                parallelism_rule='A second worker requires measured first-attempt raw/archive budgets and quota headroom of at least two raw budgets plus 10 GiB; root decides before launch.',
                changes='Versioned benefit_v2 gates initial activation in each phase using stalled-tail, relay-pipeline and paid-helper estimates. Unconfigured temporary loans are released after rejection, expired initial health or failed probe; source completion also releases its lease. Configured bindings keep the same helpers while refreshing health. V2 alone applies a 20-ms probe timeout with safe cancellation.',
                expectation='The candidate may reject unprofitable initial late/transient/slow-helper switches while retaining useful sustained-fault recovery. Probe cancellation and release should bound stranded unconfigured reservations without erasing business completion or charging a timeout as successful recovery. An active binding refreshes health without continuous route reoptimization. Failure is an allowed outcome.',
                lifecycle_revision=dict(policy='benefit_v2', probe_timeout_ns=20_000_000,
                                        gate_scope='Initial activation in each phase; not continuous candidate optimization.',
                                        probe_timeout_action='Cancel only the timed-out health probe safely and retain elapsed costs. Release through charged messages only when the binding is unconfigured or the source has completed; otherwise keep the configured helper pair and retry health.',
                                        temporary_release_triggers=['gate_rejection', 'expired_initial_health_evidence', 'probe_timeout'],
                                        configured_binding='Retain the same helpers during health refresh until source completion or phase reset; no repeated candidate selection after initial activation.',
                                        terminal_release_triggers=['source_completed', 'phase_reset'],
                                        comparison_scope='Candidate-versus-direct or legacy includes these lifecycle changes and paid reports; it is not an estimator-only ablation.'),
                denominator='All registered cases including invalid, unfinished and unrun attempts; no replacement seeds or silent retries.',
                calibration='Faults begin at 24 or 40 ms, after the unchanged 1-21 ms detector calibration.',
                confirmation_rule='The confirmation preset and its seed are frozen before pilot outcomes. Any source fix after seeing confirmation results requires a new separately labelled campaign.',
                frozen_seed_roles=deepcopy(SEEDS),
                scoring=dict(primary_conditions=list(PRIMARY),
                             scope='Finite CPU simulation with 16 logical GPUs and four scheduler phases; no hardware or population coverage claim.'),
                metrics=dict(primary='Whole-job communication completion time, candidate minus each matched comparator',
                             throughput='Matched healthy time / fault time for identical useful payload; whole-job useful throughput, not instantaneous link capacity',
                             detection='All affected paths strictly below 100 ms; retain late, missed, pre-fault, unaffected and healthy alarms',
                             costs='Paid control bytes, probe routes, activations, fresh B-prime payload, helper reports/releases and physical relay/final-ACK costs',
                             not_a_claim='A small finite pilot does not establish 95% general detection or optimal switching.'),
                preregistered_interpretation=dict(
                    sustained='Positive gate value requires lower whole-job time than direct recovery or adaptive-only on matched conditions, not merely a predicted gain.',
                    transient='Classify alarm timing relative to recovery after the run; the controller cannot access future fault duration.',
                    unnecessary_switch='Whole-run harmful switch means a switching arm is slower than paired adaptive-only; no-fresh-payload activation alone is not proof of harm because it can rescue in-flight chunks.',
                    failure='Retain every registered attempt. Only valid unfinished runs receive a horizon cap; invalid/unrun times and pair differences involving them remain null. Caps are not exact completion times.'))
    validate_plan(plan)
    return plan


def validate_plan(plan):
    names = [c['name'] for c in plan['cases']]
    if len(names) != len(set(names)) or any(Path(n).name != n for n in names):
        raise ValueError('Case names must be unique simple filenames')
    groups = defaultdict(list)
    for case in plan['cases']:
        scene = Scenario(**case['scene']).dictionary()
        if (case['method'], scene['policy']) != ARMS.get(case['arm']):
            raise ValueError('Arm method/policy mismatch')
        if scene['fault_ns'] < 21_000_000:
            raise ValueError('Primary fault overlaps detector calibration')
        if scene['fault_ns'] + 100_000_000 >= scene['horizon_ns']:
            raise ValueError('Insufficient post-fault detection horizon')
        groups[case['pair_id']].append(case)
    for pair, members in groups.items():
        scenes = []
        for case in members:
            scene = deepcopy(case['scene']); scene.pop('policy')
            scenes.append(scene)
        if any(scene != scenes[0] for scene in scenes):
            raise ValueError('Matched arms differ in scene: ' + pair)
        if len({c['arm'] for c in members}) != len(members):
            raise ValueError('Duplicate arm in pair: ' + pair)
    healthy = [c for c in plan['cases'] if c['scene']['family'] == 'healthy']
    for case in plan['cases']:
        if not any(healthy_key(h) == healthy_key(case) for h in healthy):
            raise ValueError('No matched healthy reference: ' + case['name'])
    return True


def healthy_key(case):
    """Fault timing/rate/duration are inert in a healthy run; all else must match."""
    scene = deepcopy(case['scene'])
    for key in ('family', 'fault_ns', 'fault_duration_ns', 'slowdown_fraction'):
        scene.pop(key, None)
    return (case['method'], json.dumps(scene, sort_keys=True))


def register(build, out, preset='pilot'):
    plan = make_plan(preset)
    return research.register(plan, build, out)


def cost_summary(directory, result):
    directory = Path(directory)
    counts, charged = Counter(), Counter()
    controls = directory / 'control_events.csv'
    if controls.exists():
        with controls.open(newline='') as stream:
            for row in csv.DictReader(stream):
                counts[row['event']] += 1
                charged[row['event']] += int(row['wire_bytes'])
    reports, snapshots = Counter(), []
    report_file = directory / 'helper_reports.jsonl'
    if report_file.exists():
        for line in report_file.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line); reports[row['event']] += 1
            if row['event'] == 'DELIVERED':
                snapshots.append({key: row[key] for key in (
                    'source', 'slot', 'rank', 'phase', 'lease_id', 'report_id',
                    'sampled_ns', 'delivered_ns', 'own_remaining_bytes',
                    'own_bytes_per_ns', 'known') if key in row})
    performance, status = result.get('performance', {}), result.get('status', {})
    return dict(control_events=dict(counts), control_wire_bytes_by_event=dict(charged),
                control_wire_bytes=sum(charged.values()),
                probe_routes=status.get('health_probe_routes'),
                probe_wire_bytes=status.get('probe_wire_bytes'),
                relay_wire_bytes=status.get('relay_wire_bytes'),
                network_wire_bytes=status.get('network_wire_bytes'),
                local_wire_bytes=status.get('local_wire_bytes'),
                helper_report_events=dict(reports), delivered_helper_snapshots=snapshots,
                helper_leases_activated=counts.get('LEND_ACTIVE', 0),
                helper_leases_released=counts.get('LEND_RELEASED', 0),
                activations=counts.get('ACTIVATE', 0),
                new_Bprime_completions=performance.get('new_Bprime_completions'),
                fresh_Bprime_payload_bytes=performance.get('fresh_Bprime_payload_bytes'),
                fresh_proxy_costs=performance.get('fresh_proxy_costs'),
                no_fresh_payload_activation=bool(counts.get('ACTIVATE', 0)
                                                and not performance.get('fresh_Bprime_payload_bytes')),
                helper_burden_scope='Actual contention is included in whole-job time; per-helper counterfactual slowdown is not inferred from control-event counts.')


def summarize(out):
    out = Path(out)
    registration = research.validate_registration(out)
    plan = registration['plan']; validate_plan(plan)
    rows, by_name = [], {}
    for case in plan['cases']:
        path = out / 'attempts' / (case['name'] + '.json')
        directory = out / 'runs' / case['name']
        attempt, result, error = None, {}, None
        try:
            attempt = research.read_json(path) if path.exists() else None
            result = research.read_json(directory / 'result.json') if (directory / 'result.json').exists() else {}
        except (ValueError, OSError) as exc:
            error = str(exc)
        score = dict(valid=False, classification='not_run', all_paths_timely_success=False,
                     all_paths_delay_ms=None, healthy_false_alarm=False)
        if path.exists():
            try:
                if error:
                    raise ValueError(error)
                if result.get('scene') != case['scene'] or result.get('method') != case['method']:
                    raise ValueError('Result identity differs from registered case')
                score = dict(research.score_run(directory, case))
                if not attempt['valid']:
                    raise ValueError(attempt.get('error', 'Retained invalid attempt'))
            except Exception as exc:
                error = str(exc); score.update(valid=False, classification='error',
                                               all_paths_timely_success=False)
        completed = bool(score['valid'] and result.get('status', {}).get('status') == 'completed')
        actual = result.get('performance', {}).get('communication_ms') if completed else None
        try:
            costs = cost_summary(directory, result)
            if completed and (not isinstance(actual, (int, float)) or not math.isfinite(actual) or actual <= 0):
                raise ValueError('Completed run has no finite positive communication time')
        except (KeyError, ValueError, TypeError, OSError) as exc:
            error = str(exc); costs = dict(error=error)
            score.update(valid=False, classification='error', all_paths_timely_success=False)
            completed, actual = False, None
        row = dict(name=case['name'], condition=case['condition'], arm=case['arm'],
                   method=case['method'], pair_id=case['pair_id'], seed=case['scene']['seed'],
                   attempted=path.exists(), valid=score['valid'], completed=completed,
                   classification=score['classification'], error=error,
                   communication_ms=actual,
                   capped_ms=actual if completed else ((case['scene']['horizon_ns'] - 1_000_000) / 1e6 if score['valid'] else None),
                   all_paths_timely=score['all_paths_timely_success'],
                   all_paths_delay_ms=score['all_paths_delay_ms'],
                   healthy_false_alarm=score['healthy_false_alarm'],
                   policy_decision_counts=score.get('policy_decision_counts', {}),
                   costs=costs, healthy_ratio=None,
                   audit_scope='Passed execution and observation audits' if score['valid'] else 'Invalid, absent or unfinished validation')
        if case['scene']['fault_duration_ns'] and row['all_paths_delay_ms'] is not None:
            row['all_paths_alarm_after_fault_ended'] = row['all_paths_delay_ms'] * 1e6 > case['scene']['fault_duration_ns']
        rows.append(row); by_name[case['name']] = row
    healthy = {healthy_key(c): by_name[c['name']] for c in plan['cases'] if c['scene']['family'] == 'healthy'}
    for case in plan['cases']:
        row, reference = by_name[case['name']], healthy[healthy_key(case)]
        row['healthy_reference'] = reference['name']
        if row['completed'] and reference['completed']:
            row['healthy_ratio'] = reference['communication_ms'] / row['communication_ms']
    groups = defaultdict(dict)
    for row in rows:
        groups[row['pair_id']][row['arm']] = row
    pairs = []
    for pair_id, arms in sorted(groups.items()):
        candidate = arms.get('candidate_gate')
        if not candidate:
            continue
        for arm, baseline in sorted(arms.items()):
            if arm == 'candidate_gate':
                continue
            both = candidate['completed'] and baseline['completed']
            both_valid = candidate['valid'] and baseline['valid']
            pairs.append(dict(pair_id=pair_id, comparator=arm,
                              both_valid=both_valid,
                              both_completed=both,
                              candidate_minus_baseline_ms=candidate['communication_ms'] - baseline['communication_ms'] if both else None,
                              candidate_minus_baseline_capped_ms=candidate['capped_ms'] - baseline['capped_ms'] if both_valid else None,
                              improvement_fraction=1 - candidate['communication_ms'] / baseline['communication_ms'] if both else None))
    report = dict(schema='limer-gray-gate-summary-v1', preset=plan['preset'],
                  authority='This gray-gate summary is authoritative for this study; research_summary.json uses historical arm names and acceptance logic.',
                  plan_sha256=registration['plan_sha256'], registered=len(rows),
                  attempted=sum(r['attempted'] for r in rows), valid=sum(r['valid'] for r in rows),
                  completed=sum(r['completed'] for r in rows),
                  complete=all(r['attempted'] for r in rows), rows=rows, pairs=pairs,
                  limitations=['Development and frozen-condition regression confirmation are finite diagnostics, not 95% population acceptance.',
                               'The changed seed gives new stochastic evidence only for weak loss; deterministic rate/healthy/blackhole repeats do not add independent random trials.',
                               'Only valid unfinished runs have capped time; invalid or unrun records have no performance value. A cap is not an observed completion time.',
                               'Every policy is a LIMER ablation; none is a reproduction of R2CC.',
                               'Actual helper contention is paid, but this summary does not claim a causal per-helper burden estimate.',
                               'No-fresh-payload activations can still rescue in-flight work; classify harm using paired whole-job outcomes.'])
    research.write_json(out / 'gray_gate_summary.json', report)
    return report


def execute(out, workers=1, resume=False, only_conditions=None):
    if workers not in (1, 2):
        raise ValueError('Current preregistration permits one or two workers')
    registration = research.validate_registration(out)
    validate_plan(registration['plan'])
    # The established runner skips every recorded failed attempt when resuming.
    research.execute(out, workers=workers, resume=resume, only_conditions=only_conditions)
    return summarize(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'register', 'execute', 'summarize'))
    parser.add_argument('--preset', choices=tuple(SEEDS), default='pilot')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--only-condition', action='append')
    args = parser.parse_args()
    if args.action == 'plan':
        research.write_json(args.out, make_plan(args.preset))
    elif args.action == 'register':
        if args.build is None:
            parser.error('--build is required for registration')
        print(json.dumps(register(args.build, args.out, args.preset)))
    elif args.action == 'execute':
        execute(args.out, args.workers, args.resume, args.only_condition)
    else:
        result = summarize(args.out)
        print(json.dumps({key: result[key] for key in ('registered', 'attempted', 'valid', 'completed')}))


if __name__ == '__main__':
    main()
