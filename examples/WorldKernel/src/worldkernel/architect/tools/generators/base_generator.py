"""Shared infrastructure for Stage2 generation tools.

Provides schema introspection, seed batching, world context building,
prompt construction helpers, and output validation/parsing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from worldkernel.architect.init.models import ResolvedSeed, WorldBackgroundArtifact
from worldkernel.architect.tools.base import Stage2ToolRequest
from worldkernel.architect.tools.identity_allocator import IdentityRegistry

if TYPE_CHECKING:
    from worldkernel.architect.registry.core import SchemaEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------

# Mapping from model_file prefix to generated template directory name.
# Most match directly; "agent" is the exception (templates use "character").
_MODEL_FILE_TO_ENTITY_DIR: dict[str, str] = {
    "agent": "character",
}


def _resolve_entity_template_dir(entry: SchemaEntry) -> Path | None:
    """Derive the generated template directory from a SchemaEntry."""
    root = entry.source.root_dir
    if root is None:
        return None
    model_file = entry.metadata.get("model_file", "")
    prefix = model_file.replace("_model.py", "") if model_file else ""
    if not prefix:
        return None
    entity_dir_name = _MODEL_FILE_TO_ENTITY_DIR.get(prefix, prefix)
    template_dir = root / "generated" / "templates" / entity_dir_name
    return template_dir if template_dir.is_dir() else None


def _load_template_required_fields(entry: SchemaEntry) -> dict[str, set[str]]:
    """Load required field sets from Stage1-generated JSON template files.

    Returns a dict mapping dimension name (e.g. "identity") to the set of
    required field names within that dimension.
    """
    template_dir = _resolve_entity_template_dir(entry)
    if template_dir is None:
        return {}
    result: dict[str, set[str]] = {}
    for dim_file in template_dir.iterdir():
        if dim_file.suffix != ".json" or dim_file.name == "index.json":
            continue
        dim_name = dim_file.stem
        try:
            data = json.loads(dim_file.read_text(encoding="utf-8"))
            fields = data.get("fields", [])
            required = {f["name"] for f in fields if f.get("required", False)}
            if required:
                result[dim_name] = required
        except Exception:
            continue
    return result


def introspect_schema(
    ModelClass: type[BaseModel],
    schema_entry: SchemaEntry | None = None,
) -> str:
    """Introspect a Pydantic model and return a human-readable schema description.

    For each top-level dimension (BaseModel subclass), lists required and optional
    fields with their types.  The output is designed to be embedded directly into
    LLM prompts.

    When *schema_entry* is provided, loads the Stage1-generated JSON template files
    to accurately distinguish required vs optional fields.  Without it, falls back
    to treating all fields as required (since generated Pydantic models use zero-value
    defaults for every field).
    """
    required_map: dict[str, set[str]] = {}
    if schema_entry is not None:
        required_map = _load_template_required_fields(schema_entry)

    lines: list[str] = []
    for field_name, field_info in ModelClass.model_fields.items():
        annotation = field_info.annotation
        if annotation is str:
            required = required_map.get(field_name)
            label = "必填字段" if required is None or field_name in required else "可选字段"
            lines.append(f"### 字段: {field_name}")
            lines.append(f"  {label}: {field_name}(str)")
            lines.append("")
            continue
        if annotation is None or not isinstance(annotation, type) or not issubclass(annotation, BaseModel):
            continue
        dim_class = annotation
        dim_required = required_map.get(field_name)
        dim_lines = _introspect_dimension(dim_class, dim_required)
        lines.append(f"### 维度: {field_name}")
        lines.extend(dim_lines)
        lines.append("")
    return "\n".join(lines)


def _introspect_dimension(
    dim_class: type[BaseModel],
    required_fields: set[str] | None = None,
) -> list[str]:
    """Return required/optional field lists for a single dimension model.

    When *required_fields* is provided (from JSON template files), uses it to
    distinguish required vs optional.  Otherwise treats all fields as required.
    """
    required: list[str] = []
    optional: list[str] = []
    for fname, finfo in dim_class.model_fields.items():
        type_name = _type_label(finfo.annotation)
        entry = f"{fname}({type_name})" if type_name != "str" else fname
        if required_fields is not None:
            is_req = fname in required_fields
        else:
            is_req = True  # fallback: treat all as required
        if is_req:
            required.append(entry)
        else:
            optional.append(entry)
    result: list[str] = []
    if required:
        result.append(f"  必填字段: {', '.join(required)}")
    if optional:
        result.append(f"  可选字段: {', '.join(optional)}")
    return result


def _type_label(annotation: Any) -> str:
    """Convert a Python type annotation to a short label."""
    if annotation is int:
        return "int"
    if annotation is float:
        return "float"
    if annotation is bool:
        return "bool"
    if annotation is str:
        return "str"
    name = getattr(annotation, "__name__", str(annotation))
    if "list" in name.lower():
        return "list[str]"
    return "str"


# ---------------------------------------------------------------------------
# Seed batching
# ---------------------------------------------------------------------------

def batch_seeds(
    seeds: list[ResolvedSeed],
    batch_size: int,
) -> list[list[ResolvedSeed]]:
    """Split seeds into batches of at most *batch_size*."""
    return [seeds[i : i + batch_size] for i in range(0, len(seeds), batch_size)]


# ---------------------------------------------------------------------------
# World context building
# ---------------------------------------------------------------------------

def build_world_context(request: Stage2ToolRequest) -> dict[str, str]:
    """Extract world background fields into a flat dict of strings for prompt substitution."""
    wb = request.world_background
    if wb is None:
        return {k: "" for k in (
            "world_name", "world_origin_summary", "primary", "scope",
            "tags", "simulation_start", "world_constraints",
        )}

    sim_start = wb.simulation_start
    if isinstance(sim_start, dict):
        parts = [str(v) for v in sim_start.values() if v]
        sim_str = " | ".join(parts) if parts else "未指定"
    else:
        sim_str = str(sim_start) if sim_start else "未指定"

    constraints = wb.world_constraints
    if isinstance(constraints, list) and constraints:
        constraint_lines: list[str] = []
        for i, c in enumerate(constraints, 1):
            if isinstance(c, dict):
                name = c.get("name", "")
                desc = c.get("description", "")
                constraint_lines.append(f"  {i}. {name}：{desc}")
            else:
                constraint_lines.append(f"  {i}. {c}")
        constraints_str = "\n".join(constraint_lines)
    else:
        constraints_str = "  无"

    tags = wb.tags if isinstance(wb.tags, list) else []

    return {
        "world_name": wb.world_name or "未命名世界",
        "world_origin_summary": wb.world_origin_summary or "",
        "primary": wb.primary or "",
        "scope": wb.scope or "",
        "tags": ", ".join(tags) if tags else "无",
        "simulation_start": sim_str,
        "world_constraints": constraints_str,
    }


# ---------------------------------------------------------------------------
# Seed list formatting
# ---------------------------------------------------------------------------

def build_seed_list(
    batch: list[ResolvedSeed],
    pre_allocated_ids: dict[str, str] | None = None,
) -> str:
    """Format a batch of seeds into a readable list for the prompt.

    When *pre_allocated_ids* is provided, includes the pre-allocated entity ID
    for each seed so the LLM can use it directly as identity.id.
    """
    parts: list[str] = []
    for i, seed in enumerate(batch, 1):
        id_line = ""
        if pre_allocated_ids and seed.seed_id in pre_allocated_ids:
            entity_id = pre_allocated_ids[seed.seed_id]
            id_line = f"- id: {entity_id}\n"
        parts.append(
            f"### 种子 {i}\n"
            f"{id_line}"
            f"- name: {seed.name}\n"
            f"- archetype_id: {seed.archetype_id}\n"
            f"- importance: {seed.importance}\n"
            f"- role_in_world: {seed.role_in_world}"
        )
    return "\n\n".join(parts)


def build_character_summary(
    character_seeds: list[ResolvedSeed],
    max_entries: int = 10,
) -> str:
    """Summarize character seeds for world context (limited to avoid token overflow)."""
    if not character_seeds:
        return "  无角色信息"
    display = character_seeds[:max_entries]
    lines: list[str] = []
    for seed in display:
        lines.append(f"  - {seed.name}（{seed.archetype_id}，{seed.importance}）：{seed.role_in_world}")
    remaining = len(character_seeds) - len(display)
    if remaining > 0:
        lines.append(f"  ...及其他 {remaining} 个角色")
    return "\n".join(lines)


def build_location_summary(
    location_seeds: list[ResolvedSeed],
    pre_allocated_ids: dict[str, str] | None = None,
    max_entries: int = 10,
) -> str:
    """Summarize location seeds for world context (limited to avoid token overflow)."""
    if not location_seeds:
        return "  无地点信息"
    display = location_seeds[:max_entries]
    lines: list[str] = []
    for seed in display:
        eid = pre_allocated_ids.get(seed.seed_id, "?") if pre_allocated_ids else "?"
        lines.append(f"  - {eid} | {seed.name}（{seed.archetype_id}，{seed.importance}）：{seed.role_in_world}")
    remaining = len(location_seeds) - len(display)
    if remaining > 0:
        lines.append(f"  ...及其他 {remaining} 个地点")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def build_generation_prompt(
    template: str,
    replacements: dict[str, str],
) -> str:
    """Replace all {{placeholder}} values in a prompt template."""
    result = template
    for key, value in replacements.items():
        result = result.replace("{{" + key + "}}", value)
    return result


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------

def parse_and_validate(
    raw_data: Any,
    ModelClass: type[BaseModel],
    seeds: list[ResolvedSeed],
) -> tuple[list[BaseModel], list[str]]:
    """Parse LLM output, validate against the schema, auto-correct id mismatches.

    Returns (validated_items, warnings).
    """
    if not isinstance(raw_data, list):
        raw_data = [raw_data]

    validated: list[BaseModel] = []
    warnings: list[str] = []

    for idx, item_data in enumerate(raw_data):
        if not isinstance(item_data, dict):
            warnings.append(f"item[{idx}]: expected dict, got {type(item_data).__name__}, skipped")
            continue

        # Coerce list→str and str→int for known fields
        item_data = _coerce_field_types(item_data, ModelClass, idx, warnings)

        try:
            model = ModelClass.model_validate(item_data)
            validated.append(model)
        except Exception as exc:
            warnings.append(f"item[{idx}]: validation failed: {exc}")

    return validated, warnings


def assign_entity_ids(
    items: list[BaseModel],
    seeds: list[ResolvedSeed],
    registry: IdentityRegistry,
    entity_type: str,
) -> list[str]:
    """Verify and fix items' identity.id to match registered entity IDs.

    Args:
        items: Validated Pydantic model instances.
        seeds: Corresponding seed list.
        registry: Identity registry with pre-registered mappings.
        entity_type: Entity type abbreviation ("loc", "char", "path", "rel").

    Returns:
        List of entity IDs (one per item).
    """
    return registry.verify_and_fix(items, entity_type, seeds)


def _coerce_field_types(
    item_data: dict[str, Any],
    ModelClass: type[BaseModel],
    idx: int,
    warnings: list[str],
) -> dict[str, Any]:
    """Coerce common LLM type mismatches: list→str, str→int, str→float."""
    # Build a flat map of field paths → expected types from the model schema
    expected_types: dict[str, type] = {}
    for dim_name, dim_field in ModelClass.model_fields.items():
        dim_class = dim_field.annotation
        if dim_class in (str, int, float, bool):
            expected_types[dim_name] = dim_class
            continue
        if dim_class is None or not isinstance(dim_class, type) or not issubclass(dim_class, BaseModel):
            continue
        for fname, finfo in dim_class.model_fields.items():
            expected_types[f"{dim_name}.{fname}"] = finfo.annotation

    for path, expected in expected_types.items():
        parts = path.split(".")
        if len(parts) == 1:
            val = item_data.get(path)
            if val is None:
                if expected is str:
                    item_data[path] = ""
                elif expected is int:
                    item_data[path] = 0
                elif expected is float:
                    item_data[path] = 0.0
                elif expected is bool:
                    item_data[path] = False
                continue
            if expected is str and not isinstance(val, str):
                if isinstance(val, bool):
                    item_data[path] = "true" if val else "false"
                elif isinstance(val, list):
                    item_data[path] = ", ".join(str(v) for v in val)
                elif isinstance(val, dict):
                    item_data[path] = val.get("description") or val.get("visual") or json.dumps(val, ensure_ascii=False)
                else:
                    item_data[path] = str(val)
            continue
        if len(parts) != 2:
            continue
        dim_key, field_key = parts
        dim = item_data.get(dim_key)
        if not isinstance(dim, dict):
            continue
        val = dim.get(field_key)

        # Convert None to appropriate default for the expected type
        if val is None:
            if expected is str:
                dim[field_key] = ""
            elif expected is int:
                dim[field_key] = 0
            elif expected is float:
                dim[field_key] = 0.0
            continue

        if expected is str and not isinstance(val, str):
            if isinstance(val, bool):
                dim[field_key] = "true" if val else "false"
            elif isinstance(val, list):
                dim[field_key] = ", ".join(str(v) for v in val)
            else:
                dim[field_key] = str(val)
        elif expected is int and not isinstance(val, int):
            try:
                dim[field_key] = int(val)
            except (TypeError, ValueError):
                warnings.append(f"item[{idx}]: {path} '{val}' cannot be converted to int")
        elif expected is float and not isinstance(val, (int, float)):
            try:
                dim[field_key] = float(val)
            except (TypeError, ValueError):
                warnings.append(f"item[{idx}]: {path} '{val}' cannot be converted to float")
        elif (
            isinstance(expected, type)
            and issubclass(expected, BaseModel)
            and not isinstance(val, dict)
        ):
            # LLM 把嵌套对象字段输出为列表或字符串时，尝试 coerce 成字典
            if isinstance(val, list):
                # 找第一个 list[str] 类型字段，将列表内容映射进去
                # 处理 [{"description": "..."}, ...] 这种 LLM 常见错误格式
                coerced: dict[str, Any] = {}
                for fname, finfo in expected.model_fields.items():
                    ann = finfo.annotation
                    origin = getattr(ann, "__origin__", None)
                    if origin is list:
                        str_vals = []
                        for item in val:
                            if isinstance(item, str):
                                str_vals.append(item)
                            elif isinstance(item, dict):
                                str_vals.append(item.get("description", str(item)))
                        coerced[fname] = str_vals
                        break
                dim[field_key] = coerced
            else:
                # 字符串或其他标量 → 空字典让 Pydantic 使用字段默认值
                dim[field_key] = {}

    return item_data
