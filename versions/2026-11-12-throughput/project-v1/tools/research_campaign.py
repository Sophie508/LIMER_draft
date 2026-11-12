"""Register, freeze, execute and score bounded detector/recovery experiments.

This tool is intentionally separate from the historical 2026-10-27 campaign.
The simulator never receives the ground-truth scoring functions below.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))

DEADLINE_NS = 100_000_000
PRIMARY = ('blackhole', 'quarter', 'weak_loss')
BOUNDARIES = ('transient_2ms', 'slow_proxy_1gbps', 'no_idle_helpers')
ARMS = ('no_proxy', 'always', 'benefit')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def tree_hashes(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}


def destination(src):
    return src + 4 if src < 12 else (src + 1) % 4


def affected_paths(scene):
    """Both directions of the injected B access link are affected, not only TX."""
    if scene['family'] == 'healthy':
        return set()
    nodes = set(range(4)) if scene['family'] == 'no_idle_helpers' else {scene['node']}
    return {(src * 16 + destination(src)) * 3 + 1 for src in range(16)
            if src in nodes or destination(src) in nodes}


def exact_lower_bound(successes, trials, alpha=.05):
    """One-sided exact binomial lower confidence bound; distinct from pass rate.

    This is a per-condition bound and does not correct simultaneous inference
    across several conditions. Its population interpretation assumes independent
    trials sampled from the explicitly registered fault/placement distribution.
    """
    if not 0 <= successes <= trials or not 0 < alpha < 1:
        raise ValueError('Invalid binomial count or alpha')
    if not trials:
        return None
    if not successes:
        return 0.0
    if successes == trials:
        return alpha ** (1.0 / trials)

    def upper_tail(p):
        if p <= 0:
            return 0.0
        if p >= 1:
            return 1.0
        terms = [math.lgamma(trials + 1) - math.lgamma(i + 1) - math.lgamma(trials - i + 1)
                 + i * math.log(p) + (trials - i) * math.log1p(-p)
                 for i in range(successes, trials + 1)]
        largest = max(terms)
        return math.exp(largest) * sum(math.exp(t - largest) for t in terms)

    lo, hi = 0.0, 1.0
    for _ in range(70):
        mid = (lo + hi) / 2
        if upper_tail(mid) < alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def percentile95(values):
    """Nearest-rank p95; None represents an unbounded/missing latency."""
    if not values:
        return None
    ordered = sorted(float('inf') if x is None else x for x in values)
    result = ordered[math.ceil(.95 * len(ordered)) - 1]
    return result if math.isfinite(result) else None


def timestamp(row):
    for name in ('timestamp_ns', 't', 'time_ns', 'arrival_ns'):
        if name in row:
            return int(row[name])
    raise ValueError('Timestamp field missing')


def score_alarm_rows(scene, rows, valid=True):
    """Keep every registered attempt, all affected paths, and false alarms.

    Ground truth is used exclusively here, after native execution. A trial passes
    only if every affected path alarms strictly before 100 ms and no pre-fault or
    unaffected-path alarm occurs within the registered observation horizon.
    """
    affected = affected_paths(scene)
    fault, horizon = scene['fault_ns'], scene['horizon_ns']
    alarms = []
    for row in rows:
        t, key = timestamp(row), int(row['path_id'])
        if 0 <= t <= horizon:
            alarms.append((t, key, row.get('signal', row.get('event', ''))))
    alarms.sort()
    healthy = scene['family'] == 'healthy'
    pre = [(t, key) for t, key, _ in alarms if not healthy and t < fault]
    wrong = [(t, key) for t, key, _ in alarms if not healthy and key not in affected]
    first = {}
    for t, key, _ in alarms:
        if key in affected and t >= fault:
            first.setdefault(key, t)
    latencies = {str(key): (first[key] - fault) / 1e6 if key in first else None for key in sorted(affected)}
    first_latency = min((x for x in latencies.values() if x is not None), default=None)
    all_latency = max(latencies.values()) if latencies and all(x is not None for x in latencies.values()) else None
    timely = {key for key, t in first.items() if t - fault < DEADLINE_NS}
    fault_success = bool(affected) and timely == affected and not pre and not wrong and valid
    first_success = first_latency is not None and first_latency < 100 and not pre and not wrong and valid
    if not valid:
        classification = 'error'
    elif healthy:
        classification = 'false_alarm' if alarms else 'healthy_clear'
    elif pre:
        classification = 'pre_fault_alarm'
    elif wrong:
        classification = 'mislocalized'
    elif set(first) != affected:
        classification = 'miss'
    elif timely != affected:
        classification = 'late'
    else:
        classification = 'timely'
    observed_all_latency=all_latency
    if not valid or pre or wrong:
        all_latency=None
    return dict(classification=classification, valid=bool(valid),
                affected_path_ids=sorted(affected), observed_affected_path_ids=sorted(first),
                delays_ms=latencies, all_paths_delay_ms=all_latency, first_incident_delay_ms=first_latency,
                observed_all_paths_delay_ms=observed_all_latency,
                all_paths_timely_success=fault_success, first_incident_timely_success=first_success,
                pre_fault_alarms=pre, unaffected_alarms=wrong,
                healthy_false_alarm=bool(healthy and alarms), alarm_events=len(alarms),
                healthy_exposure_ms=horizon / 1e6 if healthy else 0)


def score_run(directory, case):
    root = Path(directory)
    detector = case['scene'].get('detector', 'legacy')
    filename = 'service_alarms.csv' if detector == 'service' else 'detector_events.csv'
    result = read_json(root / 'result.json') if (root / 'result.json').exists() else None
    monitoring_end = result['status'].get('monitor_end_ns') if result else None
    monitoring_complete = monitoring_end is not None and monitoring_end >= case['scene']['horizon_ns']
    valid = bool(result and result['audit']['pass'] and result['observation_audit']['pass'] and monitoring_complete)
    if not (root / filename).exists():
        raise ValueError('Required detector evidence is missing: ' + filename)
    with (root / filename).open(newline='') as stream:
        score = score_alarm_rows(case['scene'], csv.DictReader(stream), valid=valid)
    score.update(monitor_end_ns=monitoring_end, monitoring_complete=monitoring_complete)
    score['detector_evidence'] = dict(file=filename, sha256=sha(root / filename))
    decisions = root / 'policy_decisions.csv'
    if not decisions.exists():
        decisions = root / 'policy_decisions.jsonl'
    if decisions.exists():
        with decisions.open(newline='') as stream:
            counts = {}
            records = (json.loads(line) for line in stream if line.strip()) if decisions.suffix == '.jsonl' else csv.DictReader(stream)
            for row in records:
                decision = row.get('decision', row.get('event'))
                if decision is None:
                    decision = ('switch' if row.get('should_switch') else 'stay')+':'+row.get('reason','unspecified')
                counts[decision] = counts.get(decision, 0) + 1
        score['policy_decision_counts'] = counts
        score['policy_evidence_sha256'] = sha(decisions)
    return score


def make_plan(phase, trials=60, paired_trials=20, boundary_trials=10, development_trials=2,
              horizon_ms=800, rounds=8, chunks=16, detector='service', include_slow_100=False,
              canary_period_ns=2_000_000, include_delay=False, include_slow_quarter=False,
              seed_base=None, seed_stride=32):
    """Make new plans with separated derived loss streams.

    Historical registrations must be reproduced with their own frozen tools,
    rather than regenerated using the live sampler's new default stride.
    """
    from limerlab.detector.service_detector import ServiceDetector, ServiceDetectorConfig
    if phase not in ('development', 'validation'):
        raise ValueError('Unknown phase')
    if seed_base is not None and (type(seed_base) is not int or seed_base < 0):
        raise ValueError('seed_base must be a nonnegative integer')
    if min(trials, paired_trials, boundary_trials, development_trials) < 1:
        raise ValueError('Trial counts must be positive')
    minimum_stride = 16 if phase == 'validation' else 1
    if type(seed_stride) is not int or seed_stride < minimum_stride:
        raise ValueError('seed_stride must be an integer >= ' + str(minimum_stride) + ' for ' + phase)
    largest_count = development_trials if phase == 'development' else max(trials, boundary_trials)
    if largest_count * seed_stride >= 10000:
        raise ValueError('Trial count times seed_stride must be below the 10000-seed condition range')
    if phase == 'validation' and trials < 60:
        raise ValueError('Validation requires at least 60 independent seeds per primary condition')
    if paired_trials > trials:
        raise ValueError('Paired subset exceeds primary trials')
    if horizon_ms < 160:
        raise ValueError('Observation horizon must cover calibration, latest fault and 100 ms deadline')
    detectors = ('service', 'legacy') if detector == 'both' else (detector,)
    if any(d not in ('legacy', 'service') for d in detectors):
        raise ValueError('Unknown detector')
    primary_conditions = PRIMARY + (('delay',) if include_delay else ())
    conditions = (('healthy',) + primary_conditions + BOUNDARIES
                  + (('slow_proxy_100gbps',) if include_slow_100 else ())
                  + (('slow_proxy_quarter',) if include_slow_quarter else ()))
    base = seed_base if seed_base is not None else 102800000 if phase == 'development' else 102890000
    cases = []
    for ci, condition in enumerate(conditions):
        count = development_trials if phase == 'development' else trials if condition in primary_conditions or condition == 'healthy' else boundary_trials
        for i in range(count):
            # Each trial has a disjoint PRNG seed, random placement, and random
            # onset sampled before execution. Arms receive identical inputs.
            seed = base + ci * 10000 + i * seed_stride
            rng = random.Random(seed)
            node, fault = rng.randrange(16), rng.randint(35_000_000, 55_000_000)
            family = ('short_blackhole' if condition == 'transient_2ms' else
                      'quarter' if condition == 'slow_proxy_quarter' else
                      'slow_local' if condition.startswith('slow_proxy_') else condition)
            for d in detectors:
                if phase == 'development' or condition in BOUNDARIES or condition.startswith('slow_proxy_'):
                    arms = ARMS
                elif condition == 'healthy' or i >= paired_trials:
                    arms = ('benefit',)
                else:
                    arms = ARMS
                for arm in arms:
                    local = 1 if condition in ('slow_proxy_1gbps', 'slow_proxy_quarter') else 100 if condition == 'slow_proxy_100gbps' else 2400
                    scene = dict(family=family,
                                 rounds=1 if condition == 'slow_proxy_quarter' else rounds,
                                 chunks_per_phase=256 if condition == 'slow_proxy_quarter' else chunks,
                                 horizon_ns=round(max(horizon_ms,800) * 1e6) if condition=='slow_proxy_quarter' else round(horizon_ms * 1e6), fault_ns=fault, node=node,
                                 seed=seed, local_gbps=local, detector=d,
                                 policy='benefit' if arm == 'benefit' else 'always',
                                 canary_period_ns=canary_period_ns, canary_bytes=65536,
                                 fault_duration_ns=2_000_000 if condition == 'transient_2ms' else 0)
                    pair = f'{condition}-{d}-{i:03d}'
                    cases.append(dict(name=f'{phase}-{pair}-{arm}', condition=condition, trial=i,
                                      pair_id=pair, arm=arm, detector=d,
                                      method='G10' if arm == 'no_proxy' else 'G11', family=family, scene=scene))
    return dict(schema='limer-research-plan-v1', phase=phase,
                name='LIMER service detector and observable benefit gate', cases=cases,
                hypothesis=dict(detector='Every registered affected B path alarms strictly before 100 ms in at least 95% of trials, separately per primary condition.',
                                policy='With identical inputs, observable benefit gating avoids costly replacements while retaining completion under persistent faults.'),
                scoring=dict(deadline_ns=DEADLINE_NS, target_rate=.95, unit='all affected paths within a trial',
                             primary_conditions=list(primary_conditions),
                             confidence='95% one-sided exact binomial, per condition; no familywise correction',
                             horizon_ns=round(horizon_ms * 1e6), monitor_after_job_completion=True,
                             faults_eligible=['packet loss', 'severe service slowdown', 'blackhole', 'severe propagation delay'],
                             calibration_ns=20_000_000, seed_base=base, seed_stride=seed_stride,
                             loss_rng_stream_mapping='2 * (scene.seed + injected_node) + side',
                             detector_rule_version=ServiceDetector.RULE_VERSION,
                             detector_parameters=asdict(ServiceDetectorConfig()),
                             parameter_source='Frozen mirrored defaults; native consistency checked by independent replay',
                             representative_relay_probe_bytes=65536,
                             fault_onset_ns=[35_000_000, 55_000_000],
                             scope='16 GPUs, fixed dual-plane topology and registered traffic/fault distributions; not general grey-fault coverage'))


def register(plan, build, out):
    from limerlab.config import Scenario
    from limerlab.runner import resolve_build
    out, build = Path(out).resolve(), Path(build).resolve()
    if out.exists():
        raise FileExistsError(out)
    record, _, _ = resolve_build(build)
    names = [c['name'] for c in plan['cases']]
    if len(names) != len(set(names)) or any(Path(n).name != n for n in names):
        raise ValueError('Case names must be unique simple filenames')
    for case in plan['cases']:
        Scenario(**case['scene'])
    for name, expected in record['source_hashes'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('Build is stale relative to source: ' + name)
    out.mkdir(parents=True)
    snapshot = out / 'tooling'
    for name in ('python', 'configs', 'experiments', 'tests', 'tools', 'src'):
        shutil.copytree(ROOT / name, snapshot / name, ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('limer.py', 'build_backend.py'):
        shutil.copyfile(ROOT / name, snapshot / name)
    registration = dict(schema='limer-research-registration-v1',
                        created_utc=datetime.now(timezone.utc).isoformat(), plan=plan,
                        plan_sha256=digest_json(plan), build_sha256=sha(build / 'build.json'),
                        binary_sha256=record['binary_sha256'], source_hashes=record['source_hashes'],
                        tooling_hashes=tree_hashes(snapshot), build_directory=str(build))
    write_json(out / 'registration.json', registration)
    shutil.copyfile(build / 'build.json', out / 'build.json')
    for name in ('runs', 'cases', 'logs', 'archives', 'attempts'):
        (out / name).mkdir()
    for case in plan['cases']:
        write_json(out / 'cases' / (case['name'] + '.json'), case)
    write_json(out / 'campaign_state.json', dict(status='registered', expected=len(names), attempted=0))
    return dict(registered=len(names), directory=str(out), plan_sha256=registration['plan_sha256'])


def validate_registration(out, build=None):
    from limerlab.runner import resolve_build
    out = Path(out).resolve()
    registration = read_json(out / 'registration.json')
    if digest_json(registration['plan']) != registration['plan_sha256']:
        raise ValueError('Registered plan changed')
    if tree_hashes(out / 'tooling') != registration['tooling_hashes']:
        raise ValueError('Frozen toolchain or configuration changed')
    if build is not None:
        record, _, _ = resolve_build(build)
        if sha(Path(build) / 'build.json') != registration['build_sha256'] or record['binary_sha256'] != registration['binary_sha256']:
            raise ValueError('Registered build changed')
    for case in registration['plan']['cases']:
        if read_json(out / 'cases' / (case['name'] + '.json')) != case:
            raise ValueError('Registered case changed: ' + case['name'])
    return registration


def execute(out, workers=1, timeout_seconds=5400, resume=False,
            exclude_conditions=None, only_conditions=None):
    out = Path(out).resolve()
    registration = read_json(out / 'registration.json')
    cases = registration['plan']['cases']
    if exclude_conditions and only_conditions:
        raise ValueError('exclude_conditions and only_conditions are mutually exclusive')
    excluded, included = set(exclude_conditions or ()), set(only_conditions or ())
    known_conditions = {case['condition'] for case in cases}
    unknown = (excluded | included) - known_conditions
    if unknown:
        raise ValueError('Unknown registered condition: ' + ', '.join(sorted(unknown)))
    selected = [case for case in cases if (not included or case['condition'] in included)
                and case['condition'] not in excluded]
    build = Path(registration['build_directory'])
    validate_registration(out, build)
    if workers < 1:
        raise ValueError('Workers must be positive')
    attempted = {p.stem for p in (out / 'attempts').glob('*.json')}
    if attempted and not resume:
        raise ValueError('Attempts already exist; use --resume to continue without replacing failed attempts')
    for name in attempted:
        attempt = read_json(out / 'attempts' / (name + '.json'))
        if attempt.get('archive_sha256'):
            if sha(out / 'archives' / (name + '.tar.gz')) != attempt['archive_sha256']:
                raise ValueError('Retained archive changed: ' + name)
    lock = threading.Lock()

    def state(status):
        write_json(out / 'campaign_state.json', dict(status=status, attempted=len(attempted), expected=len(cases),
                   registered_cases_remaining=sum(case['name'] not in attempted for case in cases),
                   selected_conditions=sorted(included) if included else sorted(known_conditions - excluded),
                   updated_utc=datetime.now(timezone.utc).isoformat()))

    def run(case):
        name = case['name']
        destination = out / 'runs' / name
        attempt = dict(name=name, valid=False, status='runner_error')
        try:
            if destination.exists():
                raise ValueError('Incomplete attempt retained; it cannot be overwritten or silently rerun')
            command = [sys.executable, str(out / 'tooling/limer.py'), 'run', '--build', str(build),
                       '--out', str(destination), '--case', str(out / 'cases' / (name + '.json')),
                       '--archive-to', str(out / 'archives' / (name + '.tar.gz')), '--prune-raw']
            with (out / 'logs' / (name + '.log')).open('w') as log:
                process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout_seconds)
            attempt['exit_code'] = process.returncode
            if process.returncode:
                raise RuntimeError('Runner or independent audit returned nonzero')
            result = read_json(destination / 'result.json')
            score = score_run(destination, case)
            archive = out / 'archives' / (name + '.tar.gz')
            if sha(archive) != result['archive']['sha256']:
                raise ValueError('Retained archive failed verification')
            attempt.update(valid=score['valid'], status=result['status']['status'],
                           archive_sha256=result['archive']['sha256'], score=score)
        except Exception as error:
            attempt['error'] = str(error)
        write_json(out / 'attempts' / (name + '.json'), attempt)
        with lock:
            attempted.add(name)
            state('running')
        print(json.dumps(dict(name=name, status=attempt['status'], valid=attempt['valid'])), flush=True)

    state('running')
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run, c) for c in selected if c['name'] not in attempted]
            for future in as_completed(futures):
                future.result()
    finally:
        if any(case['name'] not in attempted for case in cases):
            state('partial_registered_cases_remaining')
        else:
            state('complete_with_retained_errors' if any(not read_json(p)['valid'] for p in (out / 'attempts').glob('*.json')) else 'complete')
        summarize(out)


def summarize(out):
    out = Path(out).resolve()
    registration = validate_registration(out)
    cases = registration['plan']['cases']
    rows, groups = [], {}
    for case in cases:
        name = case['name']
        attempt_path, result_path = out / 'attempts' / (name + '.json'), out / 'runs' / name / 'result.json'
        attempt = read_json(attempt_path) if attempt_path.exists() else None
        result = read_json(result_path) if result_path.exists() else None
        score = dict(classification='not_run', valid=False, all_paths_timely_success=False,
                     first_incident_timely_success=False, all_paths_delay_ms=None,
                     first_incident_delay_ms=None, healthy_false_alarm=False, healthy_exposure_ms=0)
        if attempt:
            try:
                score = score_run(out / 'runs' / name, case)
                if not attempt['valid']:
                    score.update(classification='error', valid=False, all_paths_timely_success=False,
                                 first_incident_timely_success=False)
            except Exception as error:
                score.update(classification='error', error=str(error))
        scene = case['scene']
        complete = bool(score['valid'] and result and result['status']['status'] == 'completed')
        performance = result['performance'] if result else {}
        row = dict(name=name, condition=case['condition'], detector=case['detector'], arm=case['arm'],
                   trial=case['trial'], pair_id=case['pair_id'], seed=scene['seed'], node=scene['node'],
                   fault_ns=scene['fault_ns'], horizon_ms=scene['horizon_ns'] / 1e6,
                   classification=score['classification'], valid=score['valid'],
                   all_paths_timely=score['all_paths_timely_success'],
                   first_incident_timely=score['first_incident_timely_success'],
                   all_paths_delay_ms=score['all_paths_delay_ms'],
                   first_incident_delay_ms=score['first_incident_delay_ms'],
                   healthy_false_alarm=score['healthy_false_alarm'],
                   healthy_exposure_ms=score['healthy_exposure_ms'],
                   completed=complete, communication_ms=performance.get('communication_ms') if complete else None,
                   restricted_ms=performance.get('restricted_communication_ms'),
                   recovered=performance.get('recovery_observed'),
                   proxy_chunks=result['status'].get('proxy_chunks') if result else None,
                   monitoring_complete=bool(attempt and score.get('monitoring_complete', False)))
        # Invalid or absent attempts retain a cap penalty rather than gaining
        # a deceptively favorable zero runtime or dropping out of paired means.
        row['capped_ms'] = row['communication_ms'] if complete else (scene['horizon_ns'] - 1_000_000) / 1e6
        rows.append(row)
        groups.setdefault((case['condition'], case['detector'], case['arm']), []).append(row)
    group_rows = []
    for (condition, detector, arm), members in sorted(groups.items()):
        n, k = len(members), sum(r['all_paths_timely'] for r in members)
        healthy = condition == 'healthy'
        counts = {label: sum(r['classification'] == label for r in members)
                  for label in sorted({r['classification'] for r in members})}
        valid_count = sum(r['valid'] for r in members)
        group_rows.append(dict(condition=condition, detector=detector, arm=arm, registered=n,
                               verified=valid_count, classifications=counts, timely_trials=k,
                               empirical_timely_rate=k / n if not healthy else None,
                               exact_one_sided_95_lower=exact_lower_bound(k, n) if not healthy else None,
                               empirical_target_met=k / n >= .95 if not healthy else None,
                               first_incident_timely_trials=sum(r['first_incident_timely'] for r in members),
                               p95_all_trials_ms=percentile95([r['all_paths_delay_ms'] if r['valid'] else None for r in members]) if not healthy else None,
                               p95_all_trials_unbounded=not healthy and percentile95([r['all_paths_delay_ms'] if r['valid'] else None for r in members]) is None,
                               healthy_false_alarm_trials=sum(r['healthy_false_alarm'] for r in members) if healthy else None,
                               verified_healthy_exposure_ms=sum(r['healthy_exposure_ms'] for r in members if r['valid']) if healthy else None,
                               completed=sum(r['completed'] for r in members),
                               mean_capped_ms=sum(r['capped_ms'] for r in members) / n,
                               invalid_or_missing=n - valid_count))
    pairs = []
    paired = {}
    for row in rows:
        paired.setdefault(row['pair_id'], {})[row['arm']] = row
    for pair_id, arms in sorted(paired.items()):
        if set(arms) != set(ARMS):
            continue
        benefit, always, no_proxy = (arms[a] for a in ('benefit', 'always', 'no_proxy'))
        valid = all(arms[a]['valid'] for a in ARMS)
        pairs.append(dict(pair_id=pair_id, condition=benefit['condition'], detector=benefit['detector'],
                          valid=valid, benefit_completed=benefit['completed'],
                          always_completed=always['completed'], no_proxy_completed=no_proxy['completed'],
                          benefit_minus_always_capped_ms=benefit['capped_ms'] - always['capped_ms'],
                          benefit_minus_no_proxy_capped_ms=benefit['capped_ms'] - no_proxy['capped_ms'],
                          benefit_completion_ms=benefit['communication_ms'],
                          always_completion_ms=always['communication_ms'],
                          no_proxy_completion_ms=no_proxy['communication_ms']))
    primary_conditions = registration['plan']['scoring']['primary_conditions']
    if not primary_conditions or len(primary_conditions) != len(set(primary_conditions)):
        raise ValueError('Registered primary conditions must be nonempty and unique')
    primary = [g for g in group_rows if g['condition'] in primary_conditions and g['arm'] == 'benefit' and g['detector'] == 'service']
    healthy_groups = [g for g in group_rows if g['condition'] == 'healthy' and g['arm'] == 'benefit' and g['detector'] == 'service']
    primary_pass = len(primary) == len(primary_conditions) and all(g['registered'] >= 60 and g['empirical_target_met'] for g in primary)
    all_attempted = all((out / 'attempts' / (case['name'] + '.json')).exists() for case in cases)
    summary = dict(schema='limer-research-summary-v1', phase=registration['plan']['phase'],
                   registered=len(rows), attempted=sum((out / 'attempts' / (c['name'] + '.json')).exists() for c in cases),
                   primary_conditions=primary_conditions,
                   verified=sum(r['valid'] for r in rows), complete=all_attempted,
                   primary_empirical_95_percent_under_100ms_met=primary_pass,
                   healthy_controls_verified=bool(healthy_groups) and all(g['verified'] == g['registered'] for g in healthy_groups),
                   healthy_false_alarm_trials=sum(g['healthy_false_alarm_trials'] for g in healthy_groups),
                   groups=group_rows, paired_comparisons=pairs,
                   conclusion=('Registered simulation conditions meet the empirical detection target; inspect healthy false alarms and per-condition confidence bounds separately.'
                               if primary_pass else 'The registered detection target is not established; late/missed/invalid/pending trials remain in each condition denominator.'),
                   scope=registration['plan']['scoring']['scope'],
                   limitations=['No claim of general grey-fault coverage or GPU hardware validation.',
                                'Exact binomial bounds are per condition, not simultaneous familywise guarantees.',
                                'Capped unfinished times are lower bounds, not exact completion times; invalid attempts are cap-penalized.',
                                'Canaries continue to the registered horizon even if business work has finished.',
                                'Paired realized differences measure ex post performance; they do not prove the online estimates are optimal.'])
    write_json(out / 'research_summary.json', summary)
    with (out / 'research_trials.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ['name'])
        writer.writeheader(); writer.writerows(rows)
    if pairs:
        with (out / 'research_pairs.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(pairs[0]))
            writer.writeheader(); writer.writerows(pairs)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('plan', 'register'):
        p = commands.add_parser(command)
        p.add_argument('--phase', choices=('development', 'validation'), required=True)
        p.add_argument('--out', type=Path, required=True)
        p.add_argument('--trials', type=int, default=60)
        p.add_argument('--paired-trials', type=int, default=20)
        p.add_argument('--boundary-trials', type=int, default=10)
        p.add_argument('--development-trials', type=int, default=2)
        p.add_argument('--horizon-ms', type=float, default=800)
        p.add_argument('--rounds', type=int, default=8)
        p.add_argument('--chunks', type=int, default=16)
        p.add_argument('--detector', choices=('service', 'legacy', 'both'), default='service')
        p.add_argument('--canary-period-ns', type=int, default=2_000_000)
        p.add_argument('--seed-base', type=int, help='Explicit nonnegative base for a new disjoint development or held-out seed range')
        p.add_argument('--seed-stride', type=int, default=32,
                       help='New-plan seed spacing; validation >=16, development >=1. Historical plans use their frozen tools.')
        p.add_argument('--include-slow-100', action='store_true')
        p.add_argument('--include-delay', action='store_true', help='Add 80 ms access-channel delay as a primary detection condition')
        p.add_argument('--include-slow-quarter', action='store_true', help='Add long-phase 25%% capacity with 1 Gb/s local proxy as a policy boundary')
        if command == 'register':
            p.add_argument('--build', type=Path, required=True)
    run = commands.add_parser('execute')
    run.add_argument('directory', type=Path)
    run.add_argument('--workers', type=int, default=1)
    run.add_argument('--timeout-seconds', type=int, default=5400)
    run.add_argument('--resume', action='store_true')
    selection = run.add_mutually_exclusive_group()
    selection.add_argument('--exclude-condition', action='append', dest='exclude_conditions',
                           help='Defer this registered condition for this invocation only; repeatable')
    selection.add_argument('--only-condition', action='append', dest='only_conditions',
                           help='Submit only this registered condition for this invocation; repeatable')
    report = commands.add_parser('summarize')
    report.add_argument('directory', type=Path)
    a = parser.parse_args()
    if a.command in ('plan', 'register'):
        plan = make_plan(a.phase, a.trials, a.paired_trials, a.boundary_trials, a.development_trials,
                         a.horizon_ms, a.rounds, a.chunks, a.detector, a.include_slow_100, a.canary_period_ns,
                         a.include_delay, a.include_slow_quarter, a.seed_base, a.seed_stride)
        if a.command == 'plan':
            if a.out.exists():
                raise FileExistsError(a.out)
            a.out.parent.mkdir(parents=True, exist_ok=True)
            write_json(a.out, plan)
            print(json.dumps(dict(cases=len(plan['cases']), plan_sha256=digest_json(plan))))
        else:
            print(json.dumps(register(plan, a.build, a.out)))
    elif a.command == 'execute':
        execute(a.directory, a.workers, a.timeout_seconds, a.resume, a.exclude_conditions, a.only_conditions)
    elif a.command == 'summarize':
        result = summarize(a.directory)
        print(json.dumps({k: v for k, v in result.items() if k not in ('groups', 'paired_comparisons')}))


if __name__ == '__main__':
    main()
