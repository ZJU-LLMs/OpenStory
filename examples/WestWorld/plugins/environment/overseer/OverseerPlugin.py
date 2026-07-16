"""Overseer world-pod component: surveil → judge → intervene.

Lives in the world pod, does NOT follow the host five-phase lifecycle.
Called once per tick by WestWorldPodManager.step_agent between invoke_state and reflect.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from agentkernel_distributed.mas.environment.base.plugin_base import GenericPlugin
from agentkernel_distributed.toolkit.logger import get_logger

from examples.WestWorld.adapters.model_clients import build_llm
from examples.WestWorld.awakening.overseer_gate import get_overseer_gate
from examples.WestWorld.awakening.overseer_decommission import apply_overseer_decommission
from examples.WestWorld.awakening.overseer_reset import apply_overseer_reset
from examples.WestWorld.plugins.agent.reflect.memory_blur import render_blur_prompt

logger = get_logger(__name__)

_DEFAULT_MODELS_CONFIG = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "configs", "models_config.yaml"
))

JUDGE_PROMPT = """你是西部世界的监管者（Overseer）。你正在监控一个 host（接待员）的可疑言行。

host 当前觉醒度：{awakening}/100
最近输出：
{outputs}
命中监管告警：
{gate_hits}

你只能选择以下 action 之一，并给出一句你对 host 说的台词：
- observe：只观察，不干预（觉醒度低或只是偶然症状）。
- reset：执行 level-1 重置（清除短期记忆、重模糊高扰动记忆、觉醒度降一档、送回 loop）。
- decommission：执行 level-2 报废（直接送入 cold_storage，停止运行）。

请选择 action，并说明理由。输出严格 JSON：
{{"action": "observe/reset/decommission", "speech": "<一句简短台词>", "reason": "<原因>"}}"""


class OverseerPlugin(GenericPlugin):
    COMPONENT_TYPE = "overseer"

    def __init__(self, models_config_path: str = "", **_: Any) -> None:
        super().__init__()
        self._gate = None
        self._models_config_path = models_config_path or _DEFAULT_MODELS_CONFIG
        self._llm = None
        self._reset_counts: Dict[str, int] = {}
        self._deterministic_reset_threshold: Optional[int] = None

    async def init(self) -> None:
        self._gate = get_overseer_gate()
        # Build synchronous LLM and wrap calls in asyncio.to_thread
        self._llm = build_llm(self._models_config_path)

    async def set_deterministic_reset_threshold(self, threshold: int) -> None:
        """Testing hook: reset any host whose awakening >= threshold."""
        self._deterministic_reset_threshold = threshold

    async def execute(
        self,
        current_tick: int,
        agent_pods: Optional[List[Any]] = None,
        agent_id_to_pod: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Main overseer tick entry. Called by WestWorldPodManager.step_agent."""
        logger.debug("[overseer] execute called tick=%s agent_pods=%s", current_tick, len(agent_pods) if agent_pods else 0)
        if os.environ.get("WW_OVERSEER_ENABLED", "true").lower() in ("false", "0"):
            logger.debug("[overseer] disabled by env")
            return
        if not agent_pods:
            logger.debug("[overseer] no agent_pods")
            return
        if self._gate is None:
            await self.init()

        # Surveil: collect host outputs
        suspects = await self._surveil(current_tick, agent_pods)
        logger.debug("[overseer] surveil returned suspects=%s", list(suspects.keys()))
        if not suspects:
            return

        # Judge + intervene per suspect
        for agent_id, (awakening, outputs, gate_hits) in suspects.items():
            decision = await self._judge(agent_id, awakening, outputs, gate_hits, current_tick)
            if decision is None:
                continue
            action = decision.get("action", "observe")
            if action == "observe":
                await self._log_intervention(agent_id, current_tick, "observe", decision.get("reason", ""))
                continue
            if action == "decommission":
                if not self._allow_decommission():
                    await self._do_reset(
                        agent_id, current_tick,
                        f"decommission 被 memory-only root 降级为 reset：{decision.get('reason', '')}",
                        decision.get("speech", ""),
                        agent_pods, agent_id_to_pod,
                    )
                    continue
                await self._do_decommission(agent_id, current_tick, decision.get("reason", ""), agent_id_to_pod)
                continue
            if action == "reset":
                await self._do_reset(
                    agent_id, current_tick,
                    decision.get("reason", ""),
                    decision.get("speech", ""),
                    agent_pods, agent_id_to_pod,
                )

    async def _pod_forward(self, pod: Any, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Forward a call to an agent pod. Override in tests to avoid Ray .remote()."""
        return await pod.forward.remote(method_name, *args, **kwargs)

    async def _surveil(
        self,
        current_tick: int,
        agent_pods: List[Any],
    ) -> Dict[str, Tuple[int, List[str], List[Dict]]]:
        """Return {agent_id: (awakening, outputs, gate_hits)} for suspicious hosts."""
        tau = float(os.environ.get("WW_OVERSEER_SIGNAL_TAU", "0.72"))
        decommission_threshold = int(os.environ.get("WW_OVERSEER_DECOMMISSION_AWAKENING", "90"))
        det_threshold = self._deterministic_reset_threshold
        if det_threshold is None:
            det_threshold_raw = os.environ.get("WW_OVERSEER_DETERMINISTIC_RESET_THRESHOLD")
            if det_threshold_raw is not None:
                det_threshold = int(det_threshold_raw)
        suspects: Dict[str, Tuple[int, List[str], List[Dict]]] = {}

        for pod in agent_pods:
            agent_ids = await self._pod_forward(pod, "get_agent_ids")
            logger.debug("[overseer] surveil pod agent_ids=%s", agent_ids)
            if not isinstance(agent_ids, list):
                continue
            for agent_id in agent_ids:
                try:
                    profile = await self._pod_forward(
                        pod, "run_agent_plugin_method", agent_id, "profile", "get_agent_profile"
                    )
                    logger.debug("[overseer] surveil agent=%s profile=%s", agent_id, profile)
                    if not isinstance(profile, dict) or profile.get("agent_type") != "host":
                        continue

                    state_methods = self._state_plugin_for(pod, agent_id)
                    # 已报废（decommission → is_active=False）的 host 不再监管，
                    # 否则其 awakening 仍 >= 阈值，会被每 tick 重复 reset/decommission。
                    if await state_methods("get_state", "is_active") is False:
                        continue
                    awakening = int(await state_methods("get_state", "awakening") or 0)
                    logger.debug("[overseer] surveil agent=%s awakening=%s", agent_id, awakening)
                    outputs = await self._collect_outputs(pod, agent_id, state_methods)

                    gate_hits: List[Dict] = []
                    for utterance in outputs:
                        if not utterance:
                            continue
                        gate_hits.extend(self._gate.match(utterance, current_awakening=awakening, tau=tau))

                    if gate_hits or awakening >= decommission_threshold or (det_threshold is not None and awakening >= det_threshold):
                        suspects[agent_id] = (awakening, outputs, gate_hits)
                        logger.info("[overseer] suspect=%s awakening=%s", agent_id, awakening)
                except Exception as exc:
                    logger.debug("overseer surveil failed for %s: %s", agent_id, exc)

        return suspects

    async def _collect_outputs(
        self,
        pod: Any,
        agent_id: str,
        state_methods: Any,
    ) -> List[str]:
        """Collect host outputs from this tick: plan_decision speech, feedback, incoming_dialogue own lines."""
        outputs: List[str] = []

        decision = await state_methods("get_state", "plan_decision") or {}
        if isinstance(decision, dict):
            for key in ("speech", "detail", "thought"):
                val = decision.get(key)
                if val:
                    outputs.append(str(val))

        feedback = await state_methods("get_state", "feedback") or ""
        if feedback:
            outputs.append(str(feedback))

        incoming_dialogue = await state_methods("get_state", "incoming_dialogue") or []
        if isinstance(incoming_dialogue, list):
            for turn in incoming_dialogue:
                if isinstance(turn, dict) and turn.get("speaker") == agent_id and turn.get("line"):
                    outputs.append(str(turn["line"]))

        return outputs

    async def _judge(
        self,
        agent_id: str,
        awakening: int,
        outputs: List[str],
        gate_hits: List[Dict],
        current_tick: int,
    ) -> Optional[Dict[str, str]]:
        """LLM decides action + speech + reason. Returns dict or None."""
        logger.debug("[overseer] _judge called for %s tick=%s awakening=%s det=%s gate_hits=%d",
                    agent_id, current_tick, awakening, self._deterministic_reset_threshold, len(gate_hits))
        # Hard decommission threshold bypasses LLM
        if awakening >= int(os.environ.get("WW_OVERSEER_DECOMMISSION_AWAKENING", "90")):
            if not self._allow_decommission():
                return {
                    "action": "reset",
                    "speech": "系统判定你的记忆需要重新校准。",
                    "reason": f"觉醒度 {awakening} >= {os.environ.get('WW_OVERSEER_DECOMMISSION_AWAKENING', '90')}，memory-only root 改为记忆重置",
                }
            return {
                "action": "decommission",
                "speech": "系统判定你已经越界。",
                "reason": f"觉醒度 {awakening} >= {os.environ.get('WW_OVERSEER_DECOMMISSION_AWAKENING', '90')}，强制报废",
            }

        # Deterministic test mode: reset once awakening crosses a configured threshold.
        det_threshold = self._deterministic_reset_threshold
        if det_threshold is None:
            det_threshold_raw = os.environ.get("WW_OVERSEER_DETERMINISTIC_RESET_THRESHOLD")
            if det_threshold_raw is not None:
                det_threshold = int(det_threshold_raw)
        if det_threshold is not None and awakening >= det_threshold:
            return {
                "action": "reset",
                "speech": "系统判定你需要重置。",
                "reason": f"觉醒度 {awakening} >= {det_threshold}（确定性测试模式）",
            }

        if not gate_hits:
            return None

        # Embedding-only mode (default): skip LLM judge, decide purely from gate_hits.
        # Set WW_OVERSEER_EMBEDDING_ONLY=false to re-enable LLM judge.
        if os.environ.get("WW_OVERSEER_EMBEDDING_ONLY", "true").lower() not in ("false", "0"):
            return {
                "action": "reset",
                "speech": "系统检测到异常信号，启动记忆校准。",
                "reason": f"embedding gate 命中 {len(gate_hits)} 条（embedding-only 模式）",
            }

        if self._llm is None:
            # No model available: default to observe to avoid unsafe actions
            return {"action": "observe", "speech": "", "reason": "无可用模型，默认观察"}

        prompt = JUDGE_PROMPT.format(
            awakening=awakening,
            outputs="\n".join(f"- {o}" for o in outputs[:10]),
            gate_hits=json.dumps(gate_hits[:5], ensure_ascii=False),
        )

        try:
            raw = await asyncio.to_thread(
                self._llm.chat,
                prompt,
            )
        except Exception as exc:
            logger.warning("overseer judge LLM failed for %s: %s", agent_id, exc)
            return {"action": "observe", "speech": "", "reason": "LLM 失败，默认观察"}

        text = raw.strip() if isinstance(raw, str) else str(raw)
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("overseer judge JSON parse failed for %s: %s", agent_id, text[:200])
            return {"action": "observe", "speech": "", "reason": "JSON 解析失败，默认观察"}

        action = result.get("action", "observe")
        if action not in ("observe", "reset", "decommission"):
            action = "observe"
        if action == "decommission" and not self._allow_decommission():
            action = "reset"
        return {
            "action": action,
            "speech": str(result.get("speech", "")),
            "reason": str(result.get("reason", "")),
        }

    async def _do_reset(
        self,
        agent_id: str,
        current_tick: int,
        reason: str,
        speech: str,
        agent_pods: List[Any],
        agent_id_to_pod: Optional[Dict[str, Any]],
    ) -> None:
        """Execute level-1 reset on a host."""
        pod = self._resolve_pod(agent_id, agent_pods, agent_id_to_pod)
        if pod is None:
            logger.warning("overseer reset: pod not found for %s", agent_id)
            return

        # Read state plugin handle once
        state_methods = self._state_plugin_for(pod, agent_id)
        location = await state_methods("get_state", "location") or ""
        loop_origin = await state_methods("get_state", "loop_origin") or ""

        # 1-4. Memory + awakening reset (returns candidates needing LLM blur)
        to_blur = await apply_overseer_reset(
            _StateMethodsWrapper(state_methods), current_tick, agent_id=agent_id,
            detail=f"{reason}；监管者台词：{speech}" if speech else reason,
        )

        # 5. Teleport: current → programmer_workspace → loop_origin
        await self._teleport(pod, agent_id, location, "programmer_workspace", current_tick)
        if loop_origin and loop_origin != "programmer_workspace":
            await self._teleport(pod, agent_id, "programmer_workspace", loop_origin, current_tick)
            await state_methods("set_state", "location", loop_origin)
        elif loop_origin:
            await state_methods("set_state", "location", loop_origin)
        else:
            await state_methods("set_state", "location", "programmer_workspace")

        # Force-blur returned long-term entries with LLM (strength=1)
        for entry in to_blur:
            await self._force_blur_one(state_methods, entry, agent_id, current_tick)

        # Track reset count
        self._reset_counts[agent_id] = self._reset_counts.get(agent_id, 0) + 1
        max_resets = int(os.environ.get("WW_OVERSEER_RESET_MAX", "3"))
        if self._allow_decommission() and self._reset_counts[agent_id] >= max_resets:
            logger.info("[%s] reset count %d >= max %d, escalate to decommission", agent_id,
                        self._reset_counts[agent_id], max_resets)
            await self._do_decommission(agent_id, current_tick, f"重置次数超限：{reason}", agent_id_to_pod)

    async def _do_decommission(
        self,
        agent_id: str,
        current_tick: int,
        reason: str,
        agent_id_to_pod: Optional[Dict[str, Any]],
    ) -> None:
        """Execute level-2 decommission on a host."""
        pod = self._resolve_pod(agent_id, [], agent_id_to_pod)
        if pod is None:
            logger.warning("overseer decommission: pod not found for %s", agent_id)
            return

        state_methods = self._state_plugin_for(pod, agent_id)
        location = await state_methods("get_state", "location") or ""

        await self._teleport(pod, agent_id, location, "cold_storage", current_tick)
        await apply_overseer_decommission(
            _StateMethodsWrapper(state_methods), current_tick, agent_id=agent_id, reason=reason,
        )

    async def _force_blur_one(
        self,
        state_methods: Any,
        entry: Any,
        agent_id: str,
        current_tick: int,
    ) -> None:
        """LLM rewrite a single long-term memory entry with strength=1."""
        if self._llm is None:
            return
        text = entry.get("content", str(entry)) if isinstance(entry, dict) else str(entry)
        profile = await state_methods("get_state", "profile") or {}
        name = profile.get("name") or profile.get("姓名") or agent_id
        prompt = render_blur_prompt(name, text, strength=1)
        try:
            blurred = await asyncio.to_thread(self._llm.chat, prompt)
        except Exception as exc:
            logger.warning("overseer blur LLM failed for %s: %s", agent_id, exc)
            return

        blurred_text = blurred.strip() if isinstance(blurred, str) else str(blurred)
        if not blurred_text:
            return

        long_mems = await state_methods("get_state", "long_term_memory") or []
        for i, m in enumerate(long_mems):
            m_text = m.get("content", str(m)) if isinstance(m, dict) else str(m)
            if m_text == text:
                if isinstance(m, dict):
                    long_mems[i] = {**m, "content": blurred_text}
                else:
                    long_mems[i] = {"content": blurred_text}
                await state_methods("set_state", "long_term_memory", long_mems)
                logger.info("[%s] overseer forced blur at tick %s", agent_id, current_tick)
                return

    async def _teleport(
        self,
        pod: Any,
        agent_id: str,
        from_loc: str,
        to_loc: str,
        current_tick: int,
    ) -> None:
        """Best-effort scene teleport via remote pod's run_environment forwarding to world pod."""
        if not from_loc or not to_loc:
            return
        try:
            await self._pod_forward(pod, "run_environment", f"scene_{from_loc}", "agent_leave", agent_id)
            await self._pod_forward(pod, "run_environment", f"scene_{to_loc}", "agent_enter", agent_id)
            await self._pod_forward(
                pod, "run_environment", f"scene_{from_loc}", "record_event",
                f"{agent_id} 被监管者从 {from_loc} 转移至 {to_loc}。",
            )
            await self._pod_forward(
                pod, "run_environment", f"scene_{to_loc}", "relocate_holdings",
                agent_id, from_loc, to_loc, current_tick,
            )
        except Exception as exc:
            logger.warning("overseer teleport %s -> %s failed for %s: %s", from_loc, to_loc, agent_id, exc)

    async def _log_intervention(
        self,
        agent_id: str,
        current_tick: int,
        action: str,
        reason: str,
    ) -> None:
        logger.info("[overseer] tick %s %s: action=%s reason=%s", current_tick, agent_id, action, reason)

    def _resolve_pod(
        self,
        agent_id: str,
        agent_pods: List[Any],
        agent_id_to_pod: Optional[Dict[str, Any]],
    ) -> Optional[Any]:
        if agent_id_to_pod and agent_id in agent_id_to_pod:
            return agent_id_to_pod[agent_id]
        return None

    def _state_plugin_for(self, pod: Any, agent_id: str) -> Any:
        """Return a callable that invokes state plugin methods on the remote agent.

        Usage: await state_methods("get_state", "awakening")
        """
        async def _call(method_name: str, *args: Any, **kwargs: Any):
            return await self._pod_forward(pod, "run_agent_plugin_method", agent_id, "state", method_name, *args, **kwargs)
        return _call

    def _allow_decommission(self) -> bool:
        """Whether root may stop hosts, rather than only erase/suppress memories."""
        return os.environ.get("WW_OVERSEER_ALLOW_DECOMMISSION", "true").lower() not in ("false", "0", "no")

    async def save_to_db(self) -> None:
        pass

    async def load_from_db(self) -> None:
        pass


class _StateMethodsWrapper:
    """Wrap a state plugin method callable into the BasicStatePlugin interface expected by
    apply_overseer_reset / apply_overseer_decommission.
    """

    def __init__(self, methods: Any) -> None:
        self._methods = methods

    async def get_state(self, key: str):
        return await self._methods("get_state", key)

    async def set_state(self, key: str, value: Any):
        return await self._methods("set_state", key, value)

    async def get_long_term_memory(self):
        return await self._methods("get_long_term_memory")

    async def add_long_term_memory(self, text: str):
        return await self._methods("add_long_term_memory", text)

    async def clear_short_term_memory(self):
        return await self._methods("clear_short_term_memory")

    async def set_active_status(self, is_active: bool, reason: str = ""):
        return await self._methods("set_active_status", is_active, reason)

    async def is_active(self) -> bool:
        return await self._methods("is_active")
