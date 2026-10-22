import copy
import unittest

from simulation.audit_dynamic_dag import audit_dynamic


class DynamicDagAuditTest(unittest.TestCase):
    def fixture(self):
        graph = dict(p=2, flows=[dict(id=1, src=0, dst=1, bytes=10, plane=0, deps=[]),
                               dict(id=2, src=1, dst=0, bytes=20, plane=0, deps=[1])])
        records = []
        def control(event, ns, rank=-1):
            records.append(dict(event=event, ns=ns, version=1, rank=rank))
        def flow(fid, event, ns, plane, version):
            f=graph['flows'][fid-1]
            records.append(dict(id=fid,event=event,ns=ns,plane=plane,version=version,
                                port_src=f['src']+2*plane,port_dst=f['dst']+2*plane))
        flow(1,'start',0,0,0)
        control('request',1,1)
        def offer(ns, kind, rank, start):
            records.append(dict(event='control_offer',ns=ns,version=1,rank=rank,
                                kind=kind,start_ns=start,end_ns=start+50,bytes=64))
        offer(1,'prepare',0,1);offer(1,'prepare',1,51)
        control('prepare',51,0);offer(51,'ready',0,101)
        control('prepare',101,1);offer(101,'ready',1,151)
        control('ready',151,0);control('ready',201,1)
        offer(201,'commit_delivery',0,201);offer(201,'commit_delivery',1,251)
        control('commit_delivery',251,0);control('commit_delivery',301,1)
        control('activate',302,1)
        flow(1,'send',650,0,0);flow(1,'recv',700,0,0)
        flow(2,'start',700,1,1);flow(2,'send',750,1,1);flow(2,'recv',800,1,1)
        for i,r in enumerate(records):r['order']=i
        return graph,records,[dict(version=1,request_ns=1,affected_rank=1,unavailable_rank=-1)]

    def audit(self,records=None):
        g,r,q=self.fixture()
        return audit_dynamic(g, records if records is not None else r,q,
                             dict(capacity_bps=10_240_000_000,propagation_ns=0,timeout_ns=1000))

    def test_launched_old_flow_and_pending_new_flow_keep_their_ownership(self):
        result=self.audit()
        self.assertEqual(result['changed_flows'],1)
        self.assertEqual(result['control_bytes'],384)

    def test_receive_port_cannot_differ_from_launch(self):
        _,r,_=self.fixture();r[-1]['port_dst']=0
        with self.assertRaisesRegex(ValueError,'ownership'):self.audit(r)

    def test_version_cannot_change_inside_a_launched_transfer(self):
        _,r,_=self.fixture();r[-4]['version']=1
        with self.assertRaisesRegex(ValueError,'ownership'):self.audit(r)

    def test_missing_readiness_cannot_activate(self):
        _,r,_=self.fixture();r=[e for e in r if not(e['event']=='ready' and e['rank']==1)]
        with self.assertRaises(ValueError):self.audit(r)

    def test_unaffected_sender_cannot_change_plane(self):
        _,r,_=self.fixture();r[0].update(plane=1,port_src=2,port_dst=3)
        with self.assertRaisesRegex(ValueError,'route'):self.audit(r)

    def test_dependency_requires_receive_at_the_child_source(self):
        _,r,_=self.fixture();r[-3]['ns']=680
        with self.assertRaises(ValueError):self.audit(r)

    def test_duplicate_completion_is_rejected(self):
        _,r,_=self.fixture();r.append(dict(r[-1],order=len(r)))
        with self.assertRaisesRegex(ValueError,'duplicate'):self.audit(r)

    def test_common_activation_waits_for_all_commit_deliveries(self):
        _,r,_=self.fixture();next(e for e in r if e['event']=='activate')['ns']=300
        with self.assertRaises(ValueError):self.audit(r)

    def test_control_capacity_is_not_free(self):
        g,r,q=self.fixture()
        with self.assertRaisesRegex(ValueError,'serialization'):
            audit_dynamic(g,r,q,dict(capacity_bps=1,propagation_ns=0,timeout_ns=1000))


if __name__=='__main__':unittest.main()
