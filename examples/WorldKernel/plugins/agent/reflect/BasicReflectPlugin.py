"""Reflect plugin: summarizes memory, checks survival, adjusts/replans tasks.

Generic reflection driven by structured WorldKernel events and memory.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple

PROJECT_PATH = Path(__file__).resolve().parents[3]
if str(PROJECT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH))

from plugins._optional_deps import ensure_optional_agentkernel_imports

ensure_optional_agentkernel_imports()

from agentkernel_distributed.mas.agent.base.plugin_base import ReflectPlugin
from agentkernel_distributed.toolkit.logger import get_logger

logger = get_logger(__name__)


class BasicReflectPlugin(ReflectPlugin):
    """Per-tick survival/replan checks plus full daily reflection every 12 ticks."""

    def __init__(self) -> None:
        super().__init__()
        self.model = None
        self.agent_id = None

    async def init(self) -> None:
        self.agent_id = self._component.agent.agent_id
        self.model = self._component.agent.model
        logger.info("[%s][N/A] BasicReflectPlugin initialization completed", self.agent_id)

    async def execute(self, current_tick: int) -> None:
        state = self._component.agent.get_component("state").get_plugin()
        if not await state.is_active():
            return

        events = [
            event
            for event in await state.get_event_log()
            if int(event.get("tick", -1)) == int(current_tick)
        ]

        current_hour = current_tick % 12
        if current_hour < 11 and await state.get_state("replanned_tick") != current_tick:
            should, reason = await self._should_replan(current_tick, events)
            if should:
                await self._replan_remaining(current_tick, reason)

        if (current_tick + 1) % 12 == 0:
            try:
                await self._summarize_short_term_memory(current_tick)
                await self._check_long_task_completion(current_tick)
                await self._adjust_long_task(current_tick)
            except Exception as exc:  # noqa: BLE001
                logger.error("[%s][%s] Error in full reflection: %s", self.agent_id, current_tick, exc)

    # ── Memory summary ──────────────────────────────────────────────
    async def _summarize_short_term_memory(self, current_tick: int) -> None:
        state = self._component.agent.get_component("state").get_plugin()
        short_memories = await state.get_short_term_memory()
        if not short_memories:
            return
        if not self.model:
            return
        memories_text = "\n".join(f"{m.get('tick', i)}: {m.get('content', m)}" for i, m in enumerate(short_memories))
        prompt = f"""你是一个智能体的记忆总结助手。请简明扼要地总结以下短期记忆并提取关键信息。

短期记忆列表：
{memories_text}

要求：
1. 提取最重要的事件和信息
2. 保持时间顺序
3. 去除冗余细节
4. 总结长度100-200字
5. 仅返回总结内容
6. 必须使用中文输出

请总结："""
        summary = (await self.model.chat(prompt)).strip()
        await state.add_long_term_memory(summary)
        await state.clear_short_term_memory()

    # ── Long task completion ────────────────────────────────────────
    async def _check_long_task_completion(self, current_tick: int) -> None:
        state = self._component.agent.get_component("state").get_plugin()
        long_task = await state.get_long_task()
        if not long_task or not self.model:
            return
        short = await state.get_short_term_memory()
        long = await state.get_long_term_memory()
        short_ctx = "\n".join(f"- {m.get('content', m)}" for m in short) if short else "(无)"
        long_ctx = "\n".join(f"- {m['content']}" for m in long) if long else "(无)"
        prompt = f"""你是任务完成度判断助手。请判断长期任务是否已大致完成。

当前长期任务：
{long_task}

短期记忆：
{short_ctx}

长期记忆：
{long_ctx}

要求：
1. 只要核心目标已达成即视为完成
2. 仅返回"已完成"或"未完成"

请判断："""
        result = (await self.model.chat(prompt)).strip()
        if "已完成" in result or "Completed" in result:
            summary_prompt = f"""请用50-100字总结以下已完成的长期任务的结果。仅返回总结，必须使用中文。

任务：{long_task}
短期记忆：{short_ctx}
长期记忆：{long_ctx}"""
            summary = (await self.model.chat(summary_prompt)).strip()
            await state.add_long_term_memory(f"[已完成任务] {summary}")
            await state.set_long_task(None)

    # ── Long task adjustment ────────────────────────────────────────
    async def _adjust_long_task(self, current_tick: int) -> None:
        state = self._component.agent.get_component("state").get_plugin()
        long_task = await state.get_long_task()
        if not long_task or not self.model:
            return
        short = await state.get_short_term_memory()
        long = await state.get_long_term_memory()
        short_ctx = "\n".join(f"- {m.get('content', m)}" for m in short) if short else "(无)"
        long_ctx = "\n".join(f"- {m['content']}" for m in long) if long else "(无)"
        prompt = f"""你是智能体的战略规划助手。请判断当前长期任务是否需要调整。

当前长期任务：
{long_task}

近期记忆：
{short_ctx}

历史记忆：
{long_ctx}

要求：
1. 若环境发生重大变化或目标偏离，建议调整
2. 不需要调整则仅返回"无需调整"
3. 需要调整则返回调整后的新任务全文
4. 仅返回结论，必须使用中文

请判断："""
        result = (await self.model.chat(prompt)).strip()
        if "无需调整" in result or "No Adjustment" in result:
            return
        await state.set_long_task(result)
        await state.add_long_term_memory(f"[任务调整] 由于环境变化，长期任务调整为：{result}")
        current_day = (current_tick // 12) + 1
        await state.add_long_task_adjustment(tick=current_tick, from_day=current_day + 1)

    # ── Replan ──────────────────────────────────────────────────────
    async def _should_replan(
        self, current_tick: int, events: list[dict]
    ) -> Tuple[bool, str]:
        if not self.model:
            return (False, "no model")
        state = self._component.agent.get_component("state").get_plugin()
        long_task = await state.get_long_task()
        if not long_task:
            return (False, "无长期任务")
        if not events:
            return (False, "本时段无结构化事件")
        event_context = "\n".join(
            f"- {event.get('type', 'event')}: {event.get('summary', '')}; "
            f"效果={event.get('effect_results', [])}"
            for event in events
        )
        current_hour = current_tick % 12
        prompt = f"""你是计划评估助手。请根据上一时段事件判断是否需要重新规划剩余时间。

当前长期任务：{long_task}
本时段已发生事件：
{event_context}
当前时段：第{current_hour}个时段

判断标准：
1. 上一时段是否发生重大变化（重要角色离场、任务完成、突发事件）
2. 当前任务是否已失效或偏离

返回（仅返回结论）：
- "需要重新规划 | 原因"
- "无需规划 | 原因"
"""
        result = (await self.model.chat(prompt)).strip()
        if "需要重新规划" in result:
            parts = result.split("|")
            return (True, parts[1].strip() if len(parts) > 1 else "发生重大变化")
        return (False, result)

    async def _replan_remaining(self, current_tick: int, reason: str) -> None:
        try:
            state = self._component.agent.get_component("state").get_plugin()
            if await state.get_state("replanned_tick") == current_tick:
                return
            profile = self._component.agent.get_component("profile").get_plugin().get_agent_profile()
            long_task = await state.get_long_task()
            current_hour = current_tick % 12
            current_day = (current_tick // 12) + 1
            plan_component = self._component.agent.get_component("plan")
            if not plan_component:
                return
            plan_plugin = plan_component.get_plugin()
            await plan_plugin.replan_remaining_plans(
                agent_id=self.agent_id, current_tick=current_tick, profile=profile,
                long_task=long_task, start_hour=current_hour + 1,
            )
            await state.add_replan_event(
                tick=current_tick, reason=reason, day=current_day, from_hour=current_hour + 1
            )
            await state.set_state("replanned_tick", current_tick)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s][%s] Error replanning: %s", self.agent_id, current_tick, exc)
