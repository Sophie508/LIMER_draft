import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"python"))
from limerlab import audit as audit_module
from fixtures import base_relay_fixture

def fixture(root):
    base_relay_fixture(root)
    p = root / 'run_status.json'
    s = json.loads(p.read_text())
    s.update(method='G01', chunks_per_phase=16, new_proxy_chunks=0, rescued_chunks=1,
             scope='M13-driven persistent B-prime replacement v1')
    p.write_text(json.dumps(s))
    with (root / 'control_events.csv').open() as stream:
        controls = list(csv.DictReader(stream))
    original_activation = int(next(r['sent_ns'] for r in controls if r['event'] == 'ACTIVATE'))
    # Give the synthetic initial distributed transaction its real causal delay.
    for name in ['logical_events', 'peer_events', 'leg_events', 'wire_events', 'control_events']:
        p = root / (name + '.csv')
        with p.open() as f:
            reader = csv.DictReader(f)
            columns, data = reader.fieldnames, list(reader)
        for r in data:
            for k in ['timestamp_ns', 'sent_ns', 'arrival_ns']:
                if k in r and int(r[k]) >= original_activation:
                    r[k] = str(int(r[k]) + 4000000)
        if name == 'control_events':
            at = original_activation + 4000000
            for event, sent, arrive in [('PREPARE', at-4000000, at-3000000),
                                        ('READY', at-2000000, at-1000000),
                                        ('COMMIT', at-1000000, at)]:
                for rank in [0, 4, 1, 5]:
                    data.append(dict(sent_ns=sent, arrival_ns=arrive, event=event, rank=rank,
                                     phase=0, version=1, wire_bytes=96))
            data.sort(key=lambda r: int(r['sent_ns']))
        with p.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=columns); w.writeheader(); w.writerows(data)
    (root / 'detector_events.csv').write_text('timestamp_ns,path_id,signal,alarm_origin\n1,13,probe_gap,M13-R\n')


class ClosedLoopAuditTests(unittest.TestCase):
    def check(self, name=None, mutate=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            valid = audit_module.audit(root)
            self.assertTrue(valid['pass_'], valid['errors'])
            if name:
                p = root / name
                p.write_text(mutate(p.read_text()))
                checked = audit_module.audit(root)
                self.assertFalse(checked['pass_'], checked)

    def test_valid_m13_transaction(self): self.check()
    def test_no_alarm_rejected(self):
        self.check('detector_events.csv', lambda s: s.splitlines()[0] + '\n')
    def test_other_paths_alarm_cannot_activate(self):
        self.check('detector_events.csv', lambda s: s.replace(',13,', ',64,'))
    def test_future_alarm_cannot_activate(self):
        self.check('detector_events.csv', lambda s: s.replace('1,13,', '900000000,13,'))
    def test_tail_fallback_rejected(self):
        self.check('control_events.csv', lambda s: s + '1,1,PHASE_LAG_TRIGGER,0,0,1,0\n')
    def test_missing_ready_rejected(self):
        self.check('control_events.csv', lambda s: '\n'.join(r for r in s.splitlines() if ',READY,' not in r) + '\n')
    def test_busy_helper_rejected(self):
        self.check('peer_events.csv', lambda s: s.replace(',0,4,1,5,1,1,', ',0,4,2,5,1,1,'))
    def test_final_target_leg_required(self):
        self.check('leg_events.csv', lambda s: '\n'.join(r for r in s.splitlines() if ',LEG_DONE,1000,10002,2,' not in r) + '\n')
    def test_fresh_proxy_counter_not_rescue_counter(self):
        self.check('run_status.json', lambda s: json.dumps(dict(json.loads(s), new_proxy_chunks=1)))
    def test_fixed_ownership_unchanged(self):
        self.check('logical_events.csv', lambda s: s.replace(',65536,65536,0,0,1,', ',65536,65536,0,0,0,'))


if __name__ == '__main__':
    unittest.main()
