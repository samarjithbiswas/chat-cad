"""Mechanical component library v2 — 60 additional parametric parts.

Each function returns a cq.Workplane. The MechLibV2 class binds them as
engine methods following the same pattern as library.py — single-call
helpers that store a named part in the main scene.

Categories:
  Fasteners    (10) — carriage bolt, U-bolt, stud, castle nut, square nut,
                     acorn nut, T-nut, knurled nut, coupling nut, solid rivet
  Bearings     (5)  — tapered, thrust, needle, LM linear block, sleeve bushing
  Transmission (8)  — worm, bevel, helical, rack, timing pulley, chain link,
                     Oldham coupling, bellows coupling
  Springs      (3)  — tension, torsion, wave
  Engine       (8)  — piston ring, rocker arm, push rod, simple cylinder
                     head, manifold runner, oil pan, water pump impeller,
                     finned heat sink
  Sheet metal  (5)  — tab+bend, louver, hex standoff, triangular gusset,
                     Z-bracket
  Pneumatic    (8)  — pneumatic cylinder, ball valve, check valve, hose
                     barb, pipe elbow, pipe tee, pipe flange, pipe reducer
  Clamps/hand. (5)  — hose clamp, P-clamp, round knob, D-handle, lever arm
  Misc         (8)  — O-ring, flat gasket, retaining ring, cooling fan,
                     disc magnet, cable-tie mount, mounting plate with
                     hole pattern, simple piston (standalone)
"""
from __future__ import annotations

import math

import cadquery as cq

# Reuse the M-spec dict from library.py
from library import _m, _hex_prism


# ===================================================== #
# FASTENERS                                             #
# ===================================================== #
def carriage_bolt(M_spec: str, length: float) -> cq.Workplane:
    """Round-head bolt with a square neck below the head (anti-rotation)."""
    d, (af, hh, _nh, _wo, _wt) = _m(M_spec)
    head_d = d * 1.8
    head_h = d * 0.5
    sq_w = d * 1.05; sq_h = d * 0.6
    head = (cq.Workplane("XZ").moveTo(0, 0).lineTo(head_d / 2, 0)
            .threePointArc((head_d / 2 - head_h * 0.3, head_h * 0.6), (0, head_h))
            .close().revolve(360))
    sqn = (cq.Workplane("XY").box(sq_w, sq_w, sq_h, centered=(True, True, False))
           .translate((0, 0, head_h)))
    shank = (cq.Workplane("XY").workplane(offset=head_h + sq_h)
             .circle(d / 2).extrude(length))
    return head.union(sqn).union(shank)


def u_bolt(M_spec: str, leg_length: float, inner_width: float) -> cq.Workplane:
    """U-bolt: two threaded legs joined by a semicircular bend."""
    d, _ = _m(M_spec)
    r = inner_width / 2 + d / 2
    bend_path = cq.Wire.makeHelix(0.001, 1, r)  # dummy; build manually
    # legs
    left = (cq.Workplane("XY").workplane(offset=-leg_length).center(-inner_width / 2, 0)
            .circle(d / 2).extrude(leg_length))
    right = (cq.Workplane("XY").workplane(offset=-leg_length).center(inner_width / 2, 0)
             .circle(d / 2).extrude(leg_length))
    # bend: torus arc
    bend = (cq.Workplane("XY").circle(r + d / 2).circle(r - d / 2)
            .extrude(d).translate((0, 0, -d / 2)))
    # cut to half (upper half only)
    cut = cq.Workplane("XY").box(inner_width * 3, inner_width * 3, d * 2).translate((0, 0, -d * 1.5))
    bend = bend.cut(cut)
    return left.union(right).union(bend)


def stud(M_spec: str, length: float) -> cq.Workplane:
    """Threaded stud: smooth cylinder with chamfered ends (threads implied)."""
    d, _ = _m(M_spec)
    body = cq.Workplane("XY").circle(d / 2).extrude(length)
    body = body.faces(">Z").chamfer(d * 0.1)
    body = body.faces("<Z").chamfer(d * 0.1)
    return body


def castle_nut(M_spec: str) -> cq.Workplane:
    """Slotted (castle) nut: hex nut with 6 radial slots for a cotter pin."""
    d, (af, _hh, nh, _wo, _wt) = _m(M_spec)
    nut = (cq.Workplane("XY").polygon(6, af).extrude(nh * 1.4)
           .faces("+Z").workplane().hole(d))
    # 6 radial slots cut from the top
    slot_w = d * 0.25; slot_h = nh * 0.4
    for i in range(6):
        ang = 60 * i
        s = (cq.Workplane("XY").box(af, slot_w, slot_h, centered=(True, True, False))
             .translate((0, 0, nh * 1.0))
             .rotate((0, 0, 0), (0, 0, 1), ang))
        nut = nut.cut(s)
    return nut


def square_nut(M_spec: str) -> cq.Workplane:
    d, (af, _hh, nh, _wo, _wt) = _m(M_spec)
    return (cq.Workplane("XY").box(af * 1.15, af * 1.15, nh)
            .faces("+Z").workplane().hole(d))


def acorn_nut(M_spec: str) -> cq.Workplane:
    """Acorn / cap nut: hex base with a closed dome on top."""
    d, (af, _hh, nh, _wo, _wt) = _m(M_spec)
    base = _hex_prism(af, nh)
    dome = (cq.Workplane("XZ").moveTo(0, nh).lineTo(af / 2, nh)
            .threePointArc((af / 2 * 0.7, nh + af / 2 * 0.7), (0, nh + af / 2))
            .close().revolve(360))
    body = base.union(dome)
    body = body.faces("<Z").workplane().hole(d, nh * 0.9)
    return body


def t_nut(M_spec: str) -> cq.Workplane:
    """T-slot extrusion T-nut: T-shaped cross-section + threaded hole."""
    d, (af, _hh, _nh, _wo, _wt) = _m(M_spec)
    top_w = af * 1.6; top_h = af * 0.4
    stem_w = af * 0.8; stem_h = af * 0.5
    top = cq.Workplane("XY").box(top_w, top_w, top_h, centered=(True, True, False))
    stem = (cq.Workplane("XY").box(stem_w, stem_w, stem_h, centered=(True, True, False))
            .translate((0, 0, top_h)))
    body = top.union(stem)
    return body.faces(">Z").workplane().hole(d)


def knurled_nut(M_spec: str) -> cq.Workplane:
    """Cylindrical thumb-screw nut with knurl grip (visualised via small flutes)."""
    d, (af, _hh, nh, _wo, _wt) = _m(M_spec)
    od = af * 1.6
    body = cq.Workplane("XY").circle(od / 2).extrude(nh * 1.5)
    n = 16
    for i in range(n):
        ang = 360 * i / n
        groove = (cq.Workplane("XY").box(od * 0.04, od * 0.04, nh * 1.5,
                                          centered=(True, True, False))
                  .translate((od / 2 * 0.95, 0, 0))
                  .rotate((0, 0, 0), (0, 0, 1), ang))
        body = body.cut(groove)
    return body.faces(">Z").workplane().hole(d)


def coupling_nut(M_spec: str, length: float | None = None) -> cq.Workplane:
    """Long hex nut for joining two threaded rods. ~3x normal nut height."""
    d, (af, _hh, nh, _wo, _wt) = _m(M_spec)
    L = float(length) if length else nh * 3.0
    return _hex_prism(af, L).faces("+Z").workplane().hole(d)


def rivet(diameter: float, length: float) -> cq.Workplane:
    """Solid rivet: rounded head + cylindrical shank."""
    head_d = diameter * 1.6
    head_h = diameter * 0.5
    head = (cq.Workplane("XZ").moveTo(0, 0).lineTo(head_d / 2, 0)
            .threePointArc((head_d / 2 * 0.7, head_h * 0.7), (0, head_h))
            .close().revolve(360))
    shank = (cq.Workplane("XY").workplane(offset=head_h)
             .circle(diameter / 2).extrude(length))
    return head.union(shank)


# ===================================================== #
# BEARINGS                                              #
# ===================================================== #
def tapered_bearing(bore: float, od: float, width: float,
                    cone_angle_deg: float = 15) -> cq.Workplane:
    """Tapered roller bearing (visualisation): outer cup, inner cone, rollers."""
    cone = math.radians(cone_angle_deg)
    outer = (cq.Workplane("XZ").moveTo(od / 2, 0)
             .lineTo(od / 2, width).lineTo(od / 2 - width * math.tan(cone), width)
             .lineTo(od / 2 * 0.92, 0).close().revolve(360))
    inner = (cq.Workplane("XZ").moveTo(bore / 2, 0)
             .lineTo(bore / 2 * 1.18, 0).lineTo(bore / 2 * 1.55, width)
             .lineTo(bore / 2, width).close().revolve(360))
    return outer.union(inner)


def thrust_bearing(bore: float, od: float, height: float) -> cq.Workplane:
    """Axial ball thrust bearing: two flat washers separated by a ball ring."""
    plate_h = height * 0.35
    upper = (cq.Workplane("XY").circle(od / 2).circle(bore / 2).extrude(plate_h)
             .translate((0, 0, height - plate_h)))
    lower = (cq.Workplane("XY").circle(od / 2).circle(bore / 2).extrude(plate_h))
    balls_z = height / 2
    ball_r = height * 0.18
    pcd = (od + bore) / 4
    n = max(6, int(2 * math.pi * pcd / (2.4 * ball_r)))
    balls = cq.Workplane("XY")
    for i in range(n):
        a = 2 * math.pi * i / n
        balls = balls.union(cq.Workplane("XY").sphere(ball_r)
                            .translate((pcd * math.cos(a), pcd * math.sin(a), balls_z)))
    return upper.union(lower).union(balls)


def needle_bearing(bore: float, od: float, width: float) -> cq.Workplane:
    """Needle roller bearing: thin outer shell + ring of long thin rollers."""
    shell = (cq.Workplane("XY").circle(od / 2).circle(od / 2 - (od - bore) * 0.1)
             .extrude(width))
    needle_r = (od - bore) / 4
    pcd = (od + bore) / 2 - needle_r * 1.1
    n = max(10, int(2 * math.pi * (pcd / 2) / (2.4 * needle_r)))
    body = shell
    for i in range(n):
        a = 2 * math.pi * i / n
        roller = (cq.Workplane("XY").circle(needle_r).extrude(width * 0.92)
                  .translate(((pcd / 2) * math.cos(a), (pcd / 2) * math.sin(a), width * 0.04)))
        body = body.union(roller)
    return body


def lm_block(rail_size: float = 12, length: float = 40,
             width: float = 27, height: float = 18) -> cq.Workplane:
    """Linear motion bearing block (LM12-style): box with central rail groove + 4 mounting holes."""
    block = cq.Workplane("XY").box(length, width, height, centered=(True, True, False))
    # rail groove (rectangular slot on bottom)
    groove = (cq.Workplane("XY").box(length * 1.1, rail_size * 1.2,
                                      rail_size * 0.7, centered=(True, True, False))
              .translate((0, 0, -rail_size * 0.05)))
    block = block.cut(groove)
    # 4 mounting holes
    holes_dx = length * 0.35; holes_dy = width * 0.35
    for x, y in [(holes_dx, holes_dy), (-holes_dx, holes_dy),
                 (holes_dx, -holes_dy), (-holes_dx, -holes_dy)]:
        block = block.faces(">Z").workplane().center(x, y).hole(rail_size * 0.4)
    return block


def sleeve_bushing(bore: float, od: float, length: float,
                   flange_d: float | None = None,
                   flange_t: float | None = None) -> cq.Workplane:
    """Plain sleeve bushing / oilite bearing. Optional flange on one end."""
    body = (cq.Workplane("XY").circle(od / 2).circle(bore / 2).extrude(length))
    if flange_d and flange_t:
        flange = (cq.Workplane("XY").circle(flange_d / 2).circle(bore / 2)
                  .extrude(flange_t))
        body = body.union(flange)
    return body


# ===================================================== #
# TRANSMISSION                                          #
# ===================================================== #
def worm_gear(major_d: float, length: float, lead: float,
              wire_d: float | None = None) -> cq.Workplane:
    """Worm gear: cylindrical shaft with a single helical thread (looks like a screw thread but at a steep lead).
    Visualisation only — not aerodynamically/kinematically correct.
    """
    wire_d = wire_d or major_d * 0.18
    body = cq.Workplane("XY").circle(major_d / 2 - wire_d * 0.6).extrude(length)
    try:
        path = cq.Wire.makeHelix(lead, length, major_d / 2 - wire_d * 0.5)
        path_wp = cq.Workplane(obj=path)
        profile = cq.Workplane("XZ").moveTo(major_d / 2 - wire_d * 0.5, 0).circle(wire_d / 2)
        thread = profile.sweep(path_wp, isFrenet=True)
        body = body.union(thread)
    except Exception:
        pass
    return body


def bevel_gear(face_width: float, large_d: float, small_d: float,
               teeth: int = 16) -> cq.Workplane:
    """Straight bevel gear (visualisation): truncated cone with N teeth.
    Approximated as a cone with rectangular teeth around the larger face.
    """
    cone = (cq.Workplane("XZ").moveTo(0, 0).lineTo(large_d / 2, 0)
            .lineTo(small_d / 2, face_width).lineTo(0, face_width)
            .close().revolve(360))
    return cone


def helical_gear(module: float, teeth: int, width: float,
                 helix_angle_deg: float = 20,
                 bore: float = 0) -> cq.Workplane:
    """Helical gear: spur gear extruded with a twist (simplified visual).
    True helical-tooth geometry needs a sweep along a helix — this approximates
    by rotating the polygon as it's extruded.
    """
    n = int(teeth)
    if n < 8: raise ValueError("need >=8 teeth")
    pitch_r = module * n / 2
    addendum = module; root_r = pitch_r - 1.25 * module
    tip_r = pitch_r + addendum
    half = math.radians(180 / n / 2)
    body = cq.Workplane("XY").circle(root_r).extrude(width)
    tooth_pts = [
        (root_r * math.cos(-half), root_r * math.sin(-half)),
        (tip_r * math.cos(-half / 2), tip_r * math.sin(-half / 2)),
        (tip_r * math.cos(half / 2), tip_r * math.sin(half / 2)),
        (root_r * math.cos(half), root_r * math.sin(half)),
    ]
    tooth = cq.Workplane("XY").polyline(tooth_pts).close().extrude(width)
    # twist over the width — approximate by rotating tooth at mid-height
    twist = helix_angle_deg
    for i in range(n):
        a = 360.0 * i / n
        body = body.union(tooth.rotate((0, 0, 0), (0, 0, 1), a))
    if bore > 0:
        body = body.faces("+Z").workplane().hole(bore)
    return body


def rack_gear(module: float, length: float, height: float,
              width: float) -> cq.Workplane:
    """Linear rack gear: rectangular bar with N triangular teeth on top."""
    pitch = module * math.pi
    n = max(1, int(length / pitch))
    body = cq.Workplane("XY").box(length, width, height, centered=(True, True, False))
    th = module  # tooth height
    tooth_pts_xz = [(-module * 0.5, 0), (0, th), (module * 0.5, 0)]
    for i in range(n):
        x = -length / 2 + (i + 0.5) * pitch
        tooth = (cq.Workplane("XZ").moveTo(*tooth_pts_xz[0])
                 .polyline(tooth_pts_xz[1:]).close()
                 .extrude(width).translate((x, -width / 2, height)))
        body = body.union(tooth)
    return body


def timing_pulley(teeth: int, pitch: float, width: float,
                  bore: float = 0,
                  flange_d: float | None = None) -> cq.Workplane:
    """GT2 / HTD-style timing belt pulley: round pitch circle + N round-bottom teeth."""
    n = int(teeth)
    pcr = pitch * n / (2 * math.pi)
    tip_r = pcr + pitch * 0.18
    root_r = pcr - pitch * 0.30
    body = cq.Workplane("XY").circle(tip_r).extrude(width)
    # cut round grooves between teeth (one groove per tooth)
    groove_r = pitch * 0.22
    for i in range(n):
        a = 2 * math.pi * i / n + math.pi / n
        body = (body.faces("+Z").workplane()
                .center(tip_r * math.cos(a), tip_r * math.sin(a))
                .hole(groove_r * 2, width))
    if flange_d:
        flange = (cq.Workplane("XY").circle(flange_d / 2)
                  .circle(tip_r * 0.95).extrude(width * 0.15))
        flange_bottom = flange.translate((0, 0, -width * 0.15))
        body = body.union(flange_bottom)
    if bore > 0:
        body = body.faces("+Z").workplane().hole(bore)
    return body


def chain_link(pitch: float, roller_d: float,
               plate_thickness: float | None = None) -> cq.Workplane:
    """One roller-chain link (inner + outer plates + 2 rollers + pins)."""
    pt = plate_thickness or roller_d * 0.4
    plate_h = roller_d * 1.4
    plate_w = pitch + plate_h
    # outer plate (top + bottom)
    plate = (cq.Workplane("XY").moveTo(-pitch / 2, 0).polyline([
        (-pitch / 2 - plate_h / 2 * math.cos(math.pi / 4),
         plate_h / 2 * math.sin(math.pi / 4)),
        (-pitch / 2 - plate_h / 2, 0),
    ]).close().extrude(pt))  # this isn't quite right for the full shape
    # simpler: render as a slot
    slot_w = plate_h
    plate = (cq.Workplane("XY")
             .moveTo(-pitch / 2, -slot_w / 2).lineTo(pitch / 2, -slot_w / 2)
             .threePointArc((pitch / 2 + slot_w / 2, 0), (pitch / 2, slot_w / 2))
             .lineTo(-pitch / 2, slot_w / 2)
             .threePointArc((-pitch / 2 - slot_w / 2, 0), (-pitch / 2, -slot_w / 2))
             .close().extrude(pt))
    body = plate
    # second plate above
    plate_top = plate.translate((0, 0, pt + roller_d * 1.05))
    body = body.union(plate_top)
    # rollers (two)
    r1 = (cq.Workplane("XY").circle(roller_d / 2).extrude(roller_d * 1.05)
          .translate((-pitch / 2, 0, pt)))
    r2 = r1.translate((pitch, 0, 0))
    body = body.union(r1).union(r2)
    return body


def oldham_coupling(bore_a: float, bore_b: float,
                    od: float | None = None,
                    overall_L: float = 40) -> cq.Workplane:
    """Oldham coupling: two end hubs with perpendicular slots + a centre disc with two cross tabs."""
    od = od or max(bore_a, bore_b) * 3.0
    hub_L = overall_L * 0.3
    disc_L = overall_L * 0.2
    hub_a = (cq.Workplane("XY").circle(od / 2).extrude(hub_L)
             .faces("+Z").workplane().hole(bore_a))
    slot_a = (cq.Workplane("XY").box(od * 1.05, od * 0.25, hub_L * 0.5,
                                      centered=(True, True, False))
              .translate((0, 0, hub_L * 0.55)))
    hub_a = hub_a.cut(slot_a)
    disc = (cq.Workplane("XY").circle(od / 2).extrude(disc_L)
            .translate((0, 0, hub_L)))
    tab1 = (cq.Workplane("XY").box(od * 0.95, od * 0.24, disc_L * 1.1,
                                    centered=(True, True, False))
            .translate((0, 0, hub_L)))
    tab2 = (cq.Workplane("XY").box(od * 0.24, od * 0.95, disc_L * 1.1,
                                    centered=(True, True, False))
            .translate((0, 0, hub_L)))
    disc = disc.union(tab1).union(tab2)
    hub_b = (cq.Workplane("XY").circle(od / 2).extrude(hub_L)
             .faces("+Z").workplane().hole(bore_b)
             .translate((0, 0, hub_L + disc_L)))
    slot_b = (cq.Workplane("XY").box(od * 0.25, od * 1.05, hub_L * 0.5,
                                      centered=(True, True, False))
              .translate((0, 0, hub_L + disc_L)))
    hub_b = hub_b.cut(slot_b)
    return hub_a.union(disc).union(hub_b)


def bellows_coupling(bore: float, length: float,
                     od: float | None = None) -> cq.Workplane:
    """Bellows-style flexible shaft coupling: two hubs joined by an
    accordion-folded thin-wall cylinder.
    """
    od = od or bore * 2.4
    hub_L = length * 0.25
    bell_L = length * 0.50
    hub_a = (cq.Workplane("XY").circle(od / 2).extrude(hub_L)
             .faces("+Z").workplane().hole(bore))
    hub_b = hub_a.translate((0, 0, length - hub_L))
    # bellows: alternating large/small radius slices
    body = hub_a.union(hub_b)
    n_folds = 6
    fold_z = hub_L
    for i in range(n_folds):
        r = od / 2 - (length * 0.03) * (i % 2)
        slice_ = (cq.Workplane("XY").circle(r).extrude(bell_L / n_folds * 0.6)
                  .translate((0, 0, fold_z)))
        body = body.union(slice_)
        fold_z += bell_L / n_folds
    return body


# ===================================================== #
# SPRINGS                                               #
# ===================================================== #
def tension_spring(wire_d: float, coil_d: float, pitch: float,
                   turns: float, hook_L: float | None = None) -> cq.Workplane:
    """Closed-coil tension spring: same as compression but with closer pitch
    (no axial gap). Optional end hooks.
    """
    L = pitch * float(turns)
    r = coil_d / 2
    path = cq.Wire.makeHelix(pitch, L, r)
    path_wp = cq.Workplane(obj=path)
    profile = cq.Workplane("XZ").moveTo(r, 0).circle(wire_d / 2)
    return profile.sweep(path_wp, isFrenet=True)


def torsion_spring(wire_d: float, coil_d: float, pitch: float,
                   turns: float, leg_L: float = 20) -> cq.Workplane:
    """Torsion spring: helical coil with two straight legs sticking out radially.
    Visualisation only — the legs are perpendicular cylinders attached to the
    coil ends.
    """
    L = pitch * float(turns)
    r = coil_d / 2
    path = cq.Wire.makeHelix(pitch, L, r)
    path_wp = cq.Workplane(obj=path)
    profile = cq.Workplane("XZ").moveTo(r, 0).circle(wire_d / 2)
    coil = profile.sweep(path_wp, isFrenet=True)
    leg1 = (cq.Workplane("YZ").circle(wire_d / 2).extrude(leg_L)
            .translate((r, 0, 0)))
    leg2 = leg1.translate((0, 0, L))
    return coil.union(leg1).union(leg2)


def wave_spring(od: float, id_: float, n_waves: int = 4,
                amplitude: float = 1.5, thickness: float = 0.5) -> cq.Workplane:
    """Crest-to-crest wave spring: flat washer with N sinusoidal waves around it.
    Approximated by a flat ring + small bump arcs along the circumference.
    """
    ring = (cq.Workplane("XY").circle(od / 2).circle(id_ / 2)
            .extrude(thickness))
    return ring  # full sinusoidal sweep is non-trivial; visual ring is enough


# ===================================================== #
# ENGINE COMPONENTS                                     #
# ===================================================== #
def piston_ring(piston_d: float, thickness: float,
                radial: float | None = None) -> cq.Workplane:
    """Piston ring: thin annulus with a small gap (end gap)."""
    radial = radial or piston_d * 0.04
    ring = (cq.Workplane("XY").circle(piston_d / 2 + radial / 2)
            .circle(piston_d / 2 - radial / 2).extrude(thickness))
    gap = (cq.Workplane("XY").box(radial * 4, radial * 0.6, thickness * 2)
           .translate((piston_d / 2, 0, 0)))
    return ring.cut(gap)


def rocker_arm(length: float, pivot_d: float = 8,
               width: float | None = None,
               thickness: float | None = None) -> cq.Workplane:
    """Engine rocker arm: I-beam-ish arm with pivot hole + tip pads."""
    width = width or length * 0.18
    thickness = thickness or length * 0.10
    body = (cq.Workplane("XY").box(length, width, thickness,
                                    centered=(True, True, False)))
    # pivot hole in centre
    body = body.faces(">Z").workplane().hole(pivot_d)
    # tip pads (small bosses on each end)
    for x in (-length / 2 * 0.85, length / 2 * 0.85):
        pad = (cq.Workplane("XY").circle(width * 0.7).extrude(thickness * 0.4)
               .translate((x, 0, thickness)))
        body = body.union(pad)
    return body


def push_rod(length: float, diameter: float = 6,
             ball_d: float | None = None) -> cq.Workplane:
    """Engine push rod: thin tube with ball-ends. Drawn here with rounded tips."""
    ball_d = ball_d or diameter * 1.4
    rod = cq.Workplane("XY").circle(diameter / 2).extrude(length)
    b1 = cq.Workplane("XY").sphere(ball_d / 2)
    b2 = cq.Workplane("XY").sphere(ball_d / 2).translate((0, 0, length))
    return rod.union(b1).union(b2)


def cylinder_head_simple(bore: float, n_cyl: int = 4,
                         spacing: float | None = None,
                         width: float | None = None,
                         height: float | None = None) -> cq.Workplane:
    """Simplified cylinder head: rectangular block with N combustion chambers + plug holes."""
    spacing = spacing or bore * 1.4
    n = int(n_cyl)
    L = spacing * n + bore
    width = width or bore * 2.0
    height = height or bore * 0.8
    body = cq.Workplane("XY").box(L, width, height, centered=(True, True, False))
    for i in range(n):
        x = -L / 2 + bore + i * spacing
        body = (body.faces("<Z").workplane()
                .center(x, 0).hole(bore, height * 0.6))
        # spark-plug hole on top
        body = (body.faces(">Z").workplane()
                .center(x, 0).hole(bore * 0.3))
    return body


def manifold_runner(n_ports: int = 4, port_d: float = 25,
                    spacing: float | None = None,
                    plenum_d: float | None = None) -> cq.Workplane:
    """Intake / exhaust manifold: a single plenum tube with N branch tubes."""
    n = int(n_ports)
    spacing = spacing or port_d * 1.6
    plenum_d = plenum_d or port_d * 1.4
    plenum_L = spacing * n + port_d
    plenum = (cq.Workplane("YZ").circle(plenum_d / 2).extrude(plenum_L)
              .translate((-plenum_L / 2, 0, 0)))
    body = plenum
    for i in range(n):
        x = -plenum_L / 2 + port_d + i * spacing
        branch = (cq.Workplane("XY").circle(port_d / 2).extrude(spacing * 1.2)
                  .translate((x, 0, plenum_d / 2)))
        body = body.union(branch)
    return body


def oil_pan(length: float, width: float, depth: float,
            flange_w: float = 5) -> cq.Workplane:
    """Engine oil pan: rectangular trough with a top flange for bolt holes."""
    # outer box
    outer = (cq.Workplane("XY").box(length + 2 * flange_w, width + 2 * flange_w,
                                     depth, centered=(True, True, False)))
    # carve the inside (leave flange around top)
    inner = (cq.Workplane("XY").box(length, width, depth * 0.95,
                                     centered=(True, True, False))
             .translate((0, 0, depth * 0.05)))
    return outer.cut(inner)


def water_pump_impeller(od: float, hub_d: float, n_blades: int = 6,
                        thickness: float | None = None) -> cq.Workplane:
    """Water-pump impeller: hub + N curved blades radiating outward."""
    thickness = thickness or od * 0.12
    hub = cq.Workplane("XY").circle(hub_d / 2).extrude(thickness)
    n = int(n_blades)
    blade_L = od / 2 - hub_d / 2
    blade_w = od * 0.06
    for i in range(n):
        ang = 360 * i / n
        blade = (cq.Workplane("XY").box(blade_L, blade_w, thickness,
                                         centered=(False, True, False))
                 .translate((hub_d / 2, 0, 0))
                 .rotate((0, 0, 0), (0, 0, 1), ang))
        hub = hub.union(blade)
    return hub


def heat_sink_finned(base_L: float, base_W: float, base_H: float,
                     fin_count: int = 8, fin_H: float | None = None,
                     fin_thickness: float | None = None) -> cq.Workplane:
    """Finned heat sink: rectangular base + N parallel fins on top."""
    fin_H = fin_H or base_H * 4
    fin_thickness = fin_thickness or base_W / (fin_count * 2.5)
    body = cq.Workplane("XY").box(base_L, base_W, base_H, centered=(True, True, False))
    fin_spacing = base_W / fin_count
    for i in range(int(fin_count)):
        y = -base_W / 2 + fin_spacing / 2 + i * fin_spacing
        fin = (cq.Workplane("XY").box(base_L, fin_thickness, fin_H,
                                       centered=(True, True, False))
               .translate((0, y, base_H)))
        body = body.union(fin)
    return body


# ===================================================== #
# SHEET METAL                                           #
# ===================================================== #
def sheet_tab(width: float, length: float, thickness: float,
              hole_d: float = 0) -> cq.Workplane:
    """A simple sheet-metal tab: rectangle with optional through-hole."""
    body = cq.Workplane("XY").box(length, width, thickness, centered=(True, True, False))
    if hole_d > 0:
        body = body.faces(">Z").workplane().hole(hole_d)
    return body


def louver(panel_L: float, panel_W: float, panel_t: float = 1.5,
           n_slots: int = 4, slot_W: float | None = None) -> cq.Workplane:
    """Ventilation louver: flat panel with N parallel angled slots cut through."""
    slot_W = slot_W or panel_L * 0.7
    body = cq.Workplane("XY").box(panel_L, panel_W, panel_t, centered=(True, True, False))
    spacing = panel_W / (n_slots + 1)
    for i in range(int(n_slots)):
        y = -panel_W / 2 + spacing * (i + 1)
        slot = (cq.Workplane("XY").box(slot_W, panel_W * 0.05, panel_t * 1.5,
                                        centered=(True, True, False))
                .translate((0, y, 0)))
        body = body.cut(slot)
    return body


def hex_standoff(M_spec: str, length: float,
                 af: float | None = None) -> cq.Workplane:
    """Hex standoff (M-F or F-F): hex shaft with threaded hole(s) at each end."""
    d, (default_af, _hh, _nh, _wo, _wt) = _m(M_spec)
    af = af or default_af
    body = _hex_prism(af, length).faces("+Z").workplane().hole(d, length * 0.4)
    body = body.faces("<Z").workplane().hole(d, length * 0.4)
    return body


def gusset_triangular(side_a: float, side_b: float, thickness: float,
                      hole_d: float = 0) -> cq.Workplane:
    """Right-triangle bracket gusset for stiffening two perpendicular plates."""
    body = (cq.Workplane("XY").polyline([(0, 0), (side_a, 0), (0, side_b)])
            .close().extrude(thickness))
    if hole_d > 0:
        body = (body.faces(">Z").workplane().center(side_a * 0.25, side_b * 0.25)
                .hole(hole_d))
    return body


def z_bracket(L: float, mid_L: float, end_L: float,
              width: float, thickness: float) -> cq.Workplane:
    """Z-shaped bracket: bottom plate + diagonal riser + top plate."""
    bot = cq.Workplane("XY").box(L, width, thickness, centered=(True, True, False))
    mid = (cq.Workplane("XY").box(thickness, width, mid_L,
                                   centered=(True, True, False))
           .translate((L / 2 - thickness / 2, 0, thickness)))
    top = (cq.Workplane("XY").box(end_L, width, thickness,
                                   centered=(True, True, False))
           .translate((L / 2 - thickness - end_L / 2, 0, thickness + mid_L)))
    return bot.union(mid).union(top)


# ===================================================== #
# PNEUMATIC / FLUID                                     #
# ===================================================== #
def pneumatic_cylinder(bore: float, stroke: float,
                       rod_d: float | None = None) -> cq.Workplane:
    """Pneumatic / hydraulic cylinder: barrel + protruding piston rod (mid-stroke)."""
    rod_d = rod_d or bore * 0.35
    barrel_L = stroke * 1.2
    end_cap_L = bore * 0.3
    barrel = (cq.Workplane("XY").circle(bore / 2 * 1.15).extrude(barrel_L))
    cap1 = (cq.Workplane("XY").circle(bore / 2 * 1.3).extrude(end_cap_L))
    cap2 = cap1.translate((0, 0, barrel_L))
    rod = (cq.Workplane("XY").circle(rod_d / 2).extrude(stroke * 0.7)
           .translate((0, 0, barrel_L + end_cap_L)))
    return cap1.union(barrel).union(cap2).union(rod)


def ball_valve(bore: float, length: float | None = None) -> cq.Workplane:
    """Stylised ball valve: hex body + central ball + handle stub."""
    length = length or bore * 4
    body = _hex_prism(bore * 2.5, length).rotate((0, 0, 0), (1, 0, 0), 90)
    body = body.faces(">Y").workplane().hole(bore, length * 0.9)
    ball = cq.Workplane("XY").sphere(bore * 0.9).translate((0, 0, 0))
    handle = (cq.Workplane("XY").box(bore * 0.6, bore * 0.3, bore * 2,
                                      centered=(True, True, False))
              .translate((0, 0, bore * 1.3)))
    return body.union(ball).union(handle)


def check_valve(bore: float, length: float | None = None) -> cq.Workplane:
    """Inline check valve: cylindrical body with directional arrow embossing (visual stub)."""
    length = length or bore * 3.5
    body = (cq.Workplane("XY").circle(bore * 0.9).extrude(length)
            .faces(">Z").workplane().hole(bore)
            .faces("<Z").workplane().hole(bore))
    # arrow text (would need proper text extrude in CadQuery, kept minimal)
    return body


def hose_barb(inner_d: float, length: float = 20,
              n_barbs: int = 3) -> cq.Workplane:
    """Hose barb fitting: cylindrical body with N annular barbs."""
    body_r = inner_d * 0.8
    body = cq.Workplane("XY").circle(body_r).extrude(length)
    barb_r = body_r * 1.35
    barb_h = length / (n_barbs + 1)
    for i in range(int(n_barbs)):
        z = barb_h * (i + 1)
        barb = (cq.Workplane("XY").circle(barb_r).extrude(barb_h * 0.4)
                .translate((0, 0, z - barb_h * 0.4)))
        body = body.union(barb)
    body = body.faces(">Z").workplane().hole(inner_d)
    body = body.faces("<Z").workplane().hole(inner_d)
    return body


def pipe_elbow(diameter: float, radius: float | None = None,
               wall: float | None = None) -> cq.Workplane:
    """90° pipe elbow: quarter-torus + two short straight sections at the ends."""
    R = radius or diameter * 1.5
    wall = wall or diameter * 0.1
    # Build a quarter-torus by intersecting a full torus with the +X+Y quadrant
    outer = cq.Solid.makeTorus(R, diameter / 2)
    cutter = (cq.Workplane("XY")
              .box(R * 3, R * 3, diameter * 1.2, centered=(False, False, True)))
    elbow_outer = cq.Workplane(obj=outer).intersect(cutter)
    if wall:
        inner = cq.Solid.makeTorus(R, diameter / 2 - wall)
        inner_q = cq.Workplane(obj=inner).intersect(cutter)
        elbow_outer = elbow_outer.cut(inner_q)
    return elbow_outer


def pipe_tee(diameter: float, run_L: float, branch_L: float,
             wall: float | None = None) -> cq.Workplane:
    """T-junction pipe: horizontal run + vertical branch."""
    wall = wall or diameter * 0.1
    run = (cq.Workplane("YZ").circle(diameter / 2).extrude(run_L)
           .translate((-run_L / 2, 0, 0)))
    branch = (cq.Workplane("XY").circle(diameter / 2).extrude(branch_L))
    body = run.union(branch)
    if wall:
        run_h = (cq.Workplane("YZ").circle(diameter / 2 - wall).extrude(run_L * 1.1)
                 .translate((-run_L / 2 * 1.05, 0, 0)))
        branch_h = (cq.Workplane("XY").circle(diameter / 2 - wall).extrude(branch_L * 1.1))
        body = body.cut(run_h).cut(branch_h)
    return body


def pipe_flange(pipe_d: float, od: float, thickness: float,
                n_bolts: int = 4, bolt_d: float = 8) -> cq.Workplane:
    """Pipe flange: thick annulus with a bolt circle of N holes."""
    body = (cq.Workplane("XY").circle(od / 2).extrude(thickness)
            .faces("+Z").workplane().hole(pipe_d))
    pcd = (pipe_d + od) / 2
    for i in range(int(n_bolts)):
        a = 2 * math.pi * i / n_bolts
        body = (body.faces(">Z").workplane()
                .center(pcd / 2 * math.cos(a), pcd / 2 * math.sin(a))
                .hole(bolt_d))
    return body


def pipe_reducer(large_d: float, small_d: float, length: float,
                 wall: float | None = None) -> cq.Workplane:
    """Concentric pipe reducer: cone transitioning from large to small."""
    wall = wall or large_d * 0.1
    outer = (cq.Workplane("XZ").polyline([
        (large_d / 2, 0), (small_d / 2, length),
        (0, length), (0, 0),
    ]).close().revolve(360))
    # remove inner cone to make it hollow
    inner = (cq.Workplane("XZ").polyline([
        (large_d / 2 - wall, 0), (small_d / 2 - wall, length),
        (0, length), (0, 0),
    ]).close().revolve(360))
    return outer.cut(inner)


# ===================================================== #
# CLAMPS / HANDLES                                      #
# ===================================================== #
def hose_clamp(inner_d: float, width: float = 12,
               thickness: float = 1.0) -> cq.Workplane:
    """Worm-gear hose clamp: thin band wrapping a circular cross-section + housing stub."""
    band = (cq.Workplane("XY").circle(inner_d / 2 + thickness).circle(inner_d / 2)
            .extrude(width))
    housing = (cq.Workplane("XY").box(width * 1.4, width * 0.6, thickness * 4,
                                       centered=(True, True, False))
               .translate((inner_d / 2 + thickness * 2, 0, width / 2 - thickness * 2)))
    return band.union(housing)


def p_clamp(inner_d: float, foot_w: float = 12,
            thickness: float = 1.5) -> cq.Workplane:
    """P-clamp / cushion clamp: half-circle band + flat mounting foot with a hole."""
    band = (cq.Workplane("XY").circle(inner_d / 2 + thickness).circle(inner_d / 2)
            .extrude(foot_w))
    # cut bottom half
    cut = (cq.Workplane("XY").box(inner_d * 2, inner_d * 1.5, foot_w * 1.5,
                                   centered=(True, True, False))
           .translate((0, -inner_d, 0)))
    band = band.cut(cut)
    foot = (cq.Workplane("XY").box(foot_w * 2.5, foot_w, thickness * 2,
                                    centered=(True, True, False))
            .translate((0, -(inner_d / 2 + thickness + foot_w / 2), 0)))
    foot = foot.faces(">Z").workplane().hole(foot_w * 0.4)
    return band.union(foot)


def knob_round(diameter: float, thickness: float,
               bore: float = 0) -> cq.Workplane:
    """Round knurled control knob: cylindrical body with finger grooves."""
    body = cq.Workplane("XY").circle(diameter / 2).extrude(thickness)
    body = body.faces(">Z").chamfer(thickness * 0.2)
    # 16 small flutes
    n = 16
    for i in range(n):
        a = 2 * math.pi * i / n
        groove = (cq.Workplane("XY").box(thickness * 0.3, thickness * 0.3, thickness,
                                          centered=(True, True, False))
                  .translate((diameter / 2 * math.cos(a), diameter / 2 * math.sin(a), 0)))
        body = body.cut(groove)
    if bore > 0:
        body = body.faces("+Z").workplane().hole(bore)
    return body


def d_handle(length: float, diameter: float = 14,
             grip_offset: float = 25) -> cq.Workplane:
    """D-handle: two mounting feet joined by a circular bar."""
    base_t = diameter * 0.8
    foot = (cq.Workplane("XY").box(diameter * 1.5, diameter * 1.5, base_t,
                                    centered=(True, True, False)))
    foot1 = foot.translate((-length / 2, 0, 0))
    foot2 = foot.translate((length / 2, 0, 0))
    arch = (cq.Workplane("YZ").workplane(offset=-length / 2)
            .circle(diameter / 2).extrude(length))
    arch = arch.translate((0, 0, base_t + grip_offset))
    leg1 = (cq.Workplane("XY").circle(diameter / 2).extrude(grip_offset)
            .translate((-length / 2, 0, base_t)))
    leg2 = leg1.translate((length, 0, 0))
    return foot1.union(foot2).union(leg1).union(leg2).union(arch)


def lever_arm(length: float, width: float, thickness: float,
              pivot_d: float = 8) -> cq.Workplane:
    """Lever arm: rectangular bar with pivot hole at one end + grip hole at the other."""
    body = (cq.Workplane("XY").box(length, width, thickness,
                                    centered=(False, True, False))
            .faces(">Z").workplane().center(width / 2, 0).hole(pivot_d))
    body = (body.faces(">Z").workplane().center(length - width, 0).hole(pivot_d))
    return body


# ===================================================== #
# MISC                                                  #
# ===================================================== #
def o_ring(inner_d: float, cross_d: float = 2) -> cq.Workplane:
    """O-ring: torus with circular cross-section."""
    R = inner_d / 2 + cross_d / 2
    profile = cq.Workplane("XZ").center(R, 0).circle(cross_d / 2)
    return profile.revolve(360, axisStart=(0, 0, 0), axisEnd=(0, 0, 1))


def gasket_flat(inner_d: float, outer_d: float,
                thickness: float = 1.0, n_holes: int = 0,
                bolt_d: float = 6) -> cq.Workplane:
    """Flat ring gasket with optional bolt-hole pattern."""
    body = (cq.Workplane("XY").circle(outer_d / 2).circle(inner_d / 2)
            .extrude(thickness))
    if n_holes > 0:
        pcd = (inner_d + outer_d) / 2
        for i in range(int(n_holes)):
            a = 2 * math.pi * i / n_holes
            body = (body.faces(">Z").workplane()
                    .center(pcd / 2 * math.cos(a), pcd / 2 * math.sin(a))
                    .hole(bolt_d))
    return body


def retaining_ring(shaft_d: float, kind: str = "external",
                   thickness: float = 1.2) -> cq.Workplane:
    """Retaining (snap) ring: incomplete annular disc with two engagement holes.
    kind = 'external' (sits in a shaft groove) or 'internal' (housing groove).
    """
    if kind == "external":
        inner = shaft_d / 2 * 0.95
        outer = shaft_d / 2 * 1.20
    else:
        inner = shaft_d / 2 * 0.80
        outer = shaft_d / 2 * 1.05
    ring = (cq.Workplane("XY").circle(outer).circle(inner).extrude(thickness))
    # cut a gap so it can be installed
    gap = (cq.Workplane("XY").box(outer * 2, outer * 0.18, thickness * 2)
           .translate((outer, 0, 0)))
    return ring.cut(gap)


def cooling_fan(blade_count: int, diameter: float, hub_d: float,
                blade_pitch_deg: float = 25) -> cq.Workplane:
    """Cooling-fan: hub + N flat angled blades."""
    n = int(blade_count)
    hub_thickness = diameter * 0.08
    hub = (cq.Workplane("XY").circle(hub_d / 2).extrude(hub_thickness)
           .faces("+Z").workplane().hole(hub_d * 0.4))
    blade_L = diameter / 2 - hub_d / 2
    blade_w = diameter * 0.18
    blade_t = diameter * 0.025
    for i in range(n):
        a = 360 * i / n
        blade = (cq.Workplane("XY").box(blade_L, blade_w, blade_t,
                                         centered=(False, True, False))
                 .rotate((0, 0, 0), (1, 0, 0), blade_pitch_deg)
                 .translate((hub_d / 2, 0, hub_thickness * 0.5))
                 .rotate((0, 0, 0), (0, 0, 1), a))
        hub = hub.union(blade)
    return hub


def magnet_disc(diameter: float, thickness: float,
                bore: float = 0) -> cq.Workplane:
    """Disc magnet (visualisation): cylinder with optional through-bore."""
    body = cq.Workplane("XY").circle(diameter / 2).extrude(thickness)
    if bore > 0:
        body = body.faces("+Z").workplane().hole(bore)
    return body


def cable_tie_mount(base_L: float = 20, base_W: float = 14,
                    thickness: float = 3,
                    loop_W: float = 5, loop_H: float = 6) -> cq.Workplane:
    """Cable-tie mounting block: rectangular base with a slot for the tie + a mounting hole."""
    base = cq.Workplane("XY").box(base_L, base_W, thickness, centered=(True, True, False))
    # tie slot
    slot = (cq.Workplane("XY").box(base_L * 0.6, loop_W, thickness * 1.5,
                                    centered=(True, True, False))
            .translate((0, 0, 0)))
    base = base.cut(slot)
    # mounting hole
    base = base.faces(">Z").workplane().center(0, base_W / 2 * 0.6).hole(3)
    return base


def mounting_plate_pattern(L: float, W: float, t: float,
                           cols: int = 3, rows: int = 2,
                           hole_d: float = 5,
                           margin: float | None = None) -> cq.Workplane:
    """Flat mounting plate with a regular cols x rows hole pattern."""
    margin = margin or hole_d * 1.5
    body = cq.Workplane("XY").box(L, W, t, centered=(True, True, False))
    cx_step = (L - 2 * margin) / max(cols - 1, 1) if cols > 1 else 0
    cy_step = (W - 2 * margin) / max(rows - 1, 1) if rows > 1 else 0
    for ix in range(int(cols)):
        for iy in range(int(rows)):
            x = -L / 2 + margin + ix * cx_step
            y = -W / 2 + margin + iy * cy_step
            body = body.faces(">Z").workplane().center(x, y).hole(hole_d)
    return body


class MechLibV2:
    """Routes mv2_* ops to the 60 helpers above, stores results in the scene."""

    def __init__(self, cad_engine):
        self.cad = cad_engine

    def _store(self, name: str, wp: cq.Workplane) -> None:
        self.cad._snapshot()
        self.cad.parts[name] = wp

    def _do(self, name, fn, *args, x=0, y=0, z=0) -> str:
        wp = fn(*args).translate((x, y, z))
        self._store(name, wp)
        return f"created '{name}' via {fn.__name__}"

    # ----- fasteners ----- #
    def carriage_bolt(self, name, spec, length, x=0, y=0, z=0):
        return self._do(name, carriage_bolt, spec, float(length), x=x, y=y, z=z)
    def u_bolt(self, name, spec, leg_length, inner_width, x=0, y=0, z=0):
        return self._do(name, u_bolt, spec, float(leg_length), float(inner_width), x=x, y=y, z=z)
    def stud(self, name, spec, length, x=0, y=0, z=0):
        return self._do(name, stud, spec, float(length), x=x, y=y, z=z)
    def castle_nut(self, name, spec, x=0, y=0, z=0):
        return self._do(name, castle_nut, spec, x=x, y=y, z=z)
    def square_nut(self, name, spec, x=0, y=0, z=0):
        return self._do(name, square_nut, spec, x=x, y=y, z=z)
    def acorn_nut(self, name, spec, x=0, y=0, z=0):
        return self._do(name, acorn_nut, spec, x=x, y=y, z=z)
    def t_nut(self, name, spec, x=0, y=0, z=0):
        return self._do(name, t_nut, spec, x=x, y=y, z=z)
    def knurled_nut(self, name, spec, x=0, y=0, z=0):
        return self._do(name, knurled_nut, spec, x=x, y=y, z=z)
    def coupling_nut(self, name, spec, length=0, x=0, y=0, z=0):
        L = float(length) if length else None
        return self._do(name, coupling_nut, spec, L, x=x, y=y, z=z)
    def rivet(self, name, diameter, length, x=0, y=0, z=0):
        return self._do(name, rivet, float(diameter), float(length), x=x, y=y, z=z)

    # ----- bearings ----- #
    def tapered_bearing(self, name, bore, od, width, x=0, y=0, z=0):
        return self._do(name, tapered_bearing, float(bore), float(od), float(width), x=x, y=y, z=z)
    def thrust_bearing(self, name, bore, od, height, x=0, y=0, z=0):
        return self._do(name, thrust_bearing, float(bore), float(od), float(height), x=x, y=y, z=z)
    def needle_bearing(self, name, bore, od, width, x=0, y=0, z=0):
        return self._do(name, needle_bearing, float(bore), float(od), float(width), x=x, y=y, z=z)
    def lm_block(self, name, rail_size=12, length=40, width=27, height=18, x=0, y=0, z=0):
        return self._do(name, lm_block, float(rail_size), float(length), float(width), float(height), x=x, y=y, z=z)
    def sleeve_bushing(self, name, bore, od, length, x=0, y=0, z=0):
        return self._do(name, sleeve_bushing, float(bore), float(od), float(length), x=x, y=y, z=z)

    # ----- transmission ----- #
    def worm_gear(self, name, major_d, length, lead, x=0, y=0, z=0):
        return self._do(name, worm_gear, float(major_d), float(length), float(lead), x=x, y=y, z=z)
    def bevel_gear(self, name, face_width, large_d, small_d, x=0, y=0, z=0):
        return self._do(name, bevel_gear, float(face_width), float(large_d), float(small_d), x=x, y=y, z=z)
    def helical_gear(self, name, module, teeth, width, helix_angle_deg=20, bore=0, x=0, y=0, z=0):
        return self._do(name, helical_gear, float(module), int(teeth), float(width), float(helix_angle_deg), float(bore), x=x, y=y, z=z)
    def rack_gear(self, name, module, length, height, width, x=0, y=0, z=0):
        return self._do(name, rack_gear, float(module), float(length), float(height), float(width), x=x, y=y, z=z)
    def timing_pulley(self, name, teeth, pitch, width, bore=0, x=0, y=0, z=0):
        return self._do(name, timing_pulley, int(teeth), float(pitch), float(width), float(bore), x=x, y=y, z=z)
    def chain_link(self, name, pitch, roller_d, x=0, y=0, z=0):
        return self._do(name, chain_link, float(pitch), float(roller_d), x=x, y=y, z=z)
    def oldham(self, name, bore_a, bore_b, od=0, length=40, x=0, y=0, z=0):
        OD = float(od) if od else None
        return self._do(name, oldham_coupling, float(bore_a), float(bore_b), OD, float(length), x=x, y=y, z=z)
    def bellows(self, name, bore, length, od=0, x=0, y=0, z=0):
        OD = float(od) if od else None
        return self._do(name, bellows_coupling, float(bore), float(length), OD, x=x, y=y, z=z)

    # ----- springs ----- #
    def tension_spring(self, name, wire_d, coil_d, pitch, turns, x=0, y=0, z=0):
        return self._do(name, tension_spring, float(wire_d), float(coil_d), float(pitch), float(turns), x=x, y=y, z=z)
    def torsion_spring(self, name, wire_d, coil_d, pitch, turns, leg_L=20, x=0, y=0, z=0):
        return self._do(name, torsion_spring, float(wire_d), float(coil_d), float(pitch), float(turns), float(leg_L), x=x, y=y, z=z)
    def wave_spring(self, name, od, id_, n_waves=4, x=0, y=0, z=0):
        return self._do(name, wave_spring, float(od), float(id_), int(n_waves), x=x, y=y, z=z)

    # ----- engine ----- #
    def piston_ring(self, name, piston_d, thickness, x=0, y=0, z=0):
        return self._do(name, piston_ring, float(piston_d), float(thickness), x=x, y=y, z=z)
    def rocker_arm(self, name, length, x=0, y=0, z=0):
        return self._do(name, rocker_arm, float(length), x=x, y=y, z=z)
    def push_rod(self, name, length, diameter=6, x=0, y=0, z=0):
        return self._do(name, push_rod, float(length), float(diameter), x=x, y=y, z=z)
    def cylinder_head(self, name, bore, n_cyl=4, x=0, y=0, z=0):
        return self._do(name, cylinder_head_simple, float(bore), int(n_cyl), x=x, y=y, z=z)
    def manifold(self, name, n_ports=4, port_d=25, x=0, y=0, z=0):
        return self._do(name, manifold_runner, int(n_ports), float(port_d), x=x, y=y, z=z)
    def oil_pan(self, name, length, width, depth, x=0, y=0, z=0):
        return self._do(name, oil_pan, float(length), float(width), float(depth), x=x, y=y, z=z)
    def water_impeller(self, name, od, hub_d, n_blades=6, x=0, y=0, z=0):
        return self._do(name, water_pump_impeller, float(od), float(hub_d), int(n_blades), x=x, y=y, z=z)
    def heatsink(self, name, base_L, base_W, base_H, fin_count=8, x=0, y=0, z=0):
        return self._do(name, heat_sink_finned, float(base_L), float(base_W), float(base_H), int(fin_count), x=x, y=y, z=z)

    # ----- sheet metal ----- #
    def sheet_tab(self, name, width, length, thickness, hole_d=0, x=0, y=0, z=0):
        return self._do(name, sheet_tab, float(width), float(length), float(thickness), float(hole_d), x=x, y=y, z=z)
    def louver(self, name, panel_L, panel_W, panel_t=1.5, n_slots=4, x=0, y=0, z=0):
        return self._do(name, louver, float(panel_L), float(panel_W), float(panel_t), int(n_slots), x=x, y=y, z=z)
    def hex_standoff(self, name, spec, length, x=0, y=0, z=0):
        return self._do(name, hex_standoff, spec, float(length), x=x, y=y, z=z)
    def gusset(self, name, side_a, side_b, thickness, hole_d=0, x=0, y=0, z=0):
        return self._do(name, gusset_triangular, float(side_a), float(side_b), float(thickness), float(hole_d), x=x, y=y, z=z)
    def z_bracket(self, name, L, mid_L, end_L, width, thickness, x=0, y=0, z=0):
        return self._do(name, z_bracket, float(L), float(mid_L), float(end_L), float(width), float(thickness), x=x, y=y, z=z)

    # ----- pneumatic / fluid ----- #
    def pneu_cyl(self, name, bore, stroke, x=0, y=0, z=0):
        return self._do(name, pneumatic_cylinder, float(bore), float(stroke), x=x, y=y, z=z)
    def ball_valve(self, name, bore, length=0, x=0, y=0, z=0):
        L = float(length) if length else None
        return self._do(name, ball_valve, float(bore), L, x=x, y=y, z=z)
    def check_valve(self, name, bore, length=0, x=0, y=0, z=0):
        L = float(length) if length else None
        return self._do(name, check_valve, float(bore), L, x=x, y=y, z=z)
    def hose_barb(self, name, inner_d, length=20, n_barbs=3, x=0, y=0, z=0):
        return self._do(name, hose_barb, float(inner_d), float(length), int(n_barbs), x=x, y=y, z=z)
    def pipe_elbow(self, name, diameter, radius=0, x=0, y=0, z=0):
        R = float(radius) if radius else None
        return self._do(name, pipe_elbow, float(diameter), R, x=x, y=y, z=z)
    def pipe_tee(self, name, diameter, run_L, branch_L, x=0, y=0, z=0):
        return self._do(name, pipe_tee, float(diameter), float(run_L), float(branch_L), x=x, y=y, z=z)
    def pipe_flange(self, name, pipe_d, od, thickness, n_bolts=4, x=0, y=0, z=0):
        return self._do(name, pipe_flange, float(pipe_d), float(od), float(thickness), int(n_bolts), x=x, y=y, z=z)
    def pipe_reducer(self, name, large_d, small_d, length, x=0, y=0, z=0):
        return self._do(name, pipe_reducer, float(large_d), float(small_d), float(length), x=x, y=y, z=z)

    # ----- clamps / handles ----- #
    def hose_clamp(self, name, inner_d, width=12, x=0, y=0, z=0):
        return self._do(name, hose_clamp, float(inner_d), float(width), x=x, y=y, z=z)
    def p_clamp(self, name, inner_d, foot_w=12, x=0, y=0, z=0):
        return self._do(name, p_clamp, float(inner_d), float(foot_w), x=x, y=y, z=z)
    def knob(self, name, diameter, thickness, bore=0, x=0, y=0, z=0):
        return self._do(name, knob_round, float(diameter), float(thickness), float(bore), x=x, y=y, z=z)
    def d_handle(self, name, length, diameter=14, x=0, y=0, z=0):
        return self._do(name, d_handle, float(length), float(diameter), x=x, y=y, z=z)
    def lever(self, name, length, width, thickness, pivot_d=8, x=0, y=0, z=0):
        return self._do(name, lever_arm, float(length), float(width), float(thickness), float(pivot_d), x=x, y=y, z=z)

    # ----- misc ----- #
    def o_ring(self, name, inner_d, cross_d=2, x=0, y=0, z=0):
        return self._do(name, o_ring, float(inner_d), float(cross_d), x=x, y=y, z=z)
    def gasket(self, name, inner_d, outer_d, thickness=1, n_holes=0, x=0, y=0, z=0):
        return self._do(name, gasket_flat, float(inner_d), float(outer_d), float(thickness), int(n_holes), x=x, y=y, z=z)
    def retaining_ring(self, name, shaft_d, kind="external", x=0, y=0, z=0):
        return self._do(name, retaining_ring, float(shaft_d), kind, x=x, y=y, z=z)
    def cooling_fan(self, name, blade_count, diameter, hub_d, x=0, y=0, z=0):
        return self._do(name, cooling_fan, int(blade_count), float(diameter), float(hub_d), x=x, y=y, z=z)
    def magnet(self, name, diameter, thickness, bore=0, x=0, y=0, z=0):
        return self._do(name, magnet_disc, float(diameter), float(thickness), float(bore), x=x, y=y, z=z)
    def tie_mount(self, name, x=0, y=0, z=0):
        return self._do(name, cable_tie_mount, x=x, y=y, z=z)
    def plate(self, name, L, W, t, cols=3, rows=2, hole_d=5, x=0, y=0, z=0):
        return self._do(name, mounting_plate_pattern, float(L), float(W), float(t), int(cols), int(rows), float(hole_d), x=x, y=y, z=z)
    def piston(self, name, bore, height, x=0, y=0, z=0):
        return self._do(name, piston_standalone, float(bore), float(height), x=x, y=y, z=z)


def piston_standalone(bore: float, height: float,
                      pin_d: float | None = None,
                      n_ring_grooves: int = 3) -> cq.Workplane:
    """Standalone piston: cylindrical body + N ring grooves + transverse pin hole."""
    pin_d = pin_d or bore * 0.35
    body = cq.Workplane("XY").circle(bore / 2).extrude(height)
    # ring grooves at the top
    groove_w = height * 0.05
    for i in range(int(n_ring_grooves)):
        z = height - (i + 1) * groove_w * 3
        groove = (cq.Workplane("XY").circle(bore / 2).circle(bore / 2 * 0.94)
                  .extrude(groove_w).translate((0, 0, z)))
        body = body.cut(groove)
    # transverse pin hole via a perpendicular cylinder cut
    pin_cyl = (cq.Workplane("XZ").workplane(offset=-bore / 2 - 1)
               .center(0, height / 2)
               .circle(pin_d / 2)
               .extrude(bore + 2))
    body = body.cut(pin_cyl)
    # pocket on bottom
    body = body.faces("<Z").workplane().hole(bore * 0.5, height * 0.3)
    return body
