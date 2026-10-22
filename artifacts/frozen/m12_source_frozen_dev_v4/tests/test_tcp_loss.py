import socket
import struct
import sys
import unittest
from unittest import mock

from limer_v0.tcp_loss import TcpDeliverySampler, TcpLossDetector, parse_delivery_info


def sample(t_ms, total=0, lost=0, unacked=0, dsack=0, reordered=0, generation=1):
    return dict(status="ok", connection_generation=generation,
                sample_t_monotonic_ns=int(t_ms * 1_000_000), total_retrans=total,
                lost=lost, unacked=unacked, dsack_dups=dsack, reord_seen=reordered)


class TcpLossDetectorTest(unittest.TestCase):
    def test_requires_sustained_outstanding_loss_not_a_counter_jump(self):
        detector = TcpLossDetector()
        self.assertIsNone(detector.observe(sample(0)))
        for t in (5, 10, 15, 20, 25, 30):
            self.assertIsNone(detector.observe(sample(t, 2, 1, 10)))
        decision = detector.observe(sample(35, 2, 1, 10))
        self.assertEqual(decision["evidence_age_ms"], 30)
        self.assertEqual(decision["rule_version"], "tcp-loss-v3")
        self.assertIsNone(detector.observe(sample(40, 4, 2, 10)))

    def test_idle_resets_evidence(self):
        for replacement in (sample(20, 2, 1, 0),):
            detector = TcpLossDetector()
            for s in (sample(0), sample(5, 2, 1, 10), sample(10, 2, 1, 10),
                      replacement, sample(25, 2, 1, 10), sample(35, 2, 1, 10)):
                self.assertIsNone(detector.observe(s))

    def test_single_event_never_confirms_but_repeated_loss_may_clear_between_events(self):
        detector = TcpLossDetector()
        detector.observe(sample(0))
        for t in range(5, 40, 5):
            self.assertIsNone(detector.observe(sample(t, 1, 1, 10)))
        self.assertIsNone(detector.observe(sample(40, 1, 0, 10)))
        self.assertIsNotNone(detector.observe(sample(45, 2, 1, 10)))

    def test_dsack_and_reordering_veto_spurious_retransmissions(self):
        for field in ("dsack_dups", "reord_seen"):
            detector = TcpLossDetector()
            detector.observe(sample(0))
            detector.observe(sample(5, 2, 1, 10))
            for t in range(10, 106, 5):
                s = sample(t, 4, 2, 10)
                s[field] = 1
                self.assertIsNone(detector.observe(s))

    def test_missing_read_and_long_sample_gap_do_not_bridge_evidence(self):
        for interruption in (dict(status="unavailable"), sample(40, 2, 1, 10)):
            detector = TcpLossDetector()
            for s in (sample(0), sample(5, 2, 1, 10), sample(10, 2, 1, 10),
                      interruption, sample(45, 2, 1, 10)):
                self.assertIsNone(detector.observe(s))

    def test_replacement_and_counter_regression_reset_connection_evidence(self):
        for interruption in (sample(15, 2, 1, 10, generation=2),
                             sample(15, 1, 1, 10), sample(1, 2, 1, 10)):
            detector = TcpLossDetector()
            for s in (sample(0), sample(5, 2, 1, 10), sample(10, 2, 1, 10), interruption):
                self.assertIsNone(detector.observe(s))

    def test_retransmissions_without_loss_and_outstanding_data_never_confirm(self):
        detector = TcpLossDetector()
        for t in range(0, 150, 5):
            self.assertIsNone(detector.observe(sample(t, t, 0, 10)))

    def test_missing_old_connection_does_not_transfer_reordering_veto_to_replacement(self):
        detector = TcpLossDetector()
        detector.observe(sample(0))
        detector.observe(sample(5, dsack=1))
        detector.observe(dict(status="unavailable"))
        detector.observe(sample(10, generation=2))
        alarms = []
        for t in range(15, 51, 5):
            decision = detector.observe(sample(t, 2, 1, 10, generation=2))
            if decision:
                alarms.append(decision)
        self.assertEqual(len(alarms), 1)

    def test_old_retransmissions_cannot_confirm_an_unrelated_later_stall(self):
        detector = TcpLossDetector()
        for t in range(0, 250, 5):
            self.assertIsNone(detector.observe(sample(t, 2 if t else 0,
                                                     1 if t >= 150 else 0, 10)))

    def test_one_alarm_per_generation_but_new_connection_can_confirm(self):
        detector = TcpLossDetector()
        alarms = []
        for generation in (1, 2):
            for t in range(0, 60, 5):
                s = sample(t + 100 * (generation - 1), 2 if t else 0,
                           1 if t else 0, 10, generation=generation)
                result = detector.observe(s)
                if result:
                    alarms.append(result)
        self.assertEqual(len(alarms), 2)


class TcpDeliverySamplerTest(unittest.TestCase):
    def test_verified_linux_offsets_and_short_abi(self):
        info = bytearray(224)
        for offset, value in ((24, 10), (32, 2), (36, 1), (68, 1200),
                              (100, 7), (216, 3), (220, 4)):
            struct.pack_into("=I", info, offset, value)
        struct.pack_into("=Q", info, 120, 10000)
        struct.pack_into("=Q", info, 200, 20000)
        result = parse_delivery_info(bytes(info))
        self.assertEqual((result["unacked"], result["lost"], result["dsack_dups"],
                          result["reord_seen"], result["bytes_acked"]), (10, 2, 3, 4, 10000))
        with self.assertRaises(ValueError):
            parse_delivery_info(bytes(info[:223]))

    def test_failed_read_is_missing_and_replacement_is_a_new_generation(self):
        sampler = TcpDeliverySampler()
        a, b = mock.Mock(), mock.Mock()
        a.getsockopt.side_effect = [bytes(224), OSError("closed")]
        b.getsockopt.return_value = bytes(224)
        with mock.patch("limer_v0.tcp_loss.sys.platform", "linux"):
            first = sampler.sample({"A": a})[0]
            missing = sampler.sample({"A": a})[0]
            replacement = sampler.sample({"A": b})[0]
        self.assertEqual(missing["status"], "unavailable")
        self.assertNotIn("lost", missing)
        self.assertGreater(replacement["connection_generation"], first["connection_generation"])
        self.assertGreaterEqual(first["sample_t_monotonic_ns"], first["read_start_ns"])

    @unittest.skipUnless(sys.platform == "linux", "Linux TCP_INFO runtime required")
    def test_actual_linux_loopback_has_complete_extended_state(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            with socket.create_connection(listener.getsockname()) as sender:
                receiver, _ = listener.accept()
                with receiver:
                    sender.sendall(b"delivery-state")
                    self.assertEqual(receiver.recv(14), b"delivery-state")
                    row = TcpDeliverySampler().sample({"A": sender})[0]
                    self.assertEqual(row["status"], "ok")
                    self.assertGreaterEqual(row["bytes_sent"], 14)
