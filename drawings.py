"""Engineering-drawing-style PDF exporter for chat_cad parts.

For a given named part, produces an A4-landscape PDF with four views
(front / top / right / iso), a title block, and overall bounding-box
dimensions. The intent is to give a machinist or 3D-print operator a
quick at-a-glance summary -- it is NOT a fully dimensioned production
drawing (no GD&T, no tolerances, no view-relation symbols).
"""
from __future__ import annotations

import os
import struct
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np


def _read_stl_tris(path: str) -> np.ndarray:
    """Mirror of agents._read_stl_triangles; kept here for module independence."""
    with open(path, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        tris = np.zeros((n, 3, 3), dtype=np.float32)
        for i in range(n):
            d = f.read(50)
            v = struct.unpack("<12fH", d)
            tris[i, 0] = v[3:6]; tris[i, 1] = v[6:9]; tris[i, 2] = v[9:12]
        return tris


def _project_outline(tris: np.ndarray, axis: int) -> tuple[np.ndarray, np.ndarray]:
    """Return the (X, Y) 2D points of the silhouette projection looking
    down `axis` (0=X, 1=Y, 2=Z).
    """
    other = [i for i in range(3) if i != axis]
    pts = tris.reshape(-1, 3)
    return pts[:, other[0]], pts[:, other[1]]


def _draw_view_2d(ax, tris: np.ndarray, axis: int, title: str) -> None:
    """Outline-style 2D projection of triangles onto a plane perpendicular
    to `axis`. Renders each triangle as a filled grey polygon so overlaps
    fuse into a silhouette.
    """
    other = [i for i in range(3) if i != axis]
    polys = []
    for tri in tris:
        polys.append([(tri[k, other[0]], tri[k, other[1]]) for k in range(3)])
    from matplotlib.collections import PolyCollection
    coll = PolyCollection(polys, facecolor="#3a4250", edgecolor="#1a1d23",
                          linewidth=0.05, alpha=1.0)
    ax.add_collection(coll)
    pts = tris.reshape(-1, 3)
    pad = 0.05 * max(pts[:, other[0]].ptp(), pts[:, other[1]].ptp(), 1.0)
    ax.set_xlim(pts[:, other[0]].min() - pad, pts[:, other[0]].max() + pad)
    ax.set_ylim(pts[:, other[1]].min() - pad, pts[:, other[1]].max() + pad)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=9, pad=2)
    ax.grid(True, linewidth=0.3, alpha=0.4)
    ax.tick_params(labelsize=6)


def _draw_iso(ax, tris: np.ndarray, title: str) -> None:
    """Isometric 3D view in matplotlib's mplot3d."""
    coll = Poly3DCollection(tris, facecolor="#5870ce", edgecolor="#0a0d12",
                            linewidth=0.2, alpha=0.95)
    ax.add_collection3d(coll)
    pts = tris.reshape(-1, 3)
    mn, mx = pts.min(0), pts.max(0)
    ctr = (mn + mx) / 2
    rng = (mx - mn).max() * 0.6 or 10.0
    ax.set_xlim(ctr[0] - rng, ctr[0] + rng)
    ax.set_ylim(ctr[1] - rng, ctr[1] + rng)
    ax.set_zlim(ctr[2] - rng, ctr[2] + rng)
    ax.view_init(elev=25, azim=-55)
    ax.set_proj_type("ortho")
    ax.set_title(title, fontsize=9, pad=2)
    ax.tick_params(labelsize=6)


def export_drawing(engine, part_name: str, output_path: str,
                   project_title: str = "Chat CAD",
                   drawn_by: str = "") -> str:
    """Generate a 4-view PDF for a single named part."""
    if part_name not in engine.parts:
        raise KeyError(f"no part '{part_name}'")
    stl_path = engine.export_part_stl(part_name)
    tris = _read_stl_tris(stl_path)
    if len(tris) == 0:
        raise RuntimeError(f"part '{part_name}' has no geometry to draw")

    pts = tris.reshape(-1, 3)
    bb = (pts.min(0), pts.max(0))
    size = bb[1] - bb[0]
    vol = float(engine.parts[part_name].val().Volume())

    mat = "default"
    mass_g = vol * 1e-3  # default 1 g/cm^3
    if hasattr(engine, "materials"):
        try:
            mat = engine.materials.material_of(part_name)
            mass_g = engine.materials.mass(part_name)
        except Exception:
            pass

    fig = plt.figure(figsize=(11.69, 8.27))  # A4 landscape
    fig.patch.set_facecolor("white")

    # 2x2 grid for views, plus a thin title-block strip across the bottom
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.18],
                          hspace=0.30, wspace=0.20,
                          left=0.05, right=0.97, top=0.94, bottom=0.04)

    # Top-left: front (look along -Y, i.e. project to XZ plane = axis 1)
    ax_front = fig.add_subplot(gs[0, 0])
    _draw_view_2d(ax_front, tris, axis=1, title="FRONT (XZ)")

    # Top-right: top (look along -Z, project to XY = axis 2)
    ax_top = fig.add_subplot(gs[0, 1])
    _draw_view_2d(ax_top, tris, axis=2, title="TOP (XY)")

    # Bottom-left: right (look along -X, project to YZ = axis 0)
    ax_right = fig.add_subplot(gs[1, 0])
    _draw_view_2d(ax_right, tris, axis=0, title="RIGHT (YZ)")

    # Bottom-right: iso
    ax_iso = fig.add_subplot(gs[1, 1], projection="3d")
    _draw_iso(ax_iso, tris, title="ISO")

    # Title block strip
    tb = fig.add_subplot(gs[2, :])
    tb.axis("off")
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    title_text = (
        f"PROJECT: {project_title}      "
        f"PART: {part_name}      "
        f"MATERIAL: {mat}      "
        f"DRAWN: {drawn_by or 'chat_cad'}   {when}"
    )
    dims_text = (
        f"BBOX:  {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm     "
        f"VOLUME:  {vol:.2f} mm^3     "
        f"MASS:  {mass_g:.2f} g     "
        f"UNITS:  mm     SCALE:  fit to view"
    )
    tb.text(0.01, 0.7, title_text, fontsize=10, family="monospace",
            transform=tb.transAxes, verticalalignment="center")
    tb.text(0.01, 0.25, dims_text, fontsize=9, family="monospace",
            color="#444", transform=tb.transAxes, verticalalignment="center")
    # outer rectangle around the title block
    tb.add_patch(plt.Rectangle((0.005, 0.05), 0.99, 0.9,
                               fill=False, edgecolor="#333", linewidth=1.0,
                               transform=tb.transAxes))

    # outer page border
    fig.add_artist(plt.Rectangle((0.02, 0.02), 0.96, 0.96, fill=False,
                                 edgecolor="#222", linewidth=1.2,
                                 transform=fig.transFigure))

    with PdfPages(output_path) as pdf:
        pdf.savefig(fig)
    plt.close(fig)
    return output_path


def export_drawings_all(engine, output_path: str,
                        project_title: str = "Chat CAD") -> str:
    """Multi-page PDF, one page per part currently in the scene."""
    parts = list(engine.parts.keys())
    if not parts:
        raise RuntimeError("scene is empty, nothing to draw")
    with PdfPages(output_path) as pdf:
        for name in parts:
            try:
                stl_path = engine.export_part_stl(name)
                tris = _read_stl_tris(stl_path)
                if len(tris) == 0:
                    continue
                pts = tris.reshape(-1, 3)
                bb = (pts.min(0), pts.max(0))
                size = bb[1] - bb[0]
                vol = float(engine.parts[name].val().Volume())
                mat = "default"; mass_g = vol * 1e-3
                if hasattr(engine, "materials"):
                    try:
                        mat = engine.materials.material_of(name)
                        mass_g = engine.materials.mass(name)
                    except Exception:
                        pass
                fig = plt.figure(figsize=(11.69, 8.27))
                gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.18],
                                      hspace=0.30, wspace=0.20,
                                      left=0.05, right=0.97, top=0.94, bottom=0.04)
                _draw_view_2d(fig.add_subplot(gs[0, 0]), tris, 1, "FRONT (XZ)")
                _draw_view_2d(fig.add_subplot(gs[0, 1]), tris, 2, "TOP (XY)")
                _draw_view_2d(fig.add_subplot(gs[1, 0]), tris, 0, "RIGHT (YZ)")
                _draw_iso(fig.add_subplot(gs[1, 1], projection="3d"), tris, "ISO")
                tb = fig.add_subplot(gs[2, :]); tb.axis("off")
                when = datetime.now().strftime("%Y-%m-%d %H:%M")
                tb.text(0.01, 0.7,
                        f"PROJECT: {project_title}      PART: {name}      "
                        f"MATERIAL: {mat}      DRAWN: chat_cad   {when}",
                        fontsize=10, family="monospace",
                        transform=tb.transAxes, verticalalignment="center")
                tb.text(0.01, 0.25,
                        f"BBOX: {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm     "
                        f"VOLUME: {vol:.2f} mm^3     MASS: {mass_g:.2f} g     "
                        f"UNITS: mm",
                        fontsize=9, family="monospace", color="#444",
                        transform=tb.transAxes, verticalalignment="center")
                tb.add_patch(plt.Rectangle((0.005, 0.05), 0.99, 0.9,
                                           fill=False, edgecolor="#333",
                                           linewidth=1.0, transform=tb.transAxes))
                pdf.savefig(fig)
                plt.close(fig)
            except Exception as e:
                # skip parts that can't be rendered, keep going
                print(f"drawing skipped for {name}: {e}")
    return output_path
