import unittest
from pathlib import Path
import tempfile

from simulation.run_batch_observation import aggregate, audit, score, replay


class BatchObservationReportTest(unittest.TestCase):
    def test_unrun_and_failed_controls_are_not_verified_no_alarm_evidence(self):
        trial=dict(id="c1",condition="nominal",kind="control")
        for rows in ([],[dict(id="c1",status="FAILED")]):
            result=aggregate(dict(trials=[trial]),rows)
            self.assertEqual(result["strict_verdict"],"FAIL")
            self.assertEqual(result["verified_control_trials"],0)

    def test_misses_stay_in_p95_and_timely_denominator(self):
        trials=[dict(id=str(i),condition="loss",kind="fault") for i in range(20)]
        rows=[dict(id=str(i),status="PASS",timely=i<18,
                   delay_ms=60 if i<18 else None,missed=i>=18) for i in range(20)]
        result=aggregate(dict(trials=trials),rows)
        self.assertEqual(result["groups"]["loss"]["p95_ms"],"infinite")
        self.assertEqual(result["groups"]["loss"]["registered"],20)
        self.assertEqual(result["groups"]["loss"]["missed_or_unverified"],2)

    def test_false_alarms_include_pre_event_and_all_unaffected_paths(self):
        truth=dict(fault_time_ns=50_000_000,fault_path="2/A")
        observer=dict(alarms=[dict(path="2/A",decision_t_ns=49_000_000),
                              dict(path="1/B",decision_t_ns=80_000_000),
                              dict(path="2/A",decision_t_ns=120_000_000)])
        result=score(dict(kind="fault"),truth,observer)
        self.assertEqual(result["false_alarm_events"],2)
        self.assertEqual(result["delay_ms"],70)

    def test_missing_telemetry_blocks_a_complete_gate_even_without_alarms(self):
        trial=dict(id="c1",condition="nominal",kind="control")
        result=aggregate(dict(trials=[trial]),[dict(id="c1",status="PASS",unavailable_batches=1)])
        self.assertEqual(result["strict_verdict"],"FAIL")

    def test_final_packet_conservation_cannot_hide_unaccounted_loss(self):
        paths=[dict(path=f"{i}/A",sent=100,received=100,permanent_drops=0,
                    duplicates=0,send_rejected=0,min_wire_bytes=1500,max_wire_bytes=1500,
                    wire_packets=100,wire_bytes=150000,background_sent=0) for i in range(8)]
        self.assertTrue(audit(dict(paths=paths)))
        paths[4]["received"]=99
        with self.assertRaises(ValueError):audit(dict(paths=paths))

    def test_batches_with_both_reports_missing_are_counted_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"reports.jsonl"
            p.write_text("")
            result=replay(p,600_000_000)
        self.assertEqual(result["alarms"],[])
        self.assertEqual(result["unavailable_batches"],400)
