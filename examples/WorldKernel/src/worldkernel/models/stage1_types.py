from __future__ import annotations

from pydantic import BaseModel


class IntentResult(BaseModel):
    raw_text: str
    world_name_hint: str = ""
    source_hint: str = ""
    user_goal: str = ""
    style: str = ""
    constraints: list[str] = []
    uncertain_slots: list[str] = []


class WorldTypeResult(BaseModel):
    primary: str
    secondary: str | None = None
    confidence: float = 0.8
    tags: list[str] = []


class GenerationStep(BaseModel):
    name: str
    target: str


class GenerationPlan(BaseModel):
    steps: list[GenerationStep]


class TemplateMatch(BaseModel):
    type: str
    name: str
    source: str
    data: dict


class OntologySchema(BaseModel):
    entity_types: list[str]
    schemas: dict[str, dict]
