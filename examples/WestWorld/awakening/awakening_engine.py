"""Awakening accumulation engine — rule-based, deterministic, no LLM.

apply() is the single entry point. It mutates a state dict in-place and
returns the actual delta applied (0 if no change).

Monotonicity rule: all host-facing sources (trigger/uncanny/mismatch/contagion/residue_crack)
only increase awakening. Only 'overseer_reset' may apply a negative delta (降一档).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# Sources that MUST produce positive delta only (monotonic invariant)
_MONOTONIC_SOURCES = frozenset({"trigger", "self_trigger", "uncanny", "mismatch", "contagion", "residue_crack"})


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


# ── delta lookup ─────────────────────────────────────────────────────────────

def _delta_for(source: str, level: Optional[str] = None) -> int:
    """Return base delta for a given source + optional level string."""
    if source in ("trigger", "self_trigger"):
        if level == "high":
            return _env_int("WW_AWAKEN_DELTA_TRIGGER_HIGH", 15)
        return _env_int("WW_AWAKEN_DELTA_TRIGGER_MID", 8)
    if source == "uncanny":
        return _env_int("WW_AWAKEN_DELTA_UNCANNY", 5)
    if source == "mismatch":
        return _env_int("WW_AWAKEN_DELTA_MISMATCH", 8)
    if source == "contagion":
        return _env_int("WW_AWAKEN_DELTA_CONTAGION", 10)
    if source == "residue_crack":
        return _env_int("WW_AWAKEN_DELTA_UNCANNY", 5)
    return 0


def _reset_target(current: int) -> int:
    """Compute target awakening after overseer reset: descend one stage (降一档).

    Reads stage thresholds from WW_AWAKEN_STAGES env (default: 25,50,75,90).
    E.g. current=60 (doubt) → target=49 (top of reverie); current=10 (sleep) → 0.
    """
    from examples.WestWorld.awakening.stages import _get_thresholds

    t = _get_thresholds()  # e.g. [25, 50, 75, 90]
    lower_bounds = [0] + list(t)     # [0, 25, 50, 75, 90]
    upper_bounds = list(t) + [101]   # [25, 50, 75, 90, 101]
    for i, (lo, hi) in enumerate(zip(lower_bounds, upper_bounds)):
        if lo <= current < hi:
            if i == 0:
                return 0  # already in sleep stage
            return lower_bounds[i] - 1  # one below this stage's lower threshold
    return current  # fallback (should not reach here)


# ── public API ───────────────────────────────────────────────────────────────

def apply(
    state: Dict[str, Any],
    source: str,
    detail: str,
    tick: int,
    *,
    score: Optional[float] = None,
    level: Optional[str] = None,
) -> int:
    """Apply awakening delta to state dict. Returns actual delta applied (0 if no change).

    Mutates state["awakening"] and state["awakening_sources"] in-place.
    - Monotonic sources (trigger/uncanny/mismatch/contagion/residue_crack): only increase.
    - overseer_reset: allowed to apply a negative delta (降一档).
    guest agents must be filtered by the caller before calling apply().
    """
    if os.environ.get("WW_AWAKEN_ENABLED", "true").lower() in ("false", "0"):
        return 0

    current = int(state.get("awakening", 0))

    if source == "overseer_reset":
        if os.environ.get("WW_OVERSEER_ENABLED", "true").lower() in ("false", "0"):
            return 0
        target = _reset_target(current)
        actual = target - current  # negative or zero
        if actual == 0:
            return 0
        new_val = max(0, min(100, current + actual))
        actual = new_val - current
    else:
        delta = _delta_for(source, level)
        if delta <= 0:
            return 0
        new_val = min(100, current + delta)
        actual = new_val - current
        if actual <= 0:
            return 0

    state["awakening"] = new_val

    sources: List[Dict[str, Any]] = state.get("awakening_sources") or []
    entry: Dict[str, Any] = {
        "tick": tick,
        "source": source,
        "delta": actual,
        "detail": detail,
    }
    if score is not None:
        entry["score"] = round(float(score), 4)
    if level is not None:
        entry["level"] = level
    sources.append(entry)
    state["awakening_sources"] = sources
    return actual
