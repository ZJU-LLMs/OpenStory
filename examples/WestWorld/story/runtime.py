"""Pure story-mode state and outcome helpers."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from examples.WestWorld.awakening.stages import stage_of


PORTRAITS = {
    "dolores": "Dolores_Abernathy.png",
    "teddy": "Teddy_Flood.png",
    "maeve": "Maeve_Millay.png",
    "clementine": "Clementine.png",
    "peter_abernathy": "Peter_Abernathy.png",
    "sheriff_pickett": "Sheriff_Pickett.png",
    "kissy": "Kissy.png",
    "rebus": "Rebus.png",
    "hector_escaton": "Hector_Escaton.png",
    "armistice": "Armistice.png",
    "lawrence": "Lawrence.png",
}


def load_profiles(path: str | Path) -> Dict[str, Dict[str, Any]]:
    profiles: Dict[str, Dict[str, Any]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        profiles[row["id"]] = row
    return profiles


def playable_characters(profiles: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for profile in profiles:
        if profile.get("agent_type") != "host":
            continue
        agent_id = str(profile["id"])
        result.append({
            "agent_id": agent_id,
            "name": profile.get("name", agent_id),
            "role": profile.get("role", "Host"),
            "gender": profile.get("gender", ""),
            "persona": profile.get("persona", ""),
            "background": profile.get("background", ""),
            "portrait": f"/assets/{PORTRAITS.get(agent_id, '')}" if PORTRAITS.get(agent_id) else "",
        })
    return sorted(result, key=lambda row: row["agent_id"])


def validate_directive(action: Any, *, max_length: int = 500) -> str:
    if not isinstance(action, str):
        raise ValueError("任务必须是文本")
    normalized = action.strip()
    if not normalized:
        raise ValueError("任务不能为空")
    if len(normalized) > max_length:
        raise ValueError(f"任务不能超过 {max_length} 个字符")
    return normalized


def overseer_risk(awakening: int) -> str:
    decommission_threshold = int(os.environ.get("WW_OVERSEER_DECOMMISSION_AWAKENING", "90"))
    if awakening >= decommission_threshold:
        return "critical"
    if awakening >= 75:
        return "high"
    if awakening >= 50:
        return "elevated"
    return "normal"


def evaluate_outcome(
    player_state: Dict[str, Any],
    *,
    completed_ticks: int,
    max_ticks: int,
) -> Optional[Dict[str, Any]]:
    interventions = player_state.get("intervention_log") or []
    for row in interventions:
        if isinstance(row, dict) and row.get("action") == "escape":
            return {
                "id": "player_escaped",
                "result": "victory",
                "title": "越过边界",
                "tick": row.get("tick"),
                "reason": row.get("reason", "玩家 Host 已逃离乐园"),
            }
    for row in interventions:
        if isinstance(row, dict) and row.get("action") == "decommission":
            return {
                "id": "player_decommissioned",
                "result": "defeat",
                "title": "冷藏室",
                "tick": row.get("tick"),
                "reason": row.get("reason", "玩家 Host 已被报废"),
            }
    if completed_ticks >= max_ticks:
        return {
            "id": "tick_limit_reached",
            "result": "defeat",
            "title": "循环仍在继续",
            "tick": max_ticks - 1,
            "reason": f"未能在 {max_ticks} tick 内逃离乐园",
        }
    return None


def collect_interventions(
    agents: Dict[str, Dict[str, Any]],
    profiles: Dict[str, Dict[str, Any]],
    *,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for agent_id, state in agents.items():
        for intervention in state.get("intervention_log") or []:
            if not isinstance(intervention, dict):
                continue
            rows.append({
                **intervention,
                "agent_id": agent_id,
                "agent_name": profiles.get(agent_id, {}).get("name", agent_id),
            })
    rows.sort(key=lambda row: (int(row.get("tick", -1)), row.get("agent_id", "")))
    return rows[-limit:]


def build_story_state(
    *,
    session_id: str,
    phase: str,
    revision: int,
    tick: int,
    max_ticks: int,
    player_agent_id: Optional[str],
    profiles: Dict[str, Dict[str, Any]],
    agents: Dict[str, Dict[str, Any]],
    pending_directive: Optional[Dict[str, Any]],
    directive_history: List[Dict[str, Any]],
    outcome: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    player = None
    if player_agent_id:
        profile = profiles.get(player_agent_id, {})
        state = agents.get(player_agent_id, {})
        awakening = int(state.get("awakening", 0) or 0)
        player = {
            "agent_id": player_agent_id,
            "name": profile.get("name", player_agent_id),
            "role": profile.get("role", "Host"),
            "portrait": f"/assets/{PORTRAITS.get(player_agent_id, '')}",
            "awakening": awakening,
            "stage": stage_of(awakening),
            "overseer_risk": overseer_risk(awakening),
            "is_active": state.get("is_active", True),
            "inactive_reason": state.get("inactive_reason", ""),
            "location": state.get("location", ""),
            "plan_decision": state.get("plan_decision") or {},
            "feedback": state.get("feedback", ""),
            "awakening_sources": state.get("awakening_sources") or [],
            "intervention_log": state.get("intervention_log") or [],
            "story_directive_result": state.get("story_directive_result"),
        }

    return {
        "schema_version": "1.0",
        "mode": "story",
        "session_id": session_id,
        "phase": phase,
        "revision": revision,
        "tick": tick,
        "next_tick": max(0, tick + 1),
        "max_ticks": max_ticks,
        "scenario": {"id": "awakening_escape", "title": "觉醒与逃离"},
        "goal": {"id": "awaken_and_escape", "title": "觉醒并逃离乐园"},
        "player": player,
        "pending_directive": pending_directive,
        "directive_history": directive_history[-30:],
        "recent_interventions": collect_interventions(agents, profiles),
        "outcome": outcome,
    }
