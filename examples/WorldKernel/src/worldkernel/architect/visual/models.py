from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VisualSlot(BaseModel):
    location_id: str
    bounds_px: dict[str, int]
    safe_padding_px: int
    blend_margin_px: int
    z_index: int
    expected_projection: str
    entrance_port: dict[str, Any] = Field(default_factory=dict)


class VisualBackgroundAsset(BaseModel):
    path: str = ""
    url: str = ""
    width_px: int = 0
    height_px: int = 0
    provider: str = ""
    model: str = ""
    status: str = "pending"
    prompt_path: str = ""
    metadata_path: str = ""
    layout_preview_path: str = ""
    control_image_path: str = ""
    mask_path: str = ""
    edit_base_path: str = ""
    edit_mask_path: str = ""
    debug_mask_path: str = ""
    location_mask_path: str = ""
    road_mask_path: str = ""
    target_size: dict[str, int] = Field(default_factory=dict)
    generation_strategy: str = ""
    asset_version: str = ""
    composited_layers: list[str] = Field(default_factory=list)
    error: str = ""


class VisualLocationLayer(BaseModel):
    status: str = "missing"
    source: str = "full_canvas_visual_review"
    z_index: int = 100
    path: str = ""
    url: str = ""
    width_px: int = 0
    height_px: int = 0
    prompt_dir: str = ""
    metadata_path: str = ""
    provider: str = ""
    model: str = ""
    asset_version: str = ""
    generation_strategy: str = ""
    completed_location_ids: list[str] = Field(default_factory=list)
    failed_location_ids: list[str] = Field(default_factory=list)
    evaluation_status: str = "missing"
    evaluation_model: str = ""
    evaluation_report_path: str = ""
    attempt_count: int = 0
    selected_attempt: int = 0
    alignment_score: float = 0.0
    includes_roads: bool = False
    error: str = ""


class VisualDecoration(BaseModel):
    decoration_id: str
    kind: str
    x_px: int
    y_px: int
    w_px: int
    h_px: int
    z_index: int = 20
    variant: int = 0


class VisualRouteLayer(BaseModel):
    status: str = "placeholder"
    source: str = "spatial_blueprint.road_tiles"
    z_index: int = 150
    style: dict[str, Any] = Field(default_factory=dict)
    path: str = ""
    url: str = ""
    width_px: int = 0
    height_px: int = 0
    atlas_path: str = ""
    prompt_path: str = ""
    metadata_path: str = ""
    provider: str = ""
    model: str = ""
    asset_version: str = ""
    error: str = ""


class VisualLocationPlaceholderLayer(BaseModel):
    status: str = "ready"
    z_index: int = 100
    show_names: bool = True
    style: dict[str, Any] = Field(default_factory=dict)


class VisualLayoutManifest(BaseModel):
    world_id: str
    canvas: dict[str, int]
    mode: str = "composited_full_map"
    visual_profile: dict[str, Any] = Field(default_factory=dict)
    slots: list[VisualSlot] = Field(default_factory=list)
    background: VisualBackgroundAsset = Field(default_factory=VisualBackgroundAsset)
    route_layer: VisualRouteLayer = Field(default_factory=VisualRouteLayer)
    location_placeholder_layer: VisualLocationPlaceholderLayer = Field(default_factory=VisualLocationPlaceholderLayer)
    decorations: list[VisualDecoration] = Field(default_factory=list)
    location_layer: VisualLocationLayer = Field(default_factory=VisualLocationLayer)
    asset_contract: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
