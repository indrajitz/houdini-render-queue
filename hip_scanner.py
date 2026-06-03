"""
hip_scanner.py — Runs scan_hip.py via hython and returns a list of ROP dicts.

Each dict has keys:
    path, type, label, frame_start, frame_end, frame_step, output_path
"""

import json
import os
import subprocess

_SCAN_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scan_hip.py")


def scan_hip_rops(hip_file: str, hython: str = "hython", timeout: int = 60) -> list:
    """
    Return list of ROP info dicts for the given .hip file.
    Raises RuntimeError on failure.
    """
    try:
        result = subprocess.run(
            [hython, _SCAN_SCRIPT, "--hip", hip_file],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise RuntimeError(f"hython not found at: {hython}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("ROP scan timed out after 60 s. Is hython working?")

    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                return data.get("rops", [])
            except json.JSONDecodeError:
                continue

    stderr = result.stderr.strip()
    if result.returncode != 0:
        raise RuntimeError(stderr[:600] if stderr else f"hython exited {result.returncode}")

    return []
