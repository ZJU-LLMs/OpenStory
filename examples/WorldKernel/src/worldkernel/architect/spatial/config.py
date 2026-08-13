"""Spatial generation configuration loaded from architect.yaml."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

# ``config.py`` lives at ``src/worldkernel/architect/spatial``.  The example's
# canonical configuration is under ``examples/WorldKernel/configs`` rather
# than under ``src/configs``.
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[4] / "configs" / "architect.yaml"


class SpatialCanvasConfig(BaseModel):
    grid_width: int = 160
    grid_height: int = 100
    tile_size: int = 16
    margin_tiles: int = 6
    default_region_min_size: list[int] = Field(default_factory=lambda: [8, 6])
    default_region_max_size: list[int] = Field(default_factory=lambda: [22, 16])
    corridor_width: int = 3


class SpatialGridValuesConfig(BaseModel):
    blocked: int = 0
    walkable: int = 1

    @model_validator(mode="after")
    def _check_values(self) -> SpatialGridValuesConfig:
        if self.blocked != 0:
            raise ValueError("grid_values.blocked must be 0")
        if self.walkable != 1:
            raise ValueError("grid_values.walkable must be 1")
        return self


class SpatialLayoutConfig(BaseModel):
    algorithm: str = "fr_constraint_rect_packing"
    random_seed: int = 42
    fr_iterations: int = 200
    packing_max_attempts: int = 2000
    default_layer_id: str = "ground"
    min_region_gap: int = 6
    preferred_region_gap: int = 10
    edge_comfort_margin: int = 12
    candidate_limit: int = 256


class SpatialRoutingConfig(BaseModel):
    algorithm: str = "orthogonal_astar"
    allow_diagonal: bool = False
    default_movement_cost: float = 1.0
    secret_path_cost_multiplier: float = 1.5


class SpatialRenderingConfig(BaseModel):
    export_tiled_json: bool = True
    export_preview_png: bool = True
    background_mode: str = "simple_tile"
    ai_art_enabled: bool = False
    location_layer_enabled: bool = False
    character_atlas_enabled: bool = True
    characters_per_atlas: int = Field(default=6, ge=1, le=6)
    character_key_colors: list[str] = Field(
        default_factory=lambda: ["#00ff00", "#ff00ff", "#00ffff"]
    )
    character_transparent_threshold: int = Field(default=24, ge=0, le=255)
    character_opaque_threshold: int = Field(default=96, ge=1, le=441)
    visual_mode: Literal["composited_full_map"] = "composited_full_map"

    @model_validator(mode="after")
    def _check_character_atlas(self) -> SpatialRenderingConfig:
        if self.character_opaque_threshold <= self.character_transparent_threshold:
            raise ValueError(
                "rendering.character_opaque_threshold must exceed "
                "character_transparent_threshold"
            )
        if not self.character_key_colors:
            raise ValueError("rendering.character_key_colors must not be empty")
        return self


class SpatialValidationConfig(BaseModel):
    require_all_locations_reachable: bool = True
    require_path_edges_routable: bool = True
    max_region_overlap_ratio: float = 0.0
    min_entrances_per_location: int = 1


class SpatialGenerationConfig(BaseModel):
    enabled: bool = True
    output_subdir: str = "stage2/spatial"
    canvas: SpatialCanvasConfig = Field(default_factory=SpatialCanvasConfig)
    grid_values: SpatialGridValuesConfig = Field(default_factory=SpatialGridValuesConfig)
    layout: SpatialLayoutConfig = Field(default_factory=SpatialLayoutConfig)
    routing: SpatialRoutingConfig = Field(default_factory=SpatialRoutingConfig)
    rendering: SpatialRenderingConfig = Field(default_factory=SpatialRenderingConfig)
    validation: SpatialValidationConfig = Field(default_factory=SpatialValidationConfig)


def load_spatial_generation_config(
    path: str | Path | None = None,
) -> SpatialGenerationConfig:
    """Load spatial_generation config from architect.yaml.

    Returns defaults when the file is missing, empty, or lacks a
    ``spatial_generation`` section.
    """
    p = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not p.exists():
        logger.info("Config file %s not found; using default spatial config", p)
        return SpatialGenerationConfig()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    spatial_data = data.get("spatial_generation")
    if not spatial_data:
        logger.info("No spatial_generation section in %s; using defaults", p)
        return SpatialGenerationConfig()
    return SpatialGenerationConfig.model_validate(spatial_data)
