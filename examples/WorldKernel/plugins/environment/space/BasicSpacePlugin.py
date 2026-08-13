"""Semantic location environment for Stage3 inference and access checks."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_PATH = Path(__file__).resolve().parents[3]
if str(PROJECT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH))

from plugins._optional_deps import ensure_optional_agentkernel_imports

ensure_optional_agentkernel_imports()

from agentkernel_distributed.mas.environment.base.plugin_base import SpacePlugin


class BasicSpacePlugin(SpacePlugin):
    """Location model without raster geometry or route-topology reasoning."""

    def __init__(
        self,
        locations: list[dict[str, Any]] | dict[str, Any] | None = None,
        paths: list[dict[str, Any]] | dict[str, Any] | None = None,
        agents: list[dict[str, Any]] | dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        raw_locations = list(locations.values()) if isinstance(locations, dict) else list(locations or [])
        self.locations = [
            location
            for location in raw_locations
            if isinstance(location, dict) and location.get("id")
        ]
        # Kept only as a constructor compatibility argument for older configs.
        # Stage3 deliberately does not load or reason over route topology.
        self.paths: list[dict[str, Any]] = []
        agent_rows = list(agents.values()) if isinstance(agents, dict) else list(agents or [])
        self.location_by_id = {str(loc.get("id")): loc for loc in self.locations if loc.get("id")}
        self.location_by_name = {str(loc.get("name")): loc for loc in self.locations if loc.get("name")}
        self.agent_positions = {str(agent.get("id")): dict(agent) for agent in agent_rows if agent.get("id")}

    async def get_location_profile(self, location_id_or_name: str | None) -> dict[str, Any] | None:
        if location_id_or_name is None:
            return None
        key = str(location_id_or_name)
        return self.location_by_id.get(key) or self.location_by_name.get(key)

    async def list_locations(self) -> list[dict[str, Any]]:
        return list(self.locations)

    async def list_accessible_locations(
        self,
        agent_profile: dict[str, Any] | None,
        current_tick: int = 0,
    ) -> list[dict[str, Any]]:
        accessible: list[dict[str, Any]] = []
        for location in self.locations:
            check = await self.can_agent_enter(agent_profile, str(location.get("id") or location.get("name")))
            if check.get("allowed"):
                accessible.append(self._location_card(location))
        return accessible

    async def get_location_affordances(self, location_id: str) -> dict[str, Any]:
        location = await self.get_location_profile(location_id)
        if not location:
            return {}
        access = location.get("access", {})
        state = location.get("state", {})
        return {
            "location_id": location.get("id"),
            "name": location.get("name"),
            "type": location.get("type"),
            "description": location.get("description", ""),
            "activities": self._infer_activities(location),
            "restrictions": {"access": access, "state": state},
            "capacity": location.get("capacity", state.get("capacity", 0)),
            "current_state": state.get("current_state", ""),
            "symbolic_meaning": location.get("symbolic_meaning", ""),
            "key_plot_events": location.get("key_plot_events", ""),
            "literary_imagery": location.get("literary_imagery", ""),
            "raw": location.get("raw", {}),
        }

    async def can_agent_enter(
        self,
        agent_profile: dict[str, Any] | None,
        location_id_or_name: str,
    ) -> dict[str, Any]:
        location = await self.get_location_profile(location_id_or_name)
        if not location:
            return {"allowed": False, "reason": "location is not available in the current simulation"}

        access = location.get("access", {})
        state = location.get("state", {})
        joined = " ".join(str(value) for value in [*access.values(), *state.values()]).lower()
        blocked_tokens = [
            "closed",
            "forbidden",
            "blocked",
            "sealed",
            "locked",
            "not enter",
            "no entry",
            "不可进入",
            "封闭",
            "禁止",
            "关闭",
            "封锁",
        ]
        if any(token in joined for token in blocked_tokens):
            return {
                "allowed": False,
                "reason": "location access is restricted",
                "location_id": location.get("id"),
                "location_name": location.get("name"),
            }

        return {
            "allowed": True,
            "location_id": location.get("id"),
            "location_name": location.get("name"),
        }

    async def find_route(self, from_location_id: str, to_location_id: str) -> dict[str, Any] | None:
        """Deprecated compatibility hook; route finding is a frontend concern."""
        if from_location_id == to_location_id and from_location_id in self.location_by_id:
            return {"same_location": True}
        return None

    async def get_agent_position(self, agent_id: str) -> list[int] | None:
        entry = self.agent_positions.get(agent_id)
        return entry.get("position") if entry else None

    async def update_agent_position(self, agent_id: str, position: list[int]) -> None:
        self.agent_positions.setdefault(agent_id, {})["position"] = position

    async def update_agent_location(self, agent_id: str, location_id: str) -> None:
        location = self.location_by_id.get(location_id)
        if not location:
            raise ValueError("cannot move an agent to a location outside the simulation")
        entry = self.agent_positions.setdefault(agent_id, {"id": agent_id})
        entry["location_id"] = location_id
        entry["location"] = location.get("name", "")

    async def get_all_positions(self) -> dict[str, list[int]]:
        return {
            agent_id: data.get("position", [0, 0])
            for agent_id, data in self.agent_positions.items()
        }

    async def get_surrounding_agents(self, position: list[int], radius: int) -> list[dict[str, Any]]:
        x, y = position[:2]
        surrounding = []
        for agent_id, data in self.agent_positions.items():
            ax, ay = (data.get("position") or [0, 0])[:2]
            if abs(ax - x) + abs(ay - y) <= radius:
                surrounding.append({"id": agent_id, **data})
        return surrounding

    def _location_card(self, location: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": location.get("id"),
            "name": location.get("name"),
            "type": location.get("type"),
            "description": location.get("description", ""),
            "access": location.get("access", {}),
            "state": location.get("state", {}),
            "capacity": location.get("capacity", 0),
            "tags": location.get("tags", []),
            "activities": self._infer_activities(location),
            "symbolic_meaning": location.get("symbolic_meaning", ""),
            "key_plot_events": location.get("key_plot_events", ""),
            "literary_imagery": location.get("literary_imagery", ""),
            "raw": location.get("raw", {}),
        }

    def _infer_activities(self, location: dict[str, Any]) -> list[str]:
        text = " ".join(
            str(value)
            for value in [
                location.get("name", ""),
                location.get("type", ""),
                location.get("description", ""),
                location.get("symbolic_meaning", ""),
                location.get("key_plot_events", ""),
            ]
        ).lower()
        activities = ["observe", "rest", "move_through"]
        if any(token in text for token in ["hall", "court", "garden", "public", "meeting", "gather", "厅", "堂", "园"]):
            activities.append("socialize")
        if any(token in text for token in ["study", "library", "room", "archive", "book", "书", "学", "房"]):
            activities.append("study")
        if any(token in text for token in ["shrine", "temple", "chapel", "ritual", "庙", "祠", "祭"]):
            activities.append("ritual")
        if any(token in text for token in ["market", "shop", "trade", "市", "店"]):
            activities.append("trade")
        return activities
