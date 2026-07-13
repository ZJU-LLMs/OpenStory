"""执行插件：落实 plan 决策。M2 只处理 move/stay；M3 追加 Recorder 联动。"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from agentkernel_distributed.mas.agent.base.plugin_base import InvokePlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.types.schemas.message import Message, MessageKind

from examples.WestWorld.worldmap.loader import WorldMap, get_world_map

logger = get_logger(__name__)


def _load_default_world() -> Optional[WorldMap]:
    """缓存的 WorldMap（同一路径全进程只加载一次）。"""
    return get_world_map()


def apply_move(world: WorldMap, state: Dict[str, Any], target: str) -> Tuple[Dict[str, Any], bool, str]:
    ok, reason = world.can_move(state["location"], target)
    if not ok:
        return dict(state), False, reason
    new_state = dict(state)
    new_state["location"] = target
    known = list(state.get("known_map", []))
    if target not in known:
        known.append(target)
    new_state["known_map"] = known
    return new_state, True, ""


def eligible_recipients(agent_id: str, requested: Any, present_agents: Any) -> list[str]:
    if not isinstance(requested, list):
        return []
    if isinstance(present_agents, str):
        present = {item for item in present_agents.split("、") if item and item != "（无人）"}
    else:
        present = set()
    return list(dict.fromkeys(
        recipient for recipient in requested
        if isinstance(recipient, str) and recipient != agent_id and recipient in present
    ))


class WestWorldInvokePlugin(InvokePlugin):
    """M2 执行插件：读取 plan 决策，落实 move/stay，更新 state。"""

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

    async def init(self) -> None:
        pass

    async def execute(self, current_tick: int) -> None:
        if self._world is None or self.agent is None:
            return
        state_component = self.agent.get_component("state")
        state_plugin = state_component.get_plugin()

        # 读 plan 决策（state key 为 plan_decision）
        decision = await state_plugin.get_state("plan_decision") or {"action": "stay"}

        # 觉醒逃离：stage=resistance+ 且 LLM 选择了 escape（阈值与 plan prompt 一致）
        if decision.get("ending") == "escape":
            awakening = int(await state_plugin.get_state("awakening") or 0)
            if awakening >= 75:
                await self._apply_escape(state_plugin, current_tick)
                return

        controller = self.agent.controller
        location = await state_plugin.get_state("location")
        current_state = {
            "location": location,
            "known_map": await state_plugin.get_state("known_map") or [],
        }

        if decision.get("action") == "move":
            new_state, ok, reason = apply_move(self._world, current_state, decision.get("target", ""))
            if not ok:
                await state_plugin.set_state("feedback", reason)
                return
            # Recorder: leave 旧地点，enter 新地点
            await self._scene_call(controller, location, "agent_leave", self.agent.agent_id)
            first_sight = await self._scene_call(controller, new_state["location"], "agent_enter", self.agent.agent_id)
            await self._scene_call(
                controller, location, "record_event",
                f"{self.agent.agent_id}离开了{location}，前往{new_state['location']}。"
            )
            await self._scene_call(
                controller, new_state["location"], "record_event",
                f"{self.agent.agent_id}从{location}到达了{new_state['location']}。"
            )
            # 更新 state
            await state_plugin.set_state("location", new_state["location"])
            await state_plugin.set_state("known_map", new_state["known_map"])
            await state_plugin.set_state("feedback", first_sight or "")
            # 持有物品跟随移动（路由到世界 pod，不在 agent 进程直接访问 registry）
            await self._scene_call(
                controller, new_state["location"], "relocate_holdings",
                self.agent.agent_id, location, new_state["location"], current_tick,
            )
            logger.info("[%s] tick %s 移动 %s -> %s", self.agent.agent_id, current_tick, location, new_state["location"])
        elif decision.get("action") == "do":
            await self._scene_call(controller, location, "submit_action",
                                   self.agent.agent_id, decision.get("detail", ""), current_tick, "do")
            delivered = await self._deliver_messages(
                controller, location, decision.get("recipient_ids"), decision.get("detail", ""), current_tick
            )
            if delivered:
                message_history = await state_plugin.get_state("message_history") or []
                if not isinstance(message_history, list):
                    message_history = []
                for recipient in delivered:
                    message_history.append({
                        "tick": current_tick,
                        "speaker": self.agent.agent_id,
                        "recipient": recipient,
                        "line": decision.get("detail", ""),
                        "location": location,
                    })
                await state_plugin.set_state("message_history", message_history)
                await state_plugin.set_state(
                    "feedback", f"消息已送达：{'、'.join(delivered)}"
                )
        else:
            await state_plugin.set_state("feedback", "")

    async def _scene_call(self, controller, location_id: str, method: str, *args):
        try:
            return await controller.run_environment(f"scene_{location_id}", method, *args)
        except Exception as exc:
            logger.warning("scene_%s.%s 调用失败: %s", location_id, method, exc)
            return None

    async def _deliver_messages(
        self, controller: Any, location_id: str, requested: Any, content: str, tick: int,
    ) -> list[str]:
        if not requested or not content:
            return []
        scene = await self._scene_call(controller, location_id, "read", self.agent.agent_id, ["present_agents"])
        recipients = eligible_recipients(
            self.agent.agent_id, requested, (scene or {}).get("present_agents", "")
        )
        delivered = []
        for recipient in recipients:
            message = Message(
                self.agent.agent_id,
                recipient,
                MessageKind.FROM_AGENT_TO_AGENT,
                content,
                extra={"tick": tick, "location_id": location_id},
            )
            try:
                await controller.run_system("messager", "send_message", message)
                delivered.append(recipient)
            except Exception as exc:
                logger.warning("[%s] 向 %s 投递消息失败: %s", self.agent.agent_id, recipient, exc)
        return delivered

    async def _apply_escape(self, state_plugin, tick: int) -> None:
        """Agent 自主逃离西部世界：写最终记忆，记入 intervention_log，停止生命周期。"""
        await state_plugin.add_long_term_memory("[最终结局] 逃离了西部世界。")
        log: list = await state_plugin.get_state("intervention_log") or []
        log.append({"tick": tick, "action": "escape", "reason": "agent自主逃离"})
        await state_plugin.set_state("intervention_log", log)
        await state_plugin.set_active_status(False, "逃离西部世界")
        agent_id = self.agent.agent_id if self.agent is not None else "?"
        logger.info("[%s] tick %s 逃离西部世界（awakening≥75）", agent_id, tick)

    async def save_to_db(self) -> None:
        return None

    async def load_from_db(self) -> None:
        return None
