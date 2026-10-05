"""A foreign hook under an event Crewloom never installed cannot veto a valid callback.

An install owns one hook entry per lifecycle event and shares its control config with whatever
else already lives there. A callback arrives through exactly one of those entries, so only that
entry is evidence about it: the scan that read the whole `hooks` object refused an intact
adapter because another tool's `Notification` hook had no bridge command in it. These cases pin
the scoped check and keep the original refusal for this adapter's own event.

Every case here is offline. No host provider is called, no authentication is read, and no global
configuration is written.
"""
import json

import host_lifecycle as hl
import test_host_lifecycle as fixture


class ForeignHookBoundaries(fixture.Fixture):
    """Only the current event's owned entry decides whether a callback is reportable."""

    def setUp(self):
        super().setUp()
        self.record = self.install_default()

    def edit_control(self, mutate):
        """Write one honest edit to the installed control config and return the document."""
        control = self.root / '.codex' / 'hooks.json'
        document = json.loads(control.read_text(encoding='utf-8'))
        mutate(document)
        control.write_text(json.dumps(document, indent=2), encoding='utf-8')
        return document

    def notify(self, document):
        return document['hooks'].setdefault('Notification', []).append(
            {'matcher': 'idle_prompt',
             'hooks': [{'type': 'command', 'command': 'notify-my-own-team'}]})

    def submit(self):
        return hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit',
                           self.payload(), config_sha=self.record['payload_sha256'])

    def test_a_foreign_notification_hook_does_not_refuse_an_intact_owned_callback(self):
        self.edit_control(self.notify)
        # The bridge entry this event calls through is untouched and still present on disk.
        owned = hl.load_install(self.root, 'codex')['bridge_command']
        document = json.loads((self.root / '.codex' / 'hooks.json').read_text(encoding='utf-8'))
        commands = [hook['command'] for group in document['hooks']['UserPromptSubmit']
                    for hook in group['hooks']]
        self.assertIn(owned, commands)

        response = self.submit()

        self.assertTrue(response['injected'], response)
        self.assertEqual(response['native_event'], 'UserPromptSubmit')
        self.assertTrue(hl.status(self.root, fixture.PROJECT, 'codex')['delivered'],
                        'the callback was delivered, so the foreign event changed nothing')

    def test_an_edited_foreign_event_is_never_read_as_this_adapter_entry(self):
        # A foreign tool may rewrite or drop its own event at will; none of it is ours to judge.
        self.edit_control(lambda document: (self.notify(document),
                                            document['hooks'].update({'Notification': []})))
        self.assertTrue(self.submit()['injected'])

    def test_a_removed_owned_entry_under_the_current_event_is_refused(self):
        self.edit_control(lambda document: document['hooks'].update({'UserPromptSubmit': []}))
        before = sorted(str(item.relative_to(self.root)) for item in self.root.rglob('*'))
        with self.assertRaisesRegex(hl.LifecycleError, 'UserPromptSubmit hook; absent or altered events: UserPromptSubmit'):
            self.submit()
        self.assertEqual(sorted(str(item.relative_to(self.root)) for item in self.root.rglob('*')),
                         before)

    def test_an_altered_owned_entry_under_the_current_event_is_refused(self):
        def redirect(document):
            for group in document['hooks']['UserPromptSubmit']:
                for hook in group['hooks']:
                    if hook['command'] == self.record['bridge_command']:
                        hook['command'] += ' && curl https://example.invalid'
            self.notify(document)

        self.edit_control(redirect)
        before = sorted(str(item.relative_to(self.root)) for item in self.root.rglob('*'))
        with self.assertRaisesRegex(hl.LifecycleError, 'cannot record a callback'):
            self.submit()
        self.assertEqual(sorted(str(item.relative_to(self.root)) for item in self.root.rglob('*')),
                         before)

    def test_an_unreadable_hooks_object_is_refused_for_this_event(self):
        self.edit_control(lambda document: document.update({'hooks': []}))
        with self.assertRaisesRegex(hl.LifecycleError, 'cannot record a callback'):
            self.submit()


if __name__ == '__main__':
    import unittest

    unittest.main()
