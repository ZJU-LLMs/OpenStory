"""Player-facing field labels kept separate from simulation and inference data."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import yaml

from worldkernel.llm.client import chat_json


SCHEMA_VERSION = 1

# Shared labels are intentionally world-independent. World-specific labels are
# generated once and stored in the session's presentation sidecar.
COMMON_LABELS: dict[str, str] = {
    "id": "标识",
    "name": "名称",
    "role": "身份",
    "type": "类型",
    "description": "描述",
    "identity": "身份信息",
    "personality": "性格",
    "capabilities": "能力",
    "goals": "目标与动机",
    "constraints": "行为约束",
    "state": "当前状态",
    "visual": "人物形象",
    "visual_profile": "视觉设定",
    "social_profile": "社会关系",
    "memories": "记忆",
    "relations": "关系",
    "access": "访问规则",
    "topology": "空间连接",
    "simulation_start": "模拟起点",
    "world_name": "世界名称",
    "world_origin_summary": "世界背景摘要",
    "primary": "主要世界类型",
    "secondary": "次要世界类型",
    "tags": "标签",
    "scope": "世界规模",
    "time_point": "起始时间",
    "trigger_event": "触发事件",
    "world_constraints": "世界约束",
    "traits": "特质",
    "values": "价值观",
    "speech_style": "说话风格",
    "skills": "技能",
    "level": "水平",
    "weaknesses": "弱点",
    "short_term_goal": "短期目标",
    "long_term_goal": "长期目标",
    "motivation": "动机",
    "forbidden_actions": "禁止行为",
    "taboos": "禁忌",
    "location": "地点",
    "location_id": "地点标识",
    "position": "坐标",
    "position_x": "横坐标",
    "position_y": "纵坐标",
    "x": "横坐标",
    "y": "纵坐标",
    "group_id": "所属群体",
    "reputation": "声望",
    "background_summary": "背景摘要",
    "key_events": "关键事件",
    "world_knowledge": "世界知识",
    "social_knowledge": "社会知识",
    "knowledge": "知识",
    "secrets": "秘密",
    "relation_ids": "关系标识",
    "permissions": "权限",
    "access_level": "访问等级",
    "access_conditions": "进入条件",
    "current_state": "当前状态",
    "ownership": "归属",
    "capacity": "容量",
    "connected_to": "连接地点",
    "parent_id": "上级地点",
    "layer": "空间层级",
    "entrance_type": "入口类型",
    "current_plan": "当前计划",
    "current_action": "当前行动",
    "current_plan_note": "行动提示",
    "event_log": "事件记录",
    "dialogues": "对话记录",
    "short_term_memory": "近期记忆",
    "long_term_memory": "长期记忆",
    "is_active": "活跃状态",
    "inactive_reason": "未激活原因",
    "mood": "情绪",
    "status": "状态",
    "active_goal": "当前目标",
    "identity_anchor_code": "身份锚定码",
    "memory_asset_level": "记忆资产等级",
    "structural_integrity": "结构完整性",
}

_HIDDEN_KEYS = {
    "id",
    "raw",
    "visual",
    "visual_profile",
    "wk_entity_id",
    "entity_id",
    "agent_id",
    "character_id",
    "location_id",
    "relation_ids",
    "parent_id",
    "connected_to",
    "asset_path",
    "file_path",
    "resource_path",
    "url",
}
_HAN_RE = re.compile(r"[\u3400-\u9fff]")


def presentation_path(session_root: Path, locale: str = "zh-CN") -> Path:
    return session_root / "generated" / "presentation" / locale / "field_labels.json"


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _normalize_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        data = data["items"]
    elif isinstance(data, dict):
        data = list(data.values())
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _is_hidden(path: str, *, schema_ref: bool = False) -> bool:
    segments = path.replace("[]", "").split(".")
    key = segments[-1]
    if schema_ref or key in _HIDDEN_KEYS:
        return True
    if key.endswith("_path") or key.endswith("_url"):
        return True
    return any(segment in {"visual", "visual_profile", "raw"} for segment in segments)


def _walk_value(value: Any, prefix: str, paths: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                continue
            path = f"{prefix}.{key}"
            paths.add(path)
            _walk_value(child, path, paths)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                _walk_value(child, f"{prefix}[]", paths)


def _discover_schema_paths(session_root: Path) -> tuple[set[str], set[str]]:
    paths: set[str] = set()
    referenced_paths: set[str] = set()
    for entity, config_dir in (("character", "agent"), ("location", "location")):
        dims_dir = session_root / "configs" / config_dir / "dims"
        if not dims_dir.exists():
            continue
        for dim_file in dims_dir.glob("*.yaml"):
            dim_name = dim_file.stem
            try:
                content = yaml.safe_load(dim_file.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            for key, definition in content.items():
                if key == "dim_name" or not isinstance(definition, dict):
                    continue
                parent_path = f"{entity}.{dim_name}.{key}"
                paths.add(f"{entity}.{dim_name}")
                if "type" in definition:
                    paths.add(parent_path)
                    if definition.get("ref"):
                        referenced_paths.add(parent_path)
                    continue
                for child_key, child_definition in definition.items():
                    child_path = f"{parent_path}.{child_key}"
                    paths.add(child_path)
                    if isinstance(child_definition, dict) and child_definition.get("ref"):
                        referenced_paths.add(child_path)
    return paths, referenced_paths


def discover_presentation_paths(
    session_root: Path,
    runtime_state: dict[str, Any] | None = None,
) -> tuple[set[str], set[str]]:
    paths, referenced_paths = _discover_schema_paths(session_root)

    world = _read_json(session_root / "generated" / "plan" / "world_background.json")
    if isinstance(world, dict):
        _walk_value(world, "world", paths)

    semantic_root = session_root / "generated" / "artifacts" / "semantic"
    for entity, rel_path in (
        ("character", "characters/characters.json"),
        ("location", "locations/locations.json"),
    ):
        for item in _normalize_items(_read_json(semantic_root / rel_path)):
            _walk_value(item, entity, paths)

    if runtime_state:
        for item in runtime_state.get("agents") or []:
            profile = item.get("profile") if isinstance(item, dict) else None
            if isinstance(profile, dict):
                _walk_value(profile, "character", paths)
        for item in runtime_state.get("locations") or []:
            if isinstance(item, dict):
                _walk_value(item, "location", paths)
    return paths, referenced_paths


def _default_entry(path: str, *, schema_ref: bool = False) -> dict[str, Any]:
    key = path.replace("[]", "").split(".")[-1]
    label = key if _HAN_RE.search(key) else COMMON_LABELS.get(key, "")
    return {
        "label": label,
        "visible": not _is_hidden(path, schema_ref=schema_ref),
    }


def build_stage1_manifest(
    session_root: Path,
    presentation_fields: dict[str, Any],
    *,
    locale: str = "zh-CN",
) -> dict[str, Any]:
    """Persist display metadata without modifying any inference artifact."""

    paths, referenced_paths = discover_presentation_paths(session_root)
    fields: dict[str, dict[str, Any]] = {}
    for path in sorted(paths):
        entry = _default_entry(path, schema_ref=path in referenced_paths)
        provided = presentation_fields.get(path)
        if provided is not None:
            if hasattr(provided, "model_dump"):
                provided = provided.model_dump()
            if isinstance(provided, dict):
                label = str(provided.get("label_zh") or "").strip()
                if label and _HAN_RE.search(label):
                    entry["label"] = label
                entry["visible"] = entry["visible"] and bool(provided.get("player_visible", True))
        fields[path] = entry
    unresolved = [path for path, entry in fields.items() if entry["visible"] and not entry["label"]]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "locale": locale,
        "revision": 1,
        "status": "pending" if unresolved else "ready",
        "unresolved_count": len(unresolved),
        "fields": fields,
    }
    _atomic_write_json(presentation_path(session_root, locale), manifest)
    return manifest


class PresentationService:
    def __init__(self) -> None:
        self._tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def get_manifest(
        self,
        session_root: Path,
        *,
        locale: str = "zh-CN",
        runtime_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if locale != "zh-CN":
            raise ValueError("only zh-CN presentation labels are supported")
        paths, referenced_paths = discover_presentation_paths(session_root, runtime_state)
        path = presentation_path(session_root, locale)
        existing = _read_json(path)
        manifest = existing if isinstance(existing, dict) else {}
        fields = manifest.get("fields") if isinstance(manifest.get("fields"), dict) else {}
        changed = False
        for field_path in sorted(paths):
            default = _default_entry(field_path, schema_ref=field_path in referenced_paths)
            current = fields.get(field_path)
            if not isinstance(current, dict):
                fields[field_path] = default
                changed = True
                continue
            forced_visible = default["visible"]
            if current.get("visible") != (bool(current.get("visible", True)) and forced_visible):
                current["visible"] = bool(current.get("visible", True)) and forced_visible
                changed = True
            if not current.get("label") and default["label"]:
                current["label"] = default["label"]
                changed = True

        unresolved = [
            field_path for field_path, entry in fields.items()
            if isinstance(entry, dict) and entry.get("visible", True) and not entry.get("label")
        ]
        revision = int(manifest.get("revision", 0) or 0) + (1 if changed else 0)
        task_key = (str(session_root.resolve()), locale)
        task = self._tasks.get(task_key)
        task_running = task is not None and not task.done()
        response = {
            "schema_version": SCHEMA_VERSION,
            "locale": locale,
            "revision": max(1, revision),
            "status": "pending" if unresolved else "ready",
            "unresolved_count": len(unresolved),
            "fields": fields,
        }
        if changed or not path.exists() or manifest.get("status") != response["status"]:
            _atomic_write_json(path, response)
        if unresolved and not task_running:
            self._tasks[task_key] = asyncio.create_task(
                self._translate_missing(session_root, locale, unresolved),
                name=f"presentation-labels:{session_root.name}:{locale}",
            )
        return response

    async def _translate_missing(
        self,
        session_root: Path,
        locale: str,
        field_paths: list[str],
    ) -> None:
        key = (str(session_root.resolve()), locale)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            path = presentation_path(session_root, locale)
            try:
                prompt = (
                    "将以下程序字段路径翻译成简短、自然的简体中文界面字段名。"
                    "只翻译最后一个字段名，并结合完整路径消除歧义。"
                    "同时判断字段是否对玩家有叙事意义；技术 ID、内部代码、资源路径、"
                    "视觉生成提示和调试字段必须隐藏。"
                    "返回 JSON 对象，键必须与输入路径完全一致，值格式为"
                    "{\"label_zh\":\"中文字段名\",\"player_visible\":true}。\n"
                    + json.dumps(field_paths, ensure_ascii=False)
                )
                raw = await chat_json(
                    prompt,
                    system="你是界面字段本地化模块，只输出合法 JSON。",
                )
                translated = json.loads(raw)
                if not isinstance(translated, dict):
                    raise ValueError("translation response must be a JSON object")
                manifest = _read_json(path) or {}
                fields = manifest.get("fields") if isinstance(manifest.get("fields"), dict) else {}
                for field_path in field_paths:
                    translated_entry = translated.get(field_path)
                    if isinstance(translated_entry, dict):
                        label = str(translated_entry.get("label_zh") or "").strip()
                        player_visible = bool(translated_entry.get("player_visible", True))
                    else:
                        # Accept the first deployed string-only response shape.
                        label = str(translated_entry or "").strip()
                        player_visible = True
                    if isinstance(fields.get(field_path), dict):
                        fields[field_path]["visible"] = (
                            bool(fields[field_path].get("visible", True)) and player_visible
                        )
                        if _HAN_RE.search(label):
                            fields[field_path]["label"] = label
                unresolved = [
                    field_path for field_path, entry in fields.items()
                    if isinstance(entry, dict) and entry.get("visible", True) and not entry.get("label")
                ]
                manifest.update({
                    "schema_version": SCHEMA_VERSION,
                    "locale": locale,
                    "revision": int(manifest.get("revision", 0) or 0) + 1,
                    "status": "pending" if unresolved else "ready",
                    "unresolved_count": len(unresolved),
                    "fields": fields,
                })
                _atomic_write_json(path, manifest)
            except Exception as exc:  # noqa: BLE001 - background failures are persisted for the UI
                manifest = _read_json(path) or {}
                manifest["status"] = "failed"
                manifest["error"] = type(exc).__name__
                _atomic_write_json(path, manifest)

    async def close(self) -> None:
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
