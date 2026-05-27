"""Inverse design loop for acoustic metamaterials.

Given a target bandgap window (f_lo_Hz, f_hi_Hz), search the parameter space
of each unit-cell family for the geometry whose predicted bandgap best
matches the target. Returns the best candidate + a confidence score.

The bandgap evaluator is `phononic.estimate_bandgap_window` — a coarse
analytical placeholder until the real PhononIQ surrogate is wired in
(see INTEGRATION_PHONONIQ.md).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable

from phononic import (
    estimate_bandgap_window,
    square_hole_cell, hex_hole_cell, cross_cell,
    pillar_cell, core_inclusion_cell,
)


@dataclass
class Candidate:
    family: str       # 'square_hole' | 'hex_hole' | 'cross' | 'pillar' | 'core'
    a: float          # lattice constant (mm)
    t: float          # plate thickness (mm)
    param: float      # family-specific (hole_size, arm_L, pillar_h, core_d)
    pred_lo_Hz: float
    pred_hi_Hz: float
    score: float      # 0..1, higher = better match to target
    miss_pct: float   # average percent error from target band edges


def _score_match(pred_lo: float, pred_hi: float,
                 target_lo: float, target_hi: float) -> tuple[float, float]:
    """Score how well a predicted bandgap matches a target.

    Returns (score, miss_pct). Score is 1.0 for a perfect match, decreasing
    as the bands diverge. miss_pct is the average percentage error of the
    band edges relative to target.
    """
    if pred_hi <= pred_lo or target_hi <= target_lo:
        return 0.0, 100.0
    lo_err = abs(pred_lo - target_lo) / target_lo * 100
    hi_err = abs(pred_hi - target_hi) / target_hi * 100
    miss_pct = (lo_err + hi_err) / 2
    # exponential decay: ~10% off = 0.6 score, ~50% off = 0.1
    score = math.exp(-miss_pct / 25.0)
    return score, miss_pct


def _candidate(family: str, a: float, t: float, param: float,
               target_lo: float, target_hi: float) -> Candidate:
    pred_lo, pred_hi = estimate_bandgap_window(family, a, t, param)
    score, miss = _score_match(pred_lo, pred_hi, target_lo, target_hi)
    return Candidate(family, a, t, param, pred_lo, pred_hi, score, miss)


def _coordinate_descent(family: str,
                        target_lo: float, target_hi: float,
                        a0: float, t0: float, p0: float,
                        max_iter: int = 30,
                        verbose_log: list | None = None) -> Candidate:
    """Greedy 1-D parameter sweeps until no axis improves the score.
    Cheap but reliable on smooth landscapes; the bandgap estimator is.
    """
    a, t, p = a0, t0, p0
    best = _candidate(family, a, t, p, target_lo, target_hi)
    if verbose_log is not None:
        verbose_log.append(
            f"  start [{family}]  a={a:.2f} t={t:.2f} p={p:.2f}  "
            f"-> {best.pred_lo_Hz/1000:.1f}-{best.pred_hi_Hz/1000:.1f} kHz "
            f"(miss {best.miss_pct:.1f}%)")
    for it in range(max_iter):
        improved = False
        for axis in ("a", "t", "p"):
            base = {"a": a, "t": t, "p": p}[axis]
            for factor in (0.85, 1.15):
                trial = base * factor
                if axis == "a": cand = _candidate(family, trial, t, p, target_lo, target_hi)
                if axis == "t": cand = _candidate(family, a, trial, p, target_lo, target_hi)
                if axis == "p": cand = _candidate(family, a, t, trial, target_lo, target_hi)
                # Reject if param violates geometry (param < a, t reasonable)
                if cand.param >= cand.a * 0.95 or cand.t <= 0.2 or cand.a <= 1.0:
                    continue
                if cand.score > best.score + 1e-4:
                    best = cand
                    a, t, p = cand.a, cand.t, cand.param
                    improved = True
        if not improved:
            break
    if verbose_log is not None:
        verbose_log.append(
            f"  converged [{family}]  a={best.a:.2f} t={best.t:.2f} "
            f"p={best.param:.2f}  -> {best.pred_lo_Hz/1000:.1f}-"
            f"{best.pred_hi_Hz/1000:.1f} kHz  score={best.score:.3f}")
    return best


def design_acoustic_metamaterial(target_lo_Hz: float, target_hi_Hz: float,
                                 verbose: bool = True) -> dict:
    """Inverse-design entrypoint. Returns the best candidate across all
    unit-cell families plus a log of the optimisation.
    """
    if target_hi_Hz <= target_lo_Hz:
        return {"error": "target_hi_Hz must be greater than target_lo_Hz"}
    target_center = (target_lo_Hz + target_hi_Hz) / 2
    # plate-wave speed approximation for initial guess
    c = 5570.0  # BOROFLOAT-33 longitudinal speed
    a0 = c / (2 * target_center * 1e-3) * 1000  # mm
    a0 = max(2.0, min(a0, 60.0))
    t0 = a0 * 0.18
    p0 = a0 * 0.45

    log: list[str] = []
    log.append(f"target: {target_lo_Hz/1000:.2f}-{target_hi_Hz/1000:.2f} kHz "
               f"(center {target_center/1000:.2f} kHz)")
    log.append(f"initial guess: a={a0:.2f} mm, t={t0:.2f} mm")

    candidates: list[Candidate] = []
    t0_clock = time.time()
    for fam in ("square_hole", "hex_hole", "cross", "pillar", "core"):
        log.append(f"\nsearching family: {fam}")
        # pillar uses pillar_h as the resonant param; very different scale
        p_init = (a0 * 0.7 if fam == "pillar" else a0 * 0.45)
        c_best = _coordinate_descent(fam, target_lo_Hz, target_hi_Hz,
                                     a0, t0, p_init, verbose_log=log)
        candidates.append(c_best)

    best = max(candidates, key=lambda c: c.score)
    duration_ms = (time.time() - t0_clock) * 1000

    return {
        "ok": True,
        "target_lo_Hz": float(target_lo_Hz),
        "target_hi_Hz": float(target_hi_Hz),
        "best": {
            "family": best.family,
            "a_mm": best.a, "t_mm": best.t, "param_mm": best.param,
            "predicted_lo_Hz": best.pred_lo_Hz,
            "predicted_hi_Hz": best.pred_hi_Hz,
            "match_score": best.score,
            "miss_percent": best.miss_pct,
        },
        "all_candidates": [
            {"family": c.family, "a_mm": c.a, "t_mm": c.t, "param_mm": c.param,
             "score": c.score, "miss_percent": c.miss_pct,
             "pred_lo_Hz": c.pred_lo_Hz, "pred_hi_Hz": c.pred_hi_Hz}
            for c in candidates
        ],
        "duration_ms": duration_ms,
        "log": log,
        "note": ("Bandgap predictions use a textbook analytical estimator "
                 "as a placeholder. Wire PhononIQ's trained surrogate in "
                 "phononic.estimate_bandgap_window for production accuracy. "
                 "See INTEGRATION_PHONONIQ.md."),
    }


def build_geometry_from_candidate(engine, name: str, c: dict,
                                   nx: int = 6, ny: int = 6) -> str:
    """Materialise an inverse-design result as a CAD unit cell + lattice."""
    fam = c["family"]
    a, t, p = c["a_mm"], c["t_mm"], c["param_mm"]
    pe = engine.phononic
    unit_name = f"{name}_unit"
    if fam == "square_hole":
        pe.square_hole(unit_name, a, t, p)
    elif fam == "hex_hole":
        pe.hex_hole(unit_name, a, t, p)
    elif fam == "cross":
        pe.cross(unit_name, a, t, p, p * 0.4)
    elif fam == "pillar":
        pe.pillar(unit_name, a, t, p * 0.6, p)
    elif fam == "core":
        pe.core_inclusion(unit_name, a, t, p)
    else:
        raise ValueError(f"unknown family '{fam}'")
    pe.lattice(name, unit_name, a, int(nx), int(ny))
    return name
