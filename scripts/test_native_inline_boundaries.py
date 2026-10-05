"""The production native launcher must emit the actually supported inline hook shape."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import host_lifecycle

class NativeInlineBoundaries(unittest.TestCase):
    def test_one_hook_matches_the_observed_native_schema(self):
        actual=host_lifecycle._inline_group([{'hooks':[{'type':'command','command':'safe',
            'timeout':3,'additionalContextLimit':200}]}])
        self.assertEqual(actual,'[{hooks=[{type="command",command="safe",timeout=3,additionalContextLimit=200}]}]')

if __name__=='__main__':unittest.main()
