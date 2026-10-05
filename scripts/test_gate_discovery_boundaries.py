"""Batching must preserve recursive discovery and discover newly added test modules."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import check_repository

class GateDiscoveryBoundaries(unittest.TestCase):
    def test_nested_package_tests_are_in_the_bounded_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            for suite in check_repository.suite_directories(root):suite.mkdir(parents=True)
            nested=root/'scripts'/'nested';nested.mkdir();(nested/'__init__.py').write_text('')
            module=nested/'test_new_nested.py';module.write_text('import unittest\n')
            planned={item[0] for item in check_repository.suite_plan(root)}
            self.assertIn(module,planned)

if __name__=='__main__':unittest.main()
