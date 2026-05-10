from __future__ import annotations

import os
from pathlib import Path

import yaml


def load_model_config(config_path: Path) -> dict:
    configs = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not configs:
        raise ValueError(f"no model config in {config_path}")
    cfg = dict(configs[0])
    cfg["api_key"] = cfg.get("api_key") or os.getenv("WORLDKERNEL_API_KEY", "")
    return cfg
