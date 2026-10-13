"""Offline invariants for capacity arithmetic and unsupported claims."""

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capacity_scenarios.py"
SPEC = importlib.util.spec_from_file_location("capacity_scenarios", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def case(members=10000, visitors=2500):
    return {
        "subreddit": "example", "window_days": 60,
        "target_event": "new signups", "geography": "serviceable market",
        "channel": "organic", "members": members,
        "weekly_visitors": visitors,
        "scenarios": [{
            "name": "base",
            "unique_icp_reach": {"value": 1000, "basis": "assumed_unique", "source": "explicit pilot hypothesis"},
            "visit_rate": {"value": 0.05, "basis": "measured", "source": "prior tagged visits"},
            "outcome_rate": {"value": 0.1, "basis": "measured", "source": "prior signup cohort"},
        }],
    }


class CapacityTests(unittest.TestCase):
    def test_explicit_funnel_math_and_label(self):
        result = MODULE.evaluate_case(case())
        row = result["scenarios"][0]
        self.assertEqual(row["attributable_visits_scenario"], "50.00")
        self.assertEqual(row["captured_outcomes_scenario"], "5.00")
        self.assertEqual(row["label"], "illustrative_scenario_not_forecast")

    def test_member_count_does_not_change_customer_scenario(self):
        small = MODULE.evaluate_case(case(members=10000, visitors=2500))
        large = MODULE.evaluate_case(case(members=1000000, visitors=250000))
        self.assertEqual(small["scenarios"][0]["captured_outcomes_scenario"],
                         large["scenarios"][0]["captured_outcomes_scenario"])

    def test_no_reach_or_rates_is_not_estimable(self):
        payload = case()
        payload["scenarios"] = []
        result = MODULE.evaluate_case(payload)
        self.assertEqual(result["status"], "not_estimable_without_reach_and_rates")
        self.assertEqual(result["scenarios"], [])

    def test_missing_reach_rejected_even_with_member_count(self):
        payload = case()
        del payload["scenarios"][0]["unique_icp_reach"]
        with self.assertRaisesRegex(ValueError, "unique_icp_reach"):
            MODULE.evaluate_case(payload)

    def test_rate_above_one_rejected(self):
        payload = case()
        payload["scenarios"][0]["visit_rate"]["value"] = 1.2
        with self.assertRaisesRegex(ValueError, "visit_rate"):
            MODULE.evaluate_case(payload)

    def test_all_assumptions_remain_labeled(self):
        payload = case()
        payload["scenarios"][0]["visit_rate"]["basis"] = "assumed"
        result = MODULE.evaluate_case(payload)
        row = result["scenarios"][0]
        self.assertEqual(row["provenance"]["visit_rate"]["basis"], "assumed")
        self.assertEqual(row["label"], "illustrative_scenario_not_forecast")

    def test_duplicate_scenario_names_rejected(self):
        payload = case()
        payload["scenarios"].append(dict(payload["scenarios"][0]))
        with self.assertRaisesRegex(ValueError, "distinct"):
            MODULE.evaluate_case(payload)

    def test_paid_and_organic_must_be_separate(self):
        payload = case()
        payload["channel"] = "organic and paid"
        with self.assertRaisesRegex(ValueError, "channel"):
            MODULE.evaluate_case(payload)

    def test_large_number_does_not_crash_decimal_formatting(self):
        payload = case()
        payload["scenarios"][0]["unique_icp_reach"]["value"] = "1e40"
        row = MODULE.evaluate_case(payload)["scenarios"][0]
        self.assertEqual(row["captured_outcomes_scenario"], "50000000000000000000000000000000000000.00")


if __name__ == "__main__":
    unittest.main()
