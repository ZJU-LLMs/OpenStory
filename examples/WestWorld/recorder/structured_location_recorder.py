"""Location Recorder where LLM proposes free-form object patches validated before applying."""
from __future__ import annotations

import copy
import json
import os
import re
from typing import Any, Dict, List, Optional

from examples.WestWorld.worldmap.loader import Location
from .location_recorder import (
    FALLBACK_JUDGEMENT,
    RECENT_EVENTS_WINDOW,
    LocationRecorder,
)
from .world_object_registry import META_FIELDS, get_object_registry

_BATCH_PROPOSAL_PROMPT = """你是地点「{location_name}」的动作解析器与场景裁判。
本 tick 有 {n} 个角色同时采取了行动，请统一裁决并输出每个角色的结果。

可见对象（patch 只能使用这些 object_id；destroy 只能使用这些 object_id）：
{objects}

可见对象当前事实：
{facts}

隐藏秘密（仅你可见，严禁直接照抄给角色；隐藏物件不得出现在 patches 中）：
{hidden_secrets}

在场角色（present_agents）：{present_agents}

本 tick 角色动作列表（按提交顺序，顺序不代表优先级，由你裁决）：
{actions_list}

规则：
- 所有角色的动作视为同时发生，由你决定裁决结果（如争抢同一对象时谁获得）。
- patches 只能针对【可见对象】；隐藏物件严禁出现在 patches 中。
- 可以更新任意字段（state、quantity、container 等），字段值为简短中文字符串（不超过 100 字）。
- state 是主要状态描述，优先用它记录对象当前状况。
- held_by 是结构化所有权：当动作涉及「拿起、手持、接过、握住、抓起、拾起」某可见对象时，必须同时将该对象的 held_by 设为行动者 agent_id；涉及「放下、递出、交给、丢弃」时，必须将 held_by 改为空字符串或接收者 agent_id。
- 只更新确实发生变化的字段，未变化的字段不要出现在 patch 中。
- 动作完全不涉及任何可见对象时 patches 为空数组。
- new_objects：当动作产生新的可见物时声明，每项含 name 与初始字段；不得标 hidden。
- destroy：当可见物被彻底消灭时列其 object_id。
- 动作类型为 do 时，角色始终留在「{location_name}」，不得声称离开或到达其他地点。
- 秘密揭示：仅当动作确实触及隐藏秘密时，在 private_feedback 中渐进式透露，并把对应 object_id 写入 discovered_object_ids；未发现则为空数组。
- 所有字段值必须使用中文，严禁使用英文。

只输出 JSON，actions 数组顺序必须与输入动作列表顺序一致（顺序：{agent_ids}）：
{{"actions": [
  {{"agent_id": "角色id", "permission": true, "reason": "", "private_feedback": "...", "discovered_object_ids": [],
    "patches": [{{"object_id": "obj_0", "state": "被角色握在手中", "held_by": "角色id"}}],
    "new_objects": [{{"name": "地上的血", "state": "暗红一滩", "held_by": ""}}],
    "destroy": []}}
],
"ambient": "",
"broadcast_level": "none|location",
"event_summary": ""}}
"""

_PROPOSAL_PROMPT = """你是地点「{location_name}」的动作解析器与场景裁判。
把角色的自由文本动作转换成对【可见对象】的字段更新（patch），并判断动作是否触及隐藏秘密。你可以创造新对象或销毁现有对象。

可见对象（patch 只能使用这些 object_id；destroy 只能使用这些 object_id）：
{objects}

可见对象当前事实：
{facts}

隐藏秘密（仅你可见，严禁直接照抄给角色；隐藏物件不得出现在 patches 中）：
{hidden_secrets}

在场角色（present_agents）：{present_agents}

角色：{agent_id}
动作类型：{action_type}
动作：{action_text}

规则：
- patches 只能针对【可见对象】，每条包含 object_id 以及要修改的字段；隐藏物件严禁出现在 patches 中。
- 可以更新任意字段（state、quantity、container 等），字段值为简短中文字符串（不超过 100 字）。
- state 是主要状态描述，优先用它记录对象当前状况。
- held_by 是结构化所有权：当动作涉及「拿起、手持、接过、握住、抓起、拾起」某可见对象时，必须同时将该对象的 held_by 设为行动者 id（{agent_id}）；涉及「放下、递出、交给、丢弃」时，必须将 held_by 改为空字符串或接收者 agent_id。
- 只更新确实发生变化的字段，未变化的字段不要出现在 patch 中。
- 动作完全不涉及任何可见对象时 patches 为空数组。
- new_objects：当动作产生新的可见物（倒出的酒、地上的血、掉落的弹壳）时声明，每项含 name 与初始字段；不得标 hidden。
- destroy：当可见物被彻底消灭（烧毁、击碎丢弃）时列其 object_id。
- ambient：当整体环境氛围（光线/气味/声音/气氛）变化时给一句中文自由文本；无变化则空串。
- 动作类型为 do，表示角色始终留在「{location_name}」。不得声称角色离开、前往、进入或到达其他地点，也不得通过 patches 改变角色位置。
- 秘密揭示由你裁决：仅当动作确实触及某个隐藏秘密时，在 private_feedback 中按动作触及的深浅渐进式透露其内容，并把对应 object_id 写入 discovered_object_ids；动作未触及秘密时必须为空数组。
- 所有字段值必须使用中文，严禁使用英文。

只输出 JSON：
{{"permission": true, "reason": "", "private_feedback": "...", "discovered_object_ids": [], "broadcast_level": "none|location",
"event_summary": "", "patches": [{{"object_id": "obj_0", "state": "被{agent_id}握在手中", "held_by": "{agent_id}"}}],
"new_objects": [{{"name": "地上的血", "state": "暗红一滩", "held_by": ""}}],
"destroy": ["obj_5"],
"ambient": ""}}
"""


def _current_tick_parse_retries() -> int:
    try:
        attempts = int(os.environ.get("WW_ACTION_RETRY_LIMIT", "3"))
    except ValueError:
        attempts = 3
    return max(1, attempts) - 1


class StructuredLocationRecorder(LocationRecorder):
    """Formal-simulation Recorder: LLM proposes free-form object patches, reducer applies atomically."""

    def __init__(self, location: Location, llm: Any) -> None:
        super().__init__(location, llm)
        self.registry = get_object_registry()
        self._seed_location()
        self.fact_ledger: List[Dict[str, Any]] = []
        self._unresolved_actions: List[Dict[str, Any]] = []
        self._intent_queue: List[Dict[str, Any]] = []
        self._pending_feedback: Dict[str, Dict[str, Any]] = {}
        self._render_dynamic_objects()

    def _seed_location(self) -> None:
        if self.registry.is_location_seeded(self.location.id):
            return
        for item in self.location.objects:
            fields = {"state": item.get("note", "状态正常")}
            if item.get("secret"):
                fields["secret"] = item["secret"]
            self.registry.create(
                name=item["name"], location_id=self.location.id, by="__seed__",
                tick=None, action="__seed__", fields=fields, hidden=bool(item.get("hidden")),
            )
        self.registry.mark_location_seeded(self.location.id)

    def submit_action(
        self,
        agent_id: str,
        action_text: str,
        tick: Optional[int] = None,
        action_type: str = "do",
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """Queue this action intent; actual LLM processing happens in tick_update."""
        self._intent_queue.append({
            "agent_id": agent_id,
            "action_text": action_text,
            "action_type": action_type,
            "tick": tick,
            "retry_count": retry_count,
        })
        return {**FALLBACK_JUDGEMENT, "status": "queued", "permission": None}

    def _batch_resolve(self, intents: List[Dict[str, Any]], tick: Optional[int] = None) -> None:
        """Process all queued intents with a single batch LLM call."""
        if not intents:
            return
        self._render_dynamic_objects()
        visible_rows = self.registry.objects_at(self.location.id, include_hidden=False)
        visible_objects = [
            {"object_id": row["object_id"], "name": row["name"]} for row in visible_rows
        ]
        visible_facts = {
            row["object_id"]: {k: v for k, v in row.items() if k != "hidden"}
            for row in visible_rows
        }
        hidden_rows = [
            {
                "object_id": row["object_id"],
                "name": row["name"],
                "secret": row.get("secret", ""),
            }
            for row in self.registry.objects_at(self.location.id, include_hidden=True)
            if row.get("hidden")
        ]
        present_agents = self.chunks.get("present_agents") or "（无人）"
        actions_list = [
            {"agent_id": i["agent_id"], "action_type": i["action_type"], "action_text": i["action_text"]}
            for i in intents
        ]
        agent_ids_str = "、".join(i["agent_id"] for i in intents)
        prompt = _BATCH_PROPOSAL_PROMPT.format(
            location_name=self.location.name,
            n=len(intents),
            objects=json.dumps(visible_objects, ensure_ascii=False),
            facts=json.dumps(visible_facts, ensure_ascii=False),
            hidden_secrets=json.dumps(hidden_rows, ensure_ascii=False) if hidden_rows else "（无）",
            present_agents=present_agents,
            actions_list=json.dumps(actions_list, ensure_ascii=False),
            agent_ids=agent_ids_str,
        )
        response = self._chat_json(
            prompt,
            retries=_current_tick_parse_retries(),
            call_type="batch_action_resolve",
            metadata={"tick": tick, "agent_ids": [i["agent_id"] for i in intents]},
        )
        if not isinstance(response, dict) or not isinstance(response.get("actions"), list):
            for intent in intents:
                judgement = self._record_unresolved(
                    intent["agent_id"], intent["action_text"], tick,
                    intent["action_type"], "批量动作解析失败", intent.get("retry_count", 0),
                )
                self._pending_feedback[intent["agent_id"]] = judgement
            return
        result_by_agent = {
            r["agent_id"]: r
            for r in response["actions"]
            if isinstance(r, dict) and "agent_id" in r
        }
        with self.registry.transaction():
            for intent in intents:
                agent_id = intent["agent_id"]
                action_text = intent["action_text"]
                action_type = intent["action_type"]
                retry_count = intent.get("retry_count", 0)
                action_result = result_by_agent.get(agent_id)
                if action_result is None:
                    judgement = self._record_unresolved(
                        agent_id, action_text, tick, action_type,
                        "LLM 未返回该角色的结果", retry_count,
                    )
                    self._pending_feedback[agent_id] = judgement
                    continue
                action_ledger_start = self.registry.ledger_size()
                try:
                    patches = self._validate_patches(action_result.get("patches", []), agent_id)
                    if not action_result.get("permission", False):
                        patches, new_objects, destroy_ids, discovered_ids = [], [], [], []
                    else:
                        new_objects = self._validate_new_objects(action_result.get("new_objects", []), agent_id)
                        destroy_ids = self._validate_destroy(action_result.get("destroy", []))
                        discovered_ids = self._validate_discovered_object_ids(
                            action_result.get("discovered_object_ids", [])
                        )
                    for spec in new_objects:
                        self.registry.create(
                            name=spec["name"], location_id=self.location.id, by=agent_id,
                            tick=tick, action=action_text, fields=spec["fields"], hidden=False,
                            held_by=spec["held_by"],
                        )
                    self._apply_patches(patches, agent_id, tick)
                    for oid in destroy_ids:
                        self.registry.destroy(oid, by=agent_id, tick=tick)
                except ValueError as exc:
                    judgement = self._record_unresolved(
                        agent_id, action_text, tick, action_type, str(exc), retry_count,
                    )
                    self._pending_feedback[agent_id] = judgement
                    continue
                registry_events = self.registry.ledger_since(action_ledger_start)
                judgement = {
                    key: action_result.get(key, FALLBACK_JUDGEMENT[key])
                    for key in FALLBACK_JUDGEMENT
                }
                judgement["discovered_object_ids"] = discovered_ids
                judgement = self._normalize_judgement(judgement, agent_id, action_type)
                self.fact_ledger.append({
                    "status": "resolved",
                    "tick": tick,
                    "agent_id": agent_id,
                    "action_text": action_text,
                    "patches": patches,
                    "new_objects": new_objects,
                    "destroy": destroy_ids,
                    "discovered_object_ids": discovered_ids,
                    "ambient": None,
                    "registry_events": registry_events,
                    "judgement": judgement,
                })
                self._pending_feedback[agent_id] = judgement
        ambient = response.get("ambient") or None
        if ambient:
            self.chunks["ambient"] = str(ambient)[:200]
        broadcast_level = response.get("broadcast_level", "none")
        event_summary = str(response.get("event_summary", ""))
        if broadcast_level not in ("none", "location"):
            broadcast_level = "location" if event_summary else "none"
        # do 动作不得通过 event_summary 声称跨地点移动
        if event_summary and re.search(r"(离开|前往|到达|进入|走出|赶往|返回到)", event_summary):
            agent_ids_list = "、".join(i["agent_id"] for i in intents)
            event_summary = f"{agent_ids_list}在{self.location.name}采取了行动。"
            broadcast_level = "location"
        if broadcast_level == "location" and event_summary:
            self.chunks["recent_events"] = (
                self.chunks["recent_events"] + [event_summary]
            )[-RECENT_EVENTS_WINDOW:]

    def read_feedback(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return and clear the pending feedback for this agent, or None if absent."""
        return self._pending_feedback.pop(agent_id, None)

    def _record_unresolved(
        self, agent_id: str, action_text: str, tick: Optional[int],
        action_type: str, reason: str, retry_count: int,
    ) -> Dict[str, Any]:
        failed_attempts = retry_count + 1
        retry_scheduled = False
        judgement = {
            **FALLBACK_JUDGEMENT,
            "permission": False,
            "reason": reason,
            "private_feedback": f"动作已提交，但场景状态暂未解析完成：{reason}",
            "status": "unresolved",
        }
        record = {
            "status": "unresolved",
            "tick": tick,
            "agent_id": agent_id,
            "action_text": action_text,
            "action_type": action_type,
            "reason": reason,
            "retry_count": failed_attempts,
            "retry_scheduled": retry_scheduled,
            "judgement": copy.deepcopy(judgement),
        }
        self.fact_ledger.append(record)
        return judgement

    def _normalize_judgement(
        self, judgement: Dict[str, Any], agent_id: str, action_type: str,
    ) -> Dict[str, Any]:
        if judgement.get("broadcast_level") not in ("none", "location"):
            judgement["broadcast_level"] = (
                "location" if judgement.get("event_summary") else "none"
            )
        if action_type != "do":
            return judgement
        summary = str(judgement.get("event_summary") or "")
        if re.search(r"(离开|前往|到达|进入|走出|赶往|返回到)", summary):
            judgement["event_summary"] = f"{agent_id}在{self.location.name}采取了行动。"
        return judgement

    def _allowed_holders(self, agent_id: str) -> set:
        return {"", agent_id} | self._present_set()

    def _validate_patches(self, patches: Any, agent_id: str) -> List[Dict[str, Any]]:
        if not isinstance(patches, list):
            raise ValueError("patches 必须是数组")
        validated = []
        for patch in patches:
            if not isinstance(patch, dict):
                raise ValueError("每条 patch 必须是对象")
            object_id = patch.get("object_id")
            # Check existence: must be known to registry and belong to this location
            if not self.registry.has(object_id):
                raise ValueError(f"未知 object_id: {object_id}")
            obj = self.registry.get(object_id)
            if obj["location_id"] != self.location.id or obj["destroyed"]:
                raise ValueError(f"未知 object_id: {object_id}")
            if obj["hidden"]:
                # 隐藏对象永远保持 hidden：丢弃针对它的 patch，但不让整个动作失败
                continue
            updates: Dict[str, str] = {}
            for key, value in patch.items():
                if key == "object_id":
                    continue
                if key in META_FIELDS:
                    raise ValueError(f"不允许修改保留字段: {key}")
                if not isinstance(value, str):
                    raise ValueError(f"字段 {key} 的值必须是字符串，收到: {type(value).__name__}")
                if len(value) > 100:
                    raise ValueError(f"字段 {key} 的值不能超过 100 字符")
                if key == "held_by" and value not in self._allowed_holders(agent_id):
                    # silently skip invalid held_by transfer
                    continue
                updates[key] = value
            validated.append({"object_id": object_id, "updates": updates})
        return validated

    def _validate_discovered_object_ids(self, raw_ids: Any) -> List[str]:
        if not isinstance(raw_ids, list):
            raise ValueError("discovered_object_ids 必须是数组")
        validated: List[str] = []
        for object_id in raw_ids:
            if not isinstance(object_id, str) or not self.registry.has(object_id):
                raise ValueError(f"未知 discovered object_id: {object_id}")
            obj = self.registry.get(object_id)
            if (
                obj["location_id"] != self.location.id
                or obj["destroyed"]
                or not obj["hidden"]
            ):
                raise ValueError(f"无效 discovered object_id: {object_id}")
            if object_id not in validated:
                validated.append(object_id)
        return validated

    def _apply_patches(
        self, patches: List[Dict[str, Any]], agent_id: str, tick: Optional[int],
    ) -> None:
        for patch in patches:
            self.registry.apply_patch(
                patch["object_id"], patch["updates"], by=agent_id, tick=tick,
            )

    def _validate_new_objects(self, raw: Any, agent_id: str) -> List[Dict[str, Any]]:
        result = []
        if not isinstance(raw, list):
            return result
        allowed = self._allowed_holders(agent_id)
        for spec in raw:
            if not isinstance(spec, dict) or not spec.get("name"):
                continue
            fields = {}
            held_by = ""
            for key, value in spec.items():
                if key in ("name", "hidden", "object_id", "destroyed", "provenance", "location_id"):
                    continue
                if key == "held_by":
                    held_by = value if isinstance(value, str) and value in allowed else ""
                    continue
                if isinstance(value, str) and len(value) <= 100:
                    fields[key] = value
            result.append({"name": str(spec["name"])[:100], "fields": fields, "held_by": held_by})
        return result

    def _validate_destroy(self, raw: Any) -> List[str]:
        result = []
        if not isinstance(raw, list):
            return result
        for oid in raw:
            if (self.registry.has(oid)
                    and self.registry.get(oid)["location_id"] == self.location.id
                    and not self.registry.get(oid)["destroyed"]
                    and not self.registry.get(oid)["hidden"]):
                result.append(oid)
        return result

    def _render_dynamic_objects(self) -> None:
        parts = []
        skip = {"object_id", "name", "hidden", "destroyed", "provenance", "location_id", "state", "held_by", "secret"}
        for row in self.registry.objects_at(self.location.id):
            text = f"{row['name']}：{row.get('state', '')}"
            extras = [(k, v) for k, v in row.items() if k not in skip and v]
            if extras:
                text += "（" + "，".join(f"{k}：{v}" for k, v in extras) + "）"
            if row.get("held_by"):
                text += f"，由 {row['held_by']} 持有"
            parts.append(text)
        self.chunks["dynamic_objects"] = "；".join(parts) or "暂无可变物品。"

    def tick_update(self, tick: int) -> None:
        # Parsing attempts are exhausted in this tick; do not replay stale actions later.
        self._unresolved_actions = []
        # Drain and process the intent queue atomically
        intents, self._intent_queue = self._intent_queue, []
        self._batch_resolve(intents, tick)
        self._render_dynamic_objects()

    def read(self, agent_id: str, chunk_names: List[str]) -> Dict[str, Any]:
        self._render_dynamic_objects()
        return super().read(agent_id, chunk_names)

    # ---- Recorder 主导感知（per-agent） ----

    _RENDER_SKIP = frozenset({
        "object_id", "name", "hidden", "destroyed", "provenance",
        "location_id", "state", "held_by", "secret", "_uncanny",
    })

    def _render_dynamic_objects_for_viewer(
        self, discovered_ids: List[str], awakening: int
    ) -> str:
        parts = []
        for row in self.registry.objects_at_for_viewer(
            self.location.id, set(discovered_ids), awakening
        ):
            text = f"{row['name']}：{row.get('state', '')}"
            extras = [(k, v) for k, v in row.items() if k not in self._RENDER_SKIP and v]
            if extras:
                text += "（" + "，".join(f"{k}：{v}" for k, v in extras) + "）"
            if row.get("held_by"):
                text += f"，由 {row['held_by']} 持有"
            if row.get("_uncanny"):
                text += f"【似有异样：{row['_uncanny']}】"
            parts.append(text)
        return "；".join(parts) or "暂无可变物品。"

    def perceive(self, agent_id: str, agent_context: dict) -> Dict[str, Any]:
        """Recorder 主导感知：按该 agent 的 context 千人千面决定告知内容。

        基础在场信息（present_agents / recent_events）对同地点所有人一致；
        dynamic_objects 按 discovered_ids + awakening 做 per-agent 过滤。
        agent 可通过 focus 给出软关注点提示，但不能借此越权看不可见信息。
        """
        from typing import List as _List  # noqa: avoid shadowing outer scope

        discovered_ids: _List[str] = list(agent_context.get("discovered_ids") or [])
        awakening: int = int(agent_context.get("awakening") or 0)
        focus = agent_context.get("focus")

        from .location_recorder import READABLE_CHUNKS
        if isinstance(focus, list) and focus:
            requested = {c for c in focus if c in READABLE_CHUNKS}
            if not requested:
                requested = {"present_agents", "recent_events", "dynamic_objects"}
        else:
            requested = {"present_agents", "recent_events", "dynamic_objects"}

        result: Dict[str, Any] = {}

        # Base: identical for all agents at this location
        if "present_agents" in requested:
            result["present_agents"] = self.chunks.get("present_agents", "（无人）")
        if "recent_events" in requested:
            result["recent_events"] = self.chunks.get("recent_events", [])
        if "static_facilities" in requested:
            result["static_facilities"] = self.chunks.get("static_facilities", "")
        if "ambient" in requested:
            result["ambient"] = self.chunks.get("ambient", "")

        # Per-agent: filter objects by viewer's knowledge
        if "dynamic_objects" in requested:
            result["dynamic_objects"] = self._render_dynamic_objects_for_viewer(
                discovered_ids, awakening
            )

        return result

    def snapshot(self, include_hidden: bool = False, include_pending: bool = False) -> Dict[str, Any]:
        self._render_dynamic_objects()
        snapshot = super().snapshot(include_hidden=include_hidden, include_pending=include_pending)
        if include_hidden:
            snapshot["object_facts"] = self.registry.objects_at(self.location.id, include_hidden=True)
            snapshot["fact_ledger"] = copy.deepcopy(self.fact_ledger)
            snapshot["unresolved_actions"] = copy.deepcopy(self._unresolved_actions)
        snapshot["intent_queue"] = copy.deepcopy(self._intent_queue)
        snapshot["pending_feedback"] = copy.deepcopy(self._pending_feedback)
        return snapshot

    def restore(self, snapshot: Dict[str, Any], restore_registry: bool = False) -> None:
        """Restore per-location chunks and, optionally, the shared registry."""
        if restore_registry:
            registry_snapshot = snapshot.get("registry")
            if not isinstance(registry_snapshot, dict):
                raise ValueError("structured recorder restore requires registry snapshot")
            self.registry.restore(registry_snapshot)
        chunks = snapshot.get("chunks")
        if isinstance(chunks, dict):
            self.chunks.update(copy.deepcopy(chunks))
        self.fact_ledger = copy.deepcopy(snapshot.get("fact_ledger", []))
        self._unresolved_actions = copy.deepcopy(snapshot.get("unresolved_actions", []))
        self._intent_queue = copy.deepcopy(snapshot.get("intent_queue", []))
        self._pending_feedback = copy.deepcopy(snapshot.get("pending_feedback", {}))
        self._render_dynamic_objects()
