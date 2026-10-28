import csv
import dataclasses
import json
import math
from pathlib import Path
import tempfile
import unittest

from limerlab.benefit_policy import BenefitInput, ServiceSample, RelaySample, evaluate_benefit
from limerlab.policy_replay import replay_policy


def table(root, name, header, rows):
    with (root/name).open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(header.split(','))
        writer.writerows(rows)


def fixture(root):
    (root/'run_status.json').write_text(json.dumps(dict(method='G11', chunks_per_phase=16, policy_mode='benefit')))
    table(root, 'logical_events.csv', 'timestamp_ns,event,chunk_id,phase,src,dst,offset,length,acked,epoch,lane,route', [
        [1_000_000, 'ALLOC', 1, 0, 0, 4, 0, 65536, 0, 0, 0, 1],
        [1_000_000, 'ALLOC', 2, 0, 0, 4, 65536, 65536, 0, 0, 1, 2],
        [5_000_000, 'ACK_PROGRESS', 1, 0, 0, 4, 0, 65536, 65536, 0, 0, 1],
        [5_000_000, 'DONE', 1, 0, 0, 4, 0, 65536, 65536, 0, 0, 1],
        [34_100_000, 'MIGRATE', 2, 0, 0, 4, 65536, 65536, 0, 1, 1, 901]])
    table(root, 'peer_events.csv', 'timestamp_ns,event,route,chunk,phase,src,dst,helper_src,helper_dst,rail,relay,probe,length', [
        [28_799_998, 'RESERVE', 900, 0, 0, 0, 4, 1, 5, 1, 1, 1, 65536],
        [30_000_000, 'RELEASE', 900, 0, 0, 0, 4, 1, 5, 1, 1, 1, 65536]])
    table(root, 'leg_events.csv', 'timestamp_ns,event,route,tag,index,src,dst,nic,length', [
        [28_799_998, 'LEG_START', 900, 9001, 0, 0, 1, 1, 65536],
        [28_899_998, 'LEG_DONE', 900, 9001, 0, 0, 1, 1, 65536],
        [28_899_999, 'LEG_START', 900, 9002, 1, 1, 5, 3, 65536],
        [29_899_999, 'LEG_DONE', 900, 9002, 1, 1, 5, 3, 65536],
        [29_900_000, 'LEG_START', 900, 9003, 2, 5, 4, 1, 65536],
        [30_000_000, 'LEG_DONE', 900, 9003, 2, 5, 4, 1, 65536]])
    table(root, 'control_events.csv', 'sent_ns,arrival_ns,event,rank,phase,version,wire_bytes', [
        [34_100_000, 34_100_000, 'ACTIVATE', 0, 0, 1, 0]])
    table(root, 'service_events.csv', 'timestamp_ns,event,path_id,token,bytes', [
        [28_900_000, 'SUBMIT', 12, 500, 65536],
        [29_000_000, 'COMPLETE', 12, 500, 65536]])
    decisions = []
    for t, stage in ((30_000_000, 'probe_complete'), (34_100_000, 'commit')):
        x = BenefitInput(0, 65536, 14*65536,
                         ServiceSample(.65536, known=True), ServiceSample(0., known=True),
                         RelaySample(65536, (100000., 1000000., 100000.), 1007680.,
                                     age_ns=t-30_000_000, known=True),
                         setup_ns=4092160. if stage == 'probe_complete' else 0.)
        predicted = evaluate_benefit(x)
        decision = dict(timestamp_ns=t, src=0, phase=0, stage=stage, input=dataclasses.asdict(x))
        for key in ('should_switch', 'reason', 'stay_ns', 'switch_ns', 'gain_ns'):
            value = predicted[key]
            decision[key] = None if isinstance(value, float) and math.isinf(value) else value
        decisions.append(decision)
    (root/'policy_decisions.jsonl').write_text('\n'.join(json.dumps(d) for d in decisions)+'\n')


class PolicyReplayTests(unittest.TestCase):
    def check_mutation(self, mutate=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            valid = replay_policy(root)
            self.assertTrue(valid['pass'], valid)
            if mutate:
                mutate(root)
                checked = replay_policy(root)
                self.assertFalse(checked['pass'], checked)
            return valid

    def decisions(self, root, change):
        path = root/'policy_decisions.jsonl'
        data = [json.loads(line) for line in path.read_text().splitlines()]
        change(data)
        path.write_text('\n'.join(json.dumps(d) for d in data)+'\n')

    def test_valid_observable_replay(self):
        result = self.check_mutation()
        self.assertEqual(result['decisions_checked'], 2)
        self.assertFalse(result['truth_accessed'])

    def test_prediction_tamper_rejected(self):
        self.check_mutation(lambda root: self.decisions(root, lambda d: d[0].update(should_switch=False)))

    def test_owned_bytes_tamper_rejected_even_when_policy_recomputed(self):
        def mutate(root):
            def change(data):
                data[0]['input']['b_bytes'] += 65536
                raw = dict(data[0]['input'])
                a, b, relay = [raw.pop(k) for k in ('service_a', 'service_b', 'relay')]
                predicted = evaluate_benefit(BenefitInput(
                    service_a=ServiceSample(**a), service_b=ServiceSample(**b),
                    relay=RelaySample(**relay), **raw))
                for key in ('should_switch', 'reason', 'stay_ns', 'switch_ns', 'gain_ns'):
                    value = predicted[key]
                    data[0][key] = None if isinstance(value, float) and math.isinf(value) else value
            self.decisions(root, change)
        self.check_mutation(mutate)

    def test_probe_leg_duration_tamper_rejected(self):
        self.check_mutation(lambda root: (root/'leg_events.csv').write_text(
            (root/'leg_events.csv').read_text().replace('28899999', '28899990')))

    def test_probe_payload_tamper_rejected(self):
        self.check_mutation(lambda root: (root/'peer_events.csv').write_text(
            (root/'peer_events.csv').read_text().replace(',65536', ',1024')))

    def test_canary_fallback_service_tamper_rejected(self):
        self.check_mutation(lambda root: (root/'service_events.csv').write_text(
            (root/'service_events.csv').read_text().replace('29000000', '29100000')))

    def test_initial_activation_requires_commit(self):
        self.check_mutation(lambda root: self.decisions(root, lambda d: d.pop()))

    def test_activation_in_other_phase_rejected(self):
        self.check_mutation(lambda root: (root/'control_events.csv').write_text(
            (root/'control_events.csv').read_text().replace('ACTIVATE,0,0,', 'ACTIVATE,0,1,')))

    def test_current_control_cost_cannot_be_omitted(self):
        def mutate(root):
            path = root/'control_events.csv'
            data = path.read_text().splitlines()
            data.insert(1, '29999999,31007679,OTHER,0,0,1,96')
            path.write_text('\n'.join(data)+'\n')
        self.check_mutation(mutate)

    def test_missing_logs_fail_closed(self):
        self.check_mutation(lambda root: (root/'leg_events.csv').unlink())

    def test_no_fault_inputs_are_required_or_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            (root/'injection.txt').write_text('INVALID SECRET TRUTH')
            (root/'fault_events.csv').write_text('INVALID SECRET TRUTH')
            (root/'run_manifest.json').write_text('INVALID SECRET TRUTH')
            self.assertTrue(replay_policy(root)['pass'])

    def test_service_mode_probe_requires_delivered_health_report(self):
        def mutate(root):
            path = root/'run_status.json'
            value = json.loads(path.read_text())
            value['detector_mode'] = 'service'
            path.write_text(json.dumps(value))
        self.check_mutation(mutate)

    def test_valid_delivered_service_health_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            status = json.loads((root/'run_status.json').read_text())
            status['detector_mode'] = 'service'
            (root/'run_status.json').write_text(json.dumps(status))
            table(root, 'control_events.csv', 'sent_ns,arrival_ns,event,rank,phase,version,wire_bytes', [
                [30_000_000, 31_007_680, 'HEALTH_REPORT', 0, 0, 900, 96],
                [35_200_000, 35_200_000, 'ACTIVATE', 0, 0, 1, 0]])
            def change(data):
                for decision, timestamp in zip(data, (31_100_000, 35_200_000)):
                    decision['timestamp_ns'] = timestamp
                    decision['input']['relay']['age_ns'] = timestamp-30_000_000
            self.decisions(root, change)
            checked = replay_policy(root)
            self.assertTrue(checked['pass'], checked)
            self.assertIn('charged delivered health reports', checked['checks'])

    def test_future_health_report_cannot_authorize_measurement(self):
        def mutate(root):
            path = root/'control_events.csv'
            data = path.read_text().splitlines()
            data.insert(1, '30000000,31007680,HEALTH_REPORT,0,0,900,96')
            path.write_text('\n'.join(data)+'\n')
        self.check_mutation(mutate)

    def test_health_report_for_other_route_cannot_authorize_probe(self):
        def mutate(root):
            path = root/'control_events.csv'
            data = path.read_text().splitlines()
            data.insert(1, '28000000,29007680,HEALTH_REPORT,0,0,901,96')
            path.write_text('\n'.join(data)+'\n')
        self.check_mutation(mutate)

    def test_health_report_sent_before_physical_measurement_rejected(self):
        def mutate(root):
            path = root/'control_events.csv'
            data = path.read_text().splitlines()
            data.insert(1, '28000000,29007680,HEALTH_REPORT,0,0,900,96')
            path.write_text('\n'.join(data)+'\n')
        self.check_mutation(mutate)


if __name__ == '__main__':
    unittest.main()
