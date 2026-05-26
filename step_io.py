"""STEP file import.

Lets chat_cad consume real supplier models (McMaster-Carr, Bosch, Misumi
T-slot extrusions, screws/nuts from GrabCAD, etc.) by importing STEP files
as named parts in the scene.
"""
from __future__ import annotations

import os

import cadquery as cq


def import_step(path: str, name: str) -> cq.Workplane:
    """Load a STEP file and return it as a CadQuery Workplane."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"STEP file not found: {path}")
    wp = cq.importers.importStep(path)
    return wp


class StepIOEngine:
    """Routes step_* ops to the import helper."""

    def __init__(self, cad_engine):
        self.cad = cad_engine

    def step_import(self, name: str, path: str,
                    x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = import_step(path, name).translate((x, y, z))
        self.cad._snapshot()
        self.cad.parts[name] = wp
        try:
            bb = wp.val().BoundingBox()
            return (f"imported STEP file as '{name}' from {os.path.basename(path)} "
                    f"(bbox {bb.xlen:.1f}x{bb.ylen:.1f}x{bb.zlen:.1f} mm)")
        except Exception:
            return f"imported STEP file as '{name}' from {os.path.basename(path)}"
