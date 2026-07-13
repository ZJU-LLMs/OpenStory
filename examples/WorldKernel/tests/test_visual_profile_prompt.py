from __future__ import annotations

from pathlib import Path

from worldkernel.architect.spatial.models import BlueprintGrid, SpatialBlueprint
from worldkernel.architect.visual.layout import build_visual_layout_manifest
from worldkernel.architect.visual.prompt import FIXED_PIXEL_ART_STYLE, compose_background_prompt
from worldkernel.stage1.types import VisualProfile


def test_visual_profile_accepts_world_specific_environmental_motifs():
    profile = VisualProfile(
        environmental_motifs=["公交站", "停放车辆", "喷泉", "通用店铺外观"],
    )
    assert profile.environmental_motifs == ["公交站", "停放车辆", "喷泉", "通用店铺外观"]


def test_background_prompt_prioritizes_fixed_style_and_civilized_world_props():
    blueprint = SpatialBlueprint(
        world_id="modern-city",
        grid=BlueprintGrid(width=160, height=100, tile_size=16),
    )
    background = {
        "world_name": "晴川市",
        "world_origin_summary": "一座公共交通发达的现代滨水城市",
        "primary": "modern_city",
        "secondary": "waterfront_district",
        "tags": ["现代", "城市生活", "商业", "公共交通"],
        "visual_profile": {
            "art_style": "写实电影风格",
            "era_style": "当代城市",
            "color_palette": ["明亮灰白", "湖蓝", "草绿", "珊瑚橙"],
            "lighting_weather": "晴朗白天",
            "atmosphere": "轻松、繁华、友好",
            "environmental_motifs": ["公交站", "停放车辆", "喷泉", "通用店铺外观"],
        },
    }
    manifest = build_visual_layout_manifest(blueprint, background, Path("out"))
    payload = compose_background_prompt(background, manifest)
    prompt = payload["prompt"]

    assert FIXED_PIXEL_ART_STYLE in prompt
    assert "写实电影风格" not in prompt
    assert "晴川市" in prompt
    assert "公交站、停放车辆、喷泉、通用店铺外观" in prompt
    assert "完整落在深色可编辑区域内" in prompt
    assert "不得修改、移动、缩放、复制或另画一套" in prompt
    assert "中灰色矩形是未来地点图像的精确保留区" in prompt
    assert "第二套道路占位" in payload["negative_prompt"]
    assert "允许保留较大开阔区域" in prompt
    assert "不要为了填满画面而增加主体" in prompt
    assert "装饰过度密集" in payload["negative_prompt"]
    assert "保留区附近优先使用开阔地表" in prompt
    assert "大型主体紧贴保留区边界" in payload["negative_prompt"]
    assert "禁止抗锯齿、柔焦、渐变模糊、抖色、点描" in prompt


def test_stage1_prompt_defines_environmental_motifs_without_location_data():
    prompt_path = Path(__file__).resolve().parents[1] / "src" / "worldkernel" / "stage1" / "prompts" / "classify_world.md"
    text = prompt_path.read_text(encoding="utf-8")
    assert "environmental_motifs" in text
    assert "文明世界不得只列森林、水体、岩石、草地" in text
    assert "不得写具体地点名、人物或坐标" in text


def test_background_prompt_handles_worlds_without_location_slots():
    blueprint = SpatialBlueprint(
        world_id="empty-world",
        grid=BlueprintGrid(width=40, height=30, tile_size=16),
    )
    manifest = build_visual_layout_manifest(blueprint, {"visual_profile": {}}, Path("out"))
    payload = compose_background_prompt({"visual_profile": {}}, manifest)

    assert "本次底板中没有地点保留区" in payload["prompt"]
    assert "从 1 到 0" not in payload["prompt"]
