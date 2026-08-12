"""Relation environment plugin: agent-to-agent relationship lookups."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_PATH = Path(__file__).resolve().parents[3]
if str(PROJECT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH))

from plugins._optional_deps import ensure_optional_agentkernel_imports

ensure_optional_agentkernel_imports()

from agentkernel_distributed.mas.environment.base.plugin_base import RelationPlugin


class BasicRelationPlugin(RelationPlugin):
    """Holds the relationship graph and answers relationship queries."""

    def __init__(self, relations: list[dict[str, Any]] | dict[str, Any] | None = None) -> None:
        super().__init__()
        if isinstance(relations, dict):
            self.relations = list(relations.values())
        else:
            self.relations = relations or []

    async def get_relations(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        if not agent_id:
            return list(self.relations)
        return [
            relation
            for relation in self.relations
            if relation.get("source") == agent_id or relation.get("target") == agent_id
        ]

    async def get_relation_between(self, source: str, target: str) -> dict[str, Any] | None:
        for relation in self.relations:
            if relation.get("source") == source and relation.get("target") == target:
                return relation
            if relation.get("source") == target and relation.get("target") == source:
                return relation
        return None

    async def apply_relation_delta(
        self,
        source: str,
        target: str,
        delta: int,
        reason: str = "",
        event_id: str = "",
    ) -> dict[str, Any]:
        """Apply a bounded numeric relationship change without replacing world lore."""
        if not source or not target or source == target:
            return {"applied": False, "reason": "invalid relation endpoints"}
        try:
            parsed_delta = int(delta)
        except (TypeError, ValueError):
            return {"applied": False, "reason": "delta must be an integer"}
        if parsed_delta < -100 or parsed_delta > 100:
            return {"applied": False, "reason": "delta outside [-100, 100]"}

        relation = await self.get_relation_between(source, target)
        if relation is None:
            return {"applied": False, "reason": "relation not found"}
        properties = relation.setdefault("properties", {})
        try:
            previous = int(properties.get("strength_score", 0) or 0)
        except (TypeError, ValueError):
            previous = 0
        current = max(-100, min(100, previous + parsed_delta))
        properties["strength_score"] = current
        history = properties.setdefault("effect_history", [])
        history.append(
            {
                "event_id": str(event_id or ""),
                "delta": parsed_delta,
                "before": previous,
                "after": current,
                "reason": str(reason or "")[:240],
            }
        )
        del history[:-100]
        return {
            "applied": True,
            "type": "relation_delta",
            "source": source,
            "target": target,
            "before": previous,
            "after": current,
            "delta": parsed_delta,
        }
