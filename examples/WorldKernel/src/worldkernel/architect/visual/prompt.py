from __future__ import annotations

from typing import Any

from worldkernel.architect.visual.models import VisualLayoutManifest


FIXED_PIXEL_ART_STYLE = (
    "清晰的俯视角2D RPG卡通像素地图风格，接近经典轻松冒险与温馨模拟经营游戏。"
    "画面由大片连续地表、简洁硬边轮廓和尺寸较大的完整物件组成；像素颗粒尺度统一，"
    "使用成组的大像素块塑造轮廓，不把高分辨率插画后期像素化。"
    "采用有限且协调的调色板、清楚的深色像素轮廓和平整填色，每种材质主要使用二至四档明确色阶。"
    "建筑、设施、树木与风物使用简化、圆润、容易一眼辨认的卡通造型，装饰之间留出清楚间距。"
    "整体明亮、可爱、整洁、清晰；远看先读出地形和完整物件，放大后仍保持干净像素边缘。"
)


def compose_background_prompt(
    world_background: dict[str, Any],
    manifest: VisualLayoutManifest,
) -> dict[str, Any]:
    profile = dict(world_background.get("visual_profile") or {})
    motifs = _join((profile.get("environmental_motifs") or [])[:6])
    slot_count = len(manifest.slots)
    target_width = int(manifest.canvas.get("width_px") or 0)
    target_height = int(manifest.canvas.get("height_px") or 0)
    clearance_tiles = max(1, int(manifest.canvas.get("visual_clearance_tiles") or 0))
    slot_instruction = (
        f"底板中共有 {slot_count} 个中灰色地点保留区，整体构图必须逐一避开，不得遗漏。"
        if slot_count
        else "本次底板中没有地点保留区，但仍须遵守道路保留区。"
    )
    prompt_lines = [
        (
            f"最终输出图片的物理画布必须严格保持为 {target_width}×{target_height} 像素，"
            "不得缩小、放大、裁剪、扩边或改成近似尺寸。"
        ),
        "请把上传的输入底板编辑成符合当前世界设定的完整地图背景，只重新绘制深色可编辑区域。",
        "图中灰色矩形是未来地点图像的精确保留区，浅灰色狭长区域是未来道路图像的精确保留区。灰色区域不是建筑、平台或地形，不得修改、移动、缩放、复制或另画一套，也不要沿灰色区域增加外轮廓、描边、阴影、光晕或底座。",
        slot_instruction,
        (
            "所有建筑、设施、树木、桥梁、围墙、车辆和大型装饰都必须完整落在深色可编辑区域内，不得跨入灰色保留区。"
            f"每个灰色地点矩形外侧至少保留约 {clearance_tiles} 个网格宽的连续地表、水面或低矮铺装；这个净空带仍属于可编辑背景，不得画成新的框。"
            "大型主体的屋顶、墙体、底座、树冠、阴影和附属结构都必须与灰色区域完全分离，宁可少画，也不要截断。"
        ),
        (
            "大型建筑和大型设施只作少量、彼此分散的完整点缀；"
            "地面只用少量、低频、成片的色块表现变化，不要逐格添加纹理。"
        ),
        f"固定全局画风（最高优先级）：{FIXED_PIXEL_ART_STYLE}",
        f"世界设定：{_world_context(world_background, profile)}",
    ]
    if motifs:
        prompt_lines.append(
            f"世界通用风物候选：{motifs}。这些只是题材候选，不要求逐项画出。"
        )
    prompt_lines.extend(
        [
            "使用严格垂直向下的正交俯视视角。不要绘制道路、通行路线、具体地点主体、人物、可读文字、地点名称、地图标签或界面元素。",
             (
                f"最终输出图片的物理画布必须严格保持为 {target_width}×{target_height} 像素，"
                "不得缩小、放大、裁剪、扩边或改成近似尺寸。"
            ),
        ]
    )
    negative = (
        "布局草图，建筑藏在保留区下方，照片质感，写实光影，高细节插画，后期像素化滤镜，厚涂，复杂材质，"
        "密集微型方格，逐格纹理，重复图块图案，马赛克噪声，碎片化色块，高频轮廓，过度锐化，"
        "密集杂草，密集碎石，密集小花，重复小物件，逐片屋瓦，密集砖缝，随机斑点，颗粒，抖色，点描，"
        "柔焦，模糊，平滑渐变，抗锯齿插画感，斜俯视场景插画，等距透视，天空，地平线，"
        "不按要求输出图片尺寸，或者对图片进行缩放、裁剪、扩边或改成近似尺寸"
    )
    return {
        "prompt": "\n".join(prompt_lines),
        "negative_prompt": negative,
        "target_size": {
            "width": target_width,
            "height": target_height,
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
    ]
    return "；".join(value for value in values if value.split("：", 1)[-1].strip(" /"))


def _join(values: list[Any]) -> str:
    return "、".join(str(value) for value in values if value)
