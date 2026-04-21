from typing import Callable
from agentkernel_distributed.mas.action.base.plugin_base import CommunicationPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages.kv_adapters import RedisKVAdapter

logger = get_logger(__name__)

class BasicCommunicationPlugin(CommunicationPlugin):
    """
    BasicCommunicationPlugin achieve the communication function between two agents.
    """
    def __init__(self, adapter: Callable, redis: RedisKVAdapter):
        super().__init__()
        self.adapter = adapter

    async def init(self, controller, model_router) -> None:
        self.controller = controller
        self.model = model_router
