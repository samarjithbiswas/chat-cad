# Chat CAD

**Chat-driven mechanical CAD with a real B-rep kernel and a multi-agent design loop.**
Describe a part in plain English or with terse typed commands; get an exportable
STEP / STL / engineering-drawing PDF in seconds. Free local LLM support.
Real FEA. Windows installer.

[Download installer (Windows)](https://github.com/Samarjithbiswas/chat-cad/releases/download/v0.1.0/ChatCAD_Setup.exe)
· [Pitch deck](./PITCH.md)
· [Architecture](#architecture)
· [Demo script](#demo-script-90-second-loop)

---

## In One Picture

```
Chat / natural language
       │
       ▼
┌───────────────────────────────────────────────────────────────┐
│  Planner ─► Modeler ─► Visual Critic ─► DFM Critic            │
│      (5-agent design loop with Claude vision / Gemini)         │
└───────────────────────────────────────────────────────────────┘
       │
       ▼
CadQuery / OpenCascade B-rep kernel
       │
       ▼
SolidWorks-style viewport: feature tree · gizmos · view cube
       · right-click menu · 19 PBR material presets · IBL
       │
       ▼
Export: STEP · STL · 4-view PDF · STEP for assemblies
Simulate: linear-elastic FEA · steady-state thermal (gmsh + scikit-fem)
```

---

## Why Chat CAD

- **Real B-rep, not mesh tris.** Hand the output to a CAM package or machinist.
- **5-agent design loop** — Planner / Modeler / Visual / DFM / Standards critics.
  Catches "wall too thin" before the user ships, not after.
- **Bring-your-own LLM.** Anthropic, Google Gemini, local Ollama (offline,
  free), or in-browser WebLLM (no install, no key, ~600 MB one-time download).
- **140+ chat-callable operations** spanning primitives, booleans, sketches
  with constraint solver, assemblies with mate solving, sheet metal,
  structural profiles (T-slot / I-beam / angle iron / C-channel), library
  fasteners (M-bolt + thread, nut, washer, bearing, hinge, pulley, gear,
  spring), aerospace mockups (turbine wheel, propeller, compressor stage,
  combustor, nozzle, NACA airfoil, honeycomb), and one-command complex
  assemblies (`turbojet`, `turbofan`, `bolt_stack`, `gear_train`, `engine`).
- **Real FEA on the same geometry** — most AI CAD tools stop at "looks like
  a part." Chat CAD will mesh and solve it (linear-elastic + thermal).
- **Engineering drawings to PDF** with 4-view layout + dimension arrows +
  title block + mass-properties summary.
- **Knowledge layer** — your saved notes ("we always use M4 bolts", "wall
  thickness ≥ 3 mm for FDM") get retrieved into every agent prompt via
  TF-IDF RAG.

---

## Quick Start

### Windows (recommended)

1. Download [`ChatCAD_Setup.exe`](https://github.com/Samarjithbiswas/chat-cad/releases/download/v0.1.0/ChatCAD_Setup.exe)
2. Double-click. Wait ~5 min for the one-time Miniforge + CadQuery install (~1.5 GB).
3. Launch via the Desktop shortcut. Your browser opens to `http://127.0.0.1:5000/`.

### Manual / dev

```powershell
conda create -n chatcad python=3.11 -y
conda activate chatcad
conda install -c conda-forge cadquery -y
pip install -r requirements.txt
python app.py
```

### Pick an LLM (optional)

| Backend | How |
|---|---|
| **Anthropic Claude** (best quality) | Paste `sk-ant-...` key in settings → ~0.5¢/part |
| **Google Gemini** (free tier) | Paste `AIza...` key from aistudio.google.com |
| **Local Ollama** (offline, free) | Install Ollama + `ollama pull qwen2.5` |
| **In-browser WebLLM** (no install, no key) | Pick a `browser:` model from the dropdown |
| **None — typed-command mode** | Works out of the box, no LLM required |

---

## Demo Script (90-second loop)

```text
1. Launch → clean professional viewport
2. Type:   bolt_stack demo M8 15 60
              → plate + 2 washers + threaded M8 bolt + hex nut appears
3. Right-click the bolt → Mirror about XY → second bolt
4. Render tab → Polished steel → Apply to all
5. File tab → Drawing PDF → 4-view engineering drawing downloads
6. Simulate tab → click the plate → Run FEA → real stress in 8 seconds
7. Chat:   "turbojet engine, 200 mm fan, 600 mm length" (Design Agent mode)
              → 19-sub-part realistic axial-flow turbojet builds itself,
                 visual critic checks each milestone
8. Render tab → Brushed aluminum + Outdoor sky environment → catalog shot
```

What competitors take **4–8 hours** for, this loop does in **~2 minutes**.

---

## Architecture

```
app.py
├── Flask server (chat, scene, drawing, FEA endpoints)
├── cad_engine.py — CadEngine wrapper around CadQuery
│   ├── sketch_engine.py    — 2D sketcher + scipy constraint solver
│   ├── assembly_engine.py  — cq.Assembly with mate solver
│   ├── library.py          — fasteners, gears, springs, bearings, aerospace
│   ├── materials.py        — density table + mass-properties
│   ├── profiles.py         — T-slot, I-beam, angle, tube, channel
│   ├── sheet_metal.py      — sheet, L-bend, U-bend, box, flange
│   ├── step_io.py          — STEP import
│   ├── drawings.py         — 4-view PDF with dimensions
│   ├── knowledge.py        — TF-IDF RAG over user notes
│   └── assemblies_recipes.py — turbojet, turbofan, bolt_stack, gear_train
├── llm.py        — Claude tool schema + tool-use loop, regex parser fallback
├── llm_gemini.py — Google Gemini backend
├── llm_ollama.py — local Ollama backend with parser-fallback
├── agents.py     — Design Agent: planner + modeler + visual/DFM/standards critics
├── fea.py + fea_worker.py — gmsh + scikit-fem subprocess wrapper
└── templates/index.html — Three.js viewport (view cube, gizmos, right-click,
                           PBR + IBL, 19 material presets, ribbon toolbar)
```

---

## Pricing (intent)

| Tier | Price | What you get |
|---|---|---|
| **Open source** | $0 | Full feature set, runs locally, MIT license |
| **Pro** (planned) | $49/month | Hosted instance, priority support, custom knowledge base |
| **Team** (planned) | $499/month | Shared knowledge base, multi-user sessions, audit logs |
| **Enterprise** (planned) | Custom | On-premise deployment, SAML/SSO, fine-tuned model for your domain |

---

## What This Is And Isn't

**Is:** A credible chat-driven CAD tool with real B-rep output, real FEA,
real engineering drawings. Comparable in spirit to KittyCAD's text-to-CAD
demo but with broader operation coverage and a multi-agent design loop.

**Isn't:** A SolidWorks / Onshape / Fusion 360 replacement. Those tools
have 25–35 years of customer-validated edge cases baked into their
kernels. Chat CAD doesn't have that history. Chat CAD's wedge is
**speed of getting to a serviceable part from a chat prompt**, not
authoring 50,000-part assemblies with full tolerance stack-ups.

**Will be:** Whatever the first 10 paying customers tell us it needs to be.

---

## License

MIT. See [LICENSE](LICENSE).

---

## Built by [Samarjith Biswas](https://samarjithbiswas.com)

Mechanical engineering · acoustic metamaterials · agentic AI for design.
