"""Native host tool payloads must support real edits and real checkpoints."""
import unittest
import host_lifecycle as hl
import test_host_lifecycle as fixture

class NativeToolPayloadBoundaries(fixture.Fixture):
    def setUp(self):
        super().setUp()
        self.record=self.install(outputs=(fixture.SOURCE_FILE,))
        hl.callback(self.root,fixture.PROJECT,'codex','UserPromptSubmit',self.payload())
    def native(self,native_tool,native_args,**extra):
        return self.payload(tool_name=native_tool,tool_input=native_args,**extra)
    def test_actual_codex_patch_payload_allows_declared_source(self):
        patch='*** Begin Patch\n*** Update File: '+fixture.SOURCE_FILE+'\n@@\n-    return user\n+    return str(user)\n*** End Patch'
        response=hl.callback(self.root,fixture.PROJECT,'codex','PreToolUse',self.native('apply_patch',{'command':patch}))
        self.assertEqual(response['permissionDecision'],'allow',response)
    def test_native_patch_of_host_authority_is_denied(self):
        patch='*** Begin Patch\n*** Add File: .codex/disable.json\n+{}\n*** End Patch'
        response=hl.callback(self.root,fixture.PROJECT,'codex','PreToolUse',self.native('apply_patch',{'command':patch}))
        self.assertEqual(response['permissionDecision'],'deny')
    def test_conflicting_native_and_normalized_tool_names_are_denied(self):
        response=hl.callback(self.root,fixture.PROJECT,'codex','PreToolUse',self.native('unknown-tool',{},tool='edit',args={'filePath':fixture.SOURCE_FILE}))
        self.assertEqual(response['permissionDecision'],'deny')
    def test_post_tool_payload_invalidates_the_actual_declared_edit(self):
        (self.root/fixture.SOURCE_FILE).write_text('def login(user):\n    return str(user)\n')
        response=hl.callback(self.root,fixture.PROJECT,'codex','PostToolUse',self.native('apply_patch',{'command':'*** Begin Patch\n*** Update File: '+fixture.SOURCE_FILE+'\n@@\n+changed\n*** End Patch'}))
        self.assertEqual(response['declared_changes'],[fixture.SOURCE_FILE])
        self.assertTrue(response['invalidated'])

if __name__=='__main__':unittest.main()
