from __future__ import annotations

from typing import Any

from worldkernel.architect.visual.models import VisualLayoutManifest


FIXED_PIXEL_ART_STYLE = (
    "俯视角手工卡通像素风世界地图背景，采用经典轻松冒险游戏与温馨模拟经营游戏的原生 tile/sprite 像素美术语言。"
    "每个物体由经过设计的较大像素簇组成，不要表现成高分辨率插画或后期像素化滤镜。"
    "使用有限且协调的调色板、统一清晰的深色像素轮廓、平整连续的填充色。"
    "建筑、设施、树木和景物采用简化、圆润、容易辨认的卡通造型，每个物体内部只使用二到四档明确色阶。"
    "画面整体明亮、可爱、整洁。禁止抗锯齿、柔焦、渐变模糊、抖色、点描、颗粒、散点高光和随机纹理噪声。"
)


def compose_background_prompt(
    world_background: dict[str, Any],
    manifest: VisualLayoutManifest,
) -> dict[str, Any]:
    profile = dict(world_background.get("visual_profile") or {})
    motifs = _join((profile.get("environmental_motifs") or [])[:6])
    slot_count = len(manifest.slots)
    clearance_tiles = max(1, int(manifest.canvas.get("visual_clearance_tiles") or 0))
    slot_instruction = (
        f"底板中共有 {slot_count} 个中灰色地点保留区。所有保留区都已由硬蒙版锁定，必须在整体构图中逐一避开。"
        if slot_count
        else "本次底板中没有地点保留区，但仍须遵守道路保留区。"
    )
    prompt_lines = [
        "请把第一张输入底板编辑成符合当前世界设定的完整地图背景，只重新绘制深色可编辑区域。",
        "图中灰色矩形是未来地点图像的精确保留区，浅灰色狭长区域是未来道路图像的精确保留区。灰色区域不是建筑、平台或地形，不得修改、移动、缩放、复制或另画一套，也不要沿灰色区域增加外轮廓、描边、阴影、光晕或底座。",
        slot_instruction,
        (
            "所有建筑、设施、树木、桥梁、围墙、车辆和大型装饰都必须完整落在深色可编辑区域内，不得跨入灰色保留区。"
            f"每个灰色地点矩形外侧至少保留约 {clearance_tiles} 个网格宽的连续地表、水面或低矮铺装；这个净空带仍属于可编辑背景，不得画成新的框。"
            "大型主体的屋顶、墙体、底座、树冠、阴影和附属结构都必须与灰色区域完全分离，宁可少画，也不要截断。"
        ),
        (
            "背景采用低到中等风物密度。大型建筑和大型设施只作少量、彼此分散的完整点缀；"
            "开阔地表、水面和低矮铺装的面积必须明显多于大型主体与装饰。"
            "中小型风物也要成组留白，不要连续铺满，不要为了填满画面而增加主体。"
        ),
        f"固定全局画风（最高优先级）：{FIXED_PIXEL_ART_STYLE}",
        f"世界设定：{_world_context(world_background, profile)}",
    ]
    if motifs:
        prompt_lines.append(
            f"世界通用风物候选：{motifs}。这些只是题材候选，不要求逐项画出；按低密度选择少量最合适的完整元素。"
        )
    prompt_lines.extend(
        [
            "使用严格垂直向下的正交俯视视角。不要绘制道路、通行路线、具体地点主体、人物、可读文字、地点名称、地图标签或界面元素。",
            "视觉丰富度来自完整风物、清楚轮廓、较大像素簇和有限色阶，不使用写实材质、细碎纹理或模糊效果。",
        ]
    )
    negative = (
        "修改灰色保留区，移动保留区，复制保留区，保留区外轮廓，保留区描边，保留区阴影，保留区光晕，"
        "第二套地点占位，第二套道路占位，偏移道路，布局草图，"
        "主体跨越保留区，建筑藏在保留区下方，残缺建筑，半栋建筑，被截断屋顶，被截断墙体，被截断围墙，"
        "装饰过度密集，风物铺满画面，为填满空地而增加主体，大型主体紧贴保留区边界，默认草地，所有世界都是草地，"
        "写实风格，照片质感，高分辨率插画感，后期像素化滤镜，厚涂，复杂材质，高频微小纹理，密集噪点，"
        "抗锯齿，柔焦，模糊渐变，抖色，点描，颗粒，散点高光，随机斑点，逐片屋瓦，密集砖缝，"
        "斜俯视，等距透视，天空，地平线，道路，通行路线，人物，可读文字，地点名称，地图标签，界面元素"
    )
    return {
        "prompt": "\n".join(prompt_lines),
        "negative_prompt": negative,
        "target_size": {
            "width": int(manifest.canvas.get("width_px") or 0),
            "height": int(manifest.canvas.get("height_px") or 0),
        },
        "visual_profile": profile,
        "asset_contract": manifest.asset_contract,
    }


def _world_context(world_background: dict[str, Any], profile: dict[str, Any]) -> str:
    values = [
        f"世界名称：{world_background.get('world_name', '')}",
        f"来源与主题：{world_background.get('world_origin_summary', '')}",
        f"世界类型：{world_background.get('primary', '')} / {world_background.get('secondary', '') or ''}",
        f"标签：{_join(world_background.get('tags') or [])}",
        f"时代与文化：{profile.get('era_style', '')}",
        f"颜色：{_join(profile.get('color_palette') or [])}",
        f"光照：{profile.get('lighting_weather', '')}",
        f"氛围：{profile.get('atmosphere', '')}",
    ]
    return "；".join(value for value in values if value.split("：", 1)[-1].strip(" /"))


def _join(values: list[Any]) -> str:
    return "、".join(str(value) for value in values if value)
