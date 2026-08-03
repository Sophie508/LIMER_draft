import tempfile
import time
import unittest
from pathlib import Path

from limer_v0.orchestrator import EventLog, StepGateMonitor, _baseline_step_p95_s
from limer_v0.refiner import StepGateRefiner


class FakeSentinel:
    def __init__(self):
        self.active = False

    def rate_degraded_burst_active(self):
        return self.active


class StepGateMonitorTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.event_log = EventLog(Path(self._tmp.name) / "events.jsonl")
        self.sentinel = FakeSentinel()
        self.probe_calls = []

    def tearDown(self):
        self.event_log.close()
        self._tmp.cleanup()

    def monitor(self, probe_healthy=True):
        def probe():
            self.probe_calls.append(time.monotonic_ns())
            return {"healthy": probe_healthy}

        return StepGateMonitor(
            self.event_log,
            self.sentinel,
            StepGateRefiner(),
            baseline_step_p95_s=0.178,
            probe=probe,
            poll_interval_s=0.005,
        )

    def emit_step(self, rank, round_id, step_id, duration_s):
        self.event_log.emit(
            "STEP_DONE",
            rank=rank,
            round_id=round_id,
            step_id=step_id,
            version=0,
            send_route="A",
            duration_ns=int(duration_s * 1e9),
        )

    def wait_for_decision(self, monitor, timeout_s=2.0):
        deadline = time.monotonic() + timeout_s
        while monitor.decision is None and time.monotonic() < deadline:
            time.sleep(0.005)
        return monitor.decision

    def test_confirms_after_two_slow_steps_while_symptom_active(self):
        monitor = self.monitor()
        monitor.start()
        try:
            self.event_log.emit("SWITCH_SUSPECT", interface="sA-eth3")
            self.sentinel.active = True
            self.emit_step(3, 3, 0, 0.882)
            self.emit_step(0, 3, 1, 0.870)
            decision = self.wait_for_decision(monitor)
        finally:
            monitor.stop()
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "confirm")
        self.assertEqual(len(self.probe_calls), 1)
        confirm_events = [
            record
            for record in self.event_log.records
            if record.get("event") == "HOST_CONFIRM"
        ]
        self.assertEqual(len(confirm_events), 1)
        self.assertEqual(confirm_events[0]["gate_mode"], "step")

    def test_slow_steps_without_active_symptom_never_confirm(self):
        monitor = self.monitor()
        monitor.start()
        try:
            self.event_log.emit("SWITCH_SUSPECT", interface="sA-eth3")
            self.sentinel.active = False
            for step_id, duration_s in ((0, 0.587), (2, 0.603), (4, 0.550)):
                self.emit_step(3, 3, step_id, duration_s)
            time.sleep(0.05)
            decision = monitor.decision
        finally:
            monitor.stop()
        self.assertIsNone(decision)
        self.assertEqual(len(monitor.slow_steps), 3)
        self.assertEqual(len(monitor.confirmable_slow_steps), 0)
        self.assertEqual(self.probe_calls, [])

    def test_fast_steps_are_ignored(self):
        monitor = self.monitor()
        monitor.start()
        try:
            self.event_log.emit("SWITCH_SUSPECT", interface="sA-eth3")
            self.sentinel.active = True
            for step_id in range(6):
                self.emit_step(2, 3, step_id, 0.178)
            time.sleep(0.05)
            decision = monitor.decision
        finally:
            monitor.stop()
        self.assertIsNone(decision)
        self.assertEqual(monitor.slow_steps, [])

    def test_unhealthy_probe_defers(self):
        monitor = self.monitor(probe_healthy=False)
        monitor.start()
        try:
            self.event_log.emit("SWITCH_SUSPECT", interface="sA-eth3")
            self.sentinel.active = True
            self.emit_step(3, 3, 0, 0.882)
            self.emit_step(0, 3, 1, 0.870)
            decision = self.wait_for_decision(monitor)
        finally:
            monitor.stop()
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "defer")
        defer_events = [
            record
            for record in self.event_log.records
            if record.get("event") == "HOST_DEFER"
        ]
        self.assertEqual(len(defer_events), 1)

    def test_duplicate_step_events_count_once(self):
        monitor = self.monitor()
        monitor.start()
        try:
            self.event_log.emit("SWITCH_SUSPECT", interface="sA-eth3")
            self.sentinel.active = True
            self.emit_step(3, 3, 0, 0.882)
            self.emit_step(3, 3, 0, 0.882)
            time.sleep(0.05)
            decision = monitor.decision
        finally:
            monitor.stop()
        self.assertIsNone(decision)
        self.assertEqual(len(monitor.confirmable_slow_steps), 1)


class BaselineStepP95Test(unittest.TestCase):
    def test_flattens_baseline_step_durations(self):
        rows = [
            {
                "period": "baseline",
                "step_durations_ns": [178_000_000] * 6,
            },
            {
                "period": "baseline",
                "step_durations_ns": [177_000_000] * 5 + [200_000_000],
            },
            {
                "period": "warmup",
                "step_durations_ns": [999_000_000] * 6,
            },
        ]
        value = _baseline_step_p95_s(rows)
        self.assertGreater(value, 0.177)
        self.assertLess(value, 0.2)

    def test_requires_baseline_rows(self):
        with self.assertRaises(ValueError):
            _baseline_step_p95_s([{"period": "warmup", "step_durations_ns": [1]}])


if __name__ == "__main__":
    unittest.main()
