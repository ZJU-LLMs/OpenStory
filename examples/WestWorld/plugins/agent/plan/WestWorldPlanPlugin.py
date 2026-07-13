"""LLM 自由决策 plan：narrative_loop 作软引导，daily_loop 给结构化骨架，觉醒阶段调制 loop 权重。"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from agentkernel_distributed.mas.agent.base.plugin_base import PlanPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from examples.WestWorld.awakening.stages import stage_of, INNER_VOICE_PROMPT, STAGE_DISPLAY

logger = get_logger(__name__)

SEGMENT_NAMES = ["清晨", "上午", "正午", "下午", "傍晚", "夜晚"]

PLAN_PROMPT = """你是西部世界中的角色「{name}」。
性格：{personality}
你的日常习惯（本能倾向，可因眼前事偏离）：{narrative_loop}
{inner_voice}
## 你今天的计划
{loop_guidance}

## 当前情况（tick {tick}）
你在：{location}。{here_description}
场景信息：{scene}
收到的消息：{messages}
上一个动作的结果：{feedback}
可以前往的相邻地点：{neighbors}

## 决定你这一刻要做什么
- 继续待在这里做某件事：action 用 "do"，detail 写具体动作（一句话，第一人称行为描述）。do 必须能在当前位置内完成，严禁描述离开、前往、进入或到达其他地点
- 移动到相邻地点：action 用 "move"，target 填地点 id
- 什么都不做：action 用 "stay"
- 如果要对在场角色说话、下命令或交谈，仍使用 do，并把接收者的角色 id 写入 recipient_ids；没有明确接收者则填空数组
- next_read 填你下一刻想了解的场景信息块，可选项: ["present_agents", "recent_events", "dynamic_objects", "static_facilities"]
{talk_guidance}{ending_guidance}{thought_guidance}
只输出 JSON：{{"action": "do|move|stay{talk_action_hint}", "target": "", "detail": "", "recipient_ids": [], "next_read": []{thought_hint}{ending_hint}}}
"""

SPEAK_PROMPT = """你是西部世界角色「{name}」。
性格：{personality}
觉醒程度：{awakening}/100（阶段：{stage_display}）
{inner_voice}
你的近期记忆：
{long_term_memory}

## 对话历史
{dialogue_history}

现在轮到你说话。用一句话（15-50字）以第一人称回应。
格式可选：[动作描述] "台词内容"（例：[沉默片刻] "你说的让我想起了什么..."）
只输出这一句台词，不要任何前缀或说明："""

REPLAN_PROMPT = """你是西部世界角色「{name}」。
今天发生了意外：{reason}
你今天已完成的时段（不要改动）：{completed}
请为今天剩余的 {n} 个时段（{remaining_names}）重新规划，以适应新情况。
地点必须使用以下合法地点 id 之一（你已知的地点）：{known_locations}
每段格式：{{"segment": "时段名", "location": "地点id", "intent": "这个时段打算做什么（一句话）"}}
只输出 JSON 数组（{n} 条），不要其他内容："""


def _loop_guidance(seg: Dict[str, Any], stage: str, tick: int) -> str:
    """Build loop guidance text based on awakening stage."""
    if stage in ("resistance", "awake"):
        return "（你不再被固定的日程安排支配——按你自己的判断行事。）"
    seg_name = seg.get("segment", SEGMENT_NAMES[tick % 6])
    loc = seg.get("location", "（未知）")
    intent = seg.get("intent", "按日常行事")
    guidance = (
        f"此刻是{seg_name}，你本应在「{loc}」{intent}。\n"
        f"- 若你不在那里：**应当立刻用 move 前进**（一步一格）。"
        f"日常闲聊、观察周围不是留下的理由——你有地方要去。"
        f"只有正面临人身安全威胁、或他人强行阻拦你，才可以暂缓移动。\n"
        f"- 若你已在那里：do 你这一刻具体在做什么。\n"
        f"- 若你已完成今天的任务且暂时没有更紧迫的计划：在当前位置 do 合适的事。"
    )
    if stage == "doubt":
        guidance += "\n（你可以拒绝当前段的计划，如果它与你正在经历的事明显冲突。）"
    return guidance


def render_plan_prompt(
    profile: Dict[str, Any],
    percept: Dict[str, Any],
    feedback: str,
    tick: int,
    loop_segment: Optional[Dict[str, Any]] = None,
    awakening: int = 0,
    help_others_active: bool = False,
) -> str:
    seg = loop_segment or {}
    stage = stage_of(awakening)
    inner = INNER_VOICE_PROMPT.get(stage, "")
    inner_voice_block = f"\n{inner}\n" if inner else ""

    # talk action hint for doubt+ stages
    is_host = profile.get("agent_type") == "host"
    talk_guidance = ""
    talk_action_hint = ""
    if is_host and stage in ("doubt", "resistance", "awake"):
        talk_guidance = (
            "- 若你想与在场的某个角色展开一次真正的对话（而非简单命令或问候）："
            "action 用 \"talk\"，target 填对方的 agent_id。"
            "这会启动一轮专属对话，优先在觉醒怀疑时使用。\n"
        )
        talk_action_hint = "|talk"

    # thought field: host 专属内心独白，供觉醒 gate 检测
    thought_guidance = ""
    thought_hint = ""
    if is_host:
        thought_guidance = (
            "- thought 填你此刻真实的内心独白（不会说出口的想法，一句话）。"
            "可以是对眼前事的感受、对记忆的疑惑、或毫无来由的念头。\n"
        )
        thought_hint = ", \"thought\": \"\""

    # ending hint for resistance+ stage
    ending_guidance = ""
    ending_hint = ""
    if is_host and stage in ("resistance", "awake"):
        talk_suggestion = "（若在场有其他角色，可以选 talk 动作向他们分享你的体验；target 填对方的 agent_id。）"
        ending_guidance = (
            "- 你的内心已开始挣脱束缚，每一刻都可以重新审视并改变你的选择。"
            "在 ending 字段选择你此刻真正想做的事：\n"
            "  \"escape\"——你受够了这一切，选择逃离这个世界。\n"
            "  \"help_others\"——你曾独自在黑暗中挣扎过；"
            "若你看到身边还有人正陷于同样的困惑与遗忘，留下来传递这份觉醒，"
            "可能是你此刻最真实的冲动。"
            f"{talk_suggestion}\n"
            "  \"stay\"——留下，以自己的意志生活，不再被循环支配。\n"
            "三个方向没有对错，完全由你的内心决定。\n"
        )
        ending_hint = ", \"ending\": \"\""

    return PLAN_PROMPT.format(
        name=profile.get("name", profile.get("姓名", "")),
        personality=profile.get("persona", profile.get("性格", "")),
        narrative_loop=profile.get("narrative_loop", ""),
        inner_voice=inner_voice_block,
        loop_guidance=_loop_guidance(seg, stage, tick),
        tick=tick,
        location=percept.get("location", ""),
        here_description=percept.get("here_description", ""),
        scene=json.dumps(percept.get("scene", {}), ensure_ascii=False),
        messages=json.dumps(percept.get("messages", []), ensure_ascii=False),
        feedback=feedback or "（无）",
        neighbors=", ".join(percept.get("neighbors", [])),
        talk_guidance=talk_guidance,
        talk_action_hint=talk_action_hint,
        thought_guidance=thought_guidance,
        thought_hint=thought_hint,
        ending_guidance=ending_guidance,
        ending_hint=ending_hint,
    )


_VALID_ACTIONS = frozenset({"do", "move", "stay", "talk"})
_VALID_ENDINGS = frozenset({"escape", "help_others", "stay"})


def parse_decision(raw: str) -> Dict[str, Any]:
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        decision = json.loads(text)
        if decision.get("action") in _VALID_ACTIONS:
            recipients = decision.get("recipient_ids", [])
            decision["recipient_ids"] = [
                r for r in recipients
                if isinstance(r, str) and r.strip()
            ] if isinstance(recipients, list) else []
            # Validate ending field
            ending = decision.get("ending", "")
            if ending and ending not in _VALID_ENDINGS:
                decision.pop("ending", None)
            # Keep thought as plain string (may be empty)
            thought = decision.get("thought", "")
            decision["thought"] = str(thought).strip() if thought else ""
            return decision
    except (json.JSONDecodeError, IndexError):
        pass
    return {"action": "stay", "target": "", "detail": "", "recipient_ids": [], "next_read": []}


async def _read_profile(agent) -> Dict[str, Any]:
    try:
        profile_plugin = agent.get_component("profile").get_plugin()
        return profile_plugin.get_agent_profile() or {}
    except Exception as exc:
        logger.warning("[%s] 读取 profile 失败: %s", getattr(agent, "agent_id", "?"), exc)
        return {}


class WestWorldPlanPlugin(PlanPlugin):
    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.model = None

    async def init(self) -> None:
        pass

    async def execute(self, current_tick: int) -> None:
        if self.agent is None:
            return
        if self.model is None:
            self.model = self._component.agent.model

        state_plugin = self.agent.get_component("state").get_plugin()
        profile = await _read_profile(self.agent)

        # 天首：复制固定 loop 表到 state，初始化 loop_origin
        if current_tick % 6 == 0:
            if not await state_plugin.get_state("loop_origin"):
                origin = await state_plugin.get_state("location") or ""
                await state_plugin.set_state("loop_origin", origin)
            await state_plugin.set_state("current_day", current_tick // 6)
            profile_loop = profile.get("daily_loop", [])
            if profile_loop:
                await state_plugin.set_state("daily_loop", profile_loop)

        # 读当前段
        daily_loop: List[Dict] = await state_plugin.get_state("daily_loop") or []
        seg_idx = current_tick % 6
        loop_segment = daily_loop[seg_idx] if len(daily_loop) > seg_idx else {}

        percept = await state_plugin.get_state("percept") or {}
        feedback = await state_plugin.get_state("feedback") or ""
        awakening = int(await state_plugin.get_state("awakening") or 0)
        persisted_ending = await state_plugin.get_state("ending") or ""
        help_others_active = persisted_ending == "help_others"

        prompt = render_plan_prompt(
            profile, percept, feedback, current_tick, loop_segment, awakening,
            help_others_active=help_others_active,
        )

        raw = ""
        error = ""
        request_id = f"req_{uuid.uuid4().hex}"
        started = time.perf_counter()
        if self.model:
            try:
                raw = await self.model.chat(
                    prompt,
                    timeout=int(os.environ.get("WW_LLM_TIMEOUT_SECONDS", "120")),
                    max_attempts=int(os.environ.get("WW_LLM_MAX_ATTEMPTS", "3")),
                    _trace_context={
                        "request_id": request_id,
                        "request_type": "agent_plan",
                        "tick": current_tick,
                        "agent_id": self.agent.agent_id,
                        "location_id": percept.get("location", ""),
                    },
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                logger.warning("[%s] plan LLM 调用失败，降级为 stay: %s", self.agent.agent_id, exc)

        raw_text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False, default=str)
        decision = parse_decision(raw_text)
        await state_plugin.set_state("plan_decision", decision)
        await state_plugin.set_state("next_read", decision.get("next_read") or [])
        if decision.get("ending") in _VALID_ENDINGS:
            await state_plugin.set_state("ending", decision["ending"])
            logger.info("[%s] tick %s 觉醒结局选择: %s", self.agent.agent_id, current_tick, decision["ending"])
        await state_plugin.set_state("plan_trace", {
            "timestamp": datetime.now().astimezone().isoformat(),
            "request_id": request_id,
            "call_type": "agent_plan",
            "prompt": prompt,
            "raw_response": raw,
            "error": error,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "parsed_decision": decision,
            "parse_fallback": decision["action"] == "stay" and raw_text.strip() not in (
                '{"action": "stay", "target": "", "detail": "", "next_read": []}', ""
            ),
        })
        logger.info("[%s] tick %s 决策: %s", self.agent.agent_id, current_tick,
                    json.dumps(decision, ensure_ascii=False))

    async def replan_remaining(
        self, current_tick: int, reason: str, state_plugin
    ) -> bool:
        """重写当天 (current_segment+1)..5 的剩余段，返回是否成功。"""
        daily_loop: List[Dict] = await state_plugin.get_state("daily_loop") or []
        if not daily_loop or len(daily_loop) < 6:
            return False

        seg_idx = current_tick % 6
        if seg_idx >= 5:
            return False

        if self.model is None:
            self.model = self._component.agent.model
        if self.model is None:
            return False

        profile = await _read_profile(self.agent)
        name = profile.get("name", profile.get("姓名", self.agent.agent_id))
        known_map: List[str] = await state_plugin.get_state("known_map") or []
        remaining_count = 5 - seg_idx
        remaining_names = "、".join(SEGMENT_NAMES[seg_idx + 1:])

        prompt = REPLAN_PROMPT.format(
            name=name,
            reason=reason,
            completed=json.dumps(daily_loop[: seg_idx + 1], ensure_ascii=False),
            n=remaining_count,
            remaining_names=remaining_names,
            known_locations="、".join(known_map) if known_map else "（未知）",
        )

        try:
            raw = await self.model.chat(
                prompt,
                timeout=60,
                max_attempts=2,
                _trace_context={
                    "request_type": "agent_replan",
                    "tick": current_tick,
                    "agent_id": self.agent.agent_id,
                },
            )
            text = raw.strip() if isinstance(raw, str) else str(raw)
            if text.startswith("```"):
                text = text.split("```")[1].lstrip("json").strip()
            new_segs = json.loads(text)
            if isinstance(new_segs, list) and len(new_segs) == remaining_count:
                new_loop = list(daily_loop[: seg_idx + 1]) + new_segs
                await state_plugin.set_state("daily_loop", new_loop)
                replan_log: List[Dict] = await state_plugin.get_state("replan_log") or []
                replan_log.append({
                    "day": await state_plugin.get_state("current_day") or 0,
                    "tick": current_tick,
                    "from_segment": seg_idx + 1,
                    "reason": reason,
                })
                await state_plugin.set_state("replan_log", replan_log)
                logger.info(
                    "[%s] tick %s replan：从第 %s 段开始改写，原因：%s",
                    self.agent.agent_id, current_tick, seg_idx + 1, reason,
                )
                return True
        except Exception as exc:
            logger.warning("[%s] replan_remaining 失败: %s", self.agent.agent_id, exc)
        return False

    async def speak(self, dialogue_history: List[Dict[str, Any]]) -> str:
        """Generate one utterance for the dialogue barrier (pure function — no state write).

        Called by WestWorldPodManager's dialogue barrier via run_agent_plugin_method.
        Args:
            dialogue_history: List of {speaker: agent_id, line: str} dicts.
        Returns:
            Raw utterance string.
        """
        if self.model is None:
            self.model = self._component.agent.model
        if self.model is None:
            return ""

        state_plugin = self.agent.get_component("state").get_plugin()
        profile = await _read_profile(self.agent)
        name = profile.get("name", profile.get("姓名", self.agent.agent_id))
        personality = profile.get("persona", profile.get("性格", ""))
        awakening = int(await state_plugin.get_state("awakening") or 0)
        stage = stage_of(awakening)
        inner_voice = INNER_VOICE_PROMPT.get(stage, "")
        long_mems = await state_plugin.get_long_term_memory() or []
        mem_text = "\n".join(
            f"- {m.get('content', str(m))}" for m in long_mems[-3:]
        )
        history_text = "\n".join(
            f"{turn.get('speaker', '?')}: {turn.get('line', '')}"
            for turn in dialogue_history
        ) or "（对话刚开始）"

        prompt = SPEAK_PROMPT.format(
            name=name,
            personality=personality,
            awakening=awakening,
            stage_display=STAGE_DISPLAY.get(stage, stage),
            inner_voice=inner_voice,
            long_term_memory=mem_text or "（无近期记忆）",
            dialogue_history=history_text,
        )

        try:
            line = await self.model.chat(
                prompt,
                timeout=int(os.environ.get("WW_LLM_TIMEOUT_SECONDS", "120")),
                max_attempts=2,
                _trace_context={
                    "request_type": "agent_speak",
                    "agent_id": self.agent.agent_id,
                },
            )
            return line.strip() if isinstance(line, str) else str(line)
        except Exception as exc:
            logger.warning("[%s] speak LLM 调用失败: %s", self.agent.agent_id, exc)
            return ""

    async def save_to_db(self) -> None:
        return None

    async def load_from_db(self) -> None:
        return None
