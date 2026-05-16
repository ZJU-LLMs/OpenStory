from __future__ import annotations

import os
from pathlib import Path

import yaml


def load_model_config(config_path: Path) -> dict:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not raw:
        raise ValueError(f"no model config in {config_path}")
    if isinstance(raw, list):
        cfg = dict(raw[0])
    elif isinstance(raw, dict):
        cfg = dict(raw)
    else:
        raise ValueError(f"unexpected config format in {config_path}")
    cfg["api_key"] = cfg.get("api_key") or os.getenv("WORLDKERNEL_API_KEY", "")
    return cfg
