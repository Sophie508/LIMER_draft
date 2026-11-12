import csv
import dataclasses
import json
import math
from pathlib import Path
import tempfile
import unittest

from limerlab.benefit_policy import BenefitInputV2, HelperSample, evaluate_benefit_v2
from limerlab.policy_replay import replay_policy
from test_policy_replay import fixture, table


def fixture_v2(root):
    fixture(root)
    status=json.loads((root/'run_status.json').read_text())
    status.update(policy_mode='benefit_v2',relay_completion='pipelined',source_window=32,
                  horizon_ns=100_000_000,detector_mode='service')
    (root/'run_status.json').write_text(json.dumps(status))
    path=root/'logical_events.csv'
    with path.open() as stream:
        reader=csv.DictReader(stream);header=reader.fieldnames;logical=list(reader)
    logical=[r for r in logical if r['event']!='MIGRATE']
    for helper in (1,5):
        for i in range(16):
            row=dict(timestamp_ns=1_000_000,event='ALLOC',chunk_id=helper*100+i,
                     phase=0,src=helper,dst=helper+4,offset=i*65536,length=65536,
                     acked=0,epoch=0,lane=i%2,route=helper*100+i)
            logical.append(row)
            logical.append(dict(row,timestamp_ns=20_000_000,event='ACK_PROGRESS',acked=65536))
            logical.append(dict(row,timestamp_ns=20_000_000,event='DONE',acked=65536))
    logical.sort(key=lambda r:int(r['timestamp_ns']))
    table(root,'logical_events.csv',','.join(header),[[r[k] for k in header] for r in logical])
    controls=[
        [25_000_000,26_007_680,'LEND_TX',1,0,76,96],
        [25_000_000,26_015_360,'LEND_RX',5,0,76,96],
        [26_015_360,26_015_360,'LEND_ACTIVE',0,0,76,0],
        [28_700_000,28_700_000,'M13_REPLACEMENT_PREPARE',0,0,77,0],
        [30_000_000,31_007_680,'HEALTH_REPORT',0,0,900,96],
        [31_007_680,32_015_360,'HELPER_QUERY_TX',1,0,1001,96],
        [31_007_680,32_023_040,'HELPER_QUERY_RX',5,0,1002,96],
        [32_015_360,33_023_040,'HELPER_REPORT_TX',0,0,1001,96],
        [32_023_040,33_030_720,'HELPER_REPORT_RX',0,0,1002,96],
        [37_300_000,37_300_000,'ACTIVATE',0,0,77,0]]
    table(root,'control_events.csv','sent_ns,arrival_ns,event,rank,phase,version,wire_bytes',controls)
    reports=[]
    for slot,rank,sampled,delivered in ((0,1,32_015_360,33_023_040),(1,5,32_023_040,33_030_720)):
        report=dict(event='SENT',timestamp_ns=sampled,source=0,slot=slot,rank=rank,
                    phase=0,version=77,lease_id=76,report_id=1001+slot,sampled_ns=sampled,
                    delivered_ns=delivered,own_remaining_bytes=0,own_bytes_per_ns=0.,known=1)
        reports.extend([report,dict(report,event='DELIVERED',timestamp_ns=delivered)])
    reports.sort(key=lambda r:r['timestamp_ns'])
    (root/'helper_reports.jsonl').write_text('\n'.join(json.dumps(r) for r in reports)+'\n')
    decisions=[json.loads(line) for line in (root/'policy_decisions.jsonl').read_text().splitlines()]
    for decision,at in zip(decisions,(33_100_000,37_300_000)):
        raw=decision['input'];raw['relay']['age_ns']=at-30_000_000
        raw.update(b_no_progress_ns=at-1_000_000,tail_debounce_ns=2_000_000,
                   source_window=32,pipelined=True,helpers=[])
        metadata=[]
        for slot in (0,1):
            report=next(r for r in reports if r['slot']==slot and r['event']=='DELIVERED')
            raw['helpers'].append(dict(own_remaining_bytes=0,own_bytes_per_ns=0.,
                                      age_ns=at-report['sampled_ns'],known=True))
            metadata.append({k:report[k] for k in ('report_id','rank','phase','version',
                                                  'lease_id','sampled_ns','delivered_ns')})
        decision.update(timestamp_ns=at,policy_version=2,helper_reports=metadata)
        recompute(decision)
    write_decisions(root,decisions)


def recompute(decision):
    from limerlab.benefit_policy import ServiceSample,RelaySample
    raw=dict(decision['input'])
    for name in ('service_a','service_b'):raw[name]=ServiceSample(**raw[name])
    raw['relay']=RelaySample(**raw['relay'])
    raw['helpers']=tuple(HelperSample(**h) for h in raw['helpers'])
    predicted=evaluate_benefit_v2(BenefitInputV2(**raw))
    for key,value in predicted.items():
        decision[key]=None if isinstance(value,float) and math.isinf(value) else value


def write_decisions(root,decisions):
    (root/'policy_decisions.jsonl').write_text('\n'.join(json.dumps(d) for d in decisions)+'\n')


class PolicyReplayV2Tests(unittest.TestCase):
    def check_mutation(self,mutation=None):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture_v2(root)
            valid=replay_policy(root);self.assertTrue(valid['pass'],valid)
            if mutation:
                mutation(root)
                result=replay_policy(root);self.assertFalse(result['pass'],result)
            return valid

    def mutate_decision(self,root,change):
        decisions=[json.loads(line) for line in (root/'policy_decisions.jsonl').read_text().splitlines()]
        change(decisions[0]);recompute(decisions[0]);write_decisions(root,decisions)

    def test_independent_replay_checks_v2_paid_reports_and_tail(self):
        result=self.check_mutation()
        self.assertEqual(result['decisions_checked'],2)
        self.assertIn('chunk-local no-progress age',result['checks'])

    def test_recomputed_tail_age_tamper_rejected(self):
        self.check_mutation(lambda root:self.mutate_decision(root,
            lambda d:d['input'].update(b_no_progress_ns=123)))

    def test_recomputed_helper_work_tamper_rejected(self):
        self.check_mutation(lambda root:self.mutate_decision(root,
            lambda d:d['input']['helpers'][0].update(own_remaining_bytes=65536)))

    def test_wrong_physical_helper_report_rejected(self):
        self.check_mutation(lambda root:self.mutate_decision(root,
            lambda d:d['helper_reports'][0].update(rank=2)))

    def test_invented_sender_window_rejected(self):
        self.check_mutation(lambda root:self.mutate_decision(root,
            lambda d:d['input'].update(source_window=999)))

    def test_unsent_helper_report_rejected(self):
        def change(root):
            p=root/'helper_reports.jsonl'
            rows=[json.loads(line) for line in p.read_text().splitlines()]
            rows=[r for r in rows if r['event']!='SENT']
            p.write_text('\n'.join(json.dumps(r) for r in rows))
        self.check_mutation(change)

    def test_unpaid_helper_report_rejected(self):
        self.check_mutation(lambda root:(root/'control_events.csv').write_text(
            (root/'control_events.csv').read_text().replace('HELPER_REPORT_TX,0,0,1001,96','HELPER_REPORT_TX,0,0,1001,0')))

    def test_helper_snapshot_tamper_rejected_from_logical_acks(self):
        def change(root):
            p=root/'helper_reports.jsonl'
            rows=[json.loads(line) for line in p.read_text().splitlines()]
            for r in rows:r['own_remaining_bytes']=1
            p.write_text('\n'.join(json.dumps(r) for r in rows))
        self.check_mutation(change)


if __name__=='__main__': unittest.main()
