"""Sheet-metal mockup operations.

These produce visually correct bent-sheet parts. They do NOT compute true
bend allowances or unfold patterns — for that you'd need a dedicated sheet
metal CAD tool (Onshape sheet metal, SolidWorks sheet metal, etc.). Use
these as concept / fixture mockups; if you need a flat pattern for laser
cutting, dimension it manually.

The convention: bends are quarter-cylindrical fillets at the inside corner.
"""
from __future__ import annotations

import math
from typing import Any

import cadquery as cq


def _bent_sheet_2d(segments: list[tuple[float, float]],
                   thickness: float, bend_radius: float) -> cq.Workplane:
    """Build a sheet from a 2D centreline polyline (XZ plane), extruded along
    Y by an automatic width (segments give cross-section in XZ).
    Internal helper for the named bent shapes below.
    """
    raise NotImplementedError("use the named helpers (sheet_L, sheet_U, ...)")


def sheet_flat(length: float, width: float, thickness: float) -> cq.Workplane:
    """Flat sheet centred at origin, top face at +z=thickness/2."""
    return cq.Workplane("XY").box(float(length), float(width), float(thickness))


def sheet_l(length: float, width: float, thickness: float,
            leg_a: float, leg_b: float, bend_radius: float = 0.0) -> cq.Workplane:
    """L-shaped bent sheet (90 deg). leg_a runs along +X, leg_b along +Z.
    Inside-corner bend radius is filleted for realism.
    """
    t, r = float(thickness), float(bend_radius)
    a, b = float(leg_a), float(leg_b)
    # cross-section in XZ
    pts = [(0, 0), (a, 0), (a, t), (t, t), (t, b), (0, b)]
    sect = (cq.Workplane("XZ").polyline(pts).close()
            .extrude(float(width)))
    if r > 0:
        try:
            # inside fillet at the (t, t) corner — pick the edge there
            sect = sect.edges("|Y and >X and >Z").fillet(r)
        except Exception:
            pass
    return sect.translate((0, -float(width) / 2, 0))


def sheet_u(length: float, width: float, thickness: float,
            leg_height: float, bend_radius: float = 0.0) -> cq.Workplane:
    """U-shaped (channel-like) bent sheet. Base of length `length`, two
    upturned legs of `leg_height`, total width along Y is `width`.
    """
    t, r = float(thickness), float(bend_radius)
    L, h = float(length), float(leg_height)
    pts = [
        (0, 0), (L, 0),
        (L, h), (L - t, h),
        (L - t, t), (t, t),
        (t, h), (0, h),
    ]
    body = (cq.Workplane("XZ").polyline(pts).close()
            .extrude(float(width)))
    if r > 0:
        try:
            body = body.edges("|Y").fillet(r)
        except Exception:
            pass
    return body.translate((0, -float(width) / 2, 0))


def sheet_box(length: float, width: float, height: float,
              thickness: float, bend_radius: float = 0.0) -> cq.Workplane:
    """Open-top sheet metal box (5-sided): floor + 4 walls."""
    t = float(thickness)
    L, W, H = float(length), float(width), float(height)
    # outer box minus inner box minus a top-face lid cut
    outer = cq.Workplane("XY").box(L, W, H, centered=(True, True, False))
    inner = (cq.Workplane("XY").box(L - 2 * t, W - 2 * t, H,
                                     centered=(True, True, False))
             .translate((0, 0, t)))
    body = outer.cut(inner)
    if float(bend_radius) > 0:
        try:
            body = body.edges("|Z").fillet(float(bend_radius))
        except Exception:
            pass
    return body


def sheet_flange(part: cq.Workplane, edge_axis: str = "+X",
                 flange_length: float = 20.0,
                 thickness: float = 2.0,
                 bend_radius: float = 0.0) -> cq.Workplane:
    """Add a perpendicular flange to a flat sheet along the chosen edge.
    The new flange runs along +Z (upward) by `flange_length`.
    `edge_axis` selects which edge of the sheet to flange: +X, -X, +Y, -Y.
    """
    bb = part.val().BoundingBox()
    t = float(thickness)
    fl = float(flange_length)
    if edge_axis == "+X":
        flange = (cq.Workplane("XY")
                  .box(t, bb.ylen, fl, centered=(False, True, False))
                  .translate((bb.xmax, (bb.ymin + bb.ymax) / 2, bb.zmax)))
    elif edge_axis == "-X":
        flange = (cq.Workplane("XY")
                  .box(t, bb.ylen, fl, centered=(False, True, False))
                  .translate((bb.xmin - t, (bb.ymin + bb.ymax) / 2, bb.zmax)))
    elif edge_axis == "+Y":
        flange = (cq.Workplane("XY")
                  .box(bb.xlen, t, fl, centered=(True, False, False))
                  .translate(((bb.xmin + bb.xmax) / 2, bb.ymax, bb.zmax)))
    else:  # -Y
        flange = (cq.Workplane("XY")
                  .box(bb.xlen, t, fl, centered=(True, False, False))
                  .translate(((bb.xmin + bb.xmax) / 2, bb.ymin - t, bb.zmax)))
    body = part.union(flange)
    if float(bend_radius) > 0:
        try:
            body = body.edges(f"|Y and >Z and {edge_axis[1]}{edge_axis[0]}").fillet(float(bend_radius))
        except Exception:
            pass
    return body


# ---------------- engine binding ---------------- #
class SheetMetalEngine:
    def __init__(self, cad_engine):
        self.cad = cad_engine

    def _store(self, name: str, wp: cq.Workplane) -> None:
        self.cad._snapshot()
        self.cad.parts[name] = wp

    def flat(self, name: str, length: float, width: float, thickness: float,
             x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = sheet_flat(float(length), float(width),
                        float(thickness)).translate((x, y, z))
        self._store(name, wp)
        return f"flat sheet '{name}' {length}x{width}x{thickness}"

    def l_bend(self, name: str, length: float, width: float, thickness: float,
               leg_a: float, leg_b: float, bend_radius: float = 0,
               x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = sheet_l(float(length), float(width), float(thickness),
                     float(leg_a), float(leg_b),
                     float(bend_radius)).translate((x, y, z))
        self._store(name, wp)
        return (f"L-bent sheet '{name}' t={thickness} legs {leg_a}x{leg_b} "
                f"width={width}")

    def u_bend(self, name: str, length: float, width: float, thickness: float,
               leg_height: float, bend_radius: float = 0,
               x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = sheet_u(float(length), float(width), float(thickness),
                     float(leg_height),
                     float(bend_radius)).translate((x, y, z))
        self._store(name, wp)
        return (f"U-bent sheet '{name}' length={length} legs={leg_height} "
                f"width={width} t={thickness}")

    def box(self, name: str, length: float, width: float, height: float,
            thickness: float, bend_radius: float = 0,
            x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = sheet_box(float(length), float(width), float(height),
                       float(thickness),
                       float(bend_radius)).translate((x, y, z))
        self._store(name, wp)
        return (f"sheet box '{name}' {length}x{width}x{height} "
                f"wall={thickness}")

    def flange(self, name: str, edge_axis: str = "+X",
               flange_length: float = 20, thickness: float = 2,
               bend_radius: float = 0) -> str:
        if name not in self.cad.parts:
            raise KeyError(f"no part '{name}'")
        new = sheet_flange(self.cad.parts[name], edge_axis,
                           float(flange_length), float(thickness),
                           float(bend_radius))
        self.cad._snapshot()
        self.cad.parts[name] = new
        return f"added {edge_axis} flange ({flange_length} mm) to '{name}'"
