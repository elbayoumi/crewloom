"""Unit tests for task_queue: priority validation, state schema integrity, and lifecycle."""

from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import task_queue as queue
import usage_budget as control


class TestTaskQueueStateAndBoundaries(unittest.TestCase):
    """Test task queue state schemas, priority limits, and error handling."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="crewloom-queue-test-")
        self.folder = Path(self.temp_dir.name).resolve()
        self.addCleanup(self.temp_dir.cleanup)

    def test_empty_folder_returns_default_schema(self):
        folder = control.private_directory(self.folder / "queue")
        state = queue._state(folder)
        self.assertEqual(state["schema_version"], queue.SCHEMA_VERSION)
        self.assertEqual(state["jobs"], [])

    def test_malformed_schema_version_rejected(self):
        folder = control.private_directory(self.folder / "queue")
        control.write(folder / "queue.json", {"schema_version": 99, "jobs": []})
        with self.assertRaisesRegex(ValueError, "Malformed or exhausted queue"):
            queue._state(folder)

    def test_malformed_jobs_structure_rejected(self):
        folder = control.private_directory(self.folder / "queue")
        control.write(folder / "queue.json", {"schema_version": 1, "jobs": "not-a-list"})
        with self.assertRaisesRegex(ValueError, "Malformed or exhausted queue"):
            queue._state(folder)

    def test_duplicate_job_ids_rejected(self):
        folder = control.private_directory(self.folder / "queue")
        bad_jobs = [
            {"id": "job1", "status": "queued", "priority": 0},
            {"id": "job1", "status": "queued", "priority": 0},
        ]
        control.write(folder / "queue.json", {"schema_version": 1, "jobs": bad_jobs})
        with self.assertRaisesRegex(ValueError, "Malformed queue job"):
            queue._state(folder)

    def test_invalid_status_rejected(self):
        folder = control.private_directory(self.folder / "queue")
        bad_jobs = [{"id": "job1", "status": "exploding", "priority": 0}]
        control.write(folder / "queue.json", {"schema_version": 1, "jobs": bad_jobs})
        with self.assertRaisesRegex(ValueError, "Malformed queue job"):
            queue._state(folder)

    def test_invalid_priority_type_or_bounds_rejected(self):
        folder = control.private_directory(self.folder / "queue")
        bad_jobs = [{"id": "job1", "status": "queued", "priority": "high"}]
        control.write(folder / "queue.json", {"schema_version": 1, "jobs": bad_jobs})
        with self.assertRaisesRegex(ValueError, "Malformed queue priority"):
            queue._state(folder)

        bad_jobs = [{"id": "job1", "status": "queued", "priority": 105}]
        control.write(folder / "queue.json", {"schema_version": 1, "jobs": bad_jobs})
        with self.assertRaisesRegex(ValueError, "Malformed queue priority"):
            queue._state(folder)

    def test_change_job_actions(self):
        folder = control.private_directory(self.folder / "queue")
        job = {
            "id": "test-job-1",
            "project_id": "proj-1",
            "checkout_id": "chk-1",
            "status": "queued",
            "priority": 10,
        }
        control.write(folder / "queue.json", {"schema_version": 1, "jobs": [job]})

        # Cancel queued job
        updated = queue.change(folder, "test-job-1", "cancel")
        self.assertEqual(updated["status"], "cancelled")

        # Retry cancelled job is disallowed
        with self.assertRaisesRegex(ValueError, "Only queued jobs can be cancelled"):
            queue.change(folder, "test-job-1", "retry")

        # Set job to failed and retry
        job["status"] = "failed"
        job["error"] = "Execution timeout"
        control.write(folder / "queue.json", {"schema_version": 1, "jobs": [job]})

        retried = queue.change(folder, "test-job-1", "retry")
        self.assertEqual(retried["status"], "queued")
        self.assertIsNone(retried["error"])

        # Unknown job ID
        with self.assertRaisesRegex(ValueError, "Unknown queue job"):
            queue.change(folder, "missing-job", "cancel")

    def test_drain_workers_validation(self):
        folder = control.private_directory(self.folder / "queue")
        with self.assertRaisesRegex(ValueError, "Queue workers must be an integer from 1 to 4"):
            queue.drain(folder, workers=0)
        with self.assertRaisesRegex(ValueError, "Queue workers must be an integer from 1 to 4"):
            queue.drain(folder, workers=5)
        with self.assertRaisesRegex(ValueError, "Queue workers must be an integer from 1 to 4"):
            queue.drain(folder, workers="two")  # type: ignore

    def test_cli_main_argument_validation(self):
        # Missing required args for enqueue
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            with self.assertRaises(SystemExit) as cm:
                queue.main(["enqueue", "--directory", str(self.folder / "queue")])
            self.assertEqual(cm.exception.code, 2)

        # Invalid directory for status returns code 2
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            code = queue.main(["status", "--directory", str(self.folder / "non-existent")])
        self.assertEqual(code, 2)
        data = json.loads(stdout.getvalue())
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
