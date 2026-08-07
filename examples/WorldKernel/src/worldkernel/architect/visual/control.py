from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw

from worldkernel.architect.spatial.models import SpatialBlueprint
from worldkernel.architect.visual.models import VisualLayoutManifest


EDITABLE_BASE_COLOR = (24, 28, 36)
LOCATION_RESERVED_COLOR = (128, 128, 128)
ROAD_RESERVED_COLOR = (184, 184, 184)


def render_layout_control_assets(
    blueprint: SpatialBlueprint,
    manifest: VisualLayoutManifest,
    output_root: str | Path,
) -> dict[str, Any]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    width = int(manifest.canvas["width_px"])
    height = int(manifest.canvas["height_px"])
    tile = int(blueprint.grid.tile_size)
    location_mask = _render_location_mask(blueprint, width, height, tile)
    road_mask = _render_road_mask(blueprint, width, height, tile)
    protection = ImageChops.lighter(location_mask, road_mask)
    edit_base = _render_edit_base(location_mask, road_mask)
    edit_mask = _render_edit_mask(protection)

    edit_base_path = root / "generation_edit_base.png"
    edit_mask_path = root / "generation_edit_mask.png"
    stale_guide_path = root / "generation_layout_guide.png"
    edit_base.save(edit_base_path, format="PNG")
    edit_mask.save(edit_mask_path, format="PNG")
    stale_guide_path.unlink(missing_ok=True)
    location_pixels = location_mask.histogram()[255]
    road_pixels = road_mask.histogram()[255]
    expected_location_pixels = _expected_location_pixels(blueprint, width, height, tile)
    if location_pixels != expected_location_pixels:
        raise ValueError(
            "Location mask coverage does not match the exact region bounds: "
            f"expected {expected_location_pixels} pixels, got {location_pixels}"
        )
    expected_road_pixels = (
        len({(int(point.x), int(point.y)) for point in blueprint.road_tiles}) * tile * tile
    )
    if road_pixels != expected_road_pixels:
        raise ValueError(
            "Road mask coverage does not match the unique road tiles: "
            f"expected {expected_road_pixels} pixels, got {road_pixels}"
        )
    return {
        "control_image_path": str(edit_base_path),
        "edit_base_path": str(edit_base_path),
        "edit_mask_path": str(edit_mask_path),
        "mask_path": str(edit_mask_path),
        "target_size": {"width": width, "height": height},
        "protected_pixels": protection.histogram()[255],
        "editable_pixels": width * height - protection.histogram()[255],
        "location_region_count": len(blueprint.regions),
        "location_pixels": location_pixels,
        "road_tile_count": len({(int(point.x), int(point.y)) for point in blueprint.road_tiles}),
        "road_pixels": road_pixels,
        "mask_semantics": "transparent_pixels_editable_opaque_pixels_preserved",
        "stage2_layout_used": True,
        "visual_clearance_tiles": int(manifest.canvas.get("visual_clearance_tiles") or 0),
    }


def validate_protected_regions(
    input_path: str | Path,
    generated_path: str | Path,
    mask_path: str | Path,
    *,
    expected_size: tuple[int, int],
    blueprint: SpatialBlueprint,
    channel_tolerance: int = 8,
    max_location_changed_ratio: float = 0.5,
    max_road_changed_ratio: float = 0.9,
    fail_on_excessive_change: bool = True,
) -> dict[str, Any]:
    with Image.open(input_path) as input_image:
        source = input_image.convert("RGB")
    with Image.open(generated_path) as generated_image:
        generated = generated_image.convert("RGB")
    with Image.open(mask_path) as mask_image:
        if mask_image.mode != "RGBA":
            raise ValueError(f"Edit mask must be RGBA, got {mask_image.mode}")
        protection = mask_image.getchannel("A")

    for label, image in (("Edit base", source), ("Generated image", generated), ("Edit mask", protection)):
        if image.size != expected_size:
            raise ValueError(f"{label} size {image.size} does not match target size {expected_size}")

    protected_pixels = protection.histogram()[255]
    if not protected_pixels:
        return {
            "protected_pixels": 0,
            "changed_pixels": 0,
            "changed_ratio": 0.0,
            "channel_tolerance": channel_tolerance,
            "max_location_changed_ratio": max_location_changed_ratio,
            "max_road_changed_ratio": max_road_changed_ratio,
            "fail_on_excessive_change": fail_on_excessive_change,
            "restored_pixels": 0,
            "exact_preservation_after_restore": True,
            "passed": True,
        }

    difference = ImageChops.difference(source, generated)
    red, green, blue = difference.split()
    max_difference = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    protected_difference = ImageChops.multiply(max_difference, protection)
    changed = protected_difference.point(lambda value: 255 if value > channel_tolerance else 0)
    changed_pixels = changed.histogram()[255]
    changed_ratio = changed_pixels / protected_pixels
    tile = int(blueprint.grid.tile_size)
    location_changed_ratios: dict[str, float] = {}
    for region in blueprint.regions:
        bounds = region.bounds or {}
        box = _clamp_box(
            (
                int(bounds.get("x", 0) * tile),
                int(bounds.get("y", 0) * tile),
                int((bounds.get("x", 0) + bounds.get("w", 0)) * tile) - 1,
                int((bounds.get("y", 0) + bounds.get("h", 0)) * tile) - 1,
            ),
            expected_size[0],
            expected_size[1],
        )
        cropped = changed.crop((box[0], box[1], box[2] + 1, box[3] + 1))
        region_pixels = cropped.width * cropped.height
        location_changed_ratios[region.location_id] = (
            cropped.histogram()[255] / region_pixels if region_pixels else 0.0
        )
    worst_location_ratio = max(location_changed_ratios.values(), default=0.0)

    road_mask = _render_road_mask(
        blueprint,
        expected_size[0],
        expected_size[1],
        tile,
    )
    road_pixels = road_mask.histogram()[255]
    changed_road_pixels = ImageChops.multiply(changed, road_mask).histogram()[255]
    road_changed_ratio = changed_road_pixels / road_pixels if road_pixels else 0.0

    result = {
        "protected_pixels": protected_pixels,
        "changed_pixels": changed_pixels,
        "changed_ratio": changed_ratio,
        "channel_tolerance": channel_tolerance,
        "location_changed_ratios": location_changed_ratios,
        "worst_location_changed_ratio": worst_location_ratio,
        "road_changed_ratio": road_changed_ratio,
        "max_location_changed_ratio": max_location_changed_ratio,
        "max_road_changed_ratio": max_road_changed_ratio,
        "fail_on_excessive_change": fail_on_excessive_change,
        "restored_pixels": changed_pixels,
        "exact_preservation_after_restore": True,
        "passed": (
            worst_location_ratio <= max_location_changed_ratio
            and road_changed_ratio <= max_road_changed_ratio
        ),
    }
    restored = generated.copy()
    restored.paste(source, mask=protection)
    restored.save(generated_path, format="PNG")
    if not result["passed"] and fail_on_excessive_change:
        raise RuntimeError(
            "Image edit provider ignored one or more hard-mask regions: "
            f"worst location change {worst_location_ratio:.2%} "
            f"(allowed {max_location_changed_ratio:.2%}), road change {road_changed_ratio:.2%} "
            f"(allowed {max_road_changed_ratio:.2%})"
        )

    return result


def finalize_generated_background(
    generated_path: str | Path,
    output_path: str | Path,
    *,
    target_size: tuple[int, int],
    blueprint: SpatialBlueprint,
    placeholder_style: dict[str, Any],
) -> dict[str, Any]:
    generated_path = Path(generated_path)
    with Image.open(generated_path) as generated_image:
        original_size = generated_image.size
        generated = generated_image.convert("RGBA")
    if original_size != target_size:
        raise ValueError(f"Generated image size {original_size} does not match target size {target_size}")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    generated.convert("RGB").save(output, format="PNG")
    return {
        "input_size": {"width": original_size[0], "height": original_size[1]},
        "output_size": {"width": target_size[0], "height": target_size[1]},
        "resized": False,
        "postprocessing": "none",
        "protected_region_composite": "none",
        "composited_layers": [],
        "route_placeholder_composited": False,
        "road_reserved_pixels_cleaned": 0,
        "location_reserved_pixels_postprocessed": False,
        "route_tile_count": len(blueprint.road_tiles),
        "location_placeholder_count": 0,
    }


def clean_road_reserved_pixels(
    image: Image.Image,
    blueprint: SpatialBlueprint,
    tile: int,
) -> int:
    road_tiles = {(int(point.x), int(point.y)) for point in blueprint.road_tiles}
    location_tiles = _location_tiles(blueprint)
    return _fill_reserved_tiles_with_nearby_ground(
        image,
        tiles=road_tiles,
        blocked_tiles=road_tiles | location_tiles,
        tile=tile,
        grid_size=(blueprint.grid.width, blueprint.grid.height),
    )


def _location_tiles(blueprint: SpatialBlueprint) -> set[tuple[int, int]]:
    tiles: set[tuple[int, int]] = set()
    for region in blueprint.regions:
        bounds = region.bounds or {}
        x0 = int(bounds.get("x", 0))
        y0 = int(bounds.get("y", 0))
        width = max(0, int(bounds.get("w", 0)))
        height = max(0, int(bounds.get("h", 0)))
        tiles.update(
            (x, y)
            for y in range(y0, y0 + height)
            for x in range(x0, x0 + width)
        )
    return tiles


def _fill_reserved_tiles_with_nearby_ground(
    image: Image.Image,
    *,
    tiles: set[tuple[int, int]],
    blocked_tiles: set[tuple[int, int]],
    tile: int,
    grid_size: tuple[int, int],
) -> int:
    source = image.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    cleaned_pixels = 0
    for x, y in tiles:
        color = _sample_nearby_ground_color(
            source,
            x=x,
            y=y,
            tile=tile,
            blocked_tiles=blocked_tiles,
            grid_size=grid_size,
        )
        x0, y0 = x * tile, y * tile
        draw.rectangle(
            (x0, y0, x0 + tile - 1, y0 + tile - 1),
            fill=color + (255,),
        )
        cleaned_pixels += tile * tile
    return cleaned_pixels


def _sample_nearby_ground_color(
    image: Image.Image,
    *,
    x: int,
    y: int,
    tile: int,
    blocked_tiles: set[tuple[int, int]],
    grid_size: tuple[int, int],
) -> tuple[int, int, int]:
    grid_width, grid_height = grid_size
    candidates: list[tuple[int, int]] = []
    for radius in range(1, max(grid_width, grid_height) + 1):
        ring: list[tuple[int, int]] = []
        for offset in range(-radius, radius + 1):
            ring.extend(
                [
                    (x + offset, y - radius),
                    (x + offset, y + radius),
                    (x - radius, y + offset),
                    (x + radius, y + offset),
                ]
            )
        candidates = [
            point
            for point in dict.fromkeys(ring)
            if 0 <= point[0] < grid_width
            and 0 <= point[1] < grid_height
            and point not in blocked_tiles
        ]
        if candidates:
            break
    if not candidates:
        return EDITABLE_BASE_COLOR

    samples: list[tuple[int, int, int]] = []
    for tile_x, tile_y in candidates:
        crop = image.crop(
            (
                tile_x * tile,
                tile_y * tile,
                (tile_x + 1) * tile,
                (tile_y + 1) * tile,
            )
        )
        pixels = (
            crop.get_flattened_data()
            if hasattr(crop, "get_flattened_data")
            else crop.getdata()
        )
        samples.extend(pixels)
    return _dominant_ground_color(samples)


def _dominant_ground_color(samples: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    quantized = [tuple((channel // 16) * 16 for channel in pixel[:3]) for pixel in samples]
    reserved = {
        tuple((channel // 16) * 16 for channel in LOCATION_RESERVED_COLOR),
        tuple((channel // 16) * 16 for channel in ROAD_RESERVED_COLOR),
    }
    for color, _count in Counter(quantized).most_common():
        if color not in reserved:
            return color
    return EDITABLE_BASE_COLOR


def _draw_location_placeholders(
    draw: ImageDraw.ImageDraw,
    blueprint: SpatialBlueprint,
    tile: int,
    style: dict[str, Any],
) -> None:
    fill = _parse_color(style.get("fill_color"), (45, 55, 78, 255), force_opaque=True)
    border = _parse_color(style.get("border_color"), (230, 235, 245, 255), force_opaque=True)
    stripe = tuple(min(255, channel + 22) for channel in fill[:3]) + (255,)
    border_width = max(2, tile // 4)
    stripe_width = max(1, tile // 8)
    for region in blueprint.regions:
        bounds = region.bounds or {}
        x0 = int(bounds.get("x", 0) * tile)
        y0 = int(bounds.get("y", 0) * tile)
        x1 = int((bounds.get("x", 0) + bounds.get("w", 0)) * tile) - 1
        y1 = int((bounds.get("y", 0) + bounds.get("h", 0)) * tile) - 1
        box = _clamp_box((x0, y0, x1, y1), blueprint.grid.width * tile, blueprint.grid.height * tile)
        draw.rectangle(box, fill=fill, outline=border, width=border_width)
        for y in range(y0 + tile, y1, tile):
            draw.line((x0 + border_width, y, x1 - border_width, y), fill=stripe, width=stripe_width)


def _parse_color(
    value: Any,
    default: tuple[int, int, int, int],
    *,
    force_opaque: bool = False,
) -> tuple[int, int, int, int]:
    text = str(value or "").strip().lower()
    channels: tuple[int, int, int, int] | None = None
    if text.startswith("#") and len(text) in {4, 7}:
        raw = text[1:]
        if len(raw) == 3:
            raw = "".join(char * 2 for char in raw)
        try:
            channels = tuple(int(raw[index : index + 2], 16) for index in (0, 2, 4)) + (255,)
        except ValueError:
            channels = None
    elif text.startswith(("rgb(", "rgba(")) and text.endswith(")"):
        parts = [part.strip() for part in text[text.index("(") + 1 : -1].split(",")]
        try:
            red, green, blue = (max(0, min(255, int(float(part)))) for part in parts[:3])
            alpha = 255
            if len(parts) > 3:
                alpha_value = float(parts[3])
                alpha = round(alpha_value * 255) if alpha_value <= 1 else round(alpha_value)
            channels = (red, green, blue, max(0, min(255, alpha)))
        except (TypeError, ValueError):
            channels = None
    result = channels or default
    return result[:3] + ((255,) if force_opaque else (result[3],))


def _render_location_mask(
    blueprint: SpatialBlueprint,
    width: int,
    height: int,
    tile: int,
) -> Image.Image:
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for region in blueprint.regions:
        bounds = region.bounds or {}
        x0 = int(bounds.get("x", 0) * tile)
        y0 = int(bounds.get("y", 0) * tile)
        x1 = int((bounds.get("x", 0) + bounds.get("w", 0)) * tile) - 1
        y1 = int((bounds.get("y", 0) + bounds.get("h", 0)) * tile) - 1
        draw.rectangle(_clamp_box((x0, y0, x1, y1), width, height), fill=255)
    return mask


def _render_edit_base(location_mask: Image.Image, road_mask: Image.Image) -> Image.Image:
    image = Image.new("RGB", location_mask.size, EDITABLE_BASE_COLOR)
    image.paste(ROAD_RESERVED_COLOR, mask=road_mask)
    image.paste(LOCATION_RESERVED_COLOR, mask=location_mask)
    return image


def _render_edit_mask(protection: Image.Image) -> Image.Image:
    mask = Image.new("RGBA", protection.size, (255, 255, 255, 0))
    mask.putalpha(protection)
    return mask


def _expected_location_pixels(
    blueprint: SpatialBlueprint,
    width: int,
    height: int,
    tile: int,
) -> int:
    total = 0
    for region in blueprint.regions:
        bounds = region.bounds or {}
        x0 = max(0, int(bounds.get("x", 0) * tile))
        y0 = max(0, int(bounds.get("y", 0) * tile))
        x1 = min(width, int((bounds.get("x", 0) + bounds.get("w", 0)) * tile))
        y1 = min(height, int((bounds.get("y", 0) + bounds.get("h", 0)) * tile))
        total += max(0, x1 - x0) * max(0, y1 - y0)
    return total


def _render_road_mask(
    blueprint: SpatialBlueprint,
    width: int,
    height: int,
    tile: int,
) -> Image.Image:
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)

    for point in blueprint.road_tiles:
        x0 = int(point.x * tile)
        y0 = int(point.y * tile)
        x1 = int((point.x + 1) * tile) - 1
        y1 = int((point.y + 1) * tile) - 1
        draw.rectangle(_clamp_box((x0, y0, x1, y1), width, height), fill=255)
    return mask




def _clamp_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return max(0, x0), max(0, y0), min(width - 1, x1), min(height - 1, y1)
