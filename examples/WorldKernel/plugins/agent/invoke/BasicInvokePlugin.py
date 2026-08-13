"""Invoke plugin: executes the current hour's plan."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

PROJECT_PATH = Path(__file__).resolve().parents[3]
if str(PROJECT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH))

from plugins._optional_deps import ensure_optional_agentkernel_imports

ensure_optional_agentkernel_imports()

from agentkernel_distributed.mas.agent.base.plugin_base import InvokePlugin
from agentkernel_distributed.toolkit.logger import get_logger

logger = get_logger(__name__)

_SOLO_TARGETS = {"自己", "无", "None", "", None, "鑷繁", "鏃?"}
_DIALOGUE_IMPORTANCE_THRESHOLD = 7
_MAX_DIALOGUE_TURNS = 6
_ALLOWED_AGENT_EFFECT_FIELDS = {"mood", "status", "active_goal"}


class BasicInvokePlugin(InvokePlugin):
    """Executes hourly plans, resolves movement, and records memory."""

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
        logger.info("[%s][N/A] BasicInvokePlugin initialization completed", self.agent_id)

    async def execute(self, current_tick: int) -> None:
        try:
            state_plugin = self._component.agent.get_component("state").get_plugin()
            profile_plugin = self._component.agent.get_component("profile").get_plugin()

            if not await state_plugin.is_active():
                return

            current_day = (current_tick // 12) + 1
            current_hour = current_tick % 12
            pending = await state_plugin.get_state("pending_user_action")
            if isinstance(pending, dict):
                current_plan = [
                    str(pending.get("action") or "").strip(),
                    current_hour,
                    pending.get("target") or "自己",
                    pending.get("location") or "",
                    10,
                ]
                await state_plugin.set_state("pending_user_action", None)
            else:
                hourly_plans = await state_plugin.get_hourly_plans(day=current_day)
                current_plan = self._select_current_plan(hourly_plans, current_hour)

            if not current_plan:
                event = self._make_event(
                    current_tick,
                    event_type="idle",
                    current_action="稍作休整",
                    summary=f"{self.agent_id} 暂时没有具体计划，停下手头事务整理思绪。",
                    lines=[f"旁白：[休整] {self.agent_id}停下手头事务，整理思绪。"],
                )
                await state_plugin.set_state("current_plan", None)
                await state_plugin.set_state("occupied_by", None)
                await self._record_event(state_plugin, current_tick, event)
                return

            await state_plugin.set_state("current_plan", current_plan)
            action, _time, target, location, importance = current_plan[:5]

            try:
                importance = int(importance)
            except (TypeError, ValueError):
                importance = 5

            if importance < _DIALOGUE_IMPORTANCE_THRESHOLD and target in _SOLO_TARGETS:
                await asyncio.sleep(2)

            occupation_info = await self._get_occupation(current_tick, self.agent_id)
            if occupation_info:
                occupier = occupation_info.get("occupier")
                occ_importance = occupation_info.get("importance", 0)
                if occupier != self.agent_id and occ_importance >= importance:
                    busy = f"正在配合 {occupier} 进行：{occupation_info.get('action', '某事')}。"
                    await state_plugin.set_state("occupied_by", occupation_info)
                    event = self._make_event(
                        current_tick,
                        event_type="interaction",
                        plan=action,
                        current_action=f"配合{occupier}处理事务",
                        summary=busy,
                        participants=[self.agent_id, occupier],
                        lines=[f"旁白：[协同行动] {busy}"],
                        location=location,
                        importance=occ_importance,
                    )
                    await self._record_event(state_plugin, current_tick, event)
                    return

            await state_plugin.set_state("occupied_by", None)
            if not await self._occupy(current_tick, importance, action, location):
                occupation_info = await self._get_occupation(current_tick, self.agent_id) or {}
                occupier = occupation_info.get("occupier") or "其他角色"
                busy = f"{self.agent_id}未能开始原计划，转而配合{occupier}处理已发生的事务。"
                await state_plugin.set_state("occupied_by", occupation_info or None)
                event = self._make_event(
                    current_tick,
                    event_type="blocked",
                    plan=action,
                    current_action=f"配合{occupier}处理事务",
                    summary=busy,
                    participants=[self.agent_id, occupier],
                    lines=[self._line("旁白", "占用冲突", busy, "narration")],
                    location=occupation_info.get("location") or location,
                    importance=occupation_info.get("importance", importance),
                )
                await self._record_event(state_plugin, current_tick, event)
                return

            moved, move_note = await self._try_move(location, current_tick)
            if not moved:
                note = move_note or f"无法进入计划地点：{location}"
                await state_plugin.set_state("current_plan_note", note)
                event = self._make_event(
                    current_tick,
                    event_type="blocked",
                    plan=action,
                    current_action="受阻并重新评估计划",
                    summary=f"{self.agent_id} 的行动未能开始：{note}",
                    participants=[self.agent_id],
                    lines=[f"旁白：[行动受阻] {self.agent_id}未能推进原计划。", f"{self.agent_id}：[停下] 得换一种办法。"],
                    location=location,
                    importance=importance,
                )
                await self._record_event(state_plugin, current_tick, event)
                await self._request_replan(current_tick, note)
                return

            await state_plugin.set_state("current_plan_note", None)
            self_profile = profile_plugin.get_agent_profile()
            target_profile = None
            plan_note = None
            target_participated = False

            if target not in _SOLO_TARGETS:
                target_profile = await profile_plugin.get_agent_profile_by_id(target)
                target_active = False
                if target_profile:
                    try:
                        target_active = bool(
                            await self.controller.run_agent_method(target, "state", "is_active")
                        )
                    except Exception:
                        target_active = False
                if not target_profile:
                    plan_note = f"{target}不存在，未能参与事件。"
                elif not target_active:
                    plan_note = f"{target}已经离场，未能参与事件。"
                elif not await self._try_occupy_target(current_tick, target, importance, action):
                    plan_note = f"{target}当前被其他事件占用，未能参与。"
                else:
                    target_moved, target_move_note = await self._try_move_agent(
                        target, location, current_tick
                    )
                    if target_moved:
                        target_participated = True
                    else:
                        plan_note = f"{target}无法到达事件地点：{target_move_note or '路径或访问条件不满足'}"
                if plan_note:
                    await state_plugin.set_state("current_plan_note", plan_note)

            location_profile = await self._get_location_profile(location)
            relation = await self._get_relation(target)

            if target_participated:
                event = await self._generate_interaction_event(
                    current_tick,
                    action,
                    target,
                    location,
                    importance,
                    self_profile,
                    target_profile or {},
                    location_profile,
                    relation,
                )
            elif importance >= _DIALOGUE_IMPORTANCE_THRESHOLD:
                event = await self._generate_execution_event(
                    current_tick,
                    action,
                    target,
                    location,
                    importance,
                    self_profile,
                    target_profile,
                    plan_note,
                    location_profile,
                    relation,
                )
            else:
                event = self._simple_event(
                    current_tick,
                    self_profile,
                    action,
                    target,
                    location,
                    importance,
                    plan_note,
                )

            event["effect_results"] = await self._apply_effects(event)
            await self._record_event(state_plugin, current_tick, event)

            if target_participated:
                await self._propagate_to_target(
                    target, current_tick, action, _time, location, importance, event
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s][%s] Error executing InvokePlugin: %s", self.agent_id, current_tick, exc)
            try:
                state_plugin = self._component.agent.get_component("state").get_plugin()
                event = self._make_event(
                    current_tick,
                    event_type="blocked",
                    current_action="暂停并检查行动条件",
                    summary=f"{self.agent_id}的行动因运行时异常未能继续，系统已保留失败记录。",
                    participants=[self.agent_id],
                    lines=[self._line("旁白", "执行异常", "行动未能继续，等待下一次重新评估。", "narration")],
                )
                await self._record_event(state_plugin, current_tick, event)
            except Exception:  # noqa: BLE001
                logger.exception("[%s][%s] Failed to record invoke error event", self.agent_id, current_tick)

    @staticmethod
    def _select_current_plan(hourly_plans: Any, current_hour: int) -> list[Any] | None:
        if isinstance(hourly_plans, dict):
            if hourly_plans and all(isinstance(v, list) for v in hourly_plans.values()):
                flattened = []
                for value in hourly_plans.values():
                    flattened.extend(value if value and isinstance(value[0], list) else [value])
                hourly_plans = flattened
        if not isinstance(hourly_plans, list):
            return None
        for plan in hourly_plans:
            if isinstance(plan, list) and len(plan) >= 5 and plan[1] == current_hour:
                return plan
        return None

    async def _try_move(self, location: str, current_tick: int) -> tuple[bool, str | None]:
        return await self._try_move_agent(self.agent_id, location, current_tick)

    async def _try_move_agent(
        self, agent_id: str, location: str, current_tick: int
    ) -> tuple[bool, str | None]:
        if not self.controller or not location:
            return (True, None)
        try:
            result = await self.controller.run_action(
                "move", "move_to", agent_id=agent_id, location=location
            )
            if hasattr(result, "is_successful") and not result.is_successful():
                return (False, getattr(result, "message", "move failed"))
            if isinstance(result, dict) and result.get("status") == "error":
                return (False, str(result.get("message") or "move failed"))
            return (True, None)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s][%s] move_to failed for %s: %s", self.agent_id, current_tick, agent_id, exc)
            return (False, str(exc))

    async def _request_replan(self, current_tick: int, reason: str) -> None:
        try:
            state = self._component.agent.get_component("state").get_plugin()
            if await state.get_state("replanned_tick") == current_tick:
                return
            profile = self._component.agent.get_component("profile").get_plugin().get_agent_profile()
            long_task = await state.get_long_task()
            plan_component = self._component.agent.get_component("plan")
            if not plan_component:
                return
            await plan_component.get_plugin().replan_remaining_plans(
                agent_id=self.agent_id,
                current_tick=current_tick,
                profile=profile,
                long_task=long_task,
                start_hour=(current_tick % 12) + 1,
            )
            await state.add_replan_event(
                tick=current_tick,
                reason=reason,
                day=(current_tick // 12) + 1,
                from_hour=(current_tick % 12) + 1,
            )
            await state.set_state("replanned_tick", current_tick)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s][%s] replan request failed: %s", self.agent_id, current_tick, exc)

    async def _get_location_profile(self, location: str) -> dict[str, Any] | None:
        if not self.controller or not location:
            return None
        try:
            return await self.controller.run_environment("space", "get_location_profile", location)
        except Exception:
            return None

    async def _get_relation(self, target: str) -> dict[str, Any] | None:
        if not self.controller or target in _SOLO_TARGETS:
            return None
        try:
            return await self.controller.run_environment("relation", "get_relation_between", self.agent_id, target)
        except Exception:
            return None

    def _simple_event(
        self,
        current_tick: int,
        profile: dict[str, Any],
        action: str,
        target: str,
        location: str,
        importance: int,
        plan_note: str | None,
    ) -> dict[str, Any]:
        name = profile.get("name") or profile.get("id") or self.agent_id
        participants = [self.agent_id]
        if target not in _SOLO_TARGETS and not plan_note:
            participants.append(target)
        current_action = self._strip_location_from_action(f"着手{action}", location)
        if plan_note:
            summary = f"{name}开始推进“{action}”，但{plan_note.rstrip('。')}，只能先处理能够独立完成的部分。"
        else:
            summary = f"{name}开始推进“{action}”，完成了这一时段内可落实的步骤，事情仍将继续发展。"
        return self._make_event(
            current_tick,
            event_type="interaction" if len(participants) > 1 else "action",
            plan=action,
            current_action=current_action,
            current_actions={self.agent_id: current_action},
            summary=summary,
            participants=participants,
            absent_participants=[target] if target not in _SOLO_TARGETS and plan_note else [],
            lines=[f"旁白：[行动] {summary}"],
            location=location,
            importance=importance,
        )

    async def _get_occupation(self, tick: int, target_id: str) -> dict | None:
        if not self.redis:
            return None
        try:
            data = await self.redis.get(f"occupation:{tick}:{target_id}")
            if isinstance(data, str):
                data = json.loads(data)
            return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s][%s] get_occupation failed: %s", self.agent_id, tick, exc)
            return None

    async def _occupy(self, tick: int, importance: int, action: str, location: str = "") -> bool:
        if not self.redis:
            return True
        try:
            key = f"occupation:{tick}:{self.agent_id}"
            existing = await self.redis.get(key)
            if existing:
                if isinstance(existing, str):
                    existing = json.loads(existing)
                if existing.get("occupier") != self.agent_id and existing.get("importance", 0) >= importance:
                    return False
            await self.redis.set(
                key,
                json.dumps(
                    {"occupier": self.agent_id, "importance": importance, "action": action, "location": location},
                    ensure_ascii=False,
                ),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s][%s] occupy failed: %s", self.agent_id, tick, exc)
            return False

    async def _try_occupy_target(self, tick: int, target_id: str, my_importance: int, action: str) -> bool:
        if not self.redis:
            return True
        try:
            key = f"occupation:{tick}:{target_id}"
            occ = await self._get_occupation(tick, target_id)
            if not occ:
                await self.redis.set(
                    key,
                    json.dumps({"occupier": self.agent_id, "importance": my_importance, "action": action}, ensure_ascii=False),
                )
                return True
            occupier = occ.get("occupier")
            occ_importance = occ.get("importance", 0)
            if occupier == self.agent_id:
                return True
            if my_importance > occ_importance:
                await self.redis.set(
                    key,
                    json.dumps({"occupier": self.agent_id, "importance": my_importance, "action": action}, ensure_ascii=False),
                )
                return True
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s][%s] try_occupy_target failed: %s", self.agent_id, tick, exc)
            return False

    async def _get_agent_memory(self, agent_id: str) -> str:
        if not self.controller:
            return "无记忆"
        try:
            short_memory = await self.controller.run_agent_method(agent_id, "state", "get_short_term_memory")
            long_memory = await self.controller.run_agent_method(agent_id, "state", "get_long_term_memory")
            text = ""
            if long_memory:
                text += "[长期记忆]\n" + "\n".join(f"- {m['content']}" for m in long_memory) + "\n\n"
            if short_memory:
                text += "[近期记忆]\n" + "\n".join(f"- {m.get('content', m)}" for m in short_memory[-5:])
            return text.strip() or "无记忆"
        except Exception:
            return "无记忆"

    async def _generate_interaction_event(
        self,
        current_tick: int,
        action: str,
        target: str,
        location: str,
        importance: int,
        self_profile: Dict[str, Any],
        target_profile: Dict[str, Any],
        location_profile: Dict[str, Any] | None,
        relation: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        participants = [self.agent_id, target]
        profiles = {self.agent_id: self_profile, target: target_profile}
        lines: list[dict[str, str]] = []
        current_actions: dict[str, str] = {}

        if self.model:
            for turn in range(_MAX_DIALOGUE_TURNS):
                speaker_id = participants[turn % len(participants)]
                profile = profiles.get(speaker_id) or {}
                speaker_name = profile.get("name") or profile.get("id") or speaker_id
                previous = "\n".join(
                    f"{line['speaker']}：[{line['action']}]{line['text']}"
                    for line in lines
                ) or "（事件刚开始）"
                prompt = f"""你正在通用模拟世界中扮演角色“{speaker_name}”。请只决定这个角色此刻的一个动作和一句话。

计划意图：{action}
事件地点：{json.dumps(location_profile or {'id': location}, ensure_ascii=False)[:1400]}
事件重要度：{importance}/10
角色档案：{json.dumps(profile, ensure_ascii=False)[:2200]}
角色记忆：{await self._get_agent_memory(speaker_id)}
与对方关系：{json.dumps(relation or {}, ensure_ascii=False)[:1000]}
已有对话：
{previous}

返回严格 JSON：{{"action":"可观察动作，2-20字","text":"符合角色身份与当前世界的台词","continue":true}}
约束：
1. 只扮演当前角色，不替其他角色发言或决定反应。
2. 计划只是意图，允许质疑、拒绝、误解、冲突或产生新信息。
3. 只服从当前动态世界背景，不得引入未提供的外部叙事设定或时代规则。
4. 不在动作或台词中编造角色移动；角色位置已由系统校验。
5. 若认为双方各自已经至少回应一次且事件可结束，将 continue 设为 false。
6. 只输出 JSON。"""
                try:
                    turn_data = self._parse_event_json(str(await self.model.chat(prompt) or ""))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[%s][%s] dialogue turn %s failed: %s",
                        self.agent_id,
                        current_tick,
                        turn + 1,
                        exc,
                    )
                    break
                action_text = self._strip_location_from_action(
                    str(turn_data.get("action") or "回应对方"), location
                )
                line_text = str(turn_data.get("text") or "……").replace("[END]", "").strip()
                lines.append(self._line(speaker_id, action_text, line_text, "dialogue"))
                current_actions[speaker_id] = action_text
                if len(lines) >= len(participants) and turn_data.get("continue") is False:
                    break

        if not lines:
            lines = [
                self._line(self.agent_id, "说明来意", f"我想谈谈{action}。"),
                self._line(target, "作出回应", "我听到了，我们把事情说清楚。"),
            ]
            current_actions = {self.agent_id: "说明来意", target: "作出回应"}

        default_summary = f"{self.agent_id}与{target}围绕“{action}”进行了交谈，双方都作出了回应。"
        summary = default_summary
        effects: list[dict[str, Any]] = []
        if self.model:
            resolver_prompt = f"""你是 WorldKernel 的通用事件解析器。根据已真实发生的逐角色对话，生成事件结果和受控状态效果。

世界背景：{self._world_context()}
计划意图：{action}
参与者：{json.dumps(participants, ensure_ascii=False)}
地点：{json.dumps(location_profile or {'id': location}, ensure_ascii=False)[:1600]}
对话：{json.dumps(lines, ensure_ascii=False)}

返回严格 JSON：
{{
  "event_summary":"40-120字的实际过程、结果或新信息",
  "current_actions":{{"角色ID":"不含地点描述的具体动作"}},
  "effects":[
    {{"type":"agent_state","target":"参与者ID","field":"mood|status|active_goal","value":"新值","reason":"因果"}},
    {{"type":"relation_delta","source":"参与者ID","target":"参与者ID","delta":-10,"reason":"因果"}},
    {{"type":"activity","target":"参与者ID","is_active":false,"reason":"明确不可逆离场原因"}}
  ]
}}

约束：
1. 只总结对话中有依据的结果；计划不等于成功。
2. effects 没有充分依据时返回空数组，关系 delta 必须在 -100 到 100。
3. activity=false 仅用于对话明确发生死亡、永久离开或其他不可逆离场。
4. 禁止修改位置、路径、访问条件、资源或任意未列出的字段。
5. 只使用当前世界上下文，只输出 JSON。"""
            try:
                resolved = self._parse_event_json(str(await self.model.chat(resolver_prompt) or ""))
                summary = str(resolved.get("event_summary") or resolved.get("summary") or summary).strip()
                raw_actions = resolved.get("current_actions")
                if isinstance(raw_actions, dict):
                    for actor, actor_action in raw_actions.items():
                        if actor in participants:
                            current_actions[actor] = self._strip_location_from_action(
                                str(actor_action), location
                            )
                if isinstance(resolved.get("effects"), list):
                    effects = [item for item in resolved["effects"] if isinstance(item, dict)]
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%s][%s] interaction resolution failed: %s", self.agent_id, current_tick, exc)

        return self._make_event(
            current_tick,
            event_type="interaction",
            plan=action,
            current_action=current_actions.get(self.agent_id, "参与交谈"),
            current_actions=current_actions,
            summary=summary,
            participants=participants,
            lines=lines,
            location=location_profile or location,
            importance=importance,
            effects=effects,
        )

    @staticmethod
    def _world_context() -> str:
        try:
            from plugins.agent.plan.BasicPlanPlugin import BasicPlanPlugin

            return BasicPlanPlugin._world_context
        except Exception:
            return "一个开放的模拟世界"

    async def _generate_execution_event(
        self,
        current_tick: int,
        action: str,
        target: str,
        location: str,
        importance: int,
        self_profile: Dict[str, Any],
        target_profile: Dict[str, Any] | None,
        plan_note: str | None,
        location_profile: Dict[str, Any] | None,
        relation: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        default = self._simple_event(
            current_tick,
            self_profile,
            action,
            target,
            location,
            importance,
            plan_note,
        )
        if not self.model:
            return default

        participants = [self.agent_id]
        absent = []
        if target not in _SOLO_TARGETS:
            (absent if plan_note else participants).append(target)

        world_context = self._world_context()

        loc_context = json.dumps(location_profile or {}, ensure_ascii=False)[:1600]
        relation_context = json.dumps(relation or {}, ensure_ascii=False)[:1000]
        participant_profiles = [self_profile]
        if target_profile:
            participant_profiles.append(target_profile)
        profile_context = json.dumps(participant_profiles, ensure_ascii=False)[:3000]
        memory_parts = []
        for participant in participants:
            memory_parts.append(f"【{participant}的记忆】\n{await self._get_agent_memory(participant)}")

        prompt = f"""你是 WorldKernel 的通用事件推演器。请把角色的“计划意图”演化为这个时段实际发生的事件。

【世界背景】
{world_context}

【计划意图】
{action}

【参与者】
{json.dumps(participants, ensure_ascii=False)}

【未能参与者】
{json.dumps(absent, ensure_ascii=False)}

【角色档案】
{profile_context}

【关系】
{relation_context}

【地点（仅用于约束事件合理性）】
{location}
{loc_context}

【相关记忆】
{chr(10).join(memory_parts)}

返回严格 JSON 对象：
{{
  "current_action": "角色此刻具体、可观察的动作，10-35字",
  "event_summary": "本时段实际发生的过程、结果或新信息，40-120字",
  "lines": [{{"speaker":"角色ID或旁白","action":"动作","text":"台词或客观变化","kind":"dialogue或narration"}}],
  "effects": [
    {{"type":"agent_state","target":"参与者ID","field":"mood|status|active_goal","value":"新值","reason":"因果"}},
    {{"type":"activity","target":"参与者ID","is_active":false,"reason":"明确不可逆离场原因"}}
  ]
}}

约束：
1. 计划是意图，不是既成事实；必须推演出具体过程、阻力、结果或新信息，不能复述计划。
2. current_action 只写动作，不写地点介绍、环境氛围，不使用“正在某地执行……”句式。
3. lines 为 1-8 个结构化记录；独自行动可使用旁白并保留角色反应。
4. 所有内容必须服从上面的当前世界设定，不得引入未提供的外部叙事背景。
5. 不凭空保证计划成功；activity=false 只允许用于有充分因果的死亡、永久离开或不可逆离场。
6. effects 不得修改位置、路径、访问条件、资源或未列出的字段；没有依据就返回空数组。
7. 只输出 JSON，不要 Markdown。
"""
        try:
            response = str(await self.model.chat(prompt) or "").strip()
            resolved = self._parse_event_json(response)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s][%s] event generation failed: %s", self.agent_id, current_tick, exc)
            return default

        current_action = self._strip_location_from_action(
            str(resolved.get("current_action") or default["current_action"]).strip(),
            location,
        )
        summary = str(resolved.get("event_summary") or resolved.get("summary") or default["summary"]).strip()
        raw_lines = resolved.get("lines", [])
        if not isinstance(raw_lines, list):
            raw_lines = [raw_lines]
        lines = [self._normalize_line(line) for line in raw_lines if str(line).strip()]
        if not lines:
            lines = [self._line("旁白", "事件", summary, "narration")]
        effects = resolved.get("effects") if isinstance(resolved.get("effects"), list) else []
        return self._make_event(
            current_tick,
            event_type="interaction" if len(participants) > 1 else "action",
            plan=action,
            current_action=current_action or default["current_action"],
            current_actions={self.agent_id: current_action or default["current_action"]},
            summary=summary,
            participants=participants,
            absent_participants=absent,
            lines=lines[:8],
            location=location_profile or location,
            importance=importance,
            effects=[item for item in effects if isinstance(item, dict)],
        )

    @staticmethod
    def _parse_event_json(response: str) -> dict[str, Any]:
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        start = text.find("{")
        end = text.rfind("}") + 1
        payload = text[start:end] if start >= 0 and end > start else text
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _strip_location_from_action(current_action: str, location: str) -> str:
        text = " ".join(str(current_action or "").split()).strip("。；; ")
        if location:
            text = text.replace(str(location), "")
        text = text.replace("正在执行：", "").replace("正在执行", "").strip(" ，,：:。")
        return text[:60]

    @staticmethod
    def _line(
        speaker: Any,
        action: Any,
        text: Any,
        kind: str = "dialogue",
    ) -> dict[str, str]:
        return {
            "speaker": str(speaker or "旁白"),
            "action": str(action or "事件").replace("[END]", "").strip()[:40],
            "text": str(text or "").replace("[END]", "").strip()[:500],
            "kind": "narration" if kind == "narration" else "dialogue",
        }

    @classmethod
    def _normalize_line(cls, line: Any) -> dict[str, str]:
        if isinstance(line, dict):
            return cls._line(
                line.get("speaker"),
                line.get("action"),
                line.get("text"),
                str(line.get("kind") or "dialogue"),
            )
        raw = str(line or "").replace("[END]", "").strip()
        speaker, action, text = "旁白", "事件", raw
        if "：" in raw:
            speaker, remainder = raw.split("：", 1)
            text = remainder
        if text.startswith("[") and "]" in text:
            action, text = text[1:].split("]", 1)
        return cls._line(speaker, action, text, "narration" if speaker == "旁白" else "dialogue")

    @classmethod
    def _legacy_lines(cls, lines: list[Any]) -> list[str]:
        normalized = [cls._normalize_line(line) for line in lines]
        return [f"{line['speaker']}：[{line['action']}]{line['text']}" for line in normalized]

    @staticmethod
    def _make_event(
        tick: int,
        *,
        event_type: str,
        current_action: str,
        summary: str,
        plan: str = "",
        participants: list[Any] | None = None,
        absent_participants: list[Any] | None = None,
        current_actions: dict[str, Any] | None = None,
        lines: list[Any] | None = None,
        location: Any = "",
        importance: int = 0,
        effects: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        participant_ids = [str(item) for item in (participants or []) if item]
        location_payload = (
            {
                "id": str(location.get("id") or location.get("location_id") or ""),
                "name": str(location.get("name") or location.get("location") or ""),
            }
            if isinstance(location, dict)
            else {"id": str(location or ""), "name": str(location or "")}
        )
        action_map = {
            str(actor): BasicInvokePlugin._strip_location_from_action(
                BasicInvokePlugin._strip_location_from_action(
                    str(value), str(location_payload.get("id") or "")
                ),
                str(location_payload.get("name") or ""),
            )
            for actor, value in (current_actions or {}).items()
            if actor and value
        }
        cleaned_current_action = BasicInvokePlugin._strip_location_from_action(
            BasicInvokePlugin._strip_location_from_action(
                current_action, str(location_payload.get("id") or "")
            ),
            str(location_payload.get("name") or ""),
        )
        if participant_ids and participant_ids[0] not in action_map:
            action_map[participant_ids[0]] = cleaned_current_action
        return {
            "event_id": uuid.uuid4().hex,
            "tick": int(tick),
            "type": event_type,
            "initiator": participant_ids[0] if participant_ids else "",
            "plan": plan,
            "current_action": cleaned_current_action,
            "current_actions": action_map,
            "summary": summary,
            "participants": participant_ids,
            "absent_participants": [str(item) for item in (absent_participants or []) if item],
            "lines": [BasicInvokePlugin._normalize_line(line) for line in (lines or []) if line],
            "location": location_payload,
            "importance": int(importance or 0),
            "effects": [dict(item) for item in (effects or []) if isinstance(item, dict)],
            "effect_results": [],
        }

    @staticmethod
    async def _record_event(state_plugin: Any, current_tick: int, event: dict[str, Any]) -> None:
        summary = str(event.get("summary") or event.get("current_action") or "事件已发生")
        lines = event.get("lines") or [BasicInvokePlugin._line("旁白", "事件", summary, "narration")]
        actor_id = getattr(state_plugin, "agent_id", "")
        actor_action = (event.get("current_actions") or {}).get(actor_id)
        if await state_plugin.is_active():
            await state_plugin.set_state("current_action", actor_action or event.get("current_action") or summary)
        await state_plugin.add_short_term_memory(summary, tick=current_tick)
        await state_plugin.add_event(current_tick, event)
        await state_plugin.add_dialogue(current_tick, BasicInvokePlugin._legacy_lines(lines))

    async def _apply_effects(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        participants = set(event.get("participants") or [])
        event_id = str(event.get("event_id") or "")
        results: list[dict[str, Any]] = []
        for effect in event.get("effects") or []:
            effect_type = str(effect.get("type") or "")
            try:
                if effect_type == "agent_state":
                    target = str(effect.get("target") or "")
                    field = str(effect.get("field") or "")
                    value = effect.get("value")
                    if target not in participants or field not in _ALLOWED_AGENT_EFFECT_FIELDS:
                        raise ValueError("agent state effect is outside participant/field whitelist")
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError("agent state value must be a non-empty string")
                    await self.controller.run_agent_method(target, "state", "set_state", field, value[:500])
                    results.append({"applied": True, **effect})
                elif effect_type == "relation_delta":
                    source = str(effect.get("source") or "")
                    target = str(effect.get("target") or "")
                    if source not in participants or target not in participants or source == target:
                        raise ValueError("relation effect must connect two participants")
                    result = await self.controller.run_environment(
                        "relation",
                        "apply_relation_delta",
                        source,
                        target,
                        effect.get("delta"),
                        str(effect.get("reason") or ""),
                        event_id,
                    )
                    results.append(result if isinstance(result, dict) else {"applied": False, "reason": "invalid relation response"})
                elif effect_type == "activity":
                    target = str(effect.get("target") or "")
                    reason = str(effect.get("reason") or "").strip()
                    is_active = effect.get("is_active")
                    if target not in participants or not isinstance(is_active, bool):
                        raise ValueError("activity effect must target a participant")
                    if not is_active and len(reason) < 4:
                        raise ValueError("irreversible departure requires an explicit reason")
                    await self.controller.run_agent_method(
                        target, "state", "set_active_status", is_active, reason[:500]
                    )
                    if not is_active:
                        await self.controller.run_agent_method(
                            target, "state", "add_long_term_memory", f"[最终结局] {reason[:500]}"
                        )
                        await self._broadcast_departure(target, reason[:500])
                    results.append({"applied": True, **effect})
                else:
                    raise ValueError("effect type is not allowed")
            except Exception as exc:  # noqa: BLE001
                results.append({"applied": False, "effect": dict(effect), "reason": str(exc)})
        return results

    async def _broadcast_departure(self, target: str, reason: str) -> None:
        try:
            all_ids = await self.controller.get_all_agent_ids()
            message = f"[离场事件] {target}已无法继续参与后续行动。原因：{reason}"
            for agent_id in all_ids:
                if agent_id != target:
                    await self.controller.run_agent_method(
                        agent_id, "state", "add_long_term_memory", message
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] departure broadcast failed: %s", self.agent_id, exc)

    async def _propagate_to_target(
        self,
        target: str,
        current_tick: int,
        action: str,
        time: int,
        location: str,
        importance: int,
        event: dict[str, Any],
    ) -> None:
        if not self.controller:
            return
        try:
            occ = {"occupier": self.agent_id, "importance": importance, "action": action}
            target_action = (event.get("current_actions") or {}).get(target) or self._strip_location_from_action(
                f"回应{self.agent_id}发起的互动", location
            )
            target_event = dict(event)
            target_event["current_action"] = target_action
            target_event["perspective"] = target
            target_event["current_actions"] = dict(event.get("current_actions") or {})
            target_event["current_actions"].setdefault(target, target_action)
            target_active = bool(
                await self.controller.run_agent_method(target, "state", "is_active")
            )
            if target_active:
                await self.controller.run_agent_method(target, "state", "set_state", "occupied_by", occ)
                await self.controller.run_agent_method(
                    target, "state", "set_state", "current_plan", [action, time, self.agent_id, location, importance]
                )
            await self.controller.run_agent_method(
                target, "state", "add_short_term_memory", event.get("summary", ""), current_tick
            )
            if target_active:
                await self.controller.run_agent_method(
                    target, "state", "set_state", "current_action", target_action
                )
            await self.controller.run_agent_method(target, "state", "add_event", current_tick, target_event)
            if event.get("lines"):
                await self.controller.run_agent_method(
                    target, "state", "add_dialogue", current_tick, self._legacy_lines(event["lines"])
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s][%s] propagate to %s failed: %s", self.agent_id, current_tick, target, exc)
