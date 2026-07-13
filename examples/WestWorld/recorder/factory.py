"""用 models_config.yaml 的 text 角色构建带真实 LLM 的 LocationRecorder。"""
from __future__ import annotations

from examples.WestWorld.adapters.model_clients import build_llm
from examples.WestWorld.worldmap.loader import Location, load_world_map
from .location_recorder import LocationRecorder


def build_recorder(location: Location, models_config_path: str) -> LocationRecorder:
    """为单个地点构建带真实 LLM 的 LocationRecorder。"""
    return LocationRecorder(location=location, llm=build_llm(models_config_path))


def build_active_recorders(locations_path: str, models_config_path: str) -> dict[str, LocationRecorder]:
    """为所有活跃地点构建 LocationRecorder 字典。"""
    world = load_world_map(locations_path)
    llm = build_llm(models_config_path)
    return {lid: LocationRecorder(location=world.get(lid), llm=llm)
            for lid in sorted(world.active_ids())}
