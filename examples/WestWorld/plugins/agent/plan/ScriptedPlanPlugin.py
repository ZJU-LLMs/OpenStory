"""Deterministic plan plugin selecting actions from the fixed script."""
from __future__ import annotations

from typing import Any, List, Optional

from agentkernel_distributed.mas.agent.base.plugin_base import PlanPlugin

from examples.WestWorld.core.schema import Event


class ScriptedPlanPlugin(PlanPlugin):
    _SCRIPT_EVENTS: List[Event] = []

    def __init__(self, events: Optional[List[Event]] = None, agent_id: str = "", **_: Any) -> None:
        super().__init__()
        self._events = events if events is not None else list(self._SCRIPT_EVENTS)
        self.agent_id = agent_id

    def action_for(self, tick: int) -> Optional[Event]:
        return next((event for event in self._events if event.tick == tick and event.actor == self.agent_id), None)

    async def init(self) -> None:
        if not self.agent_id and self.agent is not None:
            self.agent_id = self.agent.agent_id
        if not self._events:
            self._events = list(self._SCRIPT_EVENTS)

    async def execute(self, current_tick: int) -> None:
        state_component = self.agent.get_component("state")
        state_plugin = state_component.get_plugin()
        event = self.action_for(current_tick)
        value = None if event is None else {
            "id": event.id, "tick": event.tick, "actor": event.actor, "action": event.action,
            "target": event.target, "visibility": event.visibility,
        }
        await state_plugin.set_state("current_action", value)

    async def save_to_db(self) -> None:
        return None

    async def load_from_db(self) -> None:
        return None
