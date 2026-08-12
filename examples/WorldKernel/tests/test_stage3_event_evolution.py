import ast
import asyncio
import copy
import json
import uuid
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _load_invoke_helpers():
    source_path = ROOT / "plugins" / "agent" / "invoke" / "BasicInvokePlugin.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    invoke_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "BasicInvokePlugin"
    )
    helper_names = {
        "_parse_event_json",
        "_strip_location_from_action",
        "_line",
        "_normalize_line",
        "_make_event",
    }
    helpers = [
        node for node in invoke_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in helper_names
    ]
    helper_class = ast.ClassDef(
        name="InvokeHelpers",
        bases=[],
        keywords=[],
        body=helpers,
        decorator_list=[],
    )
    ast.fix_missing_locations(helper_class)
    namespace = {"Any": Any, "json": json, "uuid": uuid}
    exec(compile(ast.Module(body=[helper_class], type_ignores=[]), str(source_path), "exec"), namespace)
    namespace["BasicInvokePlugin"] = namespace["InvokeHelpers"]
    return namespace["InvokeHelpers"]


def _load_class_methods(path: Path, class_name: str, method_names: set[str], namespace: dict[str, Any]):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    source_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    extracted = [
        node for node in source_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in method_names
    ]
    test_class = ast.ClassDef(
        name=f"Test{class_name}", bases=[], keywords=[], body=extracted, decorator_list=[]
    )
    ast.fix_missing_locations(test_class)
    exec(compile(ast.Module(body=[test_class], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[f"Test{class_name}"]


def test_event_action_removes_location_description() -> None:
    helpers = _load_invoke_helpers()

    action = helpers._strip_location_from_action("正在中央档案馆执行：逐页核对旧账", "中央档案馆")

    assert "中央档案馆" not in action
    assert action == "逐页核对旧账"


def test_event_json_accepts_fenced_model_output() -> None:
    helpers = _load_invoke_helpers()

    event = helpers._parse_event_json(
        '```json\n{"current_action":"核对账目","event_summary":"发现编号错位。","lines":["旁白：[发现]编号错位。"]}\n```'
    )

    assert event["current_action"] == "核对账目"
    assert event["lines"] == ["旁白：[发现]编号错位。"]


def test_structured_event_has_shared_identity_and_dialogue_objects() -> None:
    helpers = _load_invoke_helpers()

    event = helpers._make_event(
        3,
        event_type="interaction",
        current_action="说明来意",
        current_actions={"a": "说明来意", "b": "作出回应"},
        summary="双方交换了信息。",
        participants=["a", "b"],
        lines=["a：[开口]我们谈谈。", {"speaker": "b", "action": "回应", "text": "好。"}],
        location={"id": "loc-1", "name": "会议室"},
        importance=8,
    )

    assert event["event_id"]
    assert event["initiator"] == "a"
    assert event["current_actions"]["b"] == "作出回应"
    assert event["location"] == {"id": "loc-1", "name": "会议室"}
    assert event["lines"][0] == {
        "speaker": "a", "action": "开口", "text": "我们谈谈。", "kind": "dialogue"
    }


def test_event_store_appends_multiple_events_in_the_same_tick() -> None:
    path = ROOT / "plugins" / "agent" / "state" / "BasicStatePlugin.py"
    state_class = _load_class_methods(
        path,
        "BasicStatePlugin",
        {"add_event", "get_event_log", "_trim_event_log"},
        {"Any": Any, "Dict": dict, "copy": copy, "_MAX_EVENTS": 500},
    )
    state = object.__new__(state_class)
    state.agent_id = "a"
    state.state_data = {"event_log": {}}

    asyncio.run(state.add_event(2, {"event_id": "one", "summary": "first"}))
    asyncio.run(state.add_event(2, {"event_id": "two", "summary": "second"}))
    asyncio.run(state.add_event(2, {"event_id": "two", "summary": "duplicate"}))
    events = asyncio.run(state.get_event_log())

    assert [event["event_id"] for event in events] == ["one", "two"]

    state.state_data["event_log"] = [{"tick": 1, "event_id": "legacy", "summary": "old"}]
    asyncio.run(state.add_event(1, {"event_id": "new", "summary": "new"}))
    assert [event["event_id"] for event in asyncio.run(state.get_event_log())] == ["legacy", "new"]


def test_relation_effect_is_bounded_and_preserves_relation_type() -> None:
    path = ROOT / "plugins" / "environment" / "relation" / "BasicRelationPlugin.py"
    relation_class = _load_class_methods(
        path,
        "BasicRelationPlugin",
        {"get_relation_between", "apply_relation_delta"},
        {"Any": Any},
    )
    relation = object.__new__(relation_class)
    relation.relations = [{"source": "a", "target": "b", "relation": "盟友", "properties": {}}]

    result = asyncio.run(relation.apply_relation_delta("a", "b", 130, "越界", "event"))
    assert result["applied"] is False
    result = asyncio.run(relation.apply_relation_delta("a", "b", 15, "互相帮助", "event"))
    assert result["after"] == 15
    assert relation.relations[0]["relation"] == "盟友"


def test_stage3_exposes_structured_events_to_the_frontend() -> None:
    runtime = (ROOT / "src" / "worldkernel" / "stage3" / "runtime.py").read_text(encoding="utf-8")
    manager = (ROOT / "BasicPodManager.py").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")
    invoke = (ROOT / "plugins" / "agent" / "invoke" / "BasicInvokePlugin.py").read_text(encoding="utf-8")

    assert '"event_log": data.get("event_log") or []' in runtime
    assert 'remote_call("state", "get_event_log")' in manager
    assert "function renderEventLog(events)" in frontend
    assert "计划是意图，不是既成事实" in invoke
    assert "严格遵守《红楼梦》" not in invoke


def test_full_alignment_contract_is_present_without_fixed_story_prompts() -> None:
    invoke = (ROOT / "plugins" / "agent" / "invoke" / "BasicInvokePlugin.py").read_text(encoding="utf-8")
    reflect = (ROOT / "plugins" / "agent" / "reflect" / "BasicReflectPlugin.py").read_text(encoding="utf-8")
    move = (ROOT / "plugins" / "action" / "move" / "BasicMovePlugin.py").read_text(encoding="utf-8")
    server = (ROOT / "src" / "worldkernel" / "server.py").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")

    assert "_MAX_DIALOGUE_TURNS = 6" in invoke
    assert "_generate_interaction_event" in invoke
    assert "target_active" in invoke
    assert "effect_results" in invoke
    assert "get_event_log" in reflect
    assert "replanned_tick" in reflect
    assert "[END] 标记表示离场" not in reflect
    assert '"route_resolution": "frontend"' in move
    assert '"space", "find_route"' not in move
    assert '"/api/stage3/runtime/agents/{agent_id}/next-action"' in server
    assert "function startEventPlayback()" in frontend
    assert "function openEventDetail(event)" in frontend
    assert "function renderNextActionForm(agent)" in frontend

    forbidden = ["第80回", "第 80 回", "宗法礼制", "古代时辰"]
    combined = invoke + reflect
    assert not any(term in combined for term in forbidden)


def test_stage3_excludes_semantic_only_locations_and_paths() -> None:
    from worldkernel.stage3.adapter import _transform_locations, _transform_paths

    locations = [
        {"identity": {"id": "mapped", "name": "地图地点"}, "access": {}, "state": {}},
        {"identity": {"id": "semantic-only", "name": "仅语义地点"}, "access": {}, "state": {}},
    ]
    spatial = {
        "regions": [
            {
                "location_id": "mapped",
                "bounds": {"x": 1, "y": 2, "w": 3, "h": 4},
                "entrance": {"x": 2, "y": 5},
            }
        ],
        "routes": [],
    }
    warnings: list[str] = []
    rows, location_names = _transform_locations(locations, spatial, warnings)

    assert [row["id"] for row in rows] == ["mapped"]
    assert location_names == {"mapped": "地图地点"}
    assert "bounds" not in rows[0]
    assert "entrance" not in rows[0]
    assert any("semantic-only location" in warning for warning in warnings)

    paths = [
        {
            "identity": {"id": "unmapped-path"},
            "endpoints": {"from_id": "mapped", "to_id": "mapped"},
            "conditions": {},
        }
    ]
    assert _transform_paths(paths, spatial, location_names, warnings) == []
    assert any("semantic-only path" in warning for warning in warnings)


def test_stage3_uses_mapped_semantic_locations_without_map_geometry() -> None:
    adapter = (ROOT / "src" / "worldkernel" / "stage3" / "adapter.py").read_text(encoding="utf-8")
    space = (ROOT / "plugins" / "environment" / "space" / "BasicSpacePlugin.py").read_text(encoding="utf-8")
    runtime = (ROOT / "src" / "worldkernel" / "stage3" / "runtime.py").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")
    environment_config = (ROOT / "configs" / "environment_config.yaml").read_text(encoding="utf-8")

    assert "skipped semantic-only location" in adapter
    assert '"bounds": bounds' not in adapter
    assert '"entrance": entrance' not in adapter
    assert '"position": None' in adapter
    assert "does not load or reason over route topology" in space
    assert "paths: map_paths" not in environment_config
    assert "agents: map_agents" not in environment_config
    assert 'bounds = item.get("bounds") or {}' not in runtime
    assert "buildRouteMotionPoints" in frontend
    action_form = frontend.split("function renderNextActionForm(agent)", 1)[1].split("function bindNextActionForm", 1)[0]
    assert "spatial?.regions" in action_form
    assert "semanticLocations.length" not in action_form
