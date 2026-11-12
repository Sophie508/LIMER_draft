"""Verify terminal-only repair locality against the retained original traces."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GROUP = 'confirmation-terminal-fix'
SELECTED = {'healthy', 'sustained_50_early', 'blackhole'}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def controls(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def verify():
    old = ROOT / 'evidence/confirmation-v2'
    new = ROOT / 'evidence-terminal-fix' / GROUP
    original, repaired = (read(p / 'registration.json') for p in (old, new))
    assert original['plan'] == repaired['plan'], 'Condition or seed changed'
    assert original['binary_sha256'] != repaired['binary_sha256']
    old_hashes, new_hashes = original['source_hashes'], repaired['source_hashes']
    assert set(old_hashes) == set(new_hashes)
    changed = sorted(n for n in old_hashes if old_hashes[n] != new_hashes[n])
    assert changed == ['src/simulator/recovery/proxy.h',
                       'src/simulator/runtime/completion.h'], changed
    old_tools, new_tools = original['tooling_hashes'], repaired['tooling_hashes']
    tool_changes = sorted(n for n in old_tools.keys() | new_tools.keys()
                          if old_tools.get(n) != new_tools.get(n))
    assert tool_changes == sorted(changed + ['tests/test_helper_lease_v2.py',
        'tests/test_relay_pipeline.py', 'tests/test_terminal_lease_cleanup.py'])
    summary = read(new / 'gray_gate_summary.json')
    rows = summary['rows']
    attempted = [r for r in rows if r['attempted']]
    assert len(rows) == 30 and len(attempted) == 10
    assert all(r['attempted'] == (r['condition'] in SELECTED) for r in rows)
    assert all(r['valid'] and r['completed'] for r in attempted)
    comparisons = []
    for row in attempted:
        name = row['name']
        before, after = old / 'runs' / name, new / 'runs' / name
        previous, current = (read(p / 'run_status.json') for p in (before, after))
        done = current['job_done_ns']
        assert previous['job_done_ns'] == done, name
        assert sha(before / 'policy_decisions.jsonl') == sha(after / 'policy_decisions.jsonl'), name
        assert sha(before / 'service_alarms.csv') == sha(after / 'service_alarms.csv'), name
        old_control, new_control = (controls(p / 'control_events.csv') for p in (before, after))
        prefix = lambda events: [r for r in events if int(r['sent_ns']) < done]
        assert prefix(old_control) == prefix(new_control), name
        terminal_leases = []
        if row['arm'] == 'candidate_gate':
            final_phase = str(current['phases_expected'] - 1)
            requested = {r['version'] for r in new_control
                         if r['phase'] == final_phase and r['event'] == 'LEND_TX'}
            released = {r['version'] for r in new_control
                        if r['phase'] == final_phase and r['event'] == 'LEND_RELEASED'}
            assert requested <= released, (name, requested - released)
            terminal_leases = sorted(requested, key=int)
        prior_attempt = read(old / 'attempts' / (name + '.json'))
        comparisons.append(dict(name=name, original_valid=prior_attempt['valid'],
            repaired_valid=row['valid'], job_done_ns=done,
            detection_class=row['classification'],
            same_completion_timestamp=True, same_policy_stream=True,
            same_alarm_stream=True, same_precompletion_control=True,
            final_phase_leases_all_released=terminal_leases))
    failure = 'sustained_50_early-candidate_gate-s111213033'
    assert not read(old / 'attempts' / (failure + '.json'))['valid']
    record = dict(registered=30, attempted=10, valid=10, completed=10, unrun=20,
        original_failure_retained=True, native_changed_files=changed,
        tooling_changed_files=tool_changes, comparisons=comparisons,
        scope='Targeted terminal cleanup regression; not full performance qualification or independent detection evidence.')
    (ROOT / 'verification/terminal-repair-locality.json').write_text(json.dumps(record, indent=2) + '\n')
    text = ['# Terminal cleanup repair: targeted regression', '',
        'The separately built `project-terminal-fix` repairs terminal lease cleanup.',
        'All 10 preselected native cases passed the unchanged execution and observation',
        'audits. The registration retains 30 definitions; the other 20 are intentionally',
        'unrun. This is a post-failure correctness check, not a new full performance',
        'confirmation or additional independent detection trials.', '',
        '| Condition | Arm | Communication ms | Detection class |',
        '| --- | --- | ---: | --- |']
    for row in attempted:
        text.append(f'| {row["condition"]} | {row["arm"]} | {row["communication_ms"]:.6f} | {row["classification"]} |')
    missed = [r for r in attempted if r['classification'] == 'miss']
    if missed:
        text += ['', '**Execution validity does not imply detection success.**',
            f'{len(missed)} selected runs still have missed-path detection outcomes:']
        for row in missed:
            score = read(new / 'attempts' / (row['name'] + '.json'))['score']
            missing = sorted(set(score['affected_path_ids']) - set(score['observed_affected_path_ids']))
            text.append(f'- `{row["name"]}`: observed paths {score["observed_affected_path_ids"]}; '
                        f'missed paths {missing} through the 250-ms monitor horizon.')
        text += ['', 'The original and repaired alarm streams match exactly. This detector',
            'limitation predates the cleanup repair and remains unresolved; these',
            'runs do not meet the all-affected-paths-below-100-ms target.']
    text += ['', 'For every selected case, the business completion timestamp, policy-decision',
        'stream, detection-alarm stream and control records sent before completion',
        'are identical to the retained original trace. Every requested final-phase',
        'candidate lease now has its paid release recorded. Cleanup does not make',
        'the business job finish sooner; post-completion message costs remain charged.', '',
        'The original sustained-50% candidate remains invalid in the main result table.',
        'Its timestamp is used only to check repair locality, not as an accepted old',
        'performance measurement. All other original outcomes remain unchanged.', '',
        'The repaired source has only two changed native files and three test changes',
        'relative to `project`. The full local suite passes 216 tests. This repair',
        'does not address the conservative rate/helper forecast or establish the',
        '70%–80% throughput target across gray-fault workloads.', '',
        'Protocol: `research/TERMINAL_REPAIR_PROTOCOL.md`. Full compact/source',
        'verification: `verification/compact-terminal-fix.json`. Exact comparisons:',
        '`verification/terminal-repair-locality.json`. Diff: `review/terminal-fix.diff`.', '']
    (ROOT / 'TERMINAL_REPAIR_RESULTS.md').write_text('\n'.join(text))
    print(json.dumps({k: record[k] for k in ('registered', 'attempted', 'valid', 'completed', 'unrun')}))
    return record


if __name__ == '__main__':
    verify()
