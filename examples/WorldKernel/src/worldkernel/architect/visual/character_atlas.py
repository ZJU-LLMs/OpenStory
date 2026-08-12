from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import math
from pathlib import Path
import time
from typing import Any, Callable

from PIL import Image, ImageDraw

from worldkernel.architect.visual.client import ImageGenerationClient
from worldkernel.architect.visual.models import (
    VisualCharacterAsset,
    VisualCharacterAtlasBatch,
    VisualCharacterLayer,
    VisualLayoutManifest,
)
from worldkernel.llm.config_loader import load_model_config_by_capability


PROMPT_VERSION = "character-atlas-plain-v1"
POSTPROCESS_VERSION = "character-atlas-cutout-v11-preserve-native-alpha"
FOREGROUND_ALPHA_THRESHOLD = 128
PLAN_VERSION = 1
CHARACTER_TRANSPORT_MAX_ATTEMPTS = 2
CHARACTER_TRANSPORT_RETRY_SECONDS = 2.0
DISPLAYABLE_CHARACTER_STATUSES = {"ready", "needs_review"}

logger = logging.getLogger(__name__)


class InvalidCharacterBatchSelection(ValueError):
    """Raised before generation when a requested stable batch ID is unknown."""


@dataclass(frozen=True)
class CharacterSpec:
    character_id: str
    name: str
    visual: str


def hydrate_existing_character_layer(
    manifest: VisualLayoutManifest,
    spatial_root: str | Path,
    *,
    candidate_layers: list[Any] | None = None,
) -> dict[str, Any]:
    """Restore the most complete on-disk character layer into ``manifest``.

    Visual regeneration publishes progress through a newly built manifest.  Until
    character processing runs, that manifest contains an empty character layer.
    Keep the last usable layer available so an interrupted background/location
    regeneration cannot make already-generated character atlases disappear.
    """

    root = Path(spatial_root)
    candidates: list[tuple[str, Any]] = [("current_manifest", manifest.character_layer)]
    for index, layer in enumerate(candidate_layers or []):
        candidates.append((f"candidate_{index + 1}", layer))

    manifest_payload = _read_json(root / "visual_layout_manifest.json")
    candidates.append(("visual_layout_manifest", manifest_payload.get("character_layer")))

    blueprint_payload = _read_json(root / "spatial_blueprint.json")
    blueprint_visual = blueprint_payload.get("visual")
    if isinstance(blueprint_visual, dict):
        candidates.append(("spatial_blueprint", blueprint_visual.get("character_layer")))

    validated: list[tuple[tuple[int, int, int, int], str, VisualCharacterLayer]] = []
    for source, raw_layer in candidates:
        if raw_layer is None:
            continue
        try:
            layer = (
                raw_layer
                if isinstance(raw_layer, VisualCharacterLayer)
                else VisualCharacterLayer.model_validate(raw_layer)
            )
        except Exception:
            continue
        validated.append((_character_layer_score(layer, root), source, layer))

    if not validated:
        return {"status": "missing", "source": "none", "displayable_character_count": 0}

    score, source, best = max(validated, key=lambda item: item[0])
    current_score = _character_layer_score(manifest.character_layer, root)
    restored = score > current_score
    if restored:
        manifest.character_layer = best.model_copy(deep=True)
        manifest.provenance["character_layer_recovery"] = {
            "status": "restored",
            "source": source,
            "displayable_character_count": score[0],
            "available_atlas_count": score[1],
        }

    return {
        "status": "restored" if restored else "unchanged",
        "source": source,
        "displayable_character_count": score[0],
        "available_atlas_count": score[1],
    }


def _character_layer_score(
    layer: VisualCharacterLayer,
    root: Path,
) -> tuple[int, int, int, int]:
    available_batch_ids: set[str] = set()
    for atlas in layer.atlases:
        if atlas.status not in DISPLAYABLE_CHARACTER_STATUSES:
            continue
        candidates = [Path(atlas.path)] if atlas.path else []
        if atlas.url:
            candidates.append(root / atlas.url)
        if any(path.is_file() for path in candidates):
            available_batch_ids.add(atlas.batch_id)

    displayable_characters = sum(
        1
        for character in layer.characters
        if character.status in DISPLAYABLE_CHARACTER_STATUSES
        and character.batch_id in available_batch_ids
    )
    return (
        displayable_characters,
        len(available_batch_ids),
        len(layer.characters),
        int(layer.character_count),
    )


@dataclass(frozen=True)
class PlannedCharacterBatch:
    batch_id: str
    character_ids: tuple[str, ...]


def character_layout(character_count: int) -> dict[str, int]:
    if character_count < 1 or character_count > 6:
        raise ValueError(
            "character atlas batches must contain between 1 and 6 characters"
        )
    if character_count == 1:
        columns, rows, width, height = 1, 1, 1024, 1024
    elif character_count == 2:
        columns, rows, width, height = 2, 1, 1024, 1024
    elif character_count == 3:
        columns, rows, width, height = 3, 1, 1024, 1024
    elif character_count == 4:
        columns, rows, width, height = 2, 2, 1024, 1024
    else:
        columns, rows, width, height = 3, 2, 1536, 1024
    return {
        "columns": columns,
        "rows": rows,
        "width": width,
        "height": height,
    }


def reconcile_character_batch_plan(
    characters: list[Any],
    existing_plan: dict[str, Any] | None = None,
    *,
    max_batch_size: int = 6,
) -> tuple[list[CharacterSpec], list[str], list[PlannedCharacterBatch], dict[str, Any]]:
    if max_batch_size < 1 or max_batch_size > 6:
        raise ValueError("max_batch_size must be between 1 and 6")

    specs: list[CharacterSpec] = []
    missing_visual_ids: list[str] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(characters):
        item = _as_dict(raw)
        identity = (
            item.get("identity") if isinstance(item.get("identity"), dict) else {}
        )
        character_id = str(item.get("id") or identity.get("id") or "").strip()
        fallback_id = character_id or f"character-index-{index}"
        visual = str(item.get("visual") or "").strip()
        if not character_id or not visual or character_id in seen_ids:
            missing_visual_ids.append(fallback_id)
            continue
        seen_ids.add(character_id)
        specs.append(
            CharacterSpec(
                character_id=character_id,
                name=str(
                    item.get("name") or identity.get("name") or character_id
                ).strip(),
                visual=visual,
            )
        )

    specs.sort(key=lambda item: item.character_id)
    eligible_ids = {item.character_id for item in specs}
    plan = existing_plan if isinstance(existing_plan, dict) else {}
    reuse_existing = (
        plan.get("version") == PLAN_VERSION
        and int(plan.get("max_batch_size") or 0) == max_batch_size
    )
    next_batch_number = int(plan.get("next_batch_number") or 1) if reuse_existing else 1
    mutable_batches: list[dict[str, Any]] = []
    assigned: set[str] = set()

    if reuse_existing:
        for raw_batch in plan.get("batches") or []:
            if not isinstance(raw_batch, dict):
                continue
            batch_id = str(raw_batch.get("batch_id") or "").strip()
            if not batch_id:
                continue
            kept: list[str] = []
            for character_id in raw_batch.get("character_ids") or []:
                candidate = str(character_id)
                if candidate in eligible_ids and candidate not in assigned:
                    kept.append(candidate)
                    assigned.add(candidate)
            if kept:
                mutable_batches.append({"batch_id": batch_id, "character_ids": kept})

    for spec in specs:
        if spec.character_id in assigned:
            continue
        target = next(
            (
                batch
                for batch in mutable_batches
                if len(batch["character_ids"]) < max_batch_size
            ),
            None,
        )
        if target is None:
            existing_ids = {str(batch["batch_id"]) for batch in mutable_batches}
            while f"batch-{next_batch_number:03d}" in existing_ids:
                next_batch_number += 1
            target = {
                "batch_id": f"batch-{next_batch_number:03d}",
                "character_ids": [],
            }
            next_batch_number += 1
            mutable_batches.append(target)
        target["character_ids"].append(spec.character_id)
        assigned.add(spec.character_id)

    planned_batches = [
        PlannedCharacterBatch(
            batch_id=str(batch["batch_id"]),
            character_ids=tuple(str(value) for value in batch["character_ids"]),
        )
        for batch in mutable_batches
        if batch["character_ids"]
    ]
    persisted = {
        "version": PLAN_VERSION,
        "max_batch_size": max_batch_size,
        "next_batch_number": next_batch_number,
        "batches": [
            {"batch_id": batch.batch_id, "character_ids": list(batch.character_ids)}
            for batch in planned_batches
        ],
    }
    return specs, missing_visual_ids, planned_batches, persisted


def validate_character_batch_selection(
    *,
    semantic_characters: list[Any],
    character_root: str | Path,
    max_batch_size: int,
    force_batch_ids: list[str] | None,
) -> None:
    requested = {str(value) for value in force_batch_ids or []}
    if not requested:
        return
    plan_path = Path(character_root) / "character_batch_plan.json"
    _, _, batches, _ = reconcile_character_batch_plan(
        semantic_characters,
        _read_json(plan_path),
        max_batch_size=max_batch_size,
    )
    known = {batch.batch_id for batch in batches}
    unknown = sorted(requested - known)
    if unknown:
        raise InvalidCharacterBatchSelection(
            "Unknown character batch ID(s): " + ", ".join(unknown)
        )


def run_character_atlas_pipeline(
    *,
    manifest: VisualLayoutManifest,
    semantic_characters: list[Any],
    root: str | Path,
    model_config_path: str | Path,
    generate: bool,
    max_batch_size: int = 6,
    key_colors: list[str] | None = None,
    transparent_threshold: int = 24,
    opaque_threshold: int = 96,
    force_batch_ids: list[str] | None = None,
    progress_manifest_path: str | Path | None = None,
    client_factory: Callable[
        [dict[str, Any]], ImageGenerationClient
    ] = ImageGenerationClient,
) -> dict[str, Any]:
    output_root = Path(root)
    character_root = output_root / "characters"
    character_root.mkdir(parents=True, exist_ok=True)
    plan_path = character_root / "character_batch_plan.json"
    previous_plan = _read_json(plan_path)
    specs, missing_visual_ids, batches, persisted_plan = reconcile_character_batch_plan(
        semantic_characters,
        previous_plan,
        max_batch_size=max_batch_size,
    )
    _write_json(plan_path, persisted_plan)

    requested_force = {str(value) for value in force_batch_ids or []}
    known_batch_ids = {batch.batch_id for batch in batches}
    unknown = sorted(requested_force - known_batch_ids)
    if unknown:
        raise InvalidCharacterBatchSelection(
            "Unknown character batch ID(s): " + ", ".join(unknown)
        )

    if not batches:
        manifest.character_layer = _compose_character_layer(
            character_count=len(semantic_characters),
            eligible_count=len(specs),
            missing_visual_ids=missing_visual_ids,
            max_batch_size=max_batch_size,
            provider="",
            model="",
            estimated_calls=0,
            generated_count=0,
            reused_count=0,
            planned_batch_count=0,
            atlas_models=[],
            character_models=[],
        )
        if progress_manifest_path is not None:
            _write_json(
                Path(progress_manifest_path),
                manifest.model_dump(mode="json"),
            )
        return manifest.character_layer.model_dump(mode="json")

    model_config_path = Path(model_config_path)
    model_config = load_model_config_by_capability(
        model_config_path, "image_generation"
    )
    provider = str(model_config.get("name") or "")
    model = str(model_config.get("model") or "")
    style_signature, palette_hint = _style_reference_context(
        model_config,
        model_config_path,
    )
    candidates = _validated_key_colors(key_colors)
    spec_by_id = {item.character_id: item for item in specs}
    batch_contexts: list[dict[str, Any]] = []
    for batch in batches:
        batch_specs = [spec_by_id[character_id] for character_id in batch.character_ids]
        layout = character_layout(len(batch_specs))
        key_color = _choose_key_color(batch_specs, candidates)
        prompt = compose_character_atlas_prompt(
            batch_specs,
            layout=layout,
            key_color=key_color,
            palette_hint=palette_hint,
        )
        signature = _batch_signature(
            batch_specs,
            layout=layout,
            key_color=key_color,
            provider=provider,
            model=model,
            style_signature=style_signature,
        )
        batch_dir = character_root / batch.batch_id
        metadata_path = batch_dir / "metadata.json"
        output_path = batch_dir / "atlas.png"
        metadata = _read_json(metadata_path)
        cached_batch = metadata.get("batch")
        cached_status = (
            str(cached_batch.get("status") or "")
            if isinstance(cached_batch, dict)
            else ""
        )
        cached_error = str(
            metadata.get("error")
            or (
                cached_batch.get("error")
                if isinstance(cached_batch, dict)
                else ""
            )
            or ""
        )
        retryable_cached_failure = (
            cached_status == "failed" and _is_transient_image_error(cached_error)
        )
        cache_matches = (
            metadata.get("signature") == signature
            and isinstance(metadata.get("batch"), dict)
            and isinstance(metadata.get("characters"), list)
            and (
                output_path.is_file()
                or str(metadata.get("batch", {}).get("status"))
                in {"failed", "needs_review"}
            )
            and not retryable_cached_failure
        )
        batch_contexts.append(
            {
                "batch": batch,
                "specs": batch_specs,
                "layout": layout,
                "key_color": key_color,
                "prompt": prompt,
                "signature": signature,
                "batch_dir": batch_dir,
                "metadata_path": metadata_path,
                "output_path": output_path,
                "metadata": metadata,
                "cache_matches": cache_matches,
                "must_generate": batch.batch_id in requested_force or not cache_matches,
            }
        )

    estimated_calls = sum(1 for item in batch_contexts if item["must_generate"])
    atlas_models: list[VisualCharacterAtlasBatch] = []
    character_models: list[VisualCharacterAsset] = []
    generated_count = 0
    reused_count = 0
    client: ImageGenerationClient | None = None

    def publish_progress() -> None:
        manifest.character_layer = _compose_character_layer(
            character_count=len(semantic_characters),
            eligible_count=len(specs),
            missing_visual_ids=missing_visual_ids,
            max_batch_size=max_batch_size,
            provider=provider,
            model=model,
            estimated_calls=estimated_calls,
            generated_count=generated_count,
            reused_count=reused_count,
            planned_batch_count=len(batches),
            atlas_models=atlas_models,
            character_models=character_models,
        )
        if progress_manifest_path is not None:
            _write_json(
                Path(progress_manifest_path),
                manifest.model_dump(mode="json"),
            )

    publish_progress()
    for context in batch_contexts:
        if context["cache_matches"] and not context["must_generate"]:
            metadata = context["metadata"]
            raw_path = context["batch_dir"] / "atlas_raw.png"
            preview_path = context["batch_dir"] / "review_preview.png"
            if metadata.get("postprocess_version") != POSTPROCESS_VERSION and raw_path.is_file():
                processed = postprocess_character_atlas(
                    raw_path=raw_path,
                    output_path=context["output_path"],
                    preview_path=preview_path,
                    characters=context["specs"],
                    layout=context["layout"],
                    key_color=context["key_color"],
                    transparent_threshold=transparent_threshold,
                    opaque_threshold=opaque_threshold,
                )
                for item in processed["characters"]:
                    item["batch_id"] = context["batch"].batch_id
                batch_payload = dict(metadata.get("batch") or {})
                batch_payload.update(
                    {
                        "status": processed["status"],
                        "size": _postprocessed_output_size(
                            processed,
                            context["output_path"],
                            fallback=batch_payload.get("size", {}),
                        ),
                        "asset_version": _asset_version(context["output_path"]),
                        "error": processed.get("error", ""),
                    }
                )
                metadata.update(
                    {
                        "batch": batch_payload,
                        "characters": processed["characters"],
                        "postprocess_version": POSTPROCESS_VERSION,
                        "postprocessing": processed["report"],
                        "error": processed.get("error", ""),
                    }
                )
                _write_json(context["metadata_path"], metadata)
            cached_batch, cached_characters = _load_cached_models(metadata)
            atlas_models.append(cached_batch)
            character_models.extend(cached_characters)
            reused_count += 1
            publish_progress()
            continue

        if not generate:
            pending_batch, pending_characters = _pending_models(
                context,
                provider=provider,
                model=model,
            )
            atlas_models.append(pending_batch)
            character_models.extend(pending_characters)
            publish_progress()
            continue

        if client is None:
            client = client_factory(model_config)
        generated_count += 1
        context["batch_dir"].mkdir(parents=True, exist_ok=True)
        prompt_path = context["batch_dir"] / "prompt.json"
        raw_path = context["batch_dir"] / "atlas_raw.png"
        preview_path = context["batch_dir"] / "review_preview.png"
        _write_json(
            prompt_path,
            {
                "prompt_version": PROMPT_VERSION,
                "batch_id": context["batch"].batch_id,
                "layout": context["layout"],
                "key_color": context["key_color"],
                "character_ids": list(context["batch"].character_ids),
                "prompt": context["prompt"],
                "negative_prompt": _negative_prompt(context["key_color"]),
            },
        )
        try:
            generation_metadata = _generate_character_atlas_candidate(
                client=client,
                prompt=context["prompt"],
                output_path=raw_path,
                negative_prompt=_negative_prompt(context["key_color"]),
            )
            processed = postprocess_character_atlas(
                raw_path=raw_path,
                output_path=context["output_path"],
                preview_path=preview_path,
                characters=context["specs"],
                layout=context["layout"],
                key_color=context["key_color"],
                transparent_threshold=transparent_threshold,
                opaque_threshold=opaque_threshold,
            )
            for item in processed["characters"]:
                item["batch_id"] = context["batch"].batch_id
            batch_model = VisualCharacterAtlasBatch(
                batch_id=context["batch"].batch_id,
                status=processed["status"],
                character_count=len(context["specs"]),
                layout={
                    "columns": context["layout"]["columns"],
                    "rows": context["layout"]["rows"],
                },
                size={
                    **_postprocessed_output_size(
                        processed,
                        context["output_path"],
                        fallback={
                            "width": context["layout"]["width"],
                            "height": context["layout"]["height"],
                        },
                    ),
                },
                path=str(context["output_path"]),
                url=f"characters/{context['batch'].batch_id}/atlas.png",
                prompt_path=str(prompt_path),
                metadata_path=str(context["metadata_path"]),
                preview_path=str(preview_path),
                provider=provider,
                model=model,
                asset_version=_asset_version(context["output_path"]),
                signature=context["signature"],
                key_color=context["key_color"],
                error=processed.get("error", ""),
            )
            batch_characters = [
                VisualCharacterAsset.model_validate(item)
                for item in processed["characters"]
            ]
            safe_generation_metadata = {
                key: value
                for key, value in generation_metadata.items()
                if key != "raw_result"
            }
            _write_json(
                context["metadata_path"],
                {
                    "signature": context["signature"],
                    "batch": batch_model.model_dump(mode="json"),
                    "characters": [
                        item.model_dump(mode="json") for item in batch_characters
                    ],
                    "generation": safe_generation_metadata,
                    "postprocess_version": POSTPROCESS_VERSION,
                    "postprocessing": processed["report"],
                },
            )
        except Exception as exc:
            error = str(exc) or type(exc).__name__
            batch_model, batch_characters = _failed_models(
                context,
                provider=provider,
                model=model,
                error=error,
            )
            _write_json(
                context["metadata_path"],
                {
                    "signature": context["signature"],
                    "batch": batch_model.model_dump(mode="json"),
                    "characters": [
                        item.model_dump(mode="json") for item in batch_characters
                    ],
                    "error": error,
                },
            )
        atlas_models.append(batch_model)
        character_models.extend(batch_characters)
        publish_progress()

    publish_progress()
    return manifest.character_layer.model_dump(mode="json")


def _generate_character_atlas_candidate(
    *,
    client: ImageGenerationClient,
    prompt: str,
    output_path: Path,
    negative_prompt: str,
) -> dict[str, Any]:
    """Generate one atlas, retrying the same request once on transport errors."""
    failures: list[str] = []
    for transport_attempt in range(1, CHARACTER_TRANSPORT_MAX_ATTEMPTS + 1):
        try:
            metadata = client.generate(
                prompt,
                output_path,
                negative_prompt=negative_prompt,
            )
            return {
                **metadata,
                "transport_attempt_count": transport_attempt,
                "transport_failures": list(failures),
            }
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            failures.append(message)
            if (
                transport_attempt >= CHARACTER_TRANSPORT_MAX_ATTEMPTS
                or not _is_transient_image_error(message)
            ):
                raise
            logger.warning(
                "Transient character atlas image error on attempt %s/%s: %s",
                transport_attempt,
                CHARACTER_TRANSPORT_MAX_ATTEMPTS,
                message,
            )
            time.sleep(CHARACTER_TRANSPORT_RETRY_SECONDS)
    raise RuntimeError("Character atlas generation exhausted transport attempts")


def _is_transient_image_error(message: str) -> bool:
    text = message.lower()
    return any(
        token in text
        for token in (
            "http 400",
            "http 429",
            "http 502",
            "http 503",
            "http 504",
            "timed out",
            "timeout",
            "connection error",
            "connection refused",
            "connection reset",
            "connection aborted",
            "could not connect",
            "unable to connect",
            "network is unreachable",
            "name resolution",
            "remote end closed",
            "temporarily unavailable",
            "temporary failure",
            "winerror 10060",
            "winerror 10061",
        )
    )


def compose_character_atlas_prompt(
    characters: list[CharacterSpec],
    *,
    layout: dict[str, int],
    key_color: str,
    palette_hint: str = "",
) -> str:
    ordered = []
    for index, character in enumerate(characters, start=1):
        row = (index - 1) // layout["columns"] + 1
        column = (index - 1) % layout["columns"] + 1
        ordered.append(
            f"槽位 {index}（第 {row} 行第 {column} 列）：{character.name}。{character.visual}"
        )
    palette_line = f"\n参考色板提示：{palette_hint}" if palette_hint else ""
    return (
        "生成一张供 2D RPG 前端使用的像素角色全身图集。"
        f"图集中必须恰好有 {len(characters)} 个人物，采用严格的 "
        f"{layout['columns']} 列 × {layout['rows']} 行等分网格，"
        "人物顺序必须从左到右、从上到下与下列槽位完全一致。\n"
        f"每个槽位背景必须是完全均匀的纯色 {key_color}，槽位之间保留同色分隔带。"
        f"人物服装、头发、道具中禁止使用颜色 {key_color}。"
        "每格只画一个人物：完整正面全身，从头顶到鞋底全部可见，双脚靠近同一基线，"
        "居中站立，人物之间采用一致的像素比例、轮廓密度、光照和清晰硬边。"
        "画面必须是精细但低纹理的像素游戏角色素材，不画场景、地面、阴影、文字、编号、"
        "边框、水印、额外人物或身体局部特写，任何人物和随身物品都不得跨越槽位。"
        f"{palette_line}\n\n角色槽位：\n" + "\n".join(ordered)
    )


def postprocess_character_atlas(
    *,
    raw_path: str | Path,
    output_path: str | Path,
    preview_path: str | Path,
    characters: list[CharacterSpec],
    layout: dict[str, int],
    key_color: str,
    transparent_threshold: int,
    opaque_threshold: int,
) -> dict[str, Any]:
    expected_size = (layout["width"], layout["height"])
    with Image.open(raw_path) as opened:
        # Some providers already return a transparent PNG. Keep its alpha;
        # converting to RGB turns transparent pixels black and makes the whole
        # canvas look like foreground during chroma-key postprocessing.
        source = opened.convert("RGBA")
    original_size = source.size
    size_adjusted = source.size != expected_size
    aspect_ratio_changed = (
        size_adjusted
        and abs(
            (source.width / max(1, source.height))
            - (expected_size[0] / max(1, expected_size[1]))
        ) > 0.01
    )
    key_rgb = _parse_hex_color(key_color)
    x_bounds = _detect_axis_boundaries(
        source,
        divisions=layout["columns"],
        axis="x",
        key_rgb=key_rgb,
        threshold=max(transparent_threshold, 24),
    )
    y_bounds = _detect_axis_boundaries(
        source,
        divisions=layout["rows"],
        axis="y",
        key_rgb=key_rgb,
        threshold=max(transparent_threshold, 24),
    )
    # The provider may return a different physical size or aspect ratio than
    # requested. Preserve those pixels exactly: forcing the response into the
    # requested canvas distorts character proportions.
    output_size = source.size
    transparent_atlas = Image.new("RGBA", output_size, (0, 0, 0, 0))
    character_records: list[dict[str, Any]] = []
    batch_needs_review = False
    report_rows: list[dict[str, Any]] = []

    for index, character in enumerate(characters):
        row = index // layout["columns"]
        column = index % layout["columns"]
        left, right = x_bounds[column], x_bounds[column + 1]
        top, bottom = y_bounds[row], y_bounds[row + 1]
        cell = source.crop((left, top, right, bottom))
        rgba = _remove_key_color(
            cell,
            key_rgb=key_rgb,
            transparent_threshold=transparent_threshold,
            opaque_threshold=opaque_threshold,
        )
        rgba = _remove_edge_connected_light_frame(rgba)
        rgba = _retain_character_components(rgba)
        transparent_atlas.alpha_composite(rgba, (left, top))
        alpha = rgba.getchannel("A")
        bbox = alpha.getbbox()
        status = "ready"
        issues: list[str] = []
        if bbox is None:
            status = "failed"
            issues.append("empty_slot")
            bbox = (0, 0, max(1, cell.width), max(1, cell.height))
        else:
            foreground_pixels = sum(
                1 for value in alpha.getdata() if value >= FOREGROUND_ALPHA_THRESHOLD
            )
            coverage = foreground_pixels / max(1, cell.width * cell.height)
            margin_x = max(2, int(cell.width * 0.015))
            margin_y = max(2, int(cell.height * 0.015))
            touches_edge = (
                bbox[0] <= margin_x
                or bbox[1] <= margin_y
                or bbox[2] >= cell.width - margin_x
                or bbox[3] >= cell.height - margin_y
            )
            if coverage < 0.025:
                status = "failed"
                issues.append("foreground_too_small")
            elif coverage > 0.72:
                status = "needs_review"
                issues.append("foreground_too_large")
            if touches_edge and status != "failed":
                # Touching a cell boundary is useful review information, but it
                # does not make an otherwise complete transparent cutout unusable.
                issues.append("foreground_touches_slot_edge")
            if _major_component_count(alpha) > 1 and status != "failed":
                # A complete character can legitimately contain detached props,
                # hair strands, a cane, or a shoulder bag. Keep the diagnostic
                # without downgrading an otherwise usable cutout.
                issues.append("multiple_major_components")
        if size_adjusted:
            issues.append("model_output_size_differs")

        pad_x = max(2, int(cell.width * 0.015))
        pad_y = max(2, int(cell.height * 0.015))
        content_local = (
            max(0, bbox[0] - pad_x),
            max(0, bbox[1] - pad_y),
            min(cell.width, bbox[2] + pad_x),
            min(cell.height, bbox[3] + pad_y),
        )
        content_global = {
            "x": left + content_local[0],
            "y": top + content_local[1],
            "w": max(1, content_local[2] - content_local[0]),
            "h": max(1, content_local[3] - content_local[1]),
        }
        portrait_height = max(1, int(content_global["h"] * 0.46))
        character_records.append(
            {
                "character_id": character.character_id,
                "name": character.name,
                "batch_id": "",
                "slot_index": index,
                "status": status,
                "source_rect": {
                    "x": left,
                    "y": top,
                    "w": right - left,
                    "h": bottom - top,
                },
                "content_rect": content_global,
                "portrait_rect": {
                    "x": content_global["x"],
                    "y": content_global["y"],
                    "w": content_global["w"],
                    "h": portrait_height,
                },
                "error": ", ".join(issues) if status != "ready" else "",
            }
        )
        report_rows.append(
            {
                "character_id": character.character_id,
                "status": status,
                "issues": issues,
                "source_rect": character_records[-1]["source_rect"],
                "content_rect": content_global,
            }
        )
        batch_needs_review = batch_needs_review or status == "needs_review"

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    transparent_atlas.save(output, format="PNG")
    _render_review_preview(
        transparent_atlas,
        Path(preview_path),
        characters,
        character_records,
    )
    failed = any(item["status"] == "failed" for item in character_records)
    status = "failed" if failed else "needs_review" if batch_needs_review else "ready"
    return {
        "status": status,
        "characters": character_records,
        "error": "one or more character slots failed" if failed else "",
        "report": {
            "status": status,
            "expected_size": {"width": expected_size[0], "height": expected_size[1]},
            "source_size": {"width": original_size[0], "height": original_size[1]},
            "output_size": {"width": output_size[0], "height": output_size[1]},
            "size_adjusted": size_adjusted,
            "aspect_ratio_changed": aspect_ratio_changed,
            "x_boundaries": x_bounds,
            "y_boundaries": y_bounds,
            "characters": report_rows,
        },
    }


def _postprocessed_output_size(
    processed: dict[str, Any],
    output_path: Path,
    *,
    fallback: dict[str, Any],
) -> dict[str, int]:
    reported = processed.get("report", {}).get("output_size", {})
    if int(reported.get("width") or 0) > 0 and int(reported.get("height") or 0) > 0:
        return {
            "width": int(reported["width"]),
            "height": int(reported["height"]),
        }
    if output_path.is_file():
        with Image.open(output_path) as image:
            return {"width": image.width, "height": image.height}
    return {
        "width": int(fallback.get("width") or 0),
        "height": int(fallback.get("height") or 0),
    }


def _compose_character_layer(
    *,
    character_count: int,
    eligible_count: int,
    missing_visual_ids: list[str],
    max_batch_size: int,
    provider: str,
    model: str,
    estimated_calls: int,
    generated_count: int,
    reused_count: int,
    planned_batch_count: int,
    atlas_models: list[VisualCharacterAtlasBatch],
    character_models: list[VisualCharacterAsset],
) -> VisualCharacterLayer:
    failed = [item.character_id for item in character_models if item.status == "failed"]
    review = [
        item.character_id for item in character_models if item.status == "needs_review"
    ]
    pending = [item for item in character_models if item.status == "pending"]
    if eligible_count == 0:
        status = "ready" if not missing_visual_ids else "partial"
    elif len(atlas_models) < planned_batch_count or pending:
        status = "partial"
    elif failed and len(failed) == eligible_count:
        status = "failed"
    elif failed or review or missing_visual_ids:
        status = "partial"
    else:
        status = "ready"
    return VisualCharacterLayer(
        status=status,
        provider=provider,
        model=model,
        max_batch_size=max_batch_size,
        character_count=character_count,
        eligible_character_count=eligible_count,
        planned_batch_count=planned_batch_count,
        generated_batch_count=generated_count,
        reused_batch_count=reused_count,
        estimated_image_calls=estimated_calls,
        atlases=list(atlas_models),
        characters=list(character_models),
        missing_visual_ids=list(missing_visual_ids),
        failed_character_ids=failed,
        needs_review_character_ids=review,
    )


def _pending_models(
    context: dict[str, Any],
    *,
    provider: str,
    model: str,
) -> tuple[VisualCharacterAtlasBatch, list[VisualCharacterAsset]]:
    layout = context["layout"]
    batch_id = context["batch"].batch_id
    return (
        VisualCharacterAtlasBatch(
            batch_id=batch_id,
            status="pending",
            character_count=len(context["specs"]),
            layout={"columns": layout["columns"], "rows": layout["rows"]},
            size={"width": layout["width"], "height": layout["height"]},
            provider=provider,
            model=model,
            signature=context["signature"],
            key_color=context["key_color"],
        ),
        [
            VisualCharacterAsset(
                character_id=item.character_id,
                name=item.name,
                batch_id=batch_id,
                slot_index=index,
                status="pending",
            )
            for index, item in enumerate(context["specs"])
        ],
    )


def _failed_models(
    context: dict[str, Any],
    *,
    provider: str,
    model: str,
    error: str,
) -> tuple[VisualCharacterAtlasBatch, list[VisualCharacterAsset]]:
    batch, characters = _pending_models(context, provider=provider, model=model)
    batch.status = "failed"
    batch.error = error
    batch.path = str(context["output_path"])
    batch.url = f"characters/{context['batch'].batch_id}/atlas.png"
    batch.prompt_path = str(context["batch_dir"] / "prompt.json")
    batch.metadata_path = str(context["metadata_path"])
    for character in characters:
        character.status = "failed"
        character.error = error
    return batch, characters


def _load_cached_models(
    metadata: dict[str, Any],
) -> tuple[VisualCharacterAtlasBatch, list[VisualCharacterAsset]]:
    batch = VisualCharacterAtlasBatch.model_validate(metadata["batch"])
    characters = [
        VisualCharacterAsset.model_validate(item)
        for item in metadata.get("characters") or []
    ]
    return batch, characters


def _batch_signature(
    characters: list[CharacterSpec],
    *,
    layout: dict[str, int],
    key_color: str,
    provider: str,
    model: str,
    style_signature: str,
) -> str:
    payload = {
        "prompt_version": PROMPT_VERSION,
        "provider": provider,
        "model": model,
        "style_signature": style_signature,
        "layout": layout,
        "key_color": key_color,
        "characters": [
            {"id": item.character_id, "name": item.name, "visual": item.visual}
            for item in characters
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _style_reference_context(
    model_config: dict[str, Any],
    model_config_path: Path,
) -> tuple[str, str]:
    configured = str(model_config.get("style_reference_path") or "").strip()
    if not configured:
        return "", ""
    path = Path(configured)
    if not path.is_absolute():
        path = model_config_path.parent.parent / path
    if not path.is_file():
        return "missing", ""
    signature = _asset_version(path)
    try:
        with Image.open(path) as image:
            sample = image.convert("RGB")
            sample.thumbnail((64, 64), Image.Resampling.NEAREST)
            colors = sample.quantize(colors=6, method=Image.Quantize.MEDIANCUT).convert(
                "RGB"
            )
            counts = colors.getcolors(maxcolors=64 * 64) or []
        palette = [
            "#%02x%02x%02x" % color for _, color in sorted(counts, reverse=True)[:6]
        ]
        return signature, "、".join(palette)
    except Exception:
        return signature, ""


def _choose_key_color(
    characters: list[CharacterSpec],
    candidates: list[str],
) -> str:
    combined = " ".join(item.visual.lower() for item in characters)
    conflict_tokens = {
        "#00ff00": ("绿色", "翠绿", "墨绿", "green", "emerald", "lime"),
        "#ff00ff": ("紫红", "品红", "洋红", "magenta", "fuchsia"),
        "#00ffff": ("青色", "蓝绿", "cyan", "turquoise", "aqua"),
    }
    return min(
        candidates,
        key=lambda color: sum(
            combined.count(token) for token in conflict_tokens.get(color.lower(), ())
        ),
    )


def _validated_key_colors(values: list[str] | None) -> list[str]:
    candidates = values or ["#00ff00", "#ff00ff", "#00ffff"]
    valid: list[str] = []
    for value in candidates:
        normalized = str(value).strip().lower()
        _parse_hex_color(normalized)
        valid.append(normalized)
    if not valid:
        raise ValueError("At least one character key color is required")
    return valid


def _negative_prompt(key_color: str) -> str:
    return (
        "额外人物，多人同格，缺失人物，半身像，侧身，背面，裁掉头部，裁掉脚部，"
        "跨格，场景，地面，投影，文字，数字，标签，水印，渐变背景，纹理背景，"
        f"人物服饰或道具使用键控色 {key_color}"
    )


def _detect_axis_boundaries(
    image: Image.Image,
    *,
    divisions: int,
    axis: str,
    key_rgb: tuple[int, int, int],
    threshold: int,
) -> list[int]:
    if divisions <= 1:
        return [0, image.width if axis == "x" else image.height]
    rgba = image.convert("RGBA")
    extent = rgba.width if axis == "x" else rgba.height
    cross_extent = rgba.height if axis == "x" else rgba.width
    pixels = rgba.load()
    boundaries = [0]
    for division in range(1, divisions):
        expected = round(extent * division / divisions)
        window = max(3, round(extent * 0.025))
        best_position = expected
        best_score = -1.0
        for position in range(
            max(1, expected - window), min(extent - 1, expected + window + 1)
        ):
            matches = 0
            samples = 0
            step = max(1, cross_extent // 192)
            for cross in range(0, cross_extent, step):
                color = (
                    pixels[position, cross] if axis == "x" else pixels[cross, position]
                )
                samples += 1
                if color[3] < FOREGROUND_ALPHA_THRESHOLD or _color_distance(
                    color[:3], key_rgb
                ) <= threshold:
                    matches += 1
            key_ratio = matches / max(1, samples)
            closeness_penalty = abs(position - expected) / max(1, window) * 0.08
            score = key_ratio - closeness_penalty
            if score > best_score:
                best_score = score
                best_position = position
        boundaries.append(best_position)
    boundaries.append(extent)
    return boundaries


def _remove_key_color(
    image: Image.Image,
    *,
    key_rgb: tuple[int, int, int],
    transparent_threshold: int,
    opaque_threshold: int,
) -> Image.Image:
    """Remove a generated chroma-key background without retaining color haze.

    Image models rarely emit a perfectly flat key color.  The old soft alpha
    ramp left nearly-key pixels at alpha values such as 8-20; ``getbbox`` then
    treated the entire atlas cell as foreground.  Character art is intended to
    be pixel art, so use a stable binary cutout and reconstruct partially mixed
    edge colors before making them opaque.
    """
    rgba = image.convert("RGBA")
    source = rgba.tobytes()
    output = bytearray(rgba.width * rgba.height * 4)
    out_index = 0
    for index in range(0, len(source), 4):
        red, green, blue, native_alpha = source[index : index + 4]
        distance_squared = (
            (red - key_rgb[0]) ** 2
            + (green - key_rgb[1]) ** 2
            + (blue - key_rgb[2]) ** 2
        )
        if distance_squared <= transparent_threshold**2:
            soft_alpha = 0
        elif distance_squared >= opaque_threshold**2:
            soft_alpha = 255
        else:
            distance = math.sqrt(distance_squared)
            soft_alpha = round(
                255
                * (distance - transparent_threshold)
                / max(1, opaque_threshold - transparent_threshold)
            )

        combined_alpha = min(native_alpha, soft_alpha)
        if native_alpha == 0 or soft_alpha < FOREGROUND_ALPHA_THRESHOLD:
            output[out_index : out_index + 4] = b"\x00\x00\x00\x00"
        else:
            if soft_alpha < 255:
                fraction = soft_alpha / 255
                channels = (red, green, blue)
                cleaned = tuple(
                    max(
                        0,
                        min(
                            255,
                            round(
                                (channel - (1 - fraction) * key_channel) / fraction
                            ),
                        ),
                    )
                    for channel, key_channel in zip(channels, key_rgb)
                )
            else:
                cleaned = (red, green, blue)
            output[out_index : out_index + 4] = bytes((*cleaned, combined_alpha))
        out_index += 4
    return Image.frombytes("RGBA", rgba.size, bytes(output))


def _retain_character_components(image: Image.Image) -> Image.Image:
    """Discard atlas dividers and isolated keying debris from a cutout cell."""
    rgba = image.convert("RGBA")
    width, height = rgba.size
    original_alpha = rgba.getchannel("A").tobytes()
    remaining = bytearray(original_alpha)
    components: list[tuple[list[int], tuple[int, int, int, int]]] = []

    for start, value in enumerate(remaining):
        if value == 0:
            continue
        remaining[start] = 0
        stack = [start]
        pixels: list[int] = []
        min_x = max_x = start % width
        min_y = max_y = start // width
        while stack:
            index = stack.pop()
            pixels.append(index)
            x = index % width
            y = index // width
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            if x > 0:
                neighbor = index - 1
                if remaining[neighbor]:
                    remaining[neighbor] = 0
                    stack.append(neighbor)
            if x + 1 < width:
                neighbor = index + 1
                if remaining[neighbor]:
                    remaining[neighbor] = 0
                    stack.append(neighbor)
            if y > 0:
                neighbor = index - width
                if remaining[neighbor]:
                    remaining[neighbor] = 0
                    stack.append(neighbor)
            if y + 1 < height:
                neighbor = index + width
                if remaining[neighbor]:
                    remaining[neighbor] = 0
                    stack.append(neighbor)
        components.append((pixels, (min_x, min_y, max_x + 1, max_y + 1)))

    if len(components) <= 1:
        return rgba

    largest = max(len(pixels) for pixels, _ in components)
    minimum_size = max(8, round(largest * 0.004))
    retained_alpha = bytearray(width * height)
    for pixels, bbox in components:
        component_width = bbox[2] - bbox[0]
        component_height = bbox[3] - bbox[1]
        touches_border = (
            bbox[0] == 0 or bbox[1] == 0 or bbox[2] == width or bbox[3] == height
        )
        divider_like = (
            component_width >= width * 0.78 and component_height <= height * 0.06
        ) or (
            component_height >= height * 0.78 and component_width <= width * 0.06
        )
        insignificant_border_debris = touches_border and len(pixels) < largest * 0.1
        if (
            len(pixels) < minimum_size
            or divider_like
            or insignificant_border_debris
        ):
            continue
        for index in pixels:
            retained_alpha[index] = original_alpha[index]

    cleaned = rgba.copy()
    cleaned.putalpha(Image.frombytes("L", rgba.size, bytes(retained_alpha)))
    return cleaned


def _remove_edge_connected_light_frame(image: Image.Image) -> Image.Image:
    """Remove near-white slot frames without erasing detached character props."""

    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width <= 0 or height <= 0:
        return rgba

    pixels = rgba.load()
    alpha = bytearray(rgba.getchannel("A").tobytes())
    visited = bytearray(width * height)
    stack: list[int] = []

    def is_frame_pixel(index: int) -> bool:
        if alpha[index] == 0:
            return False
        x = index % width
        y = index // width
        red, green, blue, _ = pixels[x, y]
        return min(red, green, blue) >= 220 and max(red, green, blue) - min(
            red, green, blue
        ) <= 36

    edge_indices = [
        *(x for x in range(width)),
        *((height - 1) * width + x for x in range(width)),
        *(y * width for y in range(1, height - 1)),
        *(y * width + width - 1 for y in range(1, height - 1)),
    ]
    for index in edge_indices:
        if not visited[index] and is_frame_pixel(index):
            visited[index] = 1
            stack.append(index)

    while stack:
        index = stack.pop()
        alpha[index] = 0
        x = index % width
        y = index // width
        neighbors = []
        if x > 0:
            neighbors.append(index - 1)
        if x + 1 < width:
            neighbors.append(index + 1)
        if y > 0:
            neighbors.append(index - width)
        if y + 1 < height:
            neighbors.append(index + width)
        for neighbor in neighbors:
            if not visited[neighbor] and is_frame_pixel(neighbor):
                visited[neighbor] = 1
                stack.append(neighbor)

    cleaned = rgba.copy()
    cleaned.putalpha(Image.frombytes("L", rgba.size, bytes(alpha)))
    return cleaned


def _major_component_count(alpha: Image.Image) -> int:
    sample = alpha.copy()
    sample.thumbnail((96, 96), Image.Resampling.NEAREST)
    width, height = sample.size
    pixels = sample.load()
    foreground = {
        (x, y) for y in range(height) for x in range(width) if pixels[x, y] >= 128
    }
    if not foreground:
        return 0
    minimum_size = max(4, int(len(foreground) * 0.08))
    major = 0
    while foreground:
        start = foreground.pop()
        stack = [start]
        size = 0
        while stack:
            x, y = stack.pop()
            size += 1
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in foreground:
                    foreground.remove(neighbor)
                    stack.append(neighbor)
        if size >= minimum_size:
            major += 1
    return major


def _render_review_preview(
    atlas: Image.Image,
    output_path: Path,
    characters: list[CharacterSpec],
    records: list[dict[str, Any]],
) -> None:
    checker = Image.new("RGBA", atlas.size, (238, 238, 238, 255))
    draw = ImageDraw.Draw(checker)
    block = 16
    for y in range(0, checker.height, block):
        for x in range(0, checker.width, block):
            if (x // block + y // block) % 2:
                draw.rectangle(
                    (x, y, x + block - 1, y + block - 1), fill=(205, 205, 205, 255)
                )
    checker.alpha_composite(atlas)
    draw = ImageDraw.Draw(checker)
    for index, (character, record) in enumerate(
        zip(characters, records, strict=True), start=1
    ):
        rect = record["source_rect"]
        color = (
            (30, 180, 90, 255) if record["status"] == "ready" else (230, 150, 30, 255)
        )
        draw.rectangle(
            (
                rect["x"],
                rect["y"],
                rect["x"] + rect["w"] - 1,
                rect["y"] + rect["h"] - 1,
            ),
            outline=color,
            width=3,
        )
        label = f"{index}: {character.name} [{record['status']}]"
        try:
            draw.text(
                (rect["x"] + 6, rect["y"] + 6),
                label,
                fill=(20, 20, 20, 255),
                stroke_width=2,
                stroke_fill=(255, 255, 255, 255),
            )
        except UnicodeEncodeError:
            draw.text(
                (rect["x"] + 6, rect["y"] + 6),
                f"slot {index} [{record['status']}]",
                fill=(20, 20, 20, 255),
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    checker.convert("RGB").save(output_path, format="PNG")


def _parse_hex_color(value: str) -> tuple[int, int, int]:
    normalized = value.strip().lstrip("#")
    if len(normalized) != 6:
        raise ValueError(f"Invalid RGB color: {value}")
    try:
        return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as exc:
        raise ValueError(f"Invalid RGB color: {value}") from exc


def _color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _asset_version(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]
