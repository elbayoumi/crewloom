"""Unit tests for crewloom_resources: path traversal defense, resource mapping, and distribution layout."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

# Ensure scripts directory is on sys.path for direct execution and discovery
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import crewloom_resources as resources


class TestCrewloomResourcesCheckout(unittest.TestCase):
    """Test resource resolution within a source repository checkout."""

    def test_layout_source_checkout(self):
        root, roles, doc, from_checkout = resources.layout()
        self.assertTrue(from_checkout)
        self.assertTrue(root.is_dir())
        self.assertTrue(roles.is_dir())
        self.assertTrue(doc.is_dir())
        self.assertTrue(resources.source_checkout())
        self.assertEqual(resources.distribution_root(), root)
        self.assertEqual(resources.roles_dir(), roles)
        self.assertEqual(resources.documentation_dir(), doc)

    def test_role_ids_discovery(self):
        roles = resources.role_ids()
        self.assertIsInstance(roles, list)
        self.assertGreater(len(roles), 0)
        self.assertEqual(roles, sorted(roles))
        self.assertIn("reverse-engineering-analyst", roles)

    def test_role_dir_valid(self):
        path = resources.role_dir("reverse-engineering-analyst")
        self.assertTrue(path.is_dir())
        self.assertTrue((path / "SKILL.md").is_file())

    def test_role_dir_invalid_rejected(self):
        for bad_id in ("", "../escape", "foo/bar", "foo\\bar", ".", "..", "nonexistent-role-xyz"):
            with self.subTest(bad_id=bad_id):
                with self.assertRaises(resources.ResourceError):
                    resources.role_dir(bad_id)

    def test_module_file_valid(self):
        path = resources.module_file("crewloom.py")
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "crewloom.py")

    def test_module_file_invalid_rejected(self):
        for bad_mod in ("crewloom.txt", "sub/module.py", "sub\\module.py", "../escape.py", "", "bad\0.py"):
            with self.subTest(bad_mod=bad_mod):
                with self.assertRaises(resources.ResourceError):
                    resources.module_file(bad_mod)

    def test_relative_parts_security(self):
        for bad_rel in (
            "/etc/passwd",
            "../secret",
            "foo/../../bar",
            "..\\secret",
            "foo\\..\\bar",
            "foo\0bar",
            "",
        ):
            with self.subTest(bad_rel=bad_rel):
                with self.assertRaises(resources.ResourceError):
                    resources._relative_parts(bad_rel)

    def test_resolve_routing(self):
        # 1. Scripts directory route
        script_path = resources.resolve("scripts/crewloom.py")
        self.assertTrue(script_path.is_file())
        self.assertEqual(script_path.parent, resources.MODULE_DIR)

        # 2. Roles directory route
        role_path = resources.resolve(".agents/skills/reverse-engineering-analyst/SKILL.md")
        self.assertTrue(role_path.is_file())

        # 3. Documentation directory route
        doc_path = resources.resolve("documentation/TOOLS.json")
        self.assertTrue(doc_path.is_file())

    def test_require_existing_and_missing(self):
        path = resources.require("documentation/TOOLS.json")
        self.assertTrue(path.is_file())

        with self.assertRaisesRegex(resources.ResourceError, "is not part of this installation"):
            resources.require("documentation/NONEXISTENT_FILE.json")

    def test_installed_roots(self):
        roots = resources.installed_roots()
        self.assertEqual(len(roots), 3)
        self.assertEqual(roots[0], resources.MODULE_DIR)
        self.assertEqual(roots[1], resources.roles_dir())
        self.assertEqual(roots[2], resources.documentation_dir())

    def test_dashboard_dir(self):
        dash = resources.dashboard_dir()
        self.assertTrue(dash.is_dir())
        self.assertTrue((dash / "package.json").is_file())


class TestCrewloomResourcesPackagedAndFallback(unittest.TestCase):
    """Test resource resolution under packaged installation and error states."""

    def test_packaged_root_fallback(self):
        with tempfile.TemporaryDirectory() as tmp_pkg:
            pkg_path = Path(tmp_pkg)
            skills = pkg_path / ".agents" / "skills"
            skills.mkdir(parents=True)
            doc = pkg_path / "documentation"
            doc.mkdir(parents=True)

            with patch("crewloom_resources._source_root", return_value=None), \
                 patch("crewloom_resources._packaged_root", return_value=pkg_path):
                root, roles, documentation, from_checkout = resources.layout()
                self.assertFalse(from_checkout)
                self.assertEqual(root, pkg_path)
                self.assertEqual(roles, skills)
                self.assertEqual(documentation, doc)
                self.assertFalse(resources.source_checkout())

    def test_missing_resources_raises_error(self):
        with patch("crewloom_resources._source_root", return_value=None), \
             patch("crewloom_resources._packaged_root", return_value=None):
            with self.assertRaises(resources.ResourceError) as ctx:
                resources.layout()
            self.assertIn("Crewloom resources are unavailable", str(ctx.exception))

    def test_dashboard_dir_missing_in_packaged_raises_error(self):
        with patch("crewloom_resources._source_root", return_value=None):
            with self.assertRaises(resources.ResourceError) as ctx:
                resources.dashboard_dir()
            self.assertIn("The dashboard is not bundled in the Python distribution", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
