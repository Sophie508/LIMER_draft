"""Data-path tests for step-granular cutover, abort/redo, and dedup.

These use in-process socketpairs, so they run on any platform: the test
harness plays the ring peer of a rank-0 worker in a two-worker world and
drives prepare/commit through the worker's thread-safe control handlers
while a round is in flight.
"""

import io
import json
import socket
import threading
import unittest

from limer_v0.protocol import FrameHeader, crc32, recv_frame, send_frame
from limer_v0.route_plan import RoutePlan
from limer_v0.worker import FabricConfig, FabricSockets, RingWorker


CHUNK = 4096


def frame(round_id, step_id, version, rank=1, size=CHUNK):
    payload = bytes([rank & 0xFF]) * size
    header = FrameHeader(
        round_id=round_id,
        step_id=step_id,
        version=version,
        payload_len=size,
        checksum=crc32(payload),
    )
    return header, payload


class HarnessedWorker:
    """A rank-0 worker of a two-rank ring wired to the test via socketpairs."""

    def __init__(self, step_timeout_s=5.0):
        self.output = io.StringIO()
        self.worker = RingWorker(
            rank=0,
            world_size=2,
            fabrics=[
                FabricConfig("A", "127.0.0.1", "127.0.0.1", 1),
                FabricConfig("B", "127.0.0.1", "127.0.0.1", 2),
            ],
            chunk_bytes=CHUNK,
            initial_routing_policy="balanced_active_active",
            step_telemetry=True,
            step_timeout_s=step_timeout_s,
            output=self.output,
        )
        self.peer = {}
        for name in ("A", "B"):
            in_worker, in_peer = socket.socketpair()
            out_worker, out_peer = socket.socketpair()
            self.worker.sockets[name] = FabricSockets(in_worker, out_worker)
            # The peer writes into the worker's incoming socket and reads
            # what the worker sent on its outgoing socket.
            self.peer[name] = {"send": in_peer, "recv": out_peer}

    def events(self):
        return [json.loads(line) for line in self.output.getvalue().splitlines()]

    def event_names(self):
        return [event["event"] for event in self.events()]

    def close(self):
        self.worker.close()
        for name in self.peer:
            for sock in self.peer[name].values():
                try:
                    sock.close()
                except OSError:
                    pass


class StepCutoverTest(unittest.TestCase):
    def run_round_async(self, harness, round_id=0):
        result = {}
        errors = []

        def target():
            try:
                result["round"] = harness.worker.run_round(round_id)
            except BaseException as exc:  # surfaced in the test thread
                errors.append(exc)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        return thread, result, errors

    def test_mid_round_commit_applies_at_step_boundary(self):
        harness = HarnessedWorker()
        try:
            thread, result, errors = self.run_round_async(harness)
            # Step 0 under v0: rank 0 sends on A, receives rank 1's B frame.
            header, payload = recv_frame(harness.peer["A"]["recv"])
            self.assertEqual((header.round_id, header.step_id, header.version), (0, 0, 0))
            send_frame(harness.peer["B"]["send"], *frame(0, 0, 0))
            # Prepare+commit a plan moving rank 0's step-1 send from B to A,
            # effective at (round 0, step 1) — mid-round, no abort needed.
            base = RoutePlan.balanced_active_active(2)
            target_plan = base.localized_reroute(0, "B", "A")
            harness.worker._handle_prepare({
                "command": "prepare",
                "version": 1,
                "plan": target_plan.to_dict(),
                "plan_fingerprint": target_plan.fingerprint,
                "effective_round": 0,
                "effective_step": 1,
            })
            harness.worker._handle_commit({"command": "commit", "version": 1})
            # Step 1 must now be sent on A with version 1.
            header, payload = recv_frame(harness.peer["A"]["recv"])
            self.assertEqual((header.round_id, header.step_id, header.version), (0, 1, 1))
            # Rank 1's step-1 send stays on A; it must also carry version 1.
            send_frame(harness.peer["A"]["send"], *frame(0, 1, 1))
            thread.join(timeout=5.0)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(result["round"]["send_routes"], ["A", "A"])
            self.assertEqual(result["round"]["version"], 1)
            self.assertEqual(result["round"]["redo_count"], 0)
            self.assertEqual(result["round"]["checksum_errors"], 0)
            self.assertEqual(result["round"]["version_errors"], 0)
        finally:
            harness.close()

    def test_blocked_receive_is_aborted_and_redone_on_new_route(self):
        harness = HarnessedWorker()
        try:
            thread, result, errors = self.run_round_async(harness)
            # Consume rank 0's step-0 send so its send half completes.
            header, _payload = recv_frame(harness.peer["A"]["recv"])
            self.assertEqual(header.step_id, 0)
            # Never send rank 1's B frame: the worker is now blocked receiving
            # on B, emulating a dead path. Cut over: rank 1's sends move to A,
            # effective immediately, closing the dead incoming socket.
            base = RoutePlan.balanced_active_active(2)
            target_plan = base.localized_reroute(1, "B", "A")
            harness.worker._handle_prepare({
                "command": "prepare",
                "version": 1,
                "plan": target_plan.to_dict(),
                "plan_fingerprint": target_plan.fingerprint,
                "effective_round": 0,
                "effective_step": 0,
            })
            harness.worker._handle_commit({
                "command": "commit",
                "version": 1,
                "close_incoming": ["B"],
            })
            # The redone step 0 receive now expects rank 1's frame on A, v1.
            send_frame(harness.peer["A"]["send"], *frame(0, 0, 1))
            # Step 1: rank 0 sends on B (own schedule unchanged), version 1.
            header, _payload = recv_frame(harness.peer["B"]["recv"])
            self.assertEqual((header.step_id, header.version), (1, 1))
            send_frame(harness.peer["A"]["send"], *frame(0, 1, 1))
            thread.join(timeout=5.0)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(result["round"]["redo_count"], 1)
            self.assertEqual(result["round"]["receive_routes"], ["A", "A"])
            self.assertIn("STEP_REDO", harness.event_names())
            # The already-delivered send half must not run again: exactly one
            # step-0 frame ever appears on the A outgoing channel, and the
            # round reports each step sent exactly once.
            self.assertEqual(result["round"]["frame_count"], 2)
        finally:
            harness.close()

    def test_commit_resend_list_retransmits_on_new_plan(self):
        harness = HarnessedWorker()
        try:
            thread, result, errors = self.run_round_async(harness)
            # Step 0 send consumed by the peer, but (per the coordinator's
            # telemetry) the frame never reached the receiver: the harness
            # pretends it vanished with the dead fabric.
            header, _payload = recv_frame(harness.peer["A"]["recv"])
            self.assertEqual(header.step_id, 0)
            # Cut over: rank 0's A sends move to B (its step-0 slot), rank 1's
            # sends stay; close nothing (the worker is blocked on B receive —
            # rank 1's step-0 route B — which stays valid), and order a resend
            # of (0, 0) under the new plan.
            base = RoutePlan.balanced_active_active(2)
            target_plan = base.localized_reroute(0, "A", "B")
            harness.worker._handle_prepare({
                "command": "prepare",
                "version": 1,
                "plan": target_plan.to_dict(),
                "plan_fingerprint": target_plan.fingerprint,
                "effective_round": 0,
                "effective_step": 0,
            })
            harness.worker._handle_commit({
                "command": "commit",
                "version": 1,
                "resend_steps": [{"round_id": 0, "step_id": 0}],
            })
            # Unblock the in-flight receive with rank 1's step-0 frame. The
            # attempt started under v0 and the frame matches v0, so the step
            # completes normally — the benign race where the "lost" frame
            # arrives after all. The ordered resend still goes out and must be
            # absorbed by the peer's duplicate handling.
            send_frame(harness.peer["B"]["send"], *frame(0, 0, 0))
            # At the next step boundary the pending resend goes out on the new
            # route (B) with version 1.
            header, _payload = recv_frame(harness.peer["B"]["recv"])
            self.assertEqual(
                (header.round_id, header.step_id, header.version), (0, 0, 1)
            )
            # Step 1: routes unchanged for both (rank0 B, rank1 A), version 1.
            header, _payload = recv_frame(harness.peer["B"]["recv"])
            self.assertEqual((header.step_id, header.version), (1, 1))
            send_frame(harness.peer["A"]["send"], *frame(0, 1, 1))
            thread.join(timeout=5.0)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertIn("STEP_RESENT", harness.event_names())
            # The in-flight completion means no redo was needed; correctness
            # holds because the duplicate resend is discarded by the receiver.
            self.assertEqual(result["round"]["redo_count"], 0)
            self.assertEqual(result["round"]["version_errors"], 0)
        finally:
            harness.close()

    def test_stale_duplicate_frame_is_discarded(self):
        harness = HarnessedWorker()
        try:
            thread, result, errors = self.run_round_async(harness)
            header, _payload = recv_frame(harness.peer["A"]["recv"])
            send_frame(harness.peer["B"]["send"], *frame(0, 0, 0))
            # Step 1 receive route is A (rank 1's step-1 send). Deliver a
            # stale duplicate of step 0 first; the worker must discard it and
            # accept the real step-1 frame.
            send_frame(harness.peer["A"]["send"], *frame(0, 0, 0))
            send_frame(harness.peer["A"]["send"], *frame(0, 1, 0))
            recv_frame(harness.peer["B"]["recv"])  # rank 0's step-1 send on B
            thread.join(timeout=5.0)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertIn("DUPLICATE_FRAME_DISCARDED", harness.event_names())
            self.assertEqual(result["round"]["checksum_errors"], 0)
            self.assertEqual(result["round"]["version_errors"], 0)
        finally:
            harness.close()

    def test_step_timeout_is_configurable(self):
        harness = HarnessedWorker(step_timeout_s=0.3)
        try:
            thread, result, errors = self.run_round_async(harness)
            recv_frame(harness.peer["A"]["recv"])
            # Never feed the step-0 receive: the configured timeout must fire.
            thread.join(timeout=5.0)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], TimeoutError)
        finally:
            harness.close()


if __name__ == "__main__":
    unittest.main()
