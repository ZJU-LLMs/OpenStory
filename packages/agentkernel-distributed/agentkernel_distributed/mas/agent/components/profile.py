"""Profile component that manages profile metadata."""

from typing import Any, Dict

from ....toolkit.logger import get_logger
from ..base.component_base import AgentComponent
from ..base.plugin_base import ProfilePlugin

__all__ = ["ProfileComponent"]

logger = get_logger(__name__)


class ProfileComponent(AgentComponent[ProfilePlugin]):
    """Component container for profile plugin."""

    COMPONENT_NAME = "profile"

    def __init__(self) -> None:
        """Initialize the profile component."""
        super().__init__()

    async def execute(self, current_tick: int) -> None:
        """
        Execute the profile plugin for the given simulation tick.

        Args:
            current_tick (int): Simulation tick used when invoking the plugin.
        """
        if not self._plugin:
            logger.warning("No plugin found in ProfileComponent.")
            return

        await self._plugin.execute(current_tick)

    def get_agent_profile(self) -> Dict[str, Any]:
        """
        Get the agent's profile data from the plugin.

        Returns:
            Dict[str, Any]: The agent's profile data.
        """
        if not self._plugin:
            logger.warning("No plugin found in ProfileComponent.")
            return {}
        return self._plugin.get_agent_profile()
