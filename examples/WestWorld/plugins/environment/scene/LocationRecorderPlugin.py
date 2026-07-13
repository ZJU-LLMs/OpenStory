"""把 LocationRecorder 接入内核环境组件体系：每地点一个 scene_<id> 组件。"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Callable, Dict, List, Optional, Type

from agentkernel_distributed.mas.environment.base.plugin_base import GenericPlugin

from examples.WestWorld.recorder.location_recorder import LocationRecorder
from examples.WestWorld.worldmap.loader import Location, get_world_map

_DEFAULT_MODELS_CONFIG = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "configs", "models_config.yaml"
))


class LocationRecorderPlugin(GenericPlugin):
    COMPONENT_TYPE = "scene"

    def __init__(self, location_id: str, locations: Any = None,
                 llm_factory: Optional[Callable[[], Any]] = None,
                 models_config_path: str = "", **_: Any) -> None:
        super().__init__()
        self._location_id = location_id
        self._llm_factory = llm_factory
        self._models_config_path = models_config_path or _DEFAULT_MODELS_CONFIG
        self.recorder: Optional[LocationRecorder] = None
        self._recorder_lock = asyncio.Lock()

        # If locations is provided (list of dicts or list of Location), use it.
        # Otherwise fall back to loading from the default data file path.
        # (Builder injects locations per-agent by agent_id, not by location_id,
        #  so when running under the kernel we skip locations and load from file.)
        if locations is not None and isinstance(locations, list) and len(locations) > 0:
            loc = self._find_location(location_id, locations)
        else:
            loc = get_world_map().get(location_id)
        self._location = loc

    @staticmethod
    def _find_location(location_id: str, locations: list) -> Location:
        for item in locations:
            if isinstance(item, Location):
                if item.id == location_id:
                    return item
            elif isinstance(item, dict):
                if item.get("id") == location_id:
                    return Location(**item)
        raise KeyError(f"location '{location_id}' not found in provided locations list")

    async def init(self) -> None:
        recorder_mode = os.environ.get("WW_RECORDER_MODE", "structured").lower()
        if self._llm_factory is None:
            from examples.WestWorld.recorder.factory import build_llm
            if recorder_mode == "structured":
                parse_timeout = float(os.environ.get("WW_PARSE_TIMEOUT_SECONDS", "240"))
                self._llm_factory = lambda: build_llm(self._models_config_path, timeout_override=parse_timeout)
            else:
                self._llm_factory = lambda: build_llm(self._models_config_path)
        recorder_class = LocationRecorder
        if recorder_mode == "structured":
            from examples.WestWorld.recorder.structured_location_recorder import StructuredLocationRecorder
            recorder_class = StructuredLocationRecorder
        self.recorder = recorder_class(location=self._location, llm=self._llm_factory())

    async def execute(self, current_tick: int) -> None:
        if self.recorder:
            async with self._recorder_lock:
                await asyncio.to_thread(self.recorder.tick_update, current_tick)

    async def read(self, agent_id: str, chunks: List[str]) -> Dict[str, Any]:
        async with self._recorder_lock:
            return self.recorder.read(agent_id, chunks)

    async def perceive(self, agent_id: str, agent_context: dict) -> Dict[str, Any]:
        async with self._recorder_lock:
            return self.recorder.perceive(agent_id, agent_context)

    async def submit_action(
        self,
        agent_id: str,
        action_text: str,
        tick: Optional[int] = None,
        action_type: str = "do",
    ) -> Dict[str, Any]:
        # Enqueue only — no LLM call here. Lock protects list append.
        async with self._recorder_lock:
            return self.recorder.submit_action(agent_id, action_text, tick, action_type)

    async def read_feedback(self, agent_id: str) -> Optional[Dict[str, Any]]:
        async with self._recorder_lock:
            return self.recorder.read_feedback(agent_id)

    async def agent_enter(self, agent_id: str) -> str:
        async with self._recorder_lock:
            return self.recorder.agent_enter(agent_id)

    async def agent_leave(self, agent_id: str) -> None:
        async with self._recorder_lock:
            self.recorder.agent_leave(agent_id)

    async def set_present_agents(self, agent_ids: List[str]) -> None:
        async with self._recorder_lock:
            self.recorder.set_present_agents(agent_ids)

    async def record_event(self, event_summary: str) -> None:
        async with self._recorder_lock:
            self.recorder.record_event(event_summary)

    async def snapshot(self, include_hidden: bool = False, include_pending: bool = False,
                       drain_traces: bool = False) -> Dict[str, Any]:
        async with self._recorder_lock:
            snapshot = self.recorder.snapshot(
                include_hidden=include_hidden,
                include_pending=include_pending,
            )
            if drain_traces:
                snapshot["llm_traces"] = self.recorder.drain_llm_traces()
            return snapshot

    async def world_snapshot(self) -> Dict[str, Any]:
        from examples.WestWorld.recorder.world_object_registry import get_object_registry
        async with self._recorder_lock:
            return get_object_registry().snapshot()

    async def restore_world_snapshot(self, snapshot: Dict[str, Any]) -> None:
        from examples.WestWorld.recorder.world_object_registry import get_object_registry
        async with self._recorder_lock:
            get_object_registry().restore(snapshot)

    async def restore_snapshot(self, snapshot: Dict[str, Any]) -> None:
        if not self.recorder:
            raise RuntimeError("scene recorder is not initialized")
        restore = getattr(self.recorder, "restore", None)
        if not restore:
            raise RuntimeError("selected recorder does not support restore")
        async with self._recorder_lock:
            restore(snapshot)

    async def relocate_holdings(
        self, agent_id: str, from_location: str, to_location: str,
        tick: Optional[int] = None,
    ) -> None:
        from examples.WestWorld.recorder.world_object_registry import get_object_registry
        async with self._recorder_lock:
            get_object_registry().relocate_holdings(agent_id, to_location, tick)

    async def save_to_db(self) -> None:
        return None

    async def load_from_db(self) -> None:
        return None


def make_scene_plugin_class(location_id: str) -> Type[LocationRecorderPlugin]:
    """Dynamically create a per-location plugin class with COMPONENT_TYPE = scene_<location_id>."""
    return type(f"Scene_{location_id}_Plugin", (LocationRecorderPlugin,),
                {"COMPONENT_TYPE": f"scene_{location_id}"})
