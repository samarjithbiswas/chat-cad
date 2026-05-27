"""Image / sketch upload -> 3D model.

Two paths:

1. `trace_silhouette`     — pure image processing. Reads a clean drawing,
                            finds the outline, extrudes it to a 3D part.
                            No LLM required. Works on scanned drawings,
                            photo of a line sketch, screenshots, etc.

2. `interpret_with_vision`— uses Claude vision (or Gemini vision). Reads
                            the image, emits chat_cad parser commands,
                            runs them. Works for hand-drawn sketches with
                            multiple parts, dimension notes, etc.
"""
from __future__ import annotations

import base64
import io
import os
from typing import Any

import cadquery as cq
import numpy as np
from PIL import Image


# ---------------- Path A: silhouette trace ---------------- #
def trace_silhouette(image_bytes: bytes, target_width_mm: float = 50.0,
                     extrude_mm: float = 5.0,
                     epsilon_ratio: float = 0.004) -> tuple[cq.Workplane, dict]:
    """Find the largest dark contour in the image, simplify, scale, extrude.

    Returns (workplane, info_dict). Raises if no contour found.
    """
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError(
            "opencv-python isn't installed. Run "
            "'pip install opencv-python-headless' in the chatcad env."
        ) from e

    # decode bytes -> numpy array
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError("could not decode image — supported: PNG/JPG/BMP")
    h_px, w_px = img.shape

    # auto-invert if the drawing is dark-on-light (most common); we want the
    # part to be foreground (255) and background to be 0.
    if img.mean() > 127:
        img = 255 - img
    # Otsu threshold for robustness against scanning artifacts
    _, bw = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # close small holes
    kernel = np.ones((3, 3), np.uint8)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        raise RuntimeError("no contour found — the image looks empty after thresholding")
    # pick the contour with the largest enclosed area
    contour = max(contours, key=cv2.contourArea)
    area_px = float(cv2.contourArea(contour))
    if area_px < 25:
        raise RuntimeError(f"largest contour too small ({area_px:.0f} px²)")

    # simplify (Ramer–Douglas–Peucker) to control polyline complexity
    peri = float(cv2.arcLength(contour, True))
    eps = max(peri * float(epsilon_ratio), 0.5)
    simp = cv2.approxPolyDP(contour, eps, True)
    pts_px = simp[:, 0, :]   # shape (N,2)

    # Scale: longest bbox side -> target_width_mm
    x_min, y_min = pts_px.min(0); x_max, y_max = pts_px.max(0)
    bbox_w = float(x_max - x_min); bbox_h = float(y_max - y_min)
    scale = float(target_width_mm) / max(bbox_w, bbox_h)
    # flip Y (image y is downward, CAD y is upward) and centre at origin
    cx = (x_min + x_max) / 2; cy = (y_min + y_max) / 2
    pts_mm = []
    for px, py in pts_px:
        pts_mm.append((float(px - cx) * scale, float(-(py - cy)) * scale))
    if len(pts_mm) < 3:
        raise RuntimeError("simplified contour has <3 points")

    # Build CadQuery sketch + extrude
    wp = (cq.Workplane("XY")
          .moveTo(*pts_mm[0])
          .polyline(pts_mm[1:])
          .close()
          .extrude(float(extrude_mm)))
    info = {
        "n_contour_points_raw": int(len(pts_px)),
        "n_polyline_vertices": int(len(pts_mm)),
        "bbox_mm": [round(bbox_w * scale, 2), round(bbox_h * scale, 2)],
        "extrude_mm": float(extrude_mm),
        "scale_factor": scale,
        "source_image_px": [int(w_px), int(h_px)],
    }
    return wp, info


# ---------------- Path B: vision LLM interprets ---------------- #
INTERPRET_SYSTEM = """You are a CAD command interpreter. The user uploads a
hand-drawn sketch, technical drawing, or annotated image. Your job is to
emit a list of chat_cad parser commands that, when executed in order, will
build the part(s) shown.

Output rules:
- Output ONLY parser commands, one per line. Nothing else. No explanations.
- Use ONLY commands from the chat_cad parser vocabulary (box, cyl, sphere,
  cone, torus, fillet, chamfer, hole, cbore, csink, sk new / rect / circle /
  line / solve / ext, bolt, nut, washer, gear, bearing, l_bracket,
  pillow_block, etc.).
- Use snake_case names for every part.
- Make up reasonable dimensions in millimetres if the drawing doesn't show
  them. Prefer 20-100 mm for handheld parts.
- If you see multiple parts, emit a command for each.
- If you see a feature like a hole, fillet, or chamfer, emit the appropriate
  command AFTER the base part it modifies.

Example output for a sketched L-bracket with 4 holes:
l_bracket bracket 50 40 4 30 5 2

Example for a hand-drawn box with a hole:
box base 40 30 8
hole base 4

Just the commands. Nothing else.
"""


def interpret_with_vision(image_bytes: bytes, api_key: str,
                          model: str = "claude-opus-4-7") -> list[str]:
    """Call Claude vision to interpret the image and return a list of
    parser command strings. The caller executes them.
    """
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    img_b64 = base64.b64encode(image_bytes).decode("ascii")
    # detect content type from header bytes
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        media = "image/png"
    elif image_bytes[:2] == b"\xff\xd8":
        media = "image/jpeg"
    elif image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        media = "image/gif"
    else:
        media = "image/png"
    resp = client.messages.create(
        model=model, max_tokens=600, system=INTERPRET_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                  "media_type": media, "data": img_b64}},
                {"type": "text", "text":
                  "Build the part(s) shown. Output only parser commands."},
            ],
        }])
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    commands = []
    for raw in text.splitlines():
        s = raw.strip().lstrip("> ").rstrip(";")
        if s.startswith("```") or not s:
            continue
        commands.append(s)
    return commands
