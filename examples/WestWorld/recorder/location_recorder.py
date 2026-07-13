"""每地点一个的场景记录员：分块状态 + 被动调用接口。

LLM 只在 submit_action（裁决）和 tick_update（合并更新）两处被调用；
read/enter/leave 是纯文本操作。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from examples.WestWorld.worldmap.loader import Location
from . import prompts

logger = logging.getLogger(__name__)

RECENT_EVENTS_WINDOW = 10
READABLE_CHUNKS = {"static_facilities", "dynamic_objects", "present_agents", "recent_events", "ambient"}
EMPTY_PRESENCE = "（无人）"
FALLBACK_JUDGEMENT = {
    "permission": True, "reason": "", "private_feedback": "",
    "broadcast_level": "none", "event_summary": "",
}


class LocationRecorder:
    def __init__(self, location: Location, llm: Any) -> None:
        self.location = location
        self.llm = llm
        visible = "；".join(f"{o['name']}（{o.get('note', '')}）" for o in location.visible_objects())
        self.chunks: Dict[str, Any] = {
            "static_facilities": f"{location.description.strip()} 设施与陈设：{visible}",
            "dynamic_objects": "暂无特别状态。",
            "present_agents": "、".join(location.default_occupants) or EMPTY_PRESENCE,
            "recent_events": [],
            "ambient": "（无特别氛围）",
            "hidden_notes": "\n".join(f"{o['name']}: {o.get('secret', '')}" for o in location.hidden_objects()) or "（无）",
        }
        self._pending_actions: List[Dict[str, Any]] = []
        self._llm_traces: List[Dict[str, Any]] = []

    # ---- 被动读取（无 LLM） ----
    def read(self, agent_id: str, chunk_names: List[str]) -> Dict[str, Any]:
        wanted = [c for c in chunk_names if c in READABLE_CHUNKS]
        return {c: self.chunks[c] for c in wanted}

    def perceive(self, agent_id: str, agent_context: dict) -> Dict[str, Any]:
        """Recorder 主导感知：根据 agent_context 决定返回哪些信息。

        legacy recorder 无 per-agent 可见性，直接按 focus 软提示委托给 read()。
        """
        focus = agent_context.get("focus")
        if isinstance(focus, list) and focus:
            chunk_names = [c for c in focus if c in READABLE_CHUNKS]
            if not chunk_names:
                chunk_names = ["present_agents", "recent_events", "dynamic_objects"]
        else:
            chunk_names = ["present_agents", "recent_events", "dynamic_objects"]
        return self.read(agent_id, chunk_names)

    def agent_enter(self, agent_id: str) -> str:
        present = self._present_set()
        present.add(agent_id)
        self.chunks["present_agents"] = "、".join(sorted(present))
        return self.chunks["static_facilities"]

    def agent_leave(self, agent_id: str) -> None:
        present = self._present_set()
        present.discard(agent_id)
        self.chunks["present_agents"] = "、".join(sorted(present)) or EMPTY_PRESENCE

    def set_present_agents(self, agent_ids: List[str]) -> None:
        self.chunks["present_agents"] = "、".join(sorted(set(agent_ids))) or EMPTY_PRESENCE

    def record_event(self, event_summary: str) -> None:
        if event_summary:
            self.chunks["recent_events"] = (
                self.chunks["recent_events"] + [str(event_summary)]
            )[-RECENT_EVENTS_WINDOW:]

    def _present_set(self) -> set[str]:
        raw = self.chunks["present_agents"]
        return set() if raw == EMPTY_PRESENCE else {x for x in raw.split("、") if x}

    # ---- 动作裁决（每动作一次 LLM） ----
    def submit_action(
        self,
        agent_id: str,
        action_text: str,
        tick: Optional[int] = None,
        action_type: str = "do",
    ) -> Dict[str, Any]:
        prompt = prompts.render_judge(self.location.name, self.chunks, agent_id, action_text)
        judgement = self._chat_json(
            prompt, retries=1, call_type="recorder_judge",
            metadata={"agent_id": agent_id, "action_text": action_text, "tick": tick},
        )
        if judgement is None:
            logger.warning("[%s] 裁决 JSON 解析失败，降级为允许/无反馈/不广播: %s", self.location.id, action_text)
            judgement = dict(FALLBACK_JUDGEMENT)
        record = {"agent_id": agent_id, "action": action_text, **judgement}
        self._pending_actions.append(record)
        return judgement

    def _chat_json(
        self,
        prompt: str,
        retries: int,
        call_type: str = "recorder_chat",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        request_id = str((metadata or {}).get("request_id") or f"req_{uuid.uuid4().hex}")
        model_name = getattr(self.llm, "config", {}).get("model", "")
        for attempt in range(retries + 1):
            attempt_id = f"attempt_{uuid.uuid4().hex}"
            started = time.perf_counter()
            try:
                raw = self.llm.chat(prompt)
            except Exception as exc:
                self._llm_traces.append({
                    "timestamp": datetime.now().astimezone().isoformat(),
                    "request_id": request_id,
                    "attempt_id": attempt_id,
                    "call_type": call_type,
                    "attempt": attempt + 1,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "prompt": prompt,
                    "raw_response": None,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "model": model_name,
                    **(metadata or {}),
                })
                continue
            trace = {
                "timestamp": datetime.now().astimezone().isoformat(),
                "request_id": request_id,
                "attempt_id": attempt_id,
                "call_type": call_type,
                "attempt": attempt + 1,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "prompt": prompt,
                "raw_response": raw,
                "status": "success",
                "model": model_name,
                **(metadata or {}),
            }
            usage = getattr(self.llm, "last_usage", None)
            if usage:
                trace["usage"] = usage
            try:
                text = raw.strip()
                if text.startswith("```"):
                    text = text.split("```")[1].lstrip("json").strip()
                parsed = json.loads(text)
                trace["parsed_response"] = parsed
                trace["parse_ok"] = True
                self._llm_traces.append(trace)
                return parsed
            except (json.JSONDecodeError, IndexError):
                trace["parse_ok"] = False
                self._llm_traces.append(trace)
                continue
        return None

    # ---- tick 末结算（每地点每 tick 至多一次 LLM） ----
    def tick_update(self, tick: int) -> None:
        if not self._pending_actions:
            return
        actions_log = self._pending_actions
        self._pending_actions = []
        prompt = prompts.render_update(self.location.name, tick, self.chunks, actions_log)
        update = self._chat_json(
            prompt, retries=1, call_type="recorder_tick_update",
            metadata={"tick": tick, "pending_actions": actions_log},
        )
        if update is None:
            logger.error("[%s] tick %s 更新失败，保留旧状态块", self.location.id, tick)
            return
        for key in ("dynamic_objects",):
            if isinstance(update.get(key), str) and update[key].strip():
                self.chunks[key] = update[key]
        events = update.get("recent_events")
        if isinstance(events, list):
            self.chunks["recent_events"] = [str(e) for e in events][-RECENT_EVENTS_WINDOW:]

    def snapshot(self, include_hidden: bool = False, include_pending: bool = False) -> Dict[str, Any]:
        chunks = dict(self.chunks)
        if not include_hidden:
            chunks.pop("hidden_notes", None)
        snapshot: Dict[str, Any] = {
            "location": {
                "id": self.location.id,
                "name": self.location.name,
                "region": self.location.region,
                "type": self.location.type,
            },
            "chunks": chunks,
        }
        if include_pending:
            snapshot["pending_actions"] = list(self._pending_actions)
        return snapshot

    def drain_llm_traces(self) -> List[Dict[str, Any]]:
        traces = self._llm_traces
        self._llm_traces = []
        return traces
