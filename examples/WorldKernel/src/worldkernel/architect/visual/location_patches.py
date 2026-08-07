from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw

from worldkernel.architect.spatial.models import SpatialBlueprint
from worldkernel.architect.visual.client import ImageGenerationClient
from worldkernel.architect.visual.control import clean_road_reserved_pixels
from worldkernel.architect.visual.location_prompt import compose_location_patch_prompt
from worldkernel.architect.visual.models import VisualLayoutManifest, VisualPatchAsset, VisualSlot
from worldkernel.llm.config_loader import load_model_config_by_capability


GENERATION_STRATEGY = "local_context_road_free_full_patch_v4"


def generate_location_patches(
    *,
    blueprint: SpatialBlueprint,
    manifest: VisualLayoutManifest,
    world_background: dict[str, Any],
    semantic_locations: list[Any],
    root: str | Path,
    model_config_path: str | Path,
    background_reference_path: str | Path,
    progress_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    patch_root = root_path / "location_patches"
    prompt_root = root_path / "location_patch_prompts"
    metadata_root = root_path / "location_patch_metadata"
    patch_root.mkdir(parents=True, exist_ok=True)
    prompt_root.mkdir(parents=True, exist_ok=True)
    metadata_root.mkdir(parents=True, exist_ok=True)

    reference_path = Path(background_reference_path)
    if not reference_path.is_file():
        raise RuntimeError(f"Location patch context source does not exist: {reference_path}")
    with Image.open(reference_path) as reference_image:
        background = reference_image.convert("RGB")
    expected_background_size = (
        int(manifest.canvas.get("width_px") or 0),
        int(manifest.canvas.get("height_px") or 0),
    )
    if background.size != expected_background_size:
        raise ValueError(
            f"Location patch context source size {background.size} does not match "
            f"visual canvas {expected_background_size}"
        )
    road_reference_pixels_cleaned = clean_road_reserved_pixels(
        background,
        blueprint,
        int(blueprint.grid.tile_size),
    )

    cfg = load_model_config_by_capability(model_config_path, "image_generation")
    context_size, request_size, request_scale = _location_edit_config(cfg)
    client = ImageGenerationClient(cfg)
    location_index = _index_locations(semantic_locations)
    region_index = {region.location_id: region for region in blueprint.regions}
    patches: list[VisualPatchAsset] = []
    failures: list[dict[str, str]] = []
    progress_path = Path(progress_manifest_path) if progress_manifest_path else None
    for index, slot in enumerate(manifest.slots):
        region = region_index.get(slot.location_id)
        location = _lookup_location(location_index, slot, region)
        filename = _patch_filename(slot.location_id, index)
        output_path = patch_root / filename
        prompt_path = prompt_root / f"{output_path.stem}.json"
        metadata_path = metadata_root / f"{output_path.stem}.json"
        bounds = slot.bounds_px
        logical_size = (int(bounds.get("w") or 0), int(bounds.get("h") or 0))
        target_size = (context_size, context_size)
        patch = VisualPatchAsset(
            location_id=slot.location_id,
            path=str(output_path),
            url=f"location_patches/{filename}",
            status="pending",
            bounds_px=dict(bounds),
            logical_bounds_px=dict(bounds),
            prompt_path=str(prompt_path),
            metadata_path=str(metadata_path),
            provider=str(cfg.get("name") or ""),
            model=str(cfg.get("model") or ""),
            z_index=slot.z_index,
        )

        try:
            if logical_size[0] <= 0 or logical_size[1] <= 0:
                raise ValueError(f"Invalid logical location size: {logical_size}")
            context = _prepare_location_context(
                background=background,
                slot=slot,
                context_size=context_size,
                tile_size=int(blueprint.grid.tile_size),
            )
            patch.bounds_px = dict(context["crop_box"])
            prompt_payload = compose_location_patch_prompt(
                world_background=world_background,
                visual_profile=manifest.visual_profile,
                location=location,
                slot=slot,
                generation_size=request_size,
            )
            prompt_record = {
                **prompt_payload,
                "generation_strategy": GENERATION_STRATEGY,
                "context_source": str(reference_path),
                "context_crop_px": context["crop_box"],
                "slot_in_context_px": context["slot_box"],
                "request_size": {"width": request_size[0], "height": request_size[1]},
                "request_scale": request_scale,
                "mask_semantics": "transparent_pixels_editable_opaque_pixels_preserved",
                "postprocess": "integer_nearest_downscale_keep_full_local_context",
                "road_free_context": True,
                "entrance_guidance": "coordinate_only",
                "road_reference_pixels_cleaned": road_reference_pixels_cleaned,
            }
            _write_json(prompt_path, prompt_record)

            existing_metadata = _read_json(metadata_path)
            if _existing_patch_is_usable(
                output_path,
                target_size,
                metadata=existing_metadata,
                required_strategy=GENERATION_STRATEGY,
            ):
                patch.status = "ready"
                patch.asset_version = str(
                    existing_metadata.get("asset_version") or _asset_version(output_path)
                )
                existing_metadata["reused_existing_patch"] = True
                existing_metadata["context_source"] = str(reference_path)
                existing_metadata["asset_version"] = patch.asset_version
                existing_metadata["road_free_context"] = True
                existing_metadata["entrance_guidance"] = "coordinate_only"
                existing_metadata["road_reference_pixels_cleaned"] = (
                    road_reference_pixels_cleaned
                )
                _write_json(metadata_path, existing_metadata)
                _paste_context_patch(background, output_path, context["crop_box"])
                patches.append(patch)
                _write_progress_manifest(manifest, patches, progress_path)
                continue

            with _temporary_edit_paths(root_path, output_path.stem) as temporary_paths:
                input_path, mask_path, generated_path = temporary_paths
                context["image"].resize(request_size, Image.Resampling.NEAREST).save(
                    input_path, format="PNG"
                )
                context["mask"].resize(request_size, Image.Resampling.NEAREST).save(
                    mask_path, format="PNG"
                )

                model_metadata = client.generate(
                    prompt_payload["prompt"],
                    generated_path,
                    negative_prompt=prompt_payload.get("negative_prompt", ""),
                    size=f"{request_size[0]}x{request_size[1]}",
                    input_image_path=input_path,
                    mask_path=mask_path,
                )
                _validate_image_size(generated_path, request_size, "Location edit result")
                protected_validation = _validate_protected_context(
                    input_path,
                    generated_path,
                    mask_path,
                )
                _save_full_context_patch(
                    generated_path=generated_path,
                    output_path=output_path,
                    native_context_size=(context_size, context_size),
                )

            _validate_image_size(output_path, target_size, "Location patch")
            _paste_context_patch(background, output_path, context["crop_box"])
            patch.status = "ready"
            patch.asset_version = _asset_version(output_path)
            _write_json(
                metadata_path,
                {
                    "status": "ready",
                    "generation_strategy": GENERATION_STRATEGY,
                    "location_id": slot.location_id,
                    "logical_bounds_px": dict(bounds),
                    "render_bounds_px": dict(context["crop_box"]),
                    "asset_version": patch.asset_version,
                    "target_size": {"width": target_size[0], "height": target_size[1]},
                    "request_size": {"width": request_size[0], "height": request_size[1]},
                    "request_scale": request_scale,
                    "native_context_size": {"width": context_size, "height": context_size},
                    "context_crop_px": context["crop_box"],
                    "slot_in_context_px": context["slot_box"],
                    "entrance_port": dict(slot.entrance_port),
                    "road_free_context": True,
                    "entrance_guidance": "coordinate_only",
                    "road_reference_pixels_cleaned": road_reference_pixels_cleaned,
                    "protected_context_validation": protected_validation,
                    "final_extracted_size": {"width": target_size[0], "height": target_size[1]},
                    "postprocess": "integer_nearest_downscale_keep_full_local_context",
                    "final_background_protection": "full generated road-free local context retained",
                    "model": {
                        key: value for key, value in model_metadata.items() if key != "raw_result"
                    },
                    "context_source": str(reference_path),
                },
            )
        except Exception as exc:
            patch.status = "failed"
            patch.error = str(exc)
            failures.append({"location_id": slot.location_id, "error": patch.error})
            _write_json(
                metadata_path,
                {
                    "status": "failed",
                    "generation_strategy": GENERATION_STRATEGY,
                    "location_id": slot.location_id,
                    "error": patch.error,
                    "logical_bounds_px": dict(bounds),
                    "target_size": {"width": target_size[0], "height": target_size[1]},
                    "request_size": {"width": request_size[0], "height": request_size[1]},
                    "request_scale": request_scale,
                    "entrance_port": dict(slot.entrance_port),
                    "road_free_context": True,
                    "entrance_guidance": "coordinate_only",
                    "road_reference_pixels_cleaned": road_reference_pixels_cleaned,
                    "context_source": str(reference_path),
                },
            )
        patches.append(patch)
        _write_progress_manifest(manifest, patches, progress_path)

    manifest.location_patches = patches
    ready_count = sum(1 for patch in patches if patch.status == "ready")
    return {
        "status": "ready" if ready_count == len(patches) else "partial",
        "generation_strategy": GENERATION_STRATEGY,
        "patch_count": len(patches),
        "ready_patch_count": ready_count,
        "failed_patch_count": len(patches) - ready_count,
        "failures": failures,
        "context_source": str(reference_path),
        "request_size": {"width": request_size[0], "height": request_size[1]},
        "native_context_size": {"width": context_size, "height": context_size},
        "request_scale": request_scale,
        "road_free_context": True,
        "entrance_guidance": "coordinate_only",
        "road_reference_pixels_cleaned": road_reference_pixels_cleaned,
        "output_dir": str(patch_root),
    }


def hydrate_existing_location_patches(
    manifest: VisualLayoutManifest,
    root: str | Path,
) -> dict[str, Any]:
    """Attach already-generated full local-context patch files to a manifest."""
    root_path = Path(root)
    patch_root = root_path / "location_patches"
    prompt_root = root_path / "location_patch_prompts"
    metadata_root = root_path / "location_patch_metadata"
    hydrated: list[VisualPatchAsset] = []
    for index, slot in enumerate(manifest.slots):
        filename = _patch_filename(slot.location_id, index)
        output_path = patch_root / filename
        metadata_path = metadata_root / f"{output_path.stem}.json"
        metadata = _read_json(metadata_path)
        render_bounds = metadata.get("render_bounds_px")
        if not isinstance(render_bounds, dict) or not render_bounds:
            continue
        target_size = (
            int(render_bounds.get("w") or 0),
            int(render_bounds.get("h") or 0),
        )
        if not _existing_patch_is_usable(
            output_path,
            target_size,
            metadata=metadata,
            required_strategy=GENERATION_STRATEGY,
        ):
            continue
        hydrated.append(
            VisualPatchAsset(
                location_id=slot.location_id,
                path=str(output_path),
                url=f"location_patches/{filename}",
                status="ready",
                bounds_px=dict(render_bounds),
                logical_bounds_px=dict(slot.bounds_px),
                prompt_path=str(prompt_root / f"{output_path.stem}.json"),
                metadata_path=str(metadata_path),
                provider=str(metadata.get("model", {}).get("provider") or ""),
                model=str(metadata.get("model", {}).get("model") or ""),
                asset_version=str(
                    metadata.get("asset_version") or _asset_version(output_path)
                ),
                z_index=slot.z_index,
            )
        )

    manifest.location_patches = hydrated
    ready_count = sum(1 for patch in hydrated if patch.status == "ready")
    return {
        "status": "ready" if ready_count == len(manifest.slots) else "partial",
        "patch_count": len(hydrated),
        "ready_patch_count": ready_count,
        "missing_patch_count": max(0, len(manifest.slots) - ready_count),
        "output_dir": str(patch_root),
    }


def _location_edit_config(cfg: dict[str, Any]) -> tuple[int, tuple[int, int], int]:
    context_size = int(cfg.get("location_patch_context_size") or 512)
    request_scale = int(cfg.get("location_patch_request_scale") or 2)
    request_size = _parse_size(str(cfg.get("location_patch_request_size") or "1024x1024"))
    if context_size <= 0 or request_scale <= 0:
        raise ValueError("Location patch context size and request scale must be positive")
    expected = (context_size * request_scale, context_size * request_scale)
    if request_size != expected:
        raise ValueError(
            f"Location patch request size {request_size} must equal the native "
            f"context {context_size} multiplied by the integer scale {request_scale}: {expected}"
        )
    return context_size, request_size, request_scale


@contextmanager
def _temporary_edit_paths(root: Path, stem: str):
    token = uuid.uuid4().hex
    paths = (
        root / f".{stem}.{token}.edit-base.png",
        root / f".{stem}.{token}.edit-mask.png",
        root / f".{stem}.{token}.edit-result.png",
    )
    try:
        yield paths
    finally:
        for path in paths:
            path.unlink(missing_ok=True)


def _prepare_location_context(
    *,
    background: Image.Image,
    slot: VisualSlot,
    context_size: int,
    tile_size: int,
) -> dict[str, Any]:
    bounds = slot.bounds_px
    slot_x = int(bounds.get("x") or 0)
    slot_y = int(bounds.get("y") or 0)
    slot_w = int(bounds.get("w") or 0)
    slot_h = int(bounds.get("h") or 0)
    if slot_w > context_size or slot_h > context_size:
        raise ValueError(
            f"Location slot {(slot_w, slot_h)} does not fit the {context_size}x{context_size} "
            "native context window"
        )

    crop_x = _context_axis_origin(slot_x + slot_w / 2, background.width, context_size)
    crop_y = _context_axis_origin(slot_y + slot_h / 2, background.height, context_size)
    context_image = _edge_padded_crop(background, crop_x, crop_y, context_size)
    left = slot_x - crop_x
    top = slot_y - crop_y
    slot_box = (left, top, left + slot_w, top + slot_h)
    if min(slot_box) < 0 or slot_box[2] > context_size or slot_box[3] > context_size:
        raise ValueError(f"Location slot is outside its local context: {slot_box}")
    neutral_color = _sample_surrounding_color(
        background,
        (slot_x, slot_y, slot_x + slot_w, slot_y + slot_h),
        ring=max(1, tile_size),
    )
    draw = ImageDraw.Draw(context_image)
    draw.rectangle((slot_box[0], slot_box[1], slot_box[2] - 1, slot_box[3] - 1), fill=neutral_color)

    mask = Image.new("RGBA", (context_size, context_size), (255, 255, 255, 255))
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rectangle(
        (slot_box[0], slot_box[1], slot_box[2] - 1, slot_box[3] - 1),
        fill=(255, 255, 255, 0),
    )
    return {
        "image": context_image,
        "mask": mask,
        "crop_box": {"x": crop_x, "y": crop_y, "w": context_size, "h": context_size},
        "slot_box": {"x": left, "y": top, "w": slot_w, "h": slot_h},
        "slot_box_tuple": slot_box,
    }


def _context_axis_origin(center: float, canvas_size: int, context_size: int) -> int:
    if canvas_size >= context_size:
        return max(0, min(canvas_size - context_size, round(center - context_size / 2)))
    return (canvas_size - context_size) // 2


def _edge_padded_crop(image: Image.Image, x: int, y: int, size: int) -> Image.Image:
    source_x0 = max(0, x)
    source_y0 = max(0, y)
    source_x1 = min(image.width, x + size)
    source_y1 = min(image.height, y + size)
    crop = image.crop((source_x0, source_y0, source_x1, source_y1)).convert("RGB")
    left = source_x0 - x
    top = source_y0 - y
    right = size - left - crop.width
    bottom = size - top - crop.height
    if not any((left, top, right, bottom)):
        return crop

    output = Image.new("RGB", (size, size))
    output.paste(crop, (left, top))
    if top:
        output.paste(crop.crop((0, 0, crop.width, 1)).resize((crop.width, top)), (left, 0))
    if bottom:
        output.paste(
            crop.crop((0, crop.height - 1, crop.width, crop.height)).resize((crop.width, bottom)),
            (left, top + crop.height),
        )
    if left:
        output.paste(crop.crop((0, 0, 1, crop.height)).resize((left, crop.height)), (0, top))
    if right:
        output.paste(
            crop.crop((crop.width - 1, 0, crop.width, crop.height)).resize((right, crop.height)),
            (left + crop.width, top),
        )
    corner_colors = {
        (0, 0, left, top): crop.getpixel((0, 0)),
        (left + crop.width, 0, right, top): crop.getpixel((crop.width - 1, 0)),
        (0, top + crop.height, left, bottom): crop.getpixel((0, crop.height - 1)),
        (left + crop.width, top + crop.height, right, bottom): crop.getpixel(
            (crop.width - 1, crop.height - 1)
        ),
    }
    corner_draw = ImageDraw.Draw(output)
    for (corner_x, corner_y, width, height), color in corner_colors.items():
        if width and height:
            corner_draw.rectangle(
                (corner_x, corner_y, corner_x + width - 1, corner_y + height - 1),
                fill=color,
            )
    return output


def _sample_surrounding_color(
    image: Image.Image,
    box: tuple[int, int, int, int],
    *,
    ring: int,
) -> tuple[int, int, int]:
    x0, y0, x1, y1 = box
    samples: list[tuple[int, int, int]] = []
    strips = [
        (max(0, x0 - ring), max(0, y0 - ring), min(image.width, x1 + ring), max(0, y0)),
        (max(0, x0 - ring), min(image.height, y1), min(image.width, x1 + ring), min(image.height, y1 + ring)),
        (max(0, x0 - ring), max(0, y0), max(0, x0), min(image.height, y1)),
        (min(image.width, x1), max(0, y0), min(image.width, x1 + ring), min(image.height, y1)),
    ]
    for strip in strips:
        if strip[2] > strip[0] and strip[3] > strip[1]:
            cropped = image.crop(strip)
            pixels = (
                cropped.get_flattened_data()
                if hasattr(cropped, "get_flattened_data")
                else cropped.getdata()
            )
            samples.extend(pixels)
    if not samples:
        return (72, 76, 84)
    quantized = [tuple(min(255, (channel // 16) * 16) for channel in pixel) for pixel in samples]
    return Counter(quantized).most_common(1)[0][0]


def _validate_protected_context(
    input_path: Path,
    generated_path: Path,
    mask_path: Path,
) -> dict[str, Any]:
    with Image.open(input_path) as source_image:
        source = source_image.convert("RGB")
    with Image.open(generated_path) as generated_image:
        generated = generated_image.convert("RGB")
    with Image.open(mask_path) as mask_image:
        protection = mask_image.convert("RGBA").getchannel("A")
    if source.size != generated.size or source.size != protection.size:
        raise ValueError("Location edit input, output, and mask sizes must match")

    difference = ImageChops.difference(source, generated)
    red, green, blue = difference.split()
    max_difference = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    protected_difference = ImageChops.multiply(max_difference, protection)
    changed = protected_difference.point(lambda value: 255 if value else 0)
    structural_change = protected_difference.point(lambda value: 255 if value > 32 else 0)
    changed_pixels = changed.histogram()[255]
    structural_changed_pixels = structural_change.histogram()[255]
    protected_pixels = protection.histogram()[255]
    changed_ratio = changed_pixels / protected_pixels if protected_pixels else 0.0
    structural_change_ratio = (
        structural_changed_pixels / protected_pixels if protected_pixels else 0.0
    )
    histogram = protected_difference.histogram()
    mean_max_channel_delta = (
        sum(value * count for value, count in enumerate(histogram)) / protected_pixels
        if protected_pixels
        else 0.0
    )
    within_guideline = mean_max_channel_delta <= 24.0 and structural_change_ratio <= 0.25
    return {
        "protected_pixels": protected_pixels,
        "changed_pixels": changed_pixels,
        "changed_ratio": changed_ratio,
        "structural_changed_pixels": structural_changed_pixels,
        "structural_change_ratio": structural_change_ratio,
        "mean_max_channel_delta": mean_max_channel_delta,
        "exact_preservation": changed_pixels == 0,
        "provider_mask_behavior": (
            "exact_alpha_preservation" if changed_pixels == 0 else "context_redraw"
        ),
        "within_guideline": within_guideline,
        "passed": True,
        "validation_mode": "diagnostic_only",
    }


def _save_full_context_patch(
    *,
    generated_path: Path,
    output_path: Path,
    native_context_size: tuple[int, int],
) -> None:
    with Image.open(generated_path) as generated_image:
        generated = generated_image.convert("RGB")
    if generated.size != native_context_size:
        generated = generated.resize(native_context_size, Image.Resampling.NEAREST)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated.save(output_path, format="PNG")


def _paste_context_patch(
    background: Image.Image,
    patch_path: Path,
    bounds: dict[str, int],
) -> None:
    with Image.open(patch_path) as patch_image:
        patch = patch_image.convert("RGB")
    expected = (int(bounds.get("w") or 0), int(bounds.get("h") or 0))
    if patch.size != expected:
        raise ValueError(
            f"Location context patch size {patch.size} does not match render bounds {expected}"
        )
    background.paste(patch, (int(bounds.get("x") or 0), int(bounds.get("y") or 0)))


def _index_locations(items: list[Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in items:
        location = _as_dict(item)
        identity = location.get("identity") if isinstance(location.get("identity"), dict) else {}
        keys = [
            location.get("id"),
            location.get("location_id"),
            location.get("name"),
            location.get("location_name"),
            identity.get("id"),
            identity.get("location_id"),
            identity.get("name"),
        ]
        for key in keys:
            if key is not None and str(key).strip():
                index[str(key)] = location
    return index


def _lookup_location(
    location_index: dict[str, dict[str, Any]],
    slot: VisualSlot,
    region: Any,
) -> dict[str, Any]:
    keys = [slot.location_id]
    if region is not None:
        keys.extend([getattr(region, "location_id", ""), getattr(region, "name", "")])
    for key in keys:
        found = location_index.get(str(key))
        if found:
            return found
    if region is not None:
        return {
            "id": getattr(region, "location_id", slot.location_id),
            "name": getattr(region, "name", slot.location_id),
            "tags": list(getattr(region, "tags", []) or []),
        }
    return {"id": slot.location_id, "name": slot.location_id}


def _patch_filename(location_id: str, index: int) -> str:
    digest = hashlib.sha1(location_id.encode("utf-8")).hexdigest()[:10]
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", location_id).strip("._-")
    slug = slug[:48] or "location"
    return f"{index + 1:03d}_{slug}_{digest}.png"


def _asset_version(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _parse_size(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*[xX*]\s*(\d+)\s*", value)
    if not match:
        raise ValueError(f"Invalid image size: {value}")
    return int(match.group(1)), int(match.group(2))


def _as_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    return {}


def _existing_patch_is_usable(
    path: Path,
    target_size: tuple[int, int],
    *,
    metadata: dict[str, Any] | None = None,
    required_strategy: str = "",
) -> bool:
    if required_strategy and (metadata or {}).get("generation_strategy") != required_strategy:
        return False
    try:
        with Image.open(path) as image:
            return image.size == target_size and image.width > 0 and image.height > 0
    except Exception:
        return False


def _validate_image_size(path: Path, expected: tuple[int, int], label: str) -> None:
    with Image.open(path) as image:
        actual = image.size
    if actual != expected:
        raise ValueError(f"{label} image size {actual} does not match target size {expected}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_progress_manifest(
    manifest: VisualLayoutManifest,
    patches: list[VisualPatchAsset],
    path: Path | None,
) -> None:
    if path is None:
        return
    manifest.location_patches = list(patches)
    _write_json(path, manifest.model_dump(mode="json"))
