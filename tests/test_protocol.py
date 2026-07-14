import socket
import unittest

from limer_v0.protocol import FrameHeader, crc32, recv_exact


class FrameHeaderTest(unittest.TestCase):
    def test_round_trip(self):
        original = FrameHeader(
            round_id=7,
            step_id=3,
            version=2,
            payload_len=4096,
            checksum=123456,
        )
        self.assertEqual(FrameHeader.unpack(original.pack()), original)

    def test_rejects_invalid_magic(self):
        header = FrameHeader(1, 2, 0, 16, 42).pack()
        with self.assertRaisesRegex(ValueError, "magic"):
            FrameHeader.unpack(b"BAD!" + header[4:])

    def test_rejects_out_of_range_field(self):
        with self.assertRaisesRegex(ValueError, "round_id"):
            FrameHeader(-1, 0, 0, 1, 1).pack()

    def test_recv_exact_rejects_truncated_stream(self):
        left, right = socket.socketpair()
        try:
            left.sendall(b"abc")
            left.close()
            with self.assertRaisesRegex(EOFError, "expected 4 bytes"):
                recv_exact(right, 4)
        finally:
            right.close()

    def test_crc32_is_stable(self):
        self.assertEqual(crc32(b"limer"), crc32(b"limer"))
        self.assertNotEqual(crc32(b"limer"), crc32(b"LIMER"))


if __name__ == "__main__":
    unittest.main()
