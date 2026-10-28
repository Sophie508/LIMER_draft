"""Detector semantics and an independent C++/Python event replay comparison."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from limerlab.detector.service_detector import ServiceDetector, ServiceDetectorConfig


class ServiceDetectorTests(unittest.TestCase):
    def trained(self):
        d = ServiceDetector()
        for token in range(10):
            d.submit(13, token, token * 2_000_000, 65_536)
            d.complete(13, token, token * 2_000_000 + 100_000)
        d.advance(20_000_000)
        self.assertTrue(d.calibrated(13))
        self.assertEqual(d.baseline_ns(13), 100_000)
        self.assertEqual(d.deadline_ns(13), 300_000)
        return d

    def test_healthy_variable_latency_and_idle_do_not_alarm(self):
        d = self.trained()
        for token in range(10, 50):
            d.submit(13, token, token * 2_000_000, 65_536)
            d.complete(13, token, token * 2_000_000 + 250_000)
        d.advance(1_000_000_000)
        self.assertFalse(d.alarms)

    def test_sustained_fourfold_service_time_is_detected_without_truth(self):
        d = self.trained()
        for token in range(10, 13):
            d.submit(13, token, token * 2_000_000, 65_536)
            d.complete(13, token, token * 2_000_000 + 400_000)
        self.assertEqual(len(d.alarms), 1)
        self.assertEqual(d.alarms[0]["decision_t_ns"], 24_400_000)
        self.assertEqual(d.baseline_ns(13), 100_000)

    def test_blackhole_outstanding_samples_alarm_without_completion(self):
        d = self.trained()
        for token in range(10, 13):
            d.submit(13, token, token * 2_000_000, 65_536)
        d.advance(24_300_001)
        self.assertEqual(d.alarms[0]["evidence_tokens"], [10, 11, 12])
        self.assertEqual(d.pending_count(13), 3)

    def test_only_isolated_or_expired_outliers_do_not_alarm(self):
        d = self.trained()
        for token in range(10, 40):
            d.submit(13, token, token * 2_000_000, 65_536)
            d.complete(13, token, token * 2_000_000 + (500_000 if token % 25 == 10 else 100_000))
        self.assertFalse(d.alarms)

    def test_deadline_equality_is_on_time(self):
        d = self.trained()
        for token in range(10, 15):
            d.submit(13, token, token * 2_000_000, 65_536)
            d.complete(13, token, token * 2_000_000 + 300_000)
        self.assertFalse(d.alarms)

    def test_startup_blackhole_uses_fallback_after_explicit_calibration(self):
        d = ServiceDetector()
        for token in range(11):
            d.submit(13, token, token * 2_000_000, 65_536)
        self.assertEqual(d.alarms[0]["decision_t_ns"], 20_000_000)
        self.assertEqual(d.baseline_ns(13), 0)
        self.assertEqual(d.deadline_ns(13), 2_000_000)

    def test_same_instant_burst_needs_time_span_not_only_count(self):
        d = self.trained()
        for token in range(10, 13):
            d.submit(13, token, 20_000_000, 65_536)
        d.advance(21_000_000)
        self.assertFalse(d.alarms)

    def test_fast_repaired_canaries_alarm_from_sender_retransmissions(self):
        d = self.trained()
        for token in range(10, 13):
            start = token * 2_000_000
            d.submit(13, token, start, 65_536)
            d.retransmit(13, token, start + 50_000)
            d.complete(13, token, start + 100_000)
        self.assertEqual(d.alarms[0]["decision_t_ns"], 24_050_000)
        self.assertEqual(d.alarms[0]["rule_version"], "canary-service-v4")
        self.assertEqual(d.alarms[0]["evidence_tokens"], [10, 11, 12])

    def test_many_retransmissions_of_one_canary_count_only_once(self):
        d = self.trained()
        d.submit(13, 10, 20_000_000, 65_536)
        for time in (20_010_000, 20_020_000, 20_030_000, 24_000_000):
            d.retransmit(13, 10, time)
        self.assertEqual(len(d.paths[13]["bad"]), 1)
        self.assertFalse(d.alarms)

    def test_calibration_retransmissions_do_not_count_bad(self):
        d = ServiceDetector()
        for token in range(10):
            start = token * 2_000_000
            d.submit(13, token, start, 65_536)
            d.retransmit(13, token, start + 50_000)
            d.complete(13, token, start + 100_000)
        d.advance(20_000_000)
        self.assertFalse(d.alarms)
        self.assertFalse(d.paths[13]["bad"])
        self.assertEqual(d.baseline_ns(13), 100_000)

    def test_validation_rejects_conflicts_and_time_regression(self):
        d = self.trained()
        with self.assertRaises(ValueError): d.submit(13, 0, 20_000_000, 65_536)
        with self.assertRaises(ValueError): d.submit(13, 10, 20_000_000, 1000)
        with self.assertRaises(ValueError): d.complete(13, 999, 20_000_000)
        with self.assertRaises(ValueError): d.retransmit(13, 999, 20_000_000)
        with self.assertRaises(ValueError): d.advance(19_000_000)
        with self.assertRaises(ValueError): ServiceDetector(ServiceDetectorConfig(multiplier_den=0))
        with self.assertRaises(ValueError): ServiceDetector(ServiceDetectorConfig(business_stall_ns=0))
        with self.assertRaises(ValueError): ServiceDetector(ServiceDetectorConfig(spacing_multiplier_den=0))
        with self.assertRaises(ValueError): ServiceDetector(ServiceDetectorConfig(spacing_quantile_num=10))
        with self.assertRaises(ValueError): d.stall(99, 999, 20_000_000, 0, 1024)
        with self.assertRaises(ValueError): d.stall(13, 999, 20_000_000, 21_000_000, 1024)

    def test_business_stall_after_short_pulse_is_detected_despite_healthy_canaries(self):
        d = self.trained()
        for token in range(10, 30):
            start = token * 2_000_000
            d.submit(13, token, start, 65_536)
            d.complete(13, token, start + 100_000)
            d.stall(13, 999, start + 100_000, 20_000_000, 1024)
        self.assertFalse(d.alarms)
        d.stall(13, 999, 60_000_000, 20_000_000, 1024)
        self.assertEqual(d.alarms[0]["signal"], "business_ack_stall")
        self.assertEqual(d.alarms[0]["deadline_ns"], 40_000_000)
        self.assertEqual(d.alarms[0]["evidence_tokens"], [999])
        self.assertEqual(d.alarms[0]["evidence_submitted_ns"], [20_000_000])
        self.assertTrue(d.alarmed(13))

    def test_business_idle_and_recent_progress_do_not_alarm(self):
        d = self.trained()
        d.stall(13, 999, 60_000_000, 0, 0)
        d.stall(13, 999, 80_000_000, 40_000_001, 1024)
        self.assertFalse(d.alarms)
        self.assertFalse(d.alarmed(13))

    def test_business_stall_deadline_includes_exact_boundary_and_deduplicates(self):
        d = self.trained()
        d.stall(13, 999, 59_999_999, 20_000_000, 1024)
        self.assertFalse(d.alarms)
        d.stall(13, 999, 60_000_000, 20_000_000, 1024)
        d.stall(13, 998, 61_000_000, 20_000_000, 1024)
        self.assertEqual(len(d.alarms), 1)
        self.assertEqual(d.alarms[0]["decision_t_ns"], 60_000_000)

    def test_business_stall_does_not_bypass_calibration_or_duplicate_canary_alarm(self):
        d = ServiceDetector()
        d.submit(13, 1, 0, 65_536)
        d.complete(13, 1, 100_000)
        d.stall(13, 999, 15_000_000, 0, 1024)
        self.assertFalse(d.alarms)
        d = self.trained()
        for token in range(10, 13):
            start = token * 2_000_000
            d.submit(13, token, start, 65_536)
            d.retransmit(13, token, start + 50_000)
            d.complete(13, token, start + 100_000)
        d.stall(13, 999, 60_000_000, 20_000_000, 1024)
        self.assertEqual(len(d.alarms), 1)
        self.assertEqual(d.alarms[0]["signal"], "canary_service")

    def test_whole_path_spacing_shift_uses_two_past_windows(self):
        d = self.trained()
        d.spacing(13, 20_000_000, 889, 1000)
        self.assertEqual(d.spacing_baseline_ns(13), 889)
        d.spacing(13, 30_000_000, 3364, 330)
        self.assertFalse(d.alarms)
        d.spacing(13, 40_000_000, 3364, 330)
        self.assertEqual(d.alarms[0]["signal"], "delivery_spacing_shift")
        self.assertEqual(d.alarms[0]["decision_t_ns"], 40_000_000)
        self.assertEqual(d.alarms[0]["baseline_ns"], 889)
        self.assertEqual(d.alarms[0]["deadline_ns"], 1878)
        self.assertEqual(d.alarms[0]["evidence_tokens"], [30_000_000, 40_000_000])
        self.assertEqual(d.alarms[0]["evidence_submitted_ns"], [20_000_000, 30_000_000])

    def test_insufficient_spacing_window_interrupts_confirmation(self):
        d = self.trained()
        d.spacing(13, 20_000_000, 889, 64)
        d.spacing(13, 30_000_000, 3364, 330)
        d.spacing(13, 40_000_000, 0, 0)
        d.spacing(13, 50_000_000, 3364, 330)
        self.assertFalse(d.alarms)
        d.spacing(13, 60_000_000, 3364, 330)
        self.assertEqual(d.alarms[0]["evidence_tokens"], [50_000_000, 60_000_000])

    def test_spacing_threshold_equality_is_healthy_and_interrupts(self):
        d = self.trained()
        d.spacing(13, 20_000_000, 889, 64)
        for end, gap in [(30_000_000, 1879), (40_000_000, 1878), (50_000_000, 1879)]:
            d.spacing(13, end, gap, 64)
        self.assertFalse(d.alarms)
        d.spacing(13, 60_000_000, 1879, 64)
        self.assertEqual(d.alarms[0]["evidence_tokens"], [50_000_000, 60_000_000])

    def test_insufficient_spacing_calibration_does_not_train_on_later_fault(self):
        d = self.trained()
        d.spacing(13, 20_000_000, 889, 63)
        for end in (30_000_000, 40_000_000, 50_000_000):
            d.spacing(13, end, 3364, 330)
        self.assertEqual(d.spacing_baseline_ns(13), 0)
        self.assertFalse(d.alarms)

    def test_spacing_rejects_missing_duplicate_or_wrong_calibration_windows(self):
        d = self.trained()
        with self.assertRaises(ValueError): d.spacing(13, 30_000_000, 889, 64)
        with self.assertRaises(ValueError): d.spacing(99, 20_000_000, 889, 64)
        with self.assertRaises(ValueError): d.spacing(13, 20_000_000, 0, 64)
        d.spacing(13, 20_000_000, 889, 64)
        with self.assertRaises(ValueError): d.spacing(13, 20_000_000, 889, 64)
        with self.assertRaises(ValueError): d.spacing(13, 40_000_000, 3364, 64)

    def test_spacing_first_alarm_prevents_business_stall_duplicates(self):
        d = self.trained()
        d.spacing(13, 20_000_000, 889, 64)
        d.spacing(13, 30_000_000, 3364, 64)
        d.spacing(13, 40_000_000, 3364, 64)
        d.stall(13, 999, 60_000_000, 20_000_000, 1024)
        self.assertEqual(len(d.alarms), 1)

    @unittest.skipUnless(shutil.which("c++"), "C++ compiler unavailable")
    def test_cpp_and_python_have_identical_native_event_decisions(self):
        events = []
        for token in range(10):
            events.extend([("S", token, token * 2_000_000), ("C", token, token * 2_000_000 + 100_000)])
        for token in range(10, 30):
            events.append(("S", token, token * 2_000_000))
            if token < 13:
                events.extend([("R", token, token * 2_000_000 + 50_000),
                               ("C", token, token * 2_000_000 + 100_000)])
                continue
            if token % 3:
                events.append(("C", token, token * 2_000_000 + (500_000 if token % 2 else 100_000)))
        events.append(("A", 0, 70_000_000))
        business_events = events[:20] + [("B", 999, 59_999_999), ("B", 999, 60_000_000), ("B", 998, 61_000_000)]
        spacing_events = events[:20] + [("P", 889, 20_000_000), ("P", 3364, 30_000_000), ("P", 3364, 40_000_000)]
        cpp = r'''
#include "src/simulator/detection/service_detector.h"
#include <iostream>
int main() {
  limer::detection::ServiceDetector d;
  d.onAlarm=[](const limer::detection::ServiceAlarm& a) {
    std::cout << a.rule_version << " " << a.signal << " " << a.decision_t_ns << " " << a.baseline_ns << " " << a.deadline_ns;
    for(auto token:a.evidence_tokens) std::cout << " " << token;
    std::cout << "\n";
  };
  char kind; uint64_t token; int64_t time;
  while(std::cin >> kind >> token >> time) {
    if(kind=='S') d.submit(13,token,time,65536);
    else if(kind=='C') d.complete(13,token,time);
    else if(kind=='R') d.retransmit(13,token,time);
    else if(kind=='B') d.stall(13,token,time,20000000,1024);
    else if(kind=='P') d.spacing(13,time,token,64);
    else d.advance(time);
  }
}'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "replay.cc").write_text(cpp)
            subprocess.run([shutil.which("c++"), "-std=c++11", "-I", str(ROOT), str(root / "replay.cc"), "-o", str(root / "replay")], check=True, capture_output=True)
            for stream in (events, business_events, spacing_events):
                d = ServiceDetector()
                for kind, token, time in stream:
                    if kind == "S": d.submit(13, token, time, 65_536)
                    elif kind == "C": d.complete(13, token, time)
                    elif kind == "R": d.retransmit(13, token, time)
                    elif kind == "B": d.stall(13, token, time, 20_000_000, 1024)
                    elif kind == "P": d.spacing(13, time, token, 64)
                    else: d.advance(time)
                native = subprocess.run([str(root / "replay")], input="".join("%s %d %d\n" % e for e in stream), text=True, check=True, capture_output=True)
                expected = [" ".join(map(str, [a["rule_version"], a["signal"], a["decision_t_ns"], a["baseline_ns"], a["deadline_ns"]] + a["evidence_tokens"])) for a in d.alarms]
                self.assertEqual(native.stdout.splitlines(), expected)


if __name__ == "__main__":
    unittest.main()
