from typing import Dict, List, Any, Optional, Callable

from agentkernel_distributed.mas.agent.base.plugin_base import ProfilePlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter

logger = get_logger(__name__)

class BasicProfilePlugin(ProfilePlugin):
    """
    ProfilePlugin is responsible for managing agent profile data.
    """

    def __init__(self, redis: RedisKVAdapter, profile_data: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the BasicProfilePlugin.

        Args:
            redis (RedisKVAdapter): The RedisKVAdapter instance for storage.
            profile_data (Optional[Dict[str, Any]]): The initial profile data of the agent, loaded from framework configuration.
        """
        super().__init__()
        self.redis = redis
        # If profile_data is a string (config key), initialize as an empty dictionary
        if isinstance(profile_data, str):
            self.profile_data = {}
        else:
            self.profile_data = profile_data or {}
        self.agent_id = self.profile_data.get('id', 'Unknown')
        self.long_memories: List[str] = []

    async def init(self) -> None:
        """
        Initialize component-related variables after registration.
        """
        self.controller = self._component.agent.controller

    async def execute(self, current_tick: int) -> None:
        """
        Execute the profile plugin at every system tick.

        Args:
            current_tick (int): The system current tick.
        """
        pass

    async def set_profile(self, key: str, value: Any) -> None:
        """
        Update a profile entry within the plugin.
        """
        self.profile_data[key] = value
        logger.debug(f"[{self.agent_id}][N/A] Profile updated: {key} = {value}")

    async def get_profile(self, key: str) -> Any:
        """
        Get a profile entry from the plugin.
        """
        return self.profile_data.get(key)

    def get_agent_profile(self) -> Dict[str, Any]:
        """Get the agent's profile data."""
        return self.profile_data

    def update_agent_profile(self, key: str, value: Any) -> None:
        """
        Update a specific key's value in the profile data.
        """
        self.profile_data[key] = value
        logger.debug(f"[{self.agent_id}][N/A] Profile updated: {key} = {value}")

    def get_callable_profiles(self) -> Dict[str, Any]:
        """Get the keys in the profile data that have non-empty values."""
        return {k: v for k, v in self.profile_data.items() if v}

    def add_long_memory(self, content: str) -> None:
        """Add a long-term memory entry to the profile."""
        self.long_memories.append(content)
        logger.info(f"[{self.agent_id}][N/A] Added long-term memory: {content}")

    async def get_agent_profile_by_id(self, target_agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get another agent's profile by calling their profile component through the controller.

        Args:
            target_agent_id (str): The ID of the target agent.

        Returns:
            Optional[Dict[str, Any]]: The target agent's profile data, or None if failed.
        """
        try:
            profile_data = await self.controller.run_agent_method(
                target_agent_id,
                "profile",
                "get_agent_profile"
            )
            logger.debug(f"[{self.agent_id}][N/A] Successfully retrieved profile of {target_agent_id}")
            return profile_data
        except Exception as e:
            logger.warning(f"[{self.agent_id}][N/A] Failed to retrieve profile of {target_agent_id}: {e}")
            return None