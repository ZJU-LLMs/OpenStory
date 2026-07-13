from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from PIL import Image
import pytest

from worldkernel.architect.spatial.models import BlueprintGrid, BlueprintRegion, GridPoint, SpatialBlueprint
from worldkernel.architect.visual.control import (
    EDITABLE_BASE_COLOR,
    LOCATION_RESERVED_COLOR,
    ROAD_RESERVED_COLOR,
    finalize_generated_background,
)
from worldkernel.architect.visual.layout import build_visual_layout_manifest
from worldkernel.architect.visual.pipeline import run_visual_pipeline


def test_manifest_uses_strict_route_and_location_placeholder_layers():
    manifest = build_visual_layout_manifest(
        _sample_blueprint(),
        {"visual_profile": {"camera_projection": "严格正交俯视"}},
        Path("out"),
    )

    assert manifest.mode == "composited_full_map"
    assert manifest.route_layer.status == "ready"
    assert manifest.location_placeholder_layer.status == "ready"
    assert manifest.location_placeholder_layer.show_names is True
    assert manifest.canvas["visual_clearance_tiles"] == 2
    assert Path(manifest.background.control_image_path).name == "generation_edit_base.png"
    assert Path(manifest.background.mask_path).name == "generation_edit_mask.png"
    assert Path(manifest.background.edit_base_path).name == "generation_edit_base.png"
    assert Path(manifest.background.edit_mask_path).name == "generation_edit_mask.png"
    assert Path(manifest.background.debug_mask_path).name == "generation_mask.png"
    assert Path(manifest.background.location_mask_path).name == "generation_location_mask.png"
    assert Path(manifest.background.road_mask_path).name == "generation_road_mask.png"
    assert all(slot.safe_padding_px == 0 for slot in manifest.slots)
    assert manifest.decorations == []
    assert manifest.location_patches == []
    assert manifest.asset_contract["layer_order"][:3] == [
        "background.png",
        "route_layer",
        "location_placeholder_layer",
    ]


def test_frontend_draws_routes_before_opaque_location_placeholders():
    frontend_path = Path(__file__).resolve().parents[1] / "frontend" / "simulation-modern.js"
    source = frontend_path.read_text(encoding="utf-8")
    render_map = source[source.index("function renderMap()") : source.index("function drawMapBase(grid)")]
    draw_region = source[source.index("function drawRegion(") : source.index("function drawRoutes")]

    assert render_map.index("drawRoutes(routes, roadTiles)") < render_map.index("for (const region of regions)")
    assert "ctx.fillRect(left, top, width, height)" in draw_region
    assert "location_placeholder_layer?.style" in draw_region
    assert "compositedLayers.has('route_layer')" in render_map
    assert "compositedLayers.has('location_placeholder_layer')" in render_map


def test_pipeline_writes_exact_size_edit_base_and_hard_mask():
    output_root = Path(__file__).resolve().parent / f".tmp_visual_control_{uuid4().hex}"
    try:
        manifest = run_visual_pipeline(
            blueprint=_sample_blueprint(),
            world_background={
                "world_origin_summary": "一片生机盎然的幻想草原",
                "visual_profile": {"art_style": "像素卡通 RPG 地图"},
            },
            output_root=output_root,
            model_config_path=Path(__file__).resolve().parents[1] / "configs" / "image_models.yaml",
            generate_background=False,
        )

        assert manifest.background.status == "prompt_ready"
        assert (output_root / "layout_preview.png").exists()
        assert not (output_root / "generation_base.png").exists()
        assert not (output_root / "generation_control.png").exists()
        assert (output_root / "generation_edit_base.png").exists()
        assert (output_root / "generation_edit_mask.png").exists()
        assert (output_root / "generation_location_mask.png").exists()
        assert (output_root / "generation_road_mask.png").exists()
        assert (output_root / "generation_mask.png").exists()
        assert not (output_root / "background.png").exists()

        mask = Image.open(output_root / "generation_mask.png").convert("L")
        edit_base = Image.open(output_root / "generation_edit_base.png").convert("RGB")
        edit_mask = Image.open(output_root / "generation_edit_mask.png")
        location_mask = Image.open(output_root / "generation_location_mask.png").convert("L")
        road_mask = Image.open(output_root / "generation_road_mask.png").convert("L")
        assert mask.size == (480, 320)
        assert edit_base.size == mask.size
        assert edit_mask.size == mask.size
        assert edit_mask.mode == "RGBA"
        assert location_mask.size == mask.size
        assert road_mask.size == mask.size
        assert mask.getpixel((7 * 16, 6 * 16)) == 255
        assert mask.getpixel((12 * 16, 10 * 16)) == 255
        assert mask.getpixel((12 * 16, 10 * 16 - 1)) == 0
        assert mask.getpixel((12 * 16, 11 * 16)) == 0
        assert mask.getpixel((240, 300)) == 0
        assert mask.getpixel((2 * 16, 2 * 16)) == 0
        assert location_mask.getpixel((7 * 16, 6 * 16)) == 255
        assert location_mask.getpixel((12 * 16, 10 * 16)) == 0
        assert road_mask.getpixel((7 * 16, 6 * 16)) == 0
        assert road_mask.getpixel((12 * 16, 10 * 16)) == 255
        assert edit_base.getpixel((7 * 16, 6 * 16)) == LOCATION_RESERVED_COLOR
        assert edit_base.getpixel((12 * 16, 10 * 16)) == ROAD_RESERVED_COLOR
        assert edit_base.getpixel((2 * 16, 2 * 16)) == EDITABLE_BASE_COLOR
        assert edit_mask.getpixel((7 * 16, 6 * 16))[3] == 255
        assert edit_mask.getpixel((12 * 16, 10 * 16))[3] == 255
        assert edit_mask.getpixel((2 * 16, 2 * 16))[3] == 0

        prompt = json.loads((output_root / "background_prompt.json").read_text(encoding="utf-8"))
        assert prompt["target_size"] == {"width": 480, "height": 320}
        assert "第一张输入底板" in prompt["prompt"]
        assert "原生 tile/sprite 像素美术语言" in prompt["prompt"]
        assert "共有 2 个中灰色地点保留区" in prompt["prompt"]
        assert "所有保留区都已由硬蒙版锁定" in prompt["prompt"]
        assert "不得跨入灰色保留区" in prompt["prompt"]
        assert "不要沿灰色区域增加外轮廓、描边、阴影、光晕或底座" in prompt["prompt"]
        assert "允许保留较大开阔区域" in prompt["prompt"]
        assert "Stage2" not in prompt["prompt"]
        assert "空间蓝图" not in prompt["prompt"]
        assert "默认草地" in prompt["negative_prompt"]
        assert "所有世界都是草地" in prompt["negative_prompt"]

        metadata = json.loads((output_root / "background_metadata.json").read_text(encoding="utf-8"))
        assert metadata["location_region_count"] == 2
        assert metadata["road_tile_count"] == 20
        assert metadata["mask_semantics"] == "transparent_pixels_editable_opaque_pixels_preserved"

    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_generated_background_uses_one_layout_guided_edit(monkeypatch):
    output_root = Path(__file__).resolve().parent / f".tmp_visual_single_edit_{uuid4().hex}"
    calls: list[dict] = []

    class FakeImageClient:
        def __init__(self, config):
            self.config = config

        def generate(self, prompt, output_path, **kwargs):
            output = Path(output_path)
            width, height = (int(value) for value in kwargs["size"].split("x"))
            generated = Image.new("RGB", (width, height), (190, 80, 60))
            with Image.open(kwargs["input_image_path"]) as input_image:
                source = input_image.convert("RGB")
            with Image.open(kwargs["mask_path"]) as mask_image:
                protected = mask_image.getchannel("A")
            generated.paste(source, mask=protected)
            generated.save(output)
            calls.append({"output": output, "prompt": prompt, **kwargs})
            return {"provider": "fake", "model": "fake-image", "api_style": "fake", "size": kwargs["size"]}

    monkeypatch.setattr("worldkernel.architect.visual.pipeline.ImageGenerationClient", FakeImageClient)
    try:
        manifest = run_visual_pipeline(
            blueprint=_sample_blueprint(),
            world_background={"visual_profile": {"color_palette": ["草绿"]}},
            output_root=output_root,
            model_config_path=Path(__file__).resolve().parents[1] / "configs" / "image_models.yaml",
            generate_background=True,
        )

        assert manifest.background.status == "ready"
        assert manifest.background.generation_strategy == "single_hard_mask_edit"
        assert manifest.background.composited_layers == ["route_layer", "location_placeholder_layer"]
        assert len(calls) == 1
        assert calls[0]["output"].name == "background_raw.png"
        assert Path(calls[0]["input_image_path"]).name == "generation_edit_base.png"
        assert Path(calls[0]["mask_path"]).name == "generation_edit_mask.png"
        assert [Path(path).name for path in calls[0]["style_reference_paths"]] == [
            "pixel_style_reference.png",
        ]
        assert "第一张图是与输出完全同尺寸的地图编辑底板" in calls[0]["prompt"]
        assert "中灰色矩形是地点保留区" in calls[0]["prompt"]
        assert "浅灰色狭长区域是道路保留区" in calls[0]["prompt"]
        assert "允许保留较大开阔区域" in calls[0]["prompt"]
        final = Image.open(output_root / "background.png").convert("RGB")
        raw = Image.open(output_root / "background_raw.png").convert("RGB")
        assert raw.getpixel((7 * 16, 6 * 16)) == LOCATION_RESERVED_COLOR
        assert raw.getpixel((int(12.5 * 16), int(10.5 * 16))) == ROAD_RESERVED_COLOR
        assert final.getpixel((7 * 16, 6 * 16)) != LOCATION_RESERVED_COLOR
        assert final.getpixel((int(12.5 * 16), int(10.5 * 16))) != ROAD_RESERVED_COLOR
        assert final.getpixel((240, 300)) == (190, 80, 60)

        metadata = json.loads((output_root / "background_metadata.json").read_text(encoding="utf-8"))
        assert metadata["mask_validation"]["passed"] is True
        assert metadata["mask_validation"]["changed_pixels"] == 0
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_pipeline_rejects_provider_that_ignores_hard_mask(monkeypatch):
    output_root = Path(__file__).resolve().parent / f".tmp_visual_ignored_mask_{uuid4().hex}"

    class IgnoringImageClient:
        def __init__(self, config):
            self.config = config

        def generate(self, prompt, output_path, **kwargs):
            width, height = (int(value) for value in kwargs["size"].split("x"))
            Image.new("RGB", (width, height), (250, 20, 20)).save(output_path)
            return {"provider": "fake", "model": "fake-image", "api_style": "fake"}

    monkeypatch.setattr("worldkernel.architect.visual.pipeline.ImageGenerationClient", IgnoringImageClient)
    try:
        manifest = run_visual_pipeline(
            blueprint=_sample_blueprint(),
            world_background={"visual_profile": {}},
            output_root=output_root,
            model_config_path=Path(__file__).resolve().parents[1] / "configs" / "image_models.yaml",
            generate_background=True,
        )

        assert manifest.background.status == "failed"
        assert "ignored one or more hard-mask regions" in manifest.background.error
        assert not (output_root / "background.png").exists()
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_final_background_composites_all_coordinate_layers():
    output_root = Path(__file__).resolve().parent / f".tmp_visual_composite_{uuid4().hex}"
    try:
        run_visual_pipeline(
            blueprint=_sample_blueprint(),
            world_background={"visual_profile": {}},
            output_root=output_root,
            model_config_path=Path(__file__).resolve().parents[1] / "configs" / "image_models.yaml",
            generate_background=False,
        )
        generated_path = output_root / "generated.png"
        final_path = output_root / "final.png"
        Image.new("RGB", (480, 320), (220, 30, 30)).save(generated_path)
        metadata = finalize_generated_background(
            generated_path,
            final_path,
            target_size=(480, 320),
            blueprint=_sample_blueprint(),
            route_style={"base_color": "#b99d5c", "edge_color": "#8f7744", "highlight_color": "#d2bb75"},
            placeholder_style={"fill_color": "rgba(45,55,78,0.64)", "border_color": "#e6ebf5"},
        )

        final = Image.open(final_path).convert("RGB")
        assert final.getpixel((7 * 16, 6 * 16)) != (220, 30, 30)
        assert final.getpixel((int(12.5 * 16), int(10.5 * 16))) != (220, 30, 30)
        assert final.getpixel((240, 300)) == (220, 30, 30)
        assert metadata["resized"] is False
        assert metadata["postprocessing"] == "none"
        assert metadata["output_size"] == {"width": 480, "height": 320}
        assert metadata["route_tile_count"] == 20
        assert metadata["location_placeholder_count"] == 2
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_finalization_rejects_wrong_model_size_instead_of_resampling():
    output_root = Path(__file__).resolve().parent / f".tmp_visual_wrong_size_{uuid4().hex}"
    output_root.mkdir(parents=True)
    try:
        generated_path = output_root / "generated.png"
        Image.new("RGB", (100, 100), (20, 30, 40)).save(generated_path)

        with pytest.raises(ValueError, match="does not match target size"):
            finalize_generated_background(
                generated_path,
                output_root / "final.png",
                target_size=(200, 100),
                blueprint=_sample_blueprint(),
                route_style={},
                placeholder_style={},
            )
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def _sample_blueprint() -> SpatialBlueprint:
    return SpatialBlueprint(
        world_id="world-1",
        grid=BlueprintGrid(width=30, height=20, tile_size=16),
        regions=[
            BlueprintRegion(
                location_id="loc-1",
                name="地点一",
                bounds={"x": 4, "y": 4, "w": 6, "h": 5},
                entrance={"x": 10, "y": 6},
                tags=[],
            ),
            BlueprintRegion(
                location_id="loc-2",
                name="地点二",
                bounds={"x": 20, "y": 12, "w": 5, "h": 4},
                entrance={"x": 20, "y": 14},
                tags=[],
            ),
        ],
        road_tiles=[GridPoint(x=x, y=10) for x in range(5, 25)],
    )
