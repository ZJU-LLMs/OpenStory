from __future__ import annotations

import json
from pathlib import Path

import yaml

from worldkernel.stage1.types import (
    EntityTemplate,
    GenerationPlan,
    IntentResult,
    VisualProfile,
    WorldTemplate,
)
from worldkernel.stage1.world_spec import SessionInfo
from worldkernel.constraints import GenerationConstraints, load_generation_constraints
from worldkernel.stage1.generation_planner import plan_generation
from worldkernel.stage1.intent_parser import parse_intent
from worldkernel.stage1.ontology_selector import generate_templates
from worldkernel.stage1.world_type_classifier import build_world_template

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "templates"


class Stage1Error(Exception):
    def __init__(self, step: str, cause: Exception) -> None:
        self.step = step
        self.cause = cause
        super().__init__(f"Stage 1 failed at [{step}]: {cause}")


async def run_stage1(
    raw_input: str,
    constraints: GenerationConstraints | None = None,
) -> SessionInfo:
    if constraints is None:
        constraints = load_generation_constraints()
    session = SessionInfo(source_input=raw_input)
    out_dir = _TEMPLATES_DIR / session.session_id

    try:
        intent: IntentResult = await parse_intent(raw_input)
    except Exception as e:
        raise Stage1Error("intent_parser", e) from e

    try:
        world_type: WorldTemplate = await build_world_template(intent)
    except Exception as e:
        raise Stage1Error("world_type_classifier", e) from e

    try:
        plan: GenerationPlan = await plan_generation(intent, world_type, constraints=constraints)
    except Exception as e:
        raise Stage1Error("generation_planner", e) from e

    try:
        templates: dict[str, EntityTemplate] = await generate_templates(intent, world_type, plan)
    except Exception as e:
        raise Stage1Error("ontology_selector", e) from e

    _save_json(out_dir / "generated" / "world_template.json", world_type.model_dump())
    _save_plan(out_dir / "generated" / "plan", plan, world_type, session.session_id)
    _save_templates(out_dir / "generated" / "templates", templates)
    _save_entity_configs(out_dir / "configs", templates)
    _generate_pydantic_models(out_dir / "models", out_dir / "configs")
    _save_schema_manifest(out_dir / "models")
    _save_artifact_manifest(out_dir, session.session_id)

    return session


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _save_plan(plan_dir: Path, plan: GenerationPlan, world_type: WorldTemplate, session_id: str) -> None:
    plan_dir.mkdir(parents=True, exist_ok=True)

    _save_json(plan_dir / "ontology_hints.json", plan.ontology_hints.model_dump())

    catalog: dict = {
        "session_id": session_id,
        "instance_seeds": {"location": [], "character": []},
    }
    for archetype_id, seeds in plan.entity_plan.locations.items():
        for s in seeds:
            d = s.model_dump()
            d["archetype_id"] = archetype_id
            d.pop("entity_type", None)
            catalog["instance_seeds"]["location"].append(d)
    for archetype_id, seeds in plan.entity_plan.characters.items():
        for s in seeds:
            d = s.model_dump()
            d["archetype_id"] = archetype_id
            d.pop("entity_type", None)
            catalog["instance_seeds"]["character"].append(d)
    _save_json(plan_dir / "instance_seed_catalog.json", catalog)

    _save_json(plan_dir / "execution_plan.json", {"steps": [s.model_dump() for s in plan.steps]})

    bg = {
        "world_name": world_type.world_name,
        "world_origin_summary": world_type.world_origin_summary,
        "primary": world_type.primary,
        "secondary": world_type.secondary,
        "tags": world_type.tags,
        "scope": world_type.scope,
        "simulation_start": world_type.simulation_start.model_dump(),
        "visual_profile": _build_visual_profile(world_type).model_dump(),
        "world_constraints": [c.model_dump() for c in world_type.world_constraints],
    }
    _save_json(plan_dir / "world_background.json", bg)


def _build_visual_profile(world_type: WorldTemplate) -> VisualProfile:
    """Build a world-level visual contract without location-specific facts."""
    profile = world_type.visual_profile
    if any((
        profile.art_style,
        profile.camera_projection,
        profile.era_style,
        profile.color_palette,
        profile.lighting_weather,
        profile.material_texture,
        profile.environmental_motifs,
        profile.atmosphere,
        profile.edge_blending_style,
        profile.negative_visual_constraints,
    )):
        return profile

    tags = ", ".join(world_type.tags)
    summary = world_type.world_origin_summary or world_type.primary or "生成的世界"
    atmosphere = f"{summary}；标签：{tags}" if tags else summary
    return VisualProfile(
        art_style="俯视角手工卡通像素风世界地图，原生低分辨率 tile/sprite 像素美术语言，经过设计的大像素簇、统一深色像素轮廓、平整填色、硬边块状阴影、二到四档明确色阶、简化圆润造型，整体明亮、可爱、整洁",
        camera_projection="严格正交俯视，接近垂直向下的 2D 地图视角",
        era_style=f"{world_type.primary or '世界'} / {world_type.secondary or '通用'}",
        color_palette=[
            "符合世界题材的明亮像素地图底色",
            "从叙事氛围中提取的清晰强调色",
            "便于识别建筑、设施和景观的干净过渡色",
        ],
        lighting_weather="明亮、均匀、可读的全局光照，使用柔和短阴影，不使用写实或戏剧化聚光",
        material_texture=[
            "低纹理密度的大色块地表",
            "符合时代的建筑、设施、交通工具和公共景观材质",
        ],
        environmental_motifs=[
            "根据世界时代与文明形态生成通用建筑、公共设施、交通元素、街景陈设和景观装饰",
            "文明世界不能只生成森林、水体、岩石和草地",
        ],
        atmosphere=atmosphere,
        edge_blending_style="简洁像素块边缘与少量柔和过渡，便于后续地点素材融合",
        negative_visual_constraints=[
            "不要人物",
            "不要肖像",
            "不要可读文字",
            "不要标签",
            "不要界面图标",
            "不要地点名",
            "不要具体室内细节",
            "不要等距透视",
            "不要斜俯视场景插画",
            "不要写实材质",
            "不要复杂高频微小纹理",
            "不要后期像素化滤镜感、抗锯齿、柔焦或模糊",
            "不要抖色、点描、颗粒、散点高光或随机纹理噪声",
        ],
    )


def _save_templates(templates_dir: Path, templates: dict[str, EntityTemplate]) -> None:
    for entity_key, entity_template in templates.items():
        ent_dir = templates_dir / entity_key
        dim_names = list(entity_template.dimensions.keys())
        _save_json(ent_dir / "index.json", {"dimensions": dim_names})
        for dim_name, dim_data in entity_template.dimensions.items():
            _save_json(ent_dir / f"{dim_name}.json", dim_data.model_dump())


_AGENT_YAML_TEMPLATE = """\
# ============================================================
#  Agent 全局配置模版
#  定义 Agent 实体的维度组成，每个维度引用独立的类型定义文件
#  此文件结构固定，不随世界变化
# ============================================================

name: Agent
entity_type: character

dimensions:

  # ── 角色档案 ──────────────────────────────────────────────
  profile:
    identity:
      type: IdentityDim
      path: dims/identity.yaml
    social_profile:
      type: SocialProfileDim
      path: dims/social_profile.yaml
    capabilities:
      type: CapabilitiesDim
      path: dims/capabilities.yaml

  # ── 性格特质 ──────────────────────────────────────────────
  personality:
    personality:
      type: PersonalityDim
      path: dims/personality.yaml

  # ── 价值观与记忆 ──────────────────────────────────────────
  values:
    goals:
      type: GoalsDim
      path: dims/goals.yaml
    memories:
      type: MemoriesDim
      path: dims/memories.yaml

  # ── 运行时状态 ──────────────────────────────────────────────
  state:
    state:
      type: StateDim
      path: dims/state.yaml

  # Visual prompt used directly by downstream image generation
  visual:
    visual:
      type: str
      path: dims/visual.yaml
"""

_LOCATION_YAML_TEMPLATE = """\
# ============================================================
#  Location 全局配置模版
#  定义 Location 实体的维度组成
# ============================================================

name: Location
entity_type: location

dimensions:

  # ── 地点档案 ──────────────────────────────────────────────
  profile:
    identity:
      type: IdentityDim
      path: dims/identity.yaml

  # ── 访问控制 ──────────────────────────────────────────────
  access:
    access:
      type: AccessDim
      path: dims/access.yaml

  # ── 运行时状态 ──────────────────────────────────────────────
  state:
    state:
      type: StateDim
      path: dims/state.yaml

  # Visual prompt used directly by downstream image generation
  visual:
    visual:
      type: str
      path: dims/visual.yaml
"""

_PATH_YAML_TEMPLATE = """\
# ============================================================
#  Path 全局配置模版
#  定义地点路径/通道实体的维度组成
# ============================================================

name: Path
entity_type: path

dimensions:

  # ── 路径档案 ──────────────────────────────────────────────
  profile:
    identity:
      type: IdentityDim
      path: dims/identity.yaml

  # ── 端点连接 ──────────────────────────────────────────────
  endpoints:
    endpoints:
      type: EndpointsDim
      path: dims/endpoints.yaml

  # ── 路径属性 ──────────────────────────────────────────────
  properties:
    properties:
      type: PropertiesDim
      path: dims/properties.yaml

  # ── 通行条件 ──────────────────────────────────────────────
  conditions:
    conditions:
      type: ConditionsDim
      path: dims/conditions.yaml
"""

_RELATION_YAML_TEMPLATE = """\
# ============================================================
#  Relation 全局配置模版
#  定义关系实体的维度组成
# ============================================================

name: Relation
entity_type: relation

dimensions:

  # ── 关系边 ────────────────────────────────────────────────
  edge:
    edge:
      type: EdgeDim
      path: dims/edge.yaml
"""

_ENTITY_CONFIGS: list[dict] = [
    {
        "dir_name": "agent",
        "source_entity": "character",
        "template": _AGENT_YAML_TEMPLATE,
        "main_file": "agent.yaml",
        "dims": ["identity", "social_profile", "capabilities",
                 "personality", "goals", "memories", "state"],
        "scalar_dims": ["visual"],
    },
    {
        "dir_name": "location",
        "source_entity": "location",
        "template": _LOCATION_YAML_TEMPLATE,
        "main_file": "location.yaml",
        "dims": ["identity", "access", "state"],
        "scalar_dims": ["visual"],
    },
    {
        "dir_name": "path",
        "source_entity": "path",
        "template": _PATH_YAML_TEMPLATE,
        "main_file": "path.yaml",
        "dims": ["identity", "endpoints", "properties", "conditions"],
    },
    {
        "dir_name": "relation",
        "source_entity": "relation",
        "template": _RELATION_YAML_TEMPLATE,
        "main_file": "relation.yaml",
        "dims": ["edge"],
    },
]

_STAGE2_SCHEMA_ALIASES_BY_DIR_NAME: dict[str, tuple[str, str]] = {
    "location": ("location_profile", "Stage1 generated location model."),
    "agent": (
        "character_profile",
        "Stage1 generated agent model used as the Stage2 character schema.",
    ),
    "path": ("path_edge", "Stage1 generated path model."),
    "relation": ("relation_edge", "Stage1 generated relation model."),
}

_FIELD_GROUPS: dict[str, list[tuple[str, str, list[tuple[str, str]]]]] = {
    "state": [
        ("LocationRef", "location", [("location_id", "location_id")]),
        ("Position", "position", [("position_x", "x"), ("position_y", "y")]),
    ],
    "memories": [
        ("KnowledgeBase", "knowledge",
         [("world_knowledge", "world_knowledge"), ("social_knowledge", "social_knowledge")]),
    ],
}


def _build_dim_yaml(dim_name: str, fields: list) -> dict:
    dim_title = dim_name.title().replace("_", "")
    content: dict = {"dim_name": f"{dim_title}Dim"}

    groups = _FIELD_GROUPS.get(dim_name, [])
    grouped_names: set[str] = set()

    for _sub_type_name, parent_field, members in groups:
        sub_def: dict = {}
        matched_names: set[str] = set()
        for orig_name, new_name in members:
            field = next((f for f in fields if f.name == orig_name), None)
            if field:
                entry: dict = {"type": field.type}
                if field.ref:
                    entry["ref"] = field.ref
                sub_def[new_name] = entry
                matched_names.add(orig_name)
        if sub_def:
            grouped_names.update(matched_names)
            content[parent_field] = sub_def

    for f in fields:
        if f.name in grouped_names:
            continue
        entry: dict = {"type": f.type}
        if f.ref:
            entry["ref"] = f.ref
        if not f.required:
            entry["option"] = True
        content[f.name] = entry

    return content


def _save_entity_configs(configs_dir: Path, templates: dict[str, EntityTemplate]) -> None:
    for cfg in _ENTITY_CONFIGS:
        entity_template = templates.get(cfg["source_entity"])
        if not entity_template:
            continue

        ent_cfg_dir = configs_dir / cfg["dir_name"]
        ent_cfg_dir.mkdir(parents=True, exist_ok=True)
        (ent_cfg_dir / cfg["main_file"]).write_text(cfg["template"], encoding="utf-8")

        dims_dir = ent_cfg_dir / "dims"
        dims_dir.mkdir(parents=True, exist_ok=True)

        for dim_name in cfg["dims"] + cfg.get("scalar_dims", []):
            dim_data = entity_template.dimensions.get(dim_name)
            if not dim_data:
                continue
            dim_content = _build_dim_yaml(dim_name, dim_data.fields)
            _save_yaml(dims_dir / f"{dim_name}.yaml", dim_content)


# ── Pydantic 模型代码生成 ─────────────────────────────────────────────

_PY_TYPE_MAP: dict[str, tuple[str, str]] = {
    "str": ("str", '""'),
    "int": ("int", "0"),
    "float": ("float", "0.0"),
    "bool": ("bool", "False"),
    "list_str": ("list[str]", "[]"),
}


def _to_class_name(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_"))


def _sanitize_identifier(name: str) -> str:
    """Convert arbitrary string (possibly Chinese with fullwidth punctuation) to a valid Python identifier."""
    import re
    result = re.sub(r'[^\w]', '_', name, flags=re.UNICODE)
    result = re.sub(r'_+', '_', result).strip('_')
    if result and result[0].isdigit():
        result = '_' + result
    return result or 'field'


def _generate_pydantic_models(models_dir: Path, configs_dir: Path) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)

    for cfg in _ENTITY_CONFIGS:
        dims_dir = configs_dir / cfg["dir_name"] / "dims"
        if not dims_dir.exists():
            continue

        entity_name = _to_class_name(cfg["dir_name"])
        model_class_name = f"{entity_name}Model"

        lines: list[str] = [
            f'"""Auto-generated {entity_name} Pydantic model."""',
            "from pydantic import BaseModel",
            "",
            "",
        ]

        dim_classes: list[tuple[str, str]] = []
        scalar_fields: list[tuple[str, dict]] = []

        for dim_name in cfg["dims"]:
            dim_file = dims_dir / f"{dim_name}.yaml"
            if not dim_file.exists():
                continue

            dim_data = yaml.safe_load(dim_file.read_text(encoding="utf-8"))
            dim_class_name = dim_data.get("dim_name", _to_class_name(dim_name) + "Dim")

            nested_groups: list[tuple[str, str, dict]] = []
            flat_fields: list[tuple[str, dict]] = []

            for key, val in dim_data.items():
                if key == "dim_name":
                    continue
                if isinstance(val, dict) and "type" not in val:
                    if val:
                        group_class = _to_class_name(key) + "Group"
                        nested_groups.append((key, group_class, val))
                elif isinstance(val, dict) and "type" in val:
                    flat_fields.append((key, val))

            for _field_name, group_class, group_fields in nested_groups:
                lines.append(f"class {group_class}(BaseModel):")
                for fname, fval in group_fields.items():
                    ftype = fval.get("type", "str")
                    py_type, default = _PY_TYPE_MAP.get(ftype, ("str", '""'))
                    safe_fname = _sanitize_identifier(fname)
                    lines.append(f"    {safe_fname}: {py_type} = {default}")
                lines.append("")
                lines.append("")

            lines.append(f"class {dim_class_name}(BaseModel):")
            has_fields = False
            for field_name, group_class, _group_fields in nested_groups:
                safe_field_name = _sanitize_identifier(field_name)
                lines.append(f"    {safe_field_name}: {group_class} = {group_class}()")
                has_fields = True
            for fname, fval in flat_fields:
                ftype = fval.get("type", "str")
                py_type, default = _PY_TYPE_MAP.get(ftype, ("str", '""'))
                comment = "  # world-specific" if fval.get("option") else ""
                safe_fname = _sanitize_identifier(fname)
                lines.append(f"    {safe_fname}: {py_type} = {default}{comment}")
                has_fields = True
            if not has_fields:
                lines.append("    pass")
            lines.append("")
            lines.append("")

            dim_classes.append((dim_class_name, dim_name))

        for dim_name in cfg.get("scalar_dims", []):
            dim_file = dims_dir / f"{dim_name}.yaml"
            if not dim_file.exists():
                continue
            dim_data = yaml.safe_load(dim_file.read_text(encoding="utf-8"))
            for fname, fval in dim_data.items():
                if fname == "dim_name":
                    continue
                if isinstance(fval, dict) and "type" in fval:
                    scalar_fields.append((fname, fval))

        lines.append(f"class {model_class_name}(BaseModel):")
        for dim_class_name, dim_field_name in dim_classes:
            lines.append(f"    {dim_field_name}: {dim_class_name} = {dim_class_name}()")
        for fname, fval in scalar_fields:
            ftype = fval.get("type", "str")
            py_type, default = _PY_TYPE_MAP.get(ftype, ("str", '""'))
            comment = "  # world-specific" if fval.get("option") else ""
            safe_fname = _sanitize_identifier(fname)
            lines.append(f"    {safe_fname}: {py_type} = {default}{comment}")
        lines.append("")

        model_file = models_dir / f"{cfg['dir_name']}_model.py"
        model_file.write_text("\n".join(lines), encoding="utf-8")


def _save_schema_manifest(models_dir: Path) -> None:
    manifest = {
        "schemas": [
            {
                "alias": alias,
                "file": f"{cfg['dir_name']}_model.py",
                "class_name": f"{_to_class_name(cfg['dir_name'])}Model",
                "version": "v1",
                "description": description,
            }
            for cfg in _ENTITY_CONFIGS
            if cfg["dir_name"] in _STAGE2_SCHEMA_ALIASES_BY_DIR_NAME
            for alias, description in [_STAGE2_SCHEMA_ALIASES_BY_DIR_NAME[cfg["dir_name"]]]
        ]
    }
    _save_json(models_dir / "schema_manifest.json", manifest)


def _save_artifact_manifest(session_root: Path, session_id: str) -> None:
    manifest = {
        "session_id": session_id,
        "world_id": session_id,
        "world_background_path": "generated/plan/world_background.json",
        "execution_plan_path": "generated/plan/execution_plan.json",
        "instance_seed_catalog_path": "generated/plan/instance_seed_catalog.json",
        "world_template_path": "generated/world_template.json",
        "schema_manifest_path": "models/schema_manifest.json",
        "provenance": {
            "source": "stage1.pipeline",
            "session_root": str(session_root),
        },
    }
    _save_json(session_root / "generated" / "artifact_manifest.json", manifest)
