"""Ollama (local Llama / Qwen / etc.) backend for chat_cad.

Talks to a locally-running Ollama HTTP server at http://localhost:11434.
No API key, no internet, free. Trade-off: smaller models are worse at the
multi-step tool-use the design loop wants; this backend supports the single-
turn Chat mode only. For multi-agent Design Agent runs (visual critic needs
to see PNG renders), use Anthropic or Gemini.

The user must have Ollama installed: https://ollama.com/download
And have pulled a tool-calling model:
    ollama pull llama3.2
    ollama pull qwen2.5
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from llm import TOOLS, SYSTEM_PROMPT
from cad_engine import dispatch


OLLAMA_URL = "http://localhost:11434"


# ---------------- tool-format conversion ---------------- #
def _to_ollama_tools() -> list[dict]:
    """Anthropic tool schema -> OpenAI/Ollama tool schema."""
    out = []
    for t in TOOLS:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        })
    return out


# ---------------- transport ---------------- #
def _post(path: str, payload: dict, timeout: int = 180) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}{path}", data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check_ollama() -> tuple[bool, str]:
    """Quick health check; returns (ok, message)."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=2) as r:
            data = json.loads(r.read().decode("utf-8"))
            models = [m["name"] for m in data.get("models", [])]
            if not models:
                return False, ("Ollama is running but no models are installed. "
                               "Run `ollama pull llama3.2` first.")
            return True, f"{len(models)} model(s): {', '.join(models[:6])}"
    except Exception as e:
        return False, ("Ollama isn't reachable at " + OLLAMA_URL +
                       ". Install from https://ollama.com and start `ollama serve`. "
                       f"Underlying error: {e}")


# ---------------- main entry point ---------------- #
def run_ollama(model: str, history: list[dict], engine,
               user_message: str) -> tuple[str, list[str]]:
    """One user turn. Same return shape as llm.run_claude."""
    history.append({"role": "user", "content": user_message})
    op_log: list[str] = []
    tools = _to_ollama_tools()

    # Small local models (Llama 3.2 3B in particular) love to "explain how
    # they would use" a function instead of actually calling it. Tighten the
    # system prompt aggressively for these models.
    OLLAMA_SYSTEM = (
        "You are a CAD command interpreter. The user describes a part in plain "
        "English. You MUST respond by CALLING one of the provided functions. "
        "DO NOT write Python code. DO NOT explain. DO NOT provide tutorials. "
        "Pick the single most-appropriate function and call it with concrete "
        "numeric arguments. If the user wants a 'cylinder', call `cylinder` "
        "with a name and dimensions. If they want a gear, call `lib_gear`. "
        "If they want an airfoil, call `lib_naca`. ALWAYS choose a function "
        "and ALWAYS provide numeric arguments. Make up reasonable defaults "
        "when the user is vague (e.g. 30 mm cylinder, 24-tooth gear).\n\n"
        + SYSTEM_PROMPT
    )
    for _ in range(25):  # tool-loop cap
        messages = [{"role": "system", "content": OLLAMA_SYSTEM}] + history
        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {"temperature": 0.0, "top_p": 0.1},
        }
        try:
            resp = _post("/api/chat", payload, timeout=300)
        except urllib.error.HTTPError as e:
            # Ollama IS reachable but returned an error — usually 404 because
            # the model isn't pulled yet. Probe /api/tags to confirm and list
            # what's actually available.
            ok, msg = check_ollama()
            if e.code == 404:
                return (f"Ollama is running, but model '{model}' isn't pulled yet.\n"
                        f"Open PowerShell and run:\n"
                        f"    ollama pull {model}\n\n"
                        f"Status: {msg}", op_log)
            return (f"Ollama returned HTTP {e.code}: {e.reason}\n"
                    f"Status: {msg}", op_log)
        except urllib.error.URLError as e:
            return (f"Ollama not reachable at {OLLAMA_URL}. "
                    f"Install Ollama (https://ollama.com) and start it.\n"
                    f"Underlying error: {e}", op_log)
        except Exception as e:
            return (f"Ollama call failed: {e}", op_log)

        msg = resp.get("message") or {}
        content = msg.get("content", "") or ""
        tool_calls = msg.get("tool_calls") or []

        history.append({
            "role": "assistant",
            "content": content,
            **({"tool_calls": tool_calls} if tool_calls else {}),
        })

        if not tool_calls:
            return (content.strip() or "(done)", op_log)

        # execute each tool call and append a tool message
        for tc in tool_calls:
            fn = (tc.get("function") or {})
            name = fn.get("name")
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            args = dict(args or {})
            if not name:
                op_log.append(f"(malformed tool_call: {tc})")
                continue
            try:
                result = dispatch(engine, name, args)
                op_log.append(f"{name}({args}) -> {result}")
                history.append({
                    "role": "tool", "content": str(result),
                    "tool_name": name,
                })
            except Exception as e:
                op_log.append(f"{name}({args}) FAILED: {e}")
                history.append({
                    "role": "tool", "content": f"ERROR: {e}",
                    "tool_name": name,
                })

    return ("hit tool-use round cap; stopping.", op_log)
