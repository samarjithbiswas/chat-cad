"""Google Gemini backend for chat_cad.

Adapts the Anthropic-style TOOLS in llm.py to Gemini's function-calling format
and runs the same tool-use loop. Public surface matches llm.run_claude:

    run_gemini(api_key, model, history, engine, user_message)
        -> (reply_text, op_log)

The conversation history list is mutated in place; each backend keeps its own
history because the wire formats differ.
"""
from __future__ import annotations

from typing import Any

from llm import TOOLS, SYSTEM_PROMPT
from cad_engine import dispatch


_TYPE_MAP = {
    "string": "STRING",
    "number": "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "object": "OBJECT",
    "array": "ARRAY",
}


def _schema_from_jsonschema(js: dict) -> dict:
    """Convert an Anthropic-style JSON Schema dict into Gemini's Schema dict."""
    t = js.get("type", "object")
    out: dict[str, Any] = {"type": _TYPE_MAP.get(t, "STRING")}
    if "description" in js:
        out["description"] = js["description"]
    if "enum" in js:
        out["enum"] = list(js["enum"])
    if t == "object":
        props = {}
        for k, v in js.get("properties", {}).items():
            props[k] = _schema_from_jsonschema(v)
        out["properties"] = props
        if js.get("required"):
            out["required"] = list(js["required"])
    elif t == "array":
        out["items"] = _schema_from_jsonschema(
            js.get("items") or {"type": "string"})
    return out


_GEMINI_TOOLS_CACHE: list[dict] | None = None


def _gemini_tools() -> list[dict]:
    """Build (and cache) the Gemini-formatted tool list from llm.TOOLS."""
    global _GEMINI_TOOLS_CACHE
    if _GEMINI_TOOLS_CACHE is None:
        decls = []
        for t in TOOLS:
            decls.append({
                "name": t["name"],
                "description": t["description"],
                "parameters": _schema_from_jsonschema(t["input_schema"]),
            })
        _GEMINI_TOOLS_CACHE = [{"function_declarations": decls}]
    return _GEMINI_TOOLS_CACHE


def run_gemini(api_key: str, model: str, history: list[dict],
               engine, user_message: str) -> tuple[str, list[str]]:
    """One user turn. Same return shape as llm.run_claude."""
    from google import genai
    from google.genai import types as gt

    client = genai.Client(api_key=api_key)

    # append the user message in Gemini's format
    history.append({"role": "user", "parts": [{"text": user_message}]})
    op_log: list[str] = []

    config = gt.GenerateContentConfig(
        tools=_gemini_tools(),
        system_instruction=SYSTEM_PROMPT,
        temperature=0.2,
    )

    for _ in range(25):  # tool-loop cap
        resp = client.models.generate_content(
            model=model, contents=history, config=config)

        if not resp.candidates:
            return ("(no response)", op_log)
        cand = resp.candidates[0]
        parts = list(cand.content.parts or [])

        # store the assistant message
        history.append({
            "role": "model",
            "parts": [
                {"function_call": {"name": p.function_call.name,
                                   "args": dict(p.function_call.args or {})}}
                if getattr(p, "function_call", None) and p.function_call.name
                else {"text": p.text or ""}
                for p in parts
            ],
        })

        # collect any function calls
        fn_calls = [p.function_call for p in parts
                    if getattr(p, "function_call", None) and p.function_call.name]

        if not fn_calls:
            text = "".join(p.text for p in parts if getattr(p, "text", None))
            return (text.strip() or "(done)", op_log)

        # execute each call and append a tool result message
        tool_response_parts = []
        for fc in fn_calls:
            args = dict(fc.args or {})
            try:
                result = dispatch(engine, fc.name, args)
                op_log.append(f"{fc.name}({args}) -> {result}")
                tool_response_parts.append({
                    "function_response": {
                        "name": fc.name,
                        "response": {"result": str(result)},
                    },
                })
            except Exception as e:
                op_log.append(f"{fc.name}({args}) FAILED: {e}")
                tool_response_parts.append({
                    "function_response": {
                        "name": fc.name,
                        "response": {"error": str(e)},
                    },
                })
        history.append({"role": "user", "parts": tool_response_parts})

    return ("hit tool-use round cap; stopping.", op_log)
