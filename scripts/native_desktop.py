"""Optional native AX button controller with an immutable project/task/app scope.

Connects only to an explicit private CuaDriver socket. It never starts a daemon,
requests TCC grants, fronts an app, uses coordinates, types text or executes shell.
"""
import argparse
import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import project_binding as pb
import workflow as w
import privacy
import project_lessons as pl

DRIVER = '/Applications/CuaDriver.app/Contents/MacOS/cua-driver'
TOOLS = ['check_permissions', 'list_windows', 'get_window_state', 'click']


def private_file(root, relative):
    path = w.safe_path(root, relative, internal=True)
    stat = path.stat()
    if not path.is_file() or stat.st_nlink != 1 or stat.st_size > 32768:
        raise ValueError('Native policy must be a bounded regular single-link file')
    if os.name == 'posix' and (stat.st_mode & 0o077 or stat.st_uid != os.getuid()):
        raise ValueError('Native policy must be owner-only')
    return path


def prepare(project, project_id, task_id, bundle_id=None, window_title=None, buttons=None, read_only=False):
    """Prepare one explicit app/window; this does not approve or launch it."""
    root = pb.project_root(project)
    binding = pb.load_binding(root)
    if binding['project_id'] != project_id or not isinstance(task_id, str) or not w.ID.fullmatch(task_id):
        raise ValueError('Native preparation needs the bound project and stable task')
    pb.preflight_ownership(root, task_id)
    custom = bundle_id is not None or window_title is not None or buttons is not None or read_only
    if not custom:
        bundle_id, window_title, buttons = 'com.crewloom.NativeFixture', 'Crewloom Native Acceptance', ['Increment', 'Reset']
    if (not isinstance(bundle_id, str) or len(bundle_id) > 200
            or not re.fullmatch(r'(?:[A-Za-z0-9][A-Za-z0-9-]*\.)+[A-Za-z0-9][A-Za-z0-9-]*', bundle_id)
            or not isinstance(window_title, str) or not window_title.strip() or len(window_title) > 200
            or any(ord(c) < 32 for c in window_title)):
        raise ValueError('Custom native scope requires an exact bundle ID and window title')
    buttons = [] if buttons is None else buttons
    if (type(read_only) is not bool or not isinstance(buttons, list)
            or not (0 if read_only else 1) <= len(buttons) <= (0 if read_only else 16)
            or any(not isinstance(b, str) or not b.strip() or len(b) > 100 or any(ord(c) < 32 for c in b) for b in buttons)
            or len(set(buttons)) != len(buttons)):
        raise ValueError('Choose explicit unique buttons or an empty read-only scope')
    directory = '.crewloom/private/native/' + w.digest(task_id.encode())[:8]
    socket_path = str(w.safe_path(root, directory + '/driver.sock', internal=True))
    if len(socket_path.encode()) >= 104:
        raise ValueError('Private native socket path exceeds the macOS Unix socket limit')
    manifest = ('version: 3\nexpires_after: 1h\nidle_timeout: 10m\nallow:\n  tools: '
                + json.dumps([tool for tool in TOOLS if tool != 'click' or not read_only])
                + '\nresources:\n  apps:\n    - bundle_id: ' + bundle_id + '\n'
                '      launch: false\n      windows: all\n  desktop:\n    display: false\n')
    policy = {'schema_version': 1, 'scope': dict(binding, task_id=task_id), 'driver': DRIVER,
              'socket': socket_path, 'manifest': directory + '/capabilities.yaml',
              'manifest_sha256': w.digest(manifest.encode()),
              'bundle_id': bundle_id, 'window_title': window_title,
              'allowed_buttons': buttons, 'read_only': read_only}
    with w.project_lock(w.safe_path(root, '.crewloom', internal=True), reentrant=True):
        pb.preflight_ownership(root, task_id)
        for name in ('capabilities.yaml', 'policy.json'):
            if w.safe_path(root, directory + '/' + name, internal=True).exists():
                raise ValueError('Existing native policy must be reviewed; it cannot be overwritten')
        privacy.private_write(root, policy['manifest'], manifest)
        privacy.private_write(root, directory + '/policy.json', pl.canonical(policy) + '\n')
    return {'policy': directory + '/policy.json', 'manifest': str(root / policy['manifest']),
            'sha256': policy['manifest_sha256'], 'socket': socket_path,
            'status': 'prepared-not-approved', 'task_id': task_id}


class Controller:
    def __init__(self, project, project_id, task_id, policy_file, client, pid=None):
        self.root = pb.project_root(project)
        self.binding = pb.load_binding(self.root)
        self.task_id = task_id
        if self.binding['project_id'] != project_id or not isinstance(task_id, str) or not w.ID.fullmatch(task_id):
            raise ValueError('Native controller project/task mismatch')
        expected = '.crewloom/private/native/' + w.digest(task_id.encode())[:8] + '/policy.json'
        if policy_file != expected:
            raise ValueError('Native policy must belong to the selected project/task')
        self.policy_file = private_file(self.root, policy_file)
        self.policy_bytes = self.policy_file.read_bytes()
        self.policy = json.loads(self.policy_bytes)
        p = self.policy
        if (p.get('schema_version') != 1 or p.get('scope') != dict(self.binding, task_id=task_id)
                or p.get('driver') != DRIVER or not isinstance(p.get('allowed_buttons'), list)
                or type(p.get('read_only', False)) is not bool
                or not (0 if p.get('read_only') else 1) <= len(p['allowed_buttons']) <= (0 if p.get('read_only') else 16)
                or any(not isinstance(b, str) or not b.strip() or len(b) > 100 for b in p['allowed_buttons'])
                or len(set(p['allowed_buttons'])) != len(p['allowed_buttons'])
                or not isinstance(p.get('bundle_id'), str) or not p['bundle_id']
                or not isinstance(p.get('window_title'), str) or not p['window_title']):
            raise ValueError('Native policy shape or immutable scope is invalid')
        self.manifest_file = private_file(self.root, p['manifest'])
        socket_path = w.safe_path(self.root, str(Path(p['socket']).relative_to(self.root)), internal=True)
        if socket_path.parent != self.policy_file.parent or socket_path.name != 'driver.sock':
            raise ValueError('Native socket must stay beside the selected private policy')
        if type(pid) is not int or not 0 < pid <= 2147483647:
            raise ValueError('Native serving requires an explicit positive observed app PID')
        self.pid = pid
        self.client = client
        self.tokens = {}
        self.observation = 0
        self.lock = None
        self.loop = None
        self.guard()

    def operation_lock(self):
        # Python 3.9 binds locks at construction, unlike newer runtimes. A
        # synchronous constructor must not allocate an implicit event loop.
        loop = asyncio.get_running_loop()
        if self.lock is None:
            self.loop = loop
            self.lock = asyncio.Lock()
        elif self.loop is not loop:
            raise ValueError('Native controller cannot move to another event loop')
        return self.lock

    def guard(self):
        if (pb.load_binding(self.root) != self.binding or self.policy_file.read_bytes() != self.policy_bytes
                or self.manifest_file.read_bytes() == b''
                or w.digest(self.manifest_file.read_bytes()) != self.policy['manifest_sha256']):
            raise ValueError('Native project, policy or manifest changed since launch')
        private_file(self.root, str(self.policy_file.relative_to(self.root)))
        private_file(self.root, str(self.manifest_file.relative_to(self.root)))
        pb.preflight_ownership(self.root, self.task_id)

    async def call(self, name, args):
        self.guard()
        try:
            result = await self.client.call_tool(name, args)
        except Exception as exc:
            raise ValueError('Native transport failed during ' + name + '; no automatic retry') from exc
        if result.is_error:
            raise ValueError('Native driver refused ' + name)
        value = result.structured_content
        if not isinstance(value, dict):
            raise ValueError('Native driver returned no structured result for ' + name)
        return value

    async def target(self):
        permissions = await self.call('check_permissions', {'prompt': False})
        if permissions.get('accessibility') is not True:
            raise ValueError('Accessibility permission is missing; human setup is required')
        # Global list_apps requires desktop observation, which the reviewed
        # manifest intentionally denies. The trusted launcher supplies the
        # observed PID; the bounded driver checks its actual bundle before
        # listing any window. Never discover a replacement PID automatically.
        pid = self.pid
        windows = (await self.call('list_windows', {'pid': pid})).get('windows')
        if not isinstance(windows, list): raise ValueError('Native window inventory is malformed')
        matches = [window for window in windows if window.get('pid') == pid and window.get('title') == self.policy['window_title']]
        if len(matches) != 1 or type(matches[0].get('window_id')) is not int:
            raise ValueError('Exactly one allowed app window must be observed')
        return pid, matches[0]['window_id']

    async def snapshot(self):
        async with self.operation_lock():
            return await self._snapshot()

    async def _snapshot(self):
        self.tokens = {}  # A failed refresh also invalidates previous handles.
        pid, window = await self.target()
        value = await self.call('get_window_state', {'pid': pid, 'window_id': window,
            'include_screenshot': False, 'max_elements': 200, 'max_depth': 12})
        if not isinstance(value.get('elements'), list): raise ValueError('Native AX inventory is malformed')
        if (value.get('pid') != pid or value.get('window_id') != window
                or value.get('window_title') != self.policy['window_title']):
            raise ValueError('Native snapshot identity differs from the requested window')
        # CuaDriver also includes the app menu bar and indexes only actionable
        # rows. Restrict structured rows to the actual window ancestry, and
        # retain its Markdown text so non-actionable labels remain observable.
        rows = value['elements']
        if any(not isinstance(row, dict) or type(row.get('element_index')) is not int for row in rows):
            raise ValueError('Native AX row identity is malformed')
        indices = {row['element_index'] for row in rows}
        if len(indices) != len(rows): raise ValueError('Native AX row identities are ambiguous')
        windows = [row for row in rows if row.get('role') == 'AXWindow'
                   and row.get('label') == self.policy['window_title']]
        if len(windows) != 1: raise ValueError('Native snapshot lacks one exact window root')
        window_index = windows[0]['element_index']
        selected = {window_index}
        for _ in rows:
            children = {row['element_index'] for row in rows if row.get('parent_index') in selected}
            if children <= selected: break
            selected.update(children)
        elements = [row for row in rows if row['element_index'] in selected]
        lines = value.get('tree_markdown', '').splitlines()
        starts = [i for i, line in enumerate(lines) if re.match(r'^- \[' + str(window_index) + r'\] AXWindow(?:\s|$)', line)]
        if len(starts) != 1: raise ValueError('Native window text is unavailable or ambiguous')
        start = starts[0]
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('- ')), len(lines))
        if end == len(lines) and value.get('elements_complete') is not True:
            raise ValueError('Native window observation may be truncated')
        window_text = '\n'.join(lines[start:end])
        self.observation += 1
        buttons = []
        for element in elements:
            label = element.get('label')
            token = element.get('element_token')
            if (label in self.policy['allowed_buttons'] and element.get('role') == 'AXButton'
                    and element.get('enabled') is True
                    and 'AXPress' in element.get('actions', []) and isinstance(token, str) and token):
                handle = str(self.observation) + '-' + w.digest(token.encode())[:20]
                self.tokens[handle] = (pid, window, token, label)
                buttons.append({'handle': handle, 'label': label})
        # Only this exact allowed window is returned; no screenshot or global app inventory.
        return {'observation': self.observation, 'pid': pid, 'window_id': window, 'buttons': buttons,
                'elements': [{k: v for k, v in element.items() if k != 'element_token'} for element in elements],
                'window_text': window_text, 'scope': dict(self.binding, task_id=self.task_id)}

    async def click(self, handle):
        async with self.operation_lock():
            return await self._click(handle)

    async def _click(self, handle):
        if self.policy.get('read_only'):
            raise ValueError('This native policy permits observation only')
        selected = self.tokens.pop(handle, None) if isinstance(handle, str) else None
        self.tokens = {}  # All handles are one-use; uncertainty never causes an automatic retry.
        if selected is None: raise ValueError('Native handle is unknown, stale or already used')
        pid, window, token, label = selected
        if await self.target() != (pid, window): raise ValueError('Native app/window identity changed')
        self.guard()
        import user_context
        user_context.select(self.root, self.task_id)
        audit_path = '.crewloom/private/native/' + w.digest(self.task_id.encode())[:8] + '/actions/' + uuid.uuid4().hex + '.json'
        audit = {'task_id': self.task_id, 'pid': pid, 'window_id': window, 'label': label,
                 'at': pl.now(), 'status': 'attempting-background-AX', 'verified': False}
        privacy.private_write(self.root, audit_path, pl.canonical(audit) + '\n')
        try:
            await self.call('click', {'pid': pid, 'window_id': window, 'element_token': token, 'delivery_mode': 'background'})
            after = await self._snapshot()
        except (ValueError, OSError):
            audit['status'] = 'uncertain-or-refused-no-retry'
            privacy.private_write(self.root, audit_path, pl.canonical(audit) + '\n')
            raise
        audit['status'] = 'delivered-and-reobserved'
        privacy.private_write(self.root, audit_path, pl.canonical(audit) + '\n')
        after['action'] = {'label': label, 'delivered': True, 'postcondition_verified': False}
        # The fresh observation is evidence; generic delivery alone cannot prove the user's goal.
        return after


async def serve(args):
    from mcp import Client, types
    from mcp.client.stdio import StdioServerParameters
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    root = pb.project_root(args.project)
    controller = Controller(args.project, args.project_id, args.task_id, args.policy, None, args.pid)
    p = controller.policy
    sock = w.safe_path(root, str(Path(p['socket']).relative_to(root)), internal=True)
    import stat
    st = sock.stat()
    if not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.getuid():
        raise ValueError('Native driver needs an existing owner-controlled private socket; no fallback or autostart')
    params = StdioServerParameters(command=DRIVER, args=['mcp', '--embedded', '--socket', str(sock)], cwd=str(root))
    async with Client(params, mode='legacy') as client:
        controller.client = client
        controller.guard()
        mcp = MCPServer('Crewloom scoped native AX')
        @mcp.tool(annotations=types.ToolAnnotations(readOnlyHint=True, openWorldHint=False))
        async def crewloom_native_snapshot() -> dict[str, Any]:
            """Observe only the exact app/window in the reviewed launch policy."""
            try: return await controller.snapshot()
            except (ValueError, OSError) as exc: raise ToolError(str(exc)) from None
        if not p.get('read_only'):
            @mcp.tool(annotations=types.ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
            async def crewloom_native_click(handle: str) -> dict[str, Any]:
                """Press one allowed AX button from the latest observation, then observe again."""
                try: return await controller.click(handle)
                except (ValueError, OSError) as exc: raise ToolError(str(exc)) from None
        await mcp.run_stdio_async()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'serve'])
    parser.add_argument('--project', required=True)
    parser.add_argument('--project-id', required=True)
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--policy')
    parser.add_argument('--bundle-id', help='Prepare: exact target app bundle ID')
    parser.add_argument('--window-title', help='Prepare: exact target window title')
    parser.add_argument('--button', action='append', help='Prepare: explicit AX button label; repeat as needed')
    parser.add_argument('--read-only', action='store_true', help='Prepare: observation only, without a click tool')
    parser.add_argument('--pid', type=int, help='Observed allowed-app process fixed for this server; required for serve')
    args = parser.parse_args(argv)
    try:
        if args.action == 'prepare': print(json.dumps(prepare(args.project, args.project_id, args.task_id,
            args.bundle_id, args.window_title, args.button, args.read_only)))
        else:
            if args.bundle_id is not None or args.window_title is not None or args.button is not None or args.read_only:
                raise ValueError('Serving cannot change a prepared target scope')
            if not args.policy: raise ValueError('Serving requires one reviewed private policy')
            asyncio.run(serve(args))
        return 0
    except (ValueError, OSError, ImportError) as exc:
        import sys
        print('Crewloom native: ' + str(exc), file=sys.stderr); return 2


if __name__ == '__main__': raise SystemExit(main())
