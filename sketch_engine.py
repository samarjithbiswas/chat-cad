"""2D parametric sketcher with a scipy-based constraint solver.

A Sketch holds:
- points (each has x, y, fixed flag)
- lines (pairs of point names)
- circles (center point name, radius)
- rectangles (sugar: 4 points + 4 lines + auto h/v constraints)
- constraints (list of dicts)

solve() minimises the sum of squared constraint residuals using least_squares.
The result is written back into the sketch.

extrude() / revolve() turn a closed-wire sketch into a 3D CadQuery shape that
is handed back to the main CadEngine and stored as a normal named part.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import Any

import cadquery as cq
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import least_squares


# ---------------- data model ---------------- #
@dataclass
class Sketch:
    name: str
    plane: str = "XY"  # XY | XZ | YZ
    # name -> [x, y, fixed]
    points: dict[str, list] = field(default_factory=dict)
    # name -> (p1_name, p2_name)
    lines: dict[str, tuple[str, str]] = field(default_factory=dict)
    # name -> [center_point_name, radius]
    circles: dict[str, list] = field(default_factory=dict)
    # name -> (center_point_name, start_point_name, end_point_name)
    arcs: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    # name -> [pt_name, pt_name, ...]
    splines: dict[str, list[str]] = field(default_factory=dict)
    constraints: list[dict[str, Any]] = field(default_factory=list)


# ---------------- engine ---------------- #
class SketchEngine:
    """Owns all sketches and is the bridge into the 3D part dict."""

    def __init__(self, parts_ref: dict[str, cq.Workplane]):
        self.sketches: dict[str, Sketch] = {}
        self.parts_ref = parts_ref  # mutate this dict to publish 3D shapes

    # ----- access ----- #
    def _s(self, name: str) -> Sketch:
        if name not in self.sketches:
            raise KeyError(f"no sketch '{name}'. existing: {list(self.sketches)}")
        return self.sketches[name]

    def _require_point(self, sk: Sketch, p: str) -> None:
        if p not in sk.points:
            raise KeyError(f"sketch '{sk.name}' has no point '{p}'")

    def _require_line(self, sk: Sketch, ln: str) -> None:
        if ln not in sk.lines:
            raise KeyError(f"sketch '{sk.name}' has no line '{ln}'")

    # ----- creation ----- #
    def new(self, name: str, plane: str = "XY") -> str:
        plane = plane.upper()
        if plane not in ("XY", "XZ", "YZ"):
            raise ValueError("plane must be XY, XZ, or YZ")
        self.sketches[name] = Sketch(name=name, plane=plane)
        return f"created sketch '{name}' on plane {plane}"

    def list_sketches(self) -> str:
        if not self.sketches:
            return "no sketches"
        out = []
        for n, s in self.sketches.items():
            out.append(f"  {n} ({s.plane}): "
                       f"{len(s.points)} pts, {len(s.lines)} lines, "
                       f"{len(s.circles)} circles, {len(s.arcs)} arcs, "
                       f"{len(s.splines)} splines, {len(s.constraints)} cons")
        return "sketches:\n" + "\n".join(out)

    def info(self, name: str) -> str:
        s = self._s(name)
        lines = [f"sketch '{name}' on {s.plane}"]
        for n, (x, y, fx) in s.points.items():
            lines.append(f"  pt {n}: ({x:.3f}, {y:.3f}){' [fixed]' if fx else ''}")
        for n, (p1, p2) in s.lines.items():
            lines.append(f"  line {n}: {p1} -> {p2}")
        for n, (c, r) in s.circles.items():
            lines.append(f"  circle {n}: center {c}, r={r:.3f}")
        for n, (c, sp, ep) in s.arcs.items():
            lines.append(f"  arc {n}: center {c}, start {sp}, end {ep}")
        for n, pts in s.splines.items():
            lines.append(f"  spline {n}: {len(pts)} ctrl pts [{', '.join(pts)}]")
        for i, c in enumerate(s.constraints):
            lines.append(f"  c{i}: {c}")
        return "\n".join(lines)

    def delete(self, name: str) -> str:
        self._s(name)
        del self.sketches[name]
        return f"deleted sketch '{name}'"

    # ----- entities ----- #
    def add_point(self, sketch: str, point: str, x: float, y: float,
                  fixed: bool = False) -> str:
        s = self._s(sketch)
        s.points[point] = [float(x), float(y), bool(fixed)]
        return f"point '{point}' at ({x},{y}){' fixed' if fixed else ''}"

    def fix_point(self, sketch: str, point: str, fixed: bool = True) -> str:
        s = self._s(sketch)
        self._require_point(s, point)
        s.points[point][2] = bool(fixed)
        return f"point '{point}' fixed={fixed}"

    def add_line(self, sketch: str, line: str,
                 x1: float, y1: float, x2: float, y2: float) -> str:
        s = self._s(sketch)
        p1 = f"{line}_a"
        p2 = f"{line}_b"
        s.points[p1] = [float(x1), float(y1), False]
        s.points[p2] = [float(x2), float(y2), False]
        s.lines[line] = (p1, p2)
        return f"line '{line}' from ({x1},{y1}) to ({x2},{y2})"

    def add_circle(self, sketch: str, circle: str,
                   cx: float, cy: float, r: float) -> str:
        s = self._s(sketch)
        c = f"{circle}_c"
        s.points[c] = [float(cx), float(cy), False]
        s.circles[circle] = [c, float(r)]
        return f"circle '{circle}' center ({cx},{cy}) r={r}"

    def add_rect(self, sketch: str, rect: str,
                 x: float, y: float, w: float, h: float) -> str:
        """Sugar: rect = 4 points + 4 lines + 4 H/V constraints."""
        s = self._s(sketch)
        p = lambda i, X, Y: s.points.setdefault(f"{rect}_p{i}", [X, Y, False])
        p(1, x, y); p(2, x + w, y); p(3, x + w, y + h); p(4, x, y + h)
        s.lines[f"{rect}_b"] = (f"{rect}_p1", f"{rect}_p2")
        s.lines[f"{rect}_r"] = (f"{rect}_p2", f"{rect}_p3")
        s.lines[f"{rect}_t"] = (f"{rect}_p3", f"{rect}_p4")
        s.lines[f"{rect}_l"] = (f"{rect}_p4", f"{rect}_p1")
        for ln in (f"{rect}_b", f"{rect}_t"):
            s.constraints.append({"kind": "horizontal", "line": ln})
        for ln in (f"{rect}_l", f"{rect}_r"):
            s.constraints.append({"kind": "vertical", "line": ln})
        return f"rect '{rect}' at ({x},{y}) {w}x{h} (with H/V constraints)"

    def add_arc(self, sketch: str, name: str,
                cx: float, cy: float, sx: float, sy: float,
                ex: float, ey: float) -> str:
        """CCW arc by center / start / end. Radius implicit (auto-equalised)."""
        s = self._s(sketch)
        c = f"{name}_c"; sp = f"{name}_s"; ep = f"{name}_e"
        s.points[c]  = [float(cx), float(cy), False]
        s.points[sp] = [float(sx), float(sy), False]
        s.points[ep] = [float(ex), float(ey), False]
        s.arcs[name] = (c, sp, ep)
        s.constraints.append({"kind": "arc_radius", "arc": name})
        return f"arc '{name}' center ({cx},{cy}) start ({sx},{sy}) end ({ex},{ey})"

    def add_spline(self, sketch: str, name: str,
                   points: list[tuple[float, float]]) -> str:
        s = self._s(sketch)
        if len(points) < 2:
            raise ValueError("spline needs >=2 control points")
        pt_names = []
        for i, (x, y) in enumerate(points):
            pn = f"{name}_{i}"
            s.points[pn] = [float(x), float(y), False]
            pt_names.append(pn)
        s.splines[name] = pt_names
        return f"spline '{name}' with {len(pt_names)} ctrl pts"

    # ----- constraints ----- #
    def _add_c(self, sketch: str, c: dict) -> str:
        self._s(sketch).constraints.append(c)
        return f"added constraint: {c}"

    def c_coincident(self, sketch: str, a: str, b: str) -> str:
        return self._add_c(sketch, {"kind": "coincident", "a": a, "b": b})

    def c_horizontal(self, sketch: str, line: str) -> str:
        return self._add_c(sketch, {"kind": "horizontal", "line": line})

    def c_vertical(self, sketch: str, line: str) -> str:
        return self._add_c(sketch, {"kind": "vertical", "line": line})

    def c_distance(self, sketch: str, a: str, b: str, d: float) -> str:
        return self._add_c(sketch, {"kind": "distance", "a": a, "b": b, "d": float(d)})

    def c_distance_x(self, sketch: str, a: str, b: str, d: float) -> str:
        return self._add_c(sketch, {"kind": "distance_x", "a": a, "b": b, "d": float(d)})

    def c_distance_y(self, sketch: str, a: str, b: str, d: float) -> str:
        return self._add_c(sketch, {"kind": "distance_y", "a": a, "b": b, "d": float(d)})

    def c_parallel(self, sketch: str, a: str, b: str) -> str:
        return self._add_c(sketch, {"kind": "parallel", "a": a, "b": b})

    def c_perpendicular(self, sketch: str, a: str, b: str) -> str:
        return self._add_c(sketch, {"kind": "perpendicular", "a": a, "b": b})

    def c_equal(self, sketch: str, a: str, b: str) -> str:
        return self._add_c(sketch, {"kind": "equal", "a": a, "b": b})

    def c_radius(self, sketch: str, circle: str, r: float) -> str:
        return self._add_c(sketch, {"kind": "radius", "c": circle, "d": float(r)})

    def c_angle(self, sketch: str, a: str, b: str, degrees: float) -> str:
        return self._add_c(sketch, {"kind": "angle", "a": a, "b": b,
                                    "d": float(degrees)})

    # ----- solver ----- #
    def solve(self, sketch: str) -> str:
        s = self._s(sketch)
        pt_names = list(s.points.keys())
        circ_names = list(s.circles.keys())

        idx: dict[tuple[str, str], int] = {}
        x0: list[float] = []
        for n in pt_names:
            x, y, fixed = s.points[n]
            if not fixed:
                idx[(n, "x")] = len(x0); x0.append(x)
                idx[(n, "y")] = len(x0); x0.append(y)
        for cn in circ_names:
            idx[(cn, "r")] = len(x0); x0.append(s.circles[cn][1])

        if not x0:
            return "nothing free to solve"

        def gx(n, v): i = idx.get((n, "x")); return v[i] if i is not None else s.points[n][0]
        def gy(n, v): i = idx.get((n, "y")); return v[i] if i is not None else s.points[n][1]
        def gr(cn, v): i = idx.get((cn, "r")); return v[i] if i is not None else s.circles[cn][1]

        def line_dir(ln, v):
            p1, p2 = s.lines[ln]
            return gx(p2, v) - gx(p1, v), gy(p2, v) - gy(p1, v)

        def residuals(v):
            r = []
            for c in s.constraints:
                k = c["kind"]
                if k == "coincident":
                    r.append(gx(c["a"], v) - gx(c["b"], v))
                    r.append(gy(c["a"], v) - gy(c["b"], v))
                elif k == "horizontal":
                    p1, p2 = s.lines[c["line"]]
                    r.append(gy(p1, v) - gy(p2, v))
                elif k == "vertical":
                    p1, p2 = s.lines[c["line"]]
                    r.append(gx(p1, v) - gx(p2, v))
                elif k == "distance":
                    dx = gx(c["a"], v) - gx(c["b"], v)
                    dy = gy(c["a"], v) - gy(c["b"], v)
                    r.append(math.hypot(dx, dy) - c["d"])
                elif k == "distance_x":
                    r.append((gx(c["b"], v) - gx(c["a"], v)) - c["d"])
                elif k == "distance_y":
                    r.append((gy(c["b"], v) - gy(c["a"], v)) - c["d"])
                elif k == "parallel":
                    ax, ay = line_dir(c["a"], v); bx, by = line_dir(c["b"], v)
                    r.append(ax * by - ay * bx)
                elif k == "perpendicular":
                    ax, ay = line_dir(c["a"], v); bx, by = line_dir(c["b"], v)
                    r.append(ax * bx + ay * by)
                elif k == "equal":
                    if c["a"] in s.lines and c["b"] in s.lines:
                        ax, ay = line_dir(c["a"], v); bx, by = line_dir(c["b"], v)
                        r.append(math.hypot(ax, ay) - math.hypot(bx, by))
                    elif c["a"] in s.circles and c["b"] in s.circles:
                        r.append(gr(c["a"], v) - gr(c["b"], v))
                elif k == "radius":
                    r.append(gr(c["c"], v) - c["d"])
                elif k == "arc_radius":
                    cn, sn, en = s.arcs[c["arc"]]
                    dxs = gx(sn, v) - gx(cn, v); dys = gy(sn, v) - gy(cn, v)
                    dxe = gx(en, v) - gx(cn, v); dye = gy(en, v) - gy(cn, v)
                    r.append(math.hypot(dxs, dys) - math.hypot(dxe, dye))
                elif k == "angle":
                    ax, ay = line_dir(c["a"], v); bx, by = line_dir(c["b"], v)
                    na = math.hypot(ax, ay) or 1.0
                    nb = math.hypot(bx, by) or 1.0
                    cos_t = (ax * bx + ay * by) / (na * nb)
                    cos_t = max(-1.0, min(1.0, cos_t))
                    r.append(math.degrees(math.acos(cos_t)) - c["d"])
            return np.array(r) if r else np.array([0.0])

        res = least_squares(residuals, np.array(x0))
        for (n, axis), i in idx.items():
            if axis == "x":
                s.points[n][0] = float(res.x[i])
            elif axis == "y":
                s.points[n][1] = float(res.x[i])
            elif axis == "r":
                s.circles[n][1] = float(res.x[i])
        max_r = float(np.max(np.abs(res.fun))) if len(res.fun) else 0.0
        return f"solved '{sketch}' ({len(s.constraints)} cons, max residual {max_r:.4g})"

    # ----- build into 3D ----- #
    def _arc_mid(self, sk: Sketch, arc_name: str) -> tuple[float, float]:
        """Midpoint on a CCW arc going from start to end."""
        cn, sn, en = sk.arcs[arc_name]
        cx, cy, _ = sk.points[cn]
        sx, sy, _ = sk.points[sn]
        ex, ey, _ = sk.points[en]
        r = math.hypot(sx - cx, sy - cy)
        a0 = math.atan2(sy - cy, sx - cx)
        a1 = math.atan2(ey - cy, ex - cx)
        if a1 <= a0:
            a1 += 2 * math.pi
        am = 0.5 * (a0 + a1)
        return cx + r * math.cos(am), cy + r * math.sin(am)

    def _build_workplane(self, sk: Sketch) -> cq.Workplane:
        wp = cq.Workplane(sk.plane)
        for _cn, (c, r) in sk.circles.items():
            cx, cy, _ = sk.points[c]
            wp = wp.moveTo(cx, cy).circle(r)
        # collect edges (lines + arcs + splines) by endpoint adjacency
        edges: dict[str, tuple[str, str, str]] = {}  # id -> (kind, p1, p2)
        for ln, (p1, p2) in sk.lines.items():
            edges[f"L:{ln}"] = ("line", p1, p2)
        for an, (_cn, sn, en) in sk.arcs.items():
            edges[f"A:{an}"] = ("arc", sn, en)
        for spn, pts in sk.splines.items():
            edges[f"S:{spn}"] = ("spline", pts[0], pts[-1])
        adj: dict[str, list[tuple[str, str]]] = {}
        for eid, (_k, p1, p2) in edges.items():
            adj.setdefault(p1, []).append((eid, p2))
            adj.setdefault(p2, []).append((eid, p1))
        used: set[str] = set()
        for start_eid, (_sk_kind, sp1, sp2) in list(edges.items()):
            if start_eid in used:
                continue
            used.add(start_eid)
            chain_pts = [sp1, sp2]
            chain_edges = [start_eid]
            cur = sp2
            while True:
                nexts = [(eid, other) for eid, other in adj.get(cur, [])
                         if eid not in used]
                if not nexts:
                    break
                eid, other = nexts[0]
                used.add(eid)
                chain_pts.append(other)
                chain_edges.append(eid)
                cur = other
                if cur == sp1:
                    break
            if cur == sp1 and len(chain_pts) >= 4:
                # build wire edge-by-edge so arcs/splines participate
                x0, y0, _ = sk.points[chain_pts[0]]
                wp2 = wp.moveTo(x0, y0)
                for i, eid in enumerate(chain_edges):
                    kind, p1, p2 = edges[eid]
                    a_pt = chain_pts[i]; b_pt = chain_pts[i + 1]
                    ex, ey, _ = sk.points[b_pt]
                    if kind == "line":
                        wp2 = wp2.lineTo(ex, ey)
                    elif kind == "arc":
                        arc_name = eid[2:]
                        mx, my = self._arc_mid(sk, arc_name)
                        # if traversed end->start, reverse mid not needed for arc shape
                        wp2 = wp2.threePointArc((mx, my), (ex, ey))
                    elif kind == "spline":
                        spn = eid[2:]
                        pt_names = sk.splines[spn]
                        ctrl = [(sk.points[p][0], sk.points[p][1]) for p in pt_names]
                        if a_pt == pt_names[-1]:
                            ctrl = list(reversed(ctrl))
                        wp2 = wp2.spline(ctrl[1:])
                wp = wp2.close()
        return wp

    def extrude(self, sketch: str, part: str, depth: float) -> str:
        s = self._s(sketch)
        wp = self._build_workplane(s)
        try:
            solid = wp.extrude(float(depth))
        except Exception as e:
            raise RuntimeError(f"could not extrude sketch '{sketch}' "
                               f"(closed loops required): {e}")
        self.parts_ref[part] = solid
        return f"extruded sketch '{sketch}' by {depth} into part '{part}'"

    def revolve(self, sketch: str, part: str, axis: str = "Y",
                degrees: float = 360.0) -> str:
        s = self._s(sketch)
        wp = self._build_workplane(s)
        axis = axis.upper()
        a0 = (0, 0, 0)
        a1 = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[axis]
        try:
            solid = wp.revolve(float(degrees), a0, a1)
        except Exception as e:
            raise RuntimeError(f"could not revolve sketch '{sketch}': {e}")
        self.parts_ref[part] = solid
        return (f"revolved sketch '{sketch}' {degrees}deg about {axis} "
                f"into part '{part}'")

    # ----- SVG preview ----- #
    def svg(self, sketch: str) -> str:
        s = self._s(sketch)
        # compute bbox
        xs, ys = [], []
        for x, y, _ in s.points.values():
            xs.append(x); ys.append(y)
        for cn, (c, r) in s.circles.items():
            cx, cy, _ = s.points[c]
            xs += [cx - r, cx + r]; ys += [cy - r, cy + r]
        if not xs:
            xs, ys = [-10, 10], [-10, 10]
        pad = max(1.0, 0.1 * max(max(xs) - min(xs), max(ys) - min(ys)))
        x_min, x_max = min(xs) - pad, max(xs) + pad
        y_min, y_max = min(ys) - pad, max(ys) + pad
        W = 640; H = 480
        w = x_max - x_min; h = y_max - y_min
        scale = min(W / w, H / h)
        ox = (W - w * scale) / 2 - x_min * scale
        oy = (H - h * scale) / 2 + y_max * scale  # SVG y is flipped
        # convert
        def tx(x): return x * scale + ox
        def ty(y): return -y * scale + oy

        buf = io.StringIO()
        buf.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
                  f'viewBox="0 0 {W} {H}" style="background:#10141a">\n')
        # grid + axes
        buf.write(f'<line x1="0" y1="{ty(0)}" x2="{W}" y2="{ty(0)}" '
                  f'stroke="#2c3340" stroke-width="1"/>\n')
        buf.write(f'<line x1="{tx(0)}" y1="0" x2="{tx(0)}" y2="{H}" '
                  f'stroke="#2c3340" stroke-width="1"/>\n')
        # lines
        for ln, (p1, p2) in s.lines.items():
            x1, y1, _ = s.points[p1]; x2, y2, _ = s.points[p2]
            buf.write(f'<line x1="{tx(x1)}" y1="{ty(y1)}" '
                      f'x2="{tx(x2)}" y2="{ty(y2)}" '
                      f'stroke="#6aa7ff" stroke-width="2"/>\n')
        # circles
        for cn, (c, r) in s.circles.items():
            cx, cy, _ = s.points[c]
            buf.write(f'<circle cx="{tx(cx)}" cy="{ty(cy)}" r="{r*scale:.2f}" '
                      f'fill="none" stroke="#6aa7ff" stroke-width="2"/>\n')
        # arcs
        for an, (cn, sn, en) in s.arcs.items():
            cx, cy, _ = s.points[cn]
            sx, sy, _ = s.points[sn]
            ex, ey, _ = s.points[en]
            rr = math.hypot(sx - cx, sy - cy)
            buf.write(f'<path d="M {tx(sx):.2f} {ty(sy):.2f} '
                      f'A {rr*scale:.2f} {rr*scale:.2f} 0 0 0 '
                      f'{tx(ex):.2f} {ty(ey):.2f}" '
                      f'fill="none" stroke="#6aa7ff" stroke-width="2"/>\n')
        # splines (sampled)
        for spn, pt_names in s.splines.items():
            pts = [(s.points[p][0], s.points[p][1]) for p in pt_names]
            if len(pts) >= 2:
                t = np.arange(len(pts))
                xs_p = np.array([p[0] for p in pts])
                ys_p = np.array([p[1] for p in pts])
                if len(pts) >= 3:
                    csx = CubicSpline(t, xs_p)
                    csy = CubicSpline(t, ys_p)
                    ts = np.linspace(0, len(pts) - 1, 50)
                    sxs = csx(ts); sys = csy(ts)
                else:
                    ts = np.linspace(0, 1, 50)
                    sxs = xs_p[0] + (xs_p[1] - xs_p[0]) * ts
                    sys = ys_p[0] + (ys_p[1] - ys_p[0]) * ts
                pts_str = " ".join(f"{tx(float(xx)):.2f},{ty(float(yy)):.2f}"
                                   for xx, yy in zip(sxs, sys))
                buf.write(f'<polyline points="{pts_str}" '
                          f'fill="none" stroke="#6aa7ff" stroke-width="2"/>\n')
        # points
        for n, (x, y, fx) in s.points.items():
            col = "#ff7474" if fx else "#e0c060"
            buf.write(f'<circle cx="{tx(x)}" cy="{ty(y)}" r="3" fill="{col}"/>\n')
            buf.write(f'<text x="{tx(x)+5}" y="{ty(y)-5}" fill="#9aa3b2" '
                      f'font-size="10" font-family="ui-monospace">{n}</text>\n')
        buf.write('</svg>\n')
        return buf.getvalue()


def dispatch_sketch(eng: SketchEngine, op: str, args: dict) -> str:
    fn = getattr(eng, op, None)
    if fn is None or op.startswith("_"):
        raise ValueError(f"unknown sketch op '{op}'")
    return fn(**args)
