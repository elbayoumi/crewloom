"""Regressions for complete instructions and honest source coverage."""
import tempfile
import unittest
from pathlib import Path

from context_pack import BUDGET, SOURCES, build_pack


class PackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        for rel in SOURCES:
            path = self.base / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"Instructions for {rel}\nFINAL REQUIRED RULE", encoding="utf-8")

    def test_complete_sources_keep_final_rule(self):
        pack = build_pack(self.base)
        self.assertEqual(pack.count("FINAL REQUIRED RULE"), 3)
        self.assertLessEqual(len(pack), BUDGET)

    def test_large_skill_is_referred_not_chopped(self):
        source = "START\n" + "x" * 9000 + "\nCRITICAL STOP RULE"
        (self.base / "SKILL.md").write_text(source)
        pack = build_pack(self.base)
        self.assertIn(str(self.base / "SKILL.md"), pack)
        self.assertIn("Read entire source before execution", pack)
        self.assertNotIn("START", pack)
        self.assertLessEqual(len(pack), BUDGET)

    def test_rule_after_old_3000_limit_is_preserved(self):
        source = "x" * 3200 + "\nCRITICAL STOP RULE"
        (self.base / "SKILL.md").write_text(source)
        self.assertIn(source, build_pack(self.base))

    def test_missing_skill_fails(self):
        (self.base / "SKILL.md").unlink()
        with self.assertRaises(ValueError):
            build_pack(self.base)

    def test_missing_brain_fails(self):
        (self.base / SOURCES[1]).unlink()
        with self.assertRaises(ValueError):
            build_pack(self.base)

    def test_impossible_budget_fails(self):
        with self.assertRaises(ValueError):
            build_pack(self.base, budget=1)

    def test_arabic_pack_and_invalid_language(self):
        self.assertIn("# حزمة السياق", build_pack(self.base, language="ar"))
        with self.assertRaises(ValueError):
            build_pack(self.base, language="unsupported")

    def test_relative_links_rebased_to_output(self):
        import re
        (self.base / "SKILL.md").write_text(
            "See [tree](../other/references/tree.md) and [frag](#rules) and [root](/abs/path.md).\nFINAL REQUIRED RULE",
            encoding="utf-8")
        out = Path(self.temp.name) / "elsewhere" / "pack.md"
        pack = build_pack(self.base, output=out)
        targets = dict(re.findall(r"\[([^\]]*)\]\(([^)\s]+)\)", pack))
        self.assertIn("#rules", targets.values())
        self.assertIn("/abs/path.md", targets.values())
        self.assertNotIn("../other/references/tree.md", targets.values())
        resolved = (out.parent / targets["tree"]).resolve()
        self.assertEqual(resolved, (self.base.parent / "other" / "references" / "tree.md").resolve())


if __name__ == "__main__":
    unittest.main()
