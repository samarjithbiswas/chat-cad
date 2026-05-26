"""Parametric mechanical-components library.

Single-call helpers for things you'd otherwise have to model from primitives:
bolts, nuts, washers, springs, gears, slots, keys. Each function returns a
CadQuery Workplane that is stored under a name in the main parts dict.

Sizes follow common metric-engineering conventions but are not certified to
any ISO/DIN standard. Use these as visualisation / fit-checking aids, not as
manufacturing drawings.
"""
from __future__ import annotations

import math
from typing import Any

import cadquery as cq


# ---------- M-series defaults (ISO 4014 / 4032 ish) ---------- #
_M_HEX = {  # M -> (across_flats, head_height, nut_height, washer_od, washer_th)
    "M2":  (4.0,  1.4, 1.6,  5.0, 0.3),
    "M2.5":(5.0,  1.7, 2.0,  6.0, 0.5),
    "M3":  (5.5,  2.0, 2.4,  7.0, 0.5),
    "M4":  (7.0,  2.8, 3.2,  9.0, 0.8),
    "M5":  (8.0,  3.5, 4.0, 10.0, 1.0),
    "M6":  (10.0, 4.0, 5.0, 12.0, 1.6),
    "M8":  (13.0, 5.3, 6.5, 16.0, 1.6),
    "M10": (16.0, 6.4, 8.0, 20.0, 2.0),
    "M12": (18.0, 7.5, 10.0, 24.0, 2.5),
    "M16": (24.0, 10.0, 13.0, 30.0, 3.0),
    "M20": (30.0, 12.5, 16.0, 37.0, 3.0),
}


def _m(spec: str) -> tuple[float, tuple]:
    """Return (thread_diameter_mm, _M_HEX entry) for an M-spec like 'M6'."""
    s = spec.upper().strip()
    if not s.startswith("M"):
        raise ValueError(f"M-spec must start with M, got '{spec}'")
    if s not in _M_HEX:
        raise ValueError(f"unsupported M-spec '{spec}'. Available: {sorted(_M_HEX)}")
    return float(s[1:]), _M_HEX[s]


def _hex_prism(across_flats: float, height: float) -> cq.Workplane:
    """Regular hexagonal prism centred at origin, flat-to-flat = across_flats."""
    return cq.Workplane("XY").polygon(6, across_flats).extrude(height)


# ---------------- fasteners ---------------- #
def bolt(d: float, head_af: float, head_h: float, shank_d: float,
         shank_len: float) -> cq.Workplane:
    """Hex-head bolt: hex head sitting on a smooth shank along +Z."""
    head = _hex_prism(head_af, head_h)
    shaft = (cq.Workplane("XY").workplane(offset=head_h)
             .circle(shank_d / 2).extrude(shank_len))
    body = head.union(shaft)
    return body


def bolt_m(spec: str, length: float) -> cq.Workplane:
    """Convenience: bolt('M6', 30) -> 30 mm long M6 hex-head bolt."""
    d, (af, hh, _nh, _wo, _wt) = _m(spec)
    return bolt(d, af, hh, d, float(length))


def nut(d: float, across_flats: float, height: float) -> cq.Workplane:
    """Hex nut with a through-hole."""
    return _hex_prism(across_flats, height).faces("+Z").workplane().hole(d)


def nut_m(spec: str) -> cq.Workplane:
    d, (af, _hh, nh, _wo, _wt) = _m(spec)
    return nut(d, af, nh)


def washer(d: float, od: float, thickness: float) -> cq.Workplane:
    """Flat washer."""
    return (cq.Workplane("XY").circle(od / 2).extrude(thickness)
            .faces("+Z").workplane().hole(d))


def washer_m(spec: str) -> cq.Workplane:
    d, (_af, _hh, _nh, wo, wt) = _m(spec)
    return washer(d, wo, wt)


# ---------------- transmission ---------------- #
def spur_gear(module: float, teeth: int, width: float,
              bore: float = 0.0) -> cq.Workplane:
    """Visual spur gear: pitch circle + N rectangular teeth + optional bore.
    Not an involute profile - good enough for assembly visualisation only.
    """
    n = int(teeth)
    if n < 8:
        raise ValueError("gear needs >=8 teeth")
    pitch_r = module * n / 2.0
    addendum = module
    dedendum = 1.25 * module
    root_r = pitch_r - dedendum
    tip_r = pitch_r + addendum
    # tooth thickness at pitch line ~ half the circular pitch
    tooth_angle = math.degrees(math.pi / n)  # tooth occupies ~half the slot
    # base disk
    body = cq.Workplane("XY").circle(root_r).extrude(width)
    # one tooth as a wedge between root_r and tip_r, spanning tooth_angle
    half = math.radians(tooth_angle / 2)
    # build the tooth as a polygon
    pts = [
        (root_r * math.cos(-half), root_r * math.sin(-half)),
        (tip_r  * math.cos(-half / 2), tip_r  * math.sin(-half / 2)),
        (tip_r  * math.cos( half / 2), tip_r  * math.sin( half / 2)),
        (root_r * math.cos( half), root_r * math.sin( half)),
    ]
    tooth = (cq.Workplane("XY").polyline(pts).close().extrude(width))
    # array N tooth copies around Z
    for i in range(n):
        a = 360.0 * i / n
        body = body.union(tooth.rotate((0, 0, 0), (0, 0, 1), a))
    if bore > 0:
        body = body.faces("+Z").workplane().hole(bore)
    return body


def compression_spring(wire_d: float, coil_d: float, pitch: float,
                       turns: float) -> cq.Workplane:
    """Helical compression spring: small circular wire swept along a helix."""
    height = pitch * float(turns)
    radius = coil_d / 2.0
    path = cq.Wire.makeHelix(pitch, height, radius)
    path_wp = cq.Workplane(obj=path)
    profile = (cq.Workplane("XZ").moveTo(radius, 0).circle(wire_d / 2))
    return profile.sweep(path_wp, isFrenet=True)


# ---------------- slots / keys ---------------- #
def slot(length: float, width: float, depth: float) -> cq.Workplane:
    """Stadium/obround slot (a rectangle capped by two semicircles), extruded.
    `length` is end-to-end including the semicircles; `width` is the diameter.
    """
    L, W = float(length), float(width)
    if L <= W:
        # degenerate to a circle
        return cq.Workplane("XY").circle(W / 2).extrude(depth)
    half = (L - W) / 2.0
    return (cq.Workplane("XY")
            .moveTo(-half, -W / 2)
            .lineTo(half, -W / 2)
            .threePointArc((half + W / 2, 0), (half, W / 2))
            .lineTo(-half, W / 2)
            .threePointArc((-half - W / 2, 0), (-half, -W / 2))
            .close()
            .extrude(depth))


def key_block(length: float, width: float, thickness: float) -> cq.Workplane:
    """Rectangular machine key (DIN 6885 shape, square ends — no chamfer)."""
    return cq.Workplane("XY").box(length, width, thickness)


# ---------------- engine binding ---------------- #
class LibraryEngine:
    """Routes `lib_*` ops to the helpers above and stores results as named parts."""

    def __init__(self, cad_engine):
        # CadEngine instance — we mutate its parts dict directly.
        self.cad = cad_engine

    def _store(self, name: str, wp: cq.Workplane) -> None:
        self.cad._snapshot()
        self.cad.parts[name] = wp

    # ---- fasteners ---- #
    def bolt(self, name: str, spec: str, length: float,
             x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = bolt_m(spec, length).translate((x, y, z))
        self._store(name, wp)
        return f"created {spec} hex bolt '{name}' length {length} mm"

    def nut(self, name: str, spec: str,
            x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = nut_m(spec).translate((x, y, z))
        self._store(name, wp)
        return f"created {spec} hex nut '{name}'"

    def washer(self, name: str, spec: str,
               x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = washer_m(spec).translate((x, y, z))
        self._store(name, wp)
        return f"created {spec} flat washer '{name}'"

    # ---- transmission ---- #
    def gear(self, name: str, module: float, teeth: int, width: float,
             bore: float = 0,
             x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = spur_gear(float(module), int(teeth), float(width),
                       float(bore)).translate((x, y, z))
        self._store(name, wp)
        return (f"created spur gear '{name}' module={module} teeth={teeth} "
                f"width={width} bore={bore}")

    def spring(self, name: str, wire_d: float, coil_d: float, pitch: float,
               turns: float,
               x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = compression_spring(float(wire_d), float(coil_d),
                                float(pitch), float(turns)).translate((x, y, z))
        self._store(name, wp)
        return (f"created spring '{name}' wire={wire_d} coil={coil_d} "
                f"pitch={pitch} turns={turns}")

    # ---- slots / keys ---- #
    def slot(self, name: str, length: float, width: float, depth: float,
             x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = slot(float(length), float(width), float(depth)).translate((x, y, z))
        self._store(name, wp)
        return f"created slot '{name}' L={length} W={width} D={depth}"

    def key(self, name: str, length: float, width: float, thickness: float,
            x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = key_block(float(length), float(width),
                       float(thickness)).translate((x, y, z))
        self._store(name, wp)
        return f"created key '{name}' {length}x{width}x{thickness}"


def dispatch_library(eng: LibraryEngine, op: str, args: dict) -> str:
    fn = getattr(eng, op, None)
    if fn is None or op.startswith("_"):
        raise ValueError(f"unknown library op '{op}'")
    return fn(**args)
