#!/usr/bin/env python3
"""Preview the CrewAI-style tool; --require-execution requires real Docker.

No framework SDK or model is constructed by this adapter example.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

# Add repo root to sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

if __package__:
    from .demo_runtime import IMAGE, execution_mode
else:
    from demo_runtime import IMAGE, execution_mode

from adapters.interop.crewai_sandbox import CrewloomSandboxTool, build_sandbox_command


def main(argv=None) -> int:
    try:
        execute = execution_mode(argv)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    print("=" * 60)
    print("Crewloom Interop Demo: CrewAI-style Container Tool")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        (workspace / "out").mkdir()

        tool = CrewloomSandboxTool(
            workspace_root=workspace,
            image_id=IMAGE,
            timeout=15,
            writable=["out/"],
        )

        print(f"\n[+] Tool Name: {tool.name}")
        print(f"[+] Tool Protocol (.func callable): {callable(tool.func)}")
        print(f"[+] Workspace Root: {workspace}")
        print(f"[+] Writable Boundaries: {tool.writable}")

        cmd = build_sandbox_command(workspace, ["python3", "-c", "print('hello')"], writable=tool.writable)
        print("\n[+] Hardened Docker argv generated:")
        for idx, arg in enumerate(cmd[:12]):
            print(f"    [{idx:02d}] {arg}")
        print("    ... (and remaining mounts & flags)")

        code = "print('Factorial of 10 is:', __import__('math').factorial(10))"

        if execute:
            print(f"\n[+] Executing Python snippet in sandbox: {code}")
            result = tool.execute(code, language="python")
            print(f"[+] Exit Code: {result['exit_code']}")
            print(f"[+] Output:\n{result['output'].strip()}")
            print(f"[+] Duration: {result['duration_ms']}ms | Isolation: {result['isolation']}")
            if result["exit_code"] != 0:
                print(f"\n[!] Sandbox execution failed with exit code {result['exit_code']}")
                return result["exit_code"]
        else:
            print("[PREVIEW] Docker command constructed; execution and CrewAI SDK integration were skipped.")

    print("\n" + "=" * 60)
    print("Adapter example completed (exit code 0)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
