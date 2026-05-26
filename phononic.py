"""Phononic crystal unit-cell library — chat_cad ⇄ PhononIQ bridge.

Parametric generators for the six canonical unit-cell families used in
phononic-crystal research, plus a lattice-tile operator. These are the
shapes whose bandgaps PhononIQ's surrogate model is trained to predict;
exposing them as one-command CAD primitives is the first half of the
inverse-design loop.

Reference family (matches published phononic-crystal taxonomy):
  1. Square-hole array in a plate (the PhononIQ baseline geometry)
  2. Hexagonal hole array
  3. Cross-shaped (plus-sign) inclusions
  4. Pillar-on-plate locally-resonant structures
  5. Bragg layered reflector
  6. Cylindrical inclusion array (heavy core in light matrix surrogate)

Conventions
-----------
- a (lattice constant) is given in mm
- All cells are centred at the origin with the plate normal along Z
- Cell extents: -a/2 .. +a/2 in X and Y; thickness t along Z (centred at z=0)
- Returns a single cq.Workplane that is the FILLED solid (matrix material
  with inclusions removed for hole-type, or unioned for pillar-type)
"""
from __future__ import annotations

import math
from typing import Any

import cadquery as cq


# ---------------- 1. Square hole in plate ---------------- #
def square_hole_cell(a: float, t: float, hole_size: float) -> cq.Workplane:
    """Square-cross-section through-hole at the cell centre.
    The unit cell PhononIQ's surrogate was trained on. Filling fraction
    is determined by (hole_size / a)**2 — a key surrogate input.
    """
    a, t, h = float(a), float(t), float(hole_size)
    if h >= a:
        raise ValueError(f"hole_size ({h}) must be < lattice a ({a})")
    return (cq.Workplane("XY").box(a, a, t)
            .faces("+Z").workplane().rect(h, h).cutThruAll())


# ---------------- 2. Hexagonal array of circular holes ---------------- #
def hex_hole_cell(a: float, t: float, hole_d: float) -> cq.Workplane:
    """Hexagonal close-packed array of circular through-holes.
    Two holes per cell (corners + centre) approximate a 2-atom basis.
    """
    a, t, d = float(a), float(t), float(hole_d)
    if d >= a * 0.95:
        raise ValueError("hole_d too large for given a")
    cell = cq.Workplane("XY").box(a, a, t)
    # one centred hole + corner contributions modelled as a single centred hole
    cell = cell.faces("+Z").workplane().circle(d / 2).cutThruAll()
    return cell


# ---------------- 3. Cross-shaped inclusion ---------------- #
def cross_cell(a: float, t: float, arm_length: float,
               arm_width: float) -> cq.Workplane:
    """Plus-sign (cross) cutout of two perpendicular rectangles."""
    a, t = float(a), float(t)
    L = float(arm_length); w = float(arm_width)
    if L >= a or w >= a:
        raise ValueError("cross arms larger than cell")
    cell = cq.Workplane("XY").box(a, a, t)
    cutter = (cq.Workplane("XY").rect(L, w).extrude(t * 1.1)
              .union(cq.Workplane("XY").rect(w, L).extrude(t * 1.1)))
    cell = cell.cut(cutter.translate((0, 0, -t * 0.05)))
    return cell


# ---------------- 4. Pillar-on-plate (locally-resonant) ---------------- #
def pillar_cell(a: float, t: float, pillar_d: float,
                pillar_h: float) -> cq.Workplane:
    """Solid plate with a cylindrical pillar standing on top. The pillar's
    mass+stiffness ratio with the plate determines the resonance frequency.
    """
    a, t = float(a), float(t)
    pd, ph = float(pillar_d), float(pillar_h)
    plate = cq.Workplane("XY").box(a, a, t)
    pillar = (cq.Workplane("XY").circle(pd / 2).extrude(ph)
              .translate((0, 0, t / 2)))
    return plate.union(pillar)


# ---------------- 5. Bragg layered reflector ---------------- #
def bragg_cell(layer_thicknesses: list[float], plate_w: float,
               plate_d: float | None = None) -> cq.Workplane:
    """N-layer Bragg reflector. Each layer is rendered as a separate-coloured
    boxlet stacked along Z. Layer_thicknesses lists each layer's thickness
    in mm; total thickness = sum(layer_thicknesses).
    """
    w = float(plate_w); d = float(plate_d) if plate_d else w
    z_cursor = -sum(layer_thicknesses) / 2
    body: cq.Workplane | None = None
    for li in layer_thicknesses:
        slab = (cq.Workplane("XY").box(w, d, float(li),
                                        centered=(True, True, False))
                .translate((0, 0, z_cursor)))
        body = slab if body is None else body.union(slab)
        z_cursor += li
    return body


# ---------------- 6. Heavy cylindrical core (locally-resonant) ---------- #
def core_inclusion_cell(a: float, t: float, core_d: float) -> cq.Workplane:
    """A cylindrical 'core' cut from the centre of a plate. In practice the
    void would be backfilled with a heavy material; here we model the
    matrix only (one CAD body — multi-material assemblies need separate
    parts in the scene). Returns the perforated plate.
    """
    a, t, d = float(a), float(t), float(core_d)
    if d >= a:
        raise ValueError("core_d larger than cell")
    return (cq.Workplane("XY").box(a, a, t)
            .faces("+Z").workplane().circle(d / 2).cutThruAll())


# ---------------- lattice tile ---------------- #
def tile_lattice(unit_wp: cq.Workplane, a: float,
                 nx: int, ny: int) -> cq.Workplane:
    """Tile the unit cell `unit_wp` in an nx × ny rectangular lattice.
    Cells share boundaries; output is a single fused solid.
    """
    a = float(a); nx = int(nx); ny = int(ny)
    body: cq.Workplane | None = None
    for i in range(nx):
        for j in range(ny):
            dx = (i - (nx - 1) / 2) * a
            dy = (j - (ny - 1) / 2) * a
            tile = unit_wp.translate((dx, dy, 0))
            body = tile if body is None else body.union(tile)
    return body


# ---------------- bandgap-target heuristic (until PhononIQ wired) -------- #
def estimate_bandgap_window(family: str, a: float, t: float,
                            param: float) -> tuple[float, float]:
    """Placeholder estimator until the PhononIQ surrogate is wired in.
    Returns a coarse (f_lo, f_hi) Hz window using textbook scaling laws
    for plate-wave bandgaps in mm-millimetric crystals.

    REPLACE this with the real PhononIQ model call when integrating —
    see INTEGRATION_PHONONIQ.md.
    """
    # plate-wave speed in BOROFLOAT-33 ≈ 5570 m/s longitudinal
    c = 5570.0
    # Bragg condition: lambda_Bragg = 2a  =>  f_Bragg = c / (2a_mm * 1e-3)
    f_bragg = c / (2.0 * a * 1e-3)
    # Local-resonance shifts the window depending on the family + fill fraction
    ff = (param / a) ** 2 if family in {"square_hole", "hex_hole", "cross", "core"} else 0.4
    if family == "pillar":
        # pillar locally-resonant gap centred near the pillar resonance
        f_centre = c / (4.0 * param * 1e-3)  # quarter-wave on the pillar
        return (f_centre * 0.85, f_centre * 1.15)
    if family == "bragg":
        return (f_bragg * 0.7, f_bragg * 1.4)
    # hole families: gap shifts down as filling fraction increases
    f_centre = f_bragg * (1.0 - 0.35 * ff)
    return (f_centre * 0.85, f_centre * 1.18)


# ---------------- engine binding ---------------- #
class PhononicEngine:
    """Routes `pc_*` ops + stores results in the main scene."""

    def __init__(self, cad_engine):
        self.cad = cad_engine

    def _store(self, name: str, wp: cq.Workplane) -> None:
        self.cad._snapshot()
        self.cad.parts[name] = wp

    def square_hole(self, name: str, a: float, t: float, hole_size: float,
                    x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = square_hole_cell(a, t, hole_size).translate((x, y, z))
        self._store(name, wp)
        f_lo, f_hi = estimate_bandgap_window("square_hole", a, t, hole_size)
        return (f"unit cell '{name}': square-hole a={a} mm, t={t} mm, "
                f"hole={hole_size} mm — estimated bandgap "
                f"~{f_lo/1000:.1f}-{f_hi/1000:.1f} kHz (placeholder).")

    def hex_hole(self, name: str, a: float, t: float, hole_d: float,
                 x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = hex_hole_cell(a, t, hole_d).translate((x, y, z))
        self._store(name, wp)
        f_lo, f_hi = estimate_bandgap_window("hex_hole", a, t, hole_d)
        return (f"unit cell '{name}': hex-hole a={a} mm, t={t} mm, "
                f"hole_d={hole_d} mm — estimated ~{f_lo/1000:.1f}-{f_hi/1000:.1f} kHz")

    def cross(self, name: str, a: float, t: float, arm_length: float,
              arm_width: float,
              x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = cross_cell(a, t, arm_length, arm_width).translate((x, y, z))
        self._store(name, wp)
        f_lo, f_hi = estimate_bandgap_window("cross", a, t, arm_length)
        return (f"unit cell '{name}': cross-inclusion a={a} mm — "
                f"~{f_lo/1000:.1f}-{f_hi/1000:.1f} kHz")

    def pillar(self, name: str, a: float, t: float, pillar_d: float,
               pillar_h: float,
               x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = pillar_cell(a, t, pillar_d, pillar_h).translate((x, y, z))
        self._store(name, wp)
        f_lo, f_hi = estimate_bandgap_window("pillar", a, t, pillar_h)
        return (f"unit cell '{name}': pillar-on-plate, pillar_h={pillar_h} mm "
                f"— locally-resonant gap ~{f_lo/1000:.1f}-{f_hi/1000:.1f} kHz")

    def bragg(self, name: str, layer_thicknesses: list[float],
              plate_w: float, plate_d: float | None = None,
              x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = bragg_cell(layer_thicknesses, plate_w, plate_d)
        if wp is None:
            raise ValueError("bragg needs at least one layer")
        wp = wp.translate((x, y, z))
        self._store(name, wp)
        return (f"Bragg stack '{name}': {len(layer_thicknesses)} layers, "
                f"total {sum(layer_thicknesses):.2f} mm")

    def core_inclusion(self, name: str, a: float, t: float, core_d: float,
                       x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = core_inclusion_cell(a, t, core_d).translate((x, y, z))
        self._store(name, wp)
        f_lo, f_hi = estimate_bandgap_window("core", a, t, core_d)
        return (f"core-inclusion cell '{name}': a={a} mm core_d={core_d} mm "
                f"— ~{f_lo/1000:.1f}-{f_hi/1000:.1f} kHz")

    def lattice(self, out: str, unit: str, a: float, nx: int, ny: int) -> str:
        """Tile an existing named unit cell into an nx x ny lattice."""
        if unit not in self.cad.parts:
            raise KeyError(f"no unit cell named '{unit}'")
        body = tile_lattice(self.cad.parts[unit], a, nx, ny)
        self.cad._snapshot()
        self.cad.parts[out] = body
        return f"tiled '{unit}' into {nx}x{ny} lattice -> '{out}'"
