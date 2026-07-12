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
    target_size: dict[str, int] = Field(default_factory=dict)
    generation_strategy: str = ""
    error: str = ""


class VisualPatchAsset(BaseModel):
    location_id: str
    path: str = ""
    url: str = ""
    status: str = "missing"
    z_index: int = 0


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
    status: str = "ready"
    source: str = "spatial_blueprint.road_tiles"
    z_index: int = 30
    style: dict[str, Any] = Field(default_factory=dict)


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
    location_patches: list[VisualPatchAsset] = Field(default_factory=list)
    asset_contract: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
