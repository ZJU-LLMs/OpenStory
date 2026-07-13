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
from worldkernel.architect.visual.models import VisualLayoutManifest
from worldkernel.architect.visual.prompt import compose_background_prompt
from worldkernel.llm.config_loader import load_model_config_by_capability

logger = logging.getLogger(__name__)


def run_visual_pipeline(
    *,
    blueprint: SpatialBlueprint,
    world_background: dict[str, Any],
    output_root: str | Path,
    model_config_path: str | Path,
    generate_background: bool = False,
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
    manifest.background.debug_mask_path = control_metadata["debug_mask_path"]
    manifest.background.location_mask_path = control_metadata["location_mask_path"]
    manifest.background.road_mask_path = control_metadata["road_mask_path"]
    prompt_payload = compose_background_prompt(world_background, manifest)

    prompt_path = root / "background_prompt.json"
    metadata_path = root / "background_metadata.json"
    manifest_path = root / "visual_layout_manifest.json"
    _write_json(prompt_path, prompt_payload)
    manifest.background.prompt_path = str(prompt_path)
    manifest.background.metadata_path = str(metadata_path)

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
            _write_json(metadata_path, {**control_metadata, **generation_metadata})
        except Exception as exc:  # Stage2 remains usable with deterministic coordinate layers.
            logger.warning("Visual background generation skipped/failed: %s", exc)
            manifest.background.status = "failed"
            manifest.background.error = str(exc)
            _write_json(metadata_path, {**control_metadata, "status": "failed", "error": str(exc)})
    else:
        manifest.background.status = "prompt_ready"
        _write_json(
            metadata_path,
            {**control_metadata, "status": "prompt_ready", "image_generation": "disabled"},
        )

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
    location_mask_path = root / "generation_location_mask.png"
    road_mask_path = root / "generation_road_mask.png"
    _validate_image_size(edit_base_path, (target_width, target_height), "Edit base")
    _validate_image_size(edit_mask_path, (target_width, target_height), "Edit mask")
    _validate_image_size(location_mask_path, (target_width, target_height), "Location mask")
    _validate_image_size(road_mask_path, (target_width, target_height), "Road mask")
    style_reference_path = _resolve_style_reference_path(cfg, model_config_path)
    reference_paths: list[Path] = []
    if style_reference_path is not None:
        reference_paths.append(style_reference_path)
        prompt_payload["style_reference"] = str(style_reference_path)
    prompt_payload["input_image"] = str(edit_base_path)
    prompt_payload["edit_mask"] = str(edit_mask_path)
    prompt_payload["location_mask"] = str(location_mask_path)
    prompt_payload["road_mask"] = str(road_mask_path)
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
        route_style=manifest.route_layer.style,
        placeholder_style=manifest.location_placeholder_layer.style,
    )
    manifest.background.composited_layers = ["route_layer", "location_placeholder_layer"]
    safe_model_metadata = {key: value for key, value in model_metadata.items() if key != "raw_result"}
    return {
        "status": "ready",
        "generation_strategy": "single_hard_mask_edit",
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
