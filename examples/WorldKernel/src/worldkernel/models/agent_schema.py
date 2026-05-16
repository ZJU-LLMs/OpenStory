"""Agent 全局实体 Schema 的 Pydantic 运行时模型。

每个维度（Dimension）是一个独立的子类，Agent 聚合所有维度。
Stage 1 生成的模版会在这些固有字段基础上追加世界特有的额外字段。
"""
from __future__ import annotations

from pydantic import BaseModel


# ── 维度子类 ─────────────────────────────────────────────────────────

class IdentityDim(BaseModel):
    id: str
    name: str
    role: str


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""


class ConstraintsDim(BaseModel):
    forbidden_actions: list[str] = []
    taboos: list[str] = []


class StateDim(BaseModel):
    location_id: str = ""
    position_x: float = 0.0
    position_y: float = 0.0


class VisualDim(BaseModel):
    visual_description: str = ""
    visual_prompt: str = ""


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""


class RelationsDim(BaseModel):
    relation_ids: list[str] = []


# ── Agent 聚合类 ─────────────────────────────────────────────────────

class AgentEntity(BaseModel):
    """一个完整的 Agent 实例，由 9 个维度组成。"""
    identity: IdentityDim
    personality: PersonalityDim = PersonalityDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    goals: GoalsDim = GoalsDim()
    constraints: ConstraintsDim = ConstraintsDim()
    state: StateDim = StateDim()
    visual: VisualDim = VisualDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    relations: RelationsDim = RelationsDim()
