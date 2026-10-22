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
                   observationEndMs=600,lossRate=.005,probeWireBytes=64,probePps=35000,probeTargetPps=0,capacityMbps=100,offeredMbps=80)
        paths=[]
        for n in range(8):
            paths.append(dict(path=f"{n//2}/{'AB'[n%2]}",network_loss=0,network_data_only=False,
                network_defer_ns=40_000_000 if n==4 else 0,
                network_defer_fraction=.005 if n==4 else 0,
                application_loss=0,application_defer_ns=0,application_defer_fraction=0))
        truth=dict(scenario=trial['scenario'],fault_time_ns=50_000_000,run_id=62000,
                   observation_end_ns=600_000_000,paths=paths,probe_wire_bytes=64,probe_pps=35000,probe_target_pps=0,capacity_mbps=100,offered_mbps=80)
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


class RepresentativeProbeBudgetTest(unittest.TestCase):
    def test_both_arms_charge_the_same_nominal_byte_budget(self):
        from simulation.run_business_observation import make_trials
        rows=make_trials('representative')
        self.assertEqual(len(rows),150)
        self.assertEqual(len({r['runId'] for r in rows}),150)
        self.assertEqual(min(r['runId'] for r in rows),66000)
        self.assertEqual({r['probeWireBytes'] for r in rows},{64,1500})
        for r in rows: self.assertAlmostEqual(r['probePps']*r['probeWireBytes']*8,17_920_000)
        self.assertEqual(sum(r['kind']=='fault' for r in rows),90)

    def test_actual_probe_lengths_enter_wire_conservation(self):
        from simulation.run_business_observation import audit
        row=dict(path='0/A',duplicates=0,send_rejected=0,sent=3,received=3,
                 data_sent=1,probe_sent=2,data_received=1,probe_received=2,
                 permanent_drops=0,application_drops=0,probe_wire_packets=2,
                 wire_packets=3,background_sent=0,wire_bytes=4500,min_wire_bytes=1500,max_wire_bytes=1500)
        truth=dict(probe_wire_bytes=1500,paths=[dict(row,path=f"{n//2}/{'AB'[n%2]}") for n in range(8)])
        self.assertTrue(audit(truth))
        truth['paths'][0]['wire_bytes']=1628
        with self.assertRaisesRegex(ValueError,'wire byte'):audit(truth)


class CoverageEnvelopeRegistrationTest(unittest.TestCase):
    def test_capacity_and_probe_budget_are_explicit_and_held_out(self):
        from simulation.run_business_observation import make_trials
        a=make_trials('coverage_development');b=make_trials('coverage_validation')
        self.assertEqual(len(a),100);self.assertEqual(len(b),460)
        self.assertFalse({r['runId'] for r in a}&{r['runId'] for r in b})
        self.assertEqual(min(r['runId'] for r in b),68000)
        for r in a+b:
            self.assertEqual(r['capacityMbps'],10000)
            self.assertEqual(r['probePps']*r['probeWireBytes']*8,420_000_000)
        self.assertEqual(sum(r['kind']=='fault' for r in b),400)
        self.assertEqual(sum(r['kind']=='control' for r in b),60)


class AdaptiveProbeBudgetTest(unittest.TestCase):
    def test_source_budget_uses_previous_window_and_integer_wire_cost(self):
        from pathlib import Path
        import shutil, subprocess, tempfile
        compiler=shutil.which('c++')
        if not compiler:self.skipTest('C++ compiler unavailable')
        header=Path(__file__).resolve().parents[1]/'simulation/probe_budget.h'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'budget.cc';binary=root/'budget'
            source.write_text(f'#include "{header}"\nint main(){{'
                'if(ProbeBudget(0,9000000,25000)!=225)return 1;'
                'if(ProbeBudget(67,10000000,25000)!=183)return 2;'
                'if(ProbeBudget(833,10000000,25000)!=0)return 3;'
                'if(ProbeBudget(0,10000000,25000)!=250)return 4;'
                'try{ProbeBudget(0,0,25000);return 5;}catch(const std::exception&){}'
                'try{ProbeBudget(0,10000001,25000);return 6;}catch(const std::exception&){}'
                'return 0;}')
            subprocess.run([compiler,'-std=c++17',str(source),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True)

    def test_adaptive_ids_scope_and_fixed_observation_rule(self):
        from simulation.run_business_observation import make_trials
        a=make_trials('adaptive_development');b=make_trials('adaptive_validation');c=make_trials('adaptive_smoke')
        self.assertEqual((len(a),len(b),len(c)),(160,460,4))
        self.assertEqual((min(t['runId'] for t in a),min(t['runId'] for t in b)),(70000,71000))
        self.assertFalse({t['runId'] for t in a}&{t['runId'] for t in b})
        for t in a+b+c:
            self.assertEqual((t['probePps'],t['probeTargetPps'],t['probeWireBytes'],t['capacityMbps']),
                             (0,25000,1500,10000))
        self.assertEqual(sum(t['kind']=='fault' for t in b),400)

    def test_wave_audit_rejects_future_data_leak_and_wrong_emission(self):
        from simulation.run_business_observation import audit_probe_waves
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);events=[];waves=[]
            for p in range(8):
                seq=0
                for b in range(25):
                    start=max(1000000,b*10000000);end=(b+1)*10000000
                    previous=0 if b==0 else 1
                    n=25000*(end-start)//1000000000-previous*(end-start)//10000000
                    waves.append(f'{p},{b},{previous},{n},{start},{end}')
                    events.append(f'tx,{p},{b},0,{b},{start}')
                    for i in range(n):
                        events.append(f'tx,{p},{b},1,{seq},{start+(end-start)*i//n}');seq+=1
            (root/'packet_events.csv').write_text('\n'.join(events)+'\n')
            (root/'probe_waves.csv').write_text('\n'.join(waves)+'\n')
            audit_probe_waves(root,dict(probeTargetPps=25000))
            broken=waves.copy();broken[0]=broken[0].replace(',0,225,',',1,224,')
            (root/'probe_waves.csv').write_text('\n'.join(broken)+'\n')
            with self.assertRaisesRegex(ValueError,'previous closed'):audit_probe_waves(root,dict(probeTargetPps=25000))
            (root/'probe_waves.csv').write_text('\n'.join(waves)+'\n')
            (root/'packet_events.csv').write_text('\n'.join(events[0:1]+events[2:])+'\n')
            with self.assertRaisesRegex(ValueError,'actual probe wave'):audit_probe_waves(root,dict(probeTargetPps=25000))


class AdaptiveHighControlRegistrationTest(unittest.TestCase):
    def test_high_pause_and_delay_controls_keep_their_denominator(self):
        from simulation.run_business_observation import make_trials
        rows=make_trials('adaptive_high_controls')
        self.assertEqual(len(rows),60)
        self.assertEqual(min(t['runId'] for t in rows),72000)
        self.assertTrue(all(t['kind']=='control' and t['offeredMbps']==1000 for t in rows))
        self.assertEqual({t['scenario'] for t in rows},{'nominal','pause','congestion','reorder40','sparse_reorder40','processing40'})
        self.assertFalse({t['runId'] for t in rows}&{t['runId'] for t in make_trials('adaptive_validation')})
