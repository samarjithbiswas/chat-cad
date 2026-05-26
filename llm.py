"""Claude-driven and regex-parser command sources for the CAD engine.

The Claude path uses tool_use: every engine method is exposed as a tool;
Claude calls them in a loop until it has built what the user asked for.
The parser path lets the app work offline with simple `op arg arg ...` lines.
"""
from __future__ import annotations

import re
import shlex
from typing import Any

from cad_engine import CadEngine, dispatch


# ---------------- tool schema for Claude ---------------- #
TOOLS = [
    {
        "name": "box",
        "description": "Create a rectangular box centered at (x,y,z).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "length": {"type": "number"}, "width": {"type": "number"},
                "height": {"type": "number"},
                "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"},
            },
            "required": ["name", "length", "width", "height"],
        },
    },
    {
        "name": "cylinder",
        "description": "Create a cylinder along Z axis centered at (x,y,z).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "radius": {"type": "number"}, "height": {"type": "number"},
                "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"},
            },
            "required": ["name", "radius", "height"],
        },
    },
    {
        "name": "sphere",
        "description": "Create a sphere centered at (x,y,z).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "radius": {"type": "number"},
                "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"},
            },
            "required": ["name", "radius"],
        },
    },
    {
        "name": "torus",
        "description": "Create a torus (donut) on the XY plane.",
        "input_schema": {"type": "object",
            "properties": {"name": {"type": "string"},
                "major_radius": {"type": "number"}, "minor_radius": {"type": "number"},
                "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
            "required": ["name", "major_radius", "minor_radius"]}},
    {
        "name": "wedge",
        "description": "Create a wedge (triangular prism along Z).",
        "input_schema": {"type": "object",
            "properties": {"name": {"type": "string"},
                "dx": {"type": "number"}, "dy": {"type": "number"}, "dz": {"type": "number"},
                "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
            "required": ["name", "dx", "dy", "dz"]}},
    {
        "name": "polygon",
        "description": "Regular n-sided polygon extruded along Z.",
        "input_schema": {"type": "object",
            "properties": {"name": {"type": "string"},
                "sides": {"type": "integer"}, "radius": {"type": "number"},
                "height": {"type": "number"},
                "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
            "required": ["name", "sides", "radius", "height"]}},
    {
        "name": "text_3d",
        "description": "Create extruded 3D text on the XY plane.",
        "input_schema": {"type": "object",
            "properties": {"name": {"type": "string"}, "text": {"type": "string"},
                "size": {"type": "number"}, "height": {"type": "number"},
                "font": {"type": "string"},
                "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
            "required": ["name", "text"]}},
    {
        "name": "scale",
        "description": "Scale a part. Pass sx only for uniform; sx/sy/sz for anisotropic.",
        "input_schema": {"type": "object",
            "properties": {"name": {"type": "string"},
                "sx": {"type": "number"}, "sy": {"type": "number"}, "sz": {"type": "number"}},
            "required": ["name", "sx"]}},
    {
        "name": "mirror",
        "description": "Mirror a part across XY/XZ/YZ plane; result stored under 'out'.",
        "input_schema": {"type": "object",
            "properties": {"out": {"type": "string"}, "src": {"type": "string"},
                "plane": {"type": "string", "enum": ["XY", "XZ", "YZ"]}},
            "required": ["out", "src"]}},
    {
        "name": "linear_pattern",
        "description": "Stamp `count` copies of `src` translated by (dx,dy,dz) each step.",
        "input_schema": {"type": "object",
            "properties": {"prefix": {"type": "string"}, "src": {"type": "string"},
                "dx": {"type": "number"}, "dy": {"type": "number"}, "dz": {"type": "number"},
                "count": {"type": "integer"}},
            "required": ["prefix", "src", "dx", "dy", "dz", "count"]}},
    {
        "name": "polar_pattern",
        "description": "Stamp `count` copies of `src` rotated around world axis.",
        "input_schema": {"type": "object",
            "properties": {"prefix": {"type": "string"}, "src": {"type": "string"},
                "count": {"type": "integer"}, "total_angle": {"type": "number"},
                "axis": {"type": "string", "enum": ["X", "Y", "Z"]}},
            "required": ["prefix", "src", "count"]}},
    {
        "name": "cone",
        "description": "Create a (possibly truncated) cone along Z.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "radius1": {"type": "number"}, "radius2": {"type": "number"},
                "height": {"type": "number"},
                "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"},
            },
            "required": ["name", "radius1", "radius2", "height"],
        },
    },
    {
        "name": "translate",
        "description": "Move a part by (dx,dy,dz).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "dx": {"type": "number"}, "dy": {"type": "number"}, "dz": {"type": "number"},
            },
            "required": ["name", "dx", "dy", "dz"],
        },
    },
    {
        "name": "rotate",
        "description": "Rotate a part about world X, Y, or Z axis through origin.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "axis": {"type": "string", "enum": ["X", "Y", "Z"]},
                "degrees": {"type": "number"},
            },
            "required": ["name", "axis", "degrees"],
        },
    },
    {
        "name": "union",
        "description": "Boolean union: out = a ∪ b. Result stored under 'out'.",
        "input_schema": {
            "type": "object",
            "properties": {"out": {"type": "string"}, "a": {"type": "string"}, "b": {"type": "string"}},
            "required": ["out", "a", "b"],
        },
    },
    {
        "name": "cut",
        "description": "Boolean subtraction: out = a - b.",
        "input_schema": {
            "type": "object",
            "properties": {"out": {"type": "string"}, "a": {"type": "string"}, "b": {"type": "string"}},
            "required": ["out", "a", "b"],
        },
    },
    {
        "name": "intersect",
        "description": "Boolean intersection: out = a ∩ b.",
        "input_schema": {
            "type": "object",
            "properties": {"out": {"type": "string"}, "a": {"type": "string"}, "b": {"type": "string"}},
            "required": ["out", "a", "b"],
        },
    },
    {
        "name": "fillet",
        "description": "Fillet all edges of a part with given radius.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "radius": {"type": "number"}},
            "required": ["name", "radius"],
        },
    },
    {
        "name": "chamfer",
        "description": "Chamfer all edges of a part with given distance.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "distance": {"type": "number"}},
            "required": ["name", "distance"],
        },
    },
    {
        "name": "shell",
        "description": "Hollow out a part with given wall thickness; one face becomes the opening.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"}, "thickness": {"type": "number"},
                "face": {"type": "string", "description": "CadQuery selector e.g. +Z, -Z, +X"},
            },
            "required": ["name", "thickness"],
        },
    },
    {
        "name": "hole",
        "description": "Drill a hole into the +Z face of a part.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"}, "radius": {"type": "number"},
                "depth": {"type": "number"},
            },
            "required": ["name", "radius"],
        },
    },
    {
        "name": "delete",
        "description": "Remove a part from the scene.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "list_parts",
        "description": "List parts currently in the scene with bounding boxes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "clear",
        "description": "Delete every part in the scene.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "undo",
        "description": "Revert the last engine operation.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "export_step",
        "description": "Export the combined scene to STEP. Returns absolute file path.",
        "input_schema": {
            "type": "object",
            "properties": {"filename": {"type": "string"}},
        },
    },
    # ---------------- 2D sketcher ---------------- #
    {
        "name": "sketch_new",
        "description": "Create a new 2D sketch on plane XY, XZ, or YZ.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"},
                           "plane": {"type": "string", "enum": ["XY", "XZ", "YZ"]}},
            "required": ["name"],
        },
    },
    {
        "name": "sketch_add_point",
        "description": "Add a 2D point to a sketch.",
        "input_schema": {
            "type": "object",
            "properties": {"sketch": {"type": "string"}, "point": {"type": "string"},
                           "x": {"type": "number"}, "y": {"type": "number"},
                           "fixed": {"type": "boolean"}},
            "required": ["sketch", "point", "x", "y"],
        },
    },
    {
        "name": "sketch_add_line",
        "description": "Add a line segment to a sketch (auto-creates two endpoints).",
        "input_schema": {
            "type": "object",
            "properties": {"sketch": {"type": "string"}, "line": {"type": "string"},
                           "x1": {"type": "number"}, "y1": {"type": "number"},
                           "x2": {"type": "number"}, "y2": {"type": "number"}},
            "required": ["sketch", "line", "x1", "y1", "x2", "y2"],
        },
    },
    {
        "name": "sketch_add_circle",
        "description": "Add a circle to a sketch.",
        "input_schema": {
            "type": "object",
            "properties": {"sketch": {"type": "string"}, "circle": {"type": "string"},
                           "cx": {"type": "number"}, "cy": {"type": "number"},
                           "r": {"type": "number"}},
            "required": ["sketch", "circle", "cx", "cy", "r"],
        },
    },
    {
        "name": "sketch_add_rect",
        "description": "Add a rectangle (4 lines + auto H/V constraints).",
        "input_schema": {
            "type": "object",
            "properties": {"sketch": {"type": "string"}, "rect": {"type": "string"},
                           "x": {"type": "number"}, "y": {"type": "number"},
                           "w": {"type": "number"}, "h": {"type": "number"}},
            "required": ["sketch", "rect", "x", "y", "w", "h"],
        },
    },
    {"name": "sketch_fix_point",
     "description": "Mark a sketch point as fixed (or unfix).",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "point": {"type": "string"},
                       "fixed": {"type": "boolean"}},
        "required": ["sketch", "point"]}},
    {"name": "sketch_c_coincident",
     "description": "Constrain two sketch points to be coincident.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "a": {"type": "string"}, "b": {"type": "string"}},
        "required": ["sketch", "a", "b"]}},
    {"name": "sketch_c_horizontal",
     "description": "Constrain a line to be horizontal.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "line": {"type": "string"}},
        "required": ["sketch", "line"]}},
    {"name": "sketch_c_vertical",
     "description": "Constrain a line to be vertical.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "line": {"type": "string"}},
        "required": ["sketch", "line"]}},
    {"name": "sketch_c_distance",
     "description": "Constrain the distance between two points.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "a": {"type": "string"},
                       "b": {"type": "string"}, "d": {"type": "number"}},
        "required": ["sketch", "a", "b", "d"]}},
    {"name": "sketch_c_distance_x",
     "description": "Signed X distance: x(b)-x(a) = d.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "a": {"type": "string"},
                       "b": {"type": "string"}, "d": {"type": "number"}},
        "required": ["sketch", "a", "b", "d"]}},
    {"name": "sketch_c_distance_y",
     "description": "Signed Y distance: y(b)-y(a) = d.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "a": {"type": "string"},
                       "b": {"type": "string"}, "d": {"type": "number"}},
        "required": ["sketch", "a", "b", "d"]}},
    {"name": "sketch_c_parallel",
     "description": "Constrain two lines to be parallel.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "a": {"type": "string"}, "b": {"type": "string"}},
        "required": ["sketch", "a", "b"]}},
    {"name": "sketch_c_perpendicular",
     "description": "Constrain two lines to be perpendicular.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "a": {"type": "string"}, "b": {"type": "string"}},
        "required": ["sketch", "a", "b"]}},
    {"name": "sketch_c_equal",
     "description": "Constrain two lines (or two circles) to have equal length/radius.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "a": {"type": "string"}, "b": {"type": "string"}},
        "required": ["sketch", "a", "b"]}},
    {"name": "sketch_c_radius",
     "description": "Constrain a circle's radius.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "circle": {"type": "string"}, "r": {"type": "number"}},
        "required": ["sketch", "circle", "r"]}},
    {"name": "sketch_c_angle",
     "description": "Constrain the angle (degrees) between two lines.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "a": {"type": "string"},
                       "b": {"type": "string"}, "degrees": {"type": "number"}},
        "required": ["sketch", "a", "b", "degrees"]}},
    {"name": "sketch_solve",
     "description": "Run the constraint solver on a sketch.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}}, "required": ["sketch"]}},
    {"name": "sketch_extrude",
     "description": "Extrude a sketch's closed loops into a named 3D part.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "part": {"type": "string"},
                       "depth": {"type": "number"}},
        "required": ["sketch", "part", "depth"]}},
    {"name": "sketch_revolve",
     "description": "Revolve a sketch into a 3D part about world X/Y/Z axis.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "part": {"type": "string"},
                       "axis": {"type": "string", "enum": ["X","Y","Z"]},
                       "degrees": {"type": "number"}},
        "required": ["sketch", "part"]}},
    {"name": "sketch_list_sketches",
     "description": "List all sketches in the project.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "sketch_info",
     "description": "Show all points, lines, circles, and constraints of a sketch.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "sketch_delete",
     "description": "Delete a sketch.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    # ---------------- assemblies ---------------- #
    {"name": "asm_new",
     "description": "Create a new (empty) assembly.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "asm_add_component",
     "description": "Add a part to an assembly as a named component, with placement.",
     "input_schema": {"type": "object",
        "properties": {"assembly": {"type": "string"}, "component": {"type": "string"},
                       "part": {"type": "string"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"},
                       "rx": {"type": "number"}, "ry": {"type": "number"}, "rz": {"type": "number"}},
        "required": ["assembly", "component", "part"]}},
    {"name": "asm_move_component",
     "description": "Translate a component by (dx,dy,dz).",
     "input_schema": {"type": "object",
        "properties": {"assembly": {"type": "string"}, "component": {"type": "string"},
                       "dx": {"type": "number"}, "dy": {"type": "number"}, "dz": {"type": "number"}},
        "required": ["assembly", "component"]}},
    {"name": "asm_rotate_component",
     "description": "Rotate a component by (rx,ry,rz) degrees.",
     "input_schema": {"type": "object",
        "properties": {"assembly": {"type": "string"}, "component": {"type": "string"},
                       "rx": {"type": "number"}, "ry": {"type": "number"}, "rz": {"type": "number"}},
        "required": ["assembly", "component"]}},
    {"name": "asm_remove_component",
     "description": "Remove a component from an assembly.",
     "input_schema": {"type": "object",
        "properties": {"assembly": {"type": "string"}, "component": {"type": "string"}},
        "required": ["assembly", "component"]}},
    {"name": "asm_add_mate",
     "description": "Add a mate constraint (Plane/Axis/Point). Selectors are '<comp>.face.<top|bottom|left|right|front|back>', '<comp>.edge.<idx>', '<comp>.axis.<X|Y|Z>', or '<comp>.point.<vertex_idx>'. Solved by asm_solve via CadQuery's constraint solver.",
     "input_schema": {"type": "object",
        "properties": {"assembly": {"type": "string"}, "kind": {"type": "string"},
                       "a_sel": {"type": "string"}, "b_sel": {"type": "string"}},
        "required": ["assembly", "kind", "a_sel", "b_sel"]}},
    {"name": "asm_solve",
     "description": "Solve any recorded mate constraints, then build the assembly compound and put it in the 3D scene as '_asm_<name>'. If the solver fails, falls back to placement-only and prefixes a WARNING to the result.",
     "input_schema": {"type": "object",
        "properties": {"assembly": {"type": "string"}}, "required": ["assembly"]}},
    {"name": "asm_list_assemblies",
     "description": "List all assemblies.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "asm_info",
     "description": "Show all components and mates of an assembly.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "asm_delete",
     "description": "Delete an assembly.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "asm_export_step",
     "description": "Export an assembly as STEP. Returns the file path.",
     "input_schema": {"type": "object",
        "properties": {"assembly": {"type": "string"}, "filename": {"type": "string"}},
        "required": ["assembly"]}},
    # ---------------- advanced 3D ops ---------------- #
    {"name": "sweep",
     "description": "Sweep a 2D profile sketch along a 2D path sketch into a 3D part.",
     "input_schema": {"type": "object",
        "properties": {"part": {"type": "string"},
                       "profile_sketch": {"type": "string"},
                       "path_sketch": {"type": "string"}},
        "required": ["part", "profile_sketch", "path_sketch"]}},
    {"name": "loft",
     "description": "Loft through 2+ sketch profiles into a 3D part.",
     "input_schema": {"type": "object",
        "properties": {"part": {"type": "string"},
                       "sketches": {"type": "array", "items": {"type": "string"}}},
        "required": ["part", "sketches"]}},
    {"name": "helix",
     "description": "Build a helical solid (spring-like) by sweeping a small circle along a helix of given radius, pitch, height.",
     "input_schema": {"type": "object",
        "properties": {"part": {"type": "string"},
                       "radius": {"type": "number"}, "pitch": {"type": "number"},
                       "height": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["part", "radius", "pitch", "height"]}},
    {"name": "thread",
     "description": "External 60-deg triangular thread swept along a helix. Union onto your own cylinder for a screw.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "radius": {"type": "number"}, "pitch": {"type": "number"},
                       "length": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "radius", "pitch", "length"]}},
    # ---------------- sketcher: arcs + splines ---------------- #
    {"name": "sketch_add_arc",
     "description": "Add a CCW arc by center / start / end points. Radius is implicit (|c-s|=|c-e| auto-constrained).",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "name": {"type": "string"},
                       "cx": {"type": "number"}, "cy": {"type": "number"},
                       "sx": {"type": "number"}, "sy": {"type": "number"},
                       "ex": {"type": "number"}, "ey": {"type": "number"}},
        "required": ["sketch", "name", "cx", "cy", "sx", "sy", "ex", "ey"]}},
    {"name": "sketch_add_spline",
     "description": "Add a cubic spline through a list of (x,y) control points.",
     "input_schema": {"type": "object",
        "properties": {"sketch": {"type": "string"}, "name": {"type": "string"},
                       "points": {"type": "array",
                                  "items": {"type": "array",
                                            "items": {"type": "number"}}}},
        "required": ["sketch", "name", "points"]}},
]


SYSTEM_PROMPT = """You are the brain of a chat-driven CAD tool that uses CadQuery
(OpenCascade) as its kernel. The user describes parts in natural language; you
build them by calling the provided tools.

You have three families of tools:

1. Direct 3D ops (box, cylinder, union, cut, fillet, ...). Use these when the
   user wants a quick part built from primitives + booleans.

2. 2D sketcher (sketch_new, sketch_add_line, sketch_c_*, sketch_solve,
   sketch_extrude, sketch_revolve). Use this when the user describes a
   parametric profile, a sketch with constraints, or wants to extrude a 2D
   shape into 3D. Workflow:
     - sketch_new <name> on a plane
     - add lines / circles / rectangles
     - add constraints (horizontal, vertical, distance, equal, ...)
     - sketch_solve <name>
     - sketch_extrude or sketch_revolve into a named 3D part
   sketch_add_line auto-creates two endpoints named <line>_a and <line>_b.
   To weld two line endpoints together, use sketch_c_coincident.

3. Assemblies (asm_new, asm_add_component, asm_solve, asm_export_step).
   Components are placed by position+rotation. Mate constraints are recorded
   (asm_add_mate) but only the placement is used for v1 positioning. After
   asm_solve, the combined compound appears in the 3D scene as '_asm_<name>'.

4. Advanced 3D ops: sweep (profile sketch along path sketch), loft (through
   >=2 sketch profiles), helix (spring-like solid from radius/pitch/height),
   and thread (external 60-deg triangular thread along a helix; union it
   onto a cylinder you create to make a screw).

Rules:
- Work in millimetres unless the user says otherwise.
- Snake_case names. Reuse names only to overwrite intentionally.
- For booleans, store results under a new name; operands stay unless deleted.
- After completing a build, briefly describe what is now in the scene (one
  or two sentences). Do NOT dump tool JSON in your reply.
- If the user asks something you can't do with the available tools, say so.
"""


def run_claude(client, model: str, history: list[dict], engine: CadEngine,
               user_message: str) -> tuple[str, list[str]]:
    """Run one user turn through Claude with the tool loop.

    Returns (final_text_reply, list_of_op_log_lines). Mutates `history`.
    """
    history.append({"role": "user", "content": user_message})
    op_log: list[str] = []

    for _ in range(25):  # hard cap on tool-use rounds
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=history,
        )
        history.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
            return ("\n".join(text_parts).strip() or "(done)", op_log)

        tool_results = []
        for block in resp.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            try:
                result = dispatch(engine, block.name, dict(block.input))
                op_log.append(f"{block.name}({block.input}) -> {result}")
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id, "content": str(result),
                })
            except Exception as e:
                op_log.append(f"{block.name}({block.input}) FAILED: {e}")
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": f"ERROR: {e}", "is_error": True,
                })
        history.append({"role": "user", "content": tool_results})

    return ("hit tool-use round cap; stopping.", op_log)


# ---------------- regex / shell-style fallback ---------------- #
_HELP = """commands (fallback parser, used when no Claude API key is set):

 3D parts:
  box <name> <L> <W> <H> [x y z]
  cyl <name> <r> <h> [x y z]
  sphere <name> <r> [x y z]
  cone <name> <r1> <r2> <h> [x y z]
  torus <name> <R> <r> [x y z]
  wedge <name> <dx> <dy> <dz> [x y z]
  poly  <name> <sides> <r> <h> [x y z]
  text  <name> "<text>" <size> <height> [x y z]
  scale <name> <sx> [sy sz]
  mirror <out> <src> [XY|XZ|YZ]
  lpat  <prefix> <src> <dx> <dy> <dz> <count>
  ppat  <prefix> <src> <count> [total_angle] [axis]
  move <name> <dx> <dy> <dz>
  rot  <name> <X|Y|Z> <deg>
  union <out> <a> <b>
  cut   <out> <a> <b>
  inter <out> <a> <b>
  fillet <name> <r>
  chamfer <name> <d>
  shell <name> <t> [face]
  hole <name> <r> [depth]
  delete <name>
  list | clear | undo | help
  export <step|stl> [filename]

 2D sketches:
  sk new   <name> [XY|XZ|YZ]
  sk line  <sk> <line> <x1> <y1> <x2> <y2>
  sk circle <sk> <c> <cx> <cy> <r>
  sk rect  <sk> <r> <x> <y> <w> <h>
  sk arc   <sk> <name> <cx> <cy> <sx> <sy> <ex> <ey>   (CCW arc)
  sk spline <sk> <name> <x1> <y1> <x2> <y2> [<x3> <y3> ...]
  sk pt    <sk> <p> <x> <y> [fixed]
  sk fix   <sk> <p>
  sk h     <sk> <line>           (horizontal)
  sk v     <sk> <line>           (vertical)
  sk coinc <sk> <pa> <pb>
  sk dist  <sk> <pa> <pb> <d>
  sk distx <sk> <pa> <pb> <d>
  sk disty <sk> <pa> <pb> <d>
  sk par   <sk> <la> <lb>
  sk perp  <sk> <la> <lb>
  sk eq    <sk> <a> <b>
  sk rad   <sk> <circle> <r>
  sk ang   <sk> <la> <lb> <deg>
  sk solve <sk>
  sk ext   <sk> <part> <depth>
  sk rev   <sk> <part> [axis] [deg]
  sk info  <sk>
  sk list
  sk del   <sk>

 Assemblies:
  asm new      <name>
  asm add      <asm> <comp> <part> [x y z [rx ry rz]]
  asm move     <asm> <comp> <dx> <dy> <dz>
  asm rot      <asm> <comp> <rx> <ry> <rz>
  asm rm       <asm> <comp>
  asm mate     <asm> <Plane|Axis|Point|PointInPlane> <a_sel> <b_sel>
  asm solve    <asm>
  asm info     <asm>
  asm list
  asm del      <asm>
  asm export   <asm> [filename]

 Advanced:
  sweep  <part> <profile_sk> <path_sk>
  loft   <part> <sk1> <sk2> [sk3 ...]
  helix  <part> <r> <pitch> <h> [x y z]
  thread <part> <r> <pitch> <L> [x y z]
"""


def _parse_sketch(engine: CadEngine, a: list[str]) -> str:
    if not a:
        return "missing sketch sub-command. try 'help'"
    sub, *r = a
    sub = sub.lower()
    sk = engine.sketches
    if sub == "new":
        name = r[0]; plane = r[1] if len(r) > 1 else "XY"
        return sk.new(name, plane)
    if sub == "line":
        return sk.add_line(r[0], r[1], _f(r[2]), _f(r[3]), _f(r[4]), _f(r[5]))
    if sub == "circle":
        return sk.add_circle(r[0], r[1], _f(r[2]), _f(r[3]), _f(r[4]))
    if sub == "rect":
        return sk.add_rect(r[0], r[1], _f(r[2]), _f(r[3]), _f(r[4]), _f(r[5]))
    if sub == "arc":
        return sk.add_arc(r[0], r[1], _f(r[2]), _f(r[3]),
                          _f(r[4]), _f(r[5]), _f(r[6]), _f(r[7]))
    if sub == "spline":
        sketch_name, spline_name, *coords = r
        if len(coords) < 4 or len(coords) % 2 != 0:
            return "ERROR: spline needs >=2 (x,y) pairs"
        pts = [(_f(coords[i]), _f(coords[i + 1])) for i in range(0, len(coords), 2)]
        return sk.add_spline(sketch_name, spline_name, pts)
    if sub == "pt":
        fixed = len(r) > 4 and r[4].lower() in ("1", "true", "fixed", "yes")
        return sk.add_point(r[0], r[1], _f(r[2]), _f(r[3]), fixed)
    if sub == "fix":
        return sk.fix_point(r[0], r[1], True)
    if sub == "h":
        return sk.c_horizontal(r[0], r[1])
    if sub == "v":
        return sk.c_vertical(r[0], r[1])
    if sub == "coinc":
        return sk.c_coincident(r[0], r[1], r[2])
    if sub == "dist":
        return sk.c_distance(r[0], r[1], r[2], _f(r[3]))
    if sub == "distx":
        return sk.c_distance_x(r[0], r[1], r[2], _f(r[3]))
    if sub == "disty":
        return sk.c_distance_y(r[0], r[1], r[2], _f(r[3]))
    if sub == "par":
        return sk.c_parallel(r[0], r[1], r[2])
    if sub == "perp":
        return sk.c_perpendicular(r[0], r[1], r[2])
    if sub == "eq":
        return sk.c_equal(r[0], r[1], r[2])
    if sub == "rad":
        return sk.c_radius(r[0], r[1], _f(r[2]))
    if sub == "ang":
        return sk.c_angle(r[0], r[1], r[2], _f(r[3]))
    if sub == "solve":
        return sk.solve(r[0])
    if sub == "ext":
        return sk.extrude(r[0], r[1], _f(r[2]))
    if sub == "rev":
        axis = r[2] if len(r) > 2 else "Y"
        deg = _f(r[3]) if len(r) > 3 else 360.0
        return sk.revolve(r[0], r[1], axis, deg)
    if sub == "info":
        return sk.info(r[0])
    if sub == "list":
        return sk.list_sketches()
    if sub == "del":
        return sk.delete(r[0])
    return f"unknown sketch sub-command '{sub}'"


def _parse_asm(engine: CadEngine, a: list[str]) -> str:
    if not a:
        return "missing asm sub-command. try 'help'"
    sub, *r = a
    sub = sub.lower()
    am = engine.assemblies
    if sub == "new":
        return am.new(r[0])
    if sub == "add":
        # asm add <asm> <comp> <part> [x y z [rx ry rz]]
        asm, comp, part, *rest = r
        nums = [_f(x) for x in rest] + [0] * 6
        return am.add_component(asm, comp, part,
                                nums[0], nums[1], nums[2],
                                nums[3], nums[4], nums[5])
    if sub == "move":
        return am.move_component(r[0], r[1], _f(r[2]), _f(r[3]), _f(r[4]))
    if sub == "rot":
        return am.rotate_component(r[0], r[1], _f(r[2]), _f(r[3]), _f(r[4]))
    if sub == "rm":
        return am.remove_component(r[0], r[1])
    if sub == "mate":
        return am.add_mate(r[0], r[1], r[2], r[3])
    if sub == "solve":
        return am.solve(r[0])
    if sub == "info":
        return am.info(r[0])
    if sub == "list":
        return am.list_assemblies()
    if sub == "del":
        return am.delete(r[0])
    if sub == "export":
        fname = r[1] if len(r) > 1 else None
        path = am.export_step(r[0], engine.output_dir, fname)
        return f"wrote {path}"
    return f"unknown asm sub-command '{sub}'"


def _f(x: str) -> float:
    return float(x)


def run_parser(engine: CadEngine, line: str) -> str:
    line = line.strip()
    if not line:
        return ""
    parts = shlex.split(line)
    cmd, *a = parts
    cmd = cmd.lower()

    try:
        if cmd in ("help", "?"):
            return _HELP
        if cmd in ("sk", "sketch"):
            return _parse_sketch(engine, a)
        if cmd in ("asm", "assembly"):
            return _parse_asm(engine, a)
        if cmd == "box":
            name, L, W, H, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.box(name, _f(L), _f(W), _f(H), xyz[0], xyz[1], xyz[2])
        if cmd in ("cyl", "cylinder"):
            name, r, h, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.cylinder(name, _f(r), _f(h), xyz[0], xyz[1], xyz[2])
        if cmd == "sphere":
            name, r, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.sphere(name, _f(r), xyz[0], xyz[1], xyz[2])
        if cmd == "cone":
            name, r1, r2, h, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.cone(name, _f(r1), _f(r2), _f(h), xyz[0], xyz[1], xyz[2])
        if cmd == "torus":
            name, R, r, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.torus(name, _f(R), _f(r), xyz[0], xyz[1], xyz[2])
        if cmd == "wedge":
            name, dx, dy, dz, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.wedge(name, _f(dx), _f(dy), _f(dz), xyz[0], xyz[1], xyz[2])
        if cmd in ("poly", "polygon"):
            name, sides, r, h, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.polygon(name, int(sides), _f(r), _f(h), xyz[0], xyz[1], xyz[2])
        if cmd == "text":
            # text <name> "the text" <size> <height> [x y z]
            name, txt, size, h, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.text_3d(name, txt, _f(size), _f(h),
                                  x=xyz[0], y=xyz[1], z=xyz[2])
        if cmd == "scale":
            name, sx, *rest = a
            sy = _f(rest[0]) if len(rest) > 0 else None
            sz = _f(rest[1]) if len(rest) > 1 else None
            return engine.scale(name, _f(sx), sy, sz)
        if cmd == "mirror":
            out, src, *rest = a
            plane = rest[0] if rest else "XY"
            return engine.mirror(out, src, plane)
        if cmd in ("lpat", "linpat", "linear_pattern"):
            prefix, src, dx, dy, dz, count = a
            return engine.linear_pattern(prefix, src, _f(dx), _f(dy), _f(dz), int(count))
        if cmd in ("ppat", "polpat", "polar_pattern"):
            prefix, src, count, *rest = a
            total = _f(rest[0]) if len(rest) > 0 else 360.0
            axis = rest[1] if len(rest) > 1 else "Z"
            return engine.polar_pattern(prefix, src, int(count), total, axis)
        if cmd == "move":
            name, dx, dy, dz = a
            return engine.translate(name, _f(dx), _f(dy), _f(dz))
        if cmd == "rot":
            name, axis, deg = a
            return engine.rotate(name, axis, _f(deg))
        if cmd == "union":
            return engine.union(a[0], a[1], a[2])
        if cmd == "cut":
            return engine.cut(a[0], a[1], a[2])
        if cmd in ("inter", "intersect"):
            return engine.intersect(a[0], a[1], a[2])
        if cmd == "fillet":
            return engine.fillet(a[0], _f(a[1]))
        if cmd == "chamfer":
            return engine.chamfer(a[0], _f(a[1]))
        if cmd == "shell":
            face = a[2] if len(a) > 2 else "+Z"
            return engine.shell(a[0], _f(a[1]), face)
        if cmd == "hole":
            depth = _f(a[2]) if len(a) > 2 else None
            return engine.hole(a[0], _f(a[1]), depth)
        if cmd == "delete":
            return engine.delete(a[0])
        if cmd == "list":
            return engine.list_parts()
        if cmd == "clear":
            return engine.clear()
        if cmd == "undo":
            return engine.undo()
        if cmd == "export":
            fmt = a[0].lower()
            fname = a[1] if len(a) > 1 else f"scene.{fmt}"
            if fmt == "step":
                return f"wrote {engine.export_step(fname)}"
            if fmt == "stl":
                return f"wrote {engine.export_stl(fname)}"
            return f"unknown export format '{fmt}'"
        if cmd == "sweep":
            part, prof, path = a
            return engine.sweep(part, prof, path)
        if cmd == "loft":
            part, *sks = a
            return engine.loft(part, sks)
        if cmd == "helix":
            part, r, pitch, h, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.helix(part, _f(r), _f(pitch), _f(h),
                                xyz[0], xyz[1], xyz[2])
        if cmd == "thread":
            part, r, pitch, L, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.thread(part, _f(r), _f(pitch), _f(L),
                                 xyz[0], xyz[1], xyz[2])
        return f"unknown command '{cmd}'. type 'help'."
    except Exception as e:
        return f"ERROR: {e}"
