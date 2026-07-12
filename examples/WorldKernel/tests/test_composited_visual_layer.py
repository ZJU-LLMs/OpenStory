from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from PIL import Image
import pytest

from worldkernel.architect.spatial.models import BlueprintGrid, BlueprintRegion, GridPoint, SpatialBlueprint
from worldkernel.architect.visual.control import composite_protected_background
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
    assert Path(manifest.background.control_image_path).name == "generation_control.png"
    assert all(slot.safe_padding_px == 0 for slot in manifest.slots)
    assert manifest.decorations == []
    assert manifest.location_patches == []
    assert manifest.asset_contract["layer_order"][:3] == [
        "background.png",
        "route_layer",
        "location_placeholder_layer",
    ]


def test_pipeline_writes_layout_preview_base_and_protection_mask():
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
        assert (output_root / "generation_base.png").exists()
        assert (output_root / "generation_control.png").exists()
        assert (output_root / "generation_mask.png").exists()
        assert not (output_root / "background.png").exists()

        mask = Image.open(output_root / "generation_mask.png").convert("RGBA").getchannel("A")
        base = Image.open(output_root / "generation_base.png").convert("RGB")
        control = Image.open(output_root / "generation_control.png").convert("RGB")
        assert mask.size == (480, 320)
        assert mask.getpixel((7 * 16, 6 * 16)) == 255
        assert mask.getpixel((12 * 16, 10 * 16)) == 255
        assert mask.getpixel((12 * 16, 10 * 16 - 1)) == 0
        assert mask.getpixel((12 * 16, 11 * 16)) == 0
        assert mask.getpixel((240, 300)) == 0
        assert control.getpixel((7 * 16, 6 * 16)) != base.getpixel((7 * 16, 6 * 16))
        assert control.getpixel((12 * 16, 10 * 16)) != base.getpixel((12 * 16, 10 * 16))
        assert control.getpixel((12 * 16, 10 * 16 - 1)) == base.getpixel((12 * 16, 10 * 16 - 1))

        prompt = json.loads((output_root / "background_prompt.json").read_text(encoding="utf-8"))
        assert prompt["target_size"] == {"width": 480, "height": 320}
        assert "60%" not in prompt["prompt"]
        assert "地点矩形区域和道路网格已经从可编辑区域中精确扣除" in prompt["prompt"]
        assert "原生 tile/sprite 像素美术语言" in prompt["prompt"]
        assert "不再进行图像采样" not in prompt["prompt"]
        assert "不要拆成互不关联的独立装饰块" in prompt["prompt"]
        assert "先确认其屋顶、墙体、底座、轮廓、附属结构和阴影全部位于可编辑区域" in prompt["prompt"]
        assert "已经被未来建筑、院落或场所占用的位置" in prompt["prompt"]
        assert "与蒙版完全重合，是必须保留的真实空间约束" in prompt["prompt"]
        assert "不得在原始位置旁边生成第二个偏移建筑体块" in prompt["prompt"]
        assert "不得先设计跨越体块的大型建筑或设施" in prompt["prompt"]
        assert "被地点矩形挖去一块的建筑" in prompt["prompt"]

    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_generated_background_uses_one_global_masked_edit(monkeypatch):
    output_root = Path(__file__).resolve().parent / f".tmp_visual_single_edit_{uuid4().hex}"
    calls: list[dict] = []

    class FakeImageClient:
        def __init__(self, config):
            self.config = config

        def generate(self, prompt, output_path, **kwargs):
            output = Path(output_path)
            width, height = (int(value) for value in kwargs["size"].split("x"))
            Image.new("RGB", (width, height), (190, 80, 60)).save(output)
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
        assert manifest.background.generation_strategy == "single_global_masked_edit"
        assert len(calls) == 1
        assert calls[0]["output"].name == "background_raw.png"
        assert Path(calls[0]["input_image_path"]).name == "generation_control.png"
        assert Path(calls[0]["mask_path"]).name == "generation_mask.png"
        final = Image.open(output_root / "background.png").convert("RGB")
        base = Image.open(output_root / "generation_base.png").convert("RGB")
        assert final.getpixel((7 * 16, 6 * 16)) == base.getpixel((7 * 16, 6 * 16))
        assert final.getpixel((240, 300)) == (190, 80, 60)
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_final_composite_restores_protected_pixels_and_keeps_free_area():
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
        metadata = composite_protected_background(
            generated_path,
            output_root / "generation_base.png",
            output_root / "generation_mask.png",
            final_path,
            target_size=(480, 320),
        )

        final = Image.open(final_path).convert("RGB")
        base = Image.open(output_root / "generation_base.png").convert("RGB")
        assert final.getpixel((7 * 16, 6 * 16)) == base.getpixel((7 * 16, 6 * 16))
        assert final.getpixel((240, 300)) == (220, 30, 30)
        assert metadata["resized"] is False
        assert metadata["postprocessing"] == "none"
        assert metadata["output_size"] == {"width": 480, "height": 320}
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_composite_rejects_wrong_model_size_instead_of_resampling():
    output_root = Path(__file__).resolve().parent / f".tmp_visual_wrong_size_{uuid4().hex}"
    output_root.mkdir(parents=True)
    try:
        generated_path = output_root / "generated.png"
        base_path = output_root / "base.png"
        mask_path = output_root / "mask.png"
        Image.new("RGB", (100, 100), (20, 30, 40)).save(generated_path)
        Image.new("RGB", (200, 100), (50, 60, 70)).save(base_path)
        Image.new("RGBA", (200, 100), (255, 255, 255, 0)).save(mask_path)

        with pytest.raises(ValueError, match="does not match target size"):
            composite_protected_background(
                generated_path,
                base_path,
                mask_path,
                output_root / "final.png",
                target_size=(200, 100),
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
