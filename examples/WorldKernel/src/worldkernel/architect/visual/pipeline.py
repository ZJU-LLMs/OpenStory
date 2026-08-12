from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
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
from worldkernel.architect.visual.image_size import normalize_generated_image_size
from worldkernel.architect.visual.location_layer import (
    generate_location_layer as generate_location_layer_asset,
    hydrate_existing_location_layer,
)
from worldkernel.architect.visual.models import VisualLayoutManifest
from worldkernel.architect.visual.prompt import compose_background_prompt
from worldkernel.llm.config_loader import load_model_config_by_capability

logger = logging.getLogger(__name__)

BACKGROUND_TRANSPORT_MAX_ATTEMPTS = 2
BACKGROUND_TRANSPORT_RETRY_SECONDS = 2.0


def run_visual_pipeline(
    *,
    blueprint: SpatialBlueprint,
    world_background: dict[str, Any],
    output_root: str | Path,
    model_config_path: str | Path,
    generate_background: bool = False,
    generate_location_layer: bool = False,
    semantic_locations: list[Any] | None = None,
    semantic_characters: list[Any] | None = None,
    generate_character_layer: bool = False,
    character_batch_size: int = 6,
    character_key_colors: list[str] | None = None,
    character_transparent_threshold: int = 24,
    character_opaque_threshold: int = 96,
    force_character_batch_ids: list[str] | None = None,
    force_location_regeneration: bool = False,
    location_debug_artifact_root: str | Path | None = None,
) -> VisualLayoutManifest:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)

    manifest = build_visual_layout_manifest(
        blueprint=blueprint,
        world_background=world_background,
        output_root=root,
    )
    from worldkernel.architect.visual.character_atlas import (
        hydrate_existing_character_layer,
    )

    hydrate_existing_character_layer(
        manifest,
        root,
        candidate_layers=[
            blueprint.visual.get("character_layer")
            if isinstance(blueprint.visual, dict)
            else None
        ],
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
            manifest.background.asset_version = _asset_version(root / "background.png")
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
                existing_layers = []
            manifest.background.status = "ready"
            manifest.background.path = str(existing_background_path)
            manifest.background.url = "background.png"
            manifest.background.asset_version = _asset_version(existing_background_path)
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

    if generate_location_layer:
        _write_json(manifest_path, manifest.model_dump(mode="json"))
        try:
            background_reference_path = root / "background.png"
            if not background_reference_path.exists():
                raise RuntimeError(
                    "Location map generation requires an existing background.png "
                    "or generate_background=true"
                )
            layer_metadata = generate_location_layer_asset(
                blueprint=blueprint,
                manifest=manifest,
                world_background=world_background,
                semantic_locations=semantic_locations or [],
                root=root,
                model_config_path=model_config_path,
                background_reference_path=background_reference_path,
                progress_manifest_path=manifest_path,
                force_regenerate=force_location_regeneration,
                debug_artifact_root=location_debug_artifact_root,
            )
            metadata_payload["location_layer"] = layer_metadata
            manifest.provenance["location_layer_generation"] = layer_metadata
        except Exception as patch_exc:
            logger.warning("Location layer generation skipped/failed: %s", patch_exc)
            manifest.location_layer.status = "failed"
            manifest.location_layer.evaluation_status = "failed"
            manifest.location_layer.error = str(patch_exc)
            manifest.location_layer.path = ""
            manifest.location_layer.url = ""
            manifest.location_layer.completed_location_ids = []
            manifest.location_layer.failed_location_ids = [
                str(slot.location_id) for slot in manifest.slots
            ]
            metadata_payload["location_layer"] = {
                "status": "failed",
                "evaluation_status": "failed",
                "error": str(patch_exc),
            }
            manifest.provenance["location_layer_generation"] = metadata_payload["location_layer"]
    else:
        hydrated_layer = hydrate_existing_location_layer(manifest, root)
        if hydrated_layer["status"] != "missing":
            metadata_payload["existing_location_layer"] = hydrated_layer
            manifest.provenance["existing_location_layer"] = hydrated_layer

    manifest.route_layer.status = "integrated"
    manifest.route_layer.path = ""
    manifest.route_layer.url = ""
    manifest.route_layer.atlas_path = ""
    manifest.route_layer.prompt_path = ""
    manifest.route_layer.metadata_path = ""
    for legacy_name in ("road_atlas.png", "road_layer.png", "road_prompt.json", "road_metadata.json"):
        (root / legacy_name).unlink(missing_ok=True)
    metadata_payload["road_rendering"] = {
        "status": "integrated" if manifest.location_layer.status in {"ready", "partial"} else "pending",
        "source": "spatial_blueprint.road_tiles",
        "asset": "location_layer.png",
        "independent_texture_generation": False,
    }
    manifest.provenance["road_rendering"] = metadata_payload["road_rendering"]

    if semantic_characters is not None:
        from worldkernel.architect.visual.character_atlas import (
            InvalidCharacterBatchSelection,
            run_character_atlas_pipeline,
        )

        try:
            character_metadata = run_character_atlas_pipeline(
                manifest=manifest,
                semantic_characters=semantic_characters,
                root=root,
                model_config_path=model_config_path,
                generate=generate_character_layer,
                max_batch_size=character_batch_size,
                key_colors=character_key_colors,
                transparent_threshold=character_transparent_threshold,
                opaque_threshold=character_opaque_threshold,
                force_batch_ids=force_character_batch_ids,
                progress_manifest_path=manifest_path,
            )
            metadata_payload["character_layer"] = character_metadata
            manifest.provenance["character_layer_generation"] = character_metadata
        except InvalidCharacterBatchSelection:
            raise
        except Exception as exc:
            logger.warning("Character atlas generation skipped/failed: %s", exc)
            manifest.character_layer.status = "failed"
            manifest.character_layer.error = str(exc)
            metadata_payload["character_layer"] = {
                "status": "failed",
                "error": str(exc),
            }
            manifest.provenance["character_layer_generation"] = metadata_payload["character_layer"]

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
    mask_restored_path = root / "background_mask_restored.png"
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

    attempt_failures: list[str] = []
    model_metadata: dict[str, Any] | None = None
    for transport_attempt in range(1, BACKGROUND_TRANSPORT_MAX_ATTEMPTS + 1):
        try:
            generated_metadata = client.generate(
                prompt_payload["prompt"],
                raw_path,
                negative_prompt=prompt_payload.get("negative_prompt", ""),
                size=target_size,
                input_image_path=edit_base_path,
                mask_path=edit_mask_path,
                style_reference_paths=reference_paths,
            )
            model_metadata = {
                **generated_metadata,
                "transport_attempt_count": transport_attempt,
                "transport_failures": list(attempt_failures),
            }
            break
        except Exception as exc:
            message = str(exc)
            attempt_failures.append(message)
            if (
                transport_attempt >= BACKGROUND_TRANSPORT_MAX_ATTEMPTS
                or not _is_transient_image_error(message)
            ):
                raise RuntimeError(
                    "Background image generation failed after "
                    f"{transport_attempt} transport attempt(s): {message}"
                ) from exc
            logger.warning(
                "Transient background image error on attempt %s/%s: %s",
                transport_attempt,
                BACKGROUND_TRANSPORT_MAX_ATTEMPTS,
                message,
            )
            time.sleep(BACKGROUND_TRANSPORT_RETRY_SECONDS)
    if model_metadata is None:
        raise RuntimeError("Background image generation exhausted transport attempts")
    size_normalization = normalize_generated_image_size(
        raw_path,
        (target_width, target_height),
        original_output_path=root / "background_model_output.png",
    )
    model_metadata["size_normalization"] = size_normalization
    shutil.copyfile(raw_path, mask_restored_path)
    mask_validation = validate_protected_regions(
        edit_base_path,
        mask_restored_path,
        edit_mask_path,
        expected_size=(target_width, target_height),
        blueprint=blueprint,
        fail_on_excessive_change=False,
    )
    composite_metadata = finalize_generated_background(
        mask_restored_path,
        root / "background.png",
        target_size=(target_width, target_height),
        blueprint=blueprint,
        placeholder_style=manifest.location_placeholder_layer.style,
    )
    manifest.background.composited_layers = []
    safe_model_metadata = {key: value for key, value in model_metadata.items() if key != "raw_result"}
    return {
        "status": "ready",
        "generation_strategy": "full_canvas_hard_mask_sparse_background_edit_v7",
        "requested_target_size": {"width": target_width, "height": target_height},
        "model": safe_model_metadata,
        "size_normalization": size_normalization,
        "mask_validation": mask_validation,
        "raw_model_output_path": str(raw_path),
        "mask_restored_path": str(mask_restored_path),
        "composite": composite_metadata,
        "attempt_failures": attempt_failures,
        "style_reference": style_reference_path.name if style_reference_path is not None else None,
    }


def _is_transient_image_error(message: str) -> bool:
    text = message.lower()
    return any(
        token in text
        for token in (
            "http 429",
            "http 502",
            "http 503",
            "http 504",
            "timed out",
            "timeout",
            "connection reset",
            "remote end closed",
            "temporarily unavailable",
        )
    )


def _reference_image_instruction(*, has_style_reference: bool) -> str:
    if has_style_reference:
        return (
            "\n\n第二张输入图仅用作画风参考：提取其中较大像素簇、有限色阶、硬边轮廓和简化卡通造型，"
            "不要复制其中的具体建筑、车辆、人物或文字。"
        )
    return ""


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


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _asset_version(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]
