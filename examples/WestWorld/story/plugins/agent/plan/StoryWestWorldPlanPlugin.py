"""Player-directive adapter for WestWorld story mode."""
from __future__ import annotations

from typing import Any, Dict, Optional

from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter

from examples.WestWorld.plugins.agent.plan.WestWorldPlanPlugin import WestWorldPlanPlugin

logger = get_logger(__name__)


class StoryWestWorldPlanPlugin(WestWorldPlanPlugin):
    """Inject one validated player directive into the selected Host's next plan."""

    def __init__(self, redis: RedisKVAdapter, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.redis = redis

    async def _get_player_directive(self, current_tick: int) -> Optional[Dict[str, Any]]:
        agent_id = self.agent.agent_id if self.agent is not None else ""
        selected_agent_id = await self.redis.get("story:player_agent_id")
        if not agent_id or selected_agent_id != agent_id:
            return None

        key = f"user_plan:{agent_id}"
        directive = await self.redis.get(key)
        if not isinstance(directive, dict):
            return None

        scheduled_tick = directive.get("scheduled_tick", directive.get("tick"))
        if scheduled_tick != current_tick:
            if isinstance(scheduled_tick, int) and scheduled_tick < current_tick:
                await self.redis.delete(key)
                logger.warning(
                    "[%s] 丢弃过期玩家任务: scheduled_tick=%s, current_tick=%s",
                    agent_id,
                    scheduled_tick,
                    current_tick,
                )
            return None

        action = str(directive.get("action", "")).strip()
        if not action:
            await self.redis.delete(key)
            return None
        return {**directive, "action": action}

    async def _complete_player_directive(
        self,
        current_tick: int,
        directive: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        agent_id = self.agent.agent_id if self.agent is not None else ""
        if not agent_id:
            return
        await self.redis.set(f"story:directive_result:{current_tick}", result)
        await self.redis.delete(f"user_plan:{agent_id}")
        logger.info("[%s] tick %s 玩家任务已消费", agent_id, current_tick)
