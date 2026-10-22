import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from limer_v0.hybrid_delivery import HybridDeliveryDetector
from limer_v0.early_delivery import EarlyDeliveryDetector
from simulation.run_hybrid_observation import aggregate, audit, audit_observations, make_trials


class HybridEvaluationTest(unittest.TestCase):
    def test_95_percent_includes_the_miss_in_denominator(self):
        trials=[dict(id=str(i),condition="weak",kind="fault") for i in range(20)]
        results=[dict(id=str(i),status="PASS",timely=i<19,
                      delay_ms=80 if i<19 else None,false_alarm_events=0) for i in range(20)]
        result=aggregate(dict(trials=trials),results)
        self.assertEqual(result["per_condition_95_verdict"],"PASS")
        self.assertEqual(result["strict_verdict"],"FAIL")
        self.assertEqual(result["groups"]["weak"]["missed_or_unverified"],1)
        self.assertEqual(result["groups"]["weak"]["p95_ms"],80)
        results.pop()
        self.assertEqual(aggregate(dict(trials=trials),results)["per_condition_95_verdict"],"FAIL")

    def test_easy_conditions_cannot_hide_a_weak_condition(self):
        trials=[dict(id=str(i),condition="weak" if i==0 else "easy",kind="fault") for i in range(100)]
        results=[dict(id=str(i),status="PASS",timely=i!=0,delay_ms=80 if i else None,
                      false_alarm_events=0) for i in range(100)]
        self.assertEqual(aggregate(dict(trials=trials),results)["per_condition_95_verdict"],"FAIL")

    def test_control_alarm_fails_even_with_perfect_recall(self):
        trials=[dict(id="c",condition="control",kind="control")]
        results=[dict(id="c",status="PASS",false_alarm_events=1)]
        self.assertEqual(aggregate(dict(trials=trials),results)["per_condition_95_verdict"],"FAIL")

    def test_fresh_seed_ranges_and_prospective_slowdown_labels(self):
        campaigns=[make_trials(c) for c in ("development","validation","boundary")]
        runs=[{t["runId"] for t in c} for c in campaigns]
        self.assertTrue(all(not runs[i]&runs[j] for i in range(3) for j in range(i)))
        self.assertEqual(len(campaigns[1]),740)
        self.assertTrue(all(t["kind"]=="fault" for t in campaigns[1] if t["scenario"] in ("overload","reorder80")))

    def test_fifo_tampering_is_rejected_before_replay_claim(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);samples=[];offers=[];free=0
            for path in range(8):
                for batch in range(50):
                    for side,guard in (("tx",0),("tx",10_000_000),("rx",10_000_000),("rx",50_000_000)):
                        samples.append(dict(path=f"{path//2}/{'AB'[path%2]}",batch=batch,
                            side=side,count=0,guard_ns=guard,sample_t_ns=(batch+1)*10_000_000+(guard if side=="rx" or guard==10_000_000 else 0)))
            samples.sort(key=lambda r:(r["sample_t_ns"],r["path"],r["batch"]))
            for sample in samples:
                start=max(free,sample["sample_t_ns"]);free=start+51200
                offers.append(dict(path=sample["path"],batch=sample["batch"],side=sample["side"],
                    copy=0,guard_ns=sample["guard_ns"],sample_t_ns=sample["sample_t_ns"],start_ns=start,end_ns=free,lost=False))
            offers[17]["start_ns"]-=1
            for name,rows in (("samples",samples),("offers",offers),("reports",[])):
                (root/f"{name}.jsonl").write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaisesRegex(ValueError,"FIFO cost/order"):
                audit_observations(root,dict(reportRateMbps=10,reportDelayMs=1,reportCopies=1),{}, {})

    def test_probe_cost_uses_actual_mixed_wire_sizes(self):
        rows=[]
        for i in range(8):
            rows.append(dict(path=f"{i//2}/{'AB'[i%2]}",sent=3,received=3,permanent_drops=0,
                data_sent=1,data_received=1,probe_sent=2,probe_received=2,probe_wire_packets=2,
                duplicates=0,send_rejected=0,wire_packets=3,wire_bytes=1628,background_sent=0,
                min_wire_bytes=64,max_wire_bytes=1500))
        self.assertTrue(audit(dict(paths=rows)))
        rows[4]["wire_bytes"]-=128
        with self.assertRaisesRegex(ValueError,"wire byte cost"): audit(dict(paths=rows))


class EarlyDeliveryServiceTest(unittest.TestCase):
    def pair(self,d,batch,tx,rx):
        end=(batch+1)*10_000_000
        d.observe(dict(path="2/A",batch=batch,side="tx",count=tx,sample_t_ns=end+10_000_000,
                       arrival_t_ns=max(d.now_ns,end+10_000_000)))
        return d.observe(dict(path="2/A",batch=batch,side="rx",count=rx,sample_t_ns=end+10_000_000,
                              arrival_t_ns=end+11_000_000))

    def test_modest_queueing_is_not_severe_service_collapse(self):
        d=EarlyDeliveryDetector()
        for batch in range(20):
            self.assertIsNone(self.pair(d,batch,(batch+1)*100,(batch+1)*90))

    def test_two_consecutive_service_collapses_alarm_but_one_does_not(self):
        d=EarlyDeliveryDetector()
        self.assertIsNone(self.pair(d,0,100,100))
        self.assertIsNone(self.pair(d,1,200,150))
        alarm=self.pair(d,2,300,200)
        self.assertEqual(alarm["missing_packets"],100)
        self.assertEqual(alarm["evidence_batches"],[1,2])

    def test_unknown_gap_cannot_bridge_severe_windows(self):
        d=EarlyDeliveryDetector()
        self.pair(d,0,100,100);self.pair(d,1,200,150)
        self.assertIsNone(self.pair(d,3,400,250))
        self.assertIsNone(self.pair(d,4,500,300))
        self.assertIsNotNone(self.pair(d,5,600,350))

    def test_ordinary_fifo_source_pause_edges_do_not_alarm(self):
        for phase in range(500, 601):
            start = phase / 10
            def accepted(t):
                t = min(max(t, 0), 250)
                active = min(t, start) + max(0, t-start-60)
                return int(35*t + (1000/12)*active)
            d = EarlyDeliveryDetector()
            for batch in range(25):
                sample_ms = (batch+2)*10
                self.assertIsNone(self.pair(d, batch, accepted(sample_ms),
                                           accepted(sample_ms-1)), phase)

    def test_offset_source_sample_is_rejected(self):
        d = EarlyDeliveryDetector()
        with self.assertRaisesRegex(ValueError, "cannot precede"):
            d.observe(dict(path="2/A", batch=0, side="tx", count=100,
                sample_t_ns=10_000_000, arrival_t_ns=11_000_000))

    def test_simultaneous_receiver_credit_cannot_exceed_source(self):
        d = EarlyDeliveryDetector()
        with self.assertRaisesRegex(ValueError, "simultaneous RX"):
            self.pair(d, 0, 100, 101)


class NativeHybridParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which("c++")
        if not compiler: raise unittest.SkipTest("C++ compiler unavailable")
        cls.directory=tempfile.TemporaryDirectory()
        cls.root=Path(cls.directory.name)
        header=Path(__file__).resolve().parents[1]/"simulation/batch_deficit_observer.h"
        source=cls.root/"main.cc"
        source.write_text('#include <cstdint>\n#include <map>\n#include <fstream>\n#include <stdexcept>\n#include <iostream>\n'
            f'#include "{header}"\n'
            'int main(int argc,char** argv){ NativeDeficitObserver d,e(true);d.open(argv[1]);'
            'CounterObservation r;int rx;int64_t guard;while(std::cin>>r.path>>r.batch>>rx>>r.count>>r.sample>>r.arrival>>guard)'
            '{r.rx=rx;if(guard==10000000)e.observe(r);else d.observe(r);'
            'e.advance(r.arrival);d.advance(r.arrival);}d.advance(600000000);e.advance(600000000); }\n')
        cls.binary=cls.root/"observer"
        subprocess.run([compiler,"-std=c++17",str(source),"-o",str(cls.binary)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls): cls.directory.cleanup()

    def test_native_matches_unknown_gaps_reset_duplicates_and_expiry(self):
        reports=[]
        for path in range(2):
            for batch in range(30):
                for rx,guard in ((0,0),(0,10_000_000),(1,10_000_000),(1,50_000_000)):
                    # A completely absent RX batch must interrupt, never imply loss.
                    if batch==7 and rx: continue
                    count=250-(1 if rx and batch in (2,3,9,12,17,18,23) else 0)
                    if guard==10_000_000:
                        count=250*(batch+1)
                        if rx and path==1: count-=110*sum(b<=batch for b in (2,3))
                    sample=(batch+1)*10_000_000+(guard if rx or guard==10_000_000 else 0)
                    for copy in range(3):
                        arrival=sample+1_000_000+path*400_000+copy*51_200
                        reports.append(dict(path=f"{path//2}/{'AB'[path%2]}",batch=batch,
                            side="rx" if rx else "tx",count=count,sample_t_ns=sample,arrival_t_ns=arrival,guard_ns=guard))
        reports.sort(key=lambda r:r["arrival_t_ns"])
        detector=HybridDeliveryDetector();alarms=[]
        for report in reports:
            alarm=detector.observe(report)
            if alarm: alarms.append(alarm)
        detector.advance(600_000_000)
        lines=[]
        for row in reports:
            path=int(row["path"].split('/')[0])*2+(row["path"].endswith('B'))
            lines.append(f'{path} {row["batch"]} {int(row["side"]=="rx")} {row["count"]} {row["sample_t_ns"]} {row["arrival_t_ns"]} {row["guard_ns"]}')
        output=self.root/"alarms.jsonl"
        subprocess.run([str(self.binary),str(output)],input='\n'.join(lines),text=True,check=True)
        native=[json.loads(line) for line in output.read_text().splitlines()]
        self.assertEqual(native,alarms)
        self.assertEqual(len(alarms),2)
        self.assertEqual({a["rule_version"] for a in alarms},{"hybrid-early-v4","hybrid-delivery-v4"})
