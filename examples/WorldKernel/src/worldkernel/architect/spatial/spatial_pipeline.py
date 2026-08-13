"""Spatial pipeline — orchestrates Phase B→C→D→E1→G."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from worldkernel.architect.spatial.blueprint_exporter import SpatialBlueprintExporter
from worldkernel.architect.spatial.config import (
    SpatialGenerationConfig,
    load_spatial_generation_config,
)
from worldkernel.architect.spatial.models import (
    CanonicalSpatialArtifact,
    E1ValidationResult,
    LayoutPlan,
    RegionPackingResult,
    RouteRasterizationResult,
    SpatialBlueprint,
    SpatialBuildInput,
)
from worldkernel.architect.spatial.region_packer import RegionPacker
from worldkernel.architect.spatial.route_rasterizer import RouteRasterizer
from worldkernel.architect.spatial.spatial_validator import StructuralValidator
from worldkernel.architect.spatial.topology_layout import TopologyLayoutGenerator

logger = logging.getLogger(__name__)


class SpatialPipelineResult(BaseModel):
    """Complete output of the spatial pipeline."""
    build_input: SpatialBuildInput
    layout: LayoutPlan
    packing: RegionPackingResult
    rasterization: RouteRasterizationResult
    validation: E1ValidationResult
    blueprint: SpatialBlueprint
    config: SpatialGenerationConfig
    provenance: dict[str, Any] = Field(default_factory=dict)

    @property
    def artifact(self) -> CanonicalSpatialArtifact:
        return self.validation.artifact

    @property
    def passed(self) -> bool:
        return self.validation.report.passed


class SpatialPipeline:
    """Orchestrates the spatial generation pipeline: B→C→D→E1→G."""

    def __init__(self, config: SpatialGenerationConfig | None = None):
        self.config = config or load_spatial_generation_config()

    def run(self, build_input: SpatialBuildInput) -> SpatialPipelineResult:
        """Execute the full spatial pipeline."""
        config = self.config
        logger.info(
            "Spatial pipeline start: world_id=%s, locations=%d, paths=%d",
            build_input.world_id, len(build_input.locations), len(build_input.paths),
        )

        # Phase B: Layout
        logger.info("Phase B: TopologyLayoutGenerator")
        layout = TopologyLayoutGenerator().generate(build_input, config)
        logger.info("  -> %d locations laid out", len(layout.locations))

        # Phase C: Region packing
        logger.info("Phase C: RegionPacker")
        packing = RegionPacker().pack(layout, build_input, config)
        logger.info("  -> %d regions placed", len(packing.regions))

        # Phase D: Route rasterization
        logger.info("Phase D: RouteRasterizer")
        rasterization = RouteRasterizer().rasterize(build_input, layout, packing, config)
        logger.info("  -> %d routes generated", len(rasterization.routes))

        # Phase E1: Validation
        logger.info("Phase E1: StructuralValidator")
        validation = StructuralValidator().validate(
            build_input, layout, packing, rasterization, config,
        )
        logger.info(
            "  -> passed=%s, issues=%d",
            validation.report.passed, len(validation.report.issues),
        )

        # A disconnected or otherwise invalid map must never be published as a
        # usable blueprint. Callers can retry with a different layout seed or a
        # larger canvas, but Stage3 must not consume a failed spatial artifact.
        if not validation.report.passed:
            errors = [
                issue.message
                for issue in validation.report.issues
                if issue.severity == "error"
            ]
            raise RuntimeError(
                "Spatial generation failed structural validation: "
                + "; ".join(errors)
            )

        # Phase G: Blueprint export
        logger.info("Phase G: SpatialBlueprintExporter")
        blueprint = SpatialBlueprintExporter().export(validation.artifact, build_input)
        logger.info("  -> blueprint ready (%d regions, %d routes, %d spawns)",
                     len(blueprint.regions), len(blueprint.routes), len(blueprint.spawn_points))

        return SpatialPipelineResult(
            build_input=build_input,
            layout=layout,
            packing=packing,
            rasterization=rasterization,
            validation=validation,
            blueprint=blueprint,
            config=config,
            provenance={
                "phases_completed": ["B", "C", "D", "E1", "G"],
                "validation_passed": validation.report.passed,
                "validation_issues": len(validation.report.issues),
            },
        )
