"""Placement-based assembly system on top of CadQuery's Assembly.

An assembly is a named collection of components; each component points to a
part from the main scene plus a (location, rotation) placement. Solve()
builds the cq.Assembly, optionally applies stub mate constraints, then writes
the resulting compound back into the scene as a single part named
'_asm_<asm>' so it shows up in the 3D viewer.
"""
from __future__ import annotations

import cadquery as cq


# tail-spec -> CadQuery tag-style face selector for box-like solids
_FACE_TAG = {
    "top":    ">Z",
    "bottom": "<Z",
    "left":   "<X",
    "right":  ">X",
    "front":  "<Y",
    "back":   ">Y",
}


def _resolve_selector(comp_obj: cq.Workplane, selector_tail: str):
    """Return either a CadQuery face-tag string or a concrete sub-shape.

    selector_tail is the part after '<comp>.', e.g. 'face.top', 'edge.3',
    'axis.Z', 'point.0'.
    """
    parts = selector_tail.split(".")
    if len(parts) != 2:
        raise ValueError(f"bad selector tail '{selector_tail}'")
    kind, spec = parts[0].lower(), parts[1]
    if kind == "face":
        s = spec.lower()
        if s not in _FACE_TAG:
            raise ValueError(f"face spec must be one of {list(_FACE_TAG)}, got '{spec}'")
        return _FACE_TAG[s]
    if kind == "edge":
        edges = comp_obj.edges().vals()
        return edges[int(spec)]
    if kind == "axis":
        ax = spec.upper()
        if ax not in ("X", "Y", "Z"):
            raise ValueError(f"axis must be X/Y/Z, got '{spec}'")
        bb = comp_obj.val().BoundingBox()
        center = cq.Vector((bb.xmin + bb.xmax) / 2,
                           (bb.ymin + bb.ymax) / 2,
                           (bb.zmin + bb.zmax) / 2)
        direction = {"X": cq.Vector(1, 0, 0),
                     "Y": cq.Vector(0, 1, 0),
                     "Z": cq.Vector(0, 0, 1)}[ax]
        return cq.Edge.makeLine(center, center + direction)
    if kind == "point":
        verts = comp_obj.vertices().vals()
        return verts[int(spec)]
    raise ValueError(f"unknown selector kind '{kind}'")


def _split_selector(sel: str) -> tuple[str, str]:
    """Split '<comp>.<kind>.<spec>' -> ('<comp>', '<kind>.<spec>')."""
    first, _, rest = sel.partition(".")
    if not rest:
        raise ValueError(f"selector '{sel}' missing tail")
    return first, rest


def _tag_for_selector(comp_obj: cq.Workplane, comp_name: str, sel_tail: str) -> str:
    """Build a CadQuery assembly tag string like 'name@faces@>Z' or 'name?tag'.

    Falls back to indexed face/edge tags via an OCCT-style query when needed.
    """
    parts = sel_tail.split(".")
    kind, spec = parts[0].lower(), parts[1]
    if kind == "face":
        return f"{comp_name}@faces@{_FACE_TAG[spec.lower()]}"
    if kind == "edge":
        # CadQuery tag strings don't support raw indices; this query form
        # picks the i-th edge in the +X-sorted list, which is good enough.
        return f"{comp_name}@edges@>>X[{int(spec)}]"
    if kind == "axis":
        ax = spec.upper()
        return f"{comp_name}@faces@>{ax}"
    if kind == "point":
        return f"{comp_name}@vertices@>>X[{int(spec)}]"
    raise ValueError(f"unknown selector kind '{kind}'")


class AssemblyEngine:
    def __init__(self, parts_ref: dict[str, cq.Workplane]):
        self.parts_ref = parts_ref
        # name -> { comps: {comp_name: {part, x, y, z, rx, ry, rz}}, mates: [...] }
        self.assemblies: dict[str, dict] = {}

    def _a(self, name: str) -> dict:
        if name not in self.assemblies:
            existing = list(self.assemblies)
            hint = f"  →  run 'asm new {name}' first to create it"
            if existing:
                hint += f"  (existing assemblies: {existing})"
            raise KeyError(f"no assembly '{name}'.\n{hint}")
        return self.assemblies[name]

    # ----- structure ----- #
    def new(self, name: str) -> str:
        self.assemblies[name] = {"comps": {}, "mates": []}
        return f"created assembly '{name}'"

    def add_component(self, assembly: str, component: str, part: str,
                      x: float = 0, y: float = 0, z: float = 0,
                      rx: float = 0, ry: float = 0, rz: float = 0) -> str:
        # Friendly: auto-create the assembly if the user skipped 'asm new'
        if assembly not in self.assemblies:
            self.new(assembly)
        a = self.assemblies[assembly]
        if part not in self.parts_ref:
            available = list(self.parts_ref.keys())
            hint = (f"  →  no part named '{part}' exists in the scene yet.\n"
                    f"     Build it first, e.g. 'box {part} 20 20 20' or "
                    f"'cyl {part} 5 30'.")
            if available:
                hint += f"\n     Existing parts: {available}"
            raise KeyError(hint)
        a["comps"][component] = {
            "part": part,
            "x": float(x), "y": float(y), "z": float(z),
            "rx": float(rx), "ry": float(ry), "rz": float(rz),
        }
        return (f"added component '{component}' (part '{part}') to "
                f"'{assembly}' at ({x},{y},{z}) rot ({rx},{ry},{rz})")

    def move_component(self, assembly: str, component: str,
                       dx: float = 0, dy: float = 0, dz: float = 0) -> str:
        a = self._a(assembly)
        if component not in a["comps"]:
            raise KeyError(f"no component '{component}' in '{assembly}'")
        c = a["comps"][component]
        c["x"] += float(dx); c["y"] += float(dy); c["z"] += float(dz)
        return f"moved '{component}' by ({dx},{dy},{dz})"

    def rotate_component(self, assembly: str, component: str,
                         rx: float = 0, ry: float = 0, rz: float = 0) -> str:
        a = self._a(assembly)
        if component not in a["comps"]:
            raise KeyError(f"no component '{component}'")
        c = a["comps"][component]
        c["rx"] += float(rx); c["ry"] += float(ry); c["rz"] += float(rz)
        return f"rotated '{component}' by ({rx},{ry},{rz}) deg"

    def remove_component(self, assembly: str, component: str) -> str:
        a = self._a(assembly)
        if component not in a["comps"]:
            raise KeyError(f"no component '{component}'")
        del a["comps"][component]
        return f"removed '{component}' from '{assembly}'"

    # ----- mates ----- #
    def add_mate(self, assembly: str, kind: str, a_sel: str, b_sel: str) -> str:
        """Record a mate; solved by solve() via cq.Assembly.constrain/solve."""
        a = self._a(assembly)
        if kind not in ("Plane", "Axis", "Point"):
            raise ValueError(f"unknown mate kind '{kind}' (allowed: Plane, Axis, Point)")
        # validate selector shape early
        _split_selector(a_sel); _split_selector(b_sel)
        a["mates"].append({"kind": kind, "a": a_sel, "b": b_sel})
        return f"recorded mate {kind} between '{a_sel}' and '{b_sel}'"

    def _placement_loc(self, c: dict) -> cq.Location:
        loc = cq.Location(cq.Vector(c["x"], c["y"], c["z"]),
                          cq.Vector(0, 0, 1), c["rz"])
        loc = loc * cq.Location(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), c["rx"])
        loc = loc * cq.Location(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), c["ry"])
        return loc

    def _write_back_location(self, c: dict, loc: cq.Location) -> None:
        """Decompose a solved Location into (xyz, rx,ry,rz deg) and store."""
        try:
            (x, y, z), (rx, ry, rz) = loc.toTuple()
            c["x"], c["y"], c["z"] = float(x), float(y), float(z)
            c["rx"], c["ry"], c["rz"] = float(rx), float(ry), float(rz)
        except Exception:
            # fall back to translation-only readback
            t = loc.wrapped.Transformation().TranslationPart()
            c["x"], c["y"], c["z"] = float(t.X()), float(t.Y()), float(t.Z())

    # ----- build ----- #
    def place_parts(self, assembly: str) -> str:
        """Move each component's underlying part to its placed location.
        Unlike solve(), no compound is created — the SOURCE parts physically
        relocate so they're visible at the right spots. This is what users
        expect when they 'build' an assembly.
        """
        a = self._a(assembly)
        moved = []
        for comp_name, c in a["comps"].items():
            part_name = c["part"]
            if part_name not in self.parts_ref:
                continue
            part = self.parts_ref[part_name]
            # rotation first (about origin), then translation
            if c["rx"] != 0:
                part = part.rotate((0, 0, 0), (1, 0, 0), c["rx"])
            if c["ry"] != 0:
                part = part.rotate((0, 0, 0), (0, 1, 0), c["ry"])
            if c["rz"] != 0:
                part = part.rotate((0, 0, 0), (0, 0, 1), c["rz"])
            part = part.translate((c["x"], c["y"], c["z"]))
            self.parts_ref[part_name] = part
            moved.append(f"'{part_name}' -> ({c['x']:.1f},{c['y']:.1f},{c['z']:.1f})")
        return (f"assembly '{assembly}': placed {len(moved)} component(s).\n  "
                + "\n  ".join(moved))

    def solve(self, assembly: str) -> str:
        a = self._a(assembly)
        warn = ""
        asm = cq.Assembly(name=assembly)
        for comp_name, c in a["comps"].items():
            asm.add(self.parts_ref[c["part"]], name=comp_name,
                    loc=self._placement_loc(c))

        if a["mates"]:
            try:
                for m in a["mates"]:
                    a_comp, a_tail = _split_selector(m["a"])
                    b_comp, b_tail = _split_selector(m["b"])
                    a_obj = self.parts_ref[a["comps"][a_comp]["part"]]
                    b_obj = self.parts_ref[a["comps"][b_comp]["part"]]
                    a_tag = _tag_for_selector(a_obj, a_comp, a_tail)
                    b_tag = _tag_for_selector(b_obj, b_comp, b_tail)
                    asm.constrain(a_tag, b_tag, m["kind"])
                asm.solve()
                # read back solved locations
                for comp_name, c in a["comps"].items():
                    obj = asm.objects.get(comp_name)
                    if obj is not None and obj.loc is not None:
                        self._write_back_location(c, obj.loc)
            except Exception as e:
                warn = (f"WARNING: mate solve failed ({e}); "
                        f"positioning by placement only. ")
                # rebuild asm without constraints so toCompound uses placements
                asm = cq.Assembly(name=assembly)
                for comp_name, c in a["comps"].items():
                    asm.add(self.parts_ref[c["part"]], name=comp_name,
                            loc=self._placement_loc(c))

        compound = asm.toCompound()
        self.parts_ref[f"_asm_{assembly}"] = cq.Workplane(obj=compound)
        return (f"{warn}built assembly '{assembly}' with {len(a['comps'])} "
                f"components -> part '_asm_{assembly}'")

    # ----- access ----- #
    def list_assemblies(self) -> str:
        if not self.assemblies:
            return "no assemblies"
        out = []
        for n, a in self.assemblies.items():
            out.append(f"  {n}: {len(a['comps'])} components, {len(a['mates'])} mates")
        return "assemblies:\n" + "\n".join(out)

    def info(self, name: str) -> str:
        a = self._a(name)
        lines = [f"assembly '{name}'"]
        for cn, c in a["comps"].items():
            lines.append(f"  {cn}: part='{c['part']}' "
                         f"loc=({c['x']:.2f},{c['y']:.2f},{c['z']:.2f}) "
                         f"rot=({c['rx']:.1f},{c['ry']:.1f},{c['rz']:.1f})")
        for i, m in enumerate(a["mates"]):
            lines.append(f"  mate{i}: {m['kind']} {m['a']} <-> {m['b']}")
        return "\n".join(lines)

    def delete(self, name: str) -> str:
        self._a(name)
        del self.assemblies[name]
        # drop any auto-built compound from the scene
        self.parts_ref.pop(f"_asm_{name}", None)
        return f"deleted assembly '{name}'"

    def export_step(self, assembly: str, output_dir: str,
                    filename: str | None = None) -> str:
        import os
        a = self._a(assembly)
        asm = cq.Assembly(name=assembly)
        for comp_name, c in a["comps"].items():
            part = self.parts_ref[c["part"]]
            loc = cq.Location(cq.Vector(c["x"], c["y"], c["z"]),
                              cq.Vector(0, 0, 1), c["rz"])
            loc = loc * cq.Location(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), c["rx"])
            loc = loc * cq.Location(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), c["ry"])
            asm.add(part, name=comp_name, loc=loc)
        fname = filename or f"{assembly}.step"
        path = os.path.join(output_dir, fname)
        asm.save(path)
        return path


def dispatch_assembly(eng: AssemblyEngine, op: str, args: dict) -> str:
    fn = getattr(eng, op, None)
    if fn is None or op.startswith("_"):
        raise ValueError(f"unknown assembly op '{op}'")
    return fn(**args)
