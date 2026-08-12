"""State plugin: per-agent runtime state and memory management.

Generic port of story_of_the_stone's BasicStatePlugin — no 红楼梦 assumptions.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

PROJECT_PATH = Path(__file__).resolve().parents[3]
if str(PROJECT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH))

from plugins._optional_deps import ensure_optional_agentkernel_imports

ensure_optional_agentkernel_imports()

from agentkernel_distributed.mas.agent.base.plugin_base import StatePlugin
from agentkernel_distributed.toolkit.logger import get_logger

logger = get_logger(__name__)

_MAX_EVENTS = 500
_MAX_RECENT_EVENTS = 120
_MAX_LONG_TERM_MEMORIES = 200


class BasicStatePlugin(StatePlugin):
    """Manages mutable agent state: tasks, plans, memory, dialogues, activity."""

    def __init__(
        self,
        adapter: Callable | None = None,
        state_data: Optional[Dict[str, Any]] = None,
        agent_id: str = "Unknown",
    ) -> None:
        super().__init__()
        self.adapter = adapter
        # state_data may arrive as a config-key string before real injection.
        self.state_data: Dict[str, Any] = state_data if isinstance(state_data, dict) else {}
        self.agent_id = agent_id
        self.current_tick = self.state_data.get("current_tick", 0)

        self.state_data.setdefault("long_task", None)
        self.state_data.setdefault("short_term_memory", {})
        self.state_data.setdefault("long_term_memory", [])
        self.state_data.setdefault("dialogues", {})
        self.state_data.setdefault("event_log", {})
        self.state_data.setdefault("is_active", True)
        self.state_data.setdefault("inactive_reason", "")
        self.state_data.setdefault("hourly_plans", {})
        self.state_data.setdefault("replan_log", [])
        self.state_data.setdefault("long_task_adj_log", [])
        self.state_data.setdefault("current_plan", None)
        self.state_data.setdefault("current_plan_note", None)
        self.state_data.setdefault("current_action", None)
        self.state_data.setdefault("occupied_by", None)
        self.state_data.setdefault("location_id", "")
        self.state_data.setdefault("current_location", "")
        self.state_data.setdefault("position", [0, 0])
        self.state_data.setdefault("mood", "")
        self.state_data.setdefault("status", "")
        self.state_data.setdefault("active_goal", None)
        self.state_data.setdefault("pending_user_action", None)
        self.state_data.setdefault("replanned_tick", None)
        self.state_data.setdefault("memory", {})

    async def init(self) -> None:
        if getattr(self, "_component", None):
            self.agent_id = self._component.agent.agent_id

    async def execute(self, current_tick: int) -> None:
        self.current_tick = current_tick
        self.state_data["current_tick"] = current_tick

    # ── Core get/set ────────────────────────────────────────────────
    async def get_state(self, key: str | None = None, default: Any = None) -> Any:
        if key is None:
            return self.state_data
        return self.state_data.get(key, default)

    async def set_state(self, key: str, value: Any) -> None:
        self.state_data[key] = value

    async def set_state_batch(self, state: Dict[str, Any]) -> None:
        self.state_data.update(state)

    # ── Long task ───────────────────────────────────────────────────
    async def set_long_task(self, long_task_str: str | None) -> None:
        self.state_data["long_task"] = long_task_str

    async def get_long_task(self) -> Optional[str]:
        return self.state_data.get("long_task")

    # ── Hourly plans (per day) ──────────────────────────────────────
    async def set_hourly_plans(self, hourly_plans: list, tick: int | None = None) -> None:
        effective_tick = self.current_tick if tick is None else tick
        day = (int(effective_tick) // 12) + 1
        self.state_data.setdefault("hourly_plans", {})[day] = hourly_plans

    async def get_hourly_plans(self, day: int | None = None) -> Any:
        all_plans = self.state_data.get("hourly_plans", {})
        if day is None:
            return all_plans
        if not isinstance(all_plans, dict):
            return None
        return all_plans.get(day) or all_plans.get(str(day))

    # ── Short-term memory (per tick) ────────────────────────────────
    async def add_short_term_memory(self, memory: str, tick: int | None = None) -> None:
        if self.agent_id == "Unknown":
            return
        effective_tick = self.current_tick if tick is None else tick
        memories = self.state_data.setdefault("short_term_memory", {})
        existing = memories.get(effective_tick)
        if existing:
            memories[effective_tick] = f"{existing}\n{memory}"
        else:
            memories[effective_tick] = memory
        recent = self.state_data.setdefault("memory", {}).setdefault("recent_events", [])
        recent.append(
            {"tick": effective_tick, "content": memory}
        )
        del recent[:-_MAX_RECENT_EVENTS]

    async def get_short_term_memory(self) -> list:
        memories = self.state_data.get("short_term_memory", {})
        if isinstance(memories, list):
            return [{"tick": i, "content": mem} for i, mem in enumerate(memories)]
        return [
            {"tick": tick, "content": memories[tick]}
            for tick in sorted(memories.keys(), key=lambda t: int(t))
        ]

    async def clear_short_term_memory(self) -> None:
        self.state_data["short_term_memory"] = {}

    # ── Long-term memory ────────────────────────────────────────────
    async def add_long_term_memory(self, memory: str) -> None:
        if self.agent_id == "Unknown":
            return
        long_term = self.state_data.setdefault("long_term_memory", [])
        long_term.append(
            {"tick": self.current_tick, "content": memory}
        )
        del long_term[:-_MAX_LONG_TERM_MEMORIES]
        reflections = self.state_data.setdefault("memory", {}).setdefault("reflection_summaries", [])
        reflections.append(
            {"tick": self.current_tick, "content": memory}
        )
        del reflections[:-_MAX_LONG_TERM_MEMORIES]

    async def get_long_term_memory(self) -> list:
        return self.state_data.get("long_term_memory", [])

    async def get_memory_profile(self) -> dict:
        return self.state_data.get("memory", {})

    # ── Dialogues ───────────────────────────────────────────────────
    async def add_dialogue(self, tick: int, history: list) -> None:
        if self.agent_id == "Unknown":
            return
        dialogues = self.state_data.setdefault("dialogues", {})
        existing = dialogues.get(tick) or dialogues.get(str(tick)) or []
        if isinstance(existing, list):
            dialogues[int(tick)] = [*existing, *copy.deepcopy(history)]
        else:
            dialogues[int(tick)] = copy.deepcopy(history)

    async def get_dialogues(self) -> dict:
        return self.state_data.get("dialogues", {})

    # ── Events (per tick) ────────────────────────────────────────────────────
    async def add_event(self, tick: int, event: Dict[str, Any]) -> None:
        """Store the resolved outcome of a plan separately from the plan itself."""
        if self.agent_id == "Unknown":
            return
        normalized = copy.deepcopy(event or {})
        normalized["tick"] = int(tick)
        events = self.state_data.setdefault("event_log", {})
        if isinstance(events, list):
            migrated: dict[int, list[dict[str, Any]]] = {}
            for index, item in enumerate(events):
                if isinstance(item, dict):
                    migrated.setdefault(int(item.get("tick", index)), []).append(copy.deepcopy(item))
            events = migrated
            self.state_data["event_log"] = events
        elif not isinstance(events, dict):
            events = {}
            self.state_data["event_log"] = events
        tick_key = int(tick)
        current = events.get(tick_key, events.get(str(tick_key)))
        if isinstance(current, list):
            bucket = current
        elif isinstance(current, dict):
            bucket = [current]
        else:
            bucket = []
        event_id = normalized.get("event_id")
        if not event_id or all(item.get("event_id") != event_id for item in bucket if isinstance(item, dict)):
            bucket.append(normalized)
        events[tick_key] = bucket
        self._trim_event_log(events)

    async def get_event_log(self) -> list[Dict[str, Any]]:
        events = self.state_data.get("event_log", {})
        if isinstance(events, list):
            return copy.deepcopy(events)
        if not isinstance(events, dict):
            return []
        flattened: list[Dict[str, Any]] = []
        for tick in sorted(events.keys(), key=lambda value: int(value)):
            bucket = events[tick]
            if isinstance(bucket, dict):
                flattened.append(copy.deepcopy(bucket))
            elif isinstance(bucket, list):
                flattened.extend(copy.deepcopy(item) for item in bucket if isinstance(item, dict))
        return flattened[-_MAX_EVENTS:]

    @staticmethod
    def _trim_event_log(events: dict) -> None:
        ordered = sorted(events.keys(), key=lambda value: int(value))
        total = sum(len(value) if isinstance(value, list) else 1 for value in events.values())
        while total > _MAX_EVENTS and ordered:
            oldest = ordered.pop(0)
            removed = events.pop(oldest, [])
            total -= len(removed) if isinstance(removed, list) else 1

    # ── Activity status ─────────────────────────────────────────────
    async def set_active_status(self, is_active: bool, reason: str = "") -> None:
        self.state_data["is_active"] = is_active
        if reason:
            self.state_data["inactive_reason"] = reason
        elif is_active:
            self.state_data["inactive_reason"] = ""
        if not is_active:
            self.state_data["current_plan"] = None
            self.state_data["current_action"] = None
            self.state_data["occupied_by"] = None

    async def is_active(self) -> bool:
        return bool(self.state_data.get("is_active", True))

    async def get_inactive_reason(self) -> str:
        return str(self.state_data.get("inactive_reason", ""))

    # ── Change logs ─────────────────────────────────────────────────
    async def add_replan_event(self, tick: int, reason: str, day: int, from_hour: int) -> None:
        self.state_data.setdefault("replan_log", []).append(
            {"tick": tick, "reason": reason, "day": day, "from_hour": from_hour}
        )

    async def get_replan_log(self) -> list:
        return self.state_data.get("replan_log", [])

    async def add_long_task_adjustment(self, tick: int, from_day: int) -> None:
        self.state_data.setdefault("long_task_adj_log", []).append({"tick": tick, "from_day": from_day})

    async def get_long_task_adjustment_log(self) -> list:
        return self.state_data.get("long_task_adj_log", [])

    # ── Snapshot restore (branching support) ────────────────────────
    async def restore_state(self, snapshot: dict) -> None:
        skip_keys = {"profile"}
        for key, value in snapshot.items():
            if key in skip_keys:
                continue
            if key == "short_term_memory" and isinstance(value, list):
                self.state_data["short_term_memory"] = {
                    item["tick"]: item["content"] for item in value if isinstance(item, dict)
                }
            elif key == "event_log" and isinstance(value, list):
                restored: dict[int, list[dict[str, Any]]] = {}
                for index, item in enumerate(value):
                    if not isinstance(item, dict):
                        continue
                    tick = int(item.get("tick", index))
                    restored.setdefault(tick, []).append(copy.deepcopy(item))
                self.state_data["event_log"] = restored
            else:
                self.state_data[key] = copy.deepcopy(value)
