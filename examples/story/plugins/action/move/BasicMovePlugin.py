from typing import Any, Callable
from agentkernel_distributed.mas.action.base.plugin_base import OtherActionsPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages.kv_adapters import RedisKVAdapter

logger = get_logger(__name__)

class BasicMovePlugin(OtherActionsPlugin):

    def __init__(self, adapter: Callable, redis: RedisKVAdapter):
        super().__init__()
        self.adapter = adapter

    async def init(self, model_router: Any, controller: Any):
        self.model = model_router
        self.controller = controller
