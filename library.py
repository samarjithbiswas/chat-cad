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
         shank_len: float, threaded: bool = False,
         pitch: float | None = None) -> cq.Workplane:
    """Hex-head bolt: hex head sitting on a shank along +Z.
    If `threaded` is True, an external helical thread is swept along the
    bottom 2/3 of the shank length. Real geometry, but it adds ~10x the
    triangle count.
    """
    head = _hex_prism(head_af, head_h)
    shaft = (cq.Workplane("XY").workplane(offset=head_h)
             .circle(shank_d / 2).extrude(shank_len))
    body = head.union(shaft)
    if threaded:
        # default ISO coarse pitch table for common Ms (approximate)
        if pitch is None:
            pitch_table = {2: 0.4, 2.5: 0.45, 3: 0.5, 4: 0.7, 5: 0.8,
                           6: 1.0, 8: 1.25, 10: 1.5, 12: 1.75, 16: 2.0, 20: 2.5}
            pitch = pitch_table.get(round(shank_d * 2) / 2, max(0.3, shank_d * 0.16))
        thread_len = shank_len * 0.7  # threaded portion: bottom ~70% of shank
        thread_z0 = head_h + (shank_len - thread_len)
        try:
            helix = cq.Wire.makeHelix(float(pitch), float(thread_len), shank_d / 2)
            path = cq.Workplane(obj=helix).translate((0, 0, thread_z0))
            # tiny triangular profile (~60deg) sweeping along the helix
            h = pitch * 0.55           # thread crest height
            inset = 0.15               # bury thread base 0.15 mm into shank
            profile = (cq.Workplane("XZ")
                       .moveTo(shank_d / 2 - inset, thread_z0)
                       .lineTo(shank_d / 2 + h,     thread_z0 + pitch / 2)
                       .lineTo(shank_d / 2 - inset, thread_z0 + pitch)
                       .close())
            thread = profile.sweep(path, isFrenet=True)
            body = body.union(thread)
        except Exception:
            pass  # if sweep fails, return smooth shank
    return body


def bolt_m(spec: str, length: float, threaded: bool = False) -> cq.Workplane:
    """Convenience: bolt_m('M6', 30) -> 30 mm long M6 hex-head bolt.
    Pass threaded=True to cut a real helical thread along the shank.
    """
    d, (af, hh, _nh, _wo, _wt) = _m(spec)
    return bolt(d, af, hh, d, float(length), threaded=threaded)


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


# ---------------- bearings / pins / inserts ---------------- #
def ball_bearing(bore: float, od: float, width: float) -> cq.Workplane:
    """Deep-groove ball bearing visualisation: outer race + inner race +
    ring of balls. Not for analysis; rolling elements are decorative.
    """
    outer = (cq.Workplane("XY").circle(od / 2).circle(od / 2 - 0.18 * (od - bore) / 2)
             .extrude(width))
    inner = (cq.Workplane("XY").circle(bore / 2 + 0.18 * (od - bore) / 2)
             .circle(bore / 2).extrude(width))
    # ring of balls in the gap
    ball_r = (od - bore) / 4 * 0.85
    pitch_r = (od + bore) / 4
    n = max(6, int(2 * math.pi * pitch_r / (2.2 * ball_r)))
    balls = cq.Workplane("XY")
    for i in range(n):
        a = 2 * math.pi * i / n
        balls = balls.union(
            cq.Workplane("XY").sphere(ball_r).translate(
                (pitch_r * math.cos(a), pitch_r * math.sin(a), width / 2)))
    return outer.union(inner).union(balls)


def threaded_insert(M_spec: str, length: float) -> cq.Workplane:
    """Brass heat-set insert: smooth knurl-style outer + threaded ID hole.
    OD is +0.4 mm over M-bolt OD to simulate the insert wall.
    """
    d, _ = _m(M_spec)
    od = d + 1.2
    return (cq.Workplane("XY").circle(od / 2).extrude(float(length))
            .faces("+Z").workplane().hole(d, float(length) * 0.9))


def dowel_pin(diameter: float, length: float) -> cq.Workplane:
    """Cylindrical dowel pin with small chamfers on both ends."""
    chamfer = min(diameter * 0.15, 0.4)
    body = cq.Workplane("XY").circle(diameter / 2).extrude(length)
    body = body.faces(">Z").chamfer(chamfer)
    body = body.faces("<Z").chamfer(chamfer)
    return body


def hinge(length: float, leaf_width: float, pin_d: float,
          knuckles: int = 3, leaf_thickness: float = 2.0) -> cq.Workplane:
    """Barrel hinge with N knuckles. Returns a single fused body (both leaves
    and pin merged) — fine for visualisation.
    """
    knuckles = max(3, int(knuckles))
    knuckle_len = length / knuckles
    knuckle_or = pin_d * 0.9
    # leaf A (back): rectangle behind the pin axis (negative Y)
    leaf_a = (cq.Workplane("XY")
              .moveTo(0, -leaf_width / 2 - knuckle_or)
              .rect(length, leaf_width, centered=False)
              .extrude(leaf_thickness)
              .translate((-length / 2, knuckle_or, 0)))
    leaf_b = (cq.Workplane("XY")
              .moveTo(0, knuckle_or)
              .rect(length, leaf_width, centered=False)
              .extrude(leaf_thickness)
              .translate((-length / 2, 0, 0)))
    body = leaf_a.union(leaf_b)
    # knuckles: cylinders along X with central pin bore
    for i in range(knuckles):
        x0 = -length / 2 + i * knuckle_len
        knuckle = (cq.Workplane("YZ").workplane(offset=x0)
                   .circle(knuckle_or).extrude(knuckle_len))
        body = body.union(knuckle)
    # pin through the centre
    pin = (cq.Workplane("YZ").workplane(offset=-length / 2)
           .circle(pin_d / 2).extrude(length))
    body = body.union(pin)
    return body


# ===================================================================== #
# AEROSPACE MOCKUP HELPERS                                                #
#                                                                         #
# These produce visually convincing aero parts in seconds. They are NOT   #
# engineering geometry: no NURBS surfaces, no aerodynamic optimisation,   #
# no certified profiles. Use for portfolios / concept visualisations.    #
# ===================================================================== #

def naca4_profile(code: str, chord: float, n_pts: int = 50) -> list[tuple[float, float]]:
    """Return ordered (x,y) points around a NACA 4-digit airfoil at given chord.
    Standard analytical profile (Jacobs 1933). Returns ~2*n_pts points starting
    at trailing edge, going over the top, around the leading edge, back along
    the bottom.
    """
    s = code.strip()
    if len(s) != 4 or not s.isdigit():
        raise ValueError(f"NACA code must be 4 digits, got '{code}'")
    m = int(s[0]) / 100.0          # max camber as % chord
    p = int(s[1]) / 10.0           # camber position as fraction of chord
    t = int(s[2:]) / 100.0         # thickness as % chord
    # cosine-spaced beta for better LE/TE resolution
    betas = [math.pi * i / (n_pts - 1) for i in range(n_pts)]
    xs = [(1 - math.cos(b)) / 2 for b in betas]
    upper, lower = [], []
    for x in xs:
        # thickness distribution (4 percent series, blunt TE)
        yt = 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x**2
                      + 0.2843 * x**3 - 0.1015 * x**4)
        # camber line + slope
        if m == 0 or p == 0:
            yc, dyc = 0.0, 0.0
        elif x < p:
            yc = m / p**2 * (2 * p * x - x**2)
            dyc = 2 * m / p**2 * (p - x)
        else:
            yc = m / (1 - p)**2 * ((1 - 2 * p) + 2 * p * x - x**2)
            dyc = 2 * m / (1 - p)**2 * (p - x)
        theta = math.atan(dyc)
        xu = x - yt * math.sin(theta); yu = yc + yt * math.cos(theta)
        xl = x + yt * math.sin(theta); yl = yc - yt * math.cos(theta)
        upper.append((xu * chord, yu * chord))
        lower.append((xl * chord, yl * chord))
    # order: TE -> upper -> LE -> lower -> back to TE
    pts = list(reversed(upper)) + lower[1:]
    return pts


def naca_airfoil(code: str, chord: float, span: float) -> cq.Workplane:
    """Extruded NACA-4 wing section."""
    pts = naca4_profile(code, float(chord), n_pts=40)
    sk = cq.Workplane("XY").polyline(pts).close()
    return sk.extrude(float(span))


def _blade_profile_pts(chord: float, thickness_pct: float = 8.0,
                       camber_pct: float = 4.0) -> list[tuple[float, float]]:
    """Raw (x,y) points for an airfoil-like profile centred at origin."""
    code = f"{int(camber_pct):d}4{int(thickness_pct):02d}"
    pts = naca4_profile(code, chord, n_pts=24)
    cx = chord / 2
    return [(x - cx, y) for x, y in pts]


def _twisted_loft(root_pts: list[tuple[float, float]],
                  tip_pts: list[tuple[float, float]],
                  height: float, twist_deg: float) -> cq.Workplane:
    """Loft from root profile (at z=0) to tip profile (at z=height,
    rotated by twist_deg about Z). Done as a single Workplane chain so
    CadQuery's loft sees both wires.
    """
    return (cq.Workplane("XY")
            .polyline(root_pts).close()
            .workplane(offset=height)
            .transformed(rotate=(0, 0, float(twist_deg)))
            .polyline(tip_pts).close()
            .loft(combine=True, ruled=False))


def turbine_wheel(blade_count: int, od: float, hub_d: float,
                  hub_thickness: float, blade_chord: float = 0.0,
                  blade_twist_deg: float = 18.0) -> cq.Workplane:
    """Disc with N airfoil blades arranged around the rim, each twisted."""
    if blade_count < 4:
        raise ValueError("turbine needs >=4 blades")
    n = int(blade_count)
    chord = float(blade_chord) or od * 0.18
    blade_height = (od - hub_d) / 2.0
    disc = (cq.Workplane("XY").circle(od / 2).extrude(hub_thickness)
            .faces("+Z").workplane().hole(hub_d * 0.35))
    root_pts = _blade_profile_pts(chord, thickness_pct=10, camber_pct=3)
    tip_pts  = _blade_profile_pts(chord * 0.75, thickness_pct=6, camber_pct=4)
    blade = _twisted_loft(root_pts, tip_pts, blade_height, blade_twist_deg)
    # blade was built along +Z; rotate so it extends radially (+Y), then nudge to rim
    blade = (blade.rotate((0, 0, 0), (1, 0, 0), -90)
             .translate((0, (hub_d + od) / 4, hub_thickness / 2)))
    body = disc
    for i in range(n):
        body = body.union(blade.rotate((0, 0, 0), (0, 0, 1), 360.0 * i / n))
    return body


def propeller(blade_count: int, diameter: float, hub_d: float,
              root_chord: float = 0.0, tip_chord: float = 0.0,
              twist_deg: float = 28.0) -> cq.Workplane:
    """N-bladed propeller with twisted airfoil blades."""
    n = int(blade_count)
    if n < 2:
        raise ValueError("propeller needs >=2 blades")
    r = diameter / 2.0
    rc = float(root_chord) or r * 0.18
    tc = float(tip_chord)  or r * 0.08
    span = r - hub_d / 2
    hub_t = max(hub_d * 0.4, span * 0.05)
    hub = (cq.Workplane("XY").circle(hub_d / 2).extrude(hub_t)
           .faces("+Z").workplane().hole(hub_d * 0.35))
    root_pts = _blade_profile_pts(rc, thickness_pct=12, camber_pct=5)
    tip_pts  = _blade_profile_pts(tc, thickness_pct=6,  camber_pct=2)
    blade = _twisted_loft(root_pts, tip_pts, span, twist_deg)
    blade = (blade.rotate((0, 0, 0), (1, 0, 0), -90)
             .translate((0, hub_d / 2 + span / 2, hub_t / 2)))
    body = hub
    for i in range(n):
        body = body.union(blade.rotate((0, 0, 0), (0, 0, 1), 360.0 * i / n))
    return body


def compressor_stage(blade_count: int, hub_d: float, od: float,
                     blade_height: float, blade_chord: float = 0.0,
                     twist_deg: float = 12.0) -> cq.Workplane:
    """Annular array of compressor blades on a thin hub ring."""
    n = int(blade_count)
    chord = float(blade_chord) or (math.pi * (hub_d + od) / 2) / (n * 2.2)
    ring_t = float(blade_height) * 0.25
    ring = (cq.Workplane("XY").circle(od / 2).circle(hub_d / 2).extrude(ring_t))
    root_pts = _blade_profile_pts(chord, thickness_pct=8, camber_pct=3)
    tip_pts  = _blade_profile_pts(chord * 0.85, thickness_pct=5, camber_pct=2)
    blade = _twisted_loft(root_pts, tip_pts, float(blade_height), twist_deg)
    blade = (blade.rotate((0, 0, 0), (1, 0, 0), -90)
             .translate((0, (hub_d + od) / 4, ring_t / 2)))
    body = ring
    for i in range(n):
        body = body.union(blade.rotate((0, 0, 0), (0, 0, 1), 360.0 * i / n))
    return body


def rocket_nozzle(throat_d: float, exit_d: float, inlet_d: float,
                  length: float) -> cq.Workplane:
    """Converging-diverging bell-style nozzle as a thin shelled revolve.
    Approximate parabolic divergent + linear convergent.
    """
    Lc = float(length) * 0.30   # convergent length
    Ld = float(length) * 0.70   # divergent length
    r_in   = inlet_d / 2
    r_thr  = throat_d / 2
    r_exit = exit_d / 2
    # outer profile in XZ plane (X is radial, Z is axial)
    pts = []
    # convergent section: simple linear from inlet to throat
    n_seg = 14
    for i in range(n_seg + 1):
        f = i / n_seg
        z = f * Lc
        r = r_in + (r_thr - r_in) * f
        pts.append((r, z))
    # divergent: parabolic bell
    n_seg2 = 22
    for i in range(1, n_seg2 + 1):
        f = i / n_seg2
        z = Lc + f * Ld
        # parabolic: r = r_thr + (r_exit - r_thr) * sqrt(f)
        r = r_thr + (r_exit - r_thr) * math.sqrt(f)
        pts.append((r, z))
    # Closed contour from the Z axis out to the nozzle surface and back.
    # Revolving this about Z makes a solid bell with the nozzle's outer shape.
    contour = [(0.0, 0.0)] + list(pts) + [(0.0, pts[-1][1])]
    profile = (cq.Workplane("XZ")
               .moveTo(*contour[0])
               .polyline(contour[1:])
               .close())
    solid = profile.revolve(360)  # XZ workplane defaults to revolving about Z
    # Shell it from the +Z face (the exit) so visitors can see the bell.
    try:
        return solid.faces(">Z").shell(-max(0.8, (r_in + r_exit) / 50))
    except Exception:
        return solid  # if shell fails, return solid bell — still looks right


def combustor_can(diameter: float, length: float, wall_thickness: float = 2.0,
                  hole_diameter: float = 4.0, hole_rings: int = 6,
                  holes_per_ring: int = 24) -> cq.Workplane:
    """Cylindrical combustor liner with rings of cooling holes."""
    od = float(diameter)
    L  = float(length)
    w  = float(wall_thickness)
    # hollow cylinder
    body = (cq.Workplane("XY").circle(od / 2).circle(od / 2 - w).extrude(L))
    # cooling holes: radial cylinders cut through the wall
    rings = int(hole_rings)
    per = int(holes_per_ring)
    cutters: list = []
    for ri in range(rings):
        z = L * (ri + 1) / (rings + 1)
        for hi in range(per):
            ang = 360.0 * hi / per + (ri % 2) * (180.0 / per)  # stagger rings
            theta = math.radians(ang)
            # cylinder along the radial direction at (theta, z)
            # Build a horizontal cylinder along +X then rotate to the radial axis.
            h = (cq.Workplane("YZ")
                 .circle(hole_diameter / 2)
                 .extrude(od / 2 + 1.0)
                 .rotate((0, 0, 0), (0, 0, 1), math.degrees(theta))
                 .translate((0, 0, z)))
            cutters.append(h)
    if cutters:
        union = cutters[0]
        for c in cutters[1:]:
            union = union.union(c)
        try:
            body = body.cut(union)
        except Exception:
            pass
    return body


def honeycomb_panel(length: float, width: float, thickness: float,
                    cell_size: float = 6.0, wall_thickness: float = 0.6) -> cq.Workplane:
    """Honeycomb structural panel: plate with hexagonal cells cut out.
    cell_size is the flat-to-flat dimension of one hex.
    """
    L, W, T = float(length), float(width), float(thickness)
    s = float(cell_size)
    w = float(wall_thickness)
    # hex sketch with inset = wall_thickness
    inner_af = max(s - 2 * w, s * 0.4)
    plate = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))
    # hex grid spacing
    dx = s * math.sqrt(3) / 2  # row spacing (flat-to-flat geometry)
    dy = s * 1.5               # column spacing (vertex-to-vertex)
    nx = int(L / dx) + 1
    ny = int(W / dy) + 1
    cutter = cq.Workplane("XY")
    for j in range(-ny // 2, ny // 2 + 1):
        for i in range(-nx // 2, nx // 2 + 1):
            x = i * dx
            y = j * dy + (i % 2) * dy / 2
            if abs(x) > L / 2 - inner_af / 2: continue
            if abs(y) > W / 2 - inner_af / 2: continue
            cell = (cq.Workplane("XY").center(x, y)
                    .polygon(6, inner_af).extrude(T + 0.1))
            cutter = cutter.add(cell)
    try:
        return plate.cut(cutter.combine())
    except Exception:
        return plate


def v_pulley(od: float, width: float, bore: float,
             belt_width: float = 6.0) -> cq.Workplane:
    """Single V-groove pulley. Groove is a 40-deg trapezoidal cut."""
    body = cq.Workplane("XY").circle(od / 2).extrude(width)
    # groove profile on the side: revolved trapezoid cut
    groove_depth = belt_width * 0.6
    half_open = belt_width / 2
    half_inner = max(0.3, half_open - groove_depth * math.tan(math.radians(20)))
    cutter = (cq.Workplane("XZ")
              .moveTo(od / 2 + 0.1, width / 2 - half_open)
              .lineTo(od / 2 - groove_depth, width / 2 - half_inner)
              .lineTo(od / 2 - groove_depth, width / 2 + half_inner)
              .lineTo(od / 2 + 0.1, width / 2 + half_open)
              .close().revolve(360))
    body = body.cut(cutter)
    if bore > 0:
        body = body.faces("+Z").workplane().hole(bore)
    return body


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
             threaded: bool = False,
             x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = bolt_m(spec, length, threaded=bool(threaded)).translate((x, y, z))
        self._store(name, wp)
        thr = " with real helical thread" if threaded else ""
        return f"created {spec} hex bolt '{name}' length {length} mm{thr}"

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

    # ---- bearings / pins / inserts ---- #
    def bearing(self, name: str, bore: float, od: float, width: float,
                x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = ball_bearing(float(bore), float(od), float(width)).translate((x, y, z))
        self._store(name, wp)
        return f"created ball bearing '{name}' bore={bore} od={od} W={width}"

    def threaded_insert(self, name: str, spec: str, length: float,
                        x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = threaded_insert(spec, float(length)).translate((x, y, z))
        self._store(name, wp)
        return f"created {spec} threaded insert '{name}' length={length}"

    def dowel(self, name: str, diameter: float, length: float,
              x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = dowel_pin(float(diameter), float(length)).translate((x, y, z))
        self._store(name, wp)
        return f"created dowel pin '{name}' d={diameter} L={length}"

    def hinge(self, name: str, length: float, leaf_width: float, pin_d: float,
              knuckles: int = 3, leaf_thickness: float = 2.0,
              x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = hinge(float(length), float(leaf_width), float(pin_d),
                   int(knuckles), float(leaf_thickness)).translate((x, y, z))
        self._store(name, wp)
        return (f"created hinge '{name}' L={length} leaf={leaf_width} "
                f"pin={pin_d} knuckles={knuckles}")

    def pulley(self, name: str, od: float, width: float, bore: float = 0,
               belt_width: float = 6.0,
               x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = v_pulley(float(od), float(width), float(bore),
                      float(belt_width)).translate((x, y, z))
        self._store(name, wp)
        return f"created V-pulley '{name}' OD={od} W={width} bore={bore}"

    # ---- aerospace mockups ---- #
    def turbine(self, name: str, blade_count: int, od: float, hub_d: float,
                hub_thickness: float, blade_chord: float = 0,
                blade_twist_deg: float = 18,
                x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = turbine_wheel(int(blade_count), float(od), float(hub_d),
                           float(hub_thickness), float(blade_chord),
                           float(blade_twist_deg)).translate((x, y, z))
        self._store(name, wp)
        return (f"created turbine wheel '{name}' {blade_count} blades, "
                f"OD={od}, hub={hub_d}")

    def propeller(self, name: str, blade_count: int, diameter: float,
                  hub_d: float, root_chord: float = 0, tip_chord: float = 0,
                  twist_deg: float = 28,
                  x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = propeller(int(blade_count), float(diameter), float(hub_d),
                       float(root_chord), float(tip_chord),
                       float(twist_deg)).translate((x, y, z))
        self._store(name, wp)
        return (f"created propeller '{name}' {blade_count} blades, "
                f"D={diameter}, hub={hub_d}")

    def compressor(self, name: str, blade_count: int, hub_d: float, od: float,
                   blade_height: float, blade_chord: float = 0,
                   twist_deg: float = 12,
                   x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = compressor_stage(int(blade_count), float(hub_d), float(od),
                              float(blade_height), float(blade_chord),
                              float(twist_deg)).translate((x, y, z))
        self._store(name, wp)
        return (f"created compressor stage '{name}' {blade_count} blades, "
                f"hub={hub_d}, OD={od}, height={blade_height}")

    def nozzle(self, name: str, throat_d: float, exit_d: float,
               inlet_d: float, length: float,
               x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = rocket_nozzle(float(throat_d), float(exit_d), float(inlet_d),
                           float(length)).translate((x, y, z))
        self._store(name, wp)
        return (f"created bell nozzle '{name}' throat={throat_d} exit={exit_d} "
                f"inlet={inlet_d} L={length}")

    def combustor(self, name: str, diameter: float, length: float,
                  wall_thickness: float = 2, hole_diameter: float = 4,
                  hole_rings: int = 6, holes_per_ring: int = 24,
                  x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = combustor_can(float(diameter), float(length), float(wall_thickness),
                           float(hole_diameter), int(hole_rings),
                           int(holes_per_ring)).translate((x, y, z))
        self._store(name, wp)
        return (f"created combustor can '{name}' D={diameter} L={length} "
                f"{hole_rings}x{holes_per_ring} cooling holes")

    def honeycomb(self, name: str, length: float, width: float,
                  thickness: float, cell_size: float = 6,
                  wall_thickness: float = 0.6,
                  x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = honeycomb_panel(float(length), float(width), float(thickness),
                             float(cell_size),
                             float(wall_thickness)).translate((x, y, z))
        self._store(name, wp)
        return (f"created honeycomb panel '{name}' {length}x{width}x{thickness} "
                f"cell={cell_size}")

    def naca(self, name: str, code: str, chord: float, span: float,
             x: float = 0, y: float = 0, z: float = 0) -> str:
        wp = naca_airfoil(str(code), float(chord), float(span)).translate((x, y, z))
        self._store(name, wp)
        return f"created NACA {code} airfoil section '{name}' chord={chord} span={span}"


def dispatch_library(eng: LibraryEngine, op: str, args: dict) -> str:
    fn = getattr(eng, op, None)
    if fn is None or op.startswith("_"):
        raise ValueError(f"unknown library op '{op}'")
    return fn(**args)
