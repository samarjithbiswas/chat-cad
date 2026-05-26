"""Real CAD kernel wrapper around CadQuery (OpenCascade).

Each operation mutates a named-part dictionary. After every op the caller
should re-export the active scene to STL so the browser viewer can refresh.
"""
from __future__ import annotations

import copy
import math
import os
from typing import Any

import cadquery as cq

from sketch_engine import SketchEngine
from assembly_engine import AssemblyEngine
from library import LibraryEngine
from materials import MaterialsEngine
from profiles import ProfilesEngine
from step_io import StepIOEngine
from sheet_metal import SheetMetalEngine
from knowledge import KnowledgeStore


class CadEngine:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.parts: dict[str, cq.Workplane] = {}
        self.history: list[dict[str, cq.Workplane]] = []
        self.sketches = SketchEngine(self.parts)
        self.assemblies = AssemblyEngine(self.parts)
        self.library = LibraryEngine(self)
        self.materials = MaterialsEngine(self)
        self.profiles = ProfilesEngine(self)
        self.step_io = StepIOEngine(self)
        self.sheet = SheetMetalEngine(self)
        self.knowledge = KnowledgeStore(os.path.join(output_dir, "..", "knowledge"))

    # ---------- internal ----------
    def _snapshot(self) -> None:
        self.history.append(copy.copy(self.parts))
        if len(self.history) > 50:
            self.history.pop(0)

    def _require(self, name: str) -> cq.Workplane:
        if name not in self.parts:
            raise KeyError(f"no part named '{name}'. existing: {list(self.parts)}")
        return self.parts[name]

    # ---------- primitives ----------
    def box(self, name: str, length: float, width: float, height: float,
            x: float = 0, y: float = 0, z: float = 0) -> str:
        self._snapshot()
        p = cq.Workplane("XY").box(length, width, height).translate((x, y, z))
        self.parts[name] = p
        return f"created box '{name}' {length}x{width}x{height} at ({x},{y},{z})"

    def cylinder(self, name: str, radius: float, height: float,
                 x: float = 0, y: float = 0, z: float = 0) -> str:
        self._snapshot()
        p = cq.Workplane("XY").cylinder(height, radius).translate((x, y, z))
        self.parts[name] = p
        return f"created cylinder '{name}' r={radius} h={height} at ({x},{y},{z})"

    def sphere(self, name: str, radius: float,
               x: float = 0, y: float = 0, z: float = 0) -> str:
        self._snapshot()
        p = cq.Workplane("XY").sphere(radius).translate((x, y, z))
        self.parts[name] = p
        return f"created sphere '{name}' r={radius} at ({x},{y},{z})"

    def cone(self, name: str, radius1: float, radius2: float, height: float,
             x: float = 0, y: float = 0, z: float = 0) -> str:
        self._snapshot()
        pts = [(0, 0), (radius1, 0), (radius2, height), (0, height)]
        p = (cq.Workplane("XZ").polyline(pts).close().revolve(360)
             .translate((x, y, z)))
        self.parts[name] = p
        return f"created cone '{name}' r1={radius1} r2={radius2} h={height}"

    def torus(self, name: str, major_radius: float, minor_radius: float,
              x: float = 0, y: float = 0, z: float = 0) -> str:
        self._snapshot()
        solid = cq.Solid.makeTorus(major_radius, minor_radius)
        p = cq.Workplane(obj=solid).translate((x, y, z))
        self.parts[name] = p
        return f"created torus '{name}' R={major_radius} r={minor_radius}"

    def wedge(self, name: str, dx: float, dy: float, dz: float,
              x: float = 0, y: float = 0, z: float = 0) -> str:
        self._snapshot()
        solid = cq.Solid.makeWedge(dx, dy, dz, 0, 0, dx, 0)
        p = cq.Workplane(obj=solid).translate((x, y, z))
        self.parts[name] = p
        return f"created wedge '{name}' {dx}x{dy}x{dz}"

    def polygon(self, name: str, sides: int, radius: float, height: float,
                x: float = 0, y: float = 0, z: float = 0) -> str:
        """Regular n-gon prism extruded along Z."""
        self._snapshot()
        p = (cq.Workplane("XY").polygon(int(sides), 2 * float(radius))
             .extrude(float(height)).translate((x, y, z)))
        self.parts[name] = p
        return f"created {sides}-gon prism '{name}' r={radius} h={height}"

    def text_3d(self, name: str, text: str, size: float = 10,
                height: float = 2, font: str = "Arial",
                x: float = 0, y: float = 0, z: float = 0) -> str:
        self._snapshot()
        p = (cq.Workplane("XY")
             .text(text, float(size), float(height), font=font)
             .translate((x, y, z)))
        self.parts[name] = p
        return f"created 3D text '{name}' = {text!r}"

    def scale(self, name: str, sx: float, sy: float | None = None,
              sz: float | None = None) -> str:
        """Uniform scale if only sx is given; per-axis otherwise.
        Implemented via OpenCascade transform on the underlying shape.
        """
        from OCP.gp import gp_GTrsf, gp_Mat, gp_XYZ
        from OCP.BRepBuilderAPI import BRepBuilderAPI_GTransform
        self._snapshot()
        sy = sx if sy is None else sy
        sz = sx if sz is None else sz
        gtrsf = gp_GTrsf()
        mat = gp_Mat(float(sx), 0, 0, 0, float(sy), 0, 0, 0, float(sz))
        gtrsf.SetVectorialPart(mat)
        gtrsf.SetTranslationPart(gp_XYZ(0, 0, 0))
        shape = self._require(name).val().wrapped
        new_shape = BRepBuilderAPI_GTransform(shape, gtrsf, True).Shape()
        self.parts[name] = cq.Workplane(obj=cq.Shape.cast(new_shape))
        return f"scaled '{name}' by ({sx},{sy},{sz})"

    # ---------- transforms ----------
    def translate(self, name: str, dx: float, dy: float, dz: float) -> str:
        self._snapshot()
        self.parts[name] = self._require(name).translate((dx, dy, dz))
        return f"translated '{name}' by ({dx},{dy},{dz})"

    def rotate(self, name: str, axis: str, degrees: float) -> str:
        self._snapshot()
        axis = axis.upper()
        vec = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[axis]
        self.parts[name] = self._require(name).rotate((0, 0, 0), vec, degrees)
        return f"rotated '{name}' {degrees}deg about {axis}"

    # ---------- booleans ----------
    def union(self, out: str, a: str, b: str) -> str:
        self._snapshot()
        self.parts[out] = self._require(a).union(self._require(b))
        return f"union '{out}' = '{a}' u '{b}'"

    def cut(self, out: str, a: str, b: str) -> str:
        self._snapshot()
        self.parts[out] = self._require(a).cut(self._require(b))
        return f"cut '{out}' = '{a}' - '{b}'"

    def intersect(self, out: str, a: str, b: str) -> str:
        self._snapshot()
        self.parts[out] = self._require(a).intersect(self._require(b))
        return f"intersect '{out}' = '{a}' n '{b}'"

    # ---------- features ----------
    def fillet(self, name: str, radius: float) -> str:
        self._snapshot()
        self.parts[name] = self._require(name).edges().fillet(radius)
        return f"filleted all edges of '{name}' r={radius}"

    def chamfer(self, name: str, distance: float) -> str:
        self._snapshot()
        self.parts[name] = self._require(name).edges().chamfer(distance)
        return f"chamfered all edges of '{name}' d={distance}"

    def shell(self, name: str, thickness: float, face: str = "+Z") -> str:
        self._snapshot()
        self.parts[name] = self._require(name).faces(face).shell(-thickness)
        return f"shelled '{name}' t={thickness} (open face {face})"

    def hole(self, name: str, radius: float, depth: float | None = None) -> str:
        self._snapshot()
        p = self._require(name).faces("+Z").workplane().hole(radius * 2, depth)
        self.parts[name] = p
        return f"drilled hole r={radius} in top face of '{name}'"

    # ---------- selective fillet / chamfer ---------- #
    def fillet_edges(self, name: str, radius: float,
                     selector: str = "all") -> str:
        """Fillet edges matching a CadQuery selector.
        Common selectors: 'all', '+Z' (top), '-Z' (bottom), '|Z' (vertical),
        '>>Z[-1]' (highest edge in Z), '%LINE'.
        """
        self._snapshot()
        wp = self._require(name)
        edges = wp.edges() if selector == "all" else wp.edges(selector)
        if len(edges.vals()) == 0:
            raise RuntimeError(f"no edges matched selector '{selector}'")
        self.parts[name] = edges.fillet(float(radius))
        return f"filleted {len(edges.vals())} edge(s) of '{name}' r={radius} ({selector})"

    def chamfer_edges(self, name: str, distance: float,
                      selector: str = "all") -> str:
        self._snapshot()
        wp = self._require(name)
        edges = wp.edges() if selector == "all" else wp.edges(selector)
        if len(edges.vals()) == 0:
            raise RuntimeError(f"no edges matched selector '{selector}'")
        self.parts[name] = edges.chamfer(float(distance))
        return f"chamfered {len(edges.vals())} edge(s) of '{name}' d={distance} ({selector})"

    # ---------- finished holes ---------- #
    def counterbore(self, name: str, diameter: float, cbore_diameter: float,
                    cbore_depth: float, depth: float | None = None,
                    face: str = "+Z") -> str:
        """Drill a counterbore on `face`. Through-hole if depth omitted."""
        self._snapshot()
        wp = self._require(name).faces(face).workplane()
        self.parts[name] = wp.cboreHole(float(diameter),
                                        float(cbore_diameter),
                                        float(cbore_depth),
                                        None if depth is None else float(depth))
        return (f"counterbore on '{name}' d={diameter} cbore={cbore_diameter} "
                f"cdepth={cbore_depth} ({face})")

    def countersink(self, name: str, diameter: float, csk_diameter: float,
                    csk_angle: float = 82.0, depth: float | None = None,
                    face: str = "+Z") -> str:
        self._snapshot()
        wp = self._require(name).faces(face).workplane()
        self.parts[name] = wp.cskHole(float(diameter),
                                      float(csk_diameter),
                                      float(csk_angle),
                                      None if depth is None else float(depth))
        return (f"countersink on '{name}' d={diameter} csk={csk_diameter} "
                f"angle={csk_angle} ({face})")

    def tapped_hole(self, name: str, M_spec: str, depth: float,
                    face: str = "+Z") -> str:
        """Threaded hole sized for an M-spec bolt.
        Visualisation only: the hole diameter is the tap-drill size; no
        helical thread geometry is cut (would multiply triangle count ~50x).
        """
        from library import _m
        d, _ = _m(M_spec)
        # Tap-drill diameter ~ d * 0.8 (rough approximation; ISO has tables)
        tap_d = d * 0.8
        self._snapshot()
        p = (self._require(name).faces(face).workplane()
             .hole(tap_d, float(depth)))
        self.parts[name] = p
        return f"tapped hole {M_spec} depth {depth} on '{name}' ({face})"

    # ---------- sketch-driven features on an existing part ---------- #
    def boss_extrude(self, base: str, sketch: str, depth: float,
                     face: str = "+Z") -> str:
        """Extrude a sketch from a face of `base` and union it onto base."""
        self._snapshot()
        sk = self.sketches._s(sketch)
        wp = self.sketches._build_workplane(sk)
        boss = wp.extrude(float(depth))
        self.parts[base] = self._require(base).union(boss)
        return f"boss-extruded sketch '{sketch}' by {depth} onto '{base}'"

    def cut_extrude(self, base: str, sketch: str, depth: float,
                    face: str = "+Z") -> str:
        """Extrude a sketch and CUT it from `base` (pocket / hole pattern)."""
        self._snapshot()
        sk = self.sketches._s(sketch)
        wp = self.sketches._build_workplane(sk)
        tool = wp.extrude(float(depth))
        self.parts[base] = self._require(base).cut(tool)
        return f"cut-extruded sketch '{sketch}' by {depth} from '{base}'"

    # ---------- pattern along a sketch path ---------- #
    def pattern_along_curve(self, prefix: str, src: str, sketch: str,
                            count: int) -> str:
        """Place `count` copies of `src` at evenly spaced points along the
        first chain of lines in `sketch`. Simple polyline approximation; great
        for bolt-circles defined by a sketch.
        """
        self._snapshot()
        sk = self.sketches._s(sketch)
        # collect ordered points from line chain
        if not sk.lines and not sk.circles:
            raise RuntimeError(f"sketch '{sketch}' has no path to follow")
        if sk.circles:
            # use first circle's center + radius as a bolt-circle
            (c, r) = list(sk.circles.values())[0]
            cx, cy, _ = sk.points[c]
        else:
            # use centroid of all line endpoints as anchor; fall back to averaging
            pts = [sk.points[p][:2] for ln in sk.lines.values() for p in ln]
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            r = max(((p[0] - cx) ** 2 + (p[1] - cy) ** 2) ** 0.5 for p in pts)
        base = self._require(src)
        made = []
        import math
        for i in range(int(count)):
            a = 2 * math.pi * i / int(count)
            x = cx + r * math.cos(a)
            y = cy + r * math.sin(a)
            nm = f"{prefix}_{i}"
            self.parts[nm] = base.translate((x, y, 0))
            made.append(nm)
        return f"pattern-along-curve '{prefix}': {made}"

    # ---------- patterns / mirror ---------- #
    def mirror(self, out: str, src: str, plane: str = "XY") -> str:
        """Mirror a part across XY, XZ, or YZ plane; result stored as 'out'."""
        self._snapshot()
        plane = plane.upper()
        if plane not in ("XY", "XZ", "YZ"):
            raise ValueError("plane must be XY, XZ, or YZ")
        self.parts[out] = self._require(src).mirror(mirrorPlane=plane)
        return f"mirrored '{src}' across {plane} -> '{out}'"

    def linear_pattern(self, prefix: str, src: str, dx: float, dy: float,
                       dz: float, count: int) -> str:
        """Stamp `count` copies of `src` at (i*dx, i*dy, i*dz) for i=0..count-1.
        Copies are named '<prefix>_0', '<prefix>_1', ...
        """
        self._snapshot()
        base = self._require(src)
        made = []
        for i in range(int(count)):
            n = f"{prefix}_{i}"
            self.parts[n] = base.translate((i * dx, i * dy, i * dz))
            made.append(n)
        return f"linear pattern: {made}"

    def polar_pattern(self, prefix: str, src: str, count: int,
                      total_angle: float = 360.0, axis: str = "Z") -> str:
        """Stamp `count` copies of `src` rotated around world axis.
        First copy is at 0 deg; copies are 'prefix_0' .. 'prefix_{N-1}'.
        """
        self._snapshot()
        axis = axis.upper()
        vec = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[axis]
        base = self._require(src)
        n = int(count)
        step = float(total_angle) / max(n, 1) if total_angle != 360 else 360.0 / n
        made = []
        for i in range(n):
            nm = f"{prefix}_{i}"
            self.parts[nm] = base.rotate((0, 0, 0), vec, i * step)
            made.append(nm)
        return f"polar pattern around {axis}: {made}"

    # ---------- advanced 3D ops ----------
    def sweep(self, part: str, profile_sketch: str, path_sketch: str) -> str:
        """Sweep a 2D profile sketch along a 2D path sketch."""
        self._snapshot()
        prof_sk = self.sketches.sketches.get(profile_sketch)
        path_sk = self.sketches.sketches.get(path_sketch)
        if prof_sk is None:
            raise KeyError(f"no sketch '{profile_sketch}'")
        if path_sk is None:
            raise KeyError(f"no sketch '{path_sketch}'")
        try:
            prof_wp = self.sketches._build_workplane(prof_sk)
            path_wp = self.sketches._build_workplane(path_sk)
            solid = prof_wp.sweep(path_wp)
        except Exception as e:
            raise RuntimeError(f"sweep failed: {e}")
        self.parts[part] = solid
        return (f"swept profile '{profile_sketch}' along path '{path_sketch}' "
                f"-> part '{part}'")

    def loft(self, part: str, sketches: list[str]) -> str:
        """Loft through >= 2 sketch profiles."""
        self._snapshot()
        if not sketches or len(sketches) < 2:
            raise ValueError("loft needs at least 2 sketches")
        try:
            wp = cq.Workplane("XY")
            # accumulate each profile's wires into a single workplane stack
            for sn in sketches:
                sk = self.sketches.sketches.get(sn)
                if sk is None:
                    raise KeyError(f"no sketch '{sn}'")
                pw = self.sketches._build_workplane(sk)
                for w in pw.vals():
                    wp = wp.add(w)
            solid = wp.loft(combine=True)
        except Exception as e:
            raise RuntimeError(f"loft failed: {e}")
        self.parts[part] = solid
        return f"lofted through {sketches} -> part '{part}'"

    def helix(self, part: str, radius: float, pitch: float, height: float,
              x: float = 0, y: float = 0, z: float = 0) -> str:
        """Helical solid: sweep small circle along helical wire."""
        self._snapshot()
        try:
            helix_wire = cq.Wire.makeHelix(float(pitch), float(height),
                                           float(radius))
            path = cq.Workplane(obj=helix_wire)
            prof_r = float(pitch) / 4.0
            profile = cq.Workplane("XY").circle(prof_r)
            solid = profile.sweep(path, isFrenet=True)
            solid = solid.translate((x, y, z))
        except Exception as e:
            raise RuntimeError(f"helix failed: {e}")
        self.parts[part] = solid
        return (f"created helix '{part}' r={radius} pitch={pitch} h={height} "
                f"at ({x},{y},{z})")

    def thread(self, name: str, radius: float, pitch: float, length: float,
               x: float = 0, y: float = 0, z: float = 0) -> str:
        """External triangular thread (60-deg) along a helix."""
        self._snapshot()
        try:
            helix_wire = cq.Wire.makeHelix(float(pitch), float(length),
                                           float(radius))
            path = cq.Workplane(obj=helix_wire)
            # 60-deg included angle: half-angle 30, so base/2 = tri_h * tan(30)
            tri_h = float(pitch) * 0.6
            base = 2 * tri_h * math.tan(math.radians(30))
            # profile on XZ plane (X=radial outward, Z=axial); auto-attaches to path start
            pts = [(0, -base / 2), (tri_h, 0), (0, base / 2)]
            profile = cq.Workplane("XZ").polyline(pts).close()
            solid = profile.sweep(path, isFrenet=True)
            solid = solid.translate((x, y, z))
        except Exception as e:
            raise RuntimeError(f"thread failed: {e}")
        self.parts[name] = solid
        return (f"created thread '{name}' r={radius} pitch={pitch} L={length} "
                f"at ({x},{y},{z})")

    # ---------- bookkeeping ----------
    def delete(self, name: str) -> str:
        self._snapshot()
        self._require(name)
        del self.parts[name]
        return f"deleted '{name}'"

    def duplicate(self, src: str, dst: str | None = None,
                  dx: float = 5, dy: float = 0, dz: float = 0) -> str:
        """Copy a part to a new name, offset by (dx,dy,dz) to avoid overlap."""
        self._snapshot()
        if dst is None:
            i = 2
            while f"{src}_{i}" in self.parts:
                i += 1
            dst = f"{src}_{i}"
        self.parts[dst] = self._require(src).translate((float(dx), float(dy), float(dz)))
        return f"duplicated '{src}' -> '{dst}' offset ({dx},{dy},{dz})"

    def list_parts(self) -> str:
        if not self.parts:
            return "scene is empty"
        lines = []
        for n, p in self.parts.items():
            try:
                bb = p.val().BoundingBox()
                lines.append(f"  {n}: bbox {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f}")
            except Exception:
                lines.append(f"  {n}: (no bbox)")
        return "parts:\n" + "\n".join(lines)

    def clear(self) -> str:
        self._snapshot()
        self.parts.clear()
        return "scene cleared"

    def undo(self) -> str:
        if not self.history:
            return "nothing to undo"
        self.parts = self.history.pop()
        return "undid last operation"

    # ---------- export ----------
    def _combined(self) -> cq.Workplane | None:
        if not self.parts:
            return None
        objs = list(self.parts.values())
        out = objs[0]
        for o in objs[1:]:
            try:
                out = out.add(o)
            except Exception:
                pass
        return out

    def export_stl(self, filename: str = "scene.stl") -> str:
        path = os.path.join(self.output_dir, filename)
        combined = self._combined()
        if combined is None:
            # write empty placeholder
            with open(path, "wb") as f:
                f.write(b"solid empty\nendsolid empty\n")
            return path
        cq.exporters.export(combined, path, exportType="STL")
        return path

    def export_step(self, filename: str = "scene.step") -> str:
        path = os.path.join(self.output_dir, filename)
        combined = self._combined()
        if combined is None:
            raise RuntimeError("scene is empty, nothing to export")
        cq.exporters.export(combined, path, exportType="STEP")
        return path

    def export_part_stl(self, name: str) -> str:
        """Export one part to <name>.stl with fine tessellation (smoother
        curved surfaces in the viewer). Returns the absolute path.
        """
        self._require(name)
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
        path = os.path.join(self.output_dir, f"part_{safe}.stl")
        # tolerance: lower = more triangles, smoother curves.
        # 0.05 mm linear + 0.1 rad angular is high-res but still fast.
        cq.exporters.export(self.parts[name], path, exportType="STL",
                            tolerance=0.05, angularTolerance=0.1)
        return path

    def manifest(self) -> list[dict]:
        """Return a manifest of parts with a deterministic colour per name.
        Used by the viewer to render each part as its own mesh.
        """
        import colorsys
        items = []
        for n in self.parts:
            # SolidWorks-ish defaults: assemblies = silver, normal parts = hashed hue
            if n.startswith("_asm_"):
                col = "#b8bdc4"
            else:
                h = (abs(hash(n)) % 360) / 360.0
                r, g, b = colorsys.hls_to_rgb(h, 0.58, 0.55)
                col = "#{:02x}{:02x}{:02x}".format(
                    int(r * 255), int(g * 255), int(b * 255))
            try:
                bb = self.parts[n].val().BoundingBox()
                bbox = [bb.xmin, bb.ymin, bb.zmin, bb.xmax, bb.ymax, bb.zmax]
            except Exception:
                bbox = None
            items.append({"name": n, "color": col, "bbox": bbox})
        return items


# ---------- dispatch table used by both Claude tool_use and parser ----------
def dispatch(engine: CadEngine, op: str, args: dict[str, Any]) -> str:
    """Route ops to the right sub-engine.

    Names prefixed `sketch_` go to engine.sketches (method name with prefix
    stripped). Names prefixed `asm_` go to engine.assemblies. Everything else
    is a 3D-part op on the main CadEngine.
    """
    if op.startswith("sketch_"):
        sub = op[len("sketch_"):]
        fn = getattr(engine.sketches, sub, None)
        if fn is None or sub.startswith("_"):
            raise ValueError(f"unknown sketch op '{op}'")
        return fn(**args)
    if op.startswith("lib_"):
        sub = op[len("lib_"):]
        fn = getattr(engine.library, sub, None)
        if fn is None or sub.startswith("_"):
            raise ValueError(f"unknown library op '{op}'")
        return fn(**args)
    if op.startswith("mat_"):
        sub = op[len("mat_"):]
        fn = getattr(engine.materials, sub, None)
        if fn is None or sub.startswith("_"):
            raise ValueError(f"unknown materials op '{op}'")
        return fn(**args)
    if op.startswith("prof_"):
        sub = op[len("prof_"):]
        fn = getattr(engine.profiles, sub, None)
        if fn is None or sub.startswith("_"):
            raise ValueError(f"unknown profile op '{op}'")
        return fn(**args)
    if op.startswith("sm_"):
        sub = op[len("sm_"):]
        fn = getattr(engine.sheet, sub, None)
        if fn is None or sub.startswith("_"):
            raise ValueError(f"unknown sheet-metal op '{op}'")
        return fn(**args)
    if op.startswith("step_"):
        sub = op
        fn = getattr(engine.step_io, sub, None)
        if fn is None or sub.startswith("_"):
            raise ValueError(f"unknown step-io op '{op}'")
        return fn(**args)
    if op.startswith("asm_"):
        sub = op[len("asm_"):]
        # special-case: export needs output_dir
        if sub == "export_step":
            return engine.assemblies.export_step(output_dir=engine.output_dir, **args)
        fn = getattr(engine.assemblies, sub, None)
        if fn is None or sub.startswith("_"):
            raise ValueError(f"unknown assembly op '{op}'")
        return fn(**args)
    fn = getattr(engine, op, None)
    if fn is None or op.startswith("_"):
        raise ValueError(f"unknown op '{op}'")
    return fn(**args)
