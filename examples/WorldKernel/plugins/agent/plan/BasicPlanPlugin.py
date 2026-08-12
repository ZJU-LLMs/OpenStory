"""Plan plugin: generates long tasks and 12-slot daily plans."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_PATH = Path(__file__).resolve().parents[3]
if str(PROJECT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH))

from plugins._optional_deps import ensure_optional_agentkernel_imports

ensure_optional_agentkernel_imports()

from agentkernel_distributed.mas.agent.base.plugin_base import PlanPlugin
from agentkernel_distributed.toolkit.logger import get_logger

from plugins.utils.schemas import HourlyPlan, LongTask

logger = get_logger(__name__)


class BasicPlanPlugin(PlanPlugin):
    """Generates plans grounded in profile, state memory, relations, and locations."""

    _world_context: str = "一个开放的模拟世界"
    _available_locations: List[dict[str, Any]] = []

    @classmethod
    def set_world_context(cls, context: str | dict[str, Any]) -> None:
        text = cls._format_world_background(context)
        if text:
            cls._world_context = text
        logger.info("[BasicPlanPlugin] World context set")

    @classmethod
    def set_locations(cls, locations: List[Any]) -> None:
        cls._available_locations = [cls._coerce_location_card(loc) for loc in locations or []]
        logger.info("[BasicPlanPlugin] Injected %d locations", len(cls._available_locations))

    def __init__(self, redis: Any = None) -> None:
        super().__init__()
        self.redis = redis
        self.model = None
        self.agent_id = None
        self.controller = None

    async def init(self) -> None:
        self.agent_id = self._component.agent.agent_id
        self.model = self._component.agent.model
        self.controller = self._component.agent.controller
        if self.__class__._world_context == "一个开放的模拟世界":
            self.__class__.set_world_context(self._load_world_background())
        logger.info("[%s][N/A] BasicPlanPlugin initialization completed", self.agent_id)

    async def execute(self, current_tick: int) -> None:
        try:
            state_plugin = self._component.agent.get_component("state").get_plugin()
            profile_plugin = self._component.agent.get_component("profile").get_plugin()

            if not await state_plugin.is_active():
                reason = await state_plugin.get_inactive_reason()
                logger.warning("[%s][%s] Agent offline, skip planning. Reason: %s", self.agent_id, current_tick, reason)
                return

            profile = profile_plugin.get_agent_profile()
            current_long_task = await state_plugin.get_long_task()
            memory = await self._get_memory_profile()

            if current_long_task is None:
                long_task_str = await self.generate_long_task(self.agent_id, current_tick, profile, memory=memory)
                await state_plugin.set_long_task(long_task_str)
                current_long_task = long_task_str

            if current_tick >= 0 and current_tick % 12 == 0:
                hourly_plans = await self.generate_hourly_plans(
                    self.agent_id, current_tick, profile, current_long_task, memory=memory
                )
                await state_plugin.set_hourly_plans(hourly_plans, tick=current_tick)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s][%s] Error executing PlanPlugin: %s", self.agent_id, current_tick, exc)

    async def generate_long_task(
        self,
        agent_id: str,
        current_tick: int,
        profile: Dict[str, Any],
        memory: Dict[str, Any] | None = None,
    ) -> str:
        goals = profile.get("goals", {}) or {}
        motivation = goals.get("motivation") or profile.get("motivation") or "角色内在动机"
        plan = await self._generate_plan_based_on_profile(profile, memory=memory)
        long_task = LongTask(
            task_description=plan,
            motivation=motivation,
            plan=plan,
            created_tick=current_tick,
            status="pending",
        )
        logger.info("[%s][%s] Generated LongTask: %s", agent_id, current_tick, long_task.to_string())
        return long_task.to_string()

    async def _generate_plan_based_on_profile(
        self,
        profile: Dict[str, Any],
        memory: Dict[str, Any] | None = None,
    ) -> str:
        if not self.model:
            raise RuntimeError("Model not initialized")

        prompt = f"""你是 WorldKernel 的长期计划生成器。请根据角色稳定档案、记忆和世界背景，生成一个适合当前模拟世界的一次性长期目标。

【世界背景】
{self._world_context}

【已知角色】
{await self._format_characters_info()}

【角色档案】
{self._format_profile_for_prompt(profile)}

【角色记忆】
{self._format_memory_for_prompt(memory)}

要求：
1. 目标必须符合角色身份、性格、价值观和长期动机。
2. 目标应该具体、可执行，能在后续多个 tick 中推动行动。
3. 不要生成日常重复习惯，要生成一次性的叙事目标。
4. 只输出中文计划正文，不要输出 JSON。
"""
        plan = await self.model.chat(prompt)
        if not plan:
            raise RuntimeError("Model returned empty long task")
        return str(plan).strip()

    async def generate_hourly_plans(
        self,
        agent_id: str,
        current_tick: int,
        profile: Dict[str, Any],
        long_task: str | None = None,
        memory: Dict[str, Any] | None = None,
    ) -> List[List[Any]]:
        if not self.model:
            raise RuntimeError("Model not initialized")

        memory = memory if memory is not None else await self._get_memory_profile()
        location_cards = await self._get_accessible_locations(profile, current_tick)
        allowed_names = self._allowed_location_names(location_cards)
        relation_context = await self._format_relation_context()
        current_state = await self._format_current_state()

        prompt = f"""你是 WorldKernel 的日程计划生成器。请为角色生成一天 12 个时段的行动计划。

【世界背景】
{self._world_context}

【角色档案】
{self._format_profile_for_prompt(profile)}

【当前状态】
{current_state}

【记忆】
{self._format_memory_for_prompt(memory)}

【关系】
{relation_context}

【长期目标】
{long_task or "暂无"}

【可用地点卡】
{self._format_location_cards(location_cards)}

要求：
1. 必须返回严格 JSON 数组，长度为 12。
2. 每项字段为 action, time, target, location, importance。
3. time 必须为 0 到 11。
4. location 必须从可用地点卡的 name 中选择。
5. target 若不是其他角色名，填“自己”或“无”。
6. 大多数时段应是角色自己的活动，少数高重要度时段可以互动。
7. action 是“计划意图”，要写角色想推进什么、确认什么或改变什么，不要预先写成已经发生的结果。
8. 相邻时段应承接角色记忆和前一时段可能产生的变化，避免 12 个彼此孤立或重复的动作。
9. action 使用中文短句，importance 为 1 到 10。
"""
        response = await self.model.chat(prompt)
        plans_data = self._parse_plan_json(str(response or ""))
        hourly_plans = self._normalize_plans(plans_data, allowed_names)
        logger.info("[%s][%s] Generated %d hourly plans", agent_id, current_tick, len(hourly_plans))
        return hourly_plans

    async def replan_remaining_plans(
        self,
        agent_id: str,
        current_tick: int,
        profile: Dict[str, Any],
        long_task: str | None = None,
        start_hour: int = 0,
    ) -> List[List[Any]]:
        if not self.model:
            raise RuntimeError("Model not initialized")

        location_cards = await self._get_accessible_locations(profile, current_tick)
        allowed_names = self._allowed_location_names(location_cards)
        memory = await self._get_memory_profile()
        relation_context = await self._format_relation_context()
        remaining = max(0, 12 - start_hour)

        prompt = f"""你是 WorldKernel 的重规划器。请从第 {start_hour} 个时段开始，重写当天剩余 {remaining} 个时段。

【世界背景】
{self._world_context}

【角色档案】
{self._format_profile_for_prompt(profile)}

【记忆】
{self._format_memory_for_prompt(memory)}

【关系】
{relation_context}

【长期目标】
{long_task or "暂无"}

【可用地点卡】
{self._format_location_cards(location_cards)}

要求：只返回 JSON 数组；time 只能覆盖 {start_hour} 到 11；location 必须来自可用地点卡 name；action 只写尚待执行的计划意图，不把预期结果当成事实；新的计划必须回应近期事件与重规划原因。
"""
        response = await self.model.chat(prompt)
        replanned = self._normalize_plans(self._parse_plan_json(str(response or "")), allowed_names, start_hour=start_hour)

        state_plugin = self._component.agent.get_component("state").get_plugin()
        current_day = (current_tick // 12) + 1
        existing = await state_plugin.get_hourly_plans(day=current_day)
        existing_list = self._coerce_plan_list(existing)

        by_hour = {plan[1]: plan for plan in existing_list if len(plan) >= 5 and isinstance(plan[1], int)}
        for plan in replanned:
            by_hour[plan[1]] = plan
        new_plans = [by_hour.get(hour) or self._fallback_plan(hour, allowed_names) for hour in range(12)]
        await state_plugin.set_hourly_plans(new_plans, tick=current_tick)
        await state_plugin.set_state("current_plan_note", None)
        logger.info("[%s][%s] Replanned remaining plans (%d slots)", agent_id, current_tick, len(new_plans))
        return new_plans

    async def _get_accessible_locations(self, profile: Dict[str, Any], current_tick: int) -> List[dict[str, Any]]:
        if self._available_locations:
            return list(self._available_locations)
        if not self.controller:
            return []
        try:
            locations = await self.controller.run_environment(
                "space", "list_accessible_locations", profile, current_tick
            )
            return [self._coerce_location_card(loc) for loc in locations or [] if isinstance(loc, dict)]
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s][%s] Failed to query accessible locations: %s", self.agent_id, current_tick, exc)
            return []

    async def _get_memory_profile(self) -> Dict[str, Any]:
        try:
            state = self._component.agent.get_component("state").get_plugin()
            memory = await state.get_memory_profile()
            return memory or {}
        except Exception:  # noqa: BLE001
            return {}

    async def _format_characters_info(self) -> str:
        if not self.controller:
            return "暂无其他角色信息"
        try:
            all_agent_ids = await self.controller.get_all_agent_ids()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s][N/A] Failed to get all agent ids: %s", self.agent_id, exc)
            return "暂无其他角色信息"
        others = [aid for aid in all_agent_ids if aid != self.agent_id]
        return "、".join(others) if others else "暂无其他角色信息"

    async def _format_relation_context(self) -> str:
        if not self.controller:
            return "暂无关系数据"
        try:
            relations = await self.controller.run_environment("relation", "get_relations", self.agent_id)
        except Exception:
            return "暂无关系数据"
        lines = []
        for rel in relations or []:
            other = rel.get("target") if rel.get("source") == self.agent_id else rel.get("source")
            lines.append(
                f"- 与 {other}: {rel.get('relation', 'related')}, 强度={rel.get('strength', '')}, {rel.get('description', '')}"
            )
        return "\n".join(lines) if lines else "暂无关系数据"

    async def _format_current_state(self) -> str:
        try:
            state = self._component.agent.get_component("state").get_plugin()
            location = await state.get_state("current_location", "")
            mood = await state.get_state("mood", "")
            status = await state.get_state("status", "")
            active_goal = await state.get_state("active_goal", "")
            return f"当前位置：{location or '未知'}；情绪：{mood or '未知'}；状态：{status or '正常'}；当前目标：{active_goal or '暂无'}"
        except Exception:
            return "当前状态未知"

    def _format_profile_for_prompt(self, profile: Dict[str, Any]) -> str:
        name = profile.get("name") or profile.get("id") or "未知"
        role = profile.get("role", "")
        personality = profile.get("personality", {}) or {}
        goals = profile.get("goals", {}) or {}
        capabilities = profile.get("capabilities", {}) or {}
        lines = [
            f"姓名：{name}",
            f"角色定位：{role or '未知'}",
            f"性格特质：{self._join(personality.get('traits', []))}",
            f"价值观：{self._join(profile.get('values') or personality.get('values', []))}",
            f"说话风格：{profile.get('speech_style') or personality.get('speech_style') or '未知'}",
            f"能力：{self._join(capabilities.get('skills', []))}",
            f"长期目标：{goals.get('long_term_goal') or profile.get('long_term_goal') or '未知'}",
            f"核心动机：{goals.get('motivation') or '未知'}",
        ]
        social = profile.get("social_profile", {})
        if social:
            lines.append(f"社会身份：{json.dumps(social, ensure_ascii=False)}")
        return "\n".join(lines)

    def _format_memory_for_prompt(self, memory: Dict[str, Any] | None) -> str:
        memory = memory or {}
        lines: list[str] = []
        if memory.get("background_summary"):
            lines.append(f"背景摘要：{memory['background_summary']}")
        for key, label in [("key_events", "关键经历"), ("past_events", "过往事件"), ("recent_events", "近期事件")]:
            values = memory.get(key) or []
            if values:
                rendered = []
                for item in values[-5:]:
                    rendered.append(item.get("content", "") if isinstance(item, dict) else str(item))
                lines.append(f"{label}：" + "；".join(v for v in rendered if v))
        return "\n".join(lines) if lines else "暂无记忆"

    def _format_location_cards(self, cards: list[dict[str, Any]]) -> str:
        if not cards:
            return "暂无地点卡"
        lines = []
        for loc in cards:
            parts = [
                f"name={loc.get('name') or loc.get('id')}",
                f"type={loc.get('type', '')}",
                f"activities={self._join(loc.get('activities', []))}",
                f"state={(loc.get('state') or {}).get('current_state', '')}",
                f"symbol={loc.get('symbolic_meaning', '')}",
                f"events={loc.get('key_plot_events', '')}",
            ]
            lines.append("- " + "；".join(str(part) for part in parts if part))
        return "\n".join(lines)

    def _normalize_plans(
        self,
        plans_data: list[dict[str, Any]],
        allowed_names: list[str],
        start_hour: int = 0,
    ) -> list[list[Any]]:
        by_hour: dict[int, list[Any]] = {}
        allowed = set(allowed_names)
        for item in plans_data:
            try:
                time = int(item.get("time"))
                if time < start_hour or time > 11:
                    continue
                location = str(item.get("location") or "")
                if allowed and location not in allowed:
                    location = allowed_names[0]
                plan = HourlyPlan(
                    action=str(item.get("action") or "观察周围"),
                    time=time,
                    target=str(item.get("target") or "自己"),
                    location=location or (allowed_names[0] if allowed_names else ""),
                    importance=int(item.get("importance") or 1),
                ).to_list()
                by_hour[time] = plan
            except Exception:
                continue
        return [by_hour.get(hour) or self._fallback_plan(hour, allowed_names) for hour in range(start_hour, 12)]

    @staticmethod
    def _parse_plan_json(response: str) -> List[Dict[str, Any]]:
        start = response.find("[")
        end = response.rfind("]") + 1
        json_str = response[start:end] if start != -1 and end > start else response
        data = json.loads(json_str)
        return data if isinstance(data, list) else []

    @staticmethod
    def _fallback_plan(hour: int, allowed_names: list[str]) -> list[Any]:
        return ["观察周围", hour, "自己", allowed_names[0] if allowed_names else "", 1]

    @staticmethod
    def _allowed_location_names(cards: list[dict[str, Any]]) -> list[str]:
        return [str(card.get("name") or card.get("id")) for card in cards if card.get("name") or card.get("id")]

    @staticmethod
    def _coerce_location_card(location: Any) -> dict[str, Any]:
        if isinstance(location, str):
            return {"id": location, "name": location, "activities": []}
        return dict(location or {})

    @staticmethod
    def _coerce_plan_list(value: Any) -> list[list[Any]]:
        if isinstance(value, dict):
            flattened = []
            for item in value.values():
                if isinstance(item, list):
                    flattened.extend(item if item and isinstance(item[0], list) else [item])
            return flattened
        return value if isinstance(value, list) else []

    @staticmethod
    def _join(value: Any) -> str:
        if isinstance(value, list):
            return "、".join(str(v) for v in value if v) or "未知"
        return str(value) if value else "未知"

    @staticmethod
    def _load_world_background() -> dict[str, Any]:
        path = PROJECT_PATH / "data" / "world" / "background.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _format_world_background(context: str | dict[str, Any]) -> str:
        if isinstance(context, str):
            return context.strip()
        if not isinstance(context, dict) or not context:
            return ""
        fields = [
            ("world_name", "世界名"),
            ("world_type", "世界类型"),
            ("description", "描述"),
            ("theme", "主题"),
            ("tone", "基调"),
            ("world_rules", "世界规则"),
            ("world_constraints", "世界约束"),
            ("simulation_start", "模拟开端"),
        ]
        lines = []
        for key, label in fields:
            value = context.get(key)
            if value:
                lines.append(f"{label}：{json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}")
        return "\n".join(lines)
