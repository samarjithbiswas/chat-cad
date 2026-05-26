"""Standard structural-profile extrusions.

Each helper returns a CadQuery Workplane of an extruded cross-section.
Dimensions follow common metric mechanical-engineering practice but are
not certified to any specific standard (DIN/ISO/ASTM).
"""
from __future__ import annotations

import math
from typing import Any

import cadquery as cq


# ---------------- profile-cross-section helpers ---------------- #
def _tslot_sketch(series: int) -> cq.Workplane:
    """20/30/40-series T-slot (extruded aluminum) cross-section."""
    s = float(series)
    slot_w = s * 0.32   # slot width at the outer face
    slot_depth = s * 0.45
    inner_chan = s * 0.18
    centre_hole = s * 0.21
    # outer square
    wp = cq.Workplane("XY").rect(s, s)
    # central through-hole
    wp = wp.circle(centre_hole / 2)
    # four T-slots, one per side
    for ang in (0, 90, 180, 270):
        sx = s / 2 * math.cos(math.radians(ang))
        sy = s / 2 * math.sin(math.radians(ang))
        # slot near each face: stadium-ish cutout
        slot = (cq.Workplane("XY").center(sx, sy)
                .rect(slot_w if ang in (0, 180) else slot_depth,
                      slot_depth if ang in (0, 180) else slot_w))
        wp = wp.cut(slot) if False else wp  # placeholder if cut needed
    return wp


def tslot(series: int, length: float) -> cq.Workplane:
    """Aluminum T-slot extrusion of given metric series (20/30/40), extruded
    along +Z by `length`.
    """
    s = float(series)
    slot_w = s * 0.32
    slot_depth = s * 0.45
    centre_hole = s * 0.21
    # build the outer square + four slot cutouts in 2D using a polygon path
    # body: hollow square outline + 4 slot-shaped subtractions
    body = cq.Workplane("XY").rect(s, s).extrude(float(length))
    # subtract a centre hole
    body = body.faces(">Z").workplane().hole(centre_hole)
    # cut 4 T-slots: one per face, running the full length
    for ang in (0, 90, 180, 270):
        cx = (s / 2 - slot_depth / 2) * math.cos(math.radians(ang))
        cy = (s / 2 - slot_depth / 2) * math.sin(math.radians(ang))
        rect_w = slot_w if ang in (0, 180) else slot_depth + 0.1
        rect_h = slot_depth + 0.1 if ang in (0, 180) else slot_w
        slot = (cq.Workplane("XY").center(cx, cy)
                .rect(rect_w, rect_h).extrude(float(length) + 0.1))
        body = body.cut(slot)
    return body


def angle_iron(side_a: float, side_b: float, thickness: float,
               length: float) -> cq.Workplane:
    """L-section angle iron. Origin at the inside corner."""
    a, b, t = float(side_a), float(side_b), float(thickness)
    pts = [(0, 0), (a, 0), (a, t), (t, t), (t, b), (0, b)]
    return cq.Workplane("XY").polyline(pts).close().extrude(float(length))


def square_tube(side: float, wall_thickness: float,
                length: float) -> cq.Workplane:
    """Hollow square tube."""
    s, w = float(side), float(wall_thickness)
    return (cq.Workplane("XY").rect(s, s).rect(s - 2 * w, s - 2 * w)
            .extrude(float(length)))


def round_tube(od: float, wall_thickness: float,
               length: float) -> cq.Workplane:
    """Hollow round tube."""
    return (cq.Workplane("XY").circle(od / 2).circle(od / 2 - wall_thickness)
            .extrude(float(length)))


def i_beam(height: float, width: float, web_t: float, flange_t: float,
           length: float) -> cq.Workplane:
    """Symmetric I-beam, height along Y, width along X."""
    H, W, tw, tf = float(height), float(width), float(web_t), float(flange_t)
    pts = [
        (-W / 2, -H / 2), ( W / 2, -H / 2),
        ( W / 2, -H / 2 + tf), ( tw / 2, -H / 2 + tf),
        ( tw / 2,  H / 2 - tf), ( W / 2,  H / 2 - tf),
        ( W / 2,  H / 2), (-W / 2,  H / 2),
        (-W / 2,  H / 2 - tf), (-tw / 2,  H / 2 - tf),
        (-tw / 2, -H / 2 + tf), (-W / 2, -H / 2 + tf),
    ]
    return cq.Workplane("XY").polyline(pts).close().extrude(float(length))


def c_channel(height: float, width: float, thickness: float,
              length: float) -> cq.Workplane:
    """C-section channel, opening towards +X."""
    H, W, t = float(height), float(width), float(thickness)
    pts = [
        (0, -H / 2), (W, -H / 2),
        (W, -H / 2 + t), (t, -H / 2 + t),
        (t,  H / 2 - t), (W,  H / 2 - t),
        (W,  H / 2), (0,  H / 2),
    ]
    return cq.Workplane("XY").polyline(pts).close().extrude(float(length))


# ---------------- engine binding ---------------- #
class ProfilesEngine:
    def __init__(self, cad_engine):
        self.cad = cad_engine

    def _store(self, name: str, wp: cq.Workplane) -> None:
        self.cad._snapshot()
        self.cad.parts[name] = wp

    def tslot(self, name: str, series: int, length: float,
              x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = tslot(int(series), float(length)).translate((x, y, z))
        self._store(name, wp)
        return f"created {series}-series T-slot '{name}' length={length}"

    def angle(self, name: str, side_a: float, side_b: float, thickness: float,
              length: float,
              x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = angle_iron(float(side_a), float(side_b), float(thickness),
                        float(length)).translate((x, y, z))
        self._store(name, wp)
        return f"created angle '{name}' {side_a}x{side_b}x{thickness}, L={length}"

    def sqtube(self, name: str, side: float, wall: float, length: float,
               x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = square_tube(float(side), float(wall),
                         float(length)).translate((x, y, z))
        self._store(name, wp)
        return f"created square tube '{name}' {side}x{wall}, L={length}"

    def rtube(self, name: str, od: float, wall: float, length: float,
              x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = round_tube(float(od), float(wall),
                        float(length)).translate((x, y, z))
        self._store(name, wp)
        return f"created round tube '{name}' OD={od} wall={wall}, L={length}"

    def ibeam(self, name: str, height: float, width: float, web_t: float,
              flange_t: float, length: float,
              x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = i_beam(float(height), float(width), float(web_t),
                    float(flange_t), float(length)).translate((x, y, z))
        self._store(name, wp)
        return (f"created I-beam '{name}' H={height} W={width} web={web_t} "
                f"flange={flange_t} L={length}")

    def cchan(self, name: str, height: float, width: float, thickness: float,
              length: float,
              x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = c_channel(float(height), float(width), float(thickness),
                       float(length)).translate((x, y, z))
        self._store(name, wp)
        return (f"created C-channel '{name}' H={height} W={width} t={thickness} "
                f"L={length}")
