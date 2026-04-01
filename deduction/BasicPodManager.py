"""Example custom pod manager with convenience helpers."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Iterable, List, Optional

import ray

from agentkernel_distributed.mas.pod import PodManagerImpl
from agentkernel_distributed.toolkit.logger import get_logger

logger = get_logger(__name__)


@ray.remote
class BasicPodManager(PodManagerImpl):
    """Pod manager extension that exposes broadcast helpers for examples."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # In-memory storage for group discussions (shared across all pods)

    def get_all_agent_ids(self) -> List[str]:
        """
        Return all agent ids managed by the pod manager.
        """
        return list(self._agent_id_to_pod.keys())

    async def collect_agents_data(self) -> Dict[str, Any]:
        """
        并发收集所有 agent 的状态数据，使用信号量控制并发度，防止系统过载。
        """
        all_agent_ids = list(self._agent_id_to_pod.keys())
        # 限制并发 agent 数量，例如每次最多 10 个 agent
        sem = asyncio.Semaphore(10)

        async def fetch_one(agent_id: str) -> tuple:
            async with sem:
                try:
                    pod = self._agent_id_to_pod[agent_id]
                    # logger.info("collect_agents_data: fetching data for agent %s", agent_id)
                    
                    # 远程调用的辅助函数
                    async def remote_call(method, *args):
                        # 为每个远程调用增加超时控制，防止某个 Agent 忙碌导致整体挂起
                        try:
                            # 增加超时控制，默认 10s
                            return await asyncio.wait_for(
                                pod.forward.remote("run_agent_method", agent_id, method, *args),
                                timeout=10.0
                            )
                        except asyncio.TimeoutError:
                            logger.warning(f"collect_agents_data: timeout calling {method} for agent {agent_id}")
                            return None
                        except Exception as e:
                            logger.warning(f"collect_agents_data: error calling {method} for agent {agent_id}: {e}")
                            return None

                    # 基础信息获取
                    results = await asyncio.gather(
                        remote_call("state", "get_long_task"),
                        remote_call("state", "get_state", "current_plan"),
                        remote_call("state", "get_state", "current_plan_note"),
                        remote_call("state", "get_state", "current_action"),
                        remote_call("state", "get_state", "occupied_by"),
                        remote_call("state", "get_dialogues"),
                        remote_call("state", "get_hourly_plans"),
                        remote_call("state", "get_short_term_memory"),
                        remote_call("state", "get_long_term_memory"),
                        remote_call("profile", "get_agent_profile"),
                        remote_call("state", "is_active"),
                        remote_call("state", "get_inactive_reason"),
                        remote_call("state", "get_state", "current_tick"),
                    )
                    
                    long_task, current_plan, current_plan_note, current_action, occupied_by, dialogues, hourly_plans, short_mem, long_mem, profile, is_active, inactive_reason, current_tick = results

                    # 根据当前 tick 计算时辰索引，从当天计划中取出目标地点
                    tick_val = current_tick or 0
                    current_location = None

                    # 优先从 current_plan 获取位置（包括用户设定的计划）
                    if current_plan and isinstance(current_plan, (list, tuple)) and len(current_plan) >= 4:
                        current_location = current_plan[3]
                    # 如果没有 current_plan，从 hourly_plans 中获取
                    elif hourly_plans:
                        day = str((tick_val // 12) + 1)
                        shichen = tick_val % 12
                        day_plans = hourly_plans.get(day) or hourly_plans.get(int(day))
                        if day_plans:
                            for plan in day_plans:
                                # plan 格式: [action, time, target, location, importance]
                                if isinstance(plan, (list, tuple)) and len(plan) >= 4 and plan[1] == shichen:
                                    current_location = plan[3]
                                    break

                    # 如果被占用，使用占用者的地点（而非自己原计划的地点）
                    if occupied_by and occupied_by.get("location"):
                        current_location = occupied_by["location"]

                    return agent_id, {
                        "long_task": long_task or "暂无志向",
                        "current_plan": current_plan,
                        "current_plan_note": current_plan_note,
                        "current_action": current_action or "暂无行动",
                        "occupied_by": occupied_by,
                        "dialogues": dialogues or {},
                        "hourly_plans": hourly_plans or {},
                        "short_term_memory": short_mem or [],
                        "long_term_memory": long_mem or [],
                        "profile": profile,
                        "is_active": is_active,
                        "inactive_reason": inactive_reason,
                        "current_tick": current_tick or 0,
                        "current_location": current_location,
                    }
                except Exception as exc:
                    logger.error("collect_agents_data: failed for agent %s: %s", agent_id, exc)
                    return agent_id, None

        results = await asyncio.gather(*(fetch_one(aid) for aid in all_agent_ids))
        return {aid: data for aid, data in results if data is not None}

    async def collect_single_agent_data(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        收集单个 agent 的状态数据，用于动态添加 agent 后立即更新前端显示。
        """
        if agent_id not in self._agent_id_to_pod:
            logger.warning(f"collect_single_agent_data: agent '{agent_id}' not found")
            return None

        try:
            pod = self._agent_id_to_pod[agent_id]

            async def remote_call(method, *args):
                try:
                    return await asyncio.wait_for(
                        pod.forward.remote("run_agent_method", agent_id, method, *args),
                        timeout=10.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"collect_single_agent_data: timeout calling {method} for agent {agent_id}")
                    return None
                except Exception as e:
                    logger.warning(f"collect_single_agent_data: error calling {method} for agent {agent_id}: {e}")
                    return None

            results = await asyncio.gather(
                remote_call("state", "get_long_task"),
                remote_call("state", "get_state", "current_plan"),
                remote_call("state", "get_state", "current_plan_note"),
                remote_call("state", "get_state", "current_action"),
                remote_call("state", "get_state", "occupied_by"),
                remote_call("state", "get_dialogues"),
                remote_call("state", "get_hourly_plans"),
                remote_call("state", "get_short_term_memory"),
                remote_call("state", "get_long_term_memory"),
                remote_call("profile", "get_agent_profile"),
                remote_call("state", "is_active"),
                remote_call("state", "get_inactive_reason"),
                remote_call("state", "get_state", "current_tick"),
            )

            long_task, current_plan, current_plan_note, current_action, occupied_by, dialogues, hourly_plans, short_mem, long_mem, profile, is_active, inactive_reason, current_tick = results

            tick_val = current_tick or 0
            current_location = None

            # 优先从 current_plan 获取位置（包括用户设定的计划）
            if current_plan and isinstance(current_plan, (list, tuple)) and len(current_plan) >= 4:
                current_location = current_plan[3]
            # 如果没有 current_plan，从 hourly_plans 中获取
            elif hourly_plans:
                day = str((tick_val // 12) + 1)
                shichen = tick_val % 12
                day_plans = hourly_plans.get(day) or hourly_plans.get(int(day))
                if day_plans:
                    for plan in day_plans:
                        if isinstance(plan, (list, tuple)) and len(plan) >= 4 and plan[1] == shichen:
                            current_location = plan[3]
                            break

            if occupied_by and occupied_by.get("location"):
                current_location = occupied_by["location"]

            return {
                "long_task": long_task or "暂无志向",
                "current_plan": current_plan,
                "current_plan_note": current_plan_note,
                "current_action": current_action or "暂无行动",
                "occupied_by": occupied_by,
                "dialogues": dialogues or {},
                "hourly_plans": hourly_plans or {},
                "short_term_memory": short_mem or [],
                "long_term_memory": long_mem or [],
                "profile": profile,
                "is_active": is_active,
                "inactive_reason": inactive_reason,
                "current_tick": current_tick or 0,
                "current_location": current_location,
            }
        except Exception as exc:
            logger.error(f"collect_single_agent_data: failed for agent {agent_id}: {exc}")
            return None

    async def update_agents_status(self) -> None:
        """
        Trigger each pod to refresh agent status within the environment.

        Returns:
            None
        """
        try:
            await asyncio.gather(*(pod.forward.remote("update_agents_status") for pod in self._pod_id_to_pod.values()))
            logger.info("Update agent status completed across all pods.")
        except Exception as exc:
            logger.error("Failed to update agent status: %s", exc, exc_info=True)