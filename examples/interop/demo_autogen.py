#!/usr/bin/env python3
"""Preview the AutoGen-style executor; --require-execution requires real Docker.

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

from adapters.interop.autogen_sandbox import (
    CodeBlock,
    CrewloomAutoGenExecutor,
    extract_code_blocks,
)


def main(argv=None) -> int:
    try:
        execute = execution_mode(argv)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    print("=" * 60)
    print("Crewloom Interop Demo: Microsoft AutoGen Rootless CodeExecutor")
    print("=" * 60)

    markdown_sample = """Here is the solution to compute Fibonacci numbers:
```python
def fib(n):
    return n if n <= 1 else fib(n-1) + fib(n-2)
print("Fibonacci(10) =", fib(10))
```
"""

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        executor = CrewloomAutoGenExecutor(
            workspace_root=workspace,
            image_id=IMAGE,
            timeout=15,
        )

        blocks = extract_code_blocks(markdown_sample)
        print(f"\n[+] Extracted Code Blocks: {len(blocks)}")
        for idx, block in enumerate(blocks):
            print(f"    Block {idx+1} ({block.language}):\n{block.code}")

        if execute:
            print("\n[+] Executing code blocks through AutoGen CodeExecutor...")
            res = executor.execute_code_blocks(blocks)
            print(f"[+] Exit Code: {res.exit_code}")
            print(f"[+] Output:\n{res.output.strip()}")
            if res.exit_code != 0:
                print(f"\n[!] AutoGen CodeExecutor failed with exit code {res.exit_code}")
                return res.exit_code
        else:
            print("[PREVIEW] Code fences parsed; execution and AutoGen SDK integration were skipped.")

    print("\n" + "=" * 60)
    print("Adapter example completed (exit code 0)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
