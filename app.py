"""Local Flask server that hosts the chat-CAD app.

Run:  python app.py
Then visit http://127.0.0.1:5000

The Anthropic API key can be supplied via the ANTHROPIC_API_KEY env var or
typed into the UI's settings panel. Without a key the regex parser is used.
"""
from __future__ import annotations

import os
import threading
import webbrowser

from flask import Flask, jsonify, request, send_file, send_from_directory

from cad_engine import CadEngine
from llm import run_claude, run_parser

HERE = os.path.dirname(os.path.abspath(__file__))


def _is_writable(d: str) -> bool:
    # os.access(W_OK) is unreliable on Windows (ignores ACLs). Do a real probe.
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".chatcad_write_probe.tmp")
        with open(probe, "w") as f:
            f.write("")
        os.remove(probe)
        return True
    except OSError:
        return False


_default_output = os.path.join(HERE, "output")
if not _is_writable(_default_output):
    # Installed location (e.g. C:\Program Files\ChatCAD) — route outputs to user appdata.
    _user_base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    _default_output = os.path.join(_user_base, "ChatCAD", "output")
OUTPUT = os.environ.get("CHATCAD_OUTPUT", _default_output)

app = Flask(__name__, template_folder="templates", static_folder="static")
engine = CadEngine(OUTPUT)
chat_history: list[dict] = []  # Claude conversation history
gemini_history: list[dict] = []  # Gemini conversation history (separate format)
ollama_history: list[dict] = []  # Ollama conversation history
_lock = threading.Lock()

DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


def _detect_backend(api_key: str, model: str = "") -> str:
    """Return 'anthropic', 'gemini', 'ollama', or 'none' based on the model
    name (ollama models are prefixed 'ollama:') and the API key prefix.
    """
    if model and model.startswith("ollama:"):
        return "ollama"
    if not api_key:
        return "none"
    if api_key.startswith("sk-ant-"):
        return "anthropic"
    if api_key.startswith("AIza"):
        return "gemini"
    return "anthropic"  # default fallback for unknown formats


def _refresh_stl() -> None:
    engine.export_stl("scene.stl")


@app.route("/")
def index():
    return send_from_directory(app.template_folder, "index.html")


@app.route("/scene.stl")
def scene_stl():
    path = os.path.join(OUTPUT, "scene.stl")
    if not os.path.exists(path):
        _refresh_stl()
    return send_file(path, mimetype="model/stl")


@app.route("/scene/manifest")
def scene_manifest():
    with _lock:
        return jsonify({"parts": engine.manifest()})


@app.route("/part/<name>.stl")
def part_stl(name: str):
    with _lock:
        try:
            path = engine.export_part_stl(name)
        except KeyError:
            return ("no such part", 404)
    return send_file(path, mimetype="model/stl")


@app.route("/part/<name>/volume")
def part_volume(name: str):
    with _lock:
        if name not in engine.parts:
            return jsonify({"error": f"no part named '{name}'"}), 404
        try:
            shape = engine.parts[name].val()
            vol = float(shape.Volume())
            bb = shape.BoundingBox()
            bbox = [bb.xmin, bb.ymin, bb.zmin, bb.xmax, bb.ymax, bb.zmax]
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"name": name, "volume_mm3": vol, "bbox": bbox})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    message = (data.get("message") or "").strip()
    api_key = (data.get("api_key") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    model = (data.get("model") or DEFAULT_MODEL).strip()

    if not message:
        return jsonify({"reply": "(empty message)", "ops": [], "parts": engine.list_parts()})

    force_parser = bool(data.get("force_parser"))
    backend = "parser" if force_parser else _detect_backend(api_key, model)
    with _lock:
        if backend == "parser":
            reply = run_parser(engine, message)
            ops = []
            _refresh_stl()
            return jsonify({"reply": reply, "ops": ops,
                            "parts": engine.list_parts(), "backend": "parser"})
        if backend == "ollama":
            try:
                from llm_ollama import run_ollama
                ollama_model = model[len("ollama:"):]
                reply, ops = run_ollama(ollama_model, ollama_history, engine, message)
            except Exception as e:
                reply = f"Ollama call failed: {e}\nFalling back to parser.\n\n" + run_parser(engine, message)
                ops = []
        elif backend == "anthropic":
            try:
                from anthropic import Anthropic
                client = Anthropic(api_key=api_key)
                reply, ops = run_claude(client, model, chat_history, engine, message)
            except Exception as e:
                reply = f"Claude call failed: {e}\nFalling back to parser.\n\n" + run_parser(engine, message)
                ops = []
        elif backend == "gemini":
            try:
                from llm_gemini import run_gemini
                gmodel = model if model.startswith("gemini") else DEFAULT_GEMINI_MODEL
                reply, ops = run_gemini(api_key, gmodel, gemini_history, engine, message)
            except Exception as e:
                reply = f"Gemini call failed: {e}\nFalling back to parser.\n\n" + run_parser(engine, message)
                ops = []
        else:
            reply = run_parser(engine, message)
            ops = []

        _refresh_stl()
        return jsonify({"reply": reply, "ops": ops, "parts": engine.list_parts(),
                        "backend": backend})


@app.route("/sketches")
def list_sketches():
    with _lock:
        names = list(engine.sketches.sketches.keys())
        info = {n: engine.sketches.info(n) for n in names}
    return jsonify({"names": names, "info": info})


@app.route("/sketch/<name>.svg")
def sketch_svg(name: str):
    with _lock:
        if name not in engine.sketches.sketches:
            return ("sketch not found", 404)
        svg = engine.sketches.svg(name)
    return (svg, 200, {"Content-Type": "image/svg+xml"})


@app.route("/assemblies")
def list_assemblies():
    with _lock:
        names = list(engine.assemblies.assemblies.keys())
        info = {n: engine.assemblies.info(n) for n in names}
    return jsonify({"names": names, "info": info})


@app.route("/parts")
def list_parts():
    with _lock:
        return jsonify({"text": engine.list_parts()})


@app.route("/import/step", methods=["POST"])
def import_step_endpoint():
    """Upload a STEP file and add it to the scene as a named part."""
    name = (request.form.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"error": "no file uploaded"}), 400
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in f.filename)
    tmp_path = os.path.join(OUTPUT, "uploads")
    os.makedirs(tmp_path, exist_ok=True)
    saved = os.path.join(tmp_path, safe)
    f.save(saved)
    with _lock:
        try:
            msg = engine.step_io.step_import(name, saved)
            _refresh_stl()
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "reply": msg, "parts": engine.list_parts()})


@app.route("/drawing/<name>.pdf")
def drawing_pdf(name: str):
    """Download an A4 4-view engineering drawing PDF for one part."""
    from drawings import export_drawing
    with _lock:
        if name not in engine.parts:
            return jsonify({"error": f"no part '{name}'"}), 404
        try:
            path = os.path.join(OUTPUT, f"drawing_{name}.pdf")
            export_drawing(engine, name, path)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return send_file(path, as_attachment=True,
                     download_name=f"{name}.pdf")


@app.route("/knowledge/list")
def knowledge_list():
    with _lock:
        return jsonify({"notes": engine.knowledge.list_notes()})


@app.route("/knowledge/add", methods=["POST"])
def knowledge_add():
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    tags = data.get("tags") or []
    if not text:
        return jsonify({"error": "text is required"}), 400
    with _lock:
        nid = engine.knowledge.add(text, tags=tags, source="manual")
    return jsonify({"ok": True, "id": nid})


@app.route("/knowledge/remove/<note_id>", methods=["POST"])
def knowledge_remove(note_id: str):
    with _lock:
        ok = engine.knowledge.remove(note_id)
    return jsonify({"ok": ok})


@app.route("/knowledge/search")
def knowledge_search():
    q = (request.args.get("q") or "").strip()
    with _lock:
        hits = engine.knowledge.search(q, k=10)
    return jsonify({"hits": hits})


@app.route("/drawings.pdf")
def drawings_all_pdf():
    """Multi-page drawing PDF: one page per part in the scene."""
    from drawings import export_drawings_all
    with _lock:
        if not engine.parts:
            return jsonify({"error": "scene is empty"}), 400
        path = os.path.join(OUTPUT, "drawings.pdf")
        try:
            export_drawings_all(engine, path)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return send_file(path, as_attachment=True, download_name="drawings.pdf")


@app.route("/agent/design", methods=["POST"])
def agent_design():
    """Run the multi-agent design loop (planner -> modeler -> visual critic).
    Requires an Anthropic API key (visual critic needs Claude vision).
    """
    data = request.get_json(force=True)
    brief = (data.get("brief") or "").strip()
    api_key = (data.get("api_key") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    model = (data.get("model") or DEFAULT_MODEL).strip()
    max_revises = int(data.get("max_revises", 2))

    if not brief:
        return jsonify({"error": "brief is required"}), 400
    if not api_key:
        return jsonify({"error": "API key required for the design agent "
                                  "(visual critic needs Claude vision)"}), 400

    with _lock:
        try:
            from anthropic import Anthropic
            from agents import design_loop
            client = Anthropic(api_key=api_key)
            events = design_loop(client, model, engine, brief,
                                 max_revises_per_milestone=max_revises)
            _refresh_stl()
            return jsonify({"events": events,
                            "parts": engine.list_parts()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route("/reset", methods=["POST"])
def reset():
    with _lock:
        engine.clear()
        chat_history.clear()
        gemini_history.clear()
        ollama_history.clear()
        _refresh_stl()
    return jsonify({"ok": True})


@app.route("/tool/run", methods=["POST"])
def tool_run():
    """Run a single named operation. Used by the in-browser WebLLM backend
    so the browser-side LLM can call our CadQuery tools without going through
    the full /chat loop (which lives on the server).
    """
    data = request.get_json(force=True)
    op = (data.get("op") or "").strip()
    args = data.get("args") or {}
    if not op:
        return jsonify({"error": "op is required"}), 400
    with _lock:
        try:
            from cad_engine import dispatch
            result = dispatch(engine, op, dict(args))
            _refresh_stl()
            return jsonify({"ok": True, "result": str(result),
                            "parts": engine.list_parts()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/tools/list")
def tools_list():
    """Return the full Anthropic-style TOOLS array so the in-browser LLM can
    register them as function declarations.
    """
    from llm import TOOLS
    return jsonify({"tools": TOOLS})


@app.route("/fea/run", methods=["POST"])
def fea_run():
    """Run a basic linear-elastic cantilever FEA on the named part using
    gmsh + scikit-fem. Returns max stress and displacement.
    """
    data = request.get_json(force=True)
    part = (data.get("part") or "").strip()
    load_N = float(data.get("load_N", 100.0))
    axis = (data.get("axis") or "Z").strip().upper()
    if not part:
        return jsonify({"error": "part is required"}), 400
    with _lock:
        if part not in engine.parts:
            return jsonify({"error": f"no part '{part}'"}), 404
        material = engine.materials.material_of(part) if hasattr(engine, "materials") else "default"
        try:
            stl_path = engine.export_part_stl(part)
        except Exception as e:
            return jsonify({"error": f"could not export STL for FEA: {e}"}), 500
    # Run FEA outside the lock — solver can take a few seconds
    try:
        from fea import run_fea
        result = run_fea(stl_path, load_N=load_N, axis=axis, material=material)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/fea/modal", methods=["POST"])
def fea_modal():
    """Modal analysis: returns the first N natural frequencies of the part
    (rigid-body modes filtered out). Free-free boundary conditions.
    """
    data = request.get_json(force=True)
    part = (data.get("part") or "").strip()
    n_modes = int(data.get("n_modes", 6))
    if not part:
        return jsonify({"error": "part is required"}), 400
    with _lock:
        if part not in engine.parts:
            return jsonify({"error": f"no part '{part}'"}), 404
        material = engine.materials.material_of(part) if hasattr(engine, "materials") else "default"
        try:
            stl_path = engine.export_part_stl(part)
        except Exception as e:
            return jsonify({"error": f"could not export STL: {e}"}), 500
    try:
        from fea import run_modal
        return jsonify(run_modal(stl_path, material, n_modes))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/verify", methods=["POST"])
def verify():
    """Verification agent: render the current scene + ask Claude vision
    whether it matches the user's intent. Works in any mode (Chat, Design
    Agent, parser-only). Requires an Anthropic key (vision model).
    """
    data = request.get_json(force=True)
    intent = (data.get("intent") or "").strip()
    api_key = (data.get("api_key") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    model = (data.get("model") or DEFAULT_MODEL).strip()
    if not intent:
        return jsonify({"error": "intent (what you asked for) is required"}), 400
    if not api_key or not api_key.startswith("sk-ant-"):
        return jsonify({"error": "verification agent needs an Anthropic key "
                                  "(vision model). Paste sk-ant-... in settings."}), 400
    with _lock:
        if not engine.parts:
            return jsonify({"error": "scene is empty — nothing to verify"}), 400
        parts_summary = engine.list_parts()
        try:
            from agents import render_scene_png, verify_intent
            from anthropic import Anthropic
            img_path = os.path.join(OUTPUT, "_verify.png")
            render_scene_png(engine, img_path, width=640, height=480)
            client = Anthropic(api_key=api_key)
            result = verify_intent(client, model, intent, img_path, parts_summary)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route("/cfd/run", methods=["POST"])
def cfd_run():
    """2D steady Stokes flow around the part's XY silhouette. Real PDE
    solve via Taylor-Hood elements (P2-velocity / P1-pressure). Returns
    max velocity + pressure drop. Stokes regime only (Re << 1).
    """
    data = request.get_json(force=True)
    part = (data.get("part") or "").strip()
    U = float(data.get("inlet_velocity", 1.0))
    mu = float(data.get("viscosity", 1.0e-3))
    axis = (data.get("axis") or "Z").strip().upper()
    if not part:
        return jsonify({"error": "part is required"}), 400
    with _lock:
        if part not in engine.parts:
            return jsonify({"error": f"no part '{part}'"}), 404
        try:
            stl_path = engine.export_part_stl(part)
        except Exception as e:
            return jsonify({"error": f"could not export STL: {e}"}), 500
    try:
        from fea import run_cfd_2d
        return jsonify(run_cfd_2d(stl_path, U, mu, axis))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/fea/thermal", methods=["POST"])
def fea_thermal():
    """Steady-state heat conduction on the named part. Hot face fixed at
    t_hot°C on the +axis side, cold face at t_cold°C on the -axis side.
    """
    data = request.get_json(force=True)
    part = (data.get("part") or "").strip()
    t_hot = float(data.get("t_hot", 100.0))
    t_cold = float(data.get("t_cold", 20.0))
    axis = (data.get("axis") or "Z").strip().upper()
    if not part:
        return jsonify({"error": "part is required"}), 400
    with _lock:
        if part not in engine.parts:
            return jsonify({"error": f"no part '{part}'"}), 404
        try:
            stl_path = engine.export_part_stl(part)
        except Exception as e:
            return jsonify({"error": f"could not export STL: {e}"}), 500
    try:
        from fea import run_thermal
        return jsonify(run_thermal(stl_path, t_hot=t_hot, t_cold=t_cold, axis=axis))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ollama/status")
def ollama_status():
    """Quick health check used by the UI to show Ollama availability."""
    from llm_ollama import check_ollama
    ok, msg = check_ollama()
    return jsonify({"ok": ok, "message": msg})


@app.route("/export/<fmt>")
def export(fmt: str):
    fmt = fmt.lower()
    if fmt not in ("step", "stl"):
        return jsonify({"error": f"unknown format {fmt}"}), 400
    with _lock:
        try:
            path = engine.export_step("scene.step") if fmt == "step" else engine.export_stl("scene.stl")
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


def _open_browser():
    webbrowser.open(f"http://127.0.0.1:{PORT}/")


if __name__ == "__main__":
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", "5000"))
    # only launch a browser tab when running locally
    if HOST in ("127.0.0.1", "localhost"):
        threading.Timer(1.0, _open_browser).start()
    app.run(host=HOST, port=PORT, debug=False)
