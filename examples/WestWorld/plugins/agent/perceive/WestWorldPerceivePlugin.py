"""感知插件：M2 用地图静态信息占位；M3 在 execute 中追加 Recorder read。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agentkernel_distributed.mas.agent.base.plugin_base import PerceivePlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.types.schemas.message import Message

from examples.WestWorld.worldmap.loader import WorldMap, get_world_map

logger = get_logger(__name__)


def build_percept(world: WorldMap, agent_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    here = world.get(state["location"])
    return {
        "location": here.id,
        "here_description": here.description,
        "neighbors": world.neighbors(here.id, active_only=True),
        "known_map": list(state.get("known_map", [])),
    }


def _load_default_world() -> Optional[WorldMap]:
    """缓存的 WorldMap（同一路径全进程只加载一次）。"""
    return get_world_map()


class WestWorldPerceivePlugin(PerceivePlugin):
    """M2 感知插件：从地图静态信息构建 percept，写入 state。"""

    def __init__(
        self,
        world: Optional[WorldMap] = None,
        locations: Any = None,
        **_: Any,
    ) -> None:
        super().__init__()
        # Builder injects locations per-agent (keyed by agent ID) which won't match
        # map location IDs — fall back to loading from the default data file path.
        self._world = world or _load_default_world()
        self._messages: List[Message] = []

    async def init(self) -> None:
        pass

    async def add_message(self, message: Message) -> None:
        self._messages.append(message)

    def _consume_messages(self) -> List[Dict[str, Any]]:
        messages, self._messages = self._messages, []
        agent_id = getattr(self.agent, "agent_id", None)
        return [
            {
                "from_id": message.from_id,
                "content": message.content,
                "kind": getattr(message.kind, "value", str(message.kind)),
            }
            for message in messages
            if message.from_id != agent_id
        ]

    async def execute(self, current_tick: int) -> None:
        if self._world is None or self.agent is None:
            return
        state_component = self.agent.get_component("state")
        state_plugin = state_component.get_plugin()

        location = await state_plugin.get_state("location")
        known_map = await state_plugin.get_state("known_map") or []
        current_state = {"location": location, "known_map": known_map}

        # Consume pending feedback from last tick's queued action
        controller = self.agent.controller
        try:
            feedback = await controller.run_environment(
                f"scene_{location}", "read_feedback", self.agent.agent_id
            )
            if feedback and isinstance(feedback, dict):
                await state_plugin.set_state("feedback", feedback.get("private_feedback", ""))
        except Exception as exc:
            logger.warning("[%s] 读取 feedback 失败: %s", self.agent.agent_id, exc)

        percept = build_percept(self._world, self.agent.agent_id, current_state)
        percept["messages"] = self._consume_messages()

        # Recorder 主导感知（per-agent 千人千面）
        try:
            try:
                profile_component = self.agent.get_component("profile")
                profile = profile_component.get_plugin().get_agent_profile() or {}
            except Exception:
                profile = {}
            agent_context = {
                "location": location,
                "discovered_ids": await state_plugin.get_state("discovered_ids") or [],
                "awakening": await state_plugin.get_state("awakening") or 0,
                "traits": profile.get("traits") or profile.get("character") or "",
                "last_action": (await state_plugin.get_state("plan_decision") or {}).get("detail", ""),
                "focus": await state_plugin.get_state("next_read") or [],
            }
            chunks = await controller.run_environment(
                f"scene_{location}", "perceive",
                self.agent.agent_id, agent_context)
            percept["scene"] = chunks
        except Exception as exc:
            logger.warning("[%s] 读取 scene_%s 失败，使用静态感知: %s",
                           self.agent.agent_id, location, exc)
            percept["scene"] = {}

        await state_plugin.set_state("percept", percept)

    async def save_to_db(self) -> None:
        return None

    async def load_from_db(self) -> None:
        return None
