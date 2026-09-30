import importlib.util
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("quality", Path(__file__).with_name("check_ui_quality.py"))
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)


class QualityTests(unittest.TestCase):
    def audit(self, files):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name, content in files.items():
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
            return quality.audit(root)

    def test_empty_project_unmeasured(self):
        self.assertEqual(self.audit({})["state"], "unmeasured")

    def test_source_hints_never_certify_rendered_ui(self):
        result = self.audit({"page.html": '<button aria-label="Save" class="transition">Save</button><img alt="Logo"><style>@media (max-width:600px){}</style>'})
        self.assertEqual(result["state"], "unverified")
        self.assertTrue(result["browser_review_required"])

    def test_missing_responsive_rule_fails(self):
        self.assertIn("responsive", self.audit({"page.html": '<button aria-label="Save" class="transition">Save</button><img alt="Logo">'})["issues"][0])

    def test_interactive_without_accessibility_fails(self):
        self.assertTrue(any("accessible" in x for x in self.audit({"page.html": '<button>Save</button><style>@media (max-width:600px){}</style>'})["issues"]))

    def test_static_interaction_does_not_require_animation(self):
        self.assertFalse(any("transition" in x for x in self.audit({"page.html": '<button aria-label="Save">Save</button><style>@media (max-width:600px){}</style>'})["issues"]))

    def test_unused_comment_cannot_produce_acceptance(self):
        result = self.audit({"page.html": '<button>Save</button>',
                             "unused.css": '/* @media (min-width:1px){} aria-label= transition */'})
        self.assertEqual(result["state"], "unverified")

    def test_reduced_motion_does_not_prove_responsiveness(self):
        result = self.audit({"page.html": '<button>Save</button><style>@media (prefers-reduced-motion:reduce){}</style>'})
        self.assertTrue(any("responsive" in x for x in result["issues"]))

    def test_stylesheet_alone_is_unmeasured(self):
        self.assertEqual(self.audit({"style.css": 'button { color: blue; }'})["state"], "unmeasured")

    def test_cli_never_returns_success_for_hint_only_page(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "page.html").write_text('<button aria-label="Save" class="transition md:block">Save</button>')
            result = subprocess.run([sys.executable, quality.__file__, "--project-dir", d, "--json"],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertIn('"unverified"', result.stdout)

    def test_placeholder_fails(self):
        self.assertTrue(any("placeholder" in x for x in self.audit({"page.html": '<main>[TODO: add text]</main><style>@media (max-width:600px){}</style>'})["issues"]))

    def test_image_without_alt_fails(self):
        self.assertTrue(any("Image" in x for x in self.audit({"page.html": '<img src="logo.png"><style>@media (max-width:600px){}</style>'})["issues"]))

    def test_empty_button_fails(self):
        self.assertTrue(any("Empty button" in x for x in self.audit({"page.html": '<button></button><style>@media (max-width:600px){}</style>'})["issues"]))


if __name__ == "__main__":
    unittest.main()
