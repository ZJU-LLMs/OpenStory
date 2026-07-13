"""正式仿真的资源注册表。"""
from agentkernel_distributed.mas.agent.components import (
    InvokeComponent,
    PerceiveComponent,
    PlanComponent,
    ProfileComponent,
    ReflectComponent,
)
from agentkernel_distributed.mas.environment.components import RelationComponent, get_or_create_component_class
from agentkernel_distributed.mas.system.components import Messager, Timer
from agentkernel_distributed.toolkit.models.api.openai import OpenAIProvider
from agentkernel_distributed.toolkit.storages import RedisKVAdapter

from examples.story_of_the_stone.BasicController import BasicController
from examples.story_of_the_stone.plugins.agent.profile.BasicProfliePlugin import BasicProfilePlugin
from examples.story_of_the_stone.plugins.agent.state.BasicStatePlugin import BasicStatePlugin
from examples.story_of_the_stone.plugins.agent.state.component import BasicStateComponent
from examples.story_of_the_stone.plugins.environment.relation.BasicRelationPlugin import BasicRelationPlugin
from examples.WestWorld.WestWorldPodManager import WestWorldPodManager
from examples.WestWorld.plugins.agent.invoke.WestWorldInvokePlugin import WestWorldInvokePlugin
from examples.WestWorld.plugins.agent.perceive.WestWorldPerceivePlugin import WestWorldPerceivePlugin
from examples.WestWorld.plugins.agent.plan.RandomWalkPlanPlugin import RandomWalkPlanPlugin
from examples.WestWorld.plugins.agent.plan.WestWorldPlanPlugin import WestWorldPlanPlugin
from examples.WestWorld.plugins.agent.reflect.WestWorldReflectPlugin import WestWorldReflectPlugin
from examples.WestWorld.plugins.environment.overseer.OverseerPlugin import OverseerPlugin
from examples.WestWorld.plugins.environment.scene.LocationRecorderPlugin import make_scene_plugin_class
from examples.WestWorld.worldmap.loader import get_world_map

_WORLD = get_world_map()
_ACTIVE = sorted(_WORLD.active_ids())

RESOURCES_MAPS = {
    "agent_components": {
        "profile": ProfileComponent,
        "perceive": PerceiveComponent,
        "plan": PlanComponent,
        "invoke": InvokeComponent,
        "state": BasicStateComponent,
        "reflect": ReflectComponent,
    },
    "agent_plugins": {
        "BasicProfilePlugin": BasicProfilePlugin,
        "BasicStatePlugin": BasicStatePlugin,
        "WestWorldPerceivePlugin": WestWorldPerceivePlugin,
        "RandomWalkPlanPlugin": RandomWalkPlanPlugin,
        "WestWorldPlanPlugin": WestWorldPlanPlugin,
        "WestWorldInvokePlugin": WestWorldInvokePlugin,
        "WestWorldReflectPlugin": WestWorldReflectPlugin,
    },
    "action_components": {},
    "action_plugins": {},
    "environment_components": {
        "relation": RelationComponent,
        "overseer": get_or_create_component_class("overseer"),
        **{f"scene_{lid}": get_or_create_component_class(f"scene_{lid}") for lid in _ACTIVE},
    },
    "environment_plugins": {
        "BasicRelationPlugin": BasicRelationPlugin,
        "OverseerPlugin": OverseerPlugin,
        **{f"Scene_{lid}_Plugin": make_scene_plugin_class(lid) for lid in _ACTIVE},
    },
    "system_components": {
        "messager": Messager,
        "timer": Timer,
    },
    "models": {
        "OpenAIProvider": OpenAIProvider,
    },
    "adapters": {
        "RedisKVAdapter": RedisKVAdapter,
    },
    "controller": BasicController,
    "pod_manager": WestWorldPodManager,
}
