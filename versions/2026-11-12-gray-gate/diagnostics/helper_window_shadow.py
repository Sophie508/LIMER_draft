#!/usr/bin/env python3
"""Read-only helper-window shadow; write reports only to a new output directory.

No native process is launched. The original ACK trajectory remains unchanged.
Both the ACK numerator and its interval are intersected with the current phase.
"""
import argparse
import bisect
import copy
import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import sys
import tarfile

sys.dont_write_bytecode = True


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    return value


class HashingReader(io.RawIOBase):
    """Hash exactly the member bytes consumed by the CSV parser."""
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.stream.read(len(buffer))
        self.digest.update(data)
        buffer[:len(data)] = data
        return len(data)


def cumulative(values, time_ns, inclusive):
    at = bisect.bisect_right(values, (time_ns, 10**30 if inclusive else -1)) - 1
    return values[at][1] if at >= 0 else 0


def amount(values, start, end):
    return cumulative(values, end, True) - cumulative(values, start, False)


def load_policy(tooling, registration):
    policy_path = tooling / 'python/limerlab/benefit_policy.py'
    expected = registration['tooling_hashes']['python/limerlab/benefit_policy.py']
    actual = sha(policy_path)
    require(actual == expected, 'Frozen policy source differs from registration')
    spec = importlib.util.spec_from_file_location('limer_shadow_frozen_policy', policy_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, actual


def evaluate(policy, raw):
    value = copy.deepcopy(raw)
    for key in ('service_a', 'service_b'):
        value[key] = policy.ServiceSample(**value[key])
    value['relay'] = policy.RelaySample(**value['relay'])
    value['helpers'] = tuple(policy.HelperSample(**h) for h in value['helpers'])
    return policy.evaluate_benefit_v2(policy.BenefitInputV2(**value))


def analyze(args):
    root, archive, tooling = args.run.resolve(), args.archive.resolve(), args.tooling.resolve()
    attempt_path = args.attempt.resolve() if args.attempt else root.parent.parent / 'attempts' / (root.name + '.json')
    registration_path = args.registration.resolve() if args.registration else root.parent.parent / 'registration.json'
    attempt, registration = read_json(attempt_path), read_json(registration_path)
    require(attempt.get('valid') is True and attempt.get('name') == root.name,
            'A matching accepted attempt is required')
    manifest = read_json(root / 'archive_manifest.json')
    archive_hash = sha(archive)
    require(archive_hash == attempt['archive_sha256'] == manifest['sha256'],
            'Archive hash differs from accepted attempt or member manifest')
    source_hashes = {}
    for name in ('policy_decisions.jsonl', 'helper_reports.jsonl', 'phase_events.csv'):
        actual = sha(root / name)
        require(actual == manifest['files'][name], 'Compact file differs from archive manifest: ' + name)
        source_hashes[name] = actual
    if attempt.get('score', {}).get('policy_evidence_sha256'):
        require(source_hashes['policy_decisions.jsonl'] == attempt['score']['policy_evidence_sha256'],
                'Policy evidence differs from accepted score')
    policy, policy_source_hash = load_policy(tooling, registration)
    decisions = [json.loads(line) for line in (root / 'policy_decisions.jsonl').read_text().splitlines() if line.strip()]
    if args.expect_decisions is not None:
        require(len(decisions) == args.expect_decisions, 'Unexpected decision denominator')
    with (root / 'phase_events.csv').open() as stream:
        phases = {int(r['phase']): int(r['timestamp_ns']) for r in csv.DictReader(stream)}
    reports = {}
    for line in (root / 'helper_reports.jsonl').read_text().splitlines():
        row = json.loads(line)
        if row['event'] == 'DELIVERED':
            require(row['report_id'] not in reports, 'Duplicate delivered helper report')
            reports[row['report_id']] = row
    acks, phase_acks, running, phase_running, old = {}, {}, {}, {}, {}
    member_name = args.logical_member
    require(member_name in manifest['files'], 'Logical member missing from accepted archive manifest')
    with tarfile.open(archive, 'r|gz') as packed:
        found = False
        for member in packed:
            if member.name != member_name:
                continue
            require(member.isfile() and not found, 'Logical member must be a unique regular file')
            found = True
            hashed = HashingReader(packed.extractfile(member))
            with io.TextIOWrapper(io.BufferedReader(hashed)) as stream:
                for row in csv.DictReader(stream):
                    ident, rank, phase, timestamp = (int(row[k]) for k in ('chunk_id', 'src', 'phase', 'timestamp_ns'))
                    if row['event'] == 'ALLOC':
                        require(ident not in old, 'Duplicate logical allocation')
                        old[ident] = 0
                    elif row['event'] == 'ACK_PROGRESS':
                        require(ident in old, 'ACK without allocation')
                        delta = int(row['acked']) - old[ident]
                        require(delta >= 0, 'Logical ACK regressed')
                        old[ident] = int(row['acked'])
                        running[rank] = running.get(rank, 0) + delta
                        acks.setdefault(rank, []).append((timestamp, running[rank]))
                        key = phase, rank
                        phase_running[key] = phase_running.get(key, 0) + delta
                        phase_acks.setdefault(key, []).append((timestamp, phase_running[key]))
            member_hash = hashed.digest.hexdigest()
        require(found, 'Logical member not found in archive')
    require(member_hash == manifest['files'][member_name], 'Logical member hash differs from accepted manifest')
    for values in list(acks.values()) + list(phase_acks.values()):
        require(all(a <= b for a, b in zip(values, values[1:])), 'ACK events are not ordered')
    items = []
    output_keys = ('should_switch', 'reason', 'stay_ns', 'switch_ns', 'gain_ns',
                   'source_stay_ns', 'source_switch_ns', 'helper_stay_ns',
                   'helper_switch_ns', 'relay_assigned_bytes', 'tail_forecast_ns', 'relay_bytes_per_ns')
    for index, decision in enumerate(decisions):
        original = evaluate(policy, decision['input'])
        for key in output_keys:
            value = clean(original[key])
            equal = value == decision[key] if key in ('should_switch', 'reason') or value is None else math.isclose(value, decision[key], rel_tol=1e-10, abs_tol=1e-6)
            require(equal, 'Original native/Python prediction differs at decision {}: {}'.format(index, key))
        shadow, details = copy.deepcopy(decision['input']), []
        require(len(decision['helper_reports']) == 2, 'Two paid helper reports required')
        for slot, meta in enumerate(decision['helper_reports']):
            report = reports[meta['report_id']]
            require(all(meta[key] == report[key] for key in ('report_id', 'rank', 'phase', 'version', 'lease_id', 'sampled_ns', 'delivered_ns')),
                    'Decision helper identity differs from paid report')
            phase, rank, sampled = (int(report[key]) for key in ('phase', 'rank', 'sampled_ns'))
            require(phase == int(decision['phase']) and report['delivered_ns'] <= decision['timestamp_ns'],
                    'Wrong-phase or not-yet-delivered helper report')
            helper = decision['input']['helpers'][slot]
            require(helper['own_remaining_bytes'] == report['own_remaining_bytes']
                    and helper['own_bytes_per_ns'] == report['own_bytes_per_ns']
                    and helper['age_ns'] == decision['timestamp_ns'] - sampled,
                    'Decision helper observation differs from paid report')
            old_start = sampled - 10_000_000
            new_start = max(old_start, phases[phase])
            duration = max(1, sampled - new_start)
            old_n = amount(acks.get(rank, []), old_start, sampled)
            require(math.isclose(old_n / 10_000_000., report['own_bytes_per_ns'], rel_tol=0, abs_tol=1e-12),
                    'Original helper numerator differs from raw ACK events')
            values = phase_acks.get((phase, rank), [])
            new_n = amount(values, new_start, sampled)
            shadow['helpers'][slot]['own_bytes_per_ns'] = new_n / duration
            times = [t for t, _ in values if new_start <= t <= sampled]
            details.append(dict(slot=slot, rank=rank, report_id=meta['report_id'], phase=phase,
                phase_start_ns=phases[phase], sampled_ns=sampled, delivered_ns=report['delivered_ns'],
                decision_ns=decision['timestamp_ns'], old_window_start_ns=old_start, new_window_start_ns=new_start,
                old_window_ns=10_000_000, new_window_ns=duration, old_ack_bytes=old_n, new_ack_bytes=new_n,
                discarded_ack_bytes=old_n-new_n, first_current_window_ack_ns=min(times) if times else None,
                last_current_window_ack_ns=max(times) if times else None,
                own_remaining_bytes=report['own_remaining_bytes'], old_bytes_per_ns=report['own_bytes_per_ns'],
                shadow_bytes_per_ns=new_n/duration))
        comparison = copy.deepcopy(shadow)
        for slot in (0, 1):
            comparison['helpers'][slot]['own_bytes_per_ns'] = decision['input']['helpers'][slot]['own_bytes_per_ns']
        require(comparison == decision['input'], 'Shadow changed an input other than helper service')
        new = evaluate(policy, shadow)
        items.append(dict(index=index, timestamp_ns=decision['timestamp_ns'], src=decision['src'], phase=decision['phase'],
            stage=decision['stage'], original_input=decision['input'], shadow_input=shadow, helper_windows=details,
            original_prediction=original, shadow_prediction=new,
            decision_flipped=bool(original['should_switch']) != bool(new['should_switch']),
            reason_changed=original['reason'] != new['reason']))
    output = clean(dict(schema='limer-helper-window-shadow-v1',
        scope='offline same-realized-trajectory prediction shadow; not an intervention, new native run, or implemented online policy',
        campaign=str(root.parent.parent), run=root.name, attempt_valid=True, archive_sha256=archive_hash,
        logical_archive_member=member_name, logical_member_sha256=member_hash,
        compact_source_sha256=source_hashes, policy_sha256=source_hashes['policy_decisions.jsonl'],
        frozen_policy_source_sha256=policy_source_hash,
        change='helper ACK window intersected with current phase; both numerator and denominator rebuilt; report age not subtracted; every other input and threshold unchanged',
        thresholds=dict(min_gain_ns=1_000_000, min_gain_fraction=.10, max_age_ns=20_000_000, tail_debounce_ns=2_000_000),
        decisions=items, summary=dict(decisions=len(items), helper_reports_checked=sum(len(x['helper_windows']) for x in items),
            original_switches=sum(bool(x['original_prediction']['should_switch']) for x in items),
            shadow_switches=sum(bool(x['shadow_prediction']['should_switch']) for x in items),
            decision_flips=sum(x['decision_flipped'] for x in items), reason_changes=sum(x['reason_changed'] for x in items),
            windows_shortened=sum(h['new_window_ns'] < h['old_window_ns'] for x in items for h in x['helper_windows']),
            windows_with_discarded_ack_bytes=sum(h['discarded_ack_bytes'] > 0 for x in items for h in x['helper_windows']))))
    if args.check_reference:
        reference = read_json(args.check_reference)
        for key in ('run', 'archive_sha256', 'logical_archive_member', 'policy_sha256',
                    'frozen_policy_source_sha256', 'thresholds', 'summary', 'decisions'):
            require(output[key] == reference[key], 'Reproduction differs from reference JSON: ' + key)
        output['reference_comparison'] = dict(pass_=True, reference_sha256=sha(args.check_reference),
                                               note='All decision inputs, rebuilt windows, predictions, thresholds and summary match exactly')
    return output


def markdown(result):
    summary = result['summary']
    lines = ['# Reproduced helper-window shadow', '',
        '**Offline shadow only: no native intervention or performance result.**', '',
        '{} decisions, {} flips, {} original switches, {} shadow switches, {} reason changes.'.format(
            summary['decisions'], summary['decision_flips'], summary['original_switches'],
            summary['shadow_switches'], summary['reason_changes']), '',
        'Both ACK numerator and denominator were phase-clipped. Source/probe/report age/thresholds were unchanged.', '',
        'Archive, raw logical member, compact inputs and frozen policy hashes were verified against accepted manifests.', '',
        '| Index | Timestamp ms | Source | Phase | Original reason | Shadow reason | Shadow stay ms | Shadow switch ms | Flipped |',
        '|---:|---:|---:|---:|---|---|---:|---:|---|']
    for row in result['decisions']:
        old, new = row['original_prediction'], row['shadow_prediction']
        display = lambda x: 'infinity' if x is None else '{:.6f}'.format(x / 1e6)
        lines.append('| {} | {:.6f} | {} | {} | {} | {} | {} | {} | {} |'.format(
            row['index'], row['timestamp_ns']/1e6, row['src'], row['phase'], old['reason'], new['reason'],
            display(new['stay_ns']), display(new['switch_ns']), row['decision_flipped']))
    lines.extend(['', 'See `helper-window-shadow.json` for each paid report, raw reconstructed window and both complete prediction sets.', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True, help='Existing accepted raw .tar.gz archive')
    parser.add_argument('--run', type=Path, required=True, help='Existing compact run directory with archive_manifest.json')
    parser.add_argument('--tooling', type=Path, required=True, help='Existing frozen campaign tooling directory')
    parser.add_argument('--attempt', type=Path, help='Defaults to campaign/attempts/<run>.json')
    parser.add_argument('--registration', type=Path, help='Defaults to campaign/registration.json')
    parser.add_argument('--logical-member', default='logical_events.csv')
    parser.add_argument('--expect-decisions', type=int, default=14)
    parser.add_argument('--check-reference', type=Path, help='Optional previous shadow JSON; require exact decision equality')
    parser.add_argument('--output', type=Path, required=True, help='New directory outside the accepted campaign and tooling; must not exist')
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists(), 'Output already exists; refusing to overwrite: ' + str(output))
    protected = (args.run.resolve(), args.run.resolve().parent.parent, args.archive.resolve().parent, args.tooling.resolve())
    for directory in protected:
        require(output != directory and directory not in output.parents, 'Output must be outside accepted inputs/campaign: ' + str(directory))
    result = analyze(args)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'helper-window-shadow.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    (output / 'helper-window-shadow.md').write_text(markdown(result))
    print(json.dumps(dict(output=str(output), summary=result['summary'],
                          reference_comparison=result.get('reference_comparison')), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
        raise SystemExit('Shadow analysis failed: ' + str(error))
