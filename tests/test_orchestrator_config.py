import unittest

from limer_v0.orchestrator import aggregate_round_events, validate_config


def valid_config():
    return {
        "condition": "C1",
        "topology": "single",
        "chunk_bytes": 2097152,
        "warmup_rounds": 1,
        "baseline_rounds": 2,
        "post_fault_rounds": 3,
        "fault_rate_mbit": 20.0,
        "fault_loss_pct": 0.0,
        "detector": False,
        "recovery": False,
        "oracle": False,
        "transient_ms": 0,
        "what_changes": "Rate-cap only s0 to w2 while link stays up.",
        "expected": "Post-fault throughput remains below the baseline.",
    }


class ConfigValidationTest(unittest.TestCase):
    def test_accepts_complete_config(self):
        result = validate_config(valid_config())
        self.assertEqual(result["condition"], "C1")

    def test_rejects_blank_experiment_intent(self):
        for field in ("what_changes", "expected"):
            config = valid_config()
            config[field] = "   "
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                validate_config(config)

    def test_rejects_recovery_on_single_topology(self):
        config = valid_config()
        config["recovery"] = True
        with self.assertRaisesRegex(ValueError, "dual"):
            validate_config(config)

    def test_rejects_unknown_condition(self):
        config = valid_config()
        config["condition"] = "C99"
        with self.assertRaisesRegex(ValueError, "condition"):
            validate_config(config)

    def test_c2_requires_detector(self):
        config = valid_config()
        config["condition"] = "C2"
        config["detector"] = False
        with self.assertRaisesRegex(ValueError, "detector"):
            validate_config(config)

    def test_c3_requires_full_non_oracle_path(self):
        config = valid_config()
        config.update(
            {
                "condition": "C3",
                "topology": "dual",
                "detector": True,
                "recovery": True,
            }
        )
        self.assertEqual(validate_config(config)["condition"], "C3")
        config["oracle"] = True
        with self.assertRaisesRegex(ValueError, "C3"):
            validate_config(config)

    def test_c5_requires_positive_transient(self):
        config = valid_config()
        config.update(
            {
                "condition": "C5",
                "topology": "dual",
                "detector": True,
                "recovery": True,
                "transient_ms": 0,
            }
        )
        with self.assertRaisesRegex(ValueError, "transient"):
            validate_config(config)


class RoundAggregationTest(unittest.TestCase):
    def _events(self):
        return [
            {
                "event": "ROUND_DONE",
                "rank": rank,
                "round_id": 3,
                "route": "A",
                "version": 0,
                "duration_ns": 1_000_000_000 + rank,
                "bytes_sent": 12_000,
                "bytes_received": 12_000,
                "frame_count": 6,
                "checksum_errors": 0,
                "version_errors": 0,
            }
            for rank in range(4)
        ]

    def test_aggregates_collective_round_by_slowest_rank(self):
        result = aggregate_round_events(self._events(), "baseline", world_size=4)
        self.assertEqual(result["round_id"], 3)
        self.assertEqual(result["period"], "baseline")
        self.assertEqual(result["route"], "A")
        self.assertEqual(result["version"], 0)
        self.assertEqual(result["bytes_completed"], 48_000)
        self.assertEqual(result["duration_ns"], 1_000_000_003)
        self.assertAlmostEqual(result["duration_s"], 1.000000003)
        self.assertEqual(result["checksum_errors"], 0)
        self.assertEqual(result["version_errors"], 0)

    def test_rejects_missing_rank(self):
        with self.assertRaisesRegex(ValueError, "ranks"):
            aggregate_round_events(self._events()[:-1], "baseline", world_size=4)

    def test_rejects_route_or_version_split_brain(self):
        events = self._events()
        events[-1]["route"] = "B"
        with self.assertRaisesRegex(ValueError, "route"):
            aggregate_round_events(events, "post_fault", world_size=4)


if __name__ == "__main__":
    unittest.main()
