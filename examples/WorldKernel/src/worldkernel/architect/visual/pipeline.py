from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from worldkernel.architect.spatial.models import SpatialBlueprint
from worldkernel.architect.visual.client import ImageGenerationClient
from worldkernel.architect.visual.control import (
    finalize_generated_background,
    render_layout_control_assets,
    validate_protected_regions,
)
from worldkernel.architect.visual.layout import build_visual_layout_manifest
from worldkernel.architect.visual.location_patches import (
    generate_location_patches as generate_location_patch_assets,
    hydrate_existing_location_patches,
)
from worldkernel.architect.visual.models import VisualLayoutManifest
from worldkernel.architect.visual.prompt import compose_background_prompt
from worldkernel.architect.visual.road_texture import (
    generate_road_texture_assets,
    hydrate_existing_road_texture,
)
from worldkernel.llm.config_loader import load_model_config_by_capability

logger = logging.getLogger(__name__)


def run_visual_pipeline(
    *,
    blueprint: SpatialBlueprint,
    world_background: dict[str, Any],
    output_root: str | Path,
    model_config_path: str | Path,
    generate_background: bool = False,
    generate_location_patches: bool = False,
    generate_road_texture: bool = False,
    semantic_locations: list[Any] | None = None,
) -> VisualLayoutManifest:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)

    manifest = build_visual_layout_manifest(
        blueprint=blueprint,
        world_background=world_background,
        output_root=root,
    )
    control_metadata = render_layout_control_assets(blueprint, manifest, root)
    manifest.background.control_image_path = control_metadata["control_image_path"]
    manifest.background.mask_path = control_metadata["mask_path"]
    manifest.background.edit_base_path = control_metadata["edit_base_path"]
    manifest.background.edit_mask_path = control_metadata["edit_mask_path"]
    prompt_payload = compose_background_prompt(world_background, manifest)

    prompt_path = root / "background_prompt.json"
    metadata_path = root / "background_metadata.json"
    manifest_path = root / "visual_layout_manifest.json"
    _write_json(prompt_path, prompt_payload)
    manifest.background.prompt_path = str(prompt_path)
    manifest.background.metadata_path = str(metadata_path)

    metadata_payload: dict[str, Any] = dict(control_metadata)
    if generate_background:
        try:
            generation_metadata = _generate_background(
                blueprint=blueprint,
                manifest=manifest,
                prompt_payload=prompt_payload,
                root=root,
                model_config_path=Path(model_config_path),
            )
            manifest.background.status = "ready"
            manifest.background.path = str(root / "background.png")
            manifest.background.url = "background.png"
            manifest.background.generation_strategy = generation_metadata["generation_strategy"]
            metadata_payload.update(generation_metadata)
        except Exception as exc:  # Stage2 remains usable with deterministic coordinate layers.
            logger.warning("Visual background generation skipped/failed: %s", exc)
            manifest.background.status = "failed"
            manifest.background.error = str(exc)
            metadata_payload.update({"status": "failed", "error": str(exc)})
    else:
        existing_background_path = root / "background.png"
        if existing_background_path.exists():
            existing_metadata = _read_json(metadata_path)
            existing_composite = existing_metadata.get("composite")
            if not isinstance(existing_composite, dict):
                existing_composite = {}
            existing_layers = existing_composite.get("composited_layers")
            if not isinstance(existing_layers, list):
                existing_layers = ["route_layer", "location_placeholder_layer"]
            manifest.background.status = "ready"
            manifest.background.path = str(existing_background_path)
            manifest.background.url = "background.png"
            manifest.background.generation_strategy = "existing_background_reuse"
            manifest.background.composited_layers = [str(layer) for layer in existing_layers]
            metadata_payload.update({
                "status": "ready",
                "image_generation": "reused_existing_background",
                "composite": existing_composite,
            })
        else:
            manifest.background.status = "prompt_ready"
            metadata_payload.update({
                "status": "prompt_ready",
                "image_generation": "disabled",
            })

    if generate_location_patches:
        _write_json(manifest_path, manifest.model_dump(mode="json"))
        try:
            background_reference_path = root / "background.png"
            if not background_reference_path.exists():
                raise RuntimeError(
                    "Location patch generation requires an existing background.png "
                    "or generate_background=true"
                )
            patch_metadata = generate_location_patch_assets(
                blueprint=blueprint,
                manifest=manifest,
                world_background=world_background,
                semantic_locations=semantic_locations or [],
                root=root,
                model_config_path=model_config_path,
                background_reference_path=background_reference_path,
                progress_manifest_path=manifest_path,
            )
            metadata_payload["location_patches"] = patch_metadata
            manifest.provenance["location_patch_generation"] = patch_metadata
        except Exception as patch_exc:
            logger.warning("Location patch generation skipped/failed: %s", patch_exc)
            metadata_payload["location_patches"] = {
                "status": "failed",
                "error": str(patch_exc),
            }
            manifest.provenance["location_patch_generation"] = metadata_payload["location_patches"]
            hydrated_metadata = hydrate_existing_location_patches(manifest, root)
            metadata_payload["existing_location_patches"] = hydrated_metadata
            manifest.provenance["existing_location_patches"] = hydrated_metadata
    else:
        hydrated_metadata = hydrate_existing_location_patches(manifest, root)
        if hydrated_metadata["ready_patch_count"] > 0:
            metadata_payload["existing_location_patches"] = hydrated_metadata
            manifest.provenance["existing_location_patches"] = hydrated_metadata

    if generate_road_texture:
        try:
            road_metadata = generate_road_texture_assets(
                blueprint=blueprint,
                manifest=manifest,
                world_background=world_background,
                root=root,
                model_config_path=model_config_path,
            )
            metadata_payload["road_texture"] = road_metadata
            manifest.provenance["road_texture_generation"] = road_metadata
        except Exception as road_exc:
            logger.warning("Road texture generation skipped/failed: %s", road_exc)
            manifest.route_layer.status = "placeholder"
            manifest.route_layer.error = str(road_exc)
            road_metadata = {"status": "failed", "error": str(road_exc)}
            metadata_payload["road_texture"] = road_metadata
            manifest.provenance["road_texture_generation"] = road_metadata
            existing_road = hydrate_existing_road_texture(manifest, root)
            if existing_road["status"] == "ready":
                metadata_payload["existing_road_texture"] = existing_road
    else:
        existing_road = hydrate_existing_road_texture(manifest, root)
        if existing_road["status"] == "ready":
            metadata_payload["existing_road_texture"] = existing_road
            manifest.provenance["existing_road_texture"] = existing_road

    _write_json(metadata_path, metadata_payload)
    _write_json(manifest_path, manifest.model_dump(mode="json"))
    return manifest


def _generate_background(
    *,
    blueprint: SpatialBlueprint,
    manifest: VisualLayoutManifest,
    prompt_payload: dict[str, Any],
    root: Path,
    model_config_path: Path,
) -> dict[str, Any]:
    cfg = load_model_config_by_capability(model_config_path, "image_generation")
    manifest.background.provider = str(cfg.get("name") or "")
    manifest.background.model = str(cfg.get("model") or "")
    client = ImageGenerationClient(cfg)
    target_width = int(manifest.canvas["width_px"])
    target_height = int(manifest.canvas["height_px"])
    target_size = f"{target_width}x{target_height}"
    raw_path = root / "background_raw.png"
    edit_base_path = root / "generation_edit_base.png"
    edit_mask_path = root / "generation_edit_mask.png"
    _validate_image_size(edit_base_path, (target_width, target_height), "Edit base")
    _validate_image_size(edit_mask_path, (target_width, target_height), "Edit mask")
    style_reference_path = _resolve_style_reference_path(cfg, model_config_path)
    reference_paths: list[Path] = []
    if style_reference_path is not None:
        reference_paths.append(style_reference_path)
        prompt_payload["style_reference"] = str(style_reference_path)
    prompt_payload["input_image"] = str(edit_base_path)
    prompt_payload["edit_mask"] = str(edit_mask_path)
    prompt_payload["prompt"] += _reference_image_instruction(
        has_style_reference=style_reference_path is not None,
    )
    _write_json(root / "background_prompt.json", prompt_payload)

    model_metadata = client.generate(
        prompt_payload["prompt"],
        raw_path,
        negative_prompt=prompt_payload.get("negative_prompt", ""),
        size=target_size,
        input_image_path=edit_base_path,
        mask_path=edit_mask_path,
        style_reference_paths=reference_paths,
    )
    mask_validation = validate_protected_regions(
        edit_base_path,
        raw_path,
        edit_mask_path,
        expected_size=(target_width, target_height),
        blueprint=blueprint,
    )
    composite_metadata = finalize_generated_background(
        raw_path,
        root / "background.png",
        target_size=(target_width, target_height),
        blueprint=blueprint,
        placeholder_style=manifest.location_placeholder_layer.style,
    )
    manifest.background.composited_layers = ["location_placeholder_layer"]
    safe_model_metadata = {key: value for key, value in model_metadata.items() if key != "raw_result"}
    return {
        "status": "ready",
        "generation_strategy": "single_hard_mask_edit_clean_reservations_v2",
        "requested_target_size": {"width": target_width, "height": target_height},
        "model": safe_model_metadata,
        "mask_validation": mask_validation,
        "composite": composite_metadata,
        "attempt_failures": [],
        "style_reference": style_reference_path.name if style_reference_path is not None else None,
    }


def _reference_image_instruction(*, has_style_reference: bool) -> str:
    instruction = (
        "\n\n输入图顺序：第一张图是与输出完全同尺寸的地图编辑底板，并配有硬蒙版。"
        "深色区域允许重新绘制，中灰色矩形是地点保留区，浅灰色狭长区域是道路保留区。"
    )
    if has_style_reference:
        instruction += (
            "第二张图只用于参考较大像素簇、有限色阶、硬边轮廓和简化卡通造型，"
            "不要复制其中的具体建筑、车辆、人物或文字。"
        )
    return instruction


def _resolve_style_reference_path(cfg: dict[str, Any], model_config_path: Path) -> Path | None:
    configured = str(cfg.get("style_reference_path") or "").strip()
    if not configured:
        return None
    path = Path(configured)
    if not path.is_absolute():
        path = model_config_path.parent.parent / path
    path = path.resolve()
    if not path.is_file():
        raise RuntimeError(f"Configured style reference does not exist: {path}")
    return path


def _validate_image_size(path: Path, expected: tuple[int, int], label: str) -> None:
    from PIL import Image

    with Image.open(path) as image:
        actual = image.size
    if actual != expected:
        raise ValueError(f"{label} image size {actual} does not match Stage2 canvas size {expected}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
