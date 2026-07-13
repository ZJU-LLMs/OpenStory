from __future__ import annotations

from pathlib import Path
from typing import Any

from worldkernel.architect.spatial.models import SpatialBlueprint
from worldkernel.architect.visual.models import (
    VisualBackgroundAsset,
    VisualLayoutManifest,
    VisualLocationPlaceholderLayer,
    VisualRouteLayer,
    VisualSlot,
)


def build_visual_layout_manifest(
    blueprint: SpatialBlueprint,
    world_background: dict[str, Any] | None = None,
    output_root: str | Path | None = None,
) -> VisualLayoutManifest:
    profile = dict((world_background or {}).get("visual_profile") or {})
    projection = profile.get("camera_projection") or "严格正交俯视，接近垂直向下的二维地图视角"
    tile_size = blueprint.grid.tile_size
    canvas = {
        "grid_width": blueprint.grid.width,
        "grid_height": blueprint.grid.height,
        "tile_size": tile_size,
        "width_px": blueprint.grid.width * tile_size,
        "height_px": blueprint.grid.height * tile_size,
        "visual_clearance_tiles": 2,
    }

    slots: list[VisualSlot] = []
    ordered_regions = sorted(
        blueprint.regions,
        key=lambda region: (region.bounds.get("y", 0), region.bounds.get("x", 0)),
    )
    for index, region in enumerate(ordered_regions):
        bounds = region.bounds or {}
        slots.append(
            VisualSlot(
                location_id=region.location_id,
                bounds_px={
                    "x": int(bounds.get("x", 0) * tile_size),
                    "y": int(bounds.get("y", 0) * tile_size),
                    "w": int(bounds.get("w", 0) * tile_size),
                    "h": int(bounds.get("h", 0) * tile_size),
                },
                safe_padding_px=0,
                blend_margin_px=max(tile_size * 2, 24),
                z_index=100 + index,
                expected_projection=projection,
            )
        )

    root = Path(output_root) if output_root else Path("")
    background = VisualBackgroundAsset(
        path=str(root / "background.png") if output_root else "background.png",
        url="background.png",
        width_px=canvas["width_px"],
        height_px=canvas["height_px"],
        prompt_path=str(root / "background_prompt.json") if output_root else "background_prompt.json",
        metadata_path=str(root / "background_metadata.json") if output_root else "background_metadata.json",
        control_image_path=str(root / "generation_edit_base.png") if output_root else "generation_edit_base.png",
        mask_path=str(root / "generation_edit_mask.png") if output_root else "generation_edit_mask.png",
        edit_base_path=str(root / "generation_edit_base.png") if output_root else "generation_edit_base.png",
        edit_mask_path=str(root / "generation_edit_mask.png") if output_root else "generation_edit_mask.png",
        target_size={"width": canvas["width_px"], "height": canvas["height_px"]},
    )

    return VisualLayoutManifest(
        world_id=blueprint.world_id,
        canvas=canvas,
        mode="composited_full_map",
        visual_profile=profile,
        slots=slots,
        background=background,
        route_layer=VisualRouteLayer(
            status="ready",
            z_index=30,
            style={
                "kind": "pixel_ground_path",
                "base_color": "#b99d5c",
                "edge_color": "#8f7744",
                "highlight_color": "#d2bb75",
                "tile_size_px": tile_size,
            },
        ),
        location_placeholder_layer=VisualLocationPlaceholderLayer(
            status="ready",
            z_index=100,
            show_names=True,
            style={
                "fill_color": "rgba(45, 55, 78, 0.64)",
                "selected_fill_color": "rgba(232, 199, 102, 0.48)",
                "border_color": "rgba(230, 235, 245, 0.72)",
                "selected_border_color": "rgba(215, 162, 74, 0.96)",
                "label_color": "#f4f6fb",
            },
        ),
        decorations=[],
        location_patches=[],
        asset_contract={
            "layer_order": [
                "background.png",
                "route_layer",
                "location_placeholder_layer",
                "agents",
                "selection_tooltip_debug_grid",
            ],
            "shared_constraints": {
                "projection": projection,
                "fixed_art_style": "明亮整洁的俯视卡通像素模拟经营游戏风格",
                "image_postprocessing": "none",
                "texture_density": "low",
                "slot_visual_clearance_tiles": canvas["visual_clearance_tiles"],
                "lighting_weather": profile.get("lighting_weather", ""),
                "color_palette": profile.get("color_palette", []),
                "material_texture": profile.get("material_texture", []),
                "edge_blending_style": profile.get("edge_blending_style", ""),
                "reserved_asset_coverage": "opaque_exact_bounds",
            },
            "background_forbidden": ["道路", "具体地点", "人物", "文字", "界面元素"],
        },
        provenance={
            "source": "spatial_blueprint",
            "slot_count": len(slots),
            "location_patch_generation": "disabled",
            "layout_control": "full_size_edit_base_with_hard_mask",
            "mask_semantics": "transparent_pixels_editable_opaque_pixels_preserved",
        },
    )
