from agentkernel_distributed.toolkit.models.api.openai import OpenAIProvider
from agentkernel_distributed.mas.system.components import Messager, Recorder, Timer
from agentkernel_distributed.mas.action.components import CommunicationComponent, OtherActionsComponent
from agentkernel_distributed.mas.agent.components import *
from agentkernel_distributed.mas.environment.components import RelationComponent, SpaceComponent
from agentkernel_distributed.toolkit.storages import RedisKVAdapter
from examples.deduction.BasicController import BasicController
from examples.deduction.BasicPodManager import BasicPodManager

from examples.deduction.plugins.agent.invoke.BasicInvokePlugin import BasicInvokePlugin
from examples.deduction.plugins.agent.perceive.BasicPerceivePlugin import BasicPerceivePlugin
from examples.deduction.plugins.agent.profile.BasicProfliePlugin import BasicProfilePlugin
from examples.deduction.plugins.agent.state.BasicStatePlugin import BasicStatePlugin
from examples.deduction.plugins.agent.state.component import BasicStateComponent
from examples.deduction.plugins.agent.plan.BasicPlanPlugin import BasicPlanPlugin
from examples.deduction.plugins.agent.reflect.BasicReflectPlugin import BasicReflectPlugin

from examples.deduction.plugins.action.communication.BasicCommunicationPlugin import BasicCommunicationPlugin
from examples.deduction.plugins.action.move.BasicMovePlugin import BasicMovePlugin
from examples.deduction.plugins.action.other.BasicOtherActionPlugin import BasicOtherActionPlugin
from examples.deduction.plugins.environment.relation.BasicRelationPlugin import BasicRelationPlugin
from examples.deduction.plugins.environment.space.BasicSpacePlugin import BasicSpacePlugin

# Agent plugin and component registry

agent_plugin_calss_map = {
    'BasicPerceivePlugin': BasicPerceivePlugin,
    'BasicProfilePlugin': BasicProfilePlugin,
    'BasicStatePlugin': BasicStatePlugin,
    'BasicPlanPlugin': BasicPlanPlugin,
    'BasicInvokePlugin': BasicInvokePlugin,
    'BasicReflectPlugin': BasicReflectPlugin,
}

agent_component_class_map = {
    "profile": ProfileComponent,
    "state": BasicStateComponent,
    "plan": PlanComponent,
    "perceive": PerceiveComponent,
    "reflect": ReflectComponent,
    "invoke": InvokeComponent,
}

# Action plugin and component registry
action_component_class_map = {
    "communication": CommunicationComponent,
    "move": OtherActionsComponent,
    "otheractions": OtherActionsComponent,
}
action_plugin_class_map = {
    "BasicCommunicationPlugin": BasicCommunicationPlugin,
    "BasicMovePlugin": BasicMovePlugin,
    "BasicOtherActionPlugin": BasicOtherActionPlugin,
}
# Model class
model_class_map = {
    "OpenAIProvider": OpenAIProvider,
}
# Environment plugin and component registry
environment_component_class_map = {
    "relation": RelationComponent,
    "space": SpaceComponent,
}
environment_plugin_class_map = {
    "BasicRelationPlugin": BasicRelationPlugin,
    "BasicSpacePlugin": BasicSpacePlugin,
}

system_component_class_map = {
    "messager": Messager,
    "recorder": Recorder,
    "timer": Timer,
}

# Adapter class mapping
adapter_class_map = {
    "RedisKVAdapter": RedisKVAdapter,
}

RESOURCES_MAPS = {
    "agent_components": agent_component_class_map,
    "agent_plugins": agent_plugin_calss_map,
    "action_components": action_component_class_map,
    "action_plugins": action_plugin_class_map,
    "environment_components": environment_component_class_map,
    "environment_plugins": environment_plugin_class_map,
    "system_components": system_component_class_map,
    "models": model_class_map,
    "adapters": adapter_class_map,
    "controller": BasicController,
    "pod_manager": BasicPodManager,
}