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


def _run_worker(args: list[str]) -> dict:
    here = os.path.dirname(os.path.abspath(__file__))
    worker = os.path.join(here, "fea_worker.py")
    try:
        proc = subprocess.run(
            [sys.executable, worker, *args],
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {"error": "FEA worker timed out after 180 s"}
    if proc.returncode != 0:
        return {"error": f"worker exited {proc.returncode}",
                "stderr": (proc.stderr or "")[-500:]}
    out = (proc.stdout or "").strip()
    try:
        return json.loads(out)
    except Exception as e:
        return {"error": f"worker returned non-JSON: {e}",
                "stdout_tail": out[-400:]}


def run_fea(stl_path: str, load_N: float = 100.0, axis: str = "Z",
            material: str = "aluminum") -> dict:
    if not os.path.exists(stl_path):
        return {"error": f"STL not found at {stl_path}"}
    return _run_worker([stl_path, str(load_N), axis, material])


def run_thermal(stl_path: str, t_hot: float = 100.0, t_cold: float = 20.0,
                axis: str = "Z") -> dict:
    if not os.path.exists(stl_path):
        return {"error": f"STL not found at {stl_path}"}
    return _run_worker(["thermal", stl_path, str(t_hot), str(t_cold), axis])


def run_modal(stl_path: str, material: str = "aluminum",
              n_modes: int = 6) -> dict:
    if not os.path.exists(stl_path):
        return {"error": f"STL not found at {stl_path}"}
    return _run_worker(["modal", stl_path, material, str(n_modes)])


def run_cfd_2d(stl_path: str, inlet_velocity: float = 1.0,
               viscosity: float = 1.0e-3, axis: str = "Z") -> dict:
    if not os.path.exists(stl_path):
        return {"error": f"STL not found at {stl_path}"}
    return _run_worker(["cfd", stl_path, str(inlet_velocity), str(viscosity), axis])
