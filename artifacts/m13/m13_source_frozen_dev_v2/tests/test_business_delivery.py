import unittest
from limer_v0.business_delivery import BusinessDeliveryDetector


def report(batch=0, side='rx', **changes):
    sample=(batch+1)*10_000_000+10_000_000
    row=dict(path='2/A',batch=batch,side=side,count=120,data_count=100,probe_count=20,
             sample_t_ns=sample,arrival_t_ns=sample+1_000_000,guard_ns=10_000_000,
             data_gaps=0,probe_gaps=0,data_gap_age_ns=0,probe_gap_age_ns=0)
    row.update(changes)
    return row


class BusinessDeliveryTest(unittest.TestCase):
    def test_persistent_business_gap_with_healthy_probes(self):
        d=BusinessDeliveryDetector()
        self.assertIsNone(d.observe(report(data_gaps=1,data_gap_age_ns=19_000_000)))
        alarm=d.observe(report(4,data_gaps=1,data_gap_age_ns=40_000_000))
        self.assertEqual(alarm['signal'],'data_gap')
        self.assertEqual(alarm['decision_t_ns'],61_000_000)
        self.assertIsNone(d.observe(report(5,data_gaps=1,data_gap_age_ns=50_000_000)))

    def test_filled_gap_and_delayed_report_do_not_age_evidence(self):
        d=BusinessDeliveryDetector()
        self.assertIsNone(d.observe(report(data_gaps=1,data_gap_age_ns=10_000_000,
                                         arrival_t_ns=150_000_000)))
        self.assertIsNone(d.observe(report(1,arrival_t_ns=151_000_000)))

    def test_stale_gap_report_is_unknown(self):
        self.assertIsNone(BusinessDeliveryDetector().observe(report(
            4,data_gaps=1,data_gap_age_ns=40_000_000,arrival_t_ns=251_000_000)))

    def test_hidden_metadata_rejected(self):
        with self.assertRaises(ValueError): BusinessDeliveryDetector().observe(report(fault=True))

    def test_class_conservation_and_source_gap_rejected(self):
        for row in (report(data_count=101),report(side='tx',data_gaps=1,data_gap_age_ns=1),
                    report(data_gap_age_ns=1),report(data_gaps=True)):
            with self.assertRaises(ValueError): BusinessDeliveryDetector().observe(row)

    def test_business_stall_not_masked_by_probe_progress(self):
        d=BusinessDeliveryDetector();alarm=None
        for batch,(tx,rx) in enumerate(((100,100),(200,100),(300,100))):
            probe=1000*(batch+1)
            for side,data in (('tx',tx),('rx',rx)):
                result=d.observe(report(batch,side,count=data+probe,data_count=data,
                                        probe_count=probe))
                if result: alarm=result
        self.assertEqual(alarm['signal'],'data_service')
        self.assertEqual(alarm['missing_packets'],200)


if __name__=='__main__': unittest.main()


class NativeBusinessParityTest(unittest.TestCase):
    def test_native_gap_tracker_and_report_decisions(self):
        import json
        from pathlib import Path
        import shutil
        import subprocess
        import tempfile
        compiler=shutil.which('c++')
        if not compiler: self.skipTest('C++ compiler unavailable')
        header=Path(__file__).resolve().parents[1]/'simulation/business_observer.h'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'main.cc';binary=root/'observer'
            source.write_text(f'#include "{header}"\n#include <iostream>\n'
                'int main(int argc,char** argv){GapTracker g;g.receive(0,0);g.receive(2,10);'
                'if(g.holes.size()!=1||g.age(30)!=20)return 3;g.receive(1,31);if(g.age(32)||g.holes.size())return 4;'
                'BusinessObserver d;d.open(argv[1],argv[2]);BusinessObservation r;int rx;'
                'while(std::cin>>r.base.path>>r.base.batch>>rx>>r.base.count>>r.data>>r.probe'
                '>>r.base.sample>>r.base.arrival>>r.guard>>r.dataGaps>>r.probeGaps>>r.dataAge>>r.probeAge)'
                '{r.base.rx=rx;d.observe(r);}d.advance(600000000);}\n')
            subprocess.run([compiler,'-std=c++17',str(source),'-o',str(binary)],check=True,capture_output=True)
            rows=[]
            for path in ('0/A','2/A','3/B'):
                for batch in range(15):
                    for side,guard in (('tx',0),('tx',10_000_000),('rx',10_000_000),('rx',50_000_000)):
                        data=100*(batch+1) if guard==10_000_000 else 100
                        probe=1000*(batch+1) if guard==10_000_000 else 1000
                        if path=='3/B' and side=='rx' and guard==10_000_000 and batch>=3:
                            data=300 if batch<=5 else 100*(batch+1)-300
                        gaps=int(path=='2/A' and side=='rx' and batch>=4)
                        sample=(batch+1)*10_000_000+guard
                        for copy in range(3):
                            rows.append(report(batch,side,path=path,count=data+probe,data_count=data,
                                probe_count=probe,guard_ns=guard,sample_t_ns=sample,
                                arrival_t_ns=sample+1_000_000+copy*76_800,
                                data_gaps=gaps,data_gap_age_ns=40_000_000 if gaps else 0))
            rows.sort(key=lambda r:r['arrival_t_ns'])
            d=BusinessDeliveryDetector();alarms=[];baseline=[];lines=[]
            for r in rows:
                before=set(d.baseline.alarmed)
                a=d.observe(r)
                if a: alarms.append(a)
                path=int(r['path'].split('/')[0])*2+int(r['path'].endswith('B'))
                lines.append(' '.join(str(v) for v in (path,r['batch'],int(r['side']=='rx'),r['count'],
                    r['data_count'],r['probe_count'],r['sample_t_ns'],r['arrival_t_ns'],r['guard_ns'],
                    r['data_gaps'],r['probe_gaps'],r['data_gap_age_ns'],r['probe_gap_age_ns'])))
            subprocess.run([str(binary),str(root/'alarms'),str(root/'baseline')],
                           input='\n'.join(lines),text=True,check=True)
            native=[json.loads(s) for s in (root/'alarms').read_text().splitlines()]
            self.assertEqual(native,alarms)
            self.assertEqual({a['signal'] for a in alarms},{'data_gap','data_service'})


class BusinessCampaignAuditTest(unittest.TestCase):
    def test_actual_delay_must_match_registered_control_label(self):
        from simulation.run_business_observation import audit_configuration
        trial=dict(scenario='sparse_reorder40',faultTimeMs=50,runId=62000,
                   observationEndMs=600,lossRate=.005)
        paths=[]
        for n in range(8):
            paths.append(dict(path=f"{n//2}/{'AB'[n%2]}",network_loss=0,network_data_only=False,
                network_defer_ns=40_000_000 if n==4 else 0,
                network_defer_fraction=.005 if n==4 else 0,
                application_loss=0,application_defer_ns=0,application_defer_fraction=0))
        truth=dict(scenario=trial['scenario'],fault_time_ns=50_000_000,run_id=62000,
                   observation_end_ns=600_000_000,paths=paths)
        audit_configuration(trial,truth)
        paths[4]['network_defer_ns']=80_000_000
        with self.assertRaisesRegex(ValueError,'severity/class'): audit_configuration(trial,truth)

    def test_new_ids_do_not_reuse_failed_setup_or_validation(self):
        from simulation.run_business_observation import make_trials
        a={t['runId'] for t in make_trials('development')}
        b={t['runId'] for t in make_trials('validation')}
        self.assertEqual(min(a),62000)
        self.assertFalse(a&b)
        self.assertFalse(a&set(range(60000,60149)))
