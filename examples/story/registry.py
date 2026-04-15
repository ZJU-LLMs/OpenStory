from examples.story.plugins.agent.perceive.BasicPerceivePlugin import BasicPerceivePlugin
from examples.story.plugins.agent.plan.BasicPlanPlugin import BasicPlanPlugin
from examples.story.plugins.agent.invoke.BasicInvokePlugin import BasicInvokePlugin
from examples.story.plugins.agent.state.BasicStatePlugin import BasicStatePlugin
from examples.story.plugins.agent.reflect.BasicReflectPlugin import BasicReflectPlugin
from examples.story.plugins.action.move.BasicMovePlugin import BasicMovePlugin
from examples.story.plugins.action.communication.BasicCommunicationPlugin import BasicCommunicationPlugin
from examples.story.plugins.action.other.BasicOtherActionPlugin import BasicOtherActionPlugin
from examples.story.plugins.environment.relation.BasicRelationPlugin import BasicRelationPlugin

RESOURCES_MAPS = {
    "BasicPerceivePlugin": BasicPerceivePlugin,
    "BasicPlanPlugin": BasicPlanPlugin,
    "BasicInvokePlugin": BasicInvokePlugin,
    "BasicStatePlugin": BasicStatePlugin,
    "BasicReflectPlugin": BasicReflectPlugin,
    "BasicMovePlugin": BasicMovePlugin,
    "BasicCommunicationPlugin": BasicCommunicationPlugin,
    "BasicOtherActionPlugin": BasicOtherActionPlugin,
    "BasicRelationPlugin": BasicRelationPlugin,
}
