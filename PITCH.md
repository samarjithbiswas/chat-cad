# Chat CAD — Pitch Outline

> *"What if every mechanical engineer could describe a part in plain English,
> get a real B-rep model back in seconds, and have an AI critic check it for
> manufacturability before they ship it?"*

---

## Slide 1 — The Problem

- Designing a mechanical part still takes **2–8 hours** in SolidWorks for a
  trained engineer. Most of that time is the same patterns repeated:
  brackets, housings, mounting plates, fastener stacks.
- Junior engineers and product designers spend **40%+ of their week** on
  these "boilerplate" parts that aren't the interesting work.
- AI CAD tools exist (KittyCAD, CadChat, Spline AI) but they generate
  **mesh tris**, not real B-rep models you can hand to a CAM package or
  machinist.

## Slide 2 — The Insight

The bottleneck is **not the kernel**. OpenCascade has been open-source
for 25 years and powers FreeCAD, Onshape, and IronCAD. The bottleneck is
**the interface** between human intent and that kernel.

We bridge it with frontier LLMs treating CadQuery / OpenCascade operations
as **function-call tools**, plus a multi-agent loop (planner → modeler →
visual critic → DFM critic → standards critic) that catches mistakes
before they leave the chat.

## Slide 3 — What Chat CAD Does Today

**One chat command produces real, exportable, machinable geometry:**

- `bolt_stack jt M6 12 50` → plate + 2 washers + threaded M6 bolt + hex nut,
  all real B-rep solids, ready for STEP export.
- `turbojet jet 120 500` → 19 named sub-parts of a realistic axial-flow
  turbojet engine: spinner, nacelle, 8-stage compressor (rotor+stator),
  annular combustor, HP+LP turbine, afterburner, conv-div nozzle, shaft.
- `naca wing 2412 80 30` → NACA 4-digit airfoil section, extruded.
- A natural-language brief in Design Agent mode → multi-step composition
  with on-the-fly visual checking via Claude vision.

## Slide 4 — Technical Stack

| Layer | Technology | Why |
|---|---|---|
| **Kernel** | CadQuery on OpenCascade (OCP) | Same B-rep family as Onshape & FreeCAD |
| **Tool layer** | 140+ chat-callable operations | Primitives, booleans, sketches, assemblies, sheet metal, structural profiles, library parts, aerospace mockups |
| **Multi-agent** | 5 agents on Claude/Gemini | Planner · Modeler · Visual Critic · DFM Critic · Standards Critic |
| **Retrieval** | TF-IDF knowledge layer | Org standards (M-spec rules, wall-thickness mins, etc.) auto-loaded into every prompt |
| **Simulation** | gmsh + scikit-fem | Real linear-elastic FEA + steady-state thermal in a subprocess |
| **Viewport** | Three.js + PBR + IBL | 19 material presets, view cube, gizmos, section clip, exploded view |
| **LLM** | Anthropic / Google / Ollama / WebLLM | Cloud or fully local; no vendor lock-in |
| **Deployment** | Windows installer (.exe) or Docker | One-double-click install or one-line container |

## Slide 5 — What Differentiates Chat CAD

1. **Real B-rep output**, not mesh tris. STEP / STL / engineering-drawing PDF.
2. **Multi-agent loop with a DFM critic** — catches "wall too thin" and
   "sliver geometry" before the user ships.
3. **Bring-your-own LLM** — works with paid Claude/Gemini OR free Ollama
   (offline) OR free in-browser WebLLM. Customer never has to send their
   IP through a vendor they don't trust.
4. **Domain-specific recipes** — `turbojet`, `gear_train`, `bolt_stack`,
   `piston_engine` produce ready-to-export assemblies in one command.
   Generic AI CAD can't do this.
5. **Real FEA on real geometry** — most AI CAD tools stop at "looks
   like a part." Chat CAD will run a linear-elastic solve on it.

## Slide 6 — Use Cases

| Customer | Workflow | Value |
|---|---|---|
| **Junior mech engineer** | Boilerplate brackets, mounts, plates | 4 hr → 15 min |
| **3D-print hobbyist** | "Make me a wall-mount for X" | No CAD class needed |
| **Aerospace concept designer** | Turbojet / propeller / NACA mockups for proposals | 1 day → 1 hour |
| **Educator** | Live-build during a lecture from a chat | Single tool replaces 4 |

## Slide 7 — Why Now

- LLM tool use crossed the reliability threshold in mid-2024 (Claude 3.5
  Sonnet was the inflection point). Before then, a chat-driven CAD was
  a research demo. Today it can be a product.
- WebGPU shipped in browsers in 2023, making real-time PBR + IBL in the
  browser viable.
- OpenCascade's Python bindings stabilised. CadQuery 2.4 + cqkit are
  production-ready.
- 200K+ engineers laid off in the last 18 months. The market for "AI
  copilots that 10x mid-level engineering work" is wide open.

## Slide 8 — Where We Are vs Competitors

| | Chat CAD | KittyCAD | CadChat | SolidWorks |
|---|---|---|---|---|
| Real B-rep output | ✓ | ✓ | partial | ✓ |
| Chat / NL interface | ✓ | ✓ | ✓ | — |
| Multi-agent + DFM critic | ✓ | — | — | — |
| Real FEA on the same geometry | ✓ | — | — | $20k/seat add-on |
| Bring-your-own LLM (local Llama) | ✓ | — | — | — |
| Windows installer / offline mode | ✓ | — | — | ✓ |
| Aerospace recipes (turbojet etc.) | ✓ | — | — | — |
| Enterprise drawing standards | — | — | — | ✓ |
| 30 years of customer test data | — | — | — | ✓ |

## Slide 9 — Defensibility / Moat

Honest answer: **we don't have a deep moat yet. We have a head start.**
What we'd build into a moat over the first 12 months:

1. **Fine-tuned modeler agent** on a captured dataset of "brief → CadQuery
   ops" pairs. Right now we leverage frontier LLMs; over time we own the
   model.
2. **Vertical-specific recipe library** — partner with one industry
   (aerospace concept design, custom fixturing, or 3D-print on-demand)
   and own the recipe catalogue for that vertical.
3. **Customer-generated knowledge corpus** — the RAG layer is already
   built. Every customer's standards file becomes a personal moat that
   discourages switching.

## Slide 10 — Ask

- **Seed:** $500k–$1.5M
- **Use of funds:** 1 founding engineer hire (kernel) + 1 ML engineer
  (fine-tune the modeler) + 12 months runway + cloud + 3 pilot customers
- **Outcome by month 12:** 10 paying customers at $200–$500/mo, $20–60k
  ARR, validated wedge, ready for Seed-extension or Series A on real
  growth data
- **Outcome by year 3:** $1–3M ARR, $10–30M valuation. Acquired by an
  enterprise CAD vendor OR continues independently.

---

## Honest Caveats (Don't Hide These In Diligence)

1. **Open-source kernel** = no IP moat on the geometry layer. Anyone
   could build on the same foundation. Our moat is the agents, RAG,
   recipe library, and brand.
2. **Frontier-LLM dependency** for the best results = compute cost per
   user is non-trivial. The Ollama/WebLLM fallback mitigates but doesn't
   eliminate this.
3. **Not aerospace-certified.** Will not be hospital/aerospace/automotive
   for safety-critical parts until 5+ years of test data and a real
   QA process.
4. **Single-developer codebase** = bus factor of 1 until the first hire.

These caveats *belong* in the deck. They build trust with sophisticated
buyers and stop dumb objections during diligence.

---

## Demo Script (3-minute)

```
1.  Launch the .exe → browser opens to a clean white viewport
2.  Type: bolt_stack demo M8 15 60
       → 5 parts appear: plate + 2 washers + threaded M8 bolt + nut
3.  Right-click the bolt → "Mirror about XY" → second bolt
4.  Switch to RENDER ribbon → "Polished steel" → Apply to all
5.  Click Drawing PDF → 4-view engineering drawing downloads
6.  Switch to SIMULATE ribbon → Click the plate → Run FEA
       → real stress numbers in 8 seconds
7.  Type in chat: "turbojet engine, 200 mm fan, 600 mm length"
       (in Design Agent mode with Claude)
       → 19 sub-parts appear, agent picks tools, visual critic checks
8.  Switch to Materials ribbon → Apply "Brushed aluminum" + "Sky" env
       → engine catalog shot
9.  Show: this entire flow took 90 seconds. SolidWorks equivalent: 4–8 hours.
```

This is the demo that closes the meeting. It is **already possible** in
the software you have right now. Practice it, record it, send it.
