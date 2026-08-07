"""Stage 2 unified pipeline — semantic generation + spatial generation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from worldkernel.architect.semantic.models import FoundationBundle

logger = logging.getLogger(__name__)


class Stage2Result(BaseModel):
    """Complete output of the Stage 2 pipeline."""
    world_id: str
    foundation: FoundationBundle
    spatial: Any = None  # SpatialPipelineResult (avoid circular import)
    semantic_output_root: str = ""
    spatial_output_root: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)


def _default_spatial_output_root(world_id: str) -> Path:
    worldkernel_root = Path(__file__).resolve().parents[3]
    return worldkernel_root / "worlds" / "generated" / world_id / "stage2" / "spatial"


def save_spatial_blueprint(
    blueprint: Any,
    output_root: str | Path | None = None,
) -> dict[str, Path]:
    """Save spatial blueprint to disk.

    Args:
        blueprint: SpatialBlueprint instance.
        output_root: Directory to write into. Defaults to worlds/generated/{world_id}/stage2/spatial.

    Returns:
        Dict of artifact_name -> file_path.
    """
    from worldkernel.architect.spatial.models import SpatialBlueprint

    if not isinstance(blueprint, SpatialBlueprint):
        raise TypeError(f"Expected SpatialBlueprint, got {type(blueprint)}")

    root = Path(output_root) if output_root else _default_spatial_output_root(blueprint.world_id)
    root.mkdir(parents=True, exist_ok=True)

    blueprint_path = root / "spatial_blueprint.json"
    blueprint_path.write_text(
        json.dumps(blueprint.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("Spatial blueprint saved to %s", blueprint_path)
    return {"spatial_blueprint": blueprint_path}


async def run_stage2(
    session_root: str | Path,
    output_root: str | Path | None = None,
    config_path: str | Path | None = None,
    constraints: object | None = None,
    save_semantic: bool = True,
    save_spatial: bool = True,
    debug: bool = False,
) -> Stage2Result:
    """Run the complete Stage 2 pipeline: semantic generation + spatial generation.

    Args:
        session_root: Path to the session directory containing Stage1 artifacts.
        output_root: Root directory for all Stage2 outputs. Defaults to worlds/generated/{world_id}/stage2/.
        config_path: Path to architect.yaml. Defaults to configs/architect.yaml.
        save_semantic: Whether to save semantic artifacts to disk.
        save_spatial: Whether to save spatial blueprint to disk.
        debug: Whether to save debug snapshots.

    Returns:
        Stage2Result with foundation bundle and spatial pipeline result.
    """
    # Lazy imports to avoid loading heavy dependencies at module level
    from worldkernel.architect.init.loader import InitInputLoader
    from worldkernel.architect.init.pipeline import compile_stage1_init_context
    from worldkernel.architect.registry.core import create_default_schema_registry, create_default_tool_registry
    from worldkernel.architect.registry.schema_loader import load_stage1_session_schema_source
    from worldkernel.architect.semantic.bundle import FoundationBundleBuilder
    from worldkernel.architect.semantic.runner import InitDAGRunner
    from worldkernel.architect.semantic.storage import save_semantic_artifacts
    from worldkernel.architect.spatial.config import load_spatial_generation_config
    from worldkernel.architect.spatial.pipeline_adapter import SpatialPipelineAdapter
    from worldkernel.architect.spatial.spatial_pipeline import SpatialPipeline

    session_root = Path(session_root)

    # --- Semantic Phase ---
    logger.info("=== Stage 2: Semantic Generation ===")

    # 1. Load Stage1 artifacts
    logger.info("Loading Stage1 artifacts from %s", session_root)
    bundle = InitInputLoader.from_session_root(session_root)

    # 2. Load schemas and tools
    schema_registry = create_default_schema_registry()
    load_stage1_session_schema_source(session_root, schema_registry)
    tool_registry = create_default_tool_registry(schema_registry)

    # 3. Compile init context
    logger.info("Compiling init context")
    context = compile_stage1_init_context(
        bundle,
        schema_registry=schema_registry,
        tool_registry=tool_registry,
        constraints=constraints,
    )

    # 4. Run semantic generation (LLM calls)
    logger.info("Running semantic generation")
    runner = InitDAGRunner(schema_registry, tool_registry)
    gen_state = await runner.run_async(context)

    if gen_state.failed_step_id:
        logger.error("Semantic generation failed at step %s", gen_state.failed_step_id)
        raise RuntimeError(
            f"Semantic generation failed at step {gen_state.failed_step_id}: "
            f"{gen_state.errors}"
        )

    # 5. Build FoundationBundle (in-memory)
    logger.info("Building FoundationBundle")
    foundation = FoundationBundleBuilder().build(context, gen_state)

    # 6. Optionally save semantic artifacts
    semantic_output_root = ""
    if save_semantic:
        sem_root = Path(output_root) / "semantic" if output_root else None
        report = save_semantic_artifacts(
            world_id=foundation.world_id,
            init_context=context,
            generation_state=gen_state,
            output_root=sem_root,
            debug=debug,
        )
        semantic_output_root = str(sem_root or _default_semantic_root(foundation.world_id))
        logger.info("Semantic artifacts saved to %s", semantic_output_root)

    # --- Spatial Phase ---
    logger.info("=== Stage 2: Spatial Generation ===")

    # 7. Convert FoundationBundle to SpatialBuildInput (in-memory, no disk I/O)
    logger.info("Converting FoundationBundle to SpatialBuildInput")
    build_input = SpatialPipelineAdapter.from_foundation_bundle(foundation)

    # 8. Load spatial config
    spatial_config = load_spatial_generation_config(config_path)

    # 9. Run spatial pipeline (B→C→D→E1→G)
    logger.info("Running spatial pipeline")
    spatial_result = SpatialPipeline(spatial_config).run(build_input)

    # 10. Optionally run the visual layer and save spatial blueprint
    spatial_output_root = ""
    if save_spatial:
        sp_root = Path(output_root) / "spatial" if output_root else None
        visual_root = sp_root or _default_spatial_output_root(foundation.world_id)
        try:
            from worldkernel.architect.visual import run_visual_pipeline

            model_config_path = (
                Path(config_path).parent / "image_models.yaml"
                if config_path
                else Path(__file__).resolve().parents[3] / "configs" / "image_models.yaml"
            )
            visual_manifest = run_visual_pipeline(
                blueprint=spatial_result.blueprint,
                world_background=context.world_background.model_dump(mode="json"),
                output_root=visual_root,
                model_config_path=model_config_path,
                generate_background=spatial_config.rendering.ai_art_enabled,
                generate_location_layer=(
                    spatial_config.rendering.ai_art_enabled
                    and spatial_config.rendering.location_layer_enabled
                ),
                generate_road_texture=(
                    spatial_config.rendering.ai_art_enabled
                    and spatial_config.rendering.road_texture_enabled
                ),
                semantic_locations=list(foundation.locations),
            )
            spatial_result.blueprint.visual = visual_manifest.model_dump(mode="json")
        except Exception as exc:
            logger.warning("Visual layer failed; saving spatial blueprint without generated art: %s", exc)
            spatial_result.blueprint.visual = {"status": "failed", "error": str(exc)}
        saved = save_spatial_blueprint(
            blueprint=spatial_result.blueprint,
            output_root=sp_root,
        )
        spatial_output_root = str(sp_root or _default_spatial_output_root(foundation.world_id))
        logger.info("Spatial blueprint saved to %s", spatial_output_root)

    logger.info(
        "Stage 2 complete: world_id=%s, locations=%d, paths=%d, validation=%s",
        foundation.world_id,
        len(foundation.locations),
        len(foundation.path_graph),
        "PASS" if spatial_result.validation.report.passed else "FAIL",
    )

    return Stage2Result(
        world_id=foundation.world_id,
        foundation=foundation,
        spatial=spatial_result,
        semantic_output_root=semantic_output_root,
        spatial_output_root=spatial_output_root,
        provenance={
            "session_root": str(session_root),
            "save_semantic": save_semantic,
            "save_spatial": save_spatial,
        },
    )


def _default_semantic_root(world_id: str) -> str:
    worldkernel_root = Path(__file__).resolve().parents[3]
    return str(worldkernel_root / "worlds" / "generated" / world_id / "stage2" / "semantic")
