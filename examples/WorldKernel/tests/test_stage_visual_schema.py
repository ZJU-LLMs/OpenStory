from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from worldkernel.architect.tools.generators.base_generator import introspect_schema
from worldkernel.stage1.ontology_selector import _build_entity_template
from worldkernel.stage1.pipeline import _generate_pydantic_models, _save_entity_configs


def _load_model_class(model_path: Path, class_name: str):
    spec = importlib.util.spec_from_file_location(model_path.stem, model_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


def test_stage1_character_and_location_visual_templates_are_single_fixed_field():
    character = _build_entity_template(
        "character",
        {"dimensions": {"visual": {"extra": ["hair_color", "visual_prompt"]}}},
    )
    location = _build_entity_template(
        "location",
        {"dimensions": {"visual": {"extra": ["main_material", "visual_description"]}}},
    )

    character_visual = character.dimensions["visual"].fields
    location_visual = location.dimensions["visual"].fields

    assert [field.name for field in character_visual] == ["visual"]
    assert [field.type for field in character_visual] == ["str"]
    assert [field.required for field in character_visual] == [True]
    assert [field.name for field in location_visual] == ["visual"]
    assert [field.type for field in location_visual] == ["str"]
    assert [field.required for field in location_visual] == [True]


def test_stage1_codegen_emits_visual_as_top_level_string():
    templates = {
        "character": _build_entity_template("character", {"dimensions": {}}),
        "location": _build_entity_template("location", {"dimensions": {}}),
    }

    output_root = Path(__file__).resolve().parent / f".tmp_stage_visual_schema_{uuid4().hex}"
    try:
        configs_dir = output_root / "configs"
        models_dir = output_root / "models"
        _save_entity_configs(configs_dir, templates)
        _generate_pydantic_models(models_dir, configs_dir)

        AgentModel = _load_model_class(models_dir / "agent_model.py", "AgentModel")
        LocationModel = _load_model_class(models_dir / "location_model.py", "LocationModel")

        assert AgentModel.model_fields["visual"].annotation is str
        assert LocationModel.model_fields["visual"].annotation is str
        assert isinstance(AgentModel().visual, str)
        assert isinstance(LocationModel().visual, str)
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_schema_introspection_includes_top_level_visual_string():
    class IdentityDim(BaseModel):
        id: str = ""
        name: str = ""

    class AgentModel(BaseModel):
        identity: IdentityDim = IdentityDim()
        visual: str = ""

    schema_description = introspect_schema(AgentModel)

    assert "### 字段: visual" in schema_description
    assert "visual(str)" in schema_description
    assert "identity" in schema_description


def test_visual_generation_and_review_prompts_require_detailed_image_prompts():
    prompt_dir = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "worldkernel"
        / "architect"
        / "tools"
        / "generators"
        / "prompts"
    )

    character_generation = (prompt_dir / "character_generation_user.md").read_text(encoding="utf-8")
    location_generation = (prompt_dir / "location_generation_user.md").read_text(encoding="utf-8")
    character_review = (prompt_dir / "character_review_user.md").read_text(encoding="utf-8")
    location_review = (prompt_dir / "location_review_user.md").read_text(encoding="utf-8")
    character_retry = (prompt_dir / "character_retry_user.md").read_text(encoding="utf-8")
    location_retry = (prompt_dir / "location_retry_user.md").read_text(encoding="utf-8")

    assert "年龄感、体态轮廓、面部特征、发型、服装款式" in character_generation
    assert "建筑或空间结构、主体形状、可识别轮廓" in location_generation
    assert "不能写成对象、数组，也不能拆成子字段" in character_generation
    assert "不能写成对象、数组，也不能拆成子字段" in location_generation
    assert "visual_prompt_quality" in character_review
    assert "visual_prompt_quality" in location_review
    assert "必须重写完整的顶层 `visual` 字符串" in character_retry
    assert "必须重写完整的顶层 `visual` 字符串" in location_retry
