"""Materials database + per-part mass properties.

Density in g/cm^3 (= kg/L). Multiply by volume in cm^3 to get grams.
Colours are deliberately desaturated so they read as 'engineering' rather
than toy plastic.
"""
from __future__ import annotations

from typing import Any

import cadquery as cq


# density in g/cm^3, hex colour for the viewer
MATERIALS: dict[str, dict[str, Any]] = {
    "steel":      {"density": 7.85, "color": "#8a8e95"},
    "stainless":  {"density": 7.95, "color": "#a0a6ad"},
    "aluminum":   {"density": 2.70, "color": "#c2c6cc"},
    "brass":      {"density": 8.50, "color": "#c5a050"},
    "copper":     {"density": 8.96, "color": "#c68b5b"},
    "titanium":   {"density": 4.50, "color": "#9a9aa0"},
    "pla":        {"density": 1.24, "color": "#7aa2d6"},
    "abs":        {"density": 1.05, "color": "#3e3e44"},
    "nylon":      {"density": 1.14, "color": "#e8e0c0"},
    "rubber":     {"density": 1.20, "color": "#2c2c2c"},
    "wood":       {"density": 0.70, "color": "#a07a4e"},
    "glass":      {"density": 2.50, "color": "#cfe4ec"},
    "concrete":   {"density": 2.40, "color": "#9d9c98"},
    "lead":       {"density": 11.34, "color": "#5a5e66"},
    "default":    {"density": 1.00, "color": None},  # None = use hashed colour
}


def list_materials() -> str:
    rows = [f"  {name:<10}  rho={d['density']:.2f} g/cm^3"
            for name, d in MATERIALS.items() if name != "default"]
    return "materials:\n" + "\n".join(rows)


class MaterialsEngine:
    """Tracks material per part, exposes mass/COG/inertia helpers."""

    def __init__(self, cad_engine):
        self.cad = cad_engine
        # name -> material key (lookup in MATERIALS)
        self.assigned: dict[str, str] = {}

    # ----- assignment ----- #
    def assign(self, name: str, material: str) -> str:
        if name not in self.cad.parts:
            raise KeyError(f"no part '{name}' in scene")
        mat = material.lower()
        if mat not in MATERIALS:
            raise ValueError(f"unknown material '{material}'. "
                             f"Try: {', '.join(sorted(MATERIALS) - {'default'})}")
        self.assigned[name] = mat
        return f"assigned '{name}' material '{mat}'"

    def material_of(self, name: str) -> str:
        return self.assigned.get(name, "default")

    def density(self, name: str) -> float:
        return MATERIALS[self.material_of(name)]["density"]

    def color(self, name: str) -> str | None:
        return MATERIALS[self.material_of(name)]["color"]

    # ----- mass properties ----- #
    def mass(self, name: str) -> float:
        """Mass in grams (volume_mm3 * density_g_per_cm3 / 1000)."""
        if name not in self.cad.parts:
            raise KeyError(f"no part '{name}'")
        vol_mm3 = float(self.cad.parts[name].val().Volume())
        return vol_mm3 * self.density(name) * 1e-3

    def cog(self, name: str) -> tuple[float, float, float]:
        """Centre-of-gravity in world coords (mm)."""
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        if name not in self.cad.parts:
            raise KeyError(f"no part '{name}'")
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(self.cad.parts[name].val().wrapped, props)
        com = props.CentreOfMass()
        return (com.X(), com.Y(), com.Z())

    def inertia(self, name: str) -> dict[str, float]:
        """Mass moments of inertia about the centroid (g*mm^2).
        Returns Ixx, Iyy, Izz (principal-axis-aligned approximation).
        """
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(self.cad.parts[name].val().wrapped, props)
        moi = props.MatrixOfInertia()  # in volume*mm^2; multiply by density
        d = self.density(name) * 1e-3  # g/mm^3
        return {
            "Ixx_g_mm2": float(moi.Value(1, 1)) * d,
            "Iyy_g_mm2": float(moi.Value(2, 2)) * d,
            "Izz_g_mm2": float(moi.Value(3, 3)) * d,
        }

    def report(self, name: str) -> str:
        m = self.mass(name)
        cx, cy, cz = self.cog(name)
        I = self.inertia(name)
        return (f"mass properties of '{name}' ({self.material_of(name)}):\n"
                f"  volume:  {float(self.cad.parts[name].val().Volume()):.2f} mm^3\n"
                f"  mass:    {m:.3f} g  ({m/1000:.4f} kg)\n"
                f"  COG:     ({cx:.2f}, {cy:.2f}, {cz:.2f}) mm\n"
                f"  Ixx:     {I['Ixx_g_mm2']:.2e} g*mm^2\n"
                f"  Iyy:     {I['Iyy_g_mm2']:.2e} g*mm^2\n"
                f"  Izz:     {I['Izz_g_mm2']:.2e} g*mm^2")
