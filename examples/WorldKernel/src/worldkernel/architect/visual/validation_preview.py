from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from worldkernel.architect.spatial.models import SpatialBlueprint
from worldkernel.architect.visual.models import VisualLayoutManifest


def render_visual_validation_preview(
    *,
    blueprint: SpatialBlueprint,
    spatial_root: str | Path,
    output_path: str | Path,
    report_path: str | Path | None = None,
    required_layers: set[str] | None = None,
) -> dict[str, Any]:
    """Compose visual assets and draw a debug-only Stage2 coordinate overlay."""

    root = Path(spatial_root)
    preview_path = Path(output_path)
    report_output = (
        Path(report_path)
        if report_path is not None
        else preview_path.with_name("visual_validation_report.json")
    )
    manifest = _load_manifest(blueprint, root)
    canvas_size = (
        int(blueprint.grid.width * blueprint.grid.tile_size),
        int(blueprint.grid.height * blueprint.grid.tile_size),
    )
    issues: list[dict[str, str]] = []
    _validate_manifest_coordinates(blueprint, manifest, canvas_size, issues)
    _validate_required_layer_statuses(manifest, required_layers or set(), issues)

    background_path = _asset_path(root, manifest.background.path, "background.png")
    composite = _load_required_background(background_path, canvas_size, issues)
    layers: list[dict[str, Any]] = [
        _layer_record("background", manifest.background.status, background_path, True)
    ]

    location_path = _asset_path(root, manifest.location_layer.path, "location_layer.png")
    location_enabled = manifest.location_layer.status in {"ready", "partial"}
    location_included = False
    if location_enabled:
        location = _load_optional_layer(location_path, canvas_size, "location_layer", issues)
        if location is not None:
            composite = Image.alpha_composite(composite, location)
            location_included = True
    layers.append(
        _layer_record(
            "location_layer",
            manifest.location_layer.status,
            location_path,
            location_included,
        )
    )

    layers.append(
        _layer_record(
            "roads_in_location_layer",
            "integrated" if manifest.location_layer.includes_roads else "missing",
            location_path,
            location_included and manifest.location_layer.includes_roads,
        )
    )

    preview = _draw_spatial_overlay(composite, blueprint)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview.convert("RGB").save(preview_path, format="PNG")

    report = {
        "world_id": blueprint.world_id,
        "coordinate_source": "spatial_blueprint.json",
        "canvas": {
            "width_px": canvas_size[0],
            "height_px": canvas_size[1],
            "tile_size": int(blueprint.grid.tile_size),
        },
        "preview_path": str(preview_path),
        "formal_assets_modified_by_preview": False,
        "frontend_manifest_reference_added": False,
        "layers": layers,
        "spatial_counts": {
            "regions": len(blueprint.regions),
            "routes": len(blueprint.routes),
            "road_tiles": len({(point.x, point.y) for point in blueprint.road_tiles}),
        },
        "overlay": {
            "location_bounds": "red",
            "location_number": "red_box_white_text",
            "entrance": "orange",
            "road_tiles": "cyan_translucent",
            "route_centerline": "cyan",
        },
        "location_index": [
            {
                "number": number,
                "location_id": region.location_id,
                "name": region.name,
                "bounds": dict(region.bounds),
                "entrance": dict(region.entrance),
            }
            for number, region in enumerate(blueprint.regions, start=1)
        ],
        "passed": not any(issue["severity"] == "error" for issue in issues),
        "issues": issues,
    }
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report["report_path"] = str(report_output)
    return report


def _load_manifest(
    blueprint: SpatialBlueprint,
    root: Path,
) -> VisualLayoutManifest:
    manifest_path = root / "visual_layout_manifest.json"
    if manifest_path.is_file():
        return VisualLayoutManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    if blueprint.visual:
        return VisualLayoutManifest.model_validate(blueprint.visual)
    raise FileNotFoundError(f"Visual layout manifest not found: {manifest_path}")


def _validate_manifest_coordinates(
    blueprint: SpatialBlueprint,
    manifest: VisualLayoutManifest,
    canvas_size: tuple[int, int],
    issues: list[dict[str, str]],
) -> None:
    manifest_size = (
        int(manifest.canvas.get("width_px") or 0),
        int(manifest.canvas.get("height_px") or 0),
    )
    if manifest_size != canvas_size:
        _issue(
            issues,
            "error",
            "canvas_mismatch",
            f"Manifest canvas {manifest_size} does not match Stage2 canvas {canvas_size}",
        )

    tile = int(blueprint.grid.tile_size)
    expected = {
        region.location_id: {
            "x": int(region.bounds.get("x", 0)) * tile,
            "y": int(region.bounds.get("y", 0)) * tile,
            "w": int(region.bounds.get("w", 0)) * tile,
            "h": int(region.bounds.get("h", 0)) * tile,
        }
        for region in blueprint.regions
    }
    actual = {slot.location_id: dict(slot.bounds_px) for slot in manifest.slots}
    if set(actual) != set(expected):
        _issue(
            issues,
            "error",
            "location_id_mismatch",
            "Manifest slot IDs do not match Stage2 region IDs",
        )
    for location_id in sorted(set(actual) & set(expected)):
        if actual[location_id] != expected[location_id]:
            _issue(
                issues,
                "error",
                "location_bounds_mismatch",
                f"{location_id}: manifest {actual[location_id]} != Stage2 {expected[location_id]}",
            )

    invalid_road_tiles = [
        (int(point.x), int(point.y))
        for point in blueprint.road_tiles
        if not (
            0 <= int(point.x) < int(blueprint.grid.width)
            and 0 <= int(point.y) < int(blueprint.grid.height)
        )
    ]
    if invalid_road_tiles:
        _issue(
            issues,
            "error",
            "road_tiles_out_of_bounds",
            f"Found {len(invalid_road_tiles)} road tiles outside the Stage2 grid",
        )


def _validate_required_layer_statuses(
    manifest: VisualLayoutManifest,
    required_layers: set[str],
    issues: list[dict[str, str]],
) -> None:
    statuses = {
        "background": manifest.background.status,
        "locations": manifest.location_layer.status,
        "roads": (
            "integrated"
            if manifest.location_layer.includes_roads
            and manifest.location_layer.status in {"ready", "partial"}
            else "missing"
        ),
    }
    accepted = {
        "background": {"ready"},
        "locations": {"ready", "partial"},
        "roads": {"integrated"},
    }
    for layer in sorted(required_layers):
        status = statuses.get(layer, "missing")
        if status not in accepted.get(layer, set()):
            _issue(
                issues,
                "error",
                f"required_{layer}_not_ready",
                f"Required layer {layer} ended with status {status}",
            )


def _load_required_background(
    path: Path,
    expected_size: tuple[int, int],
    issues: list[dict[str, str]],
) -> Image.Image:
    if not path.is_file():
        _issue(issues, "error", "background_missing", f"Background not found: {path}")
        return Image.new("RGBA", expected_size, (24, 28, 36, 255))
    with Image.open(path) as image:
        if image.size != expected_size:
            _issue(
                issues,
                "error",
                "background_size_mismatch",
                f"Background size {image.size} != {expected_size}",
            )
            return Image.new("RGBA", expected_size, (24, 28, 36, 255))
        return image.convert("RGBA")


def _load_optional_layer(
    path: Path,
    expected_size: tuple[int, int],
    label: str,
    issues: list[dict[str, str]],
) -> Image.Image | None:
    if not path.is_file():
        _issue(issues, "error", f"{label}_missing", f"Layer not found: {path}")
        return None
    with Image.open(path) as image:
        if image.size != expected_size:
            _issue(
                issues,
                "error",
                f"{label}_size_mismatch",
                f"Layer size {image.size} != {expected_size}",
            )
            return None
        return image.convert("RGBA")


def _draw_spatial_overlay(
    composite: Image.Image,
    blueprint: SpatialBlueprint,
) -> Image.Image:
    preview = composite.convert("RGBA")
    tile = int(blueprint.grid.tile_size)

    road_overlay = Image.new("RGBA", preview.size, (0, 0, 0, 0))
    road_draw = ImageDraw.Draw(road_overlay, "RGBA")
    for point in {(int(point.x), int(point.y)) for point in blueprint.road_tiles}:
        x, y = point
        road_draw.rectangle(
            (x * tile, y * tile, (x + 1) * tile - 1, (y + 1) * tile - 1),
            fill=(0, 190, 255, 48),
        )
    centerline_width = max(2, tile // 4)
    for route in blueprint.routes:
        points = [
            (int((point.x + 0.5) * tile), int((point.y + 0.5) * tile))
            for point in route.centerline
        ]
        if len(points) >= 2:
            road_draw.line(points, fill=(0, 220, 255, 220), width=centerline_width)
    preview = Image.alpha_composite(preview, road_overlay)

    draw = ImageDraw.Draw(preview, "RGBA")
    font = ImageFont.load_default()
    line_width = max(3, tile // 4)
    marker_radius = max(4, tile // 3)
    for number, region in enumerate(blueprint.regions, start=1):
        bounds = region.bounds or {}
        left = int(bounds.get("x", 0)) * tile
        top = int(bounds.get("y", 0)) * tile
        right = (int(bounds.get("x", 0)) + int(bounds.get("w", 0))) * tile - 1
        bottom = (int(bounds.get("y", 0)) + int(bounds.get("h", 0))) * tile - 1
        draw.rectangle(
            (left, top, right, bottom),
            outline=(255, 48, 48, 255),
            width=line_width,
        )

        label = str(number)
        label_box = draw.textbbox((0, 0), label, font=font)
        label_w = label_box[2] - label_box[0] + 8
        label_h = label_box[3] - label_box[1] + 6
        draw.rectangle(
            (left, top, left + label_w, top + label_h),
            fill=(190, 20, 20, 235),
        )
        draw.text((left + 4, top + 3), label, fill=(255, 255, 255, 255), font=font)

        entrance = region.entrance or {}
        entrance_x = int((int(entrance.get("x", 0)) + 0.5) * tile)
        entrance_y = int((int(entrance.get("y", 0)) + 0.5) * tile)
        draw.ellipse(
            (
                entrance_x - marker_radius,
                entrance_y - marker_radius,
                entrance_x + marker_radius,
                entrance_y + marker_radius,
            ),
            fill=(255, 145, 0, 245),
            outline=(255, 245, 190, 255),
            width=max(1, line_width // 2),
        )
    return preview


def _asset_path(root: Path, configured: str, fallback_name: str) -> Path:
    path = Path(configured) if configured else root / fallback_name
    return path if path.is_absolute() else root / path


def _layer_record(name: str, status: str, path: Path, included: bool) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "path": str(path),
        "exists": path.is_file(),
        "included_in_preview": included,
    }


def _issue(
    issues: list[dict[str, str]],
    severity: str,
    code: str,
    message: str,
) -> None:
    issues.append({"severity": severity, "code": code, "message": message})
