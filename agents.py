"""Multi-agent design loop on top of the existing chat_cad modeler.

Three roles:
  1. Planner    decomposes a natural-language brief into modeling milestones.
  2. Modeler    runs CadQuery ops via the existing tool-use loop.
  3. Critic     renders the scene to a PNG, looks at it with Claude vision,
                says either 'done' or 'revise' with concrete feedback.

The orchestrator iterates Modeler -> Critic until the critic accepts or
max_iters is hit. Each iteration's feedback flows into the next modeler call.

This file deliberately reuses TOOLS / SYSTEM_PROMPT from llm.py for the modeler
role rather than duplicating them.
"""
from __future__ import annotations

import base64
import io
import json
import os
import struct
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Headless backend (no Tk / Qt). Must be set before importing pyplot.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from cad_engine import CadEngine
from llm import TOOLS, SYSTEM_PROMPT, run_claude


# ---------------- visual rendering ---------------- #
def _read_stl_triangles(path: str) -> np.ndarray:
    """Return an (N, 3, 3) array of triangle vertices.  Handles binary STL.
    For empty/ASCII files, returns an empty array.
    """
    with open(path, "rb") as f:
        head = f.read(80)
        if not head:
            return np.zeros((0, 3, 3))
        n_bytes = f.read(4)
        if len(n_bytes) < 4:
            return np.zeros((0, 3, 3))
        n_tri = struct.unpack("<I", n_bytes)[0]
        tris = np.zeros((n_tri, 3, 3), dtype=np.float32)
        for i in range(n_tri):
            data = f.read(50)
            if len(data) < 50:
                return tris[:i]
            v = struct.unpack("<12fH", data)
            tris[i, 0] = v[3:6]
            tris[i, 1] = v[6:9]
            tris[i, 2] = v[9:12]
        return tris


def render_scene_png(engine: CadEngine, output_path: str,
                     size: tuple[int, int] = (640, 480)) -> str:
    """Render the current parts in `engine` to a PNG suitable for Claude vision.
    Each part is rendered in its manifest colour with black edges, on a soft
    iso view that approximates the in-browser viewport.
    """
    manifest = engine.manifest()
    fig = plt.figure(figsize=(size[0] / 100, size[1] / 100), dpi=100)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_proj_type("ortho")
    ax.set_facecolor("#1a1f26")
    fig.patch.set_facecolor("#171b22")

    all_pts = []
    for p in manifest:
        name = p["name"]
        try:
            stl_path = engine.export_part_stl(name)
        except Exception:
            continue
        tris = _read_stl_triangles(stl_path)
        if len(tris) == 0:
            continue
        all_pts.append(tris.reshape(-1, 3))
        coll = Poly3DCollection(tris, facecolor=p["color"], edgecolor="#0a0d12",
                                linewidth=0.4, alpha=0.95)
        ax.add_collection3d(coll)

    if all_pts:
        pts = np.vstack(all_pts)
        mn, mx = pts.min(0), pts.max(0)
        ctr = (mn + mx) / 2
        rng = (mx - mn).max() * 0.6 or 10.0
        ax.set_xlim(ctr[0] - rng, ctr[0] + rng)
        ax.set_ylim(ctr[1] - rng, ctr[1] + rng)
        ax.set_zlim(ctr[2] - rng, ctr[2] + rng)
    else:
        ax.text(0.5, 0.5, 0.5, "(empty scene)", color="#8a8f99")

    ax.view_init(elev=25, azim=-55)  # match in-browser default-ish
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.fill = False
        axis.pane.set_edgecolor("#2a2f37")
    ax.tick_params(colors="#6a7080", labelsize=7)
    ax.set_xlabel("X", color="#6a7080"); ax.set_ylabel("Y", color="#6a7080")
    ax.set_zlabel("Z", color="#6a7080")

    fig.tight_layout(pad=0.5)
    fig.savefig(output_path, dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def _png_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


# ---------------- planner ---------------- #
PLANNER_SYSTEM = """You are the planning component of a multi-agent CAD design
system. The user gives a natural-language brief for a mechanical part.

Decompose the brief into 2-6 sequential MILESTONES. Each milestone should be
one coherent piece of geometry: a base body, a feature like a slot or boss,
a pattern, a fillet pass, etc. Order them so each builds on the previous.

For each milestone produce:
- name: short snake_case identifier
- intent: one sentence describing what should exist in the scene after this step
- success_criteria: one sentence on what a reviewer would look for to call it done

Respond as STRICT JSON only, no prose, no markdown. Schema:
{"plan":[{"name":"...","intent":"...","success_criteria":"..."},...]}"""


def plan_design(client, model: str, brief: str,
                knowledge_block: str = "") -> list[dict]:
    system = PLANNER_SYSTEM
    if knowledge_block:
        system = PLANNER_SYSTEM + "\n\n" + knowledge_block
    resp = client.messages.create(
        model=model, max_tokens=1024, system=system,
        messages=[{"role": "user", "content": f"Brief:\n{brief}"}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    # tolerate the model accidentally wrapping in ```json
    text = text.strip().lstrip("`").rstrip("`")
    if text.startswith("json"):
        text = text[4:].lstrip()
    try:
        return json.loads(text)["plan"]
    except Exception as e:
        raise RuntimeError(f"planner returned non-JSON: {e}\n---\n{text[:500]}")


# ---------------- visual critic ---------------- #
CRITIC_SYSTEM = """You are a senior mechanical engineer reviewing a CAD design
in progress. You will be shown a rendered image of the current scene plus the
original design brief and a description of what was just attempted.

Your job is to decide whether the current scene satisfies what was attempted
AND whether the overall brief is now complete. Be specific and terse. Do not
hallucinate features you cannot see in the image.

Respond as STRICT JSON only:
{
  "verdict": "done" | "revise" | "continue",
  "feedback": "one or two sentences",
  "specific_changes": ["concrete change 1", "concrete change 2"]
}

verdict meanings:
- "done"     : the brief is fully satisfied; the design is finished.
- "continue" : the last step looks OK; proceed to the next milestone.
- "revise"   : the last step is wrong or incomplete; redo it per specific_changes."""


# ---------------- DFM critic ---------------- #
DFM_SYSTEM = """You are a senior design-for-manufacturing engineer reviewing
parts in progress. You will be given numeric geometric measurements (bbox,
volume, surface area, estimated wall thickness, aspect ratio) of the parts
currently in the scene.

Decide whether the current scene has serious manufacturing problems for
common processes (CNC, 3D print FDM, sheet metal, casting). Be specific and
quantitative. Do NOT speculate beyond what the numbers tell you.

Respond as STRICT JSON only:
{
  "verdict": "pass" | "warn" | "fail",
  "feedback": "one or two sentences",
  "issues": ["concrete issue 1 with the part name and number", "..."]
}

pass : looks manufacturable; nothing to fix.
warn : minor concerns; design can ship but flag these.
fail : a part as designed is unmanufacturable (wall too thin, sliver geometry, etc.)."""


def _compute_dfm_findings(engine, names: list[str]) -> list[dict]:
    """Per-part geometric measurements relevant to manufacturability."""
    findings: list[dict] = []
    for name in names:
        if name not in engine.parts:
            continue
        try:
            shape = engine.parts[name].val()
            vol = float(shape.Volume())
            try:
                surf = float(shape.Area())
            except Exception:
                surf = 0.0
            bb = shape.BoundingBox()
            dims = sorted([bb.xlen, bb.ylen, bb.zlen])
            min_dim = dims[0]; max_dim = dims[2]
            aspect = (max_dim / min_dim) if min_dim > 1e-6 else float("inf")
            wall_est = (2.0 * vol / surf) if surf > 1e-6 else 0.0
            warnings = []
            if wall_est < 1.5:
                warnings.append(f"est. wall {wall_est:.2f} mm < 1.5 mm — fragile for most processes")
            if min_dim < 0.5:
                warnings.append(f"smallest bbox dim {min_dim:.2f} mm — likely sliver geometry")
            if aspect > 30:
                warnings.append(f"aspect ratio {aspect:.1f}:1 — long and thin, may warp on FDM")
            findings.append({
                "part": name,
                "volume_mm3": round(vol, 2),
                "surface_mm2": round(surf, 2),
                "bbox_mm": [round(bb.xlen, 2), round(bb.ylen, 2), round(bb.zlen, 2)],
                "min_dim_mm": round(min_dim, 2),
                "max_dim_mm": round(max_dim, 2),
                "aspect_ratio": round(aspect, 1),
                "est_wall_thickness_mm": round(wall_est, 2),
                "warnings": warnings,
            })
        except Exception as e:
            findings.append({"part": name, "error": str(e)})
    return findings


def critique_dfm(client, model: str, brief: str, engine) -> dict:
    """Geometric findings + LLM interpretation = DFM verdict."""
    names = list(engine.parts.keys())
    if not names:
        return {"verdict": "pass", "feedback": "(empty scene)", "issues": []}
    findings = _compute_dfm_findings(engine, names)
    user_msg = (f"BRIEF:\n{brief}\n\nGEOMETRIC FINDINGS:\n"
                f"{json.dumps(findings, indent=2)}\n\n"
                "Assess manufacturability.")
    resp = client.messages.create(
        model=model, max_tokens=600, system=DFM_SYSTEM,
        messages=[{"role": "user", "content": user_msg}])
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    text = text.strip().lstrip("`").rstrip("`")
    if text.startswith("json"):
        text = text[4:].lstrip()
    try:
        out = json.loads(text)
        out["findings"] = findings
        return out
    except Exception:
        return {"verdict": "warn", "feedback": text[:200],
                "issues": [], "findings": findings}


# ---------------- Standards critic (RAG-driven) ---------------- #
STANDARDS_SYSTEM = """You are an organizational-standards critic. You will be
shown (1) the brief, (2) excerpts from the user's knowledge base describing
their personal/team standards (e.g. 'always use M4 bolts', 'wall thickness
>=3 mm for FDM'), and (3) what's currently in the scene.

Decide whether the design respects the user's standards. Ignore items in the
notes that have nothing to do with this brief. Be specific.

Respond as STRICT JSON only:
{
  "verdict": "pass" | "warn" | "fail",
  "feedback": "one or two sentences",
  "issues": ["concrete violation 1, citing the relevant note", "..."]
}"""


def critique_standards(client, model: str, brief: str, engine) -> dict:
    """RAG over knowledge base + LLM compliance judgment."""
    if not hasattr(engine, "knowledge"):
        return {"verdict": "pass", "feedback": "(no knowledge base)",
                "issues": []}
    notes = engine.knowledge.search(brief, k=10) if engine.knowledge.notes else []
    if not notes:
        return {"verdict": "pass",
                "feedback": "(no relevant notes in knowledge base)",
                "issues": []}
    notes_text = "\n".join(f"- {n['text']}" for n in notes)
    scene = engine.list_parts()
    user_msg = (f"BRIEF:\n{brief}\n\n"
                f"USER'S NOTES / STANDARDS:\n{notes_text}\n\n"
                f"CURRENT SCENE:\n{scene}\n\n"
                "Assess standards compliance.")
    resp = client.messages.create(
        model=model, max_tokens=600, system=STANDARDS_SYSTEM,
        messages=[{"role": "user", "content": user_msg}])
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    text = text.strip().lstrip("`").rstrip("`")
    if text.startswith("json"):
        text = text[4:].lstrip()
    try:
        return json.loads(text)
    except Exception:
        return {"verdict": "warn", "feedback": text[:200], "issues": []}


def critique_visual(client, model: str, brief: str, milestone: dict,
                    modeler_summary: str, image_path: str) -> dict:
    img_b64 = _png_to_b64(image_path)
    msg = {
        "role": "user",
        "content": [
            {"type": "image", "source": {
                "type": "base64", "media_type": "image/png", "data": img_b64}},
            {"type": "text", "text":
                f"BRIEF:\n{brief}\n\n"
                f"MILESTONE just attempted:\n"
                f"  name: {milestone['name']}\n"
                f"  intent: {milestone['intent']}\n"
                f"  success_criteria: {milestone['success_criteria']}\n\n"
                f"MODELER summary:\n{modeler_summary}\n\n"
                "Assess the rendered scene."},
        ],
    }
    resp = client.messages.create(
        model=model, max_tokens=512, system=CRITIC_SYSTEM, messages=[msg])
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    text = text.strip().lstrip("`").rstrip("`")
    if text.startswith("json"):
        text = text[4:].lstrip()
    try:
        return json.loads(text)
    except Exception as e:
        return {"verdict": "continue",
                "feedback": f"(critic returned non-JSON: {e})",
                "specific_changes": []}


# ---------------- orchestrator ---------------- #
@dataclass
class AgentEvent:
    role: str    # "planner" | "modeler" | "critic" | "system"
    kind: str    # "log" | "milestone" | "tool" | "image" | "verdict"
    text: str
    data: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"role": self.role, "kind": self.kind,
                "text": self.text, "data": self.data}


def design_loop(client, model: str, engine: CadEngine, brief: str,
                max_revises_per_milestone: int = 2) -> list[dict]:
    """Run the full planner -> [modeler -> critic]* loop. Returns the event log
    as plain dicts so it can be JSON-serialised directly to the browser.
    """
    log: list[AgentEvent] = []
    log.append(AgentEvent("system", "log", f"brief: {brief}"))

    # 0. retrieve from knowledge base (TF-IDF over user notes + past designs)
    knowledge_block = ""
    if hasattr(engine, "knowledge"):
        try:
            knowledge_block = engine.knowledge.context_block(brief, k=5)
            if knowledge_block:
                log.append(AgentEvent("system", "log",
                                      "retrieved knowledge notes: "
                                      + str(knowledge_block.count("\n- "))))
        except Exception as e:
            log.append(AgentEvent("system", "log", f"knowledge lookup failed: {e}"))

    # 1. plan
    try:
        plan = plan_design(client, model, brief, knowledge_block)
    except Exception as e:
        log.append(AgentEvent("planner", "log", f"plan failed: {e}"))
        return [e.to_json() for e in log]
    log.append(AgentEvent("planner", "milestone",
                          f"plan has {len(plan)} milestone(s)",
                          data={"plan": plan}))

    modeler_history: list[dict] = []
    last_render = os.path.join(engine.output_dir, "agent_view.png")

    for m_idx, milestone in enumerate(plan):
        log.append(AgentEvent("planner", "milestone",
                              f"milestone {m_idx + 1}/{len(plan)}: {milestone['name']}",
                              data=milestone))

        for revise_idx in range(max_revises_per_milestone + 1):
            # 2. modeler
            instr = (f"Implement this milestone using the CAD tools:\n"
                     f"  name: {milestone['name']}\n"
                     f"  intent: {milestone['intent']}\n"
                     f"  success_criteria: {milestone['success_criteria']}\n")
            if revise_idx > 0:
                last_critic = log[-1].data
                instr += (f"\nPREVIOUS ATTEMPT WAS REJECTED. Critic feedback:\n"
                          f"  {last_critic.get('feedback', '')}\n"
                          f"  specific changes:\n" +
                          "\n".join(f"    - {c}" for c in last_critic.get(
                              "specific_changes", [])))
            try:
                reply, ops = run_claude(client, model, modeler_history,
                                        engine, instr)
            except Exception as e:
                log.append(AgentEvent("modeler", "log",
                                      f"modeler call failed: {e}"))
                return [e.to_json() for e in log]
            log.append(AgentEvent("modeler", "tool",
                                  reply or "(no reply)",
                                  data={"ops": ops}))

            # 3. render
            try:
                render_scene_png(engine, last_render)
            except Exception as e:
                log.append(AgentEvent("system", "log",
                                      f"render failed: {e}"))
                break

            # 4. critic
            try:
                critique = critique_visual(client, model, brief, milestone,
                                           reply or "", last_render)
            except Exception as e:
                log.append(AgentEvent("critic", "log",
                                      f"critic call failed: {e}"))
                break
            log.append(AgentEvent("critic", "verdict",
                                  f"{critique.get('verdict','?')}: "
                                  f"{critique.get('feedback','')}",
                                  data=critique))

            verdict = critique.get("verdict", "continue")
            if verdict == "done":
                log.append(AgentEvent("system", "log",
                                      "visual critic marked design complete"))
                _run_final_critics(client, model, engine, brief, log)
                _autosave_design(engine, brief, log)
                return [e.to_json() for e in log]
            if verdict == "continue":
                break
            # verdict == "revise" -> loop again within this milestone

    log.append(AgentEvent("system", "log",
                          "all milestones complete (or revise cap hit)"))
    _run_final_critics(client, model, engine, brief, log)
    _autosave_design(engine, brief, log)
    return [e.to_json() for e in log]


def _run_final_critics(client, model: str, engine: CadEngine, brief: str,
                       log: list[AgentEvent]) -> None:
    """Run DFM + standards critics on the finished scene and append findings
    to the log. These are advisory — they don't loop back to the modeler in v1.
    """
    # DFM
    try:
        dfm = critique_dfm(client, model, brief, engine)
        v = dfm.get("verdict", "?")
        fb = dfm.get("feedback", "")
        log.append(AgentEvent("critic", "verdict",
                              f"DFM {v}: {fb}", data=dfm))
    except Exception as e:
        log.append(AgentEvent("critic", "log", f"DFM critic failed: {e}"))
    # Standards (only if we have a non-empty knowledge base)
    try:
        std = critique_standards(client, model, brief, engine)
        v = std.get("verdict", "?")
        fb = std.get("feedback", "")
        log.append(AgentEvent("critic", "verdict",
                              f"Standards {v}: {fb}", data=std))
    except Exception as e:
        log.append(AgentEvent("critic", "log", f"Standards critic failed: {e}"))


def _autosave_design(engine: CadEngine, brief: str,
                     log: list[AgentEvent]) -> None:
    """Add a knowledge note summarising this design so future briefs can
    retrieve it.
    """
    if not hasattr(engine, "knowledge"):
        return
    try:
        parts_list = list(engine.parts.keys())
        if not parts_list:
            return
        # collect material info if known
        mats = {}
        for p in parts_list:
            try:
                mats[p] = engine.materials.material_of(p)
            except Exception:
                pass
        summary = (
            f"BRIEF: {brief}\n"
            f"PARTS: {', '.join(parts_list)}\n"
            f"MATERIALS: {mats if mats else '(none assigned)'}\n"
        )
        engine.knowledge.add(summary, tags=["design"], source="agent")
    except Exception:
        pass
