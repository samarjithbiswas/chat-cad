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
_lock = threading.Lock()

DEFAULT_MODEL = "claude-opus-4-7"


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

    with _lock:
        if api_key:
            try:
                from anthropic import Anthropic
                client = Anthropic(api_key=api_key)
                reply, ops = run_claude(client, model, chat_history, engine, message)
            except Exception as e:
                reply = f"Claude call failed: {e}\nFalling back to parser.\n\n" + run_parser(engine, message)
                ops = []
        else:
            reply = run_parser(engine, message)
            ops = []

        _refresh_stl()
        return jsonify({"reply": reply, "ops": ops, "parts": engine.list_parts()})


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
        _refresh_stl()
    return jsonify({"ok": True})


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
