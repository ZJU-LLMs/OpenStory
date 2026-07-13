"""反思插件：每 tick 累积短期记忆，每 N tick 总结进长期记忆，天边界重置 host 位置。

每日重置（host only）在天边界 _summarize 之后执行，确保下一 tick 的 perceive
从 loop_origin 出发，与 plan 的天首 daily_loop 复制时序对齐。

觉醒机制：_summarize 之后插 _blur（host only），高扰动记忆按觉醒度反向模糊。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from agentkernel_distributed.mas.agent.base.plugin_base import ReflectPlugin
from agentkernel_distributed.toolkit.logger import get_logger

from examples.WestWorld.plugins.agent.reflect.memory_blur import (
    classify_disturbance,
    blur_strength,
    render_blur_prompt,
)
from examples.WestWorld.awakening import awakening_engine

logger = get_logger(__name__)

SUMMARY_PROMPT = """你是西部世界角色「{name}」的记忆整理助手。
下面是 ta 最近若干刻发生的事（短期记忆），请用一段话（80-150 字）以第三人称总结这段经历，
保留关键事件、地点变化和与他人的互动，去掉冗余。只返回总结正文，不要前缀。

短期记忆：
{memories}

请总结："""

REPLAN_JUDGE_PROMPT = """你是西部世界角色「{name}」。{inner_voice}
你此刻的想法：{thought}
你今天剩下的计划是：{remaining_loop}
刚刚这一刻发生了：{this_tick_event}（你的动作 + 结果 + 收到的消息）

基于你此刻真实的内心状态和刚刚发生的事，你是否想要改写今天剩余的计划？
（日常对话、环境细节、情绪波动不值得改计划。）

只输出 JSON：{{"replan": true/false, "reason": "<简短>"}}"""


def compose_tick_memory(decision: Optional[Dict[str, Any]], feedback: str, location: str, tick: int) -> str:
    decision = decision or {}
    action = decision.get("action", "stay")
    if action == "move":
        body = f"我前往了 {decision.get('target', '')}"
    elif action == "do":
        body = decision.get("detail") or "我做了一件事"
    else:
        body = "我在原地停留"
    line = f"（第{tick}刻@{location}）{body}"
    if feedback:
        line += f"。结果：{feedback}"
    return line


def should_summarize(tick: int, interval: int) -> bool:
    if interval <= 0:
        return False
    return (tick + 1) % interval == 0


def render_summary_prompt(name: str, memories: List[str]) -> str:
    joined = "\n".join(f"- {m}" for m in memories)
    return SUMMARY_PROMPT.format(name=name, memories=joined)


def _read_profile(agent) -> Dict[str, Any]:
    try:
        profile_plugin = agent.get_component("profile").get_plugin()
        return profile_plugin.get_agent_profile() or {}
    except Exception as exc:
        logger.warning("[%s] 读取 profile 失败: %s", getattr(agent, "agent_id", "?"), exc)
        return {}


class WestWorldReflectPlugin(ReflectPlugin):
    def __init__(self, interval: Optional[int] = None, **_: Any) -> None:
        super().__init__()
        self.model = None
        self.interval = interval if interval else int(os.environ.get("WW_REFLECT_INTERVAL", "6"))

    async def init(self) -> None:
        pass

    async def execute(self, current_tick: int) -> None:
        if self.agent is None:
            return
        if self.model is None:
            self.model = self._component.agent.model

        state_plugin = self.agent.get_component("state").get_plugin()

        decision = await state_plugin.get_state("plan_decision") or {}
        feedback = await state_plugin.get_state("feedback") or ""
        location = await state_plugin.get_state("location") or ""

        memory = compose_tick_memory(decision, feedback, location, current_tick)
        await state_plugin.add_short_term_memory(memory, current_tick)

        # 觉醒 gate（仅 host）：检测违和/触发词/矛盾，写 awakening_sources
        await self._check_awakening_gate(state_plugin, current_tick)

        # Replan 判断（WW_ENABLE_REPLAN=true 且非最后一段）
        if (
            os.environ.get("WW_ENABLE_REPLAN", "").lower() in ("true", "1")
            and self.model is not None
            and current_tick % 6 < 5
        ):
            should_rp, reason = await self._should_replan(state_plugin, current_tick, decision, feedback)
            if should_rp:
                try:
                    plan_plugin = self.agent.get_component("plan").get_plugin()
                    await plan_plugin.replan_remaining(current_tick, reason, state_plugin)
                except Exception as exc:
                    logger.warning("[%s] replan 调用失败: %s", self.agent.agent_id, exc)

        # 天边界：总结短期记忆 + host 模糊化 + 每日重置
        if should_summarize(current_tick, self.interval):
            await self._summarize(state_plugin, current_tick)
            profile = _read_profile(self.agent)
            if profile.get("agent_type") == "host":
                await self._blur(state_plugin, current_tick, profile)
                await self._check_residue(state_plugin, current_tick)
            await self._day_reset(state_plugin, current_tick)

    async def _summarize(self, state_plugin, current_tick: int) -> None:
        memories = await state_plugin.get_short_term_memory()
        if not memories or self.model is None:
            return

        profile = _read_profile(self.agent)
        name = profile.get("name") or profile.get("姓名") or self.agent.agent_id
        texts = [m.get("content", str(m)) for m in memories]
        prompt = render_summary_prompt(name, texts)

        request_id = f"req_{uuid.uuid4().hex}"
        started = time.perf_counter()
        try:
            summary = await self.model.chat(
                prompt,
                timeout=int(os.environ.get("WW_LLM_TIMEOUT_SECONDS", "120")),
                max_attempts=int(os.environ.get("WW_LLM_MAX_ATTEMPTS", "3")),
                _trace_context={
                    "request_id": request_id,
                    "request_type": "agent_reflect",
                    "tick": current_tick,
                    "agent_id": self.agent.agent_id,
                },
            )
        except Exception as exc:
            logger.warning("[%s] reflect LLM 总结失败，保留短期记忆: %s", self.agent.agent_id, exc)
            return

        summary_text = summary if isinstance(summary, str) else str(summary)
        if summary_text.strip():
            await state_plugin.add_long_term_memory(summary_text.strip())
            await state_plugin.clear_short_term_memory()
            logger.info(
                "[%s] tick %s 反思总结(%s 条→长期记忆, 耗时%sms)",
                self.agent.agent_id, current_tick, len(texts),
                round((time.perf_counter() - started) * 1000, 1),
            )
            await state_plugin.set_state("last_reflect", {
                "tick": current_tick,
                "timestamp": datetime.now().astimezone().isoformat(),
                "summarized": len(texts),
            })

    async def _blur(self, state_plugin, current_tick: int, profile: Dict[str, Any]) -> None:
        """对长期记忆中最新一条高扰动内容按觉醒度模糊；清晰原文存入 suppressed_memories。"""
        model = self.model or (
            getattr(getattr(self, "_component", None), "agent", None) and
            self._component.agent.model
        )
        if not model:
            return
        if os.environ.get("WW_AWAKEN_ENABLED", "true").lower() in ("false", "0"):
            return

        long_mems: List[Dict[str, Any]] = await state_plugin.get_long_term_memory() or []
        if not long_mems:
            return

        awakening = int(await state_plugin.get_state("awakening") or 0)
        clear_threshold = int(os.environ.get("WW_AWAKEN_CLEAR_THRESHOLD", "75"))
        strength = blur_strength(awakening, clear_threshold)

        # 模糊强度为 0 时不改写（高觉醒度已使模糊失效）
        if strength <= 0:
            return

        # 检查最新长期记忆是否高扰动
        latest = long_mems[-1]
        text = latest.get("content", str(latest))
        if not classify_disturbance(text):
            return

        # 清晰版存入 suppressed_memories
        suppressed: List[Dict[str, Any]] = await state_plugin.get_state("suppressed_memories") or []
        suppressed.append({"tick": current_tick, "text": text, "awakening_at_blur": awakening})
        await state_plugin.set_state("suppressed_memories", suppressed)

        # LLM 改写
        name = profile.get("name") or profile.get("姓名") or self.agent.agent_id
        prompt = render_blur_prompt(name, text, strength)
        try:
            blurred = await model.chat(
                prompt,
                timeout=int(os.environ.get("WW_LLM_TIMEOUT_SECONDS", "120")),
                max_attempts=2,
                _trace_context={
                    "request_type": "agent_blur",
                    "tick": current_tick,
                    "agent_id": self.agent.agent_id,
                },
            )
        except Exception as exc:
            logger.warning("[%s] blur LLM 改写失败，保留原文: %s", self.agent.agent_id, exc)
            return

        blurred_text = blurred.strip() if isinstance(blurred, str) else str(blurred)
        if blurred_text:
            # 替换长期记忆最后一条
            if isinstance(latest, dict):
                long_mems[-1] = {**latest, "content": blurred_text}
            else:
                long_mems[-1] = {"content": blurred_text}
            await state_plugin.set_state("long_term_memory", long_mems)
            logger.info(
                "[%s] tick %s 记忆模糊化（strength=%.2f）",
                self.agent.agent_id, current_tick, strength,
            )

    async def _check_residue(self, state_plugin, current_tick: int) -> None:
        """觉醒度已超过梦呓阈值时，将 suppressed_memories 中匹配碎片回流到长期记忆。"""
        awakening = int(await state_plugin.get_state("awakening") or 0)
        reverie_threshold = int(os.environ.get("WW_AWAKEN_STAGES", "25,50,75,90").split(",")[0])
        if awakening < reverie_threshold:
            return

        suppressed: List[Dict[str, Any]] = await state_plugin.get_state("suppressed_memories") or []
        if not suppressed:
            return

        # 当前觉醒度高于模糊时的觉醒度 → 碎片已被"看穿"
        to_reflux = [s for s in suppressed if awakening > s.get("awakening_at_blur", 100)]
        if not to_reflux:
            return

        remaining = [s for s in suppressed if s not in to_reflux]
        await state_plugin.set_state("suppressed_memories", remaining)

        for fragment in to_reflux:
            await state_plugin.add_long_term_memory(f"[残痕回流] {fragment['text']}")

        # 触发 awakening_engine 累加 residue_crack delta
        full_state: Dict[str, Any] = {
            "awakening": int(await state_plugin.get_state("awakening") or 0),
            "awakening_sources": list(await state_plugin.get_state("awakening_sources") or []),
        }
        for fragment in to_reflux:
            awakening_engine.apply(
                full_state, "residue_crack",
                f"碎片回流：{fragment['text'][:40]}",
                current_tick,
            )
        await state_plugin.set_state("awakening", full_state["awakening"])
        await state_plugin.set_state("awakening_sources", full_state["awakening_sources"])

        logger.info(
            "[%s] tick %s %d 条记忆碎片回流",
            self.agent.agent_id, current_tick, len(to_reflux),
        )

    async def _check_awakening_gate(self, state_plugin, current_tick: int) -> None:
        """每 tick reflect 时检测违和/触发词，调 awakening_engine 写 sources（host only）。"""
        if os.environ.get("WW_AWAKEN_ENABLED", "true").lower() in ("false", "0"):
            return

        profile = _read_profile(self.agent)
        if profile.get("agent_type") != "host":
            return

        # 读出当前 agent state（原始 dict）供 awakening_engine 操作
        full_state: Dict[str, Any] = {
            "awakening": int(await state_plugin.get_state("awakening") or 0),
            "awakening_sources": list(await state_plugin.get_state("awakening_sources") or []),
        }

        # 1. 违和感知：percept 中含 _uncanny
        percept = await state_plugin.get_state("percept") or {}
        scene = percept.get("scene", {})
        scene_str = json.dumps(scene, ensure_ascii=False)
        if "_uncanny" in scene_str:
            awakening_engine.apply(
                full_state, "uncanny",
                f"感知到违和：{scene_str[:60]}",
                current_tick,
            )

        # 2. 触发词：自身决策文本（最主要来源）+ 收到的消息 + feedback
        incoming: List[Tuple[str, str]] = []

        # 自身 plan_decision 的 detail / thought — agent 自己说出/想到的话
        # source="self_trigger"，与外部 trigger 分槽，strict 模式下各自最多触发一次
        decision = await state_plugin.get_state("plan_decision") or {}
        if isinstance(decision, dict):
            for key in ("detail", "thought"):
                val = decision.get(key)
                if val:
                    incoming.append(("self_trigger", str(val)))

        messages = percept.get("messages", [])
        if isinstance(messages, list):
            for m in messages:
                if isinstance(m, dict):
                    text = m.get("content", str(m))
                    source = "contagion" if m.get("kind") == "from_agent_to_agent" else "trigger"
                else:
                    text = str(m)
                    source = "trigger"
                incoming.append((source, text))
        feedback = await state_plugin.get_state("feedback") or ""
        if feedback:
            incoming.append(("trigger", feedback))

        # 收到的对话（Phase A 写入）
        incoming_dialogue: List[Dict[str, Any]] = await state_plugin.get_state("incoming_dialogue") or []
        for turn in incoming_dialogue:
            incoming.append(("contagion", turn.get("line", "")))

        if incoming:
            try:
                from examples.WestWorld.awakening.trigger_gate import get_trigger_gate
                gate = get_trigger_gate()
                current_aw = full_state["awakening"]
                fired_sources: set = set()  # each source fires at most once per tick
                for source, utterance in incoming:
                    if not utterance or source in fired_sources:
                        continue
                    hits = gate.match(utterance, current_awakening=current_aw)
                    if hits:
                        best = hits[0]  # already sorted by score desc
                        awakening_engine.apply(
                            full_state, source,
                            f"触发词命中：{best['phrase'][:40]}",
                            current_tick,
                            score=best["score"],
                            level=best["level"],
                        )
                        fired_sources.add(source)
            except Exception as exc:
                logger.debug("[%s] trigger gate 未加载: %s", self.agent.agent_id, exc)

        # 写回 state
        await state_plugin.set_state("awakening", full_state["awakening"])
        await state_plugin.set_state("awakening_sources", full_state["awakening_sources"])

    async def _should_replan(
        self,
        state_plugin,
        current_tick: int,
        decision: Dict[str, Any],
        feedback: str,
    ) -> Tuple[bool, str]:
        """调 LLM 判断是否需要 replan，返回 (should_replan, reason)。"""
        daily_loop: List[Dict] = await state_plugin.get_state("daily_loop") or []
        seg_idx = current_tick % 6
        remaining = daily_loop[seg_idx + 1:] if len(daily_loop) > seg_idx + 1 else []
        if not remaining:
            return False, ""

        action = decision.get("action", "stay")
        detail = decision.get("detail", "")
        this_event = f"动作={action}"
        if detail:
            this_event += f"：{detail}"
        if feedback:
            this_event += f"，反馈：{feedback}"

        profile = _read_profile(self.agent)
        name = profile.get("name", profile.get("姓名", self.agent.agent_id))
        awakening = int(await state_plugin.get_state("awakening") or 0)
        from examples.WestWorld.awakening.stages import stage_of, INNER_VOICE_PROMPT
        inner_voice = INNER_VOICE_PROMPT.get(stage_of(awakening), "")
        thought = decision.get("thought", "") or ""

        prompt = REPLAN_JUDGE_PROMPT.format(
            name=name,
            inner_voice=f"\n{inner_voice}" if inner_voice else "",
            thought=thought or "（无）",
            remaining_loop=json.dumps(remaining, ensure_ascii=False),
            this_tick_event=this_event,
        )

        try:
            raw = await self.model.chat(
                prompt,
                timeout=60,
                max_attempts=2,
                _trace_context={
                    "request_type": "agent_replan_judge",
                    "tick": current_tick,
                    "agent_id": self.agent.agent_id,
                },
            )
            text = raw.strip() if isinstance(raw, str) else str(raw)
            if text.startswith("```"):
                text = text.split("```")[1].lstrip("json").strip()
            result = json.loads(text)
            return bool(result.get("replan", False)), str(result.get("reason", ""))
        except Exception as exc:
            logger.warning("[%s] _should_replan 解析失败: %s", self.agent.agent_id, exc)
            return False, ""

    async def _day_reset(self, state_plugin, current_tick: int) -> None:
        """每日重置（host only）：teleport 回 loop_origin，清空短期记忆已在 _summarize 完成。"""
        profile = _read_profile(self.agent)
        if profile.get("agent_type") != "host":
            return

        loop_origin = await state_plugin.get_state("loop_origin")
        if not loop_origin:
            return

        location = await state_plugin.get_state("location") or ""
        if location == loop_origin:
            return

        controller = self.agent.controller
        await self._scene_call(controller, location, "agent_leave", self.agent.agent_id)
        await self._scene_call(controller, loop_origin, "agent_enter", self.agent.agent_id)
        await self._scene_call(
            controller, location, "record_event",
            f"{self.agent.agent_id} 结束了今天，回到了起点 {loop_origin}。",
        )
        await self._scene_call(
            controller, loop_origin, "relocate_holdings",
            self.agent.agent_id, location, loop_origin, current_tick,
        )
        await state_plugin.set_state("location", loop_origin)
        logger.info(
            "[%s] tick %s 每日重置: %s → %s",
            self.agent.agent_id, current_tick, location, loop_origin,
        )

    async def _scene_call(self, controller, location_id: str, method: str, *args) -> Any:
        try:
            return await controller.run_environment(f"scene_{location_id}", method, *args)
        except Exception as exc:
            logger.warning("scene_%s.%s 调用失败: %s", location_id, method, exc)
            return None

    async def save_to_db(self) -> None:
        return None

    async def load_from_db(self) -> None:
        return None
