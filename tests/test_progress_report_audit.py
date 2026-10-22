import copy
import unittest

from simulation.audit_progress_reports import audit_progress


def fixture():
    graph = dict(p=2, flows=[dict(id=1,src=0,dst=1,bytes=1_000_000,plane=0,deps=[])])
    trace = [dict(id=1,event='start',ns=0,port_src=0),
             dict(id=1,event='send',ns=19_000_000,port_src=0),
             dict(id=1,event='recv',ns=20_000_000,port_src=0)]
    model = dict(period_ns=2_000_000,capacity_bps=10_000_000,
                 propagation_ns=1_000_000,launch_delay_ns=3000)
    counts = [0,100_000,200_000,300_000,400_000,500_000,510_000,
              520_000,530_000,540_000,1_000_000,1_000_000]
    records = []
    for index,acked in enumerate(counts):
        sample = index*2_000_000
        for path in range(4):
            start = sample+path*51_200
            records.append(dict(kind='offer',path=path,sample_ns=sample,
                                start_ns=start,end_ns=start+51_200,bytes=64))
        for path in range(4):
            arrival = sample+(path+1)*51_200+1_000_000
            records.append(dict(kind='report',path=path,sample_ns=sample,
                                arrival_ns=arrival,acked_bytes=acked if path==0 else 0,
                                full_busy=path==0 and 4_000_000<=sample<20_000_000))
            if path==0 and index==8:
                records.append(dict(kind='alarm',path=0,decision_ns=arrival))
    return graph,trace,records,model


class ProgressAuditTests(unittest.TestCase):
    def test_causal_reports_and_exact_online_alarm(self):
        result = audit_progress(*fixture())
        self.assertEqual(result['reports'],48)
        self.assertEqual(result['acked_bytes'],1_000_000)
        self.assertEqual(result['alarms'],[dict(path=0,decision_ns=17_051_200)])

    def test_free_reporting_is_rejected(self):
        graph,trace,records,model = fixture()
        records[0]['end_ns'] = 0
        with self.assertRaisesRegex(ValueError,'serialization'):
            audit_progress(graph,trace,records,model)

    def test_changed_online_decision_is_rejected(self):
        graph,trace,records,model = fixture()
        next(r for r in records if r['kind']=='alarm')['decision_ns'] -= 1
        with self.assertRaisesRegex(ValueError,'decision mismatch'):
            audit_progress(graph,trace,records,model)

    def test_ack_credit_cannot_disappear_at_completion(self):
        graph,trace,records,model = fixture()
        records[-4]['acked_bytes'] = 540_000
        with self.assertRaisesRegex(ValueError,'volume'):
            audit_progress(graph,trace,records,model)

    def test_idle_cannot_be_forged_as_full_busy(self):
        graph,trace,records,model = fixture()
        next(r for r in records if r['kind']=='report' and r['path']==1)['full_busy']=True
        with self.assertRaisesRegex(ValueError,'busy'):
            audit_progress(graph,trace,records,model)


if __name__=='__main__':
    unittest.main()
