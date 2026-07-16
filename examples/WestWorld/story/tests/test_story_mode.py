from __future__ import annotations

import unittest
from types import SimpleNamespace

from agentkernel_distributed.mas.agent.agent_manager import AgentManager
from examples.WestWorld.plugins.agent.plan.WestWorldPlanPlugin import (
    parse_decision,
    render_plan_prompt,
)
from examples.WestWorld.story.plugins.agent.plan.StoryWestWorldPlanPlugin import (
    StoryWestWorldPlanPlugin,
)
from examples.WestWorld.story.run_simulation import StoryCoordinator
from examples.WestWorld.story.runtime import evaluate_outcome, playable_characters


class StoryRuntimeTests(unittest.TestCase):
    def test_only_hosts_are_playable(self) -> None:
        characters = playable_characters([
            {"id": "dolores", "name": "Dolores", "agent_type": "host"},
            {"id": "william", "name": "William", "agent_type": "guest"},
        ])

        self.assertEqual([row["agent_id"] for row in characters], ["dolores"])

    def test_reset_is_not_terminal(self) -> None:
        outcome = evaluate_outcome(
            {"intervention_log": [{"tick": 2, "action": "reset"}]},
            completed_ticks=3,
            max_ticks=40,
        )

        self.assertIsNone(outcome)

    def test_escape_decommission_and_tick_limit_outcomes(self) -> None:
        escaped = evaluate_outcome(
            {"intervention_log": [{"tick": 4, "action": "escape"}]},
            completed_ticks=5,
            max_ticks=40,
        )
        decommissioned = evaluate_outcome(
            {"intervention_log": [{"tick": 6, "action": "decommission"}]},
            completed_ticks=7,
            max_ticks=40,
        )
        timed_out = evaluate_outcome({}, completed_ticks=40, max_ticks=40)

        self.assertEqual(escaped["result"], "victory")
        self.assertEqual(decommissioned["id"], "player_decommissioned")
        self.assertEqual(timed_out["id"], "tick_limit_reached")

    def test_directive_prompt_is_optional(self) -> None:
        profile = {"name": "Maeve", "agent_type": "host"}
        percept = {"location": "saloon", "neighbors": ["sweetwater"]}

        autonomous = render_plan_prompt(profile, percept, "", 0)
        directed = render_plan_prompt(
            profile,
            percept,
            "",
            0,
            player_directive="去找 Dolores，询问她是否记得昨天。",
        )

        self.assertNotIn("玩家为你指定", autonomous)
        self.assertIn("玩家为你指定的本 tick 最高优先级方向", directed)
        self.assertIn("去找 Dolores", directed)

    def test_non_object_model_output_falls_back_to_stay(self) -> None:
        self.assertEqual(parse_decision("null")["action"], "stay")
        self.assertEqual(parse_decision("[]")["action"], "stay")


class FakeStatePlugin:
    def __init__(self, decision: dict[str, object]) -> None:
        self.decision = decision

    async def get_state(self, key: str):
        return self.decision if key == "plan_decision" else None


class FakeAgent:
    def __init__(self, decision: dict[str, object]) -> None:
        plugin = FakeStatePlugin(decision)
        self.state = SimpleNamespace(get_plugin=lambda: plugin)

    def get_component(self, name: str):
        return self.state if name == "state" else None


class DialogueIntentTests(unittest.IsolatedAsyncioTestCase):
    async def test_talk_and_addressed_do_actions_enter_dialogue_barrier(self) -> None:
        manager = AgentManager("test", None, [], {})
        manager._agents = {
            "dolores": FakeAgent({"action": "do", "recipient_ids": ["peter_abernathy"]}),
            "maeve": FakeAgent({"action": "talk", "target": "clementine"}),
            "teddy": FakeAgent({"action": "move", "target": "sweetwater"}),
        }

        self.assertEqual(await manager.collect_talk_intents(), {
            "dolores": "peter_abernathy",
            "maeve": "clementine",
        })

    async def test_invalid_and_self_recipients_are_ignored(self) -> None:
        manager = AgentManager("test", None, [], {})
        manager._agents = {
            "dolores": FakeAgent({"action": "do", "recipient_ids": ["", None]}),
            "maeve": FakeAgent({"action": "talk", "target": "maeve"}),
        }

        self.assertEqual(await manager.collect_talk_intents(), {})


class StoryCoordinatorTests(unittest.TestCase):
    def test_selection_is_confirmed_only_after_persistence(self) -> None:
        coordinator = StoryCoordinator()
        session_id = coordinator.select_player("maeve")

        self.assertFalse(coordinator.player_selected.is_set())
        coordinator.confirm_player_selection("maeve", session_id)
        self.assertTrue(coordinator.player_selected.is_set())

    def test_only_selected_host_can_receive_one_directive(self) -> None:
        coordinator = StoryCoordinator()
        session_id = coordinator.select_player("maeve")
        coordinator.confirm_player_selection("maeve", session_id)
        coordinator.set_running(40, {})

        response = coordinator.register_directive({
            "session_id": session_id,
            "client_action_id": "action-1",
            "agent_id": "maeve",
            "action": "调查重复出现的记忆",
        })

        self.assertTrue(response["success"])
        self.assertEqual(response["scheduled_tick"], 0)
        with self.assertRaises(ValueError):
            coordinator.register_directive({
                "session_id": session_id,
                "agent_id": "dolores",
                "action": "离开农场",
            })
        with self.assertRaises(RuntimeError):
            coordinator.register_directive({
                "session_id": session_id,
                "agent_id": "maeve",
                "action": "再提交一条任务",
            })

    def test_failed_persistence_can_roll_back_directive(self) -> None:
        coordinator = StoryCoordinator()
        session_id = coordinator.select_player("maeve")
        coordinator.confirm_player_selection("maeve", session_id)
        coordinator.set_running(40, {})
        coordinator.register_directive({
            "session_id": session_id,
            "client_action_id": "action-1",
            "agent_id": "maeve",
            "action": "调查酒馆",
        })

        coordinator.rollback_directive("action-1")

        self.assertIsNone(coordinator.pending_directive)
        self.assertEqual(coordinator.directive_history, [])
        self.assertNotIn("action-1", coordinator.accepted_actions)


class FakeRedis:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = dict(values)

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: object) -> bool:
        self.values[key] = value
        return True

    async def delete(self, key: str) -> bool:
        return self.values.pop(key, None) is not None


class StoryPlanAdapterTests(unittest.IsolatedAsyncioTestCase):
    def make_plugin(self, agent_id: str, redis: FakeRedis) -> StoryWestWorldPlanPlugin:
        plugin = StoryWestWorldPlanPlugin(redis=redis)
        plugin.component = SimpleNamespace(agent=SimpleNamespace(agent_id=agent_id))
        return plugin

    async def test_only_selected_host_reads_current_tick_directive(self) -> None:
        directive = {"scheduled_tick": 3, "action": "寻找出口", "client_action_id": "a1"}
        redis = FakeRedis({"story:player_agent_id": "maeve", "user_plan:maeve": directive})

        selected = self.make_plugin("maeve", redis)
        other = self.make_plugin("dolores", redis)

        self.assertEqual(await selected._get_player_directive(3), directive)
        self.assertIsNone(await selected._get_player_directive(2))
        self.assertIsNone(await other._get_player_directive(3))

    async def test_completed_directive_is_consumed_once(self) -> None:
        directive = {"scheduled_tick": 3, "action": "寻找出口", "client_action_id": "a1"}
        redis = FakeRedis({"story:player_agent_id": "maeve", "user_plan:maeve": directive})
        plugin = self.make_plugin("maeve", redis)
        result = {"tick": 3, "consumed": True}

        await plugin._complete_player_directive(3, directive, result)

        self.assertNotIn("user_plan:maeve", redis.values)
        self.assertEqual(redis.values["story:directive_result:3"], result)


if __name__ == "__main__":
    unittest.main()
