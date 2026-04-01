from typing import Callable, Dict, Any, Optional
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.mas.agent.base.plugin_base import StatePlugin
from agentkernel_distributed.types.schemas.action import ActionResult

logger = get_logger(__name__)

class BasicStatePlugin(StatePlugin):
    """
    Agent state plugin.
    """

    def __init__(self, adapter: Callable, state_data: Optional[Dict[str, Any]] = None, agent_id: str = "Unknown") -> None:
        super().__init__()
        self.adapter = adapter
        # If state_data is a string (config key), initialize as empty dictionary
        if isinstance(state_data, str):
            self.state_data = {}
        else:
            self.state_data = state_data or {}
        self.agent_id = agent_id
        self.current_tick = self.state_data.get('current_tick', 0)
        self.state_data['current_tick'] = self.current_tick
        # Initialize LongTask field
        if 'long_task' not in self.state_data:
            self.state_data['long_task'] = None
        # Initialize short-term memory dictionary (stored by tick)
        if 'short_term_memory' not in self.state_data:
            self.state_data['short_term_memory'] = {}
        # Backward compatibility: if it is a list, convert to dictionary
        elif isinstance(self.state_data['short_term_memory'], list):
            old_list = self.state_data['short_term_memory']
            self.state_data['short_term_memory'] = {i: mem for i, mem in enumerate(old_list)}
        # Initialize long-term memory list
        if 'long_term_memory' not in self.state_data:
            self.state_data['long_term_memory'] = []
        # Initialize dialogue history dictionary (stored by tick)
        if 'dialogues' not in self.state_data:
            self.state_data['dialogues'] = {}
        # Initialize active status (default is True)
        if 'is_active' not in self.state_data:
            self.state_data['is_active'] = True
        # Record specific reason for inactivity
        if 'inactive_reason' not in self.state_data:
            self.state_data['inactive_reason'] = ""
        # Initialize daily hourly plans (stored by day)
        if 'hourly_plans' not in self.state_data:
            self.state_data['hourly_plans'] = {}
        # Backward compatibility: if it is a list, convert to the first day's plan
        elif isinstance(self.state_data['hourly_plans'], list):
            old_list = self.state_data['hourly_plans']
            self.state_data['hourly_plans'] = {1: old_list}

    async def init(self) -> None:
        """Initialize StatePlugin, get agent_id from component"""
        if hasattr(self, '_component') and self._component and hasattr(self._component, 'agent'):
            self.agent_id = self._component.agent.agent_id
            logger.info(f"[{self.agent_id}] StatePlugin initialized")

    async def execute(self, current_tick: int) -> None:
        self.current_tick = current_tick
        self.state_data['current_tick'] = current_tick

    async def get_state(self, key: str = None, default: Any = None) -> Dict[str, Any]:
        """
        Get state data

        Args:
            key: State key, if None returns all states
            default: Default value

        Returns:
            State data
        """
        if key is None:
            return self.state_data
        return self.state_data.get(key, default)

    async def set_state(self, key: str, value: Any) -> None:
        """
        Set a single state value

        Args:
            key: State key
            value: State value
        """
        self.state_data[key] = value
        logger.debug(f"[{self.agent_id}][{self.current_tick}] State updated: {key} = {value}")

    async def set_state_batch(self, state: Dict[str, Any]) -> None:
        """
        Batch set states

        Args:
            state: State dictionary
        """
        self.state_data.update(state)
        logger.debug(f"[{self.agent_id}][{self.current_tick}] Batch state update: {list(state.keys())}")

    async def set_long_task(self, long_task_str: str) -> None:
        """
        Set LongTask field

        Args:
            long_task_str: String representation of LongTask
        """
        await self.set_state('long_task', long_task_str)
        logger.info(f"[{self.agent_id}][{self.current_tick}] LongTask set: {long_task_str}")

    async def get_long_task(self) -> Optional[str]:
        """
        Get LongTask field

        Returns:
            String representation of LongTask, or None if it doesn't exist
        """
        return await self.get_state('long_task')

    async def set_hourly_plans(self, hourly_plans: list) -> None:
        """
        Set 12 hourly plans, stored by day

        Args:
            hourly_plans: 12 hourly plans list, format is List[List[Any]]
        """
        day = (self.current_tick // 12) + 1
        
        if 'hourly_plans' not in self.state_data or not isinstance(self.state_data['hourly_plans'], dict):
            self.state_data['hourly_plans'] = {}
            
        self.state_data['hourly_plans'][day] = hourly_plans
        logger.info(f"[{self.agent_id}][{self.current_tick}] Day {day} 12 hourly plans set, total {len(hourly_plans)} hours")

    async def get_hourly_plans(self, day: int = None) -> Optional[Any]:
        """
        Get 12 hourly plans

        Args:
            day: Which day's plan to get. If None, returns all days' plans dictionary

        Returns:
            12 hourly plans list or dictionary, or None if it doesn't exist
        """
        all_plans = await self.get_state('hourly_plans')
        if day is None:
            return all_plans
        if isinstance(all_plans, dict):
            return all_plans.get(day)
        return None

    async def add_short_term_memory(self, memory: str, tick: int = None) -> None:
        """
        Add a short-term memory, overwrite if the tick already has memory

        Args:
            memory: Memory content
            tick: Tick number, if None uses current tick
        """
        # Ignore memory operation for Unknown person
        if self.agent_id == "Unknown":
            logger.debug(f"[Unknown] Ignored short-term memory operation")
            return

        if tick is None:
            tick = self.current_tick

        # Short-term memory is stored by tick for easy overwriting
        if 'short_term_memory' not in self.state_data:
            self.state_data['short_term_memory'] = {}

        # If memory already exists for this tick, log the overwrite
        if tick in self.state_data['short_term_memory']:
            old_memory = self.state_data['short_term_memory'][tick]
            logger.info(f"[{self.agent_id}][{tick}] Overwriting short-term memory: {old_memory[:30]}... -> {memory[:30]}...")
        else:
            logger.info(f"[{self.agent_id}][{tick}] Added short-term memory: {memory}")

        self.state_data['short_term_memory'][tick] = memory

    async def get_short_term_memory(self) -> list:
        """
        Get all short-term memories, sorted by tick

        Returns:
            Short-term memory list, each element is {'tick': int, 'content': str}
        """
        memories_dict = self.state_data.get('short_term_memory', {})
        if isinstance(memories_dict, list):
            # Backward compatibility (list), convert back to object list
            return [{'tick': i, 'content': mem} for i, mem in enumerate(memories_dict)]

        # Return memory object list sorted by tick
        sorted_ticks = sorted(memories_dict.keys())
        return [{'tick': tick, 'content': memories_dict[tick]} for tick in sorted_ticks]

    async def clear_short_term_memory(self) -> None:
        """
        Clear all short-term memories
        """
        self.state_data['short_term_memory'] = {}
        logger.info(f"[{self.agent_id}][{self.current_tick}] Short-term memory cleared")

    async def add_long_term_memory(self, memory: str) -> None:
        """
        Add a long-term memory

        Args:
            memory: Memory content
        """
        # Ignore memory operation for Unknown person
        if self.agent_id == "Unknown":
            logger.debug(f"[Unknown] Ignored long-term memory operation")
            return

        if 'long_term_memory' not in self.state_data:
            self.state_data['long_term_memory'] = []

        self.state_data['long_term_memory'].append({
            'tick': self.current_tick,
            'content': memory
        })
        logger.info(f"[{self.agent_id}][{self.current_tick}] Added long-term memory: {memory[:50]}...")

    async def get_long_term_memory(self) -> list:
        """
        Get all long-term memories

        Returns:
            Long-term memory list
        """
        return self.state_data.get('long_term_memory', [])

    async def add_dialogue(self, tick: int, history: list) -> None:
        """
        Add dialogue history

        Args:
            tick: Tick number
            history: Dialogue history list
        """
        if self.agent_id == "Unknown":
            return

        if 'dialogues' not in self.state_data:
            self.state_data['dialogues'] = {}
        
        self.state_data['dialogues'][tick] = history
        logger.info(f"[{self.agent_id}][{tick}] Saved dialogue history, total {len(history)} records")

    async def get_dialogues(self) -> dict:
        """
        Get all dialogue history

        Returns:
            Dialogue history dictionary {tick: history}
        """
        return self.state_data.get('dialogues', {})

    async def set_active_status(self, is_active: bool, reason: str = "") -> None:
        """
        Set agent's active status

        Args:
            is_active: Whether active
            reason: Reason description
        """
        self.state_data['is_active'] = is_active
        if reason:
            self.state_data['inactive_reason'] = reason
        logger.warning(f"[{self.agent_id}] Status changed: is_active={is_active}, reason: {reason}")

    async def is_active(self) -> bool:
        """
        Check if agent is active

        Returns:
            bool: Whether active
        """
        return self.state_data.get('is_active', True)

    async def get_inactive_reason(self) -> str:
        """
        Get reason for inactivity

        Returns:
            str: Reason description
        """
        return self.state_data.get('inactive_reason', "")
