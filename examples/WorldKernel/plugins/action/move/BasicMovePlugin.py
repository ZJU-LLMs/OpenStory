"""Move action: update an agent's logical location after access validation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_PATH = Path(__file__).resolve().parents[3]
if str(PROJECT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH))

from plugins._optional_deps import ensure_optional_agentkernel_imports

ensure_optional_agentkernel_imports()

from agentkernel_distributed.mas.action.base.plugin_base import OtherActionsPlugin
from agentkernel_distributed.toolkit.utils.annotation import AgentCall
from agentkernel_distributed.types.schemas.action import ActionResult


def _result(method: str, ok: bool, message: str, data: dict[str, Any] | None = None) -> ActionResult:
    if ok:
        return ActionResult.success(method_name=method, message=message, data=data or {})
    return ActionResult.error(method_name=method, message=message, data=data or {})


class BasicMovePlugin(OtherActionsPlugin):
    """Validates destination access without reasoning over map route geometry."""

    def __init__(self, redis: Any = None) -> None:
        super().__init__()
        self.redis = redis
        self.model: Any = None
        self.controller: Any = None

    async def init(self, model_router: Any = None, controller: Any = None) -> None:
        self.model = model_router
        self.controller = controller

    async def _log_action(self, *args: Any, **kwargs: Any) -> None:
        return None

    @AgentCall
    async def move_to(self, agent_id: str, location: str) -> ActionResult:
        if not getattr(self, "controller", None):
            return _result("move_to", False, "controller unavailable")

        profile = await self.controller.run_agent_method(agent_id, "profile", "get_agent_profile")
        from_location_id = await self.controller.run_agent_method(
            agent_id, "state", "get_state", "location_id"
        )
        can_enter = await self.controller.run_environment("space", "can_agent_enter", profile, location)
        if not can_enter.get("allowed"):
            return _result("move_to", False, can_enter.get("reason", "location is not accessible"))

        target_location_id = can_enter.get("location_id")
        await self.controller.run_environment(
            "space", "update_agent_location", agent_id, target_location_id
        )
        await self.controller.run_agent_method(agent_id, "state", "set_state", "location_id", target_location_id)
        await self.controller.run_agent_method(
            agent_id, "state", "set_state", "current_location", can_enter.get("location_name")
        )
        return _result(
            "move_to", True, "move completed",
            {
                "from_location_id": from_location_id,
                "location_id": target_location_id,
                "location": can_enter.get("location_name"),
                "route_resolution": "frontend",
            },
        )
