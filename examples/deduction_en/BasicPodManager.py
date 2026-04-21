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
        Concurrently collect status data of all agents, using a semaphore to control concurrency and prevent system overload.
        """
        all_agent_ids = list(self._agent_id_to_pod.keys())
        # Limit the number of concurrent agents, e.g., max 10 agents at a time
        sem = asyncio.Semaphore(10)

        async def fetch_one(agent_id: str) -> tuple:
            async with sem:
                try:
                    pod = self._agent_id_to_pod[agent_id]
                    # logger.info("collect_agents_data: fetching data for agent %s", agent_id)
                    
                    # Helper function for remote calls
                    async def remote_call(method, *args):
                        # Add timeout control for each remote call to prevent overall hang when an agent is busy
                        try:
                            # Add timeout control, default 10s
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

                    # Fetch basic information
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

                    # Calculate time index based on current tick and extract target location from the day's plan
                    tick_val = current_tick or 0
                    current_location = None

                    # Prioritize location from current_plan (including user-defined plans)
                    if current_plan and isinstance(current_plan, (list, tuple)) and len(current_plan) >= 4:
                        current_location = current_plan[3]
                    # If no current_plan, fetch from hourly_plans
                    elif hourly_plans:
                        day = str((tick_val // 12) + 1)
                        shichen = tick_val % 12
                        day_plans = hourly_plans.get(day) or hourly_plans.get(int(day))
                        if day_plans:
                            for plan in day_plans:
                                # plan format: [action, time, target, location, importance]
                                if isinstance(plan, (list, tuple)) and len(plan) >= 4 and plan[1] == shichen:
                                    current_location = plan[3]
                                    break

                    # If occupied, use the occupier's location (instead of the originally planned location)
                    if occupied_by and occupied_by.get("location"):
                        current_location = occupied_by["location"]

                    return agent_id, {
                        "long_task": long_task or "No long-term task",
                        "current_plan": current_plan,
                        "current_plan_note": current_plan_note,
                        "current_action": current_action or "No current action",
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
        Collect status data for a single agent, used to immediately update the frontend display after dynamically adding an agent.
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

            # Prioritize location from current_plan (including user-defined plans)
            if current_plan and isinstance(current_plan, (list, tuple)) and len(current_plan) >= 4:
                current_location = current_plan[3]
            # If no current_plan, fetch from hourly_plans
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
                "long_task": long_task or "No long-term task",
                "current_plan": current_plan,
                "current_plan_note": current_plan_note,
                "current_action": current_action or "No current action",
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

    async def restore_all_agents(self, snapshot: Dict[str, Any]) -> None:
        """
        Restore all agents to a previously saved state snapshot.
        Called during branch fork to roll back Ray actor state.

        Args:
            snapshot: dict of { agent_id -> agent_state_dict } as saved by collect_agents_data
        """
        sem = asyncio.Semaphore(10)

        async def restore_one(agent_id: str, state: dict) -> None:
            async with sem:
                pod = self._agent_id_to_pod.get(agent_id)
                if pod is None:
                    logger.warning(f"restore_all_agents: agent '{agent_id}' not found in pod map")
                    return
                try:
                    await asyncio.wait_for(
                        pod.forward.remote("run_agent_method", agent_id, "state", "restore_state", state),
                        timeout=30.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"restore_all_agents: timeout restoring agent '{agent_id}'")
                except Exception as exc:
                    logger.error(f"restore_all_agents: failed for '{agent_id}': {exc}")

        await asyncio.gather(*(restore_one(aid, state) for aid, state in snapshot.items()))
        logger.info(f"restore_all_agents: restored {len(snapshot)} agents")