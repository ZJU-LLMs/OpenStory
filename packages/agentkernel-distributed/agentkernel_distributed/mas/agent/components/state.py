"""State component that maintains state via plugin."""

from typing import Any, List, Optional

from ....toolkit.logger import get_logger
from ..base.component_base import AgentComponent
from ..base.plugin_base import StatePlugin

__all__ = ["StateComponent"]

logger = get_logger(__name__)


class StateComponent(AgentComponent[StatePlugin]):
    """Component container for state plugin."""

    COMPONENT_NAME = "state"

    def __init__(self) -> None:
        """Initialize the state component."""
        super().__init__()

    async def execute(self, current_tick: int) -> None:
        """
        Execute the state plugin for the given simulation tick.

        Args:
            current_tick (int): Simulation tick used when invoking the plugin.
        """
        if not self._plugin:
            logger.warning("No plugin found in StateComponent.")
            return

        await self._plugin.execute(current_tick)

    async def get_hourly_plans(self) -> List[List[Any]]:
        """
        Get the hourly plans from the state plugin.

        Returns:
            List[List[Any]]: The hourly plans list.
        """
        if not self._plugin:
            logger.warning("No plugin found in StateComponent.")
            return []
        return await self._plugin.get_hourly_plans()

    async def add_short_term_memory(self, memory: str, tick: Optional[int] = None) -> None:
        """
        Add a short-term memory to the state plugin.

        Args:
            memory (str): The memory content to add.
            tick (Optional[int]): The tick number for this memory. If None, uses current tick.
        """
        if not self._plugin:
            logger.warning("No plugin found in StateComponent.")
            return
        await self._plugin.add_short_term_memory(memory, tick)

    async def get_short_term_memory(self) -> list:
        """
        Get all short-term memories from the state plugin.

        Returns:
            list: The short-term memory list.
        """
        if not self._plugin:
            logger.warning("No plugin found in StateComponent.")
            return []
        return await self._plugin.get_short_term_memory()
