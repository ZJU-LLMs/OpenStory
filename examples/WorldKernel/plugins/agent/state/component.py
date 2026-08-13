"""Custom state component for WorldKernel — delegates to BasicStatePlugin."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_PATH = Path(__file__).resolve().parents[3]
if str(PROJECT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH))

from plugins._optional_deps import ensure_optional_agentkernel_imports

ensure_optional_agentkernel_imports()

from agentkernel_distributed.mas.agent.components import StateComponent
from agentkernel_distributed.toolkit.logger import get_logger

logger = get_logger(__name__)


class BasicStateComponent(StateComponent):
    """Extended state component exposing the full BasicStatePlugin surface."""

    async def get_state(self, key: str | None = None, default: Any = None) -> Any:
        if not self._plugin:
            return default
        return await self._plugin.get_state(key, default)

    async def set_state(self, key: str, value: Any) -> None:
        if not self._plugin:
            return
        await self._plugin.set_state(key, value)

    async def get_long_task(self) -> Optional[str]:
        if not self._plugin:
            return None
        return await self._plugin.get_long_task()

    async def set_long_task(self, long_task_str: str | None) -> None:
        if not self._plugin:
            return
        await self._plugin.set_long_task(long_task_str)

    async def get_hourly_plans(self, day: int | None = None) -> Any:
        if not self._plugin:
            return {}
        return await self._plugin.get_hourly_plans(day)

    async def set_hourly_plans(self, hourly_plans: list, tick: int | None = None) -> None:
        if not self._plugin:
            return
        await self._plugin.set_hourly_plans(hourly_plans, tick)

    async def add_short_term_memory(self, memory: str, tick: int | None = None) -> None:
        if not self._plugin:
            return
        await self._plugin.add_short_term_memory(memory, tick)

    async def get_short_term_memory(self) -> List[Dict[str, Any]]:
        if not self._plugin:
            return []
        return await self._plugin.get_short_term_memory()

    async def clear_short_term_memory(self) -> None:
        if not self._plugin:
            return
        await self._plugin.clear_short_term_memory()

    async def add_long_term_memory(self, memory: str) -> None:
        if not self._plugin:
            return
        await self._plugin.add_long_term_memory(memory)

    async def get_long_term_memory(self) -> List[Dict[str, Any]]:
        if not self._plugin:
            return []
        return await self._plugin.get_long_term_memory()

    async def add_dialogue(self, tick: int, dialogue: List[str]) -> None:
        if not self._plugin:
            return
        await self._plugin.add_dialogue(tick, dialogue)

    async def get_dialogues(self) -> Dict[int, List[str]]:
        if not self._plugin:
            return {}
        return await self._plugin.get_dialogues()

    async def add_event(self, tick: int, event: Dict[str, Any]) -> None:
        if not self._plugin:
            return
        await self._plugin.add_event(tick, event)

    async def get_event_log(self) -> List[Dict[str, Any]]:
        if not self._plugin:
            return []
        return await self._plugin.get_event_log()

    async def set_active_status(self, is_active: bool, reason: str = "") -> None:
        if not self._plugin:
            return
        await self._plugin.set_active_status(is_active, reason)

    async def is_active(self) -> bool:
        if not self._plugin:
            return True
        return await self._plugin.is_active()

    async def get_inactive_reason(self) -> str:
        if not self._plugin:
            return ""
        return await self._plugin.get_inactive_reason()

    async def add_replan_event(self, tick: int, reason: str, day: int, from_hour: int) -> None:
        if not self._plugin:
            return
        await self._plugin.add_replan_event(tick, reason, day, from_hour)

    async def get_replan_log(self) -> List[Dict[str, Any]]:
        if not self._plugin:
            return []
        return await self._plugin.get_replan_log()

    async def add_long_task_adjustment(self, tick: int, from_day: int) -> None:
        if not self._plugin:
            return
        await self._plugin.add_long_task_adjustment(tick, from_day)

    async def get_long_task_adjustment_log(self) -> List[Dict[str, Any]]:
        if not self._plugin:
            return []
        return await self._plugin.get_long_task_adjustment_log()

    async def restore_state(self, snapshot: dict) -> None:
        if not self._plugin:
            return
        await self._plugin.restore_state(snapshot)
