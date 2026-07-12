from __future__ import annotations

import os
from pathlib import Path

import yaml


def _load_raw_configs(config_path: Path) -> list[dict]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not raw:
        raise ValueError(f"no model config in {config_path}")
    if isinstance(raw, list):
        return [dict(item) for item in raw]
    if isinstance(raw, dict):
        return [dict(raw)]
    raise ValueError(f"unexpected config format in {config_path}")


def _with_api_key_fallback(cfg: dict, default_env: str = "WORLDKERNEL_API_KEY") -> dict:
    env_name = cfg.get("api_key_env") or default_env
    cfg["api_key"] = cfg.get("api_key") or os.getenv(env_name, "")
    workspace_env_name = cfg.get("workspace_id_env")
    if workspace_env_name:
        cfg["workspace_id"] = cfg.get("workspace_id") or os.getenv(workspace_env_name, "")
    return cfg


def load_model_config(config_path: Path) -> dict:
    for cfg in _load_raw_configs(config_path):
        capabilities = cfg.get("capabilities") or []
        if "chat" in capabilities:
            return _with_api_key_fallback(cfg)
    return _with_api_key_fallback(_load_raw_configs(config_path)[0])


def load_model_config_by_capability(config_path: Path, capability: str) -> dict:
    for cfg in _load_raw_configs(config_path):
        capabilities = cfg.get("capabilities") or []
        if capability in capabilities:
            return _with_api_key_fallback(cfg)
    raise ValueError(f"no model config with capability {capability!r} in {config_path}")
