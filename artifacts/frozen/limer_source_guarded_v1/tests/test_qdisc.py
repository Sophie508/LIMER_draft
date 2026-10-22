import json
import unittest

from limer_v0.qdisc import parse_tc_json


class QdiscParserTest(unittest.TestCase):
    def test_parses_root_netem_sample(self):
        fixture = json.dumps(
            [
                {
                    "kind": "netem",
                    "handle": "1:",
                    "root": True,
                    "bytes": 12000,
                    "packets": 40,
                    "drops": 2,
                    "overlimits": 5,
                    "requeues": 0,
                    "backlog": 65536,
                    "qlen": 4,
                }
            ]
        )
        sample = parse_tc_json(fixture, "s0-eth3", 99)
        self.assertEqual(sample.interface, "s0-eth3")
        self.assertEqual(sample.t_ns, 99)
        self.assertEqual(sample.kind, "netem")
        self.assertEqual(sample.bytes, 12000)
        self.assertEqual(sample.packets, 40)
        self.assertEqual(sample.drops, 2)
        self.assertEqual(sample.overlimits, 5)
        self.assertEqual(sample.backlog_bytes, 65536)
        self.assertEqual(sample.qlen, 4)

    def test_missing_optional_counters_default_to_zero(self):
        sample = parse_tc_json('[{"kind":"netem","root":true}]', "s0-eth1", 1)
        self.assertEqual(sample.bytes, 0)
        self.assertEqual(sample.drops, 0)
        self.assertEqual(sample.backlog_bytes, 0)
        self.assertEqual(sample.rx_bytes, 0)
        self.assertEqual(sample.tx_dropped, 0)

    def test_rejects_empty_qdisc_list(self):
        with self.assertRaisesRegex(ValueError, "no qdisc"):
            parse_tc_json("[]", "s0-eth3", 99)


if __name__ == "__main__":
    unittest.main()
