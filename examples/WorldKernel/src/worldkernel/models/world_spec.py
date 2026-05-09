from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class WorldSpecMeta(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_input: str


class WorldSpec(BaseModel):
    meta: WorldSpecMeta
    intent: dict[str, Any]
    world_type: dict[str, Any]
    generation_plan: dict[str, Any]
    templates: dict[str, Any]
    ontology: dict[str, Any]
    constraints: list[str] = []
    uncertain_slots: list[str] = []
    confidence: float = 0.0
