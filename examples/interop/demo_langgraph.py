#!/usr/bin/env python3
"""Preview the LangGraph-style state node; --require-execution requires real Docker.

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

from adapters.interop.langgraph_sandbox import create_crewloom_sandbox_node


def main(argv=None) -> int:
    try:
        execute = execution_mode(argv)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    print("=" * 60)
    print("Crewloom Interop Demo: LangGraph-style State Node")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        sandbox_node = create_crewloom_sandbox_node(
            workspace_root=workspace,
            image_id=IMAGE,
            timeout=15,
        )

        initial_state = {
            "task_id": "compute-hashes",
            "code": "import hashlib; print('SHA-256:', hashlib.sha256(b'crewloom').hexdigest()[:16])",
            "language": "python",
        }

        print("\n[+] Input State:")
        for k, v in initial_state.items():
            print(f"    {k}: {v}")

        if execute:
            print("\n[+] Invoking LangGraph sandbox node...")
            delta = sandbox_node(initial_state)
            res = delta["sandbox_result"]
            print(f"[+] Output:\n{res['output'].strip()}")
            print(f"[+] Exit Code: {res['exit_code']} | Duration: {res['duration_ms']}ms")
            print(f"[+] Security Badge: {res['isolation']}")
            if res["exit_code"] != 0:
                print(f"\n[!] LangGraph sandbox node failed with exit code {res['exit_code']}")
                return res["exit_code"]
        else:
            print("[PREVIEW] Adapter and input state constructed; execution and LangGraph SDK integration were skipped.")

    print("\n" + "=" * 60)
    print("Adapter example completed (exit code 0)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
