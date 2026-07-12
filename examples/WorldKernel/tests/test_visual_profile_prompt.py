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
    assert "在可编辑区域内形成独立、完整、闭合且清晰可辨的整体" in prompt
    assert "不得人为扩大或改变保护区域" in prompt
    assert "地点矩形的边缘就是未来地点主体的精确边缘" in prompt
    assert "不得在可编辑区域内另画一套保护区域" in prompt
    assert "空白道路网络" in payload["negative_prompt"]
    assert "禁止抗锯齿、柔焦、渐变模糊、抖色、点描" in prompt


def test_stage1_prompt_defines_environmental_motifs_without_location_data():
    prompt_path = Path(__file__).resolve().parents[1] / "src" / "worldkernel" / "stage1" / "prompts" / "classify_world.md"
    text = prompt_path.read_text(encoding="utf-8")
    assert "environmental_motifs" in text
    assert "文明世界不得只列森林、水体、岩石、草地" in text
    assert "不得写具体地点名、人物或坐标" in text
