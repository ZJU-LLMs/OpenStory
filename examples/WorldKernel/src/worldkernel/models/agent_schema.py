"""Agent 实体 Schema — 固有维度子类 + 动态加载支持。

固有维度类（IdentityDim 等）定义 Agent 的基础结构。
Stage 1 自动生成的 agents_config.yaml 包含完整字段列表（固有 + 世界特有）。
Stage 2 实例化时可通过 load_agent_config() 获取当前世界的完整 schema。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


# ── 固有维度子类（全世界通用基础字段）────────────────────────────────

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


# ── 动态加载 ─────────────────────────────────────────────────────────

_DEFAULT_TEMPLATES_DIR = (
    Path(__file__).parent.parent.parent.parent / "templates"
)


def load_agent_config(session_id: str, base_dir: Path | None = None) -> dict[str, Any]:
    """加载指定 session 的 agent config（主文件 + 各维度）。"""
    root = base_dir or _DEFAULT_TEMPLATES_DIR
    configs_dir = root / session_id / "configs" / "agent"
    agent_path = configs_dir / "agent.yaml"
    if not agent_path.exists():
        raise FileNotFoundError(f"agent.yaml not found: {agent_path}")

    config = yaml.safe_load(agent_path.read_text(encoding="utf-8"))

    dims_dir = configs_dir / "dims"
    if dims_dir.exists():
        for dim_file in dims_dir.glob("*.yaml"):
            dim_name = dim_file.stem
            dim_data = yaml.safe_load(dim_file.read_text(encoding="utf-8"))
            if dim_name in config.get("dimensions", {}):
                config["dimensions"][dim_name]["fields"] = dim_data.get("fields", [])

    return config
