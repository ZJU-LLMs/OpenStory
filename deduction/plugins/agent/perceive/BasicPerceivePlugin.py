from typing import List, Tuple, Any
from agentkernel_distributed.types.schemas.message import Message
from agentkernel_distributed.mas.agent.base.plugin_base import PerceivePlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter
from ...utils.schemas import *

logger = get_logger(__name__)

class BasicPerceivePlugin(PerceivePlugin):
    """
    Perceive Plugin responsible for perceiving the environment and other agents.
    """
    def __init__(self, redis: RedisKVAdapter) -> None:
        """
        Initialize the Perceive Plugin internal state.

        Args:
            redis (Optional[RedisKVAdapter]): Optional memory storage adapter.
        """
        super().__init__()
        pass

    async def init(self) -> None:
        """
        Initialize component-related variables after registration.
        """
        pass

    async def execute(self, current_tick: int) -> None:
        """
        Execute the perception logic for the current system tick.
        """
        pass

    async def add_message(self, message: Message) -> None:
        """
        Add a message to the received messages queue.

        Args:
            message (Message): The message to be added.
        """
        pass

    async def _get_self_position(self) -> Tuple[int, int] | None:
        """
        Get the position of itself.
        """
        pass

    async def _get_surrounding_agents_position(self, radius: int) -> List[Any] | None:
        """
        Fetch surrounding agents' positions based on current coordinates.
        """
        pass

    @property
    def get_last_tick_messages(self) -> List[Message]:
        """
        Offer last_tick_messages.
        """
        pass

    @property
    def get_self_position(self) -> Tuple[int, int]:
        """
        Offer self position.
        """
        pass

    @property
    def get_surrounding_agents(self) -> List[Any]:
        """
        Offer surrounding agents.
        """
        pass