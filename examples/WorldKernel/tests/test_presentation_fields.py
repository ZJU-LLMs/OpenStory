import asyncio
import json
from pathlib import Path
import sys
import uuid
from unittest.mock import AsyncMock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from worldkernel.presentation import (
    PresentationService,
    build_stage1_manifest,
    discover_presentation_paths,
)
from worldkernel.stage1.ontology_selector import _parse_extra_field
from worldkernel.stage1.pipeline import _build_dim_yaml
from worldkernel.stage1.types import FieldDef, FieldPresentationDef
from worldkernel.stage3.runtime import Stage3RuntimeManager

def _make_historical_session(tmp_path: Path) -> Path:
    session = tmp_path / "historical-world"
    identity = {
        "dim_name": "IdentityDim",
        "id": {"type": "str"},
        "name": {"type": "str"},
        "mystery_signal_strength": {"type": "str", "option": True},
        "home_id": {"type": "str", "ref": "location"},
    }
    dims = session / "configs" / "agent" / "dims"
    dims.mkdir(parents=True)
    (dims / "identity.yaml").write_text(
        yaml.dump(identity, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    world_path = session / "generated" / "plan" / "world_background.json"
    world_path.parent.mkdir(parents=True)
    world_path.write_text(json.dumps({"world_name": "测试世界"}, ensure_ascii=False), encoding="utf-8")
    return session


def _test_root() -> Path:
    return ROOT / "tests" / f".presentation-{uuid.uuid4().hex}"


def _remove_tree(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            path.rmdir()
    root.rmdir()


def test_extra_fields_accept_new_and_legacy_formats() -> None:
    field, presentation = _parse_extra_field({
        "name": "memory_asset_level",
        "type": "str",
        "label_zh": "记忆资产等级",
        "player_visible": True,
    })
    assert field.name == "memory_asset_level"
    assert field.type == "str"
    assert presentation.label_zh == "记忆资产等级"

    legacy_field, legacy_presentation = _parse_extra_field("risk_score: float (legacy)")
    assert legacy_field.name == "risk_score"
    assert legacy_field.type == "float"
    assert legacy_presentation.label_zh == ""


def test_presentation_metadata_does_not_enter_inference_yaml() -> None:
    field = FieldDef(name="memory_asset_level", type="str", required=False)
    presentation = FieldPresentationDef(label_zh="记忆资产等级", player_visible=True)
    output = _build_dim_yaml("identity", [field])

    assert output["memory_asset_level"] == {"type": "str", "option": True}
    serialized = yaml.dump(output, allow_unicode=True)
    assert presentation.label_zh not in serialized
    assert "player_visible" not in serialized
    assert "label_zh" not in serialized


def test_historical_manifest_translates_unknown_fields_and_hides_refs() -> None:
    root = _test_root()

    async def exercise() -> dict:
        session = _make_historical_session(root)
        service = PresentationService()
        response_json = json.dumps(
            {"character.identity.mystery_signal_strength": "神秘信号强度"},
            ensure_ascii=False,
        )
        with patch("worldkernel.presentation.chat_json", new=AsyncMock(return_value=response_json)):
            first = await service.get_manifest(session)
            assert first["status"] == "pending"
            await asyncio.gather(*service._tasks.values())
            final = await service.get_manifest(session)
        await service.close()
        return final

    try:
        manifest = asyncio.run(exercise())
        assert manifest["status"] == "ready"
        assert manifest["fields"]["character.identity.mystery_signal_strength"]["label"] == "神秘信号强度"
        assert manifest["fields"]["character.identity.home_id"]["visible"] is False
        assert manifest["fields"]["character.identity.id"]["visible"] is False
    finally:
        _remove_tree(root)


def test_stage1_manifest_keeps_visual_and_ids_hidden() -> None:
    root = _test_root()
    try:
        session = _make_historical_session(root)
        visual_path = session / "generated" / "plan" / "world_background.json"
        visual_path.write_text(
            json.dumps({"world_name": "测试世界", "visual_profile": {"art_style": "像素"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        manifest = build_stage1_manifest(
            session,
            {
                "character.identity.mystery_signal_strength": FieldPresentationDef(
                    label_zh="神秘信号强度", player_visible=True
                )
            },
        )
        assert manifest["fields"]["world.visual_profile"]["visible"] is False
        assert manifest["fields"]["character.identity.id"]["visible"] is False
        assert manifest["fields"]["character.identity.mystery_signal_strength"]["label"] == "神秘信号强度"
    finally:
        _remove_tree(root)


def test_runtime_state_includes_latest_location_snapshot() -> None:
    manager = Stage3RuntimeManager(ROOT)
    manager.last_locations_data = [{"identity": {"id": "loc-1", "name": "大厅"}, "state": {"capacity": 9}}]
    state = manager.state()
    assert state["locations"][0]["state"]["capacity"] == 9


def test_target_world_discovers_custom_acceptance_fields() -> None:
    session = ROOT / "templates" / "0d1f1cab-0982-4104-87c4-df394e63cf81"
    paths, _referenced = discover_presentation_paths(session)
    assert "character.identity.identity_anchor_code" in paths
    assert "character.identity.memory_asset_level" in paths
    assert "location.state.structural_integrity" in paths


def test_frontend_never_title_cases_unknown_field_keys() -> None:
    script = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")
    assert "function isPresentedField" in script
    assert "部分字段名称正在本地化" in script
    assert "part[0].toUpperCase()" not in script
    assert "setDetailHeader('World Setting'" not in script
    assert "setDetailHeader('Character'" not in script
    assert "setDetailHeader('Location'" not in script
    assert "item.profile?.name || item.id" not in script
    assert "region.name || region.location_id" not in script
