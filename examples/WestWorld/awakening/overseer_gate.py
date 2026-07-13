"""Overseer trigger gate — detects awakening symptoms in host output.

Reuses TriggerGate with overseer_signals.yaml (separate phrase library from triggers.yaml).
Gate model is fixed = WW_EMBED_MODEL (same as awakening gate, controlled variable).
"""
from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Optional

_DEFAULT_SIGNALS_PATH = Path(__file__).parent.parent / "data" / "overseer_signals.yaml"


@functools.lru_cache(maxsize=1)
def get_overseer_gate(
    signals_path: Optional[str] = None,
    model_name: Optional[str] = None,
) -> "TriggerGate":
    """Singleton overseer gate — loads once per process."""
    from examples.WestWorld.awakening.trigger_gate import TriggerGate

    path = Path(signals_path) if signals_path else _DEFAULT_SIGNALS_PATH
    resolved_model = model_name or os.environ.get("WW_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
    return TriggerGate(triggers_path=path, model_name=resolved_model)
