"""Offline collector pagination and failure-status regression tests."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "collect_arctic.py"
SPEC = importlib.util.spec_from_file_location("collect_arctic", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CollectorTests(unittest.TestCase):
    def test_short_page_requires_follow_up_empty_page(self):
        calls = []

        def page(_session, _path, params):
            calls.append(dict(params))
            return [{"id": "a", "created_utc": 1790000000}] if len(calls) == 1 else []

        with patch.object(MODULE, "fetch_page", side_effect=page), patch.object(MODULE.time, "sleep"):
            posts, ledger = MODULE.collect("example", "2026-09-07", "2026-10-07", None, 10, 25)
        self.assertEqual(len(posts), 1)
        self.assertEqual(ledger["pages"], 2)
        self.assertEqual(ledger["status"], "verified_empty_page_after_pagination")

    def test_api_error_is_partial_not_zero(self):
        with patch.object(MODULE, "fetch_page", side_effect=RuntimeError("HTTP 422 timeout")):
            posts, ledger = MODULE.collect("example", "2026-09-07", "2026-10-07", None, 10, 25)
        self.assertEqual(posts, [])
        self.assertEqual(ledger["status"], "partial")
        self.assertIn("422", ledger["errors"][0])

    def test_query_mode_is_labeled_search_only(self):
        with patch.object(MODULE, "fetch_page", return_value=[]):
            _, ledger = MODULE.collect("example", "2026-09-07", "2026-10-07", "Brand", 10, 25)
        self.assertEqual(ledger["mode"], "search_only")

    def test_repeated_full_page_is_partial(self):
        row = {"id": "a", "created_utc": 1790000000}
        with patch.object(MODULE, "fetch_page", return_value=[row, row]), patch.object(MODULE.time, "sleep"):
            _, ledger = MODULE.collect("example", "2026-09-07", "2026-10-07", None, 10, 2)
        self.assertEqual(ledger["status"], "partial")
        self.assertTrue(ledger["errors"])


if __name__ == "__main__":
    unittest.main()
