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
    # ---------------- parametric components library ---------------- #
    {"name": "lib_bolt",
     "description": "M-series hex-head bolt. spec like 'M6', length in mm.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "spec": {"type": "string"},
                       "length": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "spec", "length"]}},
    {"name": "lib_nut",
     "description": "M-series hex nut.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "spec": {"type": "string"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "spec"]}},
    {"name": "lib_washer",
     "description": "M-series flat washer.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "spec": {"type": "string"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "spec"]}},
    {"name": "lib_gear",
     "description": "Visual spur gear. module = pitch_diameter / teeth. bore is optional through-hole.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "module": {"type": "number"}, "teeth": {"type": "integer"},
                       "width": {"type": "number"}, "bore": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "module", "teeth", "width"]}},
    {"name": "lib_spring",
     "description": "Helical compression spring.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "wire_d": {"type": "number"}, "coil_d": {"type": "number"},
                       "pitch": {"type": "number"}, "turns": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "wire_d", "coil_d", "pitch", "turns"]}},
    {"name": "lib_slot",
     "description": "Stadium-shaped slot extruded along Z.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "length": {"type": "number"}, "width": {"type": "number"},
                       "depth": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "length", "width", "depth"]}},
    {"name": "lib_key",
     "description": "Rectangular machine key (DIN 6885 shape).",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "length": {"type": "number"}, "width": {"type": "number"},
                       "thickness": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "length", "width", "thickness"]}},
    {"name": "lib_bearing",
     "description": "Deep-groove ball bearing visualisation: bore, od, width in mm.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "bore": {"type": "number"}, "od": {"type": "number"},
                       "width": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "bore", "od", "width"]}},
    {"name": "lib_threaded_insert",
     "description": "Heat-set / press-fit threaded insert sized for an M-bolt.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "spec": {"type": "string"},
                       "length": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "spec", "length"]}},
    {"name": "lib_dowel",
     "description": "Cylindrical dowel pin with chamfered ends.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "diameter": {"type": "number"}, "length": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "diameter", "length"]}},
    {"name": "lib_hinge",
     "description": "Barrel hinge with N knuckles, two leaves, and a pin.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "length": {"type": "number"}, "leaf_width": {"type": "number"},
                       "pin_d": {"type": "number"}, "knuckles": {"type": "integer"},
                       "leaf_thickness": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "length", "leaf_width", "pin_d"]}},
    {"name": "lib_pulley",
     "description": "Single V-groove pulley; bore is optional through-hole.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "od": {"type": "number"}, "width": {"type": "number"},
                       "bore": {"type": "number"}, "belt_width": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "od", "width"]}},
    # ---------------- aerospace mockups ---------------- #
    {"name": "lib_turbine",
     "description": "Turbine wheel: central disc + N twisted airfoil blades around the rim. Visual mockup only.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "blade_count": {"type": "integer"},
                       "od": {"type": "number"}, "hub_d": {"type": "number"},
                       "hub_thickness": {"type": "number"},
                       "blade_chord": {"type": "number"}, "blade_twist_deg": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "blade_count", "od", "hub_d", "hub_thickness"]}},
    {"name": "lib_propeller",
     "description": "Aircraft propeller: hub + N twisted blades with airfoil sections.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "blade_count": {"type": "integer"},
                       "diameter": {"type": "number"}, "hub_d": {"type": "number"},
                       "root_chord": {"type": "number"}, "tip_chord": {"type": "number"},
                       "twist_deg": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "blade_count", "diameter", "hub_d"]}},
    {"name": "lib_compressor",
     "description": "Compressor stage: thin annular ring with N twisted blades.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "blade_count": {"type": "integer"},
                       "hub_d": {"type": "number"}, "od": {"type": "number"},
                       "blade_height": {"type": "number"},
                       "blade_chord": {"type": "number"}, "twist_deg": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "blade_count", "hub_d", "od", "blade_height"]}},
    {"name": "lib_nozzle",
     "description": "Converging-diverging bell nozzle (rocket / jet exhaust). Shelled solid of revolution.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "throat_d": {"type": "number"}, "exit_d": {"type": "number"},
                       "inlet_d": {"type": "number"}, "length": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "throat_d", "exit_d", "inlet_d", "length"]}},
    {"name": "lib_combustor",
     "description": "Combustor liner: cylindrical can with N rings of cooling holes.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "diameter": {"type": "number"}, "length": {"type": "number"},
                       "wall_thickness": {"type": "number"},
                       "hole_diameter": {"type": "number"},
                       "hole_rings": {"type": "integer"}, "holes_per_ring": {"type": "integer"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "diameter", "length"]}},
    {"name": "lib_honeycomb",
     "description": "Honeycomb structural panel: flat plate with hexagonal cells cut out.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "length": {"type": "number"}, "width": {"type": "number"},
                       "thickness": {"type": "number"},
                       "cell_size": {"type": "number"}, "wall_thickness": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "length", "width", "thickness"]}},
    {"name": "lib_naca",
     "description": "Extruded NACA 4-digit airfoil wing section (e.g. code '2412' for NACA 2412).",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "code": {"type": "string"},
                       "chord": {"type": "number"}, "span": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "code", "chord", "span"]}},
    # ---------------- materials ---------------- #
    {"name": "mat_assign",
     "description": "Assign a material to a part. Available: steel, stainless, aluminum, brass, copper, titanium, pla, abs, nylon, rubber, wood, glass, concrete, lead.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "material": {"type": "string"}},
        "required": ["name", "material"]}},
    {"name": "mat_report",
     "description": "Show volume / mass / COG / inertia tensor for a part.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    # ---------------- structural profiles ---------------- #
    {"name": "prof_tslot",
     "description": "Aluminum T-slot extrusion (metric series 20/30/40), length along Z.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "series": {"type": "integer"},
                       "length": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "series", "length"]}},
    {"name": "prof_angle",
     "description": "L-section angle iron with sides a x b, wall thickness t.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "side_a": {"type": "number"}, "side_b": {"type": "number"},
                       "thickness": {"type": "number"}, "length": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "side_a", "side_b", "thickness", "length"]}},
    {"name": "prof_sqtube",
     "description": "Hollow square tube (side x side, wall thickness).",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "side": {"type": "number"}, "wall": {"type": "number"},
                       "length": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "side", "wall", "length"]}},
    {"name": "prof_rtube",
     "description": "Hollow round tube (OD, wall thickness).",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "od": {"type": "number"}, "wall": {"type": "number"},
                       "length": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "od", "wall", "length"]}},
    {"name": "prof_ibeam",
     "description": "Symmetric I-beam (height, width, web thickness, flange thickness).",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "height": {"type": "number"}, "width": {"type": "number"},
                       "web_t": {"type": "number"}, "flange_t": {"type": "number"},
                       "length": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "height", "width", "web_t", "flange_t", "length"]}},
    {"name": "prof_cchan",
     "description": "C-channel (height, width, wall thickness).",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "height": {"type": "number"}, "width": {"type": "number"},
                       "thickness": {"type": "number"}, "length": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "height", "width", "thickness", "length"]}},
    # ---------------- sheet metal ---------------- #
    {"name": "sm_flat",
     "description": "Flat sheet metal panel.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "length": {"type": "number"}, "width": {"type": "number"},
                       "thickness": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "length", "width", "thickness"]}},
    {"name": "sm_l_bend",
     "description": "L-shaped 90deg bent sheet (two legs a and b, optional bend radius).",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "length": {"type": "number"}, "width": {"type": "number"},
                       "thickness": {"type": "number"},
                       "leg_a": {"type": "number"}, "leg_b": {"type": "number"},
                       "bend_radius": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "length", "width", "thickness", "leg_a", "leg_b"]}},
    {"name": "sm_u_bend",
     "description": "U-shaped (channel) bent sheet.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "length": {"type": "number"}, "width": {"type": "number"},
                       "thickness": {"type": "number"},
                       "leg_height": {"type": "number"}, "bend_radius": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "length", "width", "thickness", "leg_height"]}},
    {"name": "sm_box",
     "description": "Open-top sheet-metal box: floor + 4 walls.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "length": {"type": "number"}, "width": {"type": "number"},
                       "height": {"type": "number"}, "thickness": {"type": "number"},
                       "bend_radius": {"type": "number"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "length", "width", "height", "thickness"]}},
    {"name": "sm_flange",
     "description": "Add a perpendicular flange to an existing flat sheet along an edge (+X/-X/+Y/-Y).",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "edge_axis": {"type": "string"},
                       "flange_length": {"type": "number"}, "thickness": {"type": "number"},
                       "bend_radius": {"type": "number"}},
        "required": ["name"]}},
    # ---------------- STEP import ---------------- #
    {"name": "step_import",
     "description": "Import a STEP file from a local path into the scene as a named part. Use for supplier models (McMaster, Bosch, etc.).",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "path": {"type": "string"},
                       "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["name", "path"]}},
    # ---------------- selective fillet / chamfer ---------------- #
    {"name": "fillet_edges",
     "description": "Fillet edges matching a CadQuery selector ('all','+Z','-Z','|Z','>Z',etc).",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "radius": {"type": "number"},
                       "selector": {"type": "string"}},
        "required": ["name", "radius"]}},
    {"name": "chamfer_edges",
     "description": "Chamfer edges matching a CadQuery selector.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "distance": {"type": "number"},
                       "selector": {"type": "string"}},
        "required": ["name", "distance"]}},
    # ---------------- finished holes ---------------- #
    {"name": "counterbore",
     "description": "Counterbored hole on a face. Common for socket-head cap screws.",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "diameter": {"type": "number"},
                       "cbore_diameter": {"type": "number"},
                       "cbore_depth": {"type": "number"},
                       "depth": {"type": "number"},
                       "face": {"type": "string"}},
        "required": ["name", "diameter", "cbore_diameter", "cbore_depth"]}},
    {"name": "countersink",
     "description": "Countersunk hole on a face. Common for flat-head screws (82deg default).",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"},
                       "diameter": {"type": "number"},
                       "csk_diameter": {"type": "number"},
                       "csk_angle": {"type": "number"},
                       "depth": {"type": "number"},
                       "face": {"type": "string"}},
        "required": ["name", "diameter", "csk_diameter"]}},
    {"name": "tapped_hole",
     "description": "Threaded hole sized for an M-bolt (visualisation only; no helical thread cut).",
     "input_schema": {"type": "object",
        "properties": {"name": {"type": "string"}, "M_spec": {"type": "string"},
                       "depth": {"type": "number"}, "face": {"type": "string"}},
        "required": ["name", "M_spec", "depth"]}},
    # ---------------- sketch-driven features ---------------- #
    {"name": "boss_extrude",
     "description": "Extrude a sketch and UNION it onto an existing part (SolidWorks 'Boss/Extrude').",
     "input_schema": {"type": "object",
        "properties": {"base": {"type": "string"}, "sketch": {"type": "string"},
                       "depth": {"type": "number"}, "face": {"type": "string"}},
        "required": ["base", "sketch", "depth"]}},
    {"name": "cut_extrude",
     "description": "Extrude a sketch and CUT it from an existing part (pockets, hole arrays).",
     "input_schema": {"type": "object",
        "properties": {"base": {"type": "string"}, "sketch": {"type": "string"},
                       "depth": {"type": "number"}, "face": {"type": "string"}},
        "required": ["base", "sketch", "depth"]}},
    {"name": "pattern_along_curve",
     "description": "Stamp `count` copies of `src` along the bolt-circle defined by a sketch.",
     "input_schema": {"type": "object",
        "properties": {"prefix": {"type": "string"}, "src": {"type": "string"},
                       "sketch": {"type": "string"}, "count": {"type": "integer"}},
        "required": ["prefix", "src", "sketch", "count"]}},
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

4. Parametric components library (lib_bolt, lib_nut, lib_washer, lib_gear,
   lib_spring, lib_slot, lib_key). Use these when the user asks for a
   standard mechanical component instead of building one from primitives.
   M-specs accept M2, M2.5, M3, M4, M5, M6, M8, M10, M12, M16, M20.

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

 Mechanical components:
  bolt   <name> <M-spec> <length> [x y z]      e.g.  bolt b1 M6 30
  nut    <name> <M-spec>          [x y z]      e.g.  nut n1 M6
  washer <name> <M-spec>          [x y z]      e.g.  washer w1 M6
  gear   <name> <module> <teeth> <width> [bore] [x y z]
  spring <name> <wire_d> <coil_d> <pitch> <turns> [x y z]
  slot   <name> <length> <width> <depth> [x y z]
  key    <name> <length> <width> <thickness>   [x y z]
  bearing <name> <bore> <od> <width> [x y z]
  insert  <name> <M-spec> <length> [x y z]
  dowel   <name> <d> <L> [x y z]
  hinge   <name> <L> <leaf_w> <pin_d> [knuckles] [leaf_t] [x y z]
  pulley  <name> <od> <width> [bore] [belt_w] [x y z]

 Aerospace mockups (visual; not engineering-grade):
  turbine    <name> <blades> <od> <hub_d> <hub_t> [chord] [twist] [x y z]
  propeller  <name> <blades> <D> <hub_d> [root_c] [tip_c] [twist] [x y z]
  compressor <name> <blades> <hub_d> <od> <height> [chord] [twist] [x y z]
  nozzle     <name> <throat_d> <exit_d> <inlet_d> <length> [x y z]
  combustor  <name> <D> <L> [wall] [hole_d] [rings] [per_ring] [x y z]
  honeycomb  <name> <L> <W> <T> [cell] [wall] [x y z]
  naca       <name> <NACA4-code> <chord> <span> [x y z]

 Materials / mass properties:
  mat list                                  show density table
  mat assign <part> <material>              steel|aluminum|brass|pla|abs|...
  mat report <part>                         volume, mass, COG, inertia

 Structural profiles:
  tslot   <name> <series> <length> [x y z]      series=20|30|40
  angle   <name> <a> <b> <t> <length> [x y z]
  sqtube  <name> <side> <wall> <length> [x y z]
  rtube   <name> <od>   <wall> <length> [x y z]
  ibeam   <name> <H> <W> <web> <flange> <length> [x y z]
  cchan   <name> <H> <W> <t> <length> [x y z]

 Sheet metal:
  sheet flat   <name> <L> <W> <t> [x y z]
  sheet l      <name> <L> <W> <t> <leg_a> <leg_b> [bend_r] [x y z]
  sheet u      <name> <L> <W> <t> <leg_h>         [bend_r] [x y z]
  sheet box    <name> <L> <W> <H> <t>             [bend_r] [x y z]
  sheet flange <name> <+X|-X|+Y|-Y> <flange_L> [t] [bend_r]

 STEP import:
  step import <name> <path-to-file.step> [x y z]

 Engineering drawing PDF (via UI button or HTTP endpoint):
  GET /drawing/<part>.pdf     download a 4-view PDF of one part
  GET /drawings.pdf           multi-page PDF, one per part

 Selective fillet / chamfer / holes / sketch-driven features:
  filletx  <name> <radius> [selector]     selector e.g. >Z, |Z, +X, all
  chamferx <name> <dist>   [selector]
  cbore   <name> <d> <cbore_d> <cbore_depth> [depth] [face]
  csink   <name> <d> <csk_d> [angle] [depth] [face]
  tap     <name> <M-spec> <depth> [face]
  boss    <base> <sketch> <depth> [face]
  pocket  <base> <sketch> <depth> [face]
  cpat    <prefix> <src> <sketch> <count>    pattern along a sketch's bolt-circle
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
        if cmd == "bolt":
            name, spec, length, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.library.bolt(name, spec, _f(length),
                                       xyz[0], xyz[1], xyz[2])
        if cmd == "nut":
            name, spec, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.library.nut(name, spec, xyz[0], xyz[1], xyz[2])
        if cmd == "washer":
            name, spec, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.library.washer(name, spec, xyz[0], xyz[1], xyz[2])
        if cmd == "gear":
            # gear <name> <module> <teeth> <width> [bore] [x y z]
            name, module, teeth, width, *rest = a
            bore = _f(rest[0]) if len(rest) > 0 else 0
            xyz = [_f(v) for v in rest[1:]] + [0, 0, 0]
            return engine.library.gear(name, _f(module), int(teeth), _f(width),
                                       bore, xyz[0], xyz[1], xyz[2])
        if cmd == "spring":
            name, wire_d, coil_d, pitch, turns, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.library.spring(name, _f(wire_d), _f(coil_d),
                                         _f(pitch), _f(turns),
                                         xyz[0], xyz[1], xyz[2])
        if cmd == "slot":
            name, length, width, depth, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.library.slot(name, _f(length), _f(width), _f(depth),
                                       xyz[0], xyz[1], xyz[2])
        if cmd == "key":
            name, length, width, thickness, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.library.key(name, _f(length), _f(width),
                                      _f(thickness), xyz[0], xyz[1], xyz[2])
        if cmd == "bearing":
            name, bore, od, width, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.library.bearing(name, _f(bore), _f(od), _f(width),
                                          xyz[0], xyz[1], xyz[2])
        if cmd == "insert":
            name, spec, length, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.library.threaded_insert(name, spec, _f(length),
                                                  xyz[0], xyz[1], xyz[2])
        if cmd == "dowel":
            name, d, L, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.library.dowel(name, _f(d), _f(L),
                                        xyz[0], xyz[1], xyz[2])
        if cmd == "hinge":
            # hinge <name> <length> <leaf_w> <pin_d> [knuckles] [leaf_t] [x y z]
            name, L, lw, pd, *rest = a
            knuckles = int(rest[0]) if len(rest) > 0 else 3
            leaf_t = _f(rest[1]) if len(rest) > 1 else 2.0
            xyz = [_f(v) for v in rest[2:]] + [0, 0, 0]
            return engine.library.hinge(name, _f(L), _f(lw), _f(pd),
                                        knuckles, leaf_t,
                                        xyz[0], xyz[1], xyz[2])
        if cmd == "pulley":
            # pulley <name> <od> <width> [bore] [belt_w] [x y z]
            name, od, w, *rest = a
            bore = _f(rest[0]) if len(rest) > 0 else 0
            belt_w = _f(rest[1]) if len(rest) > 1 else 6.0
            xyz = [_f(v) for v in rest[2:]] + [0, 0, 0]
            return engine.library.pulley(name, _f(od), _f(w), bore, belt_w,
                                         xyz[0], xyz[1], xyz[2])
        if cmd == "turbine":
            # turbine <name> <blades> <od> <hub_d> <hub_t> [chord] [twist] [x y z]
            name, blades, od, hub_d, hub_t, *rest = a
            chord = _f(rest[0]) if len(rest) > 0 else 0
            twist = _f(rest[1]) if len(rest) > 1 else 18
            xyz = [_f(v) for v in rest[2:]] + [0, 0, 0]
            return engine.library.turbine(name, int(blades), _f(od), _f(hub_d),
                                          _f(hub_t), chord, twist,
                                          xyz[0], xyz[1], xyz[2])
        if cmd == "propeller":
            # propeller <name> <blades> <D> <hub_d> [root_chord] [tip_chord] [twist] [x y z]
            name, blades, D, hub_d, *rest = a
            rc = _f(rest[0]) if len(rest) > 0 else 0
            tc = _f(rest[1]) if len(rest) > 1 else 0
            tw = _f(rest[2]) if len(rest) > 2 else 28
            xyz = [_f(v) for v in rest[3:]] + [0, 0, 0]
            return engine.library.propeller(name, int(blades), _f(D), _f(hub_d),
                                            rc, tc, tw, xyz[0], xyz[1], xyz[2])
        if cmd == "compressor":
            # compressor <name> <blades> <hub_d> <od> <height> [chord] [twist] [x y z]
            name, blades, hub_d, od, height, *rest = a
            chord = _f(rest[0]) if len(rest) > 0 else 0
            twist = _f(rest[1]) if len(rest) > 1 else 12
            xyz = [_f(v) for v in rest[2:]] + [0, 0, 0]
            return engine.library.compressor(name, int(blades), _f(hub_d),
                                             _f(od), _f(height), chord, twist,
                                             xyz[0], xyz[1], xyz[2])
        if cmd == "nozzle":
            # nozzle <name> <throat_d> <exit_d> <inlet_d> <length> [x y z]
            name, td, ed, idia, L, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.library.nozzle(name, _f(td), _f(ed), _f(idia), _f(L),
                                         xyz[0], xyz[1], xyz[2])
        if cmd == "combustor":
            # combustor <name> <D> <L> [wall] [hole_d] [rings] [per_ring] [x y z]
            name, D, L, *rest = a
            wall = _f(rest[0]) if len(rest) > 0 else 2
            hd   = _f(rest[1]) if len(rest) > 1 else 4
            rings = int(rest[2]) if len(rest) > 2 else 6
            per   = int(rest[3]) if len(rest) > 3 else 24
            xyz = [_f(v) for v in rest[4:]] + [0, 0, 0]
            return engine.library.combustor(name, _f(D), _f(L), wall, hd,
                                            rings, per, xyz[0], xyz[1], xyz[2])
        if cmd == "honeycomb":
            # honeycomb <name> <L> <W> <T> [cell] [wall] [x y z]
            name, L, W, T, *rest = a
            cell = _f(rest[0]) if len(rest) > 0 else 6
            wall = _f(rest[1]) if len(rest) > 1 else 0.6
            xyz = [_f(v) for v in rest[2:]] + [0, 0, 0]
            return engine.library.honeycomb(name, _f(L), _f(W), _f(T),
                                            cell, wall,
                                            xyz[0], xyz[1], xyz[2])
        if cmd == "naca":
            # naca <name> <code> <chord> <span> [x y z]
            name, code, chord, span, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.library.naca(name, code, _f(chord), _f(span),
                                       xyz[0], xyz[1], xyz[2])
        # ---------------- materials ----------------
        if cmd == "mat":
            # mat assign <name> <material>  |  mat report <name>  |  mat list
            sub = a[0].lower() if a else ""
            if sub == "list":
                from materials import list_materials
                return list_materials()
            if sub == "assign":
                return engine.materials.assign(a[1], a[2])
            if sub == "report":
                return engine.materials.report(a[1])
            return f"unknown mat sub-command '{sub}'"
        # ---------------- structural profiles ----------------
        if cmd == "tslot":
            name, series, length, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.profiles.tslot(name, int(series), _f(length),
                                          xyz[0], xyz[1], xyz[2])
        if cmd == "angle":
            name, sa, sb, t, L, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.profiles.angle(name, _f(sa), _f(sb), _f(t), _f(L),
                                          xyz[0], xyz[1], xyz[2])
        if cmd == "sqtube":
            name, side, wall, L, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.profiles.sqtube(name, _f(side), _f(wall), _f(L),
                                           xyz[0], xyz[1], xyz[2])
        if cmd == "rtube":
            name, od, wall, L, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.profiles.rtube(name, _f(od), _f(wall), _f(L),
                                          xyz[0], xyz[1], xyz[2])
        if cmd == "ibeam":
            name, H, W, web, flange, L, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.profiles.ibeam(name, _f(H), _f(W), _f(web),
                                          _f(flange), _f(L),
                                          xyz[0], xyz[1], xyz[2])
        if cmd == "cchan":
            name, H, W, t, L, *rest = a
            xyz = [_f(v) for v in rest] + [0, 0, 0]
            return engine.profiles.cchan(name, _f(H), _f(W), _f(t), _f(L),
                                          xyz[0], xyz[1], xyz[2])
        # ---------------- sheet metal ----------------
        if cmd == "sheet":
            sub = a[0].lower() if a else ""
            if sub == "flat":
                _, name, L, W, t, *rest = a
                xyz = [_f(v) for v in rest] + [0, 0, 0]
                return engine.sheet.flat(name, _f(L), _f(W), _f(t),
                                          xyz[0], xyz[1], xyz[2])
            if sub == "l":
                _, name, L, W, t, la, lb, *rest = a
                br = _f(rest[0]) if rest else 0
                xyz = [_f(v) for v in rest[1:]] + [0, 0, 0]
                return engine.sheet.l_bend(name, _f(L), _f(W), _f(t),
                                            _f(la), _f(lb), br,
                                            xyz[0], xyz[1], xyz[2])
            if sub == "u":
                _, name, L, W, t, lh, *rest = a
                br = _f(rest[0]) if rest else 0
                xyz = [_f(v) for v in rest[1:]] + [0, 0, 0]
                return engine.sheet.u_bend(name, _f(L), _f(W), _f(t), _f(lh),
                                            br, xyz[0], xyz[1], xyz[2])
            if sub == "box":
                _, name, L, W, H, t, *rest = a
                br = _f(rest[0]) if rest else 0
                xyz = [_f(v) for v in rest[1:]] + [0, 0, 0]
                return engine.sheet.box(name, _f(L), _f(W), _f(H), _f(t), br,
                                         xyz[0], xyz[1], xyz[2])
            if sub == "flange":
                _, name, edge, fl, *rest = a
                t = _f(rest[0]) if len(rest) > 0 else 2
                br = _f(rest[1]) if len(rest) > 1 else 0
                return engine.sheet.flange(name, edge, _f(fl), t, br)
            return f"unknown sheet sub-command '{sub}'"
        # ---------------- STEP import ----------------
        if cmd == "step":
            sub = a[0].lower() if a else ""
            if sub == "import":
                _, name, path, *rest = a
                xyz = [_f(v) for v in rest] + [0, 0, 0]
                return engine.step_io.step_import(name, path,
                                                   xyz[0], xyz[1], xyz[2])
            return f"unknown step sub-command '{sub}'"
        if cmd in ("fillete", "filletx"):
            # selective fillet:  filletx <name> <radius> [selector]
            name, r, *rest = a
            sel = rest[0] if rest else "all"
            return engine.fillet_edges(name, _f(r), sel)
        if cmd == "chamferx":
            name, d, *rest = a
            sel = rest[0] if rest else "all"
            return engine.chamfer_edges(name, _f(d), sel)
        if cmd == "cbore":
            # cbore <name> <d> <cbore_d> <cbore_depth> [depth] [face]
            name, d, cd, cdep, *rest = a
            depth = _f(rest[0]) if len(rest) > 0 else None
            face = rest[1] if len(rest) > 1 else "+Z"
            return engine.counterbore(name, _f(d), _f(cd), _f(cdep),
                                      depth, face)
        if cmd == "csink":
            # csink <name> <d> <csk_d> [angle] [depth] [face]
            name, d, csd, *rest = a
            ang = _f(rest[0]) if len(rest) > 0 else 82.0
            depth = _f(rest[1]) if len(rest) > 1 else None
            face = rest[2] if len(rest) > 2 else "+Z"
            return engine.countersink(name, _f(d), _f(csd), ang, depth, face)
        if cmd == "tap":
            name, spec, depth, *rest = a
            face = rest[0] if rest else "+Z"
            return engine.tapped_hole(name, spec, _f(depth), face)
        if cmd == "boss":
            # boss <base> <sketch> <depth> [face]
            base, sk, depth, *rest = a
            face = rest[0] if rest else "+Z"
            return engine.boss_extrude(base, sk, _f(depth), face)
        if cmd == "pocket":
            base, sk, depth, *rest = a
            face = rest[0] if rest else "+Z"
            return engine.cut_extrude(base, sk, _f(depth), face)
        if cmd == "cpat":
            prefix, src, sk, count = a
            return engine.pattern_along_curve(prefix, src, sk, int(count))
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
