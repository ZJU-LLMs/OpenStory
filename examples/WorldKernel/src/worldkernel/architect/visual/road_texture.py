from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageStat

from worldkernel.architect.spatial.models import SpatialBlueprint
from worldkernel.architect.visual.client import ImageGenerationClient
from worldkernel.architect.visual.models import VisualLayoutManifest
from worldkernel.llm.config_loader import load_model_config_by_capability


ROAD_ATLAS_SIZE = (1024, 1024)
GENERATION_STRATEGY = "single_world_road_atlas_v1"


def generate_road_texture_assets(
    *,
    blueprint: SpatialBlueprint,
    manifest: VisualLayoutManifest,
    world_background: dict[str, Any],
    root: str | Path,
    model_config_path: str | Path,
) -> dict[str, Any]:
    root_path = Path(root)
    atlas_path = root_path / "road_atlas.png"
    layer_path = root_path / "road_layer.png"
    prompt_path = root_path / "road_prompt.json"
    metadata_path = root_path / "road_metadata.json"
    canvas_size = (
        int(manifest.canvas.get("width_px") or 0),
        int(manifest.canvas.get("height_px") or 0),
    )
    if min(canvas_size) <= 0:
        raise ValueError(f"Invalid road canvas size: {canvas_size}")

    road_tiles = {(int(point.x), int(point.y)) for point in blueprint.road_tiles}
    if not road_tiles:
        prompt_payload = compose_road_texture_prompt(world_background, manifest.visual_profile)
        prompt_payload.update(
            {
                "generation_strategy": "empty_road_layer",
                "atlas_size": {
                    "width": ROAD_ATLAS_SIZE[0],
                    "height": ROAD_ATLAS_SIZE[1],
                },
                "road_geometry_source": "spatial_blueprint.road_tiles",
            }
        )
        _write_json(prompt_path, prompt_payload)
        Image.new("RGB", ROAD_ATLAS_SIZE, (0, 0, 0)).save(atlas_path, format="PNG")
        Image.new("RGBA", canvas_size, (0, 0, 0, 0)).save(layer_path, format="PNG")
        _set_route_asset(
            manifest,
            atlas_path=atlas_path,
            layer_path=layer_path,
            prompt_path=prompt_path,
            metadata_path=metadata_path,
            provider="deterministic",
            model="none",
        )
        metadata = {
            "status": "ready",
            "generation_strategy": "empty_road_layer",
            "road_tile_count": 0,
            "road_pixels": 0,
            "asset_version": manifest.route_layer.asset_version,
        }
        _write_json(metadata_path, metadata)
        return metadata

    cfg = load_model_config_by_capability(model_config_path, "image_generation")
    client = ImageGenerationClient(cfg)
    reference = compose_map_reference(root_path, manifest, canvas_size)
    prompt_payload = compose_road_texture_prompt(world_background, manifest.visual_profile)
    prompt_payload.update(
        {
            "generation_strategy": GENERATION_STRATEGY,
            "atlas_size": {"width": ROAD_ATLAS_SIZE[0], "height": ROAD_ATLAS_SIZE[1]},
            "source": "background.png + location_layer.png",
            "road_geometry_source": "spatial_blueprint.road_tiles",
        }
    )
    _write_json(prompt_path, prompt_payload)

    with _temporary_road_edit_paths(root_path) as (input_path, mask_path):
        _make_style_reference(reference, blueprint, ROAD_ATLAS_SIZE).save(input_path, format="PNG")
        Image.new("RGBA", ROAD_ATLAS_SIZE, (255, 255, 255, 0)).save(mask_path, format="PNG")
        model_metadata = client.generate(
            prompt_payload["prompt"],
            atlas_path,
            size=f"{ROAD_ATLAS_SIZE[0]}x{ROAD_ATLAS_SIZE[1]}",
            input_image_path=input_path,
            mask_path=mask_path,
        )

    _validate_image_size(atlas_path, ROAD_ATLAS_SIZE, "Road atlas")
    layer_metadata = build_road_layer(
        atlas_path=atlas_path,
        output_path=layer_path,
        blueprint=blueprint,
        canvas_size=canvas_size,
    )
    _set_route_asset(
        manifest,
        atlas_path=atlas_path,
        layer_path=layer_path,
        prompt_path=prompt_path,
        metadata_path=metadata_path,
        provider=str(cfg.get("name") or ""),
        model=str(cfg.get("model") or ""),
    )
    metadata = {
        "status": "ready",
        "generation_strategy": GENERATION_STRATEGY,
        "atlas_size": {"width": ROAD_ATLAS_SIZE[0], "height": ROAD_ATLAS_SIZE[1]},
        "canvas_size": {"width": canvas_size[0], "height": canvas_size[1]},
        "road_tile_count": len(road_tiles),
        "asset_version": manifest.route_layer.asset_version,
        "layer": layer_metadata,
        "model": {key: value for key, value in model_metadata.items() if key != "raw_result"},
    }
    _write_json(metadata_path, metadata)
    return metadata


def hydrate_existing_road_texture(
    manifest: VisualLayoutManifest,
    root: str | Path,
) -> dict[str, Any]:
    root_path = Path(root)
    atlas_path = root_path / "road_atlas.png"
    layer_path = root_path / "road_layer.png"
    prompt_path = root_path / "road_prompt.json"
    metadata_path = root_path / "road_metadata.json"
    metadata = _read_json(metadata_path)
    canvas_size = (
        int(manifest.canvas.get("width_px") or 0),
        int(manifest.canvas.get("height_px") or 0),
    )
    if (
        metadata.get("status") != "ready"
        or not atlas_path.is_file()
        or not _image_has_size(layer_path, canvas_size)
    ):
        return {"status": "missing"}
    _set_route_asset(
        manifest,
        atlas_path=atlas_path,
        layer_path=layer_path,
        prompt_path=prompt_path,
        metadata_path=metadata_path,
        provider=str((metadata.get("model") or {}).get("provider") or ""),
        model=str((metadata.get("model") or {}).get("model") or ""),
    )
    return {
        "status": "ready",
        "generation_strategy": metadata.get("generation_strategy", "existing_road_texture"),
        "asset_version": manifest.route_layer.asset_version,
    }


def compose_road_texture_prompt(
    world_background: dict[str, Any],
    visual_profile: dict[str, Any],
) -> dict[str, str]:
    world_parts = [
        world_background.get("world_name"),
        world_background.get("world_origin_summary"),
        world_background.get("primary"),
        world_background.get("secondary"),
    ]
    profile_parts = [
        visual_profile.get("art_style"),
        visual_profile.get("era_style"),
        _join(visual_profile.get("color_palette")),
        _join(visual_profile.get("material_texture")),
        visual_profile.get("lighting_weather"),
        visual_profile.get("atmosphere"),
    ]
    prompt = "\n".join(
        [
            "请把输入地图仅作为画风参考，生成一张该世界统一使用的可平铺道路地表材质底图。",
            "输出必须从左到右、从上到下只表现同一种连续材质；这不是素材图集、样张合集、九宫格或分格贴图。",
            "整张输出只表现连续、无方向性的道路表面材质，不要绘制道路路线、转角、交叉口或地图布局。",
            "采用严格正交俯视的明亮卡通像素游戏风格，使用较大的像素色块、有限色阶、低纹理密度和清晰硬边。",
            "道路材质必须符合世界时代与环境，例如未来世界可使用金属步道或能量导轨，古代世界可使用石板或夯土，现代世界可使用沥青或铺装地面。",
            "保持照明均匀，不要出现单独的中心主体；图像上下边缘与左右边缘应能自然衔接。",
            "不要生成建筑、房间、人物、车辆、道具、路牌、文字、标志、UI、水印或透视场景。",
            f"世界设定：{'；'.join(str(item) for item in world_parts if str(item or '').strip())}",
            f"视觉规范：{'；'.join(str(item) for item in profile_parts if str(item or '').strip())}",
        ]
    )
    return {"prompt": prompt}


def compose_map_reference(
    root: Path,
    manifest: VisualLayoutManifest,
    canvas_size: tuple[int, int],
) -> Image.Image:
    background_path = root / "background.png"
    if not background_path.is_file():
        raise RuntimeError("Road texture generation requires background.png")
    with Image.open(background_path) as background_image:
        image = background_image.convert("RGB")
    if image.size != canvas_size:
        raise ValueError(
            f"Road style reference size {image.size} does not match canvas {canvas_size}"
        )
    location_layer = manifest.location_layer
    if location_layer.status in {"ready", "partial"} and location_layer.url:
        layer_path = Path(location_layer.path) if location_layer.path else root / location_layer.url
        if not layer_path.is_file():
            layer_path = root / location_layer.url
        if layer_path.is_file():
            with Image.open(layer_path) as layer_image:
                rendered_layer = layer_image.convert("RGBA")
            if rendered_layer.size != canvas_size:
                raise ValueError(
                    f"Location layer size {rendered_layer.size} does not match {canvas_size}"
                )
            return Image.alpha_composite(image.convert("RGBA"), rendered_layer).convert("RGB")

    return image


def build_road_layer(
    *,
    atlas_path: str | Path,
    output_path: str | Path,
    blueprint: SpatialBlueprint,
    canvas_size: tuple[int, int],
) -> dict[str, Any]:
    with Image.open(atlas_path) as atlas_image:
        atlas = atlas_image.convert("RGB")
    texture = _mirror_tile(atlas, canvas_size)
    tile_size = int(blueprint.grid.tile_size)
    road_tiles = {(int(point.x), int(point.y)) for point in blueprint.road_tiles}
    for x, y in road_tiles:
        if x < 0 or y < 0 or x >= blueprint.grid.width or y >= blueprint.grid.height:
            raise ValueError(f"Road tile {(x, y)} is outside the map grid")
    location_tiles = _location_tiles(blueprint)
    hidden_road_tiles = road_tiles.intersection(location_tiles)
    visible_road_tiles = road_tiles.difference(location_tiles)
    mask = Image.new("L", canvas_size, 0)
    mask_draw = ImageDraw.Draw(mask)
    for x, y in visible_road_tiles:
        x0, y0 = x * tile_size, y * tile_size
        mask_draw.rectangle(
            (x0, y0, x0 + tile_size - 1, y0 + tile_size - 1),
            fill=255,
        )

    layer = texture.convert("RGBA")
    layer.putalpha(mask)
    mean = ImageStat.Stat(atlas).mean[:3]
    edge_color = tuple(max(0, min(255, round(channel * 0.55))) for channel in mean) + (255,)
    edge_width = max(1, tile_size // 8)
    draw = ImageDraw.Draw(layer)
    for x, y in visible_road_tiles:
        x0, y0 = x * tile_size, y * tile_size
        x1, y1 = x0 + tile_size - 1, y0 + tile_size - 1
        if (x - 1, y) not in visible_road_tiles:
            draw.rectangle((x0, y0, x0 + edge_width - 1, y1), fill=edge_color)
        if (x + 1, y) not in visible_road_tiles:
            draw.rectangle((x1 - edge_width + 1, y0, x1, y1), fill=edge_color)
        if (x, y - 1) not in visible_road_tiles:
            draw.rectangle((x0, y0, x1, y0 + edge_width - 1), fill=edge_color)
        if (x, y + 1) not in visible_road_tiles:
            draw.rectangle((x0, y1 - edge_width + 1, x1, y1), fill=edge_color)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    layer.save(output, format="PNG")
    alpha = layer.getchannel("A")
    road_pixels = alpha.histogram()[255]
    expected_pixels = len(visible_road_tiles) * tile_size * tile_size
    if road_pixels != expected_pixels:
        raise RuntimeError(
            f"Road layer alpha coverage mismatch: expected {expected_pixels}, got {road_pixels}"
        )
    missing_connections = _missing_boundary_connections(blueprint, visible_road_tiles)
    if missing_connections:
        raise RuntimeError(
            "Road layer does not reach one or more location entrances: "
            + ", ".join(missing_connections)
        )
    return {
        "road_pixels": road_pixels,
        "expected_road_pixels": expected_pixels,
        "source_road_tile_count": len(road_tiles),
        "visible_road_tile_count": len(visible_road_tiles),
        "location_clipped_road_tile_count": len(hidden_road_tiles),
        "transparent_pixels": canvas_size[0] * canvas_size[1] - road_pixels,
        "entrance_connections": len(blueprint.regions),
        "mirrored_tiling": True,
        "resized": False,
    }


def _location_tiles(blueprint: SpatialBlueprint) -> set[tuple[int, int]]:
    occupied: set[tuple[int, int]] = set()
    for region in blueprint.regions:
        bounds = region.bounds or {}
        x0 = int(bounds.get("x", 0))
        y0 = int(bounds.get("y", 0))
        width = max(0, int(bounds.get("w", 0)))
        height = max(0, int(bounds.get("h", 0)))
        for y in range(y0, y0 + height):
            for x in range(x0, x0 + width):
                occupied.add((x, y))
    return occupied


def _make_style_reference(
    image: Image.Image,
    blueprint: SpatialBlueprint,
    size: tuple[int, int],
) -> Image.Image:
    road_tiles = [(int(point.x), int(point.y)) for point in blueprint.road_tiles]
    tile_size = int(blueprint.grid.tile_size)
    if road_tiles:
        center_x = round(sum(x for x, _ in road_tiles) / len(road_tiles) * tile_size)
        center_y = round(sum(y for _, y in road_tiles) / len(road_tiles) * tile_size)
    else:
        center_x, center_y = image.width // 2, image.height // 2
    crop_x = max(0, min(max(0, image.width - size[0]), center_x - size[0] // 2))
    crop_y = max(0, min(max(0, image.height - size[1]), center_y - size[1] // 2))
    crop = image.crop(
        (
            crop_x,
            crop_y,
            min(image.width, crop_x + size[0]),
            min(image.height, crop_y + size[1]),
        )
    )
    if crop.size == size:
        return crop
    output = Image.new("RGB", size, crop.getpixel((0, 0)))
    output.paste(crop, ((size[0] - crop.width) // 2, (size[1] - crop.height) // 2))
    return output


def _mirror_tile(atlas: Image.Image, canvas_size: tuple[int, int]) -> Image.Image:
    output = Image.new("RGB", canvas_size)
    for row, y in enumerate(range(0, canvas_size[1], atlas.height)):
        for column, x in enumerate(range(0, canvas_size[0], atlas.width)):
            tile = atlas
            if column % 2:
                tile = tile.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if row % 2:
                tile = tile.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            width = min(tile.width, canvas_size[0] - x)
            height = min(tile.height, canvas_size[1] - y)
            output.paste(tile.crop((0, 0, width, height)), (x, y))
    return output


def _missing_boundary_connections(
    blueprint: SpatialBlueprint,
    road_tiles: set[tuple[int, int]],
) -> list[str]:
    missing: list[str] = []
    for region in blueprint.regions:
        bounds = region.bounds or {}
        x0 = int(bounds.get("x", 0))
        y0 = int(bounds.get("y", 0))
        width = max(0, int(bounds.get("w", 0)))
        height = max(0, int(bounds.get("h", 0)))
        x1 = x0 + width - 1
        y1 = y0 + height - 1
        outside_boundary = {(x, y0 - 1) for x in range(x0, x1 + 1)}
        outside_boundary.update((x, y1 + 1) for x in range(x0, x1 + 1))
        outside_boundary.update((x0 - 1, y) for y in range(y0, y1 + 1))
        outside_boundary.update((x1 + 1, y) for y in range(y0, y1 + 1))
        if not outside_boundary.intersection(road_tiles):
            missing.append(region.location_id)
    return missing


def _set_route_asset(
    manifest: VisualLayoutManifest,
    *,
    atlas_path: Path,
    layer_path: Path,
    prompt_path: Path,
    metadata_path: Path,
    provider: str,
    model: str,
) -> None:
    route = manifest.route_layer
    route.status = "ready"
    route.path = str(layer_path)
    route.url = "road_layer.png"
    route.width_px = int(manifest.canvas.get("width_px") or 0)
    route.height_px = int(manifest.canvas.get("height_px") or 0)
    route.atlas_path = str(atlas_path)
    route.prompt_path = str(prompt_path)
    route.metadata_path = str(metadata_path)
    route.provider = provider
    route.model = model
    route.asset_version = _asset_version(layer_path)
    route.error = ""


@contextmanager
def _temporary_road_edit_paths(root: Path):
    token = uuid.uuid4().hex
    paths = (
        root / f".road-atlas-{token}.input.png",
        root / f".road-atlas-{token}.mask.png",
    )
    try:
        yield paths
    finally:
        for path in paths:
            path.unlink(missing_ok=True)


def _join(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value if str(item or "").strip())
    return str(value or "")


def _asset_version(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _validate_image_size(path: Path, expected: tuple[int, int], label: str) -> None:
    with Image.open(path) as image:
        actual = image.size
    if actual != expected:
        raise ValueError(f"{label} size {actual} does not match {expected}")


def _image_has_size(path: Path, expected: tuple[int, int]) -> bool:
    try:
        with Image.open(path) as image:
            return image.size == expected
    except (FileNotFoundError, OSError):
        return False


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
