"""Pre-built complex assemblies — one chat command builds a multi-part scene.

Each helper composes existing primitives (turbine, compressor_stage, bolt,
gear, etc.) into a coherent named assembly. Sub-parts are stored under
'<prefix>_<role>' so you can right-click any one of them individually.

Visual mockups, not engineering-grade. For real turbomachinery design you
want a CFD package, not chat_cad.
"""
from __future__ import annotations

import math

import cadquery as cq

from library import (
    bolt_m, nut_m, washer_m, spur_gear,
    turbine_wheel, propeller, compressor_stage, rocket_nozzle,
    combustor_can,
)


def _store(eng, name: str, wp: cq.Workplane) -> None:
    eng._snapshot()
    eng.parts[name] = wp


class RecipesEngine:
    """Recipes that build multiple named parts at once.

    Each method takes a `prefix` (becomes the part-name root) plus a small
    set of dimensions, and creates a coherent assembly in the scene.
    """

    def __init__(self, cad_engine):
        self.cad = cad_engine

    # ============================================================ #
    # Turbojet — realistic axial-flow gas turbine cross-section    #
    # Components in axial order, matching real engine diagrams:    #
    #   spinner -> inlet -> nacelle -> 8-stage compressor          #
    #   (alternating rotor/stator) -> annular combustor ->         #
    #   2-stage turbine (HP+LP) -> afterburner -> conv-div nozzle  #
    #   + central shaft + rear tail cone                           #
    # ============================================================ #
    def turbojet(self, prefix: str, fan_d: float = 100,
                 length: float = 500, afterburner: bool = True) -> str:
        L = float(length)
        d_out  = float(fan_d)          # nacelle OD
        d_core = d_out * 0.62          # gas-path inner casing
        d_hub  = d_out * 0.32          # spinner / hub
        d_hot  = d_out * 0.50          # hot-gas-path diameter
        d_shaft= d_out * 0.12          # central drive shaft

        # axial proportions (sum = 1.0)
        spin_L = L * 0.06
        inlt_L = L * 0.08
        comp_L = L * 0.32   # 8 stages
        comb_L = L * 0.14
        turb_L = L * 0.10   # 2 stages
        ab_L   = L * 0.15 if afterburner else 0.0
        nozz_L = L - (spin_L + inlt_L + comp_L + comb_L + turb_L + ab_L)

        z = 0.0

        # 1. Front spinner (paraboloid bullet)
        spin_pts = [(0, 0)]
        nseg = 10
        for i in range(1, nseg + 1):
            f = i / nseg
            spin_pts.append((d_hub / 2 * math.sqrt(f), spin_L * f))
        spin_pts.append((0, spin_L))
        spinner = (cq.Workplane("XZ").moveTo(*spin_pts[0])
                   .polyline(spin_pts[1:]).close().revolve(360))
        _store(self.cad, f"{prefix}_spinner", spinner)
        z += spin_L

        # 2. Inlet bell (sharp lip, expanding to nacelle OD)
        ipts = [(d_hub / 2, z),
                (d_out / 2 * 1.02, z + inlt_L * 0.3),
                (d_out / 2, z + inlt_L),
                (d_core / 2 + 0.5, z + inlt_L),
                (d_core / 2 + 0.5, z + inlt_L * 0.5),
                (d_hub / 2, z + inlt_L * 0.5)]
        inlet = (cq.Workplane("XZ").moveTo(*ipts[0])
                 .polyline(ipts[1:]).close().revolve(360))
        _store(self.cad, f"{prefix}_inlet", inlet)
        z += inlt_L

        # 3. Outer nacelle — full-length cylindrical case (thin shell)
        nac_L = comp_L + comb_L + turb_L + ab_L + nozz_L * 0.6
        nacelle = (cq.Workplane("XY")
                   .circle(d_out / 2)
                   .circle(d_out / 2 - 1.5)
                   .extrude(nac_L)
                   .translate((0, 0, z)))
        _store(self.cad, f"{prefix}_nacelle", nacelle)

        # 4. Compressor — 8 axial stages alternating rotor / stator
        n_stages = 8
        stage_w = comp_L / n_stages
        for i in range(n_stages):
            is_rotor = (i % 2 == 0)
            twist = 10 + i * 1.5 if is_rotor else -(8 + i * 1.0)  # stators counter-twisted
            cs = compressor_stage(
                blade_count=18 if is_rotor else 16,
                hub_d=d_core * 0.55,
                od=d_core,
                blade_height=stage_w * 0.7,
                twist_deg=twist,
            )
            cs = cs.translate((0, 0, z + i * stage_w + stage_w * 0.15))
            tag = "rotor" if is_rotor else "stator"
            _store(self.cad, f"{prefix}_comp_{tag}_{i+1}", cs)
        z += comp_L

        # 5. Annular combustor — outer can plus inner liner
        can_outer = combustor_can(diameter=d_core * 1.20, length=comb_L,
                                  wall_thickness=2.0, hole_diameter=2.5,
                                  hole_rings=6, holes_per_ring=28)
        can_outer = can_outer.translate((0, 0, z))
        _store(self.cad, f"{prefix}_combustor_outer", can_outer)
        can_inner = (cq.Workplane("XY").circle(d_core * 0.42)
                     .circle(d_core * 0.35)
                     .extrude(comb_L)
                     .translate((0, 0, z)))
        _store(self.cad, f"{prefix}_combustor_inner", can_inner)
        z += comb_L

        # 6. HP turbine (driven by hot gas, drives the compressor)
        hp = turbine_wheel(blade_count=22, od=d_core * 1.05,
                           hub_d=d_core * 0.42, hub_thickness=turb_L * 0.45,
                           blade_twist_deg=26)
        hp = hp.translate((0, 0, z))
        _store(self.cad, f"{prefix}_turbine_HP", hp)
        # 7. LP turbine (smaller blade height, downstream)
        lp = turbine_wheel(blade_count=24, od=d_core * 1.0,
                           hub_d=d_core * 0.40, hub_thickness=turb_L * 0.45,
                           blade_twist_deg=20)
        lp = lp.translate((0, 0, z + turb_L * 0.55))
        _store(self.cad, f"{prefix}_turbine_LP", lp)
        z += turb_L

        # 8. Afterburner (optional) — long cylindrical section with internal
        #    flameholders represented by 6 radial fins
        if afterburner:
            ab_case = (cq.Workplane("XY").circle(d_core * 1.15)
                       .circle(d_core * 1.07)
                       .extrude(ab_L)
                       .translate((0, 0, z)))
            _store(self.cad, f"{prefix}_afterburner_case", ab_case)
            # Flameholder ring (simplified): an annular plate with cutouts
            fh = (cq.Workplane("XY").circle(d_core * 0.95)
                  .circle(d_core * 0.40)
                  .extrude(ab_L * 0.08)
                  .translate((0, 0, z + ab_L * 0.25)))
            _store(self.cad, f"{prefix}_flameholder", fh)
            z += ab_L

        # 9. Exhaust nozzle (convergent-divergent if afterburning)
        if afterburner:
            noz = rocket_nozzle(throat_d=d_hot * 0.62, exit_d=d_hot * 1.1,
                                inlet_d=d_core * 1.1, length=nozz_L)
        else:
            # Simpler convergent nozzle
            noz = rocket_nozzle(throat_d=d_hot * 0.75, exit_d=d_hot * 0.75,
                                inlet_d=d_core * 0.95, length=nozz_L)
        noz = noz.translate((0, 0, z))
        _store(self.cad, f"{prefix}_nozzle", noz)

        # 10. Central shaft — connects compressor rotors to turbines
        shaft_L = comp_L + comb_L + turb_L + ab_L * 0.3
        shaft = (cq.Workplane("XY").circle(d_shaft / 2)
                 .extrude(shaft_L)
                 .translate((0, 0, spin_L + inlt_L)))
        _store(self.cad, f"{prefix}_shaft", shaft)

        ab_str = "with afterburner" if afterburner else "(no afterburner)"
        n_parts = 13 + (3 if afterburner else 0) + n_stages
        return (f"built realistic turbojet '{prefix}' {ab_str}: "
                f"spinner, inlet bell, nacelle, {n_stages}-stage compressor "
                f"(rotor/stator), annular combustor (outer + inner liner), "
                f"HP+LP turbine, nozzle, central shaft — {n_parts} sub-parts, "
                f"total length {L} mm")

    # ============================================================ #
    # Turbofan — high-bypass with front fan and bypass duct        #
    # ============================================================ #
    def turbofan(self, prefix: str, fan_d: float = 180,
                 length: float = 500) -> str:
        L = float(length)
        d_fan = float(fan_d)
        d_core = d_fan * 0.45
        d_hot = d_fan * 0.42

        fan_L   = L * 0.10
        case_L  = L * 0.45    # bypass duct extends over compressor section
        comp_L  = L * 0.25
        comb_L  = L * 0.15
        turb_L  = L * 0.08
        nozz_L  = L * 0.22

        # 1. Front fan
        fan = propeller(blade_count=22, diameter=d_fan, hub_d=d_core * 1.4,
                        root_chord=d_fan * 0.10, tip_chord=d_fan * 0.05,
                        twist_deg=32)
        fan = fan.translate((0, 0, fan_L * 0.2))
        _store(self.cad, f"{prefix}_fan", fan)

        # 2. Bypass duct (hollow cylindrical case)
        case = (cq.Workplane("XY").circle(d_fan / 2 * 1.05)
                .circle(d_fan / 2 * 0.92)
                .extrude(case_L))
        case = case.translate((0, 0, fan_L * 0.6))
        _store(self.cad, f"{prefix}_bypass_case", case)

        # 3. Core: 3-stage compressor
        cstart = fan_L * 0.6 + (case_L - comp_L) * 0.3
        for i in range(3):
            cs = compressor_stage(blade_count=18, hub_d=d_core * 0.55,
                                  od=d_core, blade_height=(comp_L / 3) * 0.7,
                                  twist_deg=8 + i * 2)
            cs = cs.translate((0, 0, cstart + i * (comp_L / 3)))
            _store(self.cad, f"{prefix}_compressor_{i+1}", cs)

        # 4. Combustor
        cz = cstart + comp_L
        can = combustor_can(diameter=d_core * 1.1, length=comb_L,
                            wall_thickness=2.5, hole_diameter=3,
                            hole_rings=4, holes_per_ring=24)
        can = can.translate((0, 0, cz))
        _store(self.cad, f"{prefix}_combustor", can)

        # 5. HP turbine
        tz = cz + comb_L
        hp = turbine_wheel(blade_count=22, od=d_core * 1.05,
                           hub_d=d_core * 0.4, hub_thickness=turb_L * 0.55,
                           blade_twist_deg=24)
        hp = hp.translate((0, 0, tz))
        _store(self.cad, f"{prefix}_turbine_hp", hp)

        # 6. Exhaust nozzle (mixed)
        nz = tz + turb_L
        noz = rocket_nozzle(throat_d=d_hot * 0.75, exit_d=d_hot,
                            inlet_d=d_core * 0.9, length=nozz_L)
        noz = noz.translate((0, 0, nz))
        _store(self.cad, f"{prefix}_nozzle", noz)

        return (f"built turbofan '{prefix}' (fan, bypass case, compressor x3, "
                f"combustor, HP turbine, nozzle)")

    # ============================================================ #
    # Bolted stack — bolt + washer + plate + washer + nut          #
    # ============================================================ #
    def bolt_stack(self, prefix: str, spec: str = "M6",
                   plate_thickness: float = 10,
                   plate_size: float = 40) -> str:
        from library import _m
        d, (af, hh, nh, wo, wt) = _m(spec)
        # plate
        plate = (cq.Workplane("XY").box(plate_size, plate_size, plate_thickness)
                 .faces("+Z").workplane().hole(d * 1.1))
        _store(self.cad, f"{prefix}_plate", plate)
        # washer under head
        z_bot = plate_thickness / 2 + wt
        w_top = washer_m(spec).translate((0, 0, z_bot))
        _store(self.cad, f"{prefix}_washer_top", w_top)
        # bolt sitting on top washer (head up)
        bolt = bolt_m(spec, length=plate_thickness + wt * 2 + nh + 5,
                      threaded=True)
        # rotate so head is at +Z, shank goes down through plate
        bolt = bolt.rotate((0, 0, 0), (1, 0, 0), 180)
        bolt = bolt.translate((0, 0, plate_thickness / 2 + wt + hh + (plate_thickness + wt * 2 + nh + 5)))
        _store(self.cad, f"{prefix}_bolt", bolt)
        # washer under nut (bottom side)
        w_bot = washer_m(spec).translate((0, 0, -plate_thickness / 2 - wt))
        _store(self.cad, f"{prefix}_washer_bot", w_bot)
        # nut at the bottom
        nut = nut_m(spec).translate((0, 0, -plate_thickness / 2 - wt - nh))
        _store(self.cad, f"{prefix}_nut", nut)
        return (f"built {spec} bolted stack '{prefix}' (plate + 2 washers + "
                f"threaded bolt + nut, 5 sub-parts)")

    # ============================================================ #
    # Gear train — N gears in a line, meshing                      #
    # ============================================================ #
    def gear_train(self, prefix: str, n: int = 4, module: float = 1.5,
                   teeth: int = 20, width: float = 6) -> str:
        n = int(n)
        if n < 2 or n > 8:
            raise ValueError("gear train needs 2-8 gears")
        # pitch diameter
        pd = module * teeth
        # gears are tangent, so center-distance = pd
        for i in range(n):
            g = spur_gear(module, teeth, width, bore=pd * 0.18)
            g = g.translate((i * pd, 0, 0))
            _store(self.cad, f"{prefix}_g{i+1}", g)
        return (f"built gear train '{prefix}' ({n} meshing gears, "
                f"module {module}, {teeth} teeth each)")

    # ============================================================ #
    # Piston + connecting rod — single-cylinder engine snapshot    #
    # ============================================================ #
    def piston_engine(self, prefix: str, bore: float = 50,
                      stroke: float = 60) -> str:
        # cylinder block (open-bottom)
        block_h = stroke * 2.4
        block = (cq.Workplane("XY").box(bore * 2.4, bore * 2.4, block_h,
                                         centered=(True, True, False))
                 .faces(">Z").workplane()
                 .hole(bore + 0.4, block_h * 0.95))
        _store(self.cad, f"{prefix}_block", block)
        # piston (cylinder with skirt)
        piston = (cq.Workplane("XY").circle(bore / 2)
                  .extrude(stroke * 0.55)
                  .faces(">Z").workplane().hole(bore * 0.5, stroke * 0.3))
        piston = piston.translate((0, 0, block_h * 0.55))
        _store(self.cad, f"{prefix}_piston", piston)
        # piston pin
        pin = (cq.Workplane("YZ").circle(bore * 0.16)
               .extrude(bore * 1.05)
               .translate((-bore * 0.55, 0, block_h * 0.55 + stroke * 0.30)))
        _store(self.cad, f"{prefix}_pin", pin)
        # connecting rod (simplified I-shape)
        rod_L = stroke * 1.6
        rod_pts = [(-bore * 0.18, 0), (bore * 0.18, 0),
                   (bore * 0.12, rod_L * 0.85),
                   (bore * 0.30, rod_L), (-bore * 0.30, rod_L),
                   (-bore * 0.12, rod_L * 0.85)]
        rod = (cq.Workplane("XY").polyline(rod_pts).close()
               .extrude(bore * 0.18)
               .rotate((0, 0, 0), (1, 0, 0), 90)
               .translate((0, -bore * 0.09, block_h * 0.55 + stroke * 0.30 - rod_L)))
        _store(self.cad, f"{prefix}_rod", rod)
        # crankpin (offset cylinder)
        crank_z = block_h * 0.55 + stroke * 0.30 - rod_L
        crank = (cq.Workplane("YZ").circle(bore * 0.20)
                 .extrude(bore * 0.5)
                 .translate((-bore * 0.25, 0, crank_z)))
        _store(self.cad, f"{prefix}_crankpin", crank)
        return (f"built piston engine '{prefix}' (block, piston, pin, rod, "
                f"crankpin — bore {bore} mm, stroke {stroke} mm)")
