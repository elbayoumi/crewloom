import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from check_delivery_packet import CHECKS, check


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "proof.txt").write_text("Fixture only, not a real product review")
        self.digest = hashlib.sha256((self.root / "proof.txt").read_bytes()).hexdigest()
        self.packet = {"schema_version": 2, "project": "fixture", "revision": "abc", "implementer": "builder",
                       "checks": [{"id": x, "status": "pass", "reviewer": "reviewer",
                                   "revision": "abc", "evidence": [{"path": "proof.txt", "sha256": self.digest}],
                                   **({"review_scope": ["build", "browser", "responsive", "accessibility"]} if x == "technical" else {})} for x in sorted(CHECKS)],
                       "defects": []}

    def test_complete_packet_never_approves_product(self):
        result = check(self.packet, self.root, "abc")
        self.assertEqual(result["state"], "ready_for_review")
        self.assertFalse(result["product_approved"])

    def test_missing_stale_self_review_and_evidence_block(self):
        for field, value in [("revision", "old"), ("reviewer", "builder"),
                             ("status", "unverified"), ("evidence", [{"path": "missing.txt", "sha256": self.digest}]),
                             ("evidence", [{"path": "../outside.txt", "sha256": self.digest}])]:
            packet = copy.deepcopy(self.packet)
            packet["checks"][0][field] = value
            with self.subTest(field=field, value=value):
                self.assertEqual(check(packet, self.root, "abc")["state"], "blocked")

    def test_critical_and_exhausted_defects_count_and_block(self):
        self.packet["defects"] = [{"id": "D1", "severity": "critical", "status": "open",
                                    "owner": "builder", "failed_attempts": 2}]
        result = check(self.packet, self.root, "abc")
        self.assertEqual(result["open_defects"]["critical"], 1)
        self.assertEqual(result["escalation_required"], ["D1"])
        self.assertEqual(result["state"], "blocked")

    def test_empty_checks_and_duplicate_ids_block(self):
        self.packet["checks"] = [self.packet["checks"][0]] * 2
        self.assertEqual(check(self.packet, self.root, "abc")["state"], "blocked")

    def test_resolution_requires_verification(self):
        self.packet["defects"] = [{"id": "D1", "severity": "high", "status": "resolved",
                                    "owner": "builder", "failed_attempts": 1}]
        self.assertEqual(check(self.packet, self.root, "abc")["state"], "blocked")

    def test_changed_evidence_cannot_reuse_review(self):
        (self.root / "proof.txt").write_text("Replaced after review")
        self.assertTrue(any("changed" in x for x in check(self.packet, self.root, "abc")["problems"]))

    def test_whole_stale_packet_and_missing_expected_revision_block(self):
        for expected in (None, "new-commit"):
            self.assertEqual(check(self.packet, self.root, expected)["state"], "blocked")

    def test_old_evidence_format_is_not_silently_upgraded(self):
        self.packet["checks"][0]["evidence"] = ["proof.txt"]
        self.assertTrue(any("legacy" in x for x in check(self.packet, self.root, "abc")["problems"]))

    def test_reviewer_whitespace_does_not_create_independence(self):
        self.packet["checks"][0]["reviewer"] = " BUILDER "
        self.assertTrue(any("separate reviewer" in x for x in check(self.packet, self.root, "abc")["problems"]))

    def test_invalid_hash_blocks(self):
        self.packet["checks"][0]["evidence"][0]["sha256"] = "invalid"
        self.assertTrue(any("invalid sha256" in x for x in check(self.packet, self.root, "abc")["problems"]))

    def test_technical_review_requires_actual_review_scope(self):
        technical = next(row for row in self.packet["checks"] if row["id"] == "technical")
        technical["review_scope"] = ["build"]
        self.assertTrue(any("review_scope" in x for x in check(self.packet, self.root, "abc")["problems"]))

    def test_cli_good_and_changed_evidence(self):
        packet = self.root / "packet.json"
        packet.write_text(json.dumps(self.packet))
        command = [sys.executable, str(Path(__file__).with_name("check_delivery_packet.py")), str(packet), "--expected-revision", "abc"]
        good = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(good.returncode, 0)
        self.assertFalse(json.loads(good.stdout)["product_approved"])
        (self.root / "proof.txt").write_text("Changed")
        bad = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(bad.returncode, 1)


if __name__ == "__main__":
    unittest.main()
