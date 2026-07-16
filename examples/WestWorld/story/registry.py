"""Resource registry for WestWorld story mode."""
from __future__ import annotations

from examples.WestWorld.registry import RESOURCES_MAPS as _BASE_RESOURCES_MAPS
from examples.WestWorld.story.plugins.agent.plan.StoryWestWorldPlanPlugin import (
    StoryWestWorldPlanPlugin,
)


RESOURCES_MAPS = {
    **_BASE_RESOURCES_MAPS,
    "agent_plugins": {
        **_BASE_RESOURCES_MAPS["agent_plugins"],
        "StoryWestWorldPlanPlugin": StoryWestWorldPlanPlugin,
    },
}
