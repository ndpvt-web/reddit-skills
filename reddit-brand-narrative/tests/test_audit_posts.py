"""Regression tests for archive safety and neutral candidate counts."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_posts.py"


class AuditPostsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw.json"
        self.out = self.root / "audit.json"

    def run_audit(self, rows, *extra, output=None):
        self.raw.write_text(json.dumps(rows))
        return subprocess.run([sys.executable, str(SCRIPT), "--input", str(self.raw),
                               "--output", str(output or self.out), "--subreddit", "example",
                               "--start", "2026-09-07T00:00:00.500Z",
                               "--end", "2026-09-08T00:00:00Z", "--alias", "Brand", *extra],
                              capture_output=True, text=True)

    def post(self, **overrides):
        result = {"id": "a", "subreddit": "example", "title": "Brand question",
                  "selftext": "Anyone using it?", "created_utc": 1788739201}
        result.update(overrides)
        return result

    def test_refuses_overwriting_raw_archive(self):
        original = [self.post()]
        result = self.run_audit(original, output=self.raw)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(self.raw.read_text()), original)

    def test_fractional_start_boundary(self):
        result = self.run_audit([self.post(created_utc=1788739200), self.post(id="b")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.out.read_text())["posts_in_window"], 1)

    def test_referral_can_also_be_discussion_candidate(self):
        result = self.run_audit([self.post(selftext="Is it safe? Referral code ABC")],
                                "--incentive-pattern", "referral")
        self.assertEqual(result.returncode, 0, result.stderr)
        labels = json.loads(self.out.read_text())["matches"][0]["labels"]
        self.assertIn("incentive_candidate", labels)
        self.assertIn("substantive_candidate", labels)

    def test_conflicting_duplicate_rejected(self):
        result = self.run_audit([self.post(), self.post(title="Different")])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Conflicting duplicate", result.stderr)

    def test_removed_moderator_title(self):
        result = self.run_audit([self.post(title="[ Removed by moderator ]", selftext="Brand complaint")])
        self.assertEqual(result.returncode, 0, result.stderr)
        labels = json.loads(self.out.read_text())["matches"][0]["labels"]
        self.assertIn("removed_or_deleted", labels)
        self.assertNotIn("substantive_candidate", labels)

    def test_missing_subreddit_rejected(self):
        post = self.post()
        del post["subreddit"]
        result = self.run_audit([post])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing subreddit", result.stderr)

    def test_wrong_subreddit_rejected(self):
        result = self.run_audit([self.post(subreddit="different")])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected only r/example", result.stderr)

    def test_duplicate_identical_is_counted_once(self):
        row = self.post()
        result = self.run_audit([row, row])
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = json.loads(self.out.read_text())
        self.assertEqual(audit["posts_in_window"], 1)
        self.assertEqual(audit["identical_duplicates"], 1)

    def test_ambiguous_hit_requires_context(self):
        row = self.post(title="A FUTU account", selftext="Nothing else")
        result = self.run_audit([row], "--ambiguous-alias", "FUTU", "--context", "broker")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.out.read_text())["candidate_matches"], 0)
        row["selftext"] = "Broker options"
        result = self.run_audit([row], "--ambiguous-alias", "FUTU", "--context", "broker")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.out.read_text())["matches"][0]["contextual_aliases"], ["FUTU"])


if __name__ == "__main__":
    unittest.main()
