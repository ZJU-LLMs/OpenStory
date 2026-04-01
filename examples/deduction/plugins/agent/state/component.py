"""Custom state component for deduction example."""

from typing import Any, List, Optional, Dict
from agentkernel_distributed.mas.agent.components import StateComponent
from agentkernel_distributed.toolkit.logger import get_logger

logger = get_logger(__name__)

class BasicStateComponent(StateComponent):
    """Extended state component with more delegations."""

    async def get_long_task(self) -> Optional[str]:
        """Delegate get_long_task to plugin."""
        if not self._plugin:
            return None
        return await self._plugin.get_long_task()

    async def get_state(self, key: str = None, default: Any = None) -> Any:
        """Delegate get_state to plugin."""
        if not self._plugin:
            return default
        return await self._plugin.get_state(key, default)

    async def get_dialogues(self) -> Dict[int, List[str]]:
        """Delegate get_dialogues to plugin."""
        if not self._plugin:
            return {}
        return await self._plugin.get_dialogues()

    async def get_long_term_memory(self) -> List[Dict[str, Any]]:
        """Delegate get_long_term_memory to plugin."""
        if not self._plugin:
            return []
        return await self._plugin.get_long_term_memory()

    async def is_active(self) -> bool:
        """Delegate is_active to plugin."""
        if not self._plugin:
            return True
        return await self._plugin.is_active()

    async def get_inactive_reason(self) -> str:
        """Delegate get_inactive_reason to plugin."""
        if not self._plugin:
            return ""
        return await self._plugin.get_inactive_reason()

    async def set_state(self, key: str, value: Any) -> None:
        """Delegate set_state to plugin."""
        if not self._plugin:
            return
        return await self._plugin.set_state(key, value)

    async def add_dialogue(self, tick: int, dialogue: List[str]) -> None:
        """Delegate add_dialogue to plugin."""
        if not self._plugin:
            return
        return await self._plugin.add_dialogue(tick, dialogue)
        
    async def add_long_term_memory(self, memory: str) -> None:
        """Delegate add_long_term_memory to plugin."""
        if not self._plugin:
            return
        return await self._plugin.add_long_term_memory(memory)
        
    async def get_short_term_memory(self) -> List[Any]:
        """Delegate get_short_term_memory to plugin."""
        if not self._plugin:
            return []
        return await self._plugin.get_short_term_memory()
