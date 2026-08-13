from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from worldkernel.architect.spatial.config import (  # noqa: E402
    SpatialCanvasConfig,
    SpatialGenerationConfig,
    SpatialLayoutConfig,
    load_spatial_generation_config,
)
from worldkernel.architect.spatial.models import (  # noqa: E402
    LayoutPlan,
    LocationLayout,
    LocationSpatialFact,
    RegionPackingResult,
    RouteRasterizationResult,
    SpatialBuildInput,
    SpatialRegion,
)
from worldkernel.architect.spatial.region_packer import RegionPacker  # noqa: E402
from worldkernel.architect.spatial.route_rasterizer import RouteRasterizer  # noqa: E402
from worldkernel.architect.spatial.spatial_validator import StructuralValidator  # noqa: E402
from worldkernel.stage1.ontology_selector import _FIXED_DIMENSIONS  # noqa: E402


def test_default_spatial_config_reads_worldkernel_architect_yaml() -> None:
    config = load_spatial_generation_config()

    assert config.canvas.grid_width == 128
    assert config.canvas.grid_height == 72
    assert config.canvas.default_region_min_size == [12, 8]
    assert config.canvas.default_region_max_size == [22, 16]
    assert config.layout.min_region_gap == 6
    assert config.layout.preferred_region_gap == 10


def test_location_schema_keeps_seed_importance_for_spatial_sizing() -> None:
    identity_fields = {
        field.name for field in _FIXED_DIMENSIONS["location"]["identity"]
    }

    assert "importance" in identity_fields


def _config() -> SpatialGenerationConfig:
    return SpatialGenerationConfig(
        canvas=SpatialCanvasConfig(
            grid_width=32,
            grid_height=20,
            margin_tiles=1,
            default_region_min_size=[4, 4],
            default_region_max_size=[6, 6],
            corridor_width=1,
        )
    )


def _build_input() -> SpatialBuildInput:
    return SpatialBuildInput(
        world_id="connected-world",
        source_root=".",
        locations=[
            LocationSpatialFact(location_id="a", name="A"),
            LocationSpatialFact(location_id="b", name="B"),
            LocationSpatialFact(location_id="c", name="C"),
        ],
        paths=[],
    )


def _packing() -> RegionPackingResult:
    return RegionPackingResult(
        regions=[
            SpatialRegion(
                location_id="a", name="A", x=2, y=2, width=4, height=4,
                entrance_x=5, entrance_y=3,
            ),
            SpatialRegion(
                location_id="b", name="B", x=14, y=2, width=4, height=4,
                entrance_x=14, entrance_y=3,
            ),
            SpatialRegion(
                location_id="c", name="C", x=25, y=12, width=4, height=4,
                entrance_x=25, entrance_y=13,
            ),
        ]
    )


def test_rasterizer_connects_all_locations_without_semantic_paths() -> None:
    config = _config()
    build_input = _build_input()
    packing = _packing()
    layout = LayoutPlan(
        world_id=build_input.world_id,
        grid_width=config.canvas.grid_width,
        grid_height=config.canvas.grid_height,
        tile_size=config.canvas.tile_size,
    )

    result = RouteRasterizer().rasterize(build_input, layout, packing, config)

    assert len(result.routes) == len(packing.regions) - 1
    assert all(route.route_type == "synthetic" for route in result.routes)
    validation = StructuralValidator().validate(
        build_input, layout, packing, result, config,
    )
    assert validation.report.passed is True
    assert not {
        "disconnected_locations",
        "isolated_region",
        "unreachable_region_entrance",
    }.intersection(issue.code for issue in validation.report.issues)


def test_validator_rejects_isolated_regions_as_errors() -> None:
    config = _config()
    build_input = _build_input()
    packing = _packing()
    layout = LayoutPlan(
        world_id=build_input.world_id,
        grid_width=config.canvas.grid_width,
        grid_height=config.canvas.grid_height,
        tile_size=config.canvas.tile_size,
    )
    grid = [[0] * config.canvas.grid_width for _ in range(config.canvas.grid_height)]
    for region in packing.regions:
        for y in range(region.y, region.y + region.height):
            for x in range(region.x, region.x + region.width):
                grid[y][x] = 1
    rasterization = RouteRasterizationResult(collision_grid=grid)

    validation = StructuralValidator().validate(
        build_input, layout, packing, rasterization, config,
    )

    assert validation.report.passed is False
    errors = {issue.code for issue in validation.report.issues if issue.severity == "error"}
    assert "disconnected_locations" in errors
    assert "isolated_region" in errors
    assert "unreachable_region_entrance" in errors


def test_region_packer_centered_fallback_keeps_every_location() -> None:
    config = SpatialGenerationConfig(
        canvas=SpatialCanvasConfig(
            grid_width=32,
            grid_height=20,
            margin_tiles=1,
            default_region_min_size=[4, 4],
            default_region_max_size=[6, 6],
            corridor_width=1,
        ),
        layout=SpatialLayoutConfig(
            packing_max_attempts=1,
            min_region_gap=2,
            preferred_region_gap=2,
            edge_comfort_margin=1,
            candidate_limit=1,
        ),
    )
    build_input = _build_input()
    layout = LayoutPlan(
        world_id=build_input.world_id,
        grid_width=config.canvas.grid_width,
        grid_height=config.canvas.grid_height,
        tile_size=config.canvas.tile_size,
        locations=[
            LocationLayout(location_id=location.location_id, center_x=10, center_y=10)
            for location in build_input.locations
        ],
    )

    packing = RegionPacker().pack(layout, build_input, config)

    assert {region.location_id for region in packing.regions} == {"a", "b", "c"}
    assert packing.provenance["centered_repack_used"] is True
    left = min(region.x for region in packing.regions)
    right = max(region.x + region.width for region in packing.regions)
    top = min(region.y for region in packing.regions)
    bottom = max(region.y + region.height for region in packing.regions)
    assert abs((left + right) / 2 - config.canvas.grid_width / 2) <= 1
    assert abs((top + bottom) / 2 - config.canvas.grid_height / 2) <= 1


def test_region_packer_uses_core_major_minor_size_tiers() -> None:
    config = SpatialGenerationConfig(
        canvas=SpatialCanvasConfig(
            grid_width=90,
            grid_height=48,
            margin_tiles=1,
            default_region_min_size=[6, 4],
            default_region_max_size=[14, 10],
            corridor_width=1,
        ),
        layout=SpatialLayoutConfig(
            min_region_gap=2,
            preferred_region_gap=2,
            edge_comfort_margin=1,
            candidate_limit=256,
        ),
    )
    build_input = SpatialBuildInput(
        world_id="sized-world",
        source_root=".",
        locations=[
            LocationSpatialFact(location_id="core", name="Core", importance="core"),
            LocationSpatialFact(location_id="major", name="Major", importance="major"),
            LocationSpatialFact(location_id="minor", name="Minor", importance="minor"),
        ],
    )
    layout = LayoutPlan(
        world_id=build_input.world_id,
        grid_width=config.canvas.grid_width,
        grid_height=config.canvas.grid_height,
        tile_size=config.canvas.tile_size,
        locations=[
            LocationLayout(location_id="core", center_x=15, center_y=24),
            LocationLayout(location_id="major", center_x=45, center_y=24),
            LocationLayout(location_id="minor", center_x=75, center_y=24),
        ],
    )

    packing = RegionPacker().pack(layout, build_input, config)
    sizes = {
        region.location_id: (region.width, region.height)
        for region in packing.regions
    }

    assert sizes == {
        "core": (14, 10),
        "major": (10, 7),
        "minor": (6, 4),
    }
