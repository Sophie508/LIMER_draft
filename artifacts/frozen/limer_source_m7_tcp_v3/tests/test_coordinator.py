import unittest

from limer_v0.coordinator import RecoveryCoordinator
from limer_v0.orchestrator import _execute_handover
from limer_v0.route_plan import RoutePlan


class FakeEventLog:
    def __init__(self):
        self.records = []

    def emit(self, event, **payload):
        record = {"event": event, **payload}
        self.records.append(record)
        return record


class FakeHandle:
    def __init__(
        self,
        rank,
        fail_ready=False,
        fail_commit=False,
        wrong_fingerprint=False,
    ):
        self.rank = rank
        self.fail_ready = fail_ready
        self.fail_commit = fail_commit
        self.wrong_fingerprint = wrong_fingerprint
        self.commands = []

    def send(self, command):
        self.commands.append(dict(command))

    def wait_for_control(self, expected, timeout_s=0):
        return self.wait_for(expected, timeout_s)

    def wait_for(self, expected, timeout_s=0):
        event = expected[0]
        if event == "READY":
            if self.fail_ready:
                raise TimeoutError("synthetic READY timeout")
            prepare = next(
                command for command in self.commands if command["command"] == "prepare"
            )
            return {
                "event": "READY",
                "rank": self.rank,
                "version": prepare["version"],
                "plan_fingerprint": (
                    "0" * 64
                    if self.wrong_fingerprint
                    else prepare["plan_fingerprint"]
                ),
                "effective_round": prepare["effective_round"],
            }
        if event == "COMMITTED":
            if self.fail_commit:
                raise TimeoutError("synthetic COMMITTED timeout")
            commit = next(
                command
                for command in reversed(self.commands)
                if command["command"] == "commit"
            )
            return {
                "event": "COMMITTED",
                "rank": self.rank,
                "version": commit["version"],
            }
        if event == "ABORTED":
            abort = next(
                command
                for command in reversed(self.commands)
                if command["command"] == "abort"
            )
            return {
                "event": "ABORTED",
                "rank": self.rank,
                "version": abort["version"],
            }
        raise AssertionError(f"unexpected event wait: {event}")


class RecoveryCoordinatorTest(unittest.TestCase):
    def setUp(self):
        self.baseline = RoutePlan.balanced_active_active(4)
        self.recovered = self.baseline.localized_reroute(2, "A", "B")

    def test_commits_only_after_all_ranks_ready_for_same_plan(self):
        coordinator = RecoveryCoordinator(self.baseline)
        proposal = coordinator.propose(
            self.recovered, effective_round=4, current_round=3
        )
        self.assertEqual(proposal.version, 1)
        self.assertEqual(proposal.plan_fingerprint, self.recovered.fingerprint)
        for rank in range(4):
            coordinator.record_ready(
                rank,
                version=1,
                plan_fingerprint=proposal.plan_fingerprint,
            )
        decision = coordinator.commit_or_abort()

        self.assertEqual(decision.action, "commit")
        self.assertEqual(decision.version, 1)
        self.assertEqual(decision.ready_ranks, [0, 1, 2, 3])
        self.assertEqual(decision.plan_fingerprint, self.recovered.fingerprint)
        self.assertEqual(len(decision.changed_slots), 3)
        self.assertEqual(coordinator.active_version, 1)
        self.assertEqual(coordinator.active_plan, self.recovered)

    def test_missing_rank_aborts_without_advancing_version(self):
        coordinator = RecoveryCoordinator(self.baseline)
        proposal = coordinator.propose(
            self.recovered, effective_round=4, current_round=3
        )
        for rank in (0, 1, 2):
            coordinator.record_ready(rank, 1, proposal.plan_fingerprint)
        decision = coordinator.commit_or_abort()

        self.assertEqual(decision.action, "abort")
        self.assertEqual(decision.missing_ranks, [3])
        self.assertEqual(coordinator.active_version, 0)
        self.assertEqual(coordinator.active_plan, self.baseline)

    def test_rejects_duplicate_stale_or_wrong_fingerprint_ready(self):
        coordinator = RecoveryCoordinator(self.baseline)
        proposal = coordinator.propose(
            self.recovered, effective_round=4, current_round=3
        )
        coordinator.record_ready(0, 1, proposal.plan_fingerprint)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            coordinator.record_ready(0, 1, proposal.plan_fingerprint)
        with self.assertRaisesRegex(ValueError, "version"):
            coordinator.record_ready(1, 0, proposal.plan_fingerprint)
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            coordinator.record_ready(1, 1, "0" * 64)

    def test_rejects_non_future_effective_round_and_noop_plan(self):
        coordinator = RecoveryCoordinator(self.baseline)
        with self.assertRaisesRegex(ValueError, "future"):
            coordinator.propose(self.recovered, effective_round=3, current_round=3)
        with self.assertRaisesRegex(ValueError, "differ"):
            coordinator.propose(self.baseline, effective_round=4, current_round=3)

    def test_handover_records_zero_inflight_round_boundary_contract(self):
        handles = [FakeHandle(rank) for rank in range(4)]
        event_log = FakeEventLog()
        decision = _execute_handover(
            handles,
            event_log,
            current_plan=self.baseline,
            target_plan=self.recovered,
            current_round=3,
            effective_round=4,
        )

        self.assertEqual(decision.action, "commit")
        proposal = next(
            record
            for record in event_log.records
            if record["event"] == "RECOVERY_PROPOSE"
        )
        self.assertEqual(
            proposal["cutover_contract"]["in_flight_application_frames_at_prepare"],
            0,
        )
        self.assertEqual(proposal["cutover_contract"]["last_completed_round"], 3)
        self.assertEqual(proposal["plan_fingerprint"], self.recovered.fingerprint)
        self.assertEqual(len(proposal["changed_slots"]), 3)

    def test_prepare_timeout_aborts_every_prepared_worker(self):
        handles = [FakeHandle(rank, fail_ready=(rank == 3)) for rank in range(4)]
        event_log = FakeEventLog()
        decision = _execute_handover(
            handles,
            event_log,
            current_plan=self.baseline,
            target_plan=self.recovered,
            current_round=3,
            effective_round=4,
            prepare_timeout_s=0.01,
        )

        self.assertEqual(decision.action, "abort")
        self.assertTrue(
            all(
                any(command["command"] == "abort" for command in handle.commands)
                for handle in handles
            )
        )
        abort = next(
            record
            for record in event_log.records
            if record["event"] == "RECOVERY_ABORT"
        )
        self.assertIn("forward progress", abort["liveness_boundary"])

    def test_wrong_ready_fingerprint_aborts(self):
        handles = [
            FakeHandle(rank, wrong_fingerprint=(rank == 2)) for rank in range(4)
        ]
        decision = _execute_handover(
            handles,
            FakeEventLog(),
            current_plan=self.baseline,
            target_plan=self.recovered,
            current_round=3,
            effective_round=4,
        )
        self.assertEqual(decision.action, "abort")
        self.assertEqual(decision.missing_ranks, [2, 3])

    def test_commit_ack_failure_rolls_back_before_effective_round(self):
        handles = [FakeHandle(rank, fail_commit=(rank == 2)) for rank in range(4)]
        event_log = FakeEventLog()
        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            _execute_handover(
                handles,
                event_log,
                current_plan=self.baseline,
                target_plan=self.recovered,
                current_round=3,
                effective_round=4,
                prepare_timeout_s=0.01,
            )
        self.assertTrue(
            all(
                any(command["command"] == "abort" for command in handle.commands)
                for handle in handles
            )
        )
        self.assertTrue(
            any(record["event"] == "RECOVERY_ROLLBACK" for record in event_log.records)
        )


if __name__ == "__main__":
    unittest.main()
