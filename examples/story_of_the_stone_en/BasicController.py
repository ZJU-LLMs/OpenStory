from __future__ import annotations
from typing import List, Optional, Tuple

from agentkernel_distributed.mas.controller.controller import ControllerImpl
from agentkernel_distributed.mas.interface.protocol import EventCategory, SimulationEvent
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter

logger = get_logger(__name__)

REDIS_CHANNEL_PREFIX = "sim_events"


class BasicController(ControllerImpl):
    """Controller extension that provides event publishing and convenience helpers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def update_agents_status(self) -> None:
        """
        Trigger each pod to refresh agent status within the environment.

        Returns:
            None
        """
        logger.info("Updating agent status...")
        

    async def get_all_agent_ids(self) -> List[str]:
        """
        Get all agent ids across all pods.
        """
        if self._pod_manager:
            return await self._pod_manager.get_all_agent_ids.remote()
        return self.get_agent_ids()

    async def get_available_actions(
            self,
            method_names: Optional[List[str]] = None,
            role: Optional[str] = None,
            gender: Optional[str] = None,
            tags: Optional[List[str]] = None,
    ) -> dict:
        """
        Get available actions for the agent with optional filtering.

        Args:
            method_names (Optional[List[str]]): Optional method name or list of method names to filter.
            role (Optional[str]): The role of the agent.(has which power to execute actions) Defaults to None.
            gender (Optional[str]): The gender of the agent. Defaults to None.
            tags (Optional[List[str]]): The tags of the agent.(the one's skills or abilities) Defaults to None.

        Returns:
            dict: A dictionary mapping component names to their available methods.
              Format: {component_name: {method_name: method_info}}
        """
        # TODO: Define valid role levels, gender types, and skill tag types to replace str
        if not self._action:
            raise RuntimeError("Action plugin not initialized.")
        
        available_actions = {}
        component_names = self._action.list_components()

        for component_name in component_names:
            # Get all methods for this component
            all_comp_methods = self._action.list_comp_methods_names(component_name)
            
            # Filter by method_names if provided
            if method_names:
                if isinstance(method_names, str):
                    comp_methods = [method_names] if method_names in all_comp_methods else []
                else:
                    comp_methods = [method for method in method_names if method in all_comp_methods]
            else:
                comp_methods = all_comp_methods
            
            # Get method info for filtered methods
            methods = await self._action.get_agent_call_methods(component_name, comp_methods)

            for method_info in methods:
                # Apply custom filters (role, gender, tags)
                if self._matches_filters(method_info, role, gender, tags):
                    method_name = method_info.get("name")
                    if method_name:
                        if component_name not in available_actions:
                            available_actions[component_name] = {}
                        available_actions[component_name][method_name] = method_info
        
        return available_actions

    def _matches_filters(self, method_info: dict, role: Optional[str], gender: Optional[str], tags: Optional[List[str]]) -> bool:
        """
        Check if the method_info matches the given filters.

        Args:
            method_info (dict): The method information dictionary.
            role (Optional[str]): The role of the agent.
            gender (Optional[str]): The gender of the agent.
            tags (Optional[List[str]]): The tags of the agent.

        Returns:
            bool: True if the method_info matches the filters, False otherwise.
        """
        
        # TODO: Write more detailed action filters
        if role and method_info.get("role") and method_info.get("role") != role:
            return False
        if gender and method_info.get("gender") and method_info.get("gender") != gender:
            return False
        if tags and method_info.get("tags") and not set(tags).issubset(set(method_info.get("tags", []))):
            return False
        return True