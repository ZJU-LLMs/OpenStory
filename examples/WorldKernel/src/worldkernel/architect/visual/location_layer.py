from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont

from worldkernel.architect.spatial.models import SpatialBlueprint
from worldkernel.architect.visual.client import ImageGenerationClient
from worldkernel.architect.visual.models import VisualLayoutManifest, VisualSlot
from worldkernel.architect.visual.visual_evaluator import (
    VisualEvaluationError,
    VisualEvaluator,
    render_review_assets,
)
from worldkernel.llm.config_loader import load_model_config_by_capability


GENERATION_STRATEGY = "full_canvas_location_and_road_inverse_mask_visual_review_v7"
MIN_CONTENT_CHANGE_RATIO = 0.02
MIN_GLOBAL_CHANGE_RATIO = 0.005
MIN_EDITABLE_CHANGE_RATIO = 0.005
MARKER_WARNING_RATIO = 0.05
MAX_MARKER_REMAINING_RATIO = 0.20
INITIAL_MASK_EXPANSION_TILES = 1
LOCATION_DETAIL_TOTAL_BUDGET = 2000
LOCATION_DETAIL_MIN_CHARS = 80
LOCATION_DETAIL_MAX_CHARS = 112
IMAGE_TRANSPORT_MAX_ATTEMPTS = 2
IMAGE_TRANSPORT_RETRY_SECONDS = 2.0


def generate_location_layer(
    *,
    blueprint: SpatialBlueprint,
    manifest: VisualLayoutManifest,
    world_background: dict[str, Any],
    semantic_locations: list[Any],
    root: str | Path,
    model_config_path: str | Path,
    background_reference_path: str | Path,
    progress_manifest_path: str | Path | None = None,
    force_regenerate: bool = False,
    debug_artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    """Generate, visually review, and if needed correct one full-canvas location map."""

    root_path = Path(root)
    debug_root = Path(debug_artifact_root) if debug_artifact_root is not None else None
    attempt_root = debug_root or root_path
    if debug_root is not None:
        debug_root.mkdir(parents=True, exist_ok=True)
    layer_path = root_path / "location_layer.png"
    metadata_path = root_path / "location_layer_metadata.json"
    evaluation_report_path = root_path / "location_alignment_report.json"
    prompt_root = root_path / "location_batch_prompts"
    prompt_root.mkdir(parents=True, exist_ok=True)
    prompt_path = prompt_root / "full_map.json"

    canvas_size = (
        int(manifest.canvas.get("width_px") or 0),
        int(manifest.canvas.get("height_px") or 0),
    )
    if min(canvas_size) <= 0:
        raise ValueError(f"Invalid location layer canvas size: {canvas_size}")

    reference_path = Path(background_reference_path)
    if not reference_path.is_file():
        raise RuntimeError(f"Location layer requires background.png: {reference_path}")
    with Image.open(reference_path) as background_image:
        background = background_image.convert("RGB")
    if background.size != canvas_size:
        raise ValueError(
            f"Location background size {background.size} does not match canvas {canvas_size}"
        )

    existing_metadata = _read_json(metadata_path)
    if (
        not force_regenerate
        and existing_metadata.get("generation_strategy") == GENERATION_STRATEGY
        and existing_metadata.get("evaluation_status") in {"passed", "partial"}
        and evaluation_report_path.is_file()
        and _image_has_size(layer_path, canvas_size)
    ):
        records = _location_record_index(existing_metadata)
        model = existing_metadata.get("model") if isinstance(existing_metadata.get("model"), dict) else {}
        _set_location_layer_asset(
            manifest,
            layer_path=layer_path,
            metadata_path=metadata_path,
            prompt_root=prompt_root,
            provider=str(model.get("provider") or ""),
            model=str(model.get("model") or ""),
            records=records,
            status=str(existing_metadata.get("status") or "partial"),
            evaluation_status=str(existing_metadata.get("evaluation_status") or "partial"),
            evaluation_model=str(existing_metadata.get("evaluation_model") or ""),
            evaluation_report_path=evaluation_report_path,
            attempt_count=int(existing_metadata.get("attempt_count") or 0),
            selected_attempt=int(existing_metadata.get("selected_attempt") or 0),
            alignment_score=float(existing_metadata.get("alignment_score") or 0.0),
        )
        _write_progress_manifest(manifest, progress_manifest_path)
        return existing_metadata

    location_index = _index_locations(semantic_locations)
    region_index = {region.location_id: region for region in blueprint.regions}
    _validate_location_inputs(
        manifest=manifest,
        region_index=region_index,
        location_index=location_index,
        semantic_locations=semantic_locations,
        canvas_size=canvas_size,
    )
    items = [
        {
            "number": number,
            "slot": slot,
            "location": _lookup_location(
                location_index,
                slot,
                region_index.get(slot.location_id),
            ),
        }
        for number, slot in enumerate(manifest.slots, start=1)
    ]
    prompt_payload = compose_location_map_prompt(
        world_background=world_background,
        visual_profile=manifest.visual_profile,
        items=items,
        canvas_size=canvas_size,
    )

    control = background.copy()
    _draw_road_scaffold(control, blueprint, manifest)
    initial_marker_masks: dict[str, Image.Image] = {}
    for item in items:
        slot = item["slot"]
        _draw_location_scaffold(control, slot)
        initial_marker_masks[slot.location_id] = _draw_location_marker(
            control,
            slot,
            item["number"],
        )
    initial_edit_mask, initial_mask_metadata = build_initial_location_edit_mask(
        blueprint=blueprint,
        manifest=manifest,
        canvas_size=canvas_size,
    )
    prompt_payload["initial_edit_mask"] = initial_mask_metadata
    _write_json(prompt_path, prompt_payload)

    cfg = load_model_config_by_capability(model_config_path, "image_generation")
    evaluator_cfg = load_model_config_by_capability(model_config_path, "vision_evaluation")
    client = ImageGenerationClient(cfg)
    evaluator = VisualEvaluator(evaluator_cfg)
    attempt_reports: list[dict[str, Any]] = []
    candidate_paths: list[Path] = []
    temporary_paths: list[Path] = []
    best: dict[str, Any] | None = None

    try:
        for attempt in range(1, evaluator.max_candidates + 1):
            prefix = "location_attempt" if debug_root is not None else ".location_attempt"
            input_path = attempt_root / f"{prefix}_{attempt}_input.png"
            candidate_path = attempt_root / f"{prefix}_{attempt}.png"
            overview_path = attempt_root / f"{prefix}_{attempt}_overview.png"
            details_path = attempt_root / f"{prefix}_{attempt}_details.jpg"
            temporary_paths.extend([input_path, overview_path, details_path])
            candidate_paths.append(candidate_path)
            request_mask_path: Path | None = None

            if attempt == 1 or best is None:
                attempt_control = control.copy()
                marker_masks = initial_marker_masks
                attempt_prompt = dict(prompt_payload)
                if attempt > 1:
                    attempt_prompt["prompt"] += (
                        "\n上一个候选未通过本地检查。重新生成全部地点，并彻底移除所有编号和控制框。"
                    )
            else:
                with Image.open(best["path"]) as best_image:
                    attempt_control = best_image.convert("RGB")
                problem_ids = _problem_location_ids(best["evaluation"])
                marker_masks = _draw_correction_markers(attempt_control, items, problem_ids)
                if _road_needs_correction(best["evaluation"]):
                    _draw_road_scaffold(attempt_control, blueprint, manifest, correction=True)
                attempt_prompt = compose_location_correction_prompt(
                    base_payload=prompt_payload,
                    items=items,
                    evaluation=best["evaluation"],
                    attempt=attempt,
                )

            attempt_prompt_path = prompt_root / f"attempt_{attempt}.json"
            _write_json(attempt_prompt_path, attempt_prompt)
            attempt_control.save(input_path, format="PNG")
            if attempt == 1:
                mask_name = (
                    "location_attempt_1_mask.png"
                    if debug_root is not None
                    else ".location_attempt_1_mask.png"
                )
                request_mask_path = attempt_root / mask_name
                initial_edit_mask.save(request_mask_path, format="PNG")
                temporary_paths.append(request_mask_path)
            model_metadata = _generate_location_candidate(
                client=client,
                prompt=attempt_prompt["prompt"],
                negative_prompt=attempt_prompt["negative_prompt"],
                candidate_path=candidate_path,
                size=f"{canvas_size[0]}x{canvas_size[1]}",
                input_path=input_path,
                mask_path=request_mask_path,
            )
            _validate_image_size(candidate_path, canvas_size, f"Location candidate {attempt}")
            with Image.open(candidate_path) as generated_image:
                generated = generated_image.convert("RGB")

            local = _validate_candidate_locally(
                before=background,
                control=attempt_control,
                generated=generated,
                items=items,
                marker_masks=marker_masks,
                edit_mask=initial_edit_mask if attempt == 1 else None,
            )
            attempt_entry: dict[str, Any] = {
                "attempt": attempt,
                "prompt_path": str(attempt_prompt_path),
                "local_validation": local,
                "model": _safe_model_metadata(model_metadata),
            }
            if attempt == 1:
                attempt_entry["request_mask"] = initial_mask_metadata
            if not local["passed"]:
                attempt_entry["status"] = "local_validation_failed"
                attempt_reports.append(attempt_entry)
                continue

            render_review_assets(
                candidate=generated,
                items=items,
                blueprint=blueprint,
                overview_path=overview_path,
                details_path=details_path,
            )
            evaluation = evaluator.evaluate(
                overview_path=overview_path,
                details_path=details_path,
                items=items,
                blueprint=blueprint,
                attempt=attempt,
                local_warnings=local["warnings_by_location"],
            )
            attempt_entry["status"] = "passed" if evaluation["decision"]["passed"] else "rejected"
            attempt_entry["evaluation"] = evaluation
            attempt_reports.append(attempt_entry)
            candidate = {
                "attempt": attempt,
                "path": candidate_path,
                "evaluation": evaluation,
                "local": local,
                "model_metadata": model_metadata,
            }
            if best is None or _candidate_rank(candidate) < _candidate_rank(best):
                best = candidate
            if evaluation["decision"]["passed"]:
                best = candidate
                break

        if best is None:
            raise RuntimeError("No location candidate passed deterministic validation")

        selected_attempt = int(best["attempt"])
        selected_decision = best["evaluation"]["decision"]
        final_status = "ready" if selected_decision["passed"] else "partial"
        with Image.open(best["path"]) as selected_image:
            selected_rgba = selected_image.convert("RGBA")
            selected_rgba.save(layer_path, format="PNG")
            if final_status == "partial":
                debug_path = root_path / "location_alignment_debug.png"
                debug_details = (
                    debug_root / "location_alignment_selected_details.jpg"
                    if debug_root is not None
                    else root_path / ".location_alignment_debug_details.jpg"
                )
                render_review_assets(
                    candidate=selected_rgba,
                    items=items,
                    blueprint=blueprint,
                    overview_path=debug_path,
                    details_path=debug_details,
                )
                if debug_root is None:
                    debug_details.unlink(missing_ok=True)

        records = _records_from_evaluation(
            items=items,
            local=best["local"],
            evaluation=best["evaluation"],
        )
        alignment_report = {
            "status": "passed" if final_status == "ready" else "partial",
            "generation_strategy": GENERATION_STRATEGY,
            "evaluation_model": evaluator.model,
            "attempt_count": len(attempt_reports),
            "selected_attempt": selected_attempt,
            "alignment_score": selected_decision["alignment_score"],
            "selection_reason": _selection_reason(best, attempt_reports),
            "attempts": attempt_reports,
            "final_evaluation": best["evaluation"],
            "debug_artifact_root": str(debug_root) if debug_root is not None else "",
        }
        _write_json(evaluation_report_path, alignment_report)
    except VisualEvaluationError:
        raise
    finally:
        if debug_root is None:
            for path in temporary_paths + candidate_paths:
                path.unlink(missing_ok=True)

    _set_location_layer_asset(
        manifest,
        layer_path=layer_path,
        metadata_path=metadata_path,
        prompt_root=prompt_root,
        provider=str(cfg.get("name") or ""),
        model=str(cfg.get("model") or ""),
        records=records,
        status=final_status,
        evaluation_status="passed" if final_status == "ready" else "partial",
        evaluation_model=evaluator.model,
        evaluation_report_path=evaluation_report_path,
        attempt_count=len(attempt_reports),
        selected_attempt=selected_attempt,
        alignment_score=float(selected_decision["alignment_score"]),
    )
    metadata = _location_layer_metadata(
        manifest=manifest,
        canvas_size=canvas_size,
        records=records,
        reference_path=reference_path,
        prompt_path=prompt_path,
        model_metadata=best["model_metadata"],
        evaluation_report=alignment_report,
        initial_mask_metadata=initial_mask_metadata,
    )
    metadata["debug_artifact_root"] = str(debug_root) if debug_root is not None else ""
    metadata["debug_artifacts_retained"] = debug_root is not None
    _write_json(metadata_path, metadata)
    _write_progress_manifest(manifest, progress_manifest_path)
    return metadata


def hydrate_existing_location_layer(
    manifest: VisualLayoutManifest,
    root: str | Path,
) -> dict[str, Any]:
    root_path = Path(root)
    layer_path = root_path / "location_layer.png"
    metadata_path = root_path / "location_layer_metadata.json"
    evaluation_report_path = root_path / "location_alignment_report.json"
    prompt_root = root_path / "location_batch_prompts"
    canvas_size = (
        int(manifest.canvas.get("width_px") or 0),
        int(manifest.canvas.get("height_px") or 0),
    )
    metadata = _read_json(metadata_path)
    if (
        metadata.get("generation_strategy") != GENERATION_STRATEGY
        or metadata.get("evaluation_status") not in {"passed", "partial"}
        or not evaluation_report_path.is_file()
        or not _image_has_size(layer_path, canvas_size)
    ):
        return {"status": "missing"}
    records = _location_record_index(metadata)
    model = metadata.get("model") if isinstance(metadata.get("model"), dict) else {}
    _set_location_layer_asset(
        manifest,
        layer_path=layer_path,
        metadata_path=metadata_path,
        prompt_root=prompt_root,
        provider=str(model.get("provider") or ""),
        model=str(model.get("model") or ""),
        records=records,
        status=str(metadata.get("status") or "partial"),
        evaluation_status=str(metadata.get("evaluation_status") or "partial"),
        evaluation_model=str(metadata.get("evaluation_model") or ""),
        evaluation_report_path=evaluation_report_path,
        attempt_count=int(metadata.get("attempt_count") or 0),
        selected_attempt=int(metadata.get("selected_attempt") or 0),
        alignment_score=float(metadata.get("alignment_score") or 0.0),
    )
    return {
        "status": manifest.location_layer.status,
        "generation_strategy": GENERATION_STRATEGY,
        "ready_location_count": len(manifest.location_layer.completed_location_ids),
        "failed_location_count": len(manifest.location_layer.failed_location_ids),
        "evaluation_status": manifest.location_layer.evaluation_status,
        "alignment_score": manifest.location_layer.alignment_score,
        "asset_version": manifest.location_layer.asset_version,
    }


def compose_location_map_prompt(
    *,
    world_background: dict[str, Any],
    visual_profile: dict[str, Any],
    items: list[dict[str, Any]],
    canvas_size: tuple[int, int],
) -> dict[str, Any]:
    location_lines = []
    detail_budget = max(
        LOCATION_DETAIL_MIN_CHARS,
        min(
            LOCATION_DETAIL_MAX_CHARS,
            LOCATION_DETAIL_TOTAL_BUDGET // max(1, len(items)),
        ),
    )
    for item in items:
        slot: VisualSlot = item["slot"]
        location = item["location"]
        name = _location_name(location, slot.location_id)
        visual = _location_visual_brief(
            str(location.get("visual") or location.get("description") or name),
            max_chars=detail_budget,
        )
        location_lines.append(
            f"{item['number']}｜{name}｜{visual}｜"
            f"入口={_entrance_text(slot.entrance_port)}"
        )
    prompt = "\n".join(
        [
            f"在这张 {canvas_size[0]}×{canvas_size[1]} 游戏地图上，同时完成全部地点与连接道路。",
            "青框和左上角小编号只是位置索引，不是招牌、门牌或界面；必须连同占位底板一起彻底擦除，画面中不能留下编号和地点名称。",
            "青绿色狭长带表示道路的精确期望走廊，也必须彻底替换为符合世界设定的道路；不要保留控制色、方格边缘或路线标记。",
            "蒙版透明区允许生成地点主体、外侧一格融合边缘和全部道路走廊；每个地点以对应矩形为主体范围，完整收在附近，不遗漏、不合并。",
            "每个地点都要明确画出完整边界、地面、指定入口、2至4个标志性陈设和可行走空间。不能只画名称牌、黑色面板、屋顶或单个设备。",
            "室内地点画成严格正交俯视的无屋顶2D RPG剖面房间；室外地点画成同投影的开放场景。边缘用墙体、围栏、平台或自然边界完整收尾。",
            "直接延续输入地图的像素簇、轮廓、色板、材质和光照。地点内部细节清楚但不过密，优先保证结构和陈设可辨认。",
            "道路必须沿青绿色走廊连续生成，宽度大致保持一致，转角和交叉口自然连通，并在指定入口处准确接入地点。地点内部不得被道路横穿；进入矩形后的道路应自然收束为门口、台阶或室内入口。",
            "全世界只使用一种统一且符合世界时代、文化和地表的道路视觉语言，不自行增加捷径，不移动、遗漏或切断道路。",
            "禁止人物、可读文字、标签、招牌、信息卡、UI、水印、半栋建筑、截断房间和相互重叠。",
            f"世界设定：{_world_context(world_background)}",
            f"视觉基准：{_visual_context(visual_profile)}",
            "地点清单（名称只用于理解语义，不得画进图中）：",
            *location_lines,
        ]
    )
    negative = (
        "名称牌，文字面板，信息卡，保留编号，保留青框，空占位块，屋顶，截断地点，"
        "地点合并，偏移道路，断路，重复道路，额外捷径，人物，UI，水印，平视，斜视，细碎噪点，模糊"
    )
    return {
        "prompt": prompt,
        "negative_prompt": negative,
        "prompt_role": "location_full_map_edit",
        "background_prompt_reused": False,
        "generation_strategy": GENERATION_STRATEGY,
        "canvas_size": {"width": canvas_size[0], "height": canvas_size[1]},
        "locations": [
            {
                "number": item["number"],
                "location_id": item["slot"].location_id,
                "name": _location_name(item["location"], item["slot"].location_id),
                "visual_brief": _location_visual_brief(
                    str(
                        item["location"].get("visual")
                        or item["location"].get("description")
                        or _location_name(item["location"], item["slot"].location_id)
                    ),
                    max_chars=detail_budget,
                ),
                "bounds_px": dict(item["slot"].bounds_px),
                "entrance_port": dict(item["slot"].entrance_port),
            }
            for item in items
        ],
        "roads": {
            "source": "spatial_blueprint.road_tiles",
            "generated_in_location_layer": True,
        },
    }


def _generate_location_candidate(
    *,
    client: ImageGenerationClient,
    prompt: str,
    negative_prompt: str,
    candidate_path: Path,
    size: str,
    input_path: Path,
    mask_path: Path | None,
) -> dict[str, Any]:
    failures: list[str] = []
    for transport_attempt in range(1, IMAGE_TRANSPORT_MAX_ATTEMPTS + 1):
        try:
            metadata = client.generate(
                prompt,
                candidate_path,
                negative_prompt=negative_prompt,
                size=size,
                input_image_path=input_path,
                mask_path=mask_path,
            )
            return {
                **metadata,
                "transport_attempt_count": transport_attempt,
                "transport_failures": failures,
            }
        except Exception as exc:
            message = str(exc)
            failures.append(message)
            if transport_attempt >= IMAGE_TRANSPORT_MAX_ATTEMPTS or not _is_transient_image_error(message):
                raise
            time.sleep(IMAGE_TRANSPORT_RETRY_SECONDS)
    raise RuntimeError("Location image generation exhausted transport attempts")


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


def compose_location_correction_prompt(
    *,
    base_payload: dict[str, Any],
    items: list[dict[str, Any]],
    evaluation: dict[str, Any],
    attempt: int,
) -> dict[str, Any]:
    evaluation_by_id = {
        str(item.get("location_id")): item
        for item in evaluation.get("locations", [])
        if isinstance(item, dict)
    }
    decision = evaluation.get("decision") if isinstance(evaluation.get("decision"), dict) else {}
    problem_ids = set(decision.get("hard_failure_location_ids") or [])
    problem_ids.update(decision.get("warning_location_ids") or [])
    instructions: list[str] = []
    simplified_locations: list[dict[str, Any]] = []
    for item in items:
        slot: VisualSlot = item["slot"]
        if slot.location_id not in problem_ids:
            continue
        location = item["location"]
        result = evaluation_by_id.get(slot.location_id, {})
        name = _location_name(location, slot.location_id)
        location_type = _location_type(location) or "未指定"
        instruction = str(result.get("retry_instruction") or result.get("reason") or "重新对齐并完整生成")
        instruction = _compact_visual(instruction, max_chars=80)
        instructions.append(f"地点 {item['number']}（{name}）：{instruction}")
        simplified_locations.append(
            {
                "number": item["number"],
                "location_id": slot.location_id,
                "name": name,
                "type": location_type,
                "entrance": _entrance_text(slot.entrance_port),
            }
        )
    correction_text = "\n".join(instructions)
    correction_text = correction_text[:2000]
    road_result = evaluation.get("roads") if isinstance(evaluation.get("roads"), dict) else {}
    road_instruction = ""
    if _road_needs_correction(evaluation):
        road_instruction = _compact_visual(
            str(
                road_result.get("retry_instruction")
                or road_result.get("reason")
                or "沿青绿色道路走廊修复道路，使全部路线连续并准确连接地点入口"
            ),
            max_chars=160,
        )
    prompt = "\n".join(
        [
            f"这是第 {attempt} 次完整地图纠偏。输入图是当前最佳地点地图。",
            "只在红框和编号标出的地点附近修正问题；其他已经正确的地点应尽量保持原样。",
            "红框是后端期望区域，不是最终墙体。将对应地点主体中心放回框内，主体至少一半与框重叠。",
            "地点必须完整，不得截断、遗漏、互相合并。允许墙体、平台和屋檐向框外自然延伸一格或单边15%。",
            "彻底移除本轮红框、编号、入口标记和青绿色道路控制色。不要生成地点名称、人物、UI或水印。",
            "需要纠正的问题：",
            correction_text or "重新生成所有带标记地点并彻底移除控制标记。",
            f"道路纠正：{road_instruction}" if road_instruction else "道路已通过评价，尽量保持现有道路不变。",
        ]
    )
    if attempt >= 3:
        prompt += "\n第三次纠偏只遵循名称、类型、入口和完整性要求，不增加复杂叙事细节。"
    return {
        **base_payload,
        "prompt": prompt,
        "correction_attempt": attempt,
        "correction_locations": simplified_locations,
        "correction_roads": bool(road_instruction),
    }


def _problem_location_ids(evaluation: dict[str, Any]) -> set[str]:
    decision = evaluation.get("decision") if isinstance(evaluation.get("decision"), dict) else {}
    result = set(str(item) for item in decision.get("hard_failure_location_ids") or [])
    result.update(str(item) for item in decision.get("warning_location_ids") or [])
    for item in evaluation.get("locations", []):
        if not isinstance(item, dict) or str(item.get("location_id")) not in result:
            continue
        result.update(str(value) for value in item.get("merged_with", []) if str(value).strip())
    return result


def _road_needs_correction(evaluation: dict[str, Any]) -> bool:
    decision = evaluation.get("decision") if isinstance(evaluation.get("decision"), dict) else {}
    return bool(decision.get("road_hard_failure") or decision.get("road_warning"))


def _draw_correction_markers(
    image: Image.Image,
    items: list[dict[str, Any]],
    problem_ids: set[str],
) -> dict[str, Image.Image]:
    masks: dict[str, Image.Image] = {}
    item_by_id = {str(item["slot"].location_id): item for item in items}
    for location_id in problem_ids:
        item = item_by_id.get(location_id)
        if item is None:
            continue
        masks[location_id] = _draw_location_marker(
            image,
            item["slot"],
            int(item["number"]),
            marker_color=(255, 38, 38),
            badge_fill=(64, 0, 0),
        )
    return masks


def build_initial_location_edit_mask(
    *,
    blueprint: SpatialBlueprint,
    manifest: VisualLayoutManifest,
    canvas_size: tuple[int, int],
) -> tuple[Image.Image, dict[str, Any]]:
    """Expose Stage2 locations and roads while protecting the remaining background."""

    width, height = canvas_size
    tile_size = max(1, int(manifest.canvas.get("tile_size") or blueprint.grid.tile_size))
    alpha = Image.new("L", canvas_size, 255)
    alpha_draw = ImageDraw.Draw(alpha)

    for slot in manifest.slots:
        box = _slot_pixel_box(slot, canvas_size, expand_px=tile_size * INITIAL_MASK_EXPANSION_TILES)
        if box is not None:
            alpha_draw.rectangle(box, fill=0)

    road_tiles: set[tuple[int, int]] = set()
    for point in blueprint.road_tiles:
        tile = (int(point.x), int(point.y))
        if tile in road_tiles:
            continue
        road_tiles.add(tile)
        box = _tile_pixel_box(tile, tile_size, canvas_size)
        if box is not None:
            alpha_draw.rectangle(box, fill=0)

    connector_tiles: set[tuple[int, int]] = set()
    for slot in manifest.slots:
        connector_tiles.update(_entrance_connector_tiles(slot))
    for tile in connector_tiles:
        box = _tile_pixel_box(tile, tile_size, canvas_size)
        if box is not None:
            alpha_draw.rectangle(box, fill=0)

    for slot in manifest.slots:
        box = _slot_pixel_box(slot, canvas_size)
        if box is None:
            raise ValueError(f"Location slot is outside the edit canvas: {slot.location_id}")
        crop = alpha.crop((box[0], box[1], box[2] + 1, box[3] + 1))
        if crop.histogram()[0] != crop.width * crop.height:
            raise ValueError(f"Location slot is not fully editable: {slot.location_id}")

    editable_pixels = alpha.histogram()[0]
    protected_pixels = alpha.histogram()[255]
    editable_road_pixels = len(
        {tile for tile in road_tiles if _tile_pixel_box(tile, tile_size, canvas_size) is not None}
    ) * tile_size * tile_size
    mask = Image.new("RGBA", canvas_size, (255, 255, 255, 255))
    mask.putalpha(alpha)
    metadata = {
        "mode": "inverse_location_and_road_mask",
        "semantics": "transparent_pixels_editable_opaque_pixels_protected",
        "expansion_tiles": INITIAL_MASK_EXPANSION_TILES,
        "location_count": len(manifest.slots),
        "editable_pixels": editable_pixels,
        "protected_pixels": protected_pixels,
        "road_tile_count": len(road_tiles),
        "editable_road_pixels": editable_road_pixels,
        "protected_road_pixels": 0,
        "entrance_connector_tile_count": len(
            {
                tile
                for tile in connector_tiles
                if _tile_pixel_box(tile, tile_size, canvas_size) is not None
            }
        ),
        "canvas_size": {"width": width, "height": height},
    }
    return mask, metadata


def _validate_candidate_locally(
    *,
    before: Image.Image,
    control: Image.Image,
    generated: Image.Image,
    items: list[dict[str, Any]],
    marker_masks: dict[str, Image.Image],
    edit_mask: Image.Image | None = None,
) -> dict[str, Any]:
    global_change_ratio = _image_change_ratio(control, generated)
    editable_change_ratio: float | None = None
    protected_change_ratio: float | None = None
    location_results: dict[str, dict[str, Any]] = {}
    warnings_by_location: dict[str, list[str]] = {}
    failures: list[str] = []
    if edit_mask is None:
        if global_change_ratio < MIN_GLOBAL_CHANGE_RATIO:
            failures.append("candidate_nearly_unchanged")
    else:
        if edit_mask.size != generated.size or edit_mask.mode != "RGBA":
            raise ValueError("Initial location edit mask must be same-size RGBA")
        alpha = edit_mask.getchannel("A")
        editable = ImageChops.invert(alpha)
        difference = _max_channel(ImageChops.difference(control, generated)).point(
            lambda value: 255 if value > 12 else 0
        )
        editable_pixels = editable.histogram()[255]
        protected_pixels = alpha.histogram()[255]
        editable_changed = ImageChops.multiply(difference, editable).histogram()[255]
        protected_changed = ImageChops.multiply(difference, alpha).histogram()[255]
        editable_change_ratio = (
            editable_changed / editable_pixels if editable_pixels else 0.0
        )
        protected_change_ratio = (
            protected_changed / protected_pixels if protected_pixels else 0.0
        )
        if editable_change_ratio < MIN_EDITABLE_CHANGE_RATIO:
            failures.append("editable_area_nearly_unchanged")
    for item in items:
        slot: VisualSlot = item["slot"]
        location_id = slot.location_id
        diagnostics = _validate_location_result(
            before=before,
            control=control,
            generated=generated,
            marker_mask=marker_masks.get(location_id),
            bounds=slot.bounds_px,
        )
        location_results[location_id] = diagnostics
        warnings: list[str] = []
        marker_ratio = float(diagnostics.get("marker_remaining_ratio") or 0.0)
        if marker_ratio > MAX_MARKER_REMAINING_RATIO:
            failures.append(f"marker_remaining:{location_id}")
        elif marker_ratio > MARKER_WARNING_RATIO:
            warnings.append("控制标记可能有少量残留")
        if float(diagnostics.get("content_change_ratio") or 0.0) < MIN_CONTENT_CHANGE_RATIO:
            warnings.append("地点区域变化较少，请重点确认是否遗漏")
        if warnings:
            warnings_by_location[location_id] = warnings
    return {
        "passed": not failures,
        "failures": failures,
        "global_change_ratio": global_change_ratio,
        "minimum_global_change_ratio": MIN_GLOBAL_CHANGE_RATIO,
        "editable_change_ratio": editable_change_ratio,
        "minimum_editable_change_ratio": MIN_EDITABLE_CHANGE_RATIO,
        "protected_change_ratio": protected_change_ratio,
        "protected_change_is_diagnostic_only": edit_mask is not None,
        "marker_warning_ratio": MARKER_WARNING_RATIO,
        "maximum_marker_remaining_ratio": MAX_MARKER_REMAINING_RATIO,
        "warnings_by_location": warnings_by_location,
        "locations": location_results,
    }


def _records_from_evaluation(
    *,
    items: list[dict[str, Any]],
    local: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    evaluation_by_id = {
        str(item.get("location_id")): item
        for item in evaluation.get("locations", [])
        if isinstance(item, dict)
    }
    decision = evaluation.get("decision") if isinstance(evaluation.get("decision"), dict) else {}
    decision_by_id = {
        str(item.get("location_id")): item
        for item in decision.get("locations", [])
        if isinstance(item, dict)
    }
    hard_ids = set(str(item) for item in decision.get("hard_failure_location_ids") or [])
    records: dict[str, dict[str, Any]] = {}
    for item in items:
        slot: VisualSlot = item["slot"]
        diagnostics = {
            "local": (local.get("locations") or {}).get(slot.location_id, {}),
            "visual_evaluation": evaluation_by_id.get(slot.location_id, {}),
            "decision": decision_by_id.get(slot.location_id, {}),
        }
        records[slot.location_id] = {
            "location_id": slot.location_id,
            "status": "failed" if slot.location_id in hard_ids else "ready",
            "logical_bounds_px": dict(slot.bounds_px),
            "entrance_port": dict(slot.entrance_port),
            "diagnostics": diagnostics,
        }
    return records


def _candidate_rank(candidate: dict[str, Any]) -> tuple[float, ...]:
    decision = candidate["evaluation"]["decision"]
    return (
        float(decision["hard_failure_count"]),
        -float(decision["ok_count"]),
        float(decision["warning_count"]),
        -float(decision.get("road_score") or 0),
        -float(decision["minimum_location_score"]),
        -float(decision["average_location_score"]),
        float(candidate["attempt"]),
    )


def _selection_reason(best: dict[str, Any], attempts: list[dict[str, Any]]) -> str:
    decision = best["evaluation"]["decision"]
    if decision["passed"]:
        return f"第 {best['attempt']} 个候选通过全部本地检查和视觉评价"
    return (
        f"{len(attempts)} 个候选均未完全通过；选择严重问题最少、通过地点最多且得分最高的"
        f"第 {best['attempt']} 个候选"
    )


def _safe_model_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if key != "raw_result"}


def _image_change_ratio(before: Image.Image, after: Image.Image) -> float:
    difference = _max_channel(ImageChops.difference(before.convert("RGB"), after.convert("RGB")))
    changed = difference.point(lambda value: 255 if value > 12 else 0)
    histogram = changed.histogram()
    pixels = before.width * before.height
    return histogram[255] / pixels if pixels else 0.0


def _slot_pixel_box(
    slot: VisualSlot,
    canvas_size: tuple[int, int],
    *,
    expand_px: int = 0,
) -> tuple[int, int, int, int] | None:
    bounds = slot.bounds_px
    x = int(bounds.get("x") or 0)
    y = int(bounds.get("y") or 0)
    width = int(bounds.get("w") or 0)
    height = int(bounds.get("h") or 0)
    if width <= 0 or height <= 0:
        return None
    x0 = max(0, x - expand_px)
    y0 = max(0, y - expand_px)
    x1 = min(canvas_size[0], x + width + expand_px) - 1
    y1 = min(canvas_size[1], y + height + expand_px) - 1
    if x1 < x0 or y1 < y0:
        return None
    return (x0, y0, x1, y1)


def _tile_pixel_box(
    tile: tuple[int, int],
    tile_size: int,
    canvas_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    tile_x, tile_y = tile
    x0 = tile_x * tile_size
    y0 = tile_y * tile_size
    x1 = x0 + tile_size - 1
    y1 = y0 + tile_size - 1
    if x1 < 0 or y1 < 0 or x0 >= canvas_size[0] or y0 >= canvas_size[1]:
        return None
    return (
        max(0, x0),
        max(0, y0),
        min(canvas_size[0] - 1, x1),
        min(canvas_size[1] - 1, y1),
    )


def _entrance_connector_tiles(slot: VisualSlot) -> set[tuple[int, int]]:
    port = slot.entrance_port
    point = port.get("grid_point") if isinstance(port.get("grid_point"), dict) else {}
    grid_x = int(point.get("x") or 0)
    grid_y = int(point.get("y") or 0)
    side = str(port.get("side") or "south")
    width_tiles = max(1, int(port.get("width_tiles") or 1))
    connectors: set[tuple[int, int]] = set()
    for offset in range(width_tiles):
        if side == "north":
            connectors.add((grid_x + offset, grid_y - 1))
        elif side == "south":
            connectors.add((grid_x + offset, grid_y + 1))
        elif side == "west":
            connectors.add((grid_x - 1, grid_y + offset))
        else:
            connectors.add((grid_x + 1, grid_y + offset))
    return connectors


def _draw_road_scaffold(
    image: Image.Image,
    blueprint: SpatialBlueprint,
    manifest: VisualLayoutManifest,
    *,
    correction: bool = False,
) -> None:
    """Mark the exact Stage2 road corridor for image editing and correction."""

    tile_size = max(1, int(manifest.canvas.get("tile_size") or blueprint.grid.tile_size))
    fill = (0, 214, 210) if correction else (54, 156, 166)
    edge = (230, 255, 252) if correction else (22, 92, 100)
    draw = ImageDraw.Draw(image)
    canvas_size = image.size
    for tile in {(int(point.x), int(point.y)) for point in blueprint.road_tiles}:
        box = _tile_pixel_box(tile, tile_size, canvas_size)
        if box is None:
            continue
        draw.rectangle(box, fill=fill)
        draw.rectangle(box, outline=edge, width=max(1, tile_size // 8))


def _draw_location_scaffold(image: Image.Image, slot: VisualSlot) -> None:
    bounds = slot.bounds_px
    x = int(bounds.get("x") or 0)
    y = int(bounds.get("y") or 0)
    width = int(bounds.get("w") or 0)
    height = int(bounds.get("h") or 0)
    if width <= 0 or height <= 0:
        return
    ground = _sample_outer_color(image, (x, y, width, height))
    floor = tuple(min(255, channel + 18) for channel in ground)
    wall = tuple(max(0, round(channel * 0.45)) for channel in ground)
    draw = ImageDraw.Draw(image)
    draw.rectangle((x, y, x + width - 1, y + height - 1), fill=floor)
    outline_width = max(4, int(slot.entrance_port.get("tile_size_px") or 16) // 2)
    draw.rectangle(
        (x, y, x + width - 1, y + height - 1),
        outline=wall,
        width=outline_width,
    )
    _carve_entrance(
        draw,
        slot=slot,
        box=(x, y, width, height),
        floor=floor,
        outline_width=outline_width,
    )


def _carve_entrance(
    draw: ImageDraw.ImageDraw,
    *,
    slot: VisualSlot,
    box: tuple[int, int, int, int],
    floor: tuple[int, int, int],
    outline_width: int,
) -> None:
    x, y, width, height = box
    port = slot.entrance_port
    side = str(port.get("side") or "south")
    tile_size = max(1, int(port.get("tile_size_px") or 16))
    opening = max(1, int(port.get("width_tiles") or 1)) * tile_size
    offset = max(0, int(port.get("offset_tiles") or 0)) * tile_size
    if side in {"north", "south"}:
        left = max(x, min(x + width - opening, x + offset))
        top = y if side == "north" else y + height - outline_width
        draw.rectangle((left, top, left + opening - 1, top + outline_width - 1), fill=floor)
    else:
        top = max(y, min(y + height - opening, y + offset))
        left = x if side == "west" else x + width - outline_width
        draw.rectangle((left, top, left + outline_width - 1, top + opening - 1), fill=floor)


def _draw_location_marker(
    image: Image.Image,
    slot: VisualSlot,
    number: int,
    *,
    marker_color: tuple[int, int, int] = (0, 238, 255),
    badge_fill: tuple[int, int, int] = (0, 34, 40),
) -> Image.Image:
    bounds = slot.bounds_px
    x = int(bounds.get("x") or 0)
    y = int(bounds.get("y") or 0)
    width = int(bounds.get("w") or 0)
    height = int(bounds.get("h") or 0)
    marker_mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(image)
    marker_draw = ImageDraw.Draw(marker_mask)
    outline_width = max(3, min(7, min(width, height) // 24))
    box = (x, y, x + width - 1, y + height - 1)
    draw.rectangle(box, outline=marker_color, width=outline_width)
    marker_draw.rectangle(box, outline=255, width=outline_width)

    badge_size = max(22, min(36, min(width, height) // 5))
    badge_inset = outline_width + 3
    badge = (
        x + badge_inset,
        y + badge_inset,
        x + badge_inset + badge_size,
        y + badge_inset + badge_size,
    )
    draw.rectangle(badge, fill=badge_fill, outline=marker_color, width=outline_width)
    marker_draw.rectangle(badge, fill=255)
    font = _marker_font(max(13, int(badge_size * 0.48)))
    label = str(number)
    text_box = draw.textbbox((0, 0), label, font=font)
    text_xy = (
        badge[0] + (badge_size - (text_box[2] - text_box[0])) // 2,
        badge[1] + (badge_size - (text_box[3] - text_box[1])) // 2 - text_box[1],
    )
    draw.text(text_xy, label, fill=(255, 255, 255), font=font)
    marker_draw.text(text_xy, label, fill=255, font=font)
    return marker_mask


def _validate_location_result(
    *,
    before: Image.Image,
    control: Image.Image,
    generated: Image.Image,
    marker_mask: Image.Image | None,
    bounds: dict[str, int],
) -> dict[str, Any]:
    x = int(bounds.get("x") or 0)
    y = int(bounds.get("y") or 0)
    width = int(bounds.get("w") or 0)
    height = int(bounds.get("h") or 0)
    region = (x, y, x + width, y + height)
    region_mask = Image.new("L", generated.size, 0)
    ImageDraw.Draw(region_mask).rectangle(region, fill=255)
    changed = _max_channel(ImageChops.difference(before, generated)).point(
        lambda value: 255 if value > 16 else 0
    )
    changed_pixels = ImageChops.multiply(changed, region_mask).histogram()[255]
    region_pixels = region_mask.histogram()[255]
    change_ratio = changed_pixels / region_pixels if region_pixels else 0.0

    marker_remaining_ratio = 0.0
    marker_pixels = 0
    if marker_mask is not None and marker_mask.getbbox() is not None:
        marker_changed = _max_channel(ImageChops.difference(control, generated)).point(
            lambda value: 255 if value > 12 else 0
        )
        marker_changed_pixels = ImageChops.multiply(marker_changed, marker_mask).histogram()[255]
        marker_pixels = marker_mask.histogram()[255]
        marker_remaining_ratio = (
            1.0 - marker_changed_pixels / marker_pixels if marker_pixels else 0.0
        )
    passed = (
        marker_remaining_ratio <= MAX_MARKER_REMAINING_RATIO
    )
    return {
        "passed": passed,
        "content_change_ratio": change_ratio,
        "marker_remaining_ratio": marker_remaining_ratio,
        "marker_pixel_count": marker_pixels,
        "minimum_content_change_ratio": MIN_CONTENT_CHANGE_RATIO,
        "maximum_marker_remaining_ratio": MAX_MARKER_REMAINING_RATIO,
    }


def _location_layer_metadata(
    *,
    manifest: VisualLayoutManifest,
    canvas_size: tuple[int, int],
    records: dict[str, dict[str, Any]],
    reference_path: Path,
    prompt_path: Path,
    model_metadata: dict[str, Any],
    evaluation_report: dict[str, Any],
    initial_mask_metadata: dict[str, Any],
) -> dict[str, Any]:
    ready = [key for key, value in records.items() if value.get("status") == "ready"]
    failed = [key for key, value in records.items() if value.get("status") == "failed"]
    return {
        "status": manifest.location_layer.status,
        "generation_strategy": GENERATION_STRATEGY,
        "layer_mode": "full_canvas_locations_and_roads_replacement",
        "includes_roads": True,
        "road_geometry_source": "spatial_blueprint.road_tiles",
        "single_pass": False,
        "mask_commit": False,
        "initial_request_mask_used": True,
        "initial_request_mask": initial_mask_metadata,
        "canvas_size": {"width": canvas_size[0], "height": canvas_size[1]},
        "request_size_source": "visual_layout_manifest.canvas",
        "resize_or_crop": False,
        "background_source": str(reference_path),
        "prompt_path": str(prompt_path),
        "location_count": len(manifest.slots),
        "ready_location_count": len(ready),
        "failed_location_count": len(failed),
        "completed_location_ids": ready,
        "failed_location_ids": failed,
        "evaluation_status": manifest.location_layer.evaluation_status,
        "evaluation_model": manifest.location_layer.evaluation_model,
        "evaluation_report_path": manifest.location_layer.evaluation_report_path,
        "attempt_count": manifest.location_layer.attempt_count,
        "selected_attempt": manifest.location_layer.selected_attempt,
        "alignment_score": manifest.location_layer.alignment_score,
        "locations": list(records.values()),
        "model": {
            "provider": manifest.location_layer.provider,
            "model": manifest.location_layer.model,
            "api_style": model_metadata.get("api_style"),
        },
        "evaluation": {
            "status": evaluation_report.get("status"),
            "attempt_count": evaluation_report.get("attempt_count"),
            "selected_attempt": evaluation_report.get("selected_attempt"),
            "selection_reason": evaluation_report.get("selection_reason"),
        },
        "asset_version": manifest.location_layer.asset_version,
    }


def _set_location_layer_asset(
    manifest: VisualLayoutManifest,
    *,
    layer_path: Path,
    metadata_path: Path,
    prompt_root: Path,
    provider: str,
    model: str,
    records: dict[str, dict[str, Any]],
    status: str,
    evaluation_status: str,
    evaluation_model: str,
    evaluation_report_path: Path,
    attempt_count: int,
    selected_attempt: int,
    alignment_score: float,
) -> None:
    ready = [key for key, value in records.items() if value.get("status") == "ready"]
    failed = [key for key, value in records.items() if value.get("status") == "failed"]
    manifest.location_layer.status = status
    manifest.location_layer.path = str(layer_path)
    manifest.location_layer.url = "location_layer.png"
    manifest.location_layer.width_px = int(manifest.canvas.get("width_px") or 0)
    manifest.location_layer.height_px = int(manifest.canvas.get("height_px") or 0)
    manifest.location_layer.prompt_dir = str(prompt_root)
    manifest.location_layer.metadata_path = str(metadata_path)
    manifest.location_layer.provider = provider
    manifest.location_layer.model = model
    manifest.location_layer.generation_strategy = GENERATION_STRATEGY
    manifest.location_layer.completed_location_ids = ready
    manifest.location_layer.failed_location_ids = failed
    manifest.location_layer.evaluation_status = evaluation_status
    manifest.location_layer.evaluation_model = evaluation_model
    manifest.location_layer.evaluation_report_path = str(evaluation_report_path)
    manifest.location_layer.attempt_count = attempt_count
    manifest.location_layer.selected_attempt = selected_attempt
    manifest.location_layer.alignment_score = alignment_score
    manifest.location_layer.includes_roads = True
    manifest.location_layer.error = ""
    manifest.location_layer.asset_version = _asset_version(layer_path)


def _sample_outer_color(
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> tuple[int, int, int]:
    x, y, width, height = box
    ring = 8
    samples: list[tuple[int, int, int]] = []
    strips = (
        (max(0, x - ring), max(0, y - ring), min(image.width, x + width + ring), y),
        (max(0, x - ring), y + height, min(image.width, x + width + ring), min(image.height, y + height + ring)),
        (max(0, x - ring), y, x, min(image.height, y + height)),
        (x + width, y, min(image.width, x + width + ring), min(image.height, y + height)),
    )
    for strip in strips:
        if strip[2] <= strip[0] or strip[3] <= strip[1]:
            continue
        crop = image.crop(strip).convert("RGB")
        pixels = crop.get_flattened_data() if hasattr(crop, "get_flattened_data") else crop.getdata()
        samples.extend(pixels)
    if not samples:
        return (64, 72, 80)
    middle = len(samples) // 2
    return tuple(sorted(pixel[index] for pixel in samples)[middle] for index in range(3))


def _marker_font(size: int) -> ImageFont.ImageFont:
    for candidate in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _max_channel(image: Image.Image) -> Image.Image:
    red, green, blue = image.convert("RGB").split()
    return ImageChops.lighter(ImageChops.lighter(red, green), blue)


def _index_locations(items: list[Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in items:
        location = _as_dict(item)
        identity = location.get("identity") if isinstance(location.get("identity"), dict) else {}
        for key in (
            location.get("id"),
            location.get("location_id"),
            location.get("name"),
            location.get("location_name"),
            identity.get("id"),
            identity.get("location_id"),
            identity.get("name"),
        ):
            if str(key or "").strip():
                index[str(key)] = location
    return index


def _validate_location_inputs(
    *,
    manifest: VisualLayoutManifest,
    region_index: dict[str, Any],
    location_index: dict[str, dict[str, Any]],
    semantic_locations: list[Any],
    canvas_size: tuple[int, int],
) -> None:
    slot_ids = [str(slot.location_id) for slot in manifest.slots]
    if len(slot_ids) != len(set(slot_ids)):
        raise ValueError("Visual location slots contain duplicate location IDs")
    if set(slot_ids) != set(str(key) for key in region_index):
        raise ValueError("Visual location slots do not match Stage2 regions")
    if semantic_locations:
        missing_semantic = []
        for slot in manifest.slots:
            region = region_index.get(slot.location_id)
            keys = [slot.location_id]
            if region is not None:
                keys.extend([getattr(region, "location_id", ""), getattr(region, "name", "")])
            if not any(str(key) in location_index for key in keys if str(key).strip()):
                missing_semantic.append(slot.location_id)
        if missing_semantic:
            raise ValueError(f"Semantic locations are missing Stage2 regions: {missing_semantic}")
    canvas_width, canvas_height = canvas_size
    for slot in manifest.slots:
        bounds = slot.bounds_px
        x = int(bounds.get("x") or 0)
        y = int(bounds.get("y") or 0)
        width = int(bounds.get("w") or 0)
        height = int(bounds.get("h") or 0)
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid visual slot size for {slot.location_id}: {bounds}")
        if x < 0 or y < 0 or x + width > canvas_width or y + height > canvas_height:
            raise ValueError(f"Visual slot is outside the canvas for {slot.location_id}: {bounds}")


def _lookup_location(
    location_index: dict[str, dict[str, Any]],
    slot: VisualSlot,
    region: Any,
) -> dict[str, Any]:
    keys = [slot.location_id]
    if region is not None:
        keys.extend([getattr(region, "location_id", ""), getattr(region, "name", "")])
    for key in keys:
        if str(key) in location_index:
            return location_index[str(key)]
    if region is not None:
        return {
            "id": getattr(region, "location_id", slot.location_id),
            "name": getattr(region, "name", slot.location_id),
            "tags": list(getattr(region, "tags", []) or []),
        }
    return {"id": slot.location_id, "name": slot.location_id}


def _location_name(location: dict[str, Any], fallback: str) -> str:
    identity = location.get("identity") if isinstance(location.get("identity"), dict) else {}
    return str(location.get("name") or location.get("location_name") or identity.get("name") or fallback)


def _location_type(location: dict[str, Any]) -> str:
    identity = location.get("identity") if isinstance(location.get("identity"), dict) else {}
    return str(location.get("location_type") or location.get("type") or identity.get("type") or "")


def _compact_visual(value: str, max_chars: int = 100) -> str:
    return re.sub(r"\s+", " ", value).strip()[:max_chars]


def _location_visual_brief(value: str, *, max_chars: int) -> str:
    """Keep spatially useful scene details instead of truncating the opening prose."""

    text = re.sub(r"\s+", " ", value).strip()
    if not text:
        return "完整可进入场景，清晰边界、地面、核心陈设和可行走空间"

    if any(token in text for token in ("开放场景", "庭院", "公园", "广场", "码头", "车站")):
        scene = "俯视开放场景"
    elif any(token in text for token in ("剖面房间", "室内", "大厅", "库房")):
        scene = "室内无屋顶剖面"
    else:
        scene = "俯视可进入场景"

    clauses = [part.strip(" ：:，,") for part in re.split(r"[。；;\n]+", text) if part.strip()]
    clauses = [re.sub(r"^无屋顶的?(?:俯视)?(?:RPG)?(?:剖面房间|开放场景)?[，,:： ]*", "", part) for part in clauses]

    structure = clauses[0] if clauses else ""
    material = _first_matching_clause(
        clauses,
        ("主材质", "主色", "墙体", "地面", "边界"),
        fallback=False,
        keyword_priority=True,
    )
    landmarks = _extract_landmarks(clauses)

    parts = [scene]
    if structure:
        parts.append(_trim_visual_clause(structure, 42))
    material_brief = ""
    if material and material != structure:
        material_brief = _trim_visual_clause(material, 20)
    if landmarks:
        prefix = "陈设="
        material_reserve = len(material_brief) + 1 if material_brief else 0
        available = max_chars - len("；".join(parts)) - len(prefix) - material_reserve - 1
        selected: list[str] = []
        for landmark in landmarks:
            landmark = _trim_visual_clause(landmark, 13)
            candidate = "、".join([*selected, landmark])
            if len(candidate) > available:
                break
            selected.append(landmark)
        if selected:
            parts.append(prefix + "、".join(selected))
    if material_brief:
        available = max_chars - len("；".join(parts)) - 1
        if available >= 8:
            parts.append(material_brief[:available].rstrip("，、；:："))

    brief = "；".join(part for part in parts if part)
    return brief.rstrip("，、；:：")


def _first_matching_clause(
    clauses: list[str],
    keywords: tuple[str, ...],
    *,
    fallback: bool = True,
    keyword_priority: bool = False,
) -> str:
    if keyword_priority:
        for keyword in keywords:
            for clause in clauses:
                if keyword in clause:
                    return clause
    else:
        for clause in clauses:
            if any(keyword in clause for keyword in keywords):
                return clause
    return clauses[0] if fallback and clauses else ""


def _extract_landmarks(clauses: list[str]) -> list[str]:
    explicit = _first_matching_clause(
        clauses,
        ("标志性陈设", "标志物", "包括"),
        fallback=False,
        keyword_priority=True,
    )
    landmarks: list[str] = []
    if explicit:
        value = re.sub(r"^.*?(?:标志性陈设|标志物|包括)[：:， ]*", "", explicit)
        for candidate in re.split(r"[、，,]", value):
            candidate = _trim_visual_clause(candidate.strip(" ：:，,"), 18)
            if candidate and candidate not in landmarks:
                landmarks.append(candidate)

    sources = [
        clause
        for clause in clauses
        if clause != explicit
        and any(
            token in clause
            for token in (
                "中心有",
                "中央有",
                "安置",
                "排列",
                "悬吊",
                "矗立",
                "设有",
                "设一",
                "墙边设",
                "摆放",
                "配有",
                "悬挂",
                "嵌一",
                "角落",
            )
        )
    ]
    for source in sources:
        candidate = re.split(r"[，,]", source, maxsplit=1)[0]
        candidate = re.sub(
            r"^.*?(?:中心有|中央有|安置|悬吊|矗立|设有|设一|墙边设|摆放|配有|悬挂|嵌一|角落)[一组座个根条部台架面张]*",
            "",
            candidate,
        )
        candidate = _trim_visual_clause(candidate, 18)
        if candidate and candidate not in landmarks:
            landmarks.append(candidate)
        if len(landmarks) >= 4:
            return landmarks

    if len(landmarks) < 2:
        skip_tokens = ("主材质", "主色", "照明", "装饰密度", "可行走", "通道宽", "地面是", "墙体为")
        for clause in clauses[1:]:
            if any(token in clause for token in skip_tokens):
                continue
            candidate = _trim_visual_clause(re.split(r"[，,]", clause, maxsplit=1)[0], 18)
            if candidate and candidate not in landmarks:
                landmarks.append(candidate)
            if len(landmarks) >= 2:
                break
    return landmarks


def _trim_visual_clause(value: str, max_chars: int) -> str:
    value = re.sub(r"^(?:整体|平面|地面|墙体|边界|主色(?:调)?)[为是由：:， ]*", "", value)
    return value.strip()[:max_chars].rstrip("，、；:：")


def _entrance_text(port: dict[str, Any]) -> str:
    side_labels = {"north": "上边", "south": "下边", "west": "左边", "east": "右边"}
    side = str(port.get("side") or "south")
    offset = int(port.get("offset_tiles") or 0) + 1
    width = max(1, int(port.get("width_tiles") or 1))
    return f"{side_labels.get(side, '下边')}第 {offset} 格，宽 {width} 格"


def _world_context(world_background: dict[str, Any]) -> str:
    values = [
        world_background.get("world_name"),
        world_background.get("world_origin_summary"),
    ]
    return "；".join(str(value) for value in values if str(value or "").strip())


def _visual_context(profile: dict[str, Any]) -> str:
    art_style = _compact_visual(str(profile.get("art_style") or "卡通像素游戏美术"), max_chars=96)
    projection = _compact_visual(str(profile.get("camera_projection") or "严格正交俯视"), max_chars=40)
    era_style = _compact_visual(str(profile.get("era_style") or ""), max_chars=72)
    palette = profile.get("color_palette")
    materials = profile.get("material_texture")
    if isinstance(palette, list):
        palette = "、".join(str(item) for item in palette[:6])
    if isinstance(materials, list):
        materials = "、".join(str(item) for item in materials[:4])
    parts = [projection, art_style]
    if era_style:
        parts.append(era_style)
    if str(palette or "").strip():
        parts.append("主色=" + _compact_visual(str(palette), max_chars=56))
    if str(materials or "").strip():
        parts.append("材质=" + _compact_visual(str(materials), max_chars=72))
    return "；".join(parts)


def _location_record_index(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = metadata.get("locations")
    if not isinstance(records, list):
        return {}
    return {
        str(record.get("location_id")): record
        for record in records
        if isinstance(record, dict) and str(record.get("location_id") or "").strip()
    }


def _asset_version(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _image_has_size(path: Path, expected: tuple[int, int]) -> bool:
    try:
        with Image.open(path) as image:
            return image.size == expected
    except (OSError, ValueError):
        return False


def _validate_image_size(path: Path, expected: tuple[int, int], label: str) -> None:
    with Image.open(path) as image:
        actual = image.size
    if actual != expected:
        raise ValueError(f"{label} size {actual} does not match canvas {expected}")


def _as_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    return {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_progress_manifest(
    manifest: VisualLayoutManifest,
    path: str | Path | None,
) -> None:
    if path is not None:
        _write_json(Path(path), manifest.model_dump(mode="json"))
