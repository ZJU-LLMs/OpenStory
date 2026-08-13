from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import time
from pathlib import Path
from typing import Any

from worldkernel.stage3.adapter import build_agentkernel_project


PROJECT_PATH = Path(__file__).resolve().parents[3]
PROJECT_ROOT = PROJECT_PATH.parents[1]
PACKAGES_ROOT = PROJECT_ROOT / "packages"


def _ensure_paths() -> None:
    for path in [PROJECT_ROOT, PROJECT_PATH]:
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
    if PACKAGES_ROOT.exists():
        for child in PACKAGES_ROOT.iterdir():
            if child.is_dir():
                child_str = str(child)
                if child_str not in sys.path:
                    sys.path.insert(0, child_str)


def _ensure_real_ray_available() -> None:
    if importlib.util.find_spec("ray") is None:
        raise RuntimeError("Ray is required for Stage3 runtime simulation")


class Stage3RuntimeManager:
    """Single active WorldKernel Agent-Kernel runtime for the web server."""

    def __init__(self, project_root: Path = PROJECT_PATH) -> None:
        self.project_root = project_root
        self.session_id: str | None = None
        self.session_root: Path | None = None
        self.adapter_result: dict[str, Any] | None = None
        self.builder: Any = None
        self.pod_manager: Any = None
        self.system: Any = None
        self.current_tick: int = 0
        self.last_agents_data: dict[str, Any] = {}
        self.last_locations_data: list[dict[str, Any]] = []
        self.started: bool = False
        self._lock = asyncio.Lock()
        self._stop_requested: bool = False

    async def start(self, session_root: str | Path, max_ticks: int = 100) -> dict[str, Any]:
        session_path = Path(session_root).resolve()
        self._validate_stage2_artifacts(session_path)
        _ensure_real_ray_available()

        async with self._lock:
            self._stop_requested = True
            await self._stop_unlocked(shutdown_ray=False)
            self._stop_requested = False

            adapter_result = build_agentkernel_project(session_path, max_ticks=max_ticks)
            if not adapter_result.dry_validation_passed:
                warnings = "; ".join(adapter_result.warnings or [])
                raise RuntimeError(f"Stage3 adapter dry validation failed. {warnings}")

            _ensure_paths()
            os.environ["MAS_PROJECT_ABS_PATH"] = str(self.project_root)
            os.environ["MAS_PROJECT_REL_PATH"] = "examples.WorldKernel"

            import ray
            from agentkernel_distributed.mas.builder import Builder
            from registry import RESOURCES_MAPS

            if not ray.is_initialized():
                ray.init(
                    runtime_env={
                        "working_dir": str(self.project_root),
                        "env_vars": {"PYTHONPATH": os.pathsep.join(sys.path)},
                        "excludes": ["*.pyc", "__pycache__"],
                    }
                )

            self.builder = Builder(project_path=str(self.project_root), resource_maps=RESOURCES_MAPS)
            self.pod_manager, self.system = await self.builder.init()
            self.session_id = session_path.name
            self.session_root = session_path
            self.adapter_result = adapter_result.model_dump(mode="json")
            self.current_tick = await self.system.run("timer", "get_tick")
            self.last_agents_data, self.last_locations_data = await asyncio.gather(
                self.pod_manager.collect_agents_data.remote(),
                self.pod_manager.collect_locations_data.remote(),
            )
            self.started = True
            return self.state()

    async def tick(self) -> dict[str, Any]:
        async with self._lock:
            if self._stop_requested:
                return self.state(extra={"stopping": True})
            if not self.started or not self.pod_manager or not self.system:
                raise RuntimeError("Stage3 runtime is not started")

            started_at = time.time()
            await self.pod_manager.step_agent.remote()
            if self._stop_requested:
                return self.state(extra={"stopping": True})
            await self.system.run("messager", "dispatch_messages")
            if self._stop_requested:
                return self.state(extra={"stopping": True})
            current_tick = await self.system.run("timer", "get_tick")
            duration = time.time() - started_at
            await self.pod_manager.update_agents_status.remote()
            if self._stop_requested:
                return self.state(extra={"stopping": True})
            await self.system.run("timer", "add_tick", duration_seconds=duration)

            self.current_tick = current_tick
            self.last_agents_data, self.last_locations_data = await asyncio.gather(
                self.pod_manager.collect_agents_data.remote(),
                self.pod_manager.collect_locations_data.remote(),
            )
            return self.state(extra={"duration_seconds": duration})

    def state(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        agents = self._normalize_agents(self.last_agents_data)
        payload = {
            "started": self.started,
            "session_id": self.session_id,
            "current_tick": self.current_tick,
            "agents": agents,
            "locations": self._normalize_locations(self.last_locations_data),
            "events": self._dedupe_events(agents),
            "adapter": self.adapter_result,
        }
        if extra:
            payload.update(extra)
        return payload

    async def set_next_action(
        self,
        agent_id: str,
        action: str,
        target: str | None,
        location: str,
    ) -> dict[str, Any]:
        async with self._lock:
            if not self.started or not self.pod_manager:
                raise RuntimeError("Stage3 runtime is not started")
            agent_ids = set((self.last_agents_data or {}).keys())
            if agent_id not in agent_ids:
                raise ValueError("agent not found")
            if target and target not in agent_ids:
                raise ValueError("target agent not found")
            normalized_action = " ".join(str(action or "").split()).strip()
            if not normalized_action:
                raise ValueError("action must not be empty")
            if len(normalized_action) > 300:
                raise ValueError("action is too long")

            # Adapter locations are already the semantic/spatial intersection.
            # Do not reload bounds or entrances here: Stage3 validates only the
            # logical destination, while the frontend resolves display routes.
            location_ids: set[str] = set()
            location_names: dict[str, str] = {}
            for item in self.last_locations_data or []:
                if not isinstance(item, dict):
                    continue
                location_id = str(item.get("id") or "")
                location_name = str(item.get("name") or "")
                if location_id:
                    location_ids.add(location_id)
                    if location_name:
                        location_names[location_name] = location_id
            resolved_location = location_names.get(location, location)
            if resolved_location not in location_ids:
                raise ValueError("location is not available in the current simulation")

            payload = {
                "action": normalized_action,
                "target": target or None,
                "location": resolved_location,
                "importance": 10,
                "submitted_tick": self.current_tick,
            }
            accepted = await self.pod_manager.set_pending_user_action.remote(agent_id, payload)
            if not accepted:
                raise RuntimeError("failed to store pending user action")
            self.last_agents_data.setdefault(agent_id, {})["pending_user_action"] = payload
            return {"accepted": True, "agent_id": agent_id, "pending_user_action": payload}

    async def stop(self, shutdown_ray: bool = True) -> dict[str, Any]:
        self._stop_requested = True
        async with self._lock:
            return await self._stop_unlocked(shutdown_ray=shutdown_ray)

    async def _stop_unlocked(self, shutdown_ray: bool = True) -> dict[str, Any]:
        try:
            if self.pod_manager:
                await self.pod_manager.close.remote()
        finally:
            self.pod_manager = None
        try:
            if self.system:
                await self.system.close()
        finally:
            self.system = None

        if shutdown_ray and importlib.util.find_spec("ray") is not None:
            import ray

            if ray.is_initialized():
                ray.shutdown()

        self.builder = None
        self.session_id = None
        self.session_root = None
        self.adapter_result = None
        self.started = False
        self.current_tick = 0
        self.last_agents_data = {}
        self.last_locations_data = []
        self._stop_requested = False
        return self.state()

    @staticmethod
    def _validate_stage2_artifacts(session_root: Path) -> None:
        if not session_root.exists():
            raise FileNotFoundError(f"session not found: {session_root}")
        semantic_manifest = session_root / "generated" / "artifacts" / "semantic" / "metadata" / "semantic_manifest.json"
        legacy_manifest = session_root / "generated" / "artifacts" / "metadata" / "semantic_manifest.json"
        spatial_blueprint = session_root / "generated" / "artifacts" / "spatial" / "spatial_blueprint.json"
        legacy_spatial = session_root / "generated" / "stage2" / "spatial" / "spatial_blueprint.json"
        if not semantic_manifest.exists() and not legacy_manifest.exists():
            raise FileNotFoundError("Stage2 semantic artifacts not found; run Stage2 first")
        if not spatial_blueprint.exists() and not legacy_spatial.exists():
            raise FileNotFoundError("Stage2 spatial blueprint not found; run Stage2 first")

    @staticmethod
    def _normalize_agents(raw_agents: dict[str, Any] | None) -> list[dict[str, Any]]:
        agents = []
        for agent_id, data in (raw_agents or {}).items():
            data = data or {}
            agents.append(
                {
                    "id": agent_id,
                    "profile": data.get("profile") or {},
                    "current_tick": data.get("current_tick", 0),
                    "location_id": data.get("location_id"),
                    "current_location": data.get("current_location"),
                    "position": data.get("position"),
                    "current_plan": data.get("current_plan"),
                    "current_action": data.get("current_action"),
                    "current_plan_note": data.get("current_plan_note"),
                    "occupied_by": data.get("occupied_by"),
                    "event_log": data.get("event_log") or [],
                    "dialogues": data.get("dialogues") or {},
                    "short_term_memory": data.get("short_term_memory") or [],
                    "long_term_memory": data.get("long_term_memory") or [],
                    "is_active": data.get("is_active", True),
                    "inactive_reason": data.get("inactive_reason", ""),
                    "mood": data.get("mood", ""),
                    "status": data.get("status", ""),
                    "active_goal": data.get("active_goal"),
                    "pending_user_action": data.get("pending_user_action"),
                }
            )
        return agents

    @staticmethod
    def _normalize_locations(raw_locations: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        return [dict(location) for location in (raw_locations or []) if isinstance(location, dict)]

    @staticmethod
    def _dedupe_events(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for agent in agents:
            for event in agent.get("event_log") or []:
                if not isinstance(event, dict):
                    continue
                event_id = str(event.get("event_id") or "")
                if not event_id:
                    event_id = "legacy:" + "|".join(
                        [
                            str(event.get("tick", "")),
                            str(event.get("initiator") or (event.get("participants") or [""])[0]),
                            str(event.get("summary", "")),
                        ]
                    )
                unique.setdefault(event_id, event)
        return sorted(
            unique.values(),
            key=lambda event: (int(event.get("tick", 0) or 0), str(event.get("event_id", ""))),
        )
