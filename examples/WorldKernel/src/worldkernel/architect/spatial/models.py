"""Spatial layer data models for input assembly and annotation maps."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Input assembly models
# ---------------------------------------------------------------------------


class SpatialInputWarning(BaseModel):
    code: str
    message: str
    source: str = ""
    item_index: int | None = None
    item_id: str = ""


class LocationSpatialFact(BaseModel):
    location_id: str
    name: str
    location_type: str = ""
    description: str = ""
    importance: str = ""
    access_level: str = ""
    capacity: int = 0
    tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class PathSpatialFact(BaseModel):
    path_id: str
    from_location_id: str
    to_location_id: str
    name: str = ""
    path_type: str = ""
    bidirectional: bool = True
    is_secret: bool = False
    access_level: str = ""
    danger_level: str = ""
    movement_hint: str = ""
    tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class CharacterPlacementFact(BaseModel):
    character_id: str
    name: str
    home_location_id: str = ""
    current_location_id: str = ""
    preferred_location_id: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class SpatialBuildInput(BaseModel):
    world_id: str
    source_root: str
    locations: list[LocationSpatialFact] = Field(default_factory=list)
    paths: list[PathSpatialFact] = Field(default_factory=list)
    characters: list[CharacterPlacementFact] = Field(default_factory=list)
    warnings: list[SpatialInputWarning] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Layout models
# ---------------------------------------------------------------------------


class LocationLayout(BaseModel):
    location_id: str
    center_x: int
    center_y: int
    layer_id: str = "ground"


class LayoutPlan(BaseModel):
    world_id: str
    grid_width: int
    grid_height: int
    tile_size: int
    locations: list[LocationLayout] = Field(default_factory=list)
    synthetic_edges: list[tuple[str, str]] = Field(default_factory=list)
    warnings: list[SpatialInputWarning] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Region packing models
# ---------------------------------------------------------------------------


class SpatialRegion(BaseModel):
    location_id: str
    name: str
    layer_id: str = "ground"
    x: int
    y: int
    width: int
    height: int
    entrance_x: int
    entrance_y: int
    tags: list[str] = Field(default_factory=list)


class RegionPackingResult(BaseModel):
    regions: list[SpatialRegion] = Field(default_factory=list)
    warnings: list[SpatialInputWarning] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Route rasterization models
# ---------------------------------------------------------------------------


class GridPoint(BaseModel):
    x: int
    y: int


class SpatialRoute(BaseModel):
    path_edge_id: str
    from_location_id: str
    to_location_id: str
    route_tiles: list[GridPoint] = Field(default_factory=list)
    route_type: str = "corridor"
    bidirectional: bool = True
    movement_cost: float = 1.0
    access_tags: list[str] = Field(default_factory=list)


class RouteRasterizationResult(BaseModel):
    routes: list[SpatialRoute] = Field(default_factory=list)
    road_tiles: list[GridPoint] = Field(default_factory=list)
    collision_grid: list[list[int]] = Field(default_factory=list)
    warnings: list[SpatialInputWarning] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Phase E1: Canonical artifact & validation models
# ---------------------------------------------------------------------------


class SpatialIndexes(BaseModel):
    location_id_to_region: dict[str, SpatialRegion] = Field(default_factory=dict)
    path_edge_id_to_route: dict[str, SpatialRoute] = Field(default_factory=dict)
    location_id_to_routes: dict[str, list[str]] = Field(default_factory=dict)


class CanonicalSpatialArtifact(BaseModel):
    world_id: str
    grid_width: int
    grid_height: int
    tile_size: int
    regions: list[SpatialRegion] = Field(default_factory=list)
    routes: list[SpatialRoute] = Field(default_factory=list)
    road_tiles: list[GridPoint] = Field(default_factory=list)
    collision_grid: list[list[int]] = Field(default_factory=list)
    indexes: SpatialIndexes = Field(default_factory=SpatialIndexes)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    code: str
    severity: str  # "error" | "warning"
    message: str
    affected_id: str = ""


class ValidationReport(BaseModel):
    passed: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class E1ValidationResult(BaseModel):
    artifact: CanonicalSpatialArtifact
    report: ValidationReport


# ---------------------------------------------------------------------------
# Phase G: Spatial blueprint models
# ---------------------------------------------------------------------------


class BlueprintGrid(BaseModel):
    width: int
    height: int
    tile_size: int


class BlueprintRegion(BaseModel):
    location_id: str
    name: str
    bounds: dict[str, int]  # {x, y, w, h}
    entrance: dict[str, int]  # {x, y}
    tags: list[str] = Field(default_factory=list)


class BlueprintRoute(BaseModel):
    path_edge_id: str
    from_location_id: str
    to_location_id: str
    centerline: list[GridPoint] = Field(default_factory=list)
    corridor_width: int = 3
    movement_cost: float = 1.0
    access_tags: list[str] = Field(default_factory=list)


class BlueprintSpawnPoint(BaseModel):
    character_id: str
    character_name: str
    location_id: str
    position: list[int]  # [x, y]


class SpatialBlueprint(BaseModel):
    world_id: str
    grid: BlueprintGrid
    collision: list[list[int]] = Field(default_factory=list)
    regions: list[BlueprintRegion] = Field(default_factory=list)
    routes: list[BlueprintRoute] = Field(default_factory=list)
    road_tiles: list[GridPoint] = Field(default_factory=list)
    spawn_points: list[BlueprintSpawnPoint] = Field(default_factory=list)
    visual: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
