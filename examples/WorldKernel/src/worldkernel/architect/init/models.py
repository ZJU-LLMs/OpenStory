from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorldBackgroundArtifact(BaseModel):
    world_id: str = ""
    source_id: str = "primary"
    world_name: str = ""
    world_origin_summary: str = ""
    primary: str = ""
    secondary: str | None = None
    tags: list[str] = Field(default_factory=list)
    scope: str = ""
    simulation_start: dict[str, Any] = Field(default_factory=dict)
    visual_profile: dict[str, Any] = Field(default_factory=dict)
    world_constraints: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlanStepArtifact(BaseModel):
    step_id: str
    generator_type: str
    target_entity_type: str
    batch_size: int = 1
    priority: int = 1
    description: str = ""


class ExecutionPlanArtifact(BaseModel):
    steps: list[ExecutionPlanStepArtifact] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class SeedCatalogEntry(BaseModel):
    seed_id: str
    archetype_id: str
    name: str = ""
    importance: str = ""
    source_type: str = ""
    confidence: float = 0.0
    generation_priority: int = 1
    role_in_world: str = ""


class InstanceSeedBucketsArtifact(BaseModel):
    location: list[SeedCatalogEntry] = Field(default_factory=list)
    character: list[SeedCatalogEntry] = Field(default_factory=list)


class InstanceSeedCatalogArtifact(BaseModel):
    session_id: str
    instance_seeds: InstanceSeedBucketsArtifact = Field(default_factory=InstanceSeedBucketsArtifact)
    provenance: dict[str, Any] = Field(default_factory=dict)


class SchemaManifestEntryArtifact(BaseModel):
    alias: str
    file: str
    class_name: str
    version: str = "v1"
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SchemaManifestArtifact(BaseModel):
    schemas: list[SchemaManifestEntryArtifact] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class WorldTemplateArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    primary: str = ""
    secondary: str | None = None
    world_name: str = ""
    world_origin_summary: str = ""
    scope: str = ""
    simulation_start: dict[str, Any] = Field(default_factory=dict)
    visual_profile: dict[str, Any] = Field(default_factory=dict)
    location_archetypes: list[dict[str, Any]] = Field(default_factory=list)
    character_archetypes: list[dict[str, Any]] = Field(default_factory=list)
    rule_archetypes: list[dict[str, Any]] = Field(default_factory=list)
    world_constraints: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ArtifactManifest(BaseModel):
    session_id: str
    world_id: str
    world_background_path: str
    execution_plan_path: str
    instance_seed_catalog_path: str
    world_template_path: str | None = None
    schema_manifest_path: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class Stage1ArtifactBundle(BaseModel):
    world_background: WorldBackgroundArtifact
    execution_plan: ExecutionPlanArtifact
    seed_catalog: InstanceSeedCatalogArtifact
    schema_manifest: SchemaManifestArtifact | None = None
    world_template: WorldTemplateArtifact | None = None
    world_id: str
    source_id: str = "primary"
    provenance: dict[str, Any] = Field(default_factory=dict)


class ExecutionDAGNode(ExecutionPlanStepArtifact):
    depends_on: list[str] = Field(default_factory=list)
    tool_id: str = ""
    output_schema_alias: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)


class ExecutionDAG(BaseModel):
    nodes: list[ExecutionDAGNode] = Field(default_factory=list)
    execution_order: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ResolvedSeed(BaseModel):
    seed: SeedCatalogEntry
    entity_type: str
    source: str = "stage1_seed_catalog"
    provenance: dict[str, Any] = Field(default_factory=dict)

    @property
    def archetype_id(self) -> str:
        return self.seed.archetype_id

    @property
    def seed_id(self) -> str:
        return self.seed.seed_id

    @property
    def name(self) -> str:
        return self.seed.name

    @property
    def importance(self) -> str:
        return self.seed.importance

    @property
    def source_type(self) -> str:
        return self.seed.source_type

    @property
    def confidence(self) -> float:
        return self.seed.confidence

    @property
    def priority(self) -> int:
        return self.seed.generation_priority

    @property
    def role_in_world(self) -> str:
        return self.seed.role_in_world


class InitBuildContext(BaseModel):
    world_background: WorldBackgroundArtifact
    execution_dag: ExecutionDAG
    resolved_location_seeds: list[ResolvedSeed] = Field(default_factory=list)
    resolved_character_seeds: list[ResolvedSeed] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


# Backward-compatible aliases for earlier Stage2 naming.
RawStage1Bundle = Stage1ArtifactBundle
CompiledWorldBackground = WorldBackgroundArtifact
