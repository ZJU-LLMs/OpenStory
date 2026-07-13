"""A2 pod manager: one world pod (pods[0], agents=[], full environment) + N agent pods.

scene_* components and WorldObjectRegistry live only in the world pod.
Agent pods have environment=None; their controllers forward environment calls
via pod_manager → world pod (see controller.run_environment forwarding patch).

Phase A: step_agent now includes a dialogue barrier between perceive_plan and invoke_state.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

import ray

from agentkernel_distributed.mas.pod import PodManagerImpl
from agentkernel_distributed.mas.pod.mas_pod import MasPod
from agentkernel_distributed.types.configs import Config, PodConfig

logger = logging.getLogger(__name__)

_WORLD_POD_ID = "pod_world"


# ── overseer barrier helper (extracted for testability) ─────────────────────
async def run_overseer_barrier(
    world_pod: Any,
    agent_pods: List[Any],
    agent_id_to_pod: Dict[str, Any],
    current_tick: int,
) -> None:
    """Call the overseer environment component once per tick.

    Runs after scene tick_update and before reflect. world_pod, agent_pods, and
    agent_id_to_pod are Ray actor handles in production; tests can pass mocks.
    """
    logger.debug("[run_overseer_barrier] tick=%s enabled=%s agent_pods=%d", current_tick,
                os.environ.get("WW_OVERSEER_ENABLED", "true"), len(agent_pods))
    if os.environ.get("WW_OVERSEER_ENABLED", "true").lower() in ("false", "0"):
        return
    try:
        await world_pod.forward.remote(
            "run_environment", "overseer", "execute",
            current_tick, agent_pods, agent_id_to_pod,
        )
    except Exception as exc:
        logger.warning("overseer barrier failed at tick %s: %s", current_tick, exc)


@ray.remote
class WestWorldPodManager(PodManagerImpl):
    """A2 pattern: world pod holds environment; agent pods hold only agents."""

    async def init(
        self,
        configs: Config,
        resource_maps: Dict[str, Any],
        model_router_config: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._resource_maps = resource_maps
        self._configs = configs
        self._model_router_config = model_router_config

        from agentkernel_distributed.toolkit.models.router import ModelRouter, AsyncModelRouter
        if model_router_config:
            model_backend = AsyncModelRouter(models_configs=model_router_config)
            self._model_router = ModelRouter(model_backend)

        await self._init_adapters()

        # ── 1. 世界 pod：无 agent，持有完整 environment ──────────────────────
        world_cfg = PodConfig(
            agent_templates=configs.agent_templates,
            agents=[],
            actions=configs.actions,
            environment=configs.environment,
            database=configs.database,
        )
        world_pod = MasPod.remote(
            pod_id=_WORLD_POD_ID,
            pod_config=world_cfg,
            resource_maps=resource_maps,
            controller_class=self._controller_class,
        )

        # ── 2. Agent pods：持有 agent，environment=None ───────────────────────
        all_agents = configs.agents or []
        agent_batches = [
            all_agents[i: i + self._pod_size]
            for i in range(0, len(all_agents), self._pod_size)
        ] if all_agents else []

        agent_pod_handles: Dict[str, MasPod] = {}
        for idx, batch in enumerate(agent_batches):
            pod_id = f"pod_{idx}"
            pod_cfg = PodConfig(
                agent_templates=configs.agent_templates,
                agents=batch,
                actions=configs.actions,
                environment=None,   # no local environment — forward to world pod
                database=configs.database,
            )
            handle = MasPod.remote(
                pod_id=pod_id,
                pod_config=pod_cfg,
                resource_maps=resource_maps,
                controller_class=self._controller_class,
            )
            agent_pod_handles[pod_id] = handle

        # world pod 放 pods[0]，与内核 save_to_db("all") 约定一致
        self._pod_id_to_pod = {_WORLD_POD_ID: world_pod, **agent_pod_handles}

        # ── 3. 初始化所有 pod ────────────────────────────────────────────────
        all_handles = list(self._pod_id_to_pod.values())
        for batch_start in range(0, len(all_handles), self._init_batch_size):
            batch = all_handles[batch_start: batch_start + self._init_batch_size]
            await asyncio.gather(
                *[h.init.remote(model_router_config=self._model_router_config) for h in batch]
            )
            logger.info("Initialized WestWorld pod batch %d", batch_start // self._init_batch_size + 1)

        # ── 4. 建立 agent_id → pod 映射 ─────────────────────────────────────
        agent_id_to_pod: Dict[str, MasPod] = {}
        for pod_handle in agent_pod_handles.values():
            ids = await pod_handle.forward.remote("get_agent_ids")
            for agent_id in ids:
                agent_id_to_pod[agent_id] = pod_handle
        self._agent_id_to_pod = agent_id_to_pod

        await self.save_to_db(scope="all")

    # ── 环境路由：始终转发到世界 pod ─────────────────────────────────────────
    async def run_environment(
        self, component_name: str, method_name: str, *args: Any, **kwargs: Any
    ) -> Any:
        world_pod = self._pod_id_to_pod.get(_WORLD_POD_ID)
        if world_pod is None:
            raise RuntimeError("World pod is not initialized")
        return await world_pod.forward.remote(
            "run_environment", component_name, method_name, *args, **kwargs
        )

    # ── tick 推进：perceive_plan → dialogue barrier → invoke_state → tick_update → reflect ──
    async def step_agent(self) -> None:
        agent_pods = [p for pid, p in self._pod_id_to_pod.items() if pid != _WORLD_POD_ID]
        if not agent_pods:
            return

        # 1. perceive + plan（并行）
        await asyncio.gather(*[p.forward.remote("step_perceive_plan") for p in agent_pods])

        # 2. 对话 barrier（串行，避免跨 pod 死锁）
        await self._run_dialogue_barrier()

        # 3. invoke + state（并行，含 recorder enqueue）
        await asyncio.gather(*[p.forward.remote("step_invoke_state") for p in agent_pods])

        # 4. tick_update 栅栏：世界 pod 批量裁决本 tick 所有排队动作
        current_tick = await self._system_handle.run("timer", "get_tick")
        world_pod = self._pod_id_to_pod[_WORLD_POD_ID]
        scene_components: List[str] = await world_pod.forward.remote("list_environment_components")
        scene_ids = [c for c in scene_components if c.startswith("scene_")]
        await asyncio.gather(*[
            world_pod.forward.remote("run_environment", scene, "execute", current_tick)
            for scene in scene_ids
        ])

        # 5. overseer barrier：监管者 surveil→judge→intervene
        await run_overseer_barrier(world_pod, agent_pods, self._agent_id_to_pod, current_tick)

        # 6. reflect 阶段：agent 读到最新裁决结果后总结
        await asyncio.gather(*[p.forward.remote("step_reflect") for p in agent_pods])

    async def _run_dialogue_barrier(self) -> None:
        """Serial dialogue barrier: collect talk intents, pair speakers, run rounds via speak()."""
        agent_pods = [p for pid, p in self._pod_id_to_pod.items() if pid != _WORLD_POD_ID]

        # Collect talk intents from all agent pods
        intent_lists = await asyncio.gather(*[
            p.forward.remote("collect_talk_intents") for p in agent_pods
        ])
        all_intents: Dict[str, str] = {}
        for pod_intents in intent_lists:
            if isinstance(pod_intents, dict):
                all_intents.update(pod_intents)

        if not all_intents:
            return

        max_rounds = int(os.environ.get("WW_DIALOGUE_MAX_ROUNDS", "4"))
        done_pairs: Set[Tuple[str, str]] = set()

        for speaker_id, target_id in all_intents.items():
            if not target_id:
                continue
            pair = (min(speaker_id, target_id), max(speaker_id, target_id))
            if pair in done_pairs:
                continue
            done_pairs.add(pair)

            speaker_pod = self._agent_id_to_pod.get(speaker_id)
            target_pod = self._agent_id_to_pod.get(target_id)
            if not speaker_pod or not target_pod:
                logger.warning("dialogue barrier: pod not found for %s or %s", speaker_id, target_id)
                continue

            history: List[Dict[str, Any]] = []
            for _ in range(max_rounds):
                # Speaker's line
                line = await speaker_pod.forward.remote(
                    "run_agent_plugin_method", speaker_id, "plan", "speak", history
                )
                if line:
                    history.append({"speaker": speaker_id, "line": line})
                # Target's line
                line = await target_pod.forward.remote(
                    "run_agent_plugin_method", target_id, "plan", "speak", history
                )
                if line:
                    history.append({"speaker": target_id, "line": line})

            if history:
                current_tick = await self._system_handle.run("timer", "get_tick")
                record = {
                    "tick": current_tick,
                    "participants": [speaker_id, target_id],
                    "turns": history,
                }
                # Write dialogue to each participant's state for reflect to consume
                await speaker_pod.forward.remote(
                    "run_agent_plugin_method", speaker_id, "state", "set_state", "incoming_dialogue", history
                )
                await target_pod.forward.remote(
                    "run_agent_plugin_method", target_id, "state", "set_state", "incoming_dialogue", history
                )
                await self._append_dialogue_history(speaker_pod, speaker_id, record)
                await self._append_dialogue_history(target_pod, target_id, record)
                logger.info(
                    "dialogue barrier: %s ↔ %s，%d 轮，%d 条",
                    speaker_id, target_id, max_rounds, len(history),
                )

    async def _append_dialogue_history(self, pod: Any, agent_id: str, record: Dict[str, Any]) -> None:
        history = await pod.forward.remote(
            "run_agent_plugin_method", agent_id, "state", "get_state", "dialogue_history"
        ) or []
        if not isinstance(history, list):
            history = []
        history.append(record)
        await pod.forward.remote(
            "run_agent_plugin_method", agent_id, "state", "set_state", "dialogue_history", history
        )

    # ── add_agent：加入空闲 agent pod（不动世界 pod）──────────────────────
    async def add_agent(self, agent_id: str, template_name: str, data: Dict[str, Any]) -> bool:
        if agent_id in self._agent_id_to_pod:
            logger.error("Agent '%s' already exists", agent_id)
            return False

        # 找有空位的 agent pod
        target_pod: Optional[MasPod] = None
        for pid, pod in self._pod_id_to_pod.items():
            if pid == _WORLD_POD_ID:
                continue
            count = await pod.forward.remote("get_agent_count")
            if count < self._pod_size:
                target_pod = pod
                break

        if target_pod is None:
            # 新建 agent pod
            pod_id = f"pod_{len(self._pod_id_to_pod) - 1}"  # -1 for world pod
            pod_cfg = PodConfig(
                agent_templates=self._configs.agent_templates,
                agents=[],
                actions=self._configs.actions,
                environment=None,
                database=self._configs.database,
            )
            target_pod = MasPod.remote(
                pod_id=pod_id,
                pod_config=pod_cfg,
                resource_maps=self._resource_maps,
                controller_class=self._controller_class,
            )
            await target_pod.init.remote(model_router_config=self._model_router_config)
            await target_pod.post_init.remote(self._system_handle, self._self_handle)
            self._pod_id_to_pod[pod_id] = target_pod

        success = await target_pod.forward.remote("add_agent", agent_id, template_name, data)
        if success:
            self._agent_id_to_pod[agent_id] = target_pod
        return success
