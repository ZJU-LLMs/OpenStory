from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import patch

from examples.WestWorld.plugins.agent.perceive.WestWorldPerceivePlugin import (
    WestWorldPerceivePlugin,
    merge_discovered_ids,
)
from examples.WestWorld.plugins.agent.plan.WestWorldPlanPlugin import (
    WestWorldPlanPlugin,
    _parse_decision,
)
from examples.WestWorld.plugins.agent.reflect.WestWorldReflectPlugin import (
    WestWorldReflectPlugin,
    compose_tick_memory,
    dialogue_source,
)
from examples.WestWorld.recorder.location_recorder import LocationRecorder
from examples.WestWorld.recorder.structured_location_recorder import (
    StructuredLocationRecorder,
)
from examples.WestWorld.recorder.world_object_registry import reset_object_registry
from examples.WestWorld.worldmap.loader import Location


class FakeModel:
    def __init__(self, responses: List[Any]) -> None:
        self.responses = list(responses)
        self.calls: List[Dict[str, Any]] = []
        self.config: Dict[str, Any] = {}
        self.last_usage = None

    async def chat(self, prompt: str, **kwargs: Any) -> Any:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.responses.pop(0)


class SyncFakeModel:
    def __init__(self, responses: List[Any]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.config: Dict[str, Any] = {}
        self.last_usage = None

    def chat(self, prompt: str) -> Any:
        self.calls += 1
        return self.responses.pop(0)


class FakeState:
    def __init__(self, initial: Dict[str, Any]) -> None:
        self.data = dict(initial)

    async def get_state(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    async def set_state(self, key: str, value: Any) -> None:
        self.data[key] = value

    async def add_short_term_memory(self, memory: str, tick: int) -> None:
        self.data.setdefault("short_term_memory", {})[tick] = memory


class FakeProfile:
    def __init__(self, profile: Dict[str, Any]) -> None:
        self.profile = profile

    def get_agent_profile(self) -> Dict[str, Any]:
        return self.profile


class FakeAgent:
    def __init__(self, agent_id: str, model: Any, state: FakeState, profile: Dict[str, Any]) -> None:
        self.agent_id = agent_id
        self.model = model
        self._plugins = {
            "state": state,
            "profile": FakeProfile(profile),
        }

    def get_component(self, name: str) -> Any:
        plugin = self._plugins[name]
        return SimpleNamespace(get_plugin=lambda: plugin)


class FakeController:
    def __init__(self) -> None:
        self.perceive_context: Dict[str, Any] = {}

    async def run_environment(self, environment_id: str, method: str, *args: Any) -> Any:
        if method == "read_feedback":
            return {
                "private_feedback": "你发现了松动地板。",
                "discovered_object_ids": ["obj_0"],
            }
        if method == "perceive":
            self.perceive_context = dict(args[1])
            return {"dynamic_objects": "松动地板：边缘有新鲜划痕"}
        raise AssertionError(f"unexpected environment call: {environment_id}.{method}")


class FakeWorld:
    def get(self, location_id: str) -> Any:
        return SimpleNamespace(id=location_id, description="测试场景")

    def neighbors(self, location_id: str, active_only: bool = True) -> List[str]:
        return []


def attach(plugin: Any, agent: FakeAgent) -> None:
    plugin.component = SimpleNamespace(agent=agent)


def make_location(objects: List[Dict[str, Any]] | None = None) -> Location:
    return Location(
        id="test_location",
        name="测试地点",
        region="test",
        type="room",
        active=True,
        bbox=[0, 0, 1, 1],
        adjacency=[],
        description="测试场景",
        objects=objects or [],
        default_occupants=["dolores"],
    )


class PlanDecisionTests(unittest.IsolatedAsyncioTestCase):
    def test_non_object_json_falls_back_without_exception(self) -> None:
        decision, ok = _parse_decision("[]")
        self.assertFalse(ok)
        self.assertEqual("stay", decision["action"])

        decision, ok = _parse_decision('{"action":"do","detail":7}')
        self.assertFalse(ok)
        self.assertEqual("stay", decision["action"])

    async def test_invalid_output_is_regenerated_once(self) -> None:
        model = FakeModel([
            "[]",
            json.dumps({
                "action": "do", "target": "", "detail": "检查门锁",
                "recipient_ids": [], "next_read": ["dynamic_objects"],
            }, ensure_ascii=False),
        ])
        state = FakeState({
            "location": "test_location", "daily_loop": [], "percept": {},
            "feedback": "", "awakening": 0,
        })
        agent = FakeAgent("dolores", model, state, {"agent_type": "host"})
        plugin = WestWorldPlanPlugin()
        plugin.model = model
        attach(plugin, agent)

        await plugin.execute(1)

        self.assertEqual(2, len(model.calls))
        self.assertEqual("do", state.data["plan_decision"]["action"])
        self.assertTrue(state.data["plan_trace"]["format_retry_attempted"])
        self.assertFalse(state.data["plan_trace"]["parse_fallback"])

    async def test_two_invalid_outputs_fall_back_to_stay(self) -> None:
        model = FakeModel(["[]", "null"])
        state = FakeState({
            "location": "test_location", "daily_loop": [], "percept": {},
            "feedback": "", "awakening": 0,
        })
        agent = FakeAgent("dolores", model, state, {"agent_type": "host"})
        plugin = WestWorldPlanPlugin()
        plugin.model = model
        attach(plugin, agent)

        await plugin.execute(1)

        self.assertEqual("stay", state.data["plan_decision"]["action"])
        self.assertTrue(state.data["plan_trace"]["parse_fallback"])

class DialogueMemoryTests(unittest.IsolatedAsyncioTestCase):
    def test_dialogue_memory_and_source_are_explicit(self) -> None:
        turns = [
            {"speaker": "dolores", "line": "你也记得吗？"},
            {"speaker": "teddy", "line": "我见过这个地方。"},
        ]
        memory = compose_tick_memory(
            {"action": "talk"}, "", "test_location", 3,
            incoming_dialogue=turns, agent_id="dolores",
        )
        self.assertIn("我与他人进行了一次交谈", memory)
        self.assertIn("我说：你也记得吗？", memory)
        self.assertIn("teddy说：我见过这个地方。", memory)
        self.assertEqual("self_trigger", dialogue_source(turns[0], "dolores"))
        self.assertEqual("contagion", dialogue_source(turns[1], "dolores"))

    async def test_reflect_consumes_incoming_dialogue(self) -> None:
        state = FakeState({
            "plan_decision": {"action": "talk"},
            "feedback": "",
            "location": "test_location",
            "incoming_dialogue": [{"speaker": "guest", "line": "你好"}],
        })
        model = object()
        agent = FakeAgent("dolores", model, state, {"agent_type": "guest"})
        plugin = WestWorldReflectPlugin(interval=6)
        plugin.model = model
        attach(plugin, agent)

        await plugin.execute(1)

        self.assertEqual([], state.data["incoming_dialogue"])
        self.assertIn("guest说：你好", state.data["short_term_memory"][1])


class RecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_object_registry()

    def test_json_array_is_retried_then_rejected(self) -> None:
        model = SyncFakeModel(["[]", "[]"])
        recorder = LocationRecorder(make_location(), model)

        self.assertIsNone(recorder._chat_json("prompt", retries=1))
        self.assertEqual(2, model.calls)

    def test_unresolved_action_is_not_replayed_next_tick(self) -> None:
        model = SyncFakeModel(["[]", "[]"])
        recorder = StructuredLocationRecorder(make_location(), model)
        recorder.submit_action("dolores", "观察房间", tick=1)

        with patch.dict(os.environ, {"WW_ACTION_RETRY_LIMIT": "2"}):
            recorder.tick_update(1)
        first_call_count = model.calls
        feedback = recorder.read_feedback("dolores")
        recorder.tick_update(2)

        self.assertEqual("unresolved", feedback["status"])
        self.assertFalse(recorder.fact_ledger[-1]["retry_scheduled"])
        self.assertEqual(first_call_count, model.calls)

    def test_hidden_discovery_is_validated_and_returned(self) -> None:
        location = make_location([
            {"name": "松动地板", "hidden": True, "secret": "下面藏着一封信"},
        ])
        response = {
            "actions": [{
                "agent_id": "dolores",
                "permission": True,
                "reason": "",
                "private_feedback": "你发现地板下有东西。",
                "discovered_object_ids": ["obj_0"],
                "patches": [],
                "new_objects": [],
                "destroy": [],
            }],
            "ambient": "",
            "broadcast_level": "none",
            "event_summary": "",
        }
        recorder = StructuredLocationRecorder(
            location, SyncFakeModel([json.dumps(response, ensure_ascii=False)]),
        )
        recorder.submit_action("dolores", "掀开松动地板", tick=1)

        recorder.tick_update(1)
        feedback = recorder.read_feedback("dolores")

        self.assertEqual(["obj_0"], feedback["discovered_object_ids"])
        visible = recorder.registry.objects_at_for_viewer(
            "test_location", {"obj_0"}, viewer_awakening=0,
        )
        self.assertEqual("松动地板", visible[0]["name"])

    def test_merge_discovered_ids_is_deduplicated(self) -> None:
        self.assertEqual(
            ["obj_0", "obj_1"],
            merge_discovered_ids(["obj_0"], ["obj_0", "obj_1", None]),
        )


class DiscoveryPerceiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_feedback_discovery_is_persisted_before_scene_perception(self) -> None:
        state = FakeState({
            "location": "test_location",
            "known_map": ["test_location"],
            "discovered_ids": ["obj_existing"],
            "awakening": 0,
            "plan_decision": {"action": "do", "detail": "检查地板"},
            "next_read": ["dynamic_objects"],
        })
        controller = FakeController()
        agent = FakeAgent("dolores", object(), state, {"agent_type": "host"})
        agent.controller = controller
        plugin = WestWorldPerceivePlugin(world=FakeWorld())
        attach(plugin, agent)

        await plugin.execute(2)

        self.assertEqual(["obj_existing", "obj_0"], state.data["discovered_ids"])
        self.assertEqual("你发现了松动地板。", state.data["feedback"])
        self.assertEqual(
            ["obj_existing", "obj_0"], controller.perceive_context["discovered_ids"],
        )
        self.assertEqual(
            "松动地板：边缘有新鲜划痕",
            state.data["percept"]["scene"]["dynamic_objects"],
        )


if __name__ == "__main__":
    unittest.main()
