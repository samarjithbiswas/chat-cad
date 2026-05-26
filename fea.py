"""Thin wrapper that invokes fea_worker.py as a subprocess.

gmsh's signal handlers require the main thread of an interpreter. Flask
serves requests on worker threads, so gmsh fails if called in-process.
Running the work in a subprocess sidesteps the problem.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


def run_fea(stl_path: str, load_N: float = 100.0, axis: str = "Z",
            material: str = "aluminum") -> dict:
    if not os.path.exists(stl_path):
        return {"error": f"STL not found at {stl_path}"}
    here = os.path.dirname(os.path.abspath(__file__))
    worker = os.path.join(here, "fea_worker.py")
    try:
        proc = subprocess.run(
            [sys.executable, worker, stl_path, str(load_N), axis, material],
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {"error": "FEA timed out after 180 s"}
    if proc.returncode != 0:
        return {"error": f"worker exited {proc.returncode}",
                "stderr": (proc.stderr or "")[-500:]}
    out = (proc.stdout or "").strip()
    try:
        return json.loads(out)
    except Exception as e:
        return {"error": f"worker returned non-JSON: {e}",
                "stdout_tail": out[-400:]}
