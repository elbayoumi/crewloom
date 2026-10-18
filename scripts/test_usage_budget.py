"""Unit tests for usage_budget: admission boundaries, ledger security, and atomicity."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

# Ensure scripts directory is on sys.path for direct execution and discovery
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import project_binding as pb
import usage_budget as budget


class TestUsageBudgetMoneyConversions(unittest.TestCase):
    """Test money conversion precision, boundary rounding, and refusal of invalid inputs."""

    def test_zero_amount(self):
        self.assertEqual(budget.money(0), 0)
        self.assertEqual(budget.money(0.0), 0)
        self.assertEqual(budget.money("0"), 0)

    def test_positive_integers_and_floats(self):
        self.assertEqual(budget.money(1), 1_000_000)
        self.assertEqual(budget.money(0.5), 500_000)
        self.assertEqual(budget.money("0.000001"), 1)

    def test_fractional_micro_usd_rounds_up_to_ceiling(self):
        # 0.0000001 USD is 0.1 micro-USD -> rounds up to 1 micro-USD
        self.assertEqual(budget.money(0.0000001), 1)
        self.assertEqual(budget.money("0.0000002"), 1)

    def test_booleans_strictly_rejected(self):
        with self.assertRaisesRegex(ValueError, "Dollar allowance must be finite and nonnegative"):
            budget.money(True)
        with self.assertRaisesRegex(ValueError, "Dollar allowance must be finite and nonnegative"):
            budget.money(False)

    def test_unsupported_types_rejected(self):
        with self.assertRaises(TypeError):
            budget.money([1.0])
        with self.assertRaises(TypeError):
            budget.money({"cost": 1.0})

    def test_negative_amounts_rejected(self):
        with self.assertRaisesRegex(ValueError, "Dollar allowance must be finite and nonnegative"):
            budget.money(-0.01)
        with self.assertRaisesRegex(ValueError, "Dollar allowance must be finite and nonnegative"):
            budget.money(-5)

    def test_infinite_and_nan_rejected(self):
        with self.assertRaisesRegex(ValueError, "Dollar allowance must be finite and nonnegative"):
            budget.money(float("inf"))
        with self.assertRaisesRegex(ValueError, "Dollar allowance must be finite and nonnegative"):
            budget.money(float("-inf"))
        with self.assertRaisesRegex(ValueError, "Dollar allowance must be finite and nonnegative"):
            budget.money(float("nan"))
        with self.assertRaisesRegex(ValueError, "Dollar allowance must be finite and nonnegative"):
            budget.money("inf")
        with self.assertRaises(ValueError):
            budget.money("not-a-number")


class TestUsageBudgetFilesystemSecurity(unittest.TestCase):
    """Test private directory creation, permissions validation, and symlink refusal."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="crewloom-budget-test-")
        self.folder = Path(self.temp_dir.name).resolve()
        self.addCleanup(self.temp_dir.cleanup)

    def test_private_directory_created_with_0700(self):
        target = self.folder / "private_budget"
        resolved = budget.private_directory(target, create=True)
        self.assertTrue(resolved.is_dir())
        if os.name != "nt":
            mode = stat.S_IMODE(resolved.stat().st_mode)
            self.assertEqual(mode & 0o077, 0, "Directory group and other permissions must be 0")

    def test_private_directory_not_created_when_create_is_false(self):
        target = self.folder / "absent"
        with self.assertRaisesRegex(ValueError, "Existing configured control directory required"):
            budget.private_directory(target, create=False)

    def test_insecure_permissions_rejected(self):
        if os.name == "nt":
            self.skipTest("POSIX mode bits not enforced on Windows")
        target = self.folder / "insecure_budget"
        target.mkdir(mode=0o777)
        # Explicitly chmod to ensure 0o777 is not masked by umask
        os.chmod(target, 0o777)
        with self.assertRaisesRegex(ValueError, "Control directory must be owner-only"):
            budget.private_directory(target, create=False)

    def test_symlink_directory_rejected(self):
        real_target = self.folder / "real_dir"
        real_target.mkdir(mode=0o700)
        symlink_target = self.folder / "symlink_dir"
        symlink_target.symlink_to(real_target)
        with self.assertRaisesRegex(ValueError, "Control directory may not follow symlinks"):
            budget.private_directory(symlink_target, create=False)

    def test_symlink_file_read_write_rejected(self):
        real_file = self.folder / "real_file.json"
        real_file.write_text("{}", encoding="utf-8")
        symlink_file = self.folder / "symlink_file.json"
        symlink_file.symlink_to(real_file)
        with self.assertRaisesRegex(ValueError, "Invalid or oversized control record"):
            budget.read(symlink_file)
        with self.assertRaisesRegex(ValueError, "Invalid or oversized control record"):
            budget.write(symlink_file, {"key": "value"})

    def test_file_read_oversized_rejected(self):
        big_file = self.folder / "oversized.json"
        big_file.write_text("{}", encoding="utf-8")
        with patch.object(Path, "lstat") as mock_lstat:
            mock_res = type(
                "Stat",
                (),
                {
                    "st_mode": stat.S_IFREG | 0o600,
                    "st_size": budget.MAX_RECORD_SIZE_BYTES + 100,
                    "st_nlink": 1,
                    "st_uid": os.getuid(),
                },
            )()
            mock_lstat.return_value = mock_res
            with self.assertRaisesRegex(ValueError, "Invalid or oversized control record"):
                budget.read(big_file)


class TestUsageBudgetLifecycle(unittest.TestCase):
    """Test configure, reserve, settle, summary and CLI execution."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="crewloom-lifecycle-test-")
        self.folder = Path(self.temp_dir.name).resolve()
        self.addCleanup(self.temp_dir.cleanup)

        # Setup mock project binding
        self.project_root = self.folder / "project"
        self.project_root.mkdir(mode=0o700)
        self.config = pb.default_config("budget-project")
        (self.project_root / pb.CONFIG_NAME).write_text(json.dumps(self.config), encoding="utf-8")
        self.binding_dir = self.project_root / ".crewloom"
        self.binding_dir.mkdir(mode=0o700)
        self.checkout_id = uuid.uuid4().hex
        self.binding_data = {
            "schema_version": 1,
            "project_root": str(self.project_root),
            "project_id": "budget-project",
            "checkout_id": self.checkout_id,
            "bound_at": "2026-10-18T20:00:00Z",
            "active_task_id": None,
            "relocations": [],
        }
        (self.binding_dir / "binding.json").write_text(json.dumps(self.binding_data), encoding="utf-8")

        self.identity = {
            "project_root": str(self.project_root),
            "project_id": "budget-project",
            "checkout_id": self.checkout_id,
            "workflow": "test-flow",
            "step": "step-1",
        }
        self.budget_dir = self.folder / "budget_ctrl"

    def test_configure_and_summary(self):
        res = budget.configure(self.budget_dir, max_requests=10, max_usd=5.0, reserve_usd=0.25)
        self.assertEqual(res["requests"], 0)
        self.assertEqual(res["max_requests"], 10)
        self.assertEqual(res["max_usd"], 5.0)
        self.assertEqual(res["reserved_or_reported_usd"], 0.0)
        self.assertFalse(res["over_allowance"])

    def test_cannot_reconfigure_existing_budget(self):
        budget.configure(self.budget_dir, max_requests=10)
        with self.assertRaisesRegex(ValueError, "Budget already exists"):
            budget.configure(self.budget_dir, max_requests=20)

    def test_invalid_max_requests_rejected(self):
        with self.assertRaisesRegex(ValueError, "max_requests must be an integer from 1 to 10000"):
            budget.configure(self.budget_dir, max_requests=0)
        with self.assertRaisesRegex(ValueError, "max_requests must be an integer from 1 to 10000"):
            budget.configure(self.budget_dir, max_requests=budget.MAX_REQUEST_LIMIT + 1)

    def test_mismatched_dollar_budget_arguments_rejected(self):
        with self.assertRaisesRegex(ValueError, "Dollar control needs both max_usd and reserve_usd"):
            budget.configure(self.budget_dir, max_requests=10, max_usd=5.0, reserve_usd=None)
        with self.assertRaisesRegex(ValueError, "Dollar control needs both max_usd and reserve_usd"):
            budget.configure(self.budget_dir, max_requests=10, max_usd=None, reserve_usd=0.5)

    def test_reserve_and_settle_lifecycle(self):
        budget.configure(self.budget_dir, max_requests=2, max_usd=1.0, reserve_usd=0.20)

        call_id = budget.reserve(self.budget_dir, self.identity)
        self.assertTrue(isinstance(call_id, str) and len(call_id) == 32)

        summ = budget.summary(self.budget_dir)
        self.assertEqual(summ["requests"], 1)
        self.assertEqual(summ["reserved_or_reported_usd"], 0.20)
        self.assertEqual(summ["unknown_cost_calls"], 1)

        # Settle known cost
        budget.settle(self.budget_dir, call_id, cost=0.15)
        summ2 = budget.summary(self.budget_dir)
        self.assertEqual(summ2["reserved_or_reported_usd"], 0.15)
        self.assertEqual(summ2["unknown_cost_calls"], 0)

    def test_reserve_exhausts_request_budget(self):
        budget.configure(self.budget_dir, max_requests=1)
        budget.reserve(self.budget_dir, self.identity)

        with self.assertRaisesRegex(ValueError, "request budget exhausted"):
            budget.reserve(self.budget_dir, self.identity)

    def test_reserve_exhausts_dollar_admission(self):
        budget.configure(self.budget_dir, max_requests=10, max_usd=0.50, reserve_usd=0.30)
        budget.reserve(self.budget_dir, self.identity)

        # Second reserve would require 0.30 + 0.30 = 0.60 > 0.50 max_usd
        with self.assertRaisesRegex(ValueError, "dollar admission allowance exhausted"):
            budget.reserve(self.budget_dir, self.identity)

    def test_reserve_identity_mismatch_rejected(self):
        budget.configure(self.budget_dir, max_requests=10)
        tampered_identity = dict(self.identity)
        tampered_identity["checkout_id"] = "a" * 32

        with self.assertRaisesRegex(ValueError, "does not match project binding"):
            budget.reserve(self.budget_dir, tampered_identity)

    def test_settle_unknown_cost_call(self):
        budget.configure(self.budget_dir, max_requests=5, max_usd=1.0, reserve_usd=0.10)
        call_id = budget.reserve(self.budget_dir, self.identity)

        # Settle without cost -> status becomes unknown, keeps reserved charge
        budget.settle(self.budget_dir, call_id, cost=None)
        summ = budget.summary(self.budget_dir)
        self.assertEqual(summ["unknown_cost_calls"], 1)
        self.assertEqual(summ["reserved_or_reported_usd"], 0.10)

    def test_double_settle_rejected(self):
        budget.configure(self.budget_dir, max_requests=5)
        call_id = budget.reserve(self.budget_dir, self.identity)
        budget.settle(self.budget_dir, call_id, cost=0.05)

        with self.assertRaisesRegex(ValueError, "Unknown or already settled budget reservation"):
            budget.settle(self.budget_dir, call_id, cost=0.05)

    def test_cli_configure_and_status(self):
        budget_path = str(self.folder / "cli_budget")
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            ret = budget.main(["configure", "--directory", budget_path, "--max-requests", "5"])
        self.assertEqual(ret, 0)
        data = json.loads(stdout.getvalue())
        self.assertEqual(data["max_requests"], 5)

        stdout_status = io.StringIO()
        with patch("sys.stdout", stdout_status):
            ret_status = budget.main(["status", "--directory", budget_path])
        self.assertEqual(ret_status, 0)
        data_status = json.loads(stdout_status.getvalue())
        self.assertEqual(data_status["requests"], 0)

    def test_cli_error_returns_code_2(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            ret = budget.main(["status", "--directory", str(self.folder / "nonexistent")])
        self.assertEqual(ret, 2)
        err = json.loads(stdout.getvalue())
        self.assertIn("error", err)


if __name__ == "__main__":
    unittest.main()
