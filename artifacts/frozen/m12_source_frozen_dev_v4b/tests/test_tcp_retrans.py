import socket
import struct
import sys
import unittest
from unittest import mock

from limer_v0.tcp_retrans import (
    TcpRetransmissionSampler, parse_total_retransmissions,
    read_total_retransmissions,
)


class TcpRetransmissionTest(unittest.TestCase):
    def test_native_endian_total_counter_and_short_prefix(self):
        info = bytearray(104)
        struct.pack_into("=I", info, 100, 0x12345678)
        self.assertEqual(parse_total_retransmissions(bytes(info)), 0x12345678)
        with self.assertRaises(ValueError):
            parse_total_retransmissions(bytes(info[:103]))

    def test_delta_wrap_and_connection_replacement(self):
        sampler = TcpRetransmissionSampler()
        original, replacement = object(), object()
        with mock.patch("limer_v0.tcp_retrans.read_total_retransmissions",
                        side_effect=[(1 << 32) - 2, 3, 7]):
            first = sampler.sample({"A": original}, 100)[0]
            wrapped = sampler.sample({"A": original}, 120)[0]
            replaced = sampler.sample({"A": replacement}, 140)[0]
        self.assertIsNone(first["retrans_delta"])
        self.assertEqual(wrapped["retrans_delta"], 5)
        self.assertEqual(wrapped["sample_interval_ns"], 20)
        self.assertIsNone(replaced["retrans_delta"])

    def test_failed_sample_is_missing_and_resets_baseline(self):
        sampler = TcpRetransmissionSampler()
        sock = object()
        with mock.patch("limer_v0.tcp_retrans.read_total_retransmissions",
                        side_effect=[2, OSError("closed"), 5]):
            sampler.sample({"A": sock}, 100)
            missing = sampler.sample({"A": sock}, 120)[0]
            resumed = sampler.sample({"A": sock}, 140)[0]
        self.assertEqual(missing["status"], "unavailable")
        self.assertIsNone(missing["total_retrans"])
        self.assertIsNone(missing["retrans_delta"])
        self.assertIsNone(resumed["retrans_delta"])

    def test_removed_connection_does_not_reuse_baseline(self):
        sampler = TcpRetransmissionSampler()
        sock = object()
        with mock.patch("limer_v0.tcp_retrans.read_total_retransmissions", return_value=2):
            sampler.sample({"A": sock}, 100)
            self.assertEqual(sampler.sample({}, 120), [])
            self.assertIsNone(sampler.sample({"A": sock}, 140)[0]["retrans_delta"])

    @unittest.skipUnless(sys.platform == "linux", "Linux TCP_INFO runtime required")
    def test_actual_linux_tcp_connection(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            with socket.create_connection(listener.getsockname()) as sender:
                receiver, _ = listener.accept()
                with receiver:
                    sender.sendall(b"telemetry")
                    self.assertEqual(receiver.recv(9), b"telemetry")
                    self.assertGreaterEqual(read_total_retransmissions(sender), 0)


if __name__ == "__main__":
    unittest.main()
