"""Shared, bounded prerequisites for adapter examples; no framework SDK checks."""

import argparse
import shutil
import subprocess

IMAGE = "python:3.14-slim"


def execution_mode(argv=None):
    parser = argparse.ArgumentParser(description="Preview a Crewloom adapter without a framework SDK.")
    parser.add_argument("--require-execution", action="store_true",
                        help="Require Docker execution; fail if the daemon or local image is unavailable")
    requested = parser.parse_args(argv).require_execution
    if not requested:
        print("[SKIP] Container execution: preview mode. Use --require-execution to run supplied code.")
        print("[INFO] This adapter example does not verify an installed framework SDK.")
        return False
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is required for --require-execution; executable not found.")
    for arguments, label in ((["info"], "Docker daemon"),
                             (["image", "inspect", IMAGE], "Local image " + IMAGE)):
        try:
            result = subprocess.run([docker] + arguments, capture_output=True, timeout=10,
                                    check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(label + " prerequisite failed: " + str(exc)) from exc
        if result.returncode:
            raise RuntimeError(label + " unavailable; start Docker and pull " + IMAGE + " explicitly.")
    print("[INFO] Running supplied code through the adapter; no framework SDK is exercised.")
    return True
