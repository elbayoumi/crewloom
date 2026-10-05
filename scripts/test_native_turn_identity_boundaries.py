"""Actual optional OpenCode message ID shape must still bind a concrete turn."""
import json
import unittest
import test_native_plugin_acceptance_boundaries as fixture

class NativeTurnIdentityBoundaries(unittest.TestCase):
    setUp=fixture.NativePluginBoundaries.setUp
    node=fixture.NativePluginBoundaries.node
    assert_refused=fixture.NativePluginBoundaries.assert_refused
    def test_output_user_message_identity_is_a_real_supported_turn(self):
        result=self.node("await hooks['chat.message']({sessionID:'s'},{message:{id:'actual-generated-turn',sessionID:'s'}}); const output={system:[]}; await hooks['experimental.chat.system.transform']({sessionID:'s'},output); console.log(JSON.stringify(output));")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['system'],['callback-only-marker'])
    def test_output_message_from_a_foreign_session_is_refused(self):
        self.assert_refused("await hooks['chat.message']({sessionID:'s'},{message:{id:'t',sessionID:'foreign'}});")
    def test_two_different_message_identities_are_refused(self):
        self.assert_refused("await hooks['chat.message']({sessionID:'s',messageID:'input-turn'},{message:{id:'output-turn',sessionID:'s'}});")

if __name__=='__main__':unittest.main()
