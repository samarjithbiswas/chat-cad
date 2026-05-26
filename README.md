---
title: Chat CAD
emoji: 🧱
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Chat CAD

A chat-driven CAD tool with a real B-rep kernel (CadQuery / OpenCascade),
a parametric 2D sketcher with constraint solver, and a placement-based
assembly system. Talk to it in plain English (via Claude) or drive it with
a built-in command parser; export STEP / STL of what you built.

```
chat_cad/
  app.py              Flask server + browser launcher
  cad_engine.py       3D parts: primitives, booleans, fillets, ...
  sketch_engine.py    2D sketches + scipy-based constraint solver + SVG view
  assembly_engine.py  Named-component assemblies built on cq.Assembly
  llm.py              Claude tool-use loop  +  regex parser fallback
  templates/
    index.html        Chat UI + Three.js viewer + sketch / assembly tabs
  output/             Generated STL / STEP files
  requirements.txt
```

## Install

```powershell
# option A: conda (recommended on Windows)
conda create -n chatcad python=3.11 -y
conda activate chatcad
conda install -c conda-forge cadquery -y
pip install flask anthropic numpy scipy

# option B: pip only (slower; cadquery wheel is large)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```powershell
python app.py
```

Opens http://127.0.0.1:5000 in your browser. Paste an Anthropic API key in
the settings panel (or set `ANTHROPIC_API_KEY` before launching) to enable
the Claude path; otherwise the parser handles requests.

## Three workflows

### 1. Direct 3D primitives (parser or chat)

```
box base 40 40 5
cyl post 5 30 0 0 15
union body base post
fillet body 1
export step knob.step
```

### 2. Parametric sketches → extrude / revolve

A sketch is a named container of points, lines, circles, and rectangles
with explicit constraints (horizontal, vertical, distance, parallel,
perpendicular, equal, radius, angle). After you add constraints, run
`sk solve <name>`; the solver minimises constraint residuals with
`scipy.optimize.least_squares`. Then extrude or revolve to make a part.

```
sk new profile XY
sk rect  profile bracket 0 0 40 20
sk circle profile hole 30 10 0    # placeholder radius
sk rad   profile hole 4           # constrain radius
sk solve profile
sk ext   profile bracket_3d 5
```

Open the **Sketches** tab to see an SVG preview with point names and the
constraint manifest. Closed wires are extrudable; open chains are skipped.

### 3. Assemblies with placements

Components reference a 3D part plus a (location, rotation). After `asm solve`
the combined compound appears in the 3D scene as `_asm_<name>` and can be
exported with `asm export <name>`.

```
box left  10 10 30
box right 10 10 30
asm new wall
asm add wall l left  0  0 0
asm add wall r right 30 0 0
asm solve wall
asm export wall wall.step
```

Mate constraints (`asm mate <Plane|Axis|Point|PointInPlane> <a_sel> <b_sel>`)
are **recorded but not solved** in v1 — solver-driven mating needs a robust
topological selector layer and is the next obvious upgrade.

## Available operations

### 3D parts (top-level)
Primitives: `box`, `cylinder`, `sphere`, `cone`, `torus`, `wedge`, `polygon`,
`text` (extruded 3D text).
Transforms: `translate`, `rotate`, `scale`, `mirror`.
Booleans: `union`, `cut`, `intersect`.
Features: `fillet`, `chamfer`, `shell`, `hole`.
Patterns: `lpat` (linear), `ppat` (polar) — stamp N copies of a part.
Bookkeeping: `delete`, `list`, `clear`, `undo`, `export step|stl`.

### 2D sketcher (`sk <sub>` or `sketch_*` tools)
Entities: `pt`, `line`, `circle`, `rect`, `fix`.
Constraints: `coinc`, `h`, `v`, `dist`, `distx`, `disty`, `par`, `perp`,
`eq`, `rad`, `ang`.
Lifecycle: `new`, `solve`, `ext`, `rev`, `info`, `list`, `del`.

### Assemblies (`asm <sub>` or `asm_*` tools)
Structure: `new`, `add`, `move`, `rot`, `rm`, `mate`, `solve`,
`info`, `list`, `del`, `export`.

Type `help` in the chat for the full parser cheat-sheet.

## Viewer

The 3D viewport is set up like a CAD viewport rather than a generic Three.js
demo:

- **Z is up**, matching CadQuery / SolidWorks conventions.
- Each part is rendered as its own mesh with a deterministic colour derived
  from its name, so unioned vs. distinct parts read clearly.
- Black **edge outlines** (dihedral angle > 25°) give the SolidWorks-style
  feature-edge look.
- **3-point studio lighting** (key + fill + rim) plus a hemisphere light for
  ambient sky/ground fill — Blender-ish viewport shading.
- **Soft ground shadow** under the bounding box, repositioned each reload.
- **Auto-fit camera** on first load; click *Fit view* to reframe later.

## What this is and isn't

This is a small build to give Claude a CAD body to act through. The kernel
under the hood is the same OpenCascade that drives FreeCAD / Onshape, so
the parts and assemblies you build are real B-reps you can hand to a slicer
or CAM package.

Honest limits versus SolidWorks:
- Sketcher has no on-canvas drag editing yet (sketches are edited by chat).
- Solver handles the common 80% but does not detect over-constrained
  systems gracefully — if it doesn't converge, remove a constraint.
- Assemblies position parts but do not yet solve mate equations
  (face-on-face, axis-coincident).
- No history tree edit, no drawings, no rendering / materials beyond Three.js.

The next obvious upgrades, in order, are: (1) on-canvas sketch dragging
that re-solves live, (2) a topological selector layer so mate constraints
can actually be solved, (3) a feature tree with edit-by-reference.
