"""Optional stdio MCP bridge bound to one project, checkout and task at launch.

Core installation remains dependency-free. Install the `mcp` extra on Python
3.11+ to use the official SDK. No tool accepts a project root, command or plan.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import project_binding as pb
import project_context as pc
import workflow as w


class Bridge:
    """One immutable launch scope; revalidate local authority before every call."""

    def __init__(self, project, project_id, task_id, plan=None, allow_import=False,
                 allow_verify=False, image=w.DEFAULT_IMAGE, allow_context_update=False):
        path = Path(project)
        if not path.is_absolute() or path.resolve(strict=True) != path:
            raise ValueError('MCP requires an absolute canonical project root without symlinks')
        self.root = pb.project_root(str(path))
        self.identity = (path.stat().st_dev, path.stat().st_ino)
        if not isinstance(task_id, str) or not w.ID.fullmatch(task_id):
            raise ValueError('MCP needs a stable kebab-case task ID')
        self.task_id = task_id
        self.binding = pb.load_binding(self.root)
        self.config, _ = pb.load_config(self.root)
        if self.binding['project_id'] != project_id:
            raise ValueError('MCP project identity does not match the bound checkout')
        if not self.config or self.config['project_id'] != project_id:
            raise ValueError('MCP portable project identity does not match the bound checkout')
        pb.catalog_guard(self.root, project_id)
        self.plan_file = plan
        self.plan = self.fingerprint = None
        if plan is not None:
            self.plan, self.fingerprint = w.read_plan(self.root, plan)
            if self.plan['id'] != task_id:
                raise ValueError('MCP plan ID must match the selected task ID')
            if any(step.get('kind') == 'model' for step in self.plan['steps']):
                raise ValueError('MCP task bridge does not dispatch model hosts; use task and command steps')
        if (allow_import or allow_verify) and self.plan is None:
            raise ValueError('MCP write tools require one explicit reviewed workflow plan')
        self.allow_import = allow_import
        self.allow_verify = allow_verify
        self.allow_context_update = allow_context_update
        self.image = image

    def guard(self):
        path = self.root
        if path.resolve(strict=True) != path or (path.stat().st_dev, path.stat().st_ino) != self.identity:
            raise ValueError('MCP project root changed since launch')
        if pb.load_binding(path) != self.binding:
            raise ValueError('MCP checkout binding changed; restart with a reviewed scope')
        if pb.load_config(path)[0] != self.config:
            raise ValueError('MCP project policy changed; restart with a reviewed scope')
        pb.catalog_guard(path, self.binding['project_id'])
        active = pb.reservation(path)
        if active and active['task_id'] != self.task_id:
            raise ValueError('MCP cannot access another active project task')
        active_workflow = w.active_workflow(path)
        if active_workflow and active_workflow['workflow'] != self.task_id:
            raise ValueError('MCP cannot access another active workflow')
        if self.plan is not None:
            plan, fingerprint = w.read_plan(path, self.plan_file)
            if fingerprint != self.fingerprint or plan != self.plan:
                raise ValueError('MCP plan changed since launch; restart with a reviewed plan')

    def status(self) -> Dict[str, Any]:
        self.guard()
        value = pb.status(self.root, self.binding['project_id'])
        value['tasks'] = [task for task in value['tasks'] if task['task_id'] == self.task_id]
        return {**value, 'task_id': self.task_id, 'transport': 'stdio',
                'capabilities': {'import_reply': self.allow_import, 'verify': self.allow_verify,
                                 'answer_question': self.allow_context_update,
                                 'desktop_control': False, 'model_generation': False}}

    def context(self) -> Dict[str, Any]:
        self.guard()
        value = pc.require_fresh(self.root, self.binding, self.task_id)
        if len(json.dumps(value, ensure_ascii=False).encode()) > 1024 * 1024:
            raise ValueError('MCP frozen context byte budget exceeded')
        return value

    def packet(self) -> Dict[str, Any]:
        self.guard()
        if self.plan is None:
            raise ValueError('No workflow plan selected for this MCP session')
        # state_for creates state when missing; read-only MCP must never bootstrap it.
        path = w.safe_path(self.root, '.crewloom/workflows/' + self.task_id + '/state.json', internal=True)
        if not path.is_file():
            raise ValueError('Start the selected workflow through the CLI before requesting a packet')
        return w.agent_packet(self.root, self.plan, self.fingerprint)

    def questions(self) -> Dict[str, Any]:
        self.guard()
        import user_context
        return user_context.capture_status(self.root, self.task_id)

    def answer(self, question_id, source, quote) -> Dict[str, Any]:
        if not self.allow_context_update:
            raise ValueError('Question answers require explicit --allow-context-update at launch')
        self.guard()
        import user_context
        return user_context.answer_question(self.root, self.task_id, question_id, source, quote)

    def import_candidate(self, packet, response) -> Dict[str, Any]:
        if not self.allow_import:
            raise ValueError('Reply import is disabled; explicit --allow-import at launch is required')
        self.guard()
        return w.import_reply(self.root, self.plan, self.fingerprint, packet, response)

    def verify(self) -> Dict[str, Any]:
        if not self.allow_verify:
            raise ValueError('Command verification is disabled; explicit --allow-verify at launch is required')
        self.guard()
        # `run` stops at awaiting tasks. It cannot accept a task, register a reviewer,
        # change its fixed plan, enable native CLI generation or bypass Docker.
        return w.run(self.root, self.plan, self.fingerprint, self.image)


def server(bridge):
    try:
        from mcp.server import MCPServer
        from mcp import types
        from mcp.server.mcpserver.exceptions import ToolError
    except ImportError as exc:
        raise ValueError('Install crewloom[mcp] with Python 3.11+ to use the optional MCP bridge') from exc
    mcp = MCPServer('Crewloom project task')
    read = types.ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = types.ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

    def invoke(method, *args):
        try:
            return method(*args)
        except (ValueError, OSError) as exc:
            raise ToolError(str(exc)) from None

    @mcp.tool(annotations=read)
    def crewloom_status() -> dict[str, Any]:
        """Inspect only the project, checkout and task bound to this server."""
        return invoke(bridge.status)

    @mcp.tool(annotations=read)
    def crewloom_context() -> dict[str, Any]:
        """Read the selected task's frozen context; stale or foreign context is refused."""
        return invoke(bridge.context)

    @mcp.tool(annotations=read)
    def crewloom_questions() -> dict[str, Any]:
        """Read this task's capture status and unresolved source-linked clarification questions."""
        return invoke(bridge.questions)

    if bridge.plan is not None:
        @mcp.tool(annotations=read)
        def crewloom_task_packet() -> dict[str, Any]:
            """Read the next awaiting task's prompt/schema; grants no write or acceptance permission."""
            return invoke(bridge.packet)

    if bridge.allow_context_update:
        @mcp.tool(annotations=write)
        def crewloom_answer(question_id: str, source: str, quote: str) -> dict[str, Any]:
            """Resolve one question using an exact quote from a later captured user message."""
            return invoke(bridge.answer, question_id, source, quote)

    if bridge.allow_import:
        @mcp.tool(annotations=write)
        def crewloom_import_reply(packet: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
            """Import declared candidate files from a fresh packet. Review and tests remain required."""
            return invoke(bridge.import_candidate, packet, response)

    if bridge.allow_verify:
        @mcp.tool(annotations=write)
        def crewloom_verify() -> dict[str, Any]:
            """Run this fixed plan's pending commands in Docker; stops at tasks awaiting review."""
            return invoke(bridge.verify)
    return mcp


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--project-id', required=True)
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--plan')
    parser.add_argument('--allow-import', action='store_true')
    parser.add_argument('--allow-verify', action='store_true')
    parser.add_argument('--allow-context-update', action='store_true')
    parser.add_argument('--image', default=w.DEFAULT_IMAGE)
    args = parser.parse_args(argv)
    try:
        bridge = Bridge(args.project, args.project_id, args.task_id, args.plan,
                        args.allow_import, args.allow_verify, args.image, args.allow_context_update)
        server(bridge).run(transport='stdio')
        return 0
    except (ValueError, OSError) as exc:
        # stdout belongs exclusively to JSON-RPC.
        print('Crewloom MCP: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
