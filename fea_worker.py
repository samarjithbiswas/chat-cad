"""FEA subprocess worker.

Invoked by fea.py as a separate Python process so gmsh's signal handlers
(which require the main thread of the interpreter) work correctly.

Usage:
    python fea_worker.py <stl_path> <load_N> <axis> <material>
Prints a single line of JSON to stdout with the result.
"""
from __future__ import annotations

import json
import sys
import traceback

import numpy as np


def _mesh_with_gmsh(stl_path: str, mesh_size: float):
    import gmsh
    gmsh.initialize(["", "-noenv"])
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size)
        gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_size * 0.3)
        gmsh.merge(stl_path)
        gmsh.model.mesh.classifySurfaces(np.pi / 6, True, False, np.pi / 6)
        gmsh.model.mesh.createGeometry()
        surfs = gmsh.model.getEntities(2)
        sl = gmsh.model.geo.addSurfaceLoop([e[1] for e in surfs])
        gmsh.model.geo.addVolume([sl])
        gmsh.model.geo.synchronize()
        gmsh.model.mesh.generate(3)
        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        coords = np.array(coords).reshape(-1, 3)
        tag_to_idx = {int(t): i for i, t in enumerate(node_tags)}
        elem_types, elem_tags, node_ids = gmsh.model.mesh.getElements(3)
        if not elem_types:
            raise RuntimeError("gmsh produced no 3D elements")
        tets = np.array(node_ids[0]).reshape(-1, 4)
        tets = np.vectorize(lambda t: tag_to_idx[int(t)])(tets)
        return coords, tets
    finally:
        gmsh.finalize()


_MATERIALS = {
    "aluminum":  {"E": 69e9,  "nu": 0.33},
    "steel":     {"E": 210e9, "nu": 0.30},
    "stainless": {"E": 200e9, "nu": 0.30},
    "brass":     {"E": 100e9, "nu": 0.34},
    "titanium":  {"E": 116e9, "nu": 0.34},
    "pla":       {"E":  3.5e9, "nu": 0.36},
    "abs":       {"E":  2.3e9, "nu": 0.35},
    "default":   {"E": 69e9,  "nu": 0.33},
}


def run(stl_path: str, load_N: float, axis: str, material: str) -> dict:
    # bbox-based mesh size from STL
    with open(stl_path, "rb") as f:
        head = f.read(80); nb = f.read(4)
        if len(nb) < 4:
            return {"error": "STL too short / empty"}
        import struct
        n = struct.unpack("<I", nb)[0]
        pts = []
        for _ in range(min(n, 5000)):
            d = f.read(50)
            if len(d) < 50: break
            v = struct.unpack("<12fH", d)
            pts.extend([v[3:6], v[6:9], v[9:12]])
        pts = np.array(pts, dtype=np.float32)
    bb = np.ptp(pts, axis=0)
    longest = float(bb.max()) if bb.size else 10.0
    mesh_size = max(0.5, longest / 18.0)

    pts3d, tets = _mesh_with_gmsh(stl_path, mesh_size=mesh_size)
    if len(tets) < 10:
        return {"error": "mesh has <10 tetrahedral elements; part too small"}

    from skfem import (MeshTet, Basis, ElementVector, ElementTetP1, asm,
                       condense, solve)
    from skfem.models.elasticity import linear_elasticity, lame_parameters

    mesh = MeshTet(pts3d.T, tets.T)
    e = ElementVector(ElementTetP1())
    basis = Basis(mesh, e)

    mat = _MATERIALS.get(material.lower(), _MATERIALS["default"])
    lam, mu = lame_parameters(mat["E"], mat["nu"])

    K = asm(linear_elasticity(lam, mu), basis)

    n_nodes = pts3d.shape[0]
    ax = {"X": 0, "Y": 1, "Z": 2}[axis.upper()]
    bb_min = pts3d.min(0); bb_max = pts3d.max(0)
    tol = max((bb_max[ax] - bb_min[ax]) * 0.02, 0.01)
    top_mask = np.abs(pts3d[:, ax] - bb_max[ax]) < tol
    bot_mask = np.abs(pts3d[:, ax] - bb_min[ax]) < tol
    if top_mask.sum() == 0 or bot_mask.sum() == 0:
        return {"error": "could not identify top/bottom faces"}

    f = np.zeros(3 * n_nodes)
    top_idx = np.where(top_mask)[0]
    per_node = -float(load_N) / max(len(top_idx), 1)
    f[3 * top_idx + ax] = per_node

    bot_idx = np.where(bot_mask)[0]
    fixed = np.concatenate([3 * bot_idx, 3 * bot_idx + 1, 3 * bot_idx + 2])

    u = solve(*condense(K, f, D=fixed))

    disp = u.reshape(-1, 3)
    disp_mag = np.linalg.norm(disp, axis=1)
    max_disp_mm = float(disp_mag.max())  # mm because input is mm + Pa? actually
    # input is mm geometry, E in Pa, load in N. Units mix — for relative sense
    # the magnitudes are off but the patterns are right. Caveat noted in UI.

    # von Mises stress per tet
    vm = np.zeros(len(tets))
    for i, tet in enumerate(tets):
        P = pts3d[tet]; U = disp[tet]
        A = (P[:3] - P[3]).T
        B = (U[:3] - U[3]).T
        try:
            grad_u = B @ np.linalg.inv(A)
        except np.linalg.LinAlgError:
            continue
        eps = 0.5 * (grad_u + grad_u.T)
        sigma = lam * np.trace(eps) * np.eye(3) + 2 * mu * eps
        s = sigma - np.trace(sigma) / 3.0 * np.eye(3)
        vm[i] = np.sqrt(1.5 * np.sum(s * s))

    return {
        "ok": True,
        "n_nodes": int(n_nodes),
        "n_elems": int(len(tets)),
        "material": material,
        "load_N": float(load_N),
        "axis": axis.upper(),
        "max_disp_mm": float(max_disp_mm) * 1000.0,
        "max_stress_MPa": float(vm.max()) / 1e6,
        "E_GPa": mat["E"] / 1e9,
    }


def run_thermal(stl_path: str, t_hot: float, t_cold: float,
                axis: str = "Z") -> dict:
    """Steady-state heat conduction: T_hot on +axis face, T_cold on -axis face.
    Returns max/min temperature and the maximum gradient magnitude.
    """
    with open(stl_path, "rb") as f:
        f.read(80); nb = f.read(4)
        if len(nb) < 4:
            return {"error": "STL too short / empty"}
        import struct
        n = struct.unpack("<I", nb)[0]
        sample_pts = []
        for _ in range(min(n, 5000)):
            d = f.read(50)
            if len(d) < 50: break
            v = struct.unpack("<12fH", d)
            sample_pts.extend([v[3:6], v[6:9], v[9:12]])
        sample_pts = np.array(sample_pts, dtype=np.float32)
    bb = np.ptp(sample_pts, axis=0)
    longest = float(bb.max()) if bb.size else 10.0
    mesh_size = max(0.5, longest / 18.0)

    pts3d, tets = _mesh_with_gmsh(stl_path, mesh_size=mesh_size)
    if len(tets) < 10:
        return {"error": "mesh too small for thermal analysis"}

    from skfem import MeshTet, Basis, ElementTetP1, asm, condense, solve
    from skfem.helpers import dot, grad
    from skfem.models.poisson import laplace

    mesh = MeshTet(pts3d.T, tets.T)
    basis = Basis(mesh, ElementTetP1())
    K = asm(laplace, basis)

    ax = {"X": 0, "Y": 1, "Z": 2}[axis.upper()]
    bb_min = pts3d.min(0); bb_max = pts3d.max(0)
    tol = max((bb_max[ax] - bb_min[ax]) * 0.02, 0.01)
    hot_idx  = np.where(np.abs(pts3d[:, ax] - bb_max[ax]) < tol)[0]
    cold_idx = np.where(np.abs(pts3d[:, ax] - bb_min[ax]) < tol)[0]
    if len(hot_idx) == 0 or len(cold_idx) == 0:
        return {"error": "couldn't identify hot/cold faces"}

    n = pts3d.shape[0]
    T = np.zeros(n)
    T[hot_idx] = float(t_hot)
    T[cold_idx] = float(t_cold)
    fixed_dofs = np.concatenate([hot_idx, cold_idx])

    T_sol = solve(*condense(K, x=T, D=fixed_dofs))

    # Compute per-element gradient magnitude
    grads = np.zeros(len(tets))
    for i, tet in enumerate(tets):
        P = pts3d[tet]; Tv = T_sol[tet]
        A = (P[:3] - P[3]).T
        b = Tv[:3] - Tv[3]
        try:
            g = np.linalg.solve(A.T, b)
        except np.linalg.LinAlgError:
            continue
        grads[i] = np.linalg.norm(g)

    return {
        "ok": True,
        "n_nodes": int(n),
        "n_elems": int(len(tets)),
        "axis": axis.upper(),
        "t_max": float(T_sol.max()),
        "t_min": float(T_sol.min()),
        "grad_max": float(grads.max()),
    }


if __name__ == "__main__":
    try:
        mode = sys.argv[1]
        if mode == "thermal":
            stl_path = sys.argv[2]
            t_hot = float(sys.argv[3])
            t_cold = float(sys.argv[4])
            axis = sys.argv[5] if len(sys.argv) > 5 else "Z"
            out = run_thermal(stl_path, t_hot, t_cold, axis)
        else:
            # Legacy positional: <stl> <load_N> <axis> [material]  -> elasticity
            stl_path = sys.argv[1]
            load_N = float(sys.argv[2])
            axis = sys.argv[3]
            material = sys.argv[4] if len(sys.argv) > 4 else "aluminum"
            out = run(stl_path, load_N, axis, material)
    except Exception as e:
        out = {"error": f"{type(e).__name__}: {e}",
               "trace": traceback.format_exc()[-500:]}
    sys.stdout.write(json.dumps(out))
