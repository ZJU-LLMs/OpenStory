from __future__ import annotations

import asyncio
from typing import Any

import ray

from plugins._optional_deps import ensure_optional_agentkernel_imports

ensure_optional_agentkernel_imports()

from agentkernel_distributed.mas.pod import PodManagerImpl


@ray.remote
class WKPodManager(PodManagerImpl):
    def get_all_agent_ids(self) -> list[str]:
        return list(self._agent_id_to_pod.keys())

    async def update_agents_status(self) -> None:
        return None

    async def collect_and_reset_token_usage(self) -> dict[str, int]:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    async def collect_locations_data(self) -> list[dict[str, Any]]:
        """Read the shared environment from one representative pod."""
        if not self._pod_id_to_pod:
            return []
        representative_pod = next(iter(self._pod_id_to_pod.values()))
        try:
            locations = await asyncio.wait_for(
                representative_pod.forward.remote(
                    "run_environment", "space", "list_locations"
                ),
                timeout=10.0,
            )
        except Exception:
            return []
        return locations if isinstance(locations, list) else []

    async def make_snapshot(self) -> bool:
        return True

    async def rollback_to_tick(self, tick: int) -> bool:
        return True

    async def restore_all_agents(self, snapshot: dict[str, Any]) -> bool:
        return True

    async def set_pending_user_action(self, agent_id: str, action: dict[str, Any]) -> bool:
        pod = self._agent_id_to_pod.get(agent_id)
        if pod is None:
            return False
        await pod.forward.remote(
            "run_agent_method", agent_id, "state", "set_state", "pending_user_action", action
        )
        return True

    async def collect_agents_data(self) -> dict[str, Any]:
        all_agent_ids = list(self._agent_id_to_pod.keys())
        sem = asyncio.Semaphore(10)

        async def fetch_one(agent_id: str) -> tuple[str, dict[str, Any] | None]:
            async with sem:
                try:
                    pod = self._agent_id_to_pod[agent_id]

                    async def remote_call(component: str, method: str, *args: Any) -> Any:
                        try:
                            return await asyncio.wait_for(
                                pod.forward.remote("run_agent_method", agent_id, component, method, *args),
                                timeout=10.0,
                            )
                        except Exception:
                            return None

                    results = await asyncio.gather(
                        remote_call("state", "get_long_task"),
                        remote_call("state", "get_state", "current_plan"),
                        remote_call("state", "get_state", "current_plan_note"),
                        remote_call("state", "get_state", "current_action"),
                        remote_call("state", "get_state", "occupied_by"),
                        remote_call("state", "get_dialogues"),
                        remote_call("state", "get_event_log"),
                        remote_call("state", "get_hourly_plans"),
                        remote_call("state", "get_short_term_memory"),
                        remote_call("state", "get_long_term_memory"),
                        remote_call("profile", "get_agent_profile"),
                        remote_call("state", "is_active"),
                        remote_call("state", "get_inactive_reason"),
                        remote_call("state", "get_state", "current_tick"),
                        remote_call("state", "get_replan_log"),
                        remote_call("state", "get_long_task_adjustment_log"),
                        remote_call("state", "get_state", "location_id"),
                        remote_call("state", "get_state", "current_location"),
                        remote_call("state", "get_state", "position"),
                        remote_call("state", "get_state", "mood"),
                        remote_call("state", "get_state", "status"),
                        remote_call("state", "get_state", "active_goal"),
                        remote_call("state", "get_state", "pending_user_action"),
                    )
                    (
                        long_task,
                        current_plan,
                        current_plan_note,
                        current_action,
                        occupied_by,
                        dialogues,
                        event_log,
                        hourly_plans,
                        short_mem,
                        long_mem,
                        profile,
                        is_active,
                        inactive_reason,
                        current_tick,
                        replan_log,
                        long_task_adj_log,
                        location_id,
                        current_location,
                        position,
                        mood,
                        status,
                        active_goal,
                        pending_user_action,
                    ) = results
                    return agent_id, {
                        "long_task": long_task,
                        "current_plan": current_plan,
                        "current_plan_note": current_plan_note,
                        "current_action": current_action,
                        "occupied_by": occupied_by,
                        "dialogues": dialogues or {},
                        "event_log": event_log or [],
                        "hourly_plans": hourly_plans or {},
                        "short_term_memory": short_mem or [],
                        "long_term_memory": long_mem or [],
                        "profile": profile,
                        "is_active": True if is_active is None else is_active,
                        "inactive_reason": inactive_reason or "",
                        "current_tick": current_tick or 0,
                        "location_id": location_id,
                        "current_location": current_location,
                        "position": position,
                        "mood": mood or "",
                        "status": status or "",
                        "active_goal": active_goal,
                        "pending_user_action": pending_user_action,
                        "replan_log": replan_log or [],
                        "long_task_adj_log": long_task_adj_log or [],
                    }
                except Exception:
                    return agent_id, None

        results = await asyncio.gather(*(fetch_one(agent_id) for agent_id in all_agent_ids))
        return {agent_id: data for agent_id, data in results if data is not None}
