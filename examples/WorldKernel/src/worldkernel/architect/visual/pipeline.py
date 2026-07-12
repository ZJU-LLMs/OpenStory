from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from worldkernel.architect.spatial.models import SpatialBlueprint
from worldkernel.architect.visual.client import ImageGenerationClient
from worldkernel.architect.visual.control import (
    composite_protected_background,
    render_layout_control_assets,
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
    style_reference_path = _resolve_style_reference_path(cfg, model_config_path)
    style_instruction = _style_reference_instruction()
    if style_reference_path is not None:
        prompt_payload["prompt"] += style_instruction
        prompt_payload["style_reference"] = str(style_reference_path)
        _write_json(root / "background_prompt.json", prompt_payload)

    model_metadata = client.generate(
        prompt_payload["prompt"],
        raw_path,
        negative_prompt=prompt_payload.get("negative_prompt", ""),
        size=target_size,
        input_image_path=root / "generation_control.png",
        mask_path=root / "generation_mask.png",
        style_reference_paths=[style_reference_path] if style_reference_path is not None else None,
    )
    composite_metadata = composite_protected_background(
        raw_path,
        root / "generation_base.png",
        root / "generation_mask.png",
        root / "background.png",
        target_size=(target_width, target_height),
    )
    safe_model_metadata = {key: value for key, value in model_metadata.items() if key != "raw_result"}
    return {
        "status": "ready",
        "generation_strategy": "single_global_masked_edit",
        "requested_target_size": {"width": target_width, "height": target_height},
        "model": safe_model_metadata,
        "composite": composite_metadata,
        "attempt_failures": [],
        "style_reference": style_reference_path.name if style_reference_path is not None else None,
    }


def _style_reference_instruction() -> str:
    return (
        "\n\n输入图说明：第一张图像是严格的布局控制底板，其中的完整建筑体块和道路走廊是必须保留的坐标约束；"
        "只能围绕这些已占用位置生成环境，不得复制或移动这些形状。第二张图像只用于参考像素美术语言。"
        "仅学习第二张图的较大像素块、有限色阶、清晰硬边轮廓、简化卡通造型和低纹理密度，"
        "不复制其中的警察局、车辆、道路、文字、具体建筑结构、人物或现代城市内容。"
        "地图题材与风物必须完全服从当前世界设定。"
    )


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
