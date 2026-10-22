import unittest

from limer_v0.orchestrator import _guarded_headroom_snapshot, validate_config
from test_orchestrator_config import valid_config, valid_active_active_config


class GuardedHeadroomTest(unittest.TestCase):
    def test_idle_window_retains_calibrated_spare(self):
        result = _guarded_headroom_snapshot({"spare_bps": None}, {"spare_bps": 60e6})
        self.assertEqual(result["spare_bps"], 60e6)
        self.assertEqual(result["estimate_source"], "calibrated_idle_fallback")

    def test_new_congestion_lowers_spare(self):
        result = _guarded_headroom_snapshot({"spare_bps": 10e6}, {"spare_bps": 60e6})
        self.assertEqual(result["spare_bps"], 10e6)

    def test_fault_induced_idle_does_not_raise_spare(self):
        result = _guarded_headroom_snapshot({"spare_bps": 90e6}, {"spare_bps": 5e6})
        self.assertEqual(result["spare_bps"], 5e6)

    def test_unknown_baseline_remains_unknown(self):
        result = _guarded_headroom_snapshot({"spare_bps": 60e6}, {"spare_bps": None})
        self.assertIsNone(result["spare_bps"])

    def test_does_not_mutate_or_alias_snapshots(self):
        current = {"spare_bps": None}
        baseline = {"spare_bps": 60e6}
        result = _guarded_headroom_snapshot(current, baseline)
        result["current_observation"]["spare_bps"] = 1
        result["calibrated_reference"]["spare_bps"] = 2
        self.assertEqual(current, {"spare_bps": None})
        self.assertEqual(baseline, {"spare_bps": 60e6})

    def test_default_mode_is_original_live_policy(self):
        self.assertEqual(validate_config(valid_config())["policy_headroom_mode"], "live")

    def test_guarded_mode_requires_policy_gate(self):
        config = valid_config()
        config["policy_headroom_mode"] = "baseline_guarded"
        with self.assertRaisesRegex(ValueError, "host_gate policy"):
            validate_config(config)

    def test_unknown_mode_is_rejected(self):
        config = valid_config()
        config["policy_headroom_mode"] = "guess_capacity"
        with self.assertRaisesRegex(ValueError, "policy_headroom_mode"):
            validate_config(config)

    def test_guarded_policy_mode_is_accepted(self):
        config = valid_active_active_config()
        config.update(scenario_id="AA12_POLICY", host_gate="policy", detector_rule="burst",
                      policy_headroom_mode="baseline_guarded")
        self.assertEqual(validate_config(config)["policy_headroom_mode"], "baseline_guarded")
