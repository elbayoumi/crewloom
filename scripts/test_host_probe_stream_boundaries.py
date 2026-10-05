"""A supported CLI may print successful help to stderr rather than stdout."""
import subprocess
import unittest
from unittest import mock
import model_host as host
class HostProbeStreamBoundaries(unittest.TestCase):
    def test_successful_stderr_help_is_supported_without_generation(self):
        help_text=' '.join(host.OPENCODE_REQUIRED_FLAGS)
        replies=[subprocess.CompletedProcess(['opencode'],0,'',help_text),subprocess.CompletedProcess(['opencode'],0,'1.18.32','')]
        with mock.patch.object(host.shutil,'which',return_value='/owned/opencode'), mock.patch.object(host.subprocess,'run',side_effect=replies):
            report=host.probe('opencode')
        self.assertTrue(report['generation_supported'])
        self.assertFalse(report['authentication_verified'])
    def test_failed_help_is_refused_even_when_it_mentions_every_flag(self):
        reply=subprocess.CompletedProcess(['opencode'],2,'',' '.join(host.OPENCODE_REQUIRED_FLAGS))
        with mock.patch.object(host.shutil,'which',return_value='/owned/opencode'), mock.patch.object(host.subprocess,'run',return_value=reply):
            with self.assertRaises(host.HostUnavailable):host.probe('opencode')
if __name__=='__main__':unittest.main()
