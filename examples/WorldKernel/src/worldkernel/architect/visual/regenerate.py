from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from worldkernel.architect.pipeline import save_spatial_blueprint
from worldkernel.architect.semantic.repository import SemanticArtifactRepository
from worldkernel.architect.spatial.config import load_spatial_generation_config
from worldkernel.architect.spatial.input_assembler import (
    SpatialInputAssembler,
    SpatialInputAssemblyError,
)
from worldkernel.architect.spatial.models import SpatialBlueprint
from worldkernel.architect.spatial.spatial_pipeline import SpatialPipeline
from worldkernel.architect.visual.pipeline import run_visual_pipeline


class VisualRegenerationResult(BaseModel):
    world_id: str
    template_root: str
    semantic_root: str
    spatial_output_root: str
    spatial_source: str
    semantic_counts: dict[str, int] = Field(default_factory=dict)
    spatial_counts: dict[str, int] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    blueprint: SpatialBlueprint


def regenerate_visual_from_template(
    *,
    template_root: str | Path,
    config_path: str | Path,
    image_model_config_path: str | Path,
    generate_background: bool = True,
    generate_location_layer: bool | None = None,
    generate_characters: bool | None = None,
    force_character_batch_ids: list[str] | None = None,
    reuse_existing_spatial: bool = True,
    force_visual_regeneration: bool = False,
    visual_debug_root: str | Path | None = None,
) -> VisualRegenerationResult:
    """Regenerate visual assets from already saved Stage2 semantic artifacts.

    This test path deliberately skips Stage1 and the semantic DAG. It reuses an
    existing spatial blueprint when present, so prompt/model iteration does not
    accidentally change map coordinates.
    """
    template_path = Path(template_root)
    if not template_path.exists():
        raise FileNotFoundError(f"template not found: {template_path}")

    world_id = _load_world_id(template_path)
    semantic_root = _resolve_semantic_root(template_path)
    if not semantic_root.exists():
        raise FileNotFoundError(
            f"semantic artifacts not found: {semantic_root}; run Stage2 semantic generation first"
        )

    repository = SemanticArtifactRepository(world_id=world_id, root=semantic_root)
    foundation = repository.build_foundation_bundle()
    spatial_output_root = template_path / "generated" / "artifacts" / "spatial"
    spatial_output_root.mkdir(parents=True, exist_ok=True)

    spatial_config = load_spatial_generation_config(config_path)
    if generate_location_layer is None:
        generate_location_layer = (
            spatial_config.rendering.ai_art_enabled
            and spatial_config.rendering.location_layer_enabled
        )
    if generate_characters is None:
        generate_characters = (
            spatial_config.rendering.ai_art_enabled
            and spatial_config.rendering.character_atlas_enabled
        )
    if force_character_batch_ids:
        from worldkernel.architect.visual.character_atlas import (
            validate_character_batch_selection,
        )

        validate_character_batch_selection(
            semantic_characters=list(foundation.characters),
            character_root=spatial_output_root / "characters",
            max_batch_size=spatial_config.rendering.characters_per_atlas,
            force_batch_ids=force_character_batch_ids,
        )
    existing_blueprint_path = spatial_output_root / "spatial_blueprint.json"
    validation_payload: dict[str, Any] = {"passed": None, "issues": []}
    if reuse_existing_spatial and existing_blueprint_path.exists():
        blueprint = SpatialBlueprint.model_validate_json(
            existing_blueprint_path.read_text(encoding="utf-8")
        )
        spatial_source = "existing_spatial_blueprint"
    else:
        try:
            build_input = SpatialInputAssembler().assemble(
                world_id=world_id,
                semantic_root=semantic_root,
            )
        except SpatialInputAssemblyError:
            raise
        spatial_result = SpatialPipeline(spatial_config).run(build_input)
        blueprint = spatial_result.blueprint
        spatial_source = "rebuilt_from_semantic_artifacts"
        report = spatial_result.validation.report
        validation_payload = {
            "passed": report.passed,
            "issues": [issue.model_dump(mode="json") for issue in report.issues],
        }

    world_background = _load_world_background(template_path)
    visual_manifest = run_visual_pipeline(
        blueprint=blueprint,
        world_background=world_background,
        output_root=spatial_output_root,
        model_config_path=image_model_config_path,
        generate_background=generate_background,
        generate_location_layer=bool(generate_location_layer),
        semantic_locations=list(foundation.locations),
        semantic_characters=list(foundation.characters),
        generate_character_layer=bool(generate_characters),
        character_batch_size=spatial_config.rendering.characters_per_atlas,
        character_key_colors=spatial_config.rendering.character_key_colors,
        character_transparent_threshold=(
            spatial_config.rendering.character_transparent_threshold
        ),
        character_opaque_threshold=spatial_config.rendering.character_opaque_threshold,
        force_character_batch_ids=force_character_batch_ids,
        force_location_regeneration=force_visual_regeneration,
        location_debug_artifact_root=(
            Path(visual_debug_root) / "location_attempts"
            if visual_debug_root is not None
            else None
        ),
    )
    blueprint.visual = visual_manifest.model_dump(mode="json")
    save_spatial_blueprint(blueprint, spatial_output_root)

    semantic_counts = {
        "locations": len(foundation.locations),
        "paths": len(foundation.path_graph),
        "characters": len(foundation.characters),
        "relations": len(foundation.relation_graph),
    }
    return VisualRegenerationResult(
        world_id=world_id,
        template_root=str(template_path),
        semantic_root=str(semantic_root),
        spatial_output_root=str(spatial_output_root),
        spatial_source=spatial_source,
        semantic_counts=semantic_counts,
        spatial_counts={
            "regions": len(blueprint.regions),
            "routes": len(blueprint.routes),
            "road_tiles": len(blueprint.road_tiles),
            "spawn_points": len(blueprint.spawn_points),
            "location_layer_ready": int(visual_manifest.location_layer.status == "ready"),
            "ready_locations": len(visual_manifest.location_layer.completed_location_ids),
            "failed_locations": len(visual_manifest.location_layer.failed_location_ids),
            "roads_integrated": int(
                visual_manifest.location_layer.includes_roads
                and visual_manifest.location_layer.status in {"ready", "partial"}
            ),
            "character_count": visual_manifest.character_layer.character_count,
            "eligible_character_count": (
                visual_manifest.character_layer.eligible_character_count
            ),
            "planned_character_batches": (
                visual_manifest.character_layer.planned_batch_count
            ),
            "generated_character_batches": (
                visual_manifest.character_layer.generated_batch_count
            ),
            "reused_character_batches": (
                visual_manifest.character_layer.reused_batch_count
            ),
            "estimated_character_image_calls": (
                visual_manifest.character_layer.estimated_image_calls
            ),
        },
        validation=validation_payload,
        blueprint=blueprint,
    )


def _load_world_id(template_root: Path) -> str:
    world_background = _load_world_background(template_root)
    world_id = str(world_background.get("world_id") or "").strip()
    return world_id or template_root.name


def _load_world_background(template_root: Path) -> dict[str, Any]:
    path = template_root / "generated" / "plan" / "world_background.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid world_background.json: {path}") from exc
    return data if isinstance(data, dict) else {}


def _resolve_semantic_root(template_root: Path) -> Path:
    artifacts_root = template_root / "generated" / "artifacts"
    candidates = [
        artifacts_root / "semantic",
        artifacts_root,
    ]
    for candidate in candidates:
        if (candidate / "metadata" / "semantic_manifest.json").exists():
            return candidate
    return artifacts_root / "semantic"
