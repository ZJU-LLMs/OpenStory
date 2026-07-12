from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from worldkernel.architect.spatial.models import SpatialBlueprint
from worldkernel.architect.visual.models import VisualLayoutManifest


def render_layout_control_assets(
    blueprint: SpatialBlueprint,
    manifest: VisualLayoutManifest,
    output_root: str | Path,
) -> dict[str, Any]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    width = int(manifest.canvas["width_px"])
    height = int(manifest.canvas["height_px"])
    tile = int(manifest.canvas["tile_size"])
    visual_clearance_tiles = int(manifest.canvas.get("visual_clearance_tiles") or 0)

    base = _render_neutral_base(width, height, manifest.visual_profile, blueprint.world_id, tile)
    control = base.copy()
    _render_reserved_layout_context(
        control,
        blueprint,
        tile,
        visual_clearance_tiles=visual_clearance_tiles,
    )
    protection = _render_protection_mask(blueprint, width, height, tile)
    preview = _render_layout_preview(blueprint, width, height, tile)

    base_path = root / "generation_base.png"
    control_path = root / "generation_control.png"
    mask_path = root / "generation_mask.png"
    preview_path = root / "layout_preview.png"
    base.save(base_path, format="PNG")
    control.save(control_path, format="PNG")
    _to_openai_mask(protection).save(mask_path, format="PNG")
    preview.save(preview_path, format="PNG")

    protected_pixels = width * height - protection.histogram()[0]
    return {
        "layout_preview_path": str(preview_path),
        "control_image_path": str(control_path),
        "protected_underlay_path": str(base_path),
        "mask_path": str(mask_path),
        "target_size": {"width": width, "height": height},
        "protected_pixels": protected_pixels,
        "editable_pixels": width * height - protected_pixels,
        "visual_clearance_tiles": visual_clearance_tiles,
    }


def composite_protected_background(
    generated_path: str | Path,
    base_path: str | Path,
    mask_path: str | Path,
    output_path: str | Path,
    *,
    target_size: tuple[int, int],
) -> dict[str, Any]:
    generated = Image.open(generated_path).convert("RGB")
    original_size = generated.size
    if generated.size != target_size:
        raise ValueError(f"Generated image size {generated.size} does not match target size {target_size}")

    base = Image.open(base_path).convert("RGB")
    if base.size != target_size:
        raise ValueError(f"Control image size {base.size} does not match target size {target_size}")

    rgba_mask = Image.open(mask_path).convert("RGBA")
    protection = rgba_mask.getchannel("A")
    if protection.size != target_size:
        raise ValueError(f"Protection mask size {protection.size} does not match target size {target_size}")

    composited = Image.composite(base, generated, protection)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    composited.save(output, format="PNG")
    return {
        "input_size": {"width": original_size[0], "height": original_size[1]},
        "output_size": {"width": target_size[0], "height": target_size[1]},
        "resized": False,
        "postprocessing": "none",
        "protected_region_composite": "binary_mask",
    }


def _render_neutral_base(
    width: int,
    height: int,
    profile: dict[str, Any],
    world_id: str,
    tile: int,
) -> Image.Image:
    base_color = _profile_base_color(profile)
    image = Image.new("RGB", (width, height), base_color)
    draw = ImageDraw.Draw(image)
    rng = random.Random(_stable_seed(world_id))
    step = max(4, tile // 2)
    for y in range(0, height, step):
        for x in range(0, width, step):
            delta = rng.choice((-7, -4, -2, 0, 0, 2, 4, 6))
            color = tuple(max(0, min(255, channel + delta)) for channel in base_color)
            draw.rectangle((x, y, min(width - 1, x + step - 1), min(height - 1, y + step - 1)), fill=color)
    return image


def _render_reserved_layout_context(
    image: Image.Image,
    blueprint: SpatialBlueprint,
    tile: int,
    *,
    visual_clearance_tiles: int,
) -> None:
    draw = ImageDraw.Draw(image)
    base_color = image.getpixel((0, 0))
    road_color = _blend_color(base_color, (202, 188, 156), 0.58)
    slot_outer = _blend_color(base_color, (66, 70, 72), 0.62)
    slot_inner = _blend_color(base_color, (168, 158, 142), 0.72)
    slot_highlight = _blend_color(slot_inner, (232, 224, 205), 0.34)
    clearance_color = (244, 170, 54)

    for point in blueprint.road_tiles:
        draw.rectangle(
            (
                point.x * tile,
                point.y * tile,
                (point.x + 1) * tile - 1,
                (point.y + 1) * tile - 1,
            ),
            fill=road_color,
        )

    outline_width = max(2, tile // 4)
    inset = max(outline_width + 1, tile // 2)
    ordered_regions = sorted(
        blueprint.regions,
        key=lambda region: (
            int((region.bounds or {}).get("y", 0)),
            int((region.bounds or {}).get("x", 0)),
            region.location_id,
        ),
    )
    marker_font = _load_font(max(14, tile * 2))
    clearance_px = max(0, visual_clearance_tiles) * tile
    for index, region in enumerate(ordered_regions, start=1):
        bounds = region.bounds or {}
        x0 = int(bounds.get("x", 0) * tile)
        y0 = int(bounds.get("y", 0) * tile)
        x1 = int((bounds.get("x", 0) + bounds.get("w", 0)) * tile) - 1
        y1 = int((bounds.get("y", 0) + bounds.get("h", 0)) * tile) - 1
        if clearance_px:
            clearance_box = _clamp_box(
                (x0 - clearance_px, y0 - clearance_px, x1 + clearance_px, y1 + clearance_px),
                image.width,
                image.height,
            )
            draw.rectangle(clearance_box, outline=clearance_color, width=outline_width)
        box = _clamp_box((x0, y0, x1, y1), image.width, image.height)
        draw.rectangle(box, fill=slot_outer)
        inner = _clamp_box((x0 + inset, y0 + inset, x1 - inset, y1 - inset), image.width, image.height)
        if inner[0] <= inner[2] and inner[1] <= inner[3]:
            draw.rectangle(inner, fill=slot_inner)
            ridge_y = (inner[1] + inner[3]) // 2
            draw.line((inner[0], ridge_y, inner[2], ridge_y), fill=slot_highlight, width=outline_width)
        marker = str(index)
        marker_box = draw.textbbox((0, 0), marker, font=marker_font)
        marker_x = x0 + (x1 - x0 - (marker_box[2] - marker_box[0])) / 2
        marker_y = y0 + (y1 - y0 - (marker_box[3] - marker_box[1])) / 2
        draw.text(
            (marker_x, marker_y),
            marker,
            font=marker_font,
            fill=(255, 230, 72),
            stroke_width=max(1, tile // 8),
            stroke_fill=(32, 38, 40),
        )


def _render_protection_mask(
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

        entrance = region.entrance or {}
        ex = int(entrance.get("x", 0))
        ey = int(entrance.get("y", 0))
        draw.rectangle(
            _clamp_box((ex * tile, ey * tile, (ex + 1) * tile - 1, (ey + 1) * tile - 1), width, height),
            fill=255,
        )

    for point in blueprint.road_tiles:
        x0 = int(point.x * tile)
        y0 = int(point.y * tile)
        x1 = int((point.x + 1) * tile) - 1
        y1 = int((point.y + 1) * tile) - 1
        draw.rectangle(_clamp_box((x0, y0, x1, y1), width, height), fill=255)
    return mask


def _render_layout_preview(
    blueprint: SpatialBlueprint,
    width: int,
    height: int,
    tile: int,
) -> Image.Image:
    image = Image.new("RGB", (width, height), "#171b2b")
    draw = ImageDraw.Draw(image, "RGBA")
    grid_color = (100, 118, 155, 28)
    for x in range(0, width + 1, tile):
        draw.line((x, 0, x, height), fill=grid_color, width=1)
    for y in range(0, height + 1, tile):
        draw.line((0, y, width, y), fill=grid_color, width=1)

    for point in blueprint.road_tiles:
        draw.rectangle(
            (point.x * tile, point.y * tile, (point.x + 1) * tile, (point.y + 1) * tile),
            fill=(112, 218, 246, 190),
        )

    font = _load_font(max(12, tile))
    for index, region in enumerate(blueprint.regions):
        bounds = region.bounds or {}
        x0 = int(bounds.get("x", 0) * tile)
        y0 = int(bounds.get("y", 0) * tile)
        x1 = int((bounds.get("x", 0) + bounds.get("w", 0)) * tile)
        y1 = int((bounds.get("y", 0) + bounds.get("h", 0)) * tile)
        fill = (68, 76, 105, 210) if index % 3 else (126, 58, 70, 210)
        draw.rectangle((x0, y0, x1, y1), fill=fill, outline=(224, 231, 246, 190), width=max(1, tile // 8))
        label = region.name or region.location_id
        _draw_centered_label(draw, (x0, y0, x1, y1), label, font)
        entrance = region.entrance or {}
        ex = int((entrance.get("x", 0) + 0.5) * tile)
        ey = int((entrance.get("y", 0) + 0.5) * tile)
        radius = max(3, tile // 3)
        draw.ellipse((ex - radius, ey - radius, ex + radius, ey + radius), fill=(255, 196, 40, 255))
    return image


def _to_openai_mask(protection: Image.Image) -> Image.Image:
    image = Image.new("RGBA", protection.size, (255, 255, 255, 0))
    image.putalpha(protection)
    return image


def _profile_base_color(profile: dict[str, Any]) -> tuple[int, int, int]:
    palette = profile.get("color_palette") or []
    for value in palette:
        match = re.search(r"#[0-9a-fA-F]{6}", str(value))
        if match:
            raw = match.group(0)[1:]
            return tuple(int(raw[index : index + 2], 16) for index in (0, 2, 4))
    context_values = [
        *palette,
        *(profile.get("material_texture") or []),
        *(profile.get("environmental_motifs") or []),
        profile.get("era_style") or "",
        profile.get("atmosphere") or "",
    ]
    context_text = " ".join(str(value).lower() for value in context_values)
    if any(token in context_text for token in ("snow", "ice", "雪", "冰", "冻土")):
        return (210, 222, 218)
    if any(token in context_text for token in ("green", "grass", "绿", "草", "柳", "竹", "花木", "园林", "植被")):
        return (112, 137, 91)
    if any(token in context_text for token in ("sand", "earth", "沙", "土", "米黄", "淡金", "荒漠")):
        return (196, 176, 126)
    if any(token in context_text for token in ("gray", "grey", "灰", "stone", "石", "城市", "混凝土")):
        return (174, 181, 174)
    return (112, 137, 91)


def _blend_color(
    source: tuple[int, int, int],
    target: tuple[int, int, int],
    amount: float,
) -> tuple[int, int, int]:
    return tuple(round(start + (end - start) * amount) for start, end in zip(source, target))


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ):
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _draw_centered_label(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    text: str,
    font: ImageFont.ImageFont,
) -> None:
    x0, y0, x1, y1 = bounds
    max_width = max(8, x1 - x0 - 8)
    label = text
    while len(label) > 2 and draw.textbbox((0, 0), label, font=font)[2] > max_width:
        label = label[:-2] + "…"
    text_box = draw.textbbox((0, 0), label, font=font)
    x = x0 + (x1 - x0 - (text_box[2] - text_box[0])) / 2
    y = y0 + (y1 - y0 - (text_box[3] - text_box[1])) / 2
    draw.text((x, y), label, font=font, fill=(245, 247, 252, 255))


def _clamp_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return max(0, x0), max(0, y0), min(width - 1, x1), min(height - 1, y1)


def _stable_seed(value: str) -> int:
    result = 2166136261
    for char in value:
        result = ((result ^ ord(char)) * 16777619) & 0xFFFFFFFF
    return result
