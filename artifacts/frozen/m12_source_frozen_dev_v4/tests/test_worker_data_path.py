import concurrent.futures
import socket
import unittest

from limer_v0.route_plan import RoutePlan
from limer_v0.worker import FabricConfig, FabricSockets, RingWorker


def connected_workers(world_size=4, chunk_bytes=4096):
    workers = [
        RingWorker(
            rank,
            world_size,
            [
                FabricConfig("A", "127.0.0.1", "127.0.0.1", 1),
                FabricConfig("B", "127.0.0.1", "127.0.0.1", 2),
            ],
            chunk_bytes,
            initial_routing_policy="balanced_active_active",
        )
        for rank in range(world_size)
    ]
    for fabric in ("A", "B"):
        incoming = [None] * world_size
        outgoing = [None] * world_size
        for sender_rank in range(world_size):
            sender, receiver = socket.socketpair()
            sender.settimeout(10.0)
            receiver.settimeout(10.0)
            outgoing[sender_rank] = sender
            incoming[(sender_rank + 1) % world_size] = receiver
        for rank, worker in enumerate(workers):
            worker.sockets[fabric] = FabricSockets(
                incoming=incoming[rank],
                outgoing=outgoing[rank],
            )
    return workers


def run_round(workers, round_id):
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(workers)
    ) as executor:
        futures = [
            executor.submit(worker.run_round, round_id) for worker in workers
        ]
        return [future.result(timeout=15.0) for future in futures]


class WorkerDataPathTest(unittest.TestCase):
    def test_four_workers_preserve_unaffected_schedules_after_localized_commit(self):
        workers = connected_workers()
        try:
            initial = RoutePlan.balanced_active_active(4)
            baseline_results = run_round(workers, 0)
            for rank, result in enumerate(baseline_results):
                self.assertEqual(result["version"], 0)
                self.assertEqual(
                    result["route_plan_fingerprint"], initial.fingerprint
                )
                self.assertEqual(result["send_routes"], list(initial.routes[rank]))
                self.assertEqual(result["send_steps_by_fabric"], {"A": 3, "B": 3})
                self.assertEqual(result["checksum_errors"], 0)
                self.assertEqual(result["version_errors"], 0)

            recovered = initial.localized_reroute(2, "A", "B")
            for worker in workers:
                worker.route_state.prepare(1, recovered, 2)
                worker.route_state.commit(1)

            pre_effective_results = run_round(workers, 1)
            recovered_results = run_round(workers, 2)
            self.assertTrue(
                all(result["version"] == 0 for result in pre_effective_results)
            )
            self.assertTrue(
                all(result["version"] == 1 for result in recovered_results)
            )

            for rank in (0, 1, 3):
                self.assertEqual(
                    recovered_results[rank]["send_routes"],
                    baseline_results[rank]["send_routes"],
                )
            self.assertEqual(
                recovered_results[2]["send_routes"],
                ["B", "B", "B", "B", "B", "B"],
            )
            self.assertEqual(
                recovered_results[3]["receive_routes"],
                recovered_results[2]["send_routes"],
            )
            for result in recovered_results:
                self.assertEqual(
                    result["route_plan_fingerprint"], recovered.fingerprint
                )
                self.assertEqual(result["bytes_sent"], 6 * 4096)
                self.assertEqual(result["bytes_received"], 6 * 4096)
                self.assertEqual(result["checksum_errors"], 0)
                self.assertEqual(result["version_errors"], 0)
        finally:
            for worker in workers:
                worker.close()


if __name__ == "__main__":
    unittest.main()
