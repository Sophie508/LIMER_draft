import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def unused_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def loopback_alias_available():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.11", 0))
        return True
    except OSError:
        return False
    finally:
        sock.close()


class WorkerProcess:
    def __init__(self, rank, local_ip, next_ip, port_a, port_b):
        command = [
            sys.executable,
            "-m",
            "limer_v0.worker",
            "--rank",
            str(rank),
            "--world-size",
            "2",
            "--fabric",
            f"A,{local_ip},{next_ip},{port_a}",
            "--fabric",
            f"B,{local_ip},{next_ip},{port_b}",
            "--chunk-bytes",
            "65536",
        ]
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        self.process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        self.events = queue.Queue()
        self.reader = threading.Thread(target=self._read_stdout, daemon=True)
        self.reader.start()

    def _read_stdout(self):
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.events.put(json.loads(line))

    def send(self, payload):
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def wait_event(self, event_name, timeout=15):
        deadline = time.monotonic() + timeout
        observed = []
        while time.monotonic() < deadline:
            try:
                event = self.events.get(timeout=0.2)
            except queue.Empty:
                if self.process.poll() is not None:
                    stderr = self.process.stderr.read() if self.process.stderr else ""
                    self.fail(f"worker exited early: {stderr}")
                continue
            observed.append(event)
            if event.get("event") == event_name:
                return event
        stderr = self.process.stderr.read() if self.process.stderr else ""
        raise AssertionError(
            f"timed out waiting for {event_name}; observed={observed}; stderr={stderr}"
        )

    def fail(self, message):
        raise AssertionError(message)

    def close(self):
        if self.process.poll() is None:
            try:
                self.send({"command": "shutdown"})
                self.wait_event("SHUTDOWN_COMPLETE", timeout=3)
            except (BrokenPipeError, AssertionError):
                self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
        self.reader.join(timeout=1)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


class WorkerLoopbackTest(unittest.TestCase):
    @unittest.skipUnless(
        loopback_alias_available(),
        "host does not route arbitrary 127/8 aliases; the Debian/Mininet run covers this test",
    )
    def test_two_workers_switch_fabrics_at_committed_round(self):
        port_a = unused_port()
        port_b = unused_port()
        workers = [
            WorkerProcess(0, "127.0.0.11", "127.0.0.12", port_a, port_b),
            WorkerProcess(1, "127.0.0.12", "127.0.0.11", port_a, port_b),
        ]
        try:
            for worker in workers:
                ready = worker.wait_event("WORKER_READY")
                self.assertEqual(set(ready["fabrics"]), {"A", "B"})

            for worker in workers:
                worker.send({"command": "run_round", "round_id": 0})
            first = [worker.wait_event("ROUND_DONE") for worker in workers]
            self.assertTrue(all(event["route"] == "A" for event in first))
            self.assertTrue(all(event["version"] == 0 for event in first))

            for worker in workers:
                worker.send(
                    {
                        "command": "prepare",
                        "version": 1,
                        "route": "B",
                        "effective_round": 2,
                    }
                )
            for worker in workers:
                self.assertEqual(worker.wait_event("READY")["version"], 1)
            for worker in workers:
                worker.send({"command": "commit", "version": 1})
            for worker in workers:
                self.assertEqual(worker.wait_event("COMMITTED")["version"], 1)

            for round_id, expected_route, expected_version in (
                (1, "A", 0),
                (2, "B", 1),
            ):
                for worker in workers:
                    worker.send({"command": "run_round", "round_id": round_id})
                events = [worker.wait_event("ROUND_DONE") for worker in workers]
                for event in events:
                    self.assertEqual(event["route"], expected_route)
                    self.assertEqual(event["version"], expected_version)
                    self.assertEqual(event["bytes_sent"], 2 * 65536)
                    self.assertEqual(event["bytes_received"], 2 * 65536)
                    self.assertEqual(event["checksum_errors"], 0)
                    self.assertEqual(event["version_errors"], 0)
        finally:
            for worker in workers:
                worker.close()


if __name__ == "__main__":
    unittest.main()
