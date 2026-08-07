from __future__ import annotations

import re
from typing import Any

from worldkernel.architect.visual.models import VisualSlot


def compose_location_patch_prompt(
    *,
    world_background: dict[str, Any],
    visual_profile: dict[str, Any],
    location: dict[str, Any],
    slot: VisualSlot,
    generation_size: tuple[int, int] | None = None,
) -> dict[str, Any]:
    bounds = slot.bounds_px
    target_width = int(bounds.get("w") or 0)
    target_height = int(bounds.get("h") or 0)
    request_width, request_height = generation_size or (target_width, target_height)
    identity = _dict(location.get("identity"))
    name = str(
        location.get("name")
        or location.get("location_name")
        or identity.get("name")
        or slot.location_id
    )
    location_type = str(
        location.get("location_type")
        or location.get("type")
        or identity.get("type")
        or ""
    )
    tags = _join(location.get("tags") or identity.get("tags") or [])
    visual = str(location.get("visual") or location.get("map_patch_hint") or "").strip()
    description = str(location.get("description") or identity.get("description") or "").strip()
    if not visual:
        visual = description or f"{name}，{location_type}".strip("，")
    visual = _compact_map_visual(visual)
    entrance = _entrance_description(slot.entrance_port)

    prompt = "\n".join(
        [
            "请在输入的局部世界地图上完成一个可进入的 2D RPG 地点场景。",
            "输入图是已经清除临时道路颜色的地点周边环境，不包含最终道路。蒙版内是包含地点核心与自然过渡边缘的完整视觉编辑区；蒙版外保持原有构图、主体位置和环境连续性。",
            "延续周边背景的色板、像素簇大小、硬边轮廓宽度、材质处理、光照方向和明暗层级，让地点看起来原本就属于这张连续地图。",
            "地板保持正交俯视；室内地点使用无屋顶剖面房间，南向墙体只显示一至两格高的统一立面；室外地点使用同投影的开放场景。",
            f"入口接口：{entrance}。请只按该坐标在地点边缘留下畅通的门口或开放缺口；最终道路会在后续图层中连接到这里，不要自行绘制道路或彩色入口占位块。",
            "地点边缘必须表现为完整墙体、围栏、平台边缘或自然地形边界；不要生成独立相框、卡片底板、悬浮阴影或图片边框。",
            "只使用少量完整、容易辨认的标志性陈设表达地点语义，中间保留清晰可行走区域；所有主体必须完整落在可编辑区域内。",
            "采用明亮整洁的卡通像素游戏语言：较大像素色块、有限色阶、低纹理密度、清晰硬边和简化圆润造型。",
            "不生成固定人物、地点名、可读文字、UI、地图标签、屋顶、平视立面或复杂透视。",
            f"世界背景：{_world_context(world_background)}",
            f"全局视觉规范：{_visual_context(visual_profile)}",
            f"地点名称：{name}",
            f"地点类型：{location_type}",
            f"地点标签：{tags}",
            f"地点地图视觉：{visual}",
        ]
    )
    negative = (
        "修改蒙版外背景，改变入口坐标，自行绘制道路，黄色方块，彩色入口占位块，临时道路标记，独立矩形插画，卡片边框，悬浮阴影，屋顶，建筑外观立面，"
        "平视摄影，斜俯视，等距透视，远景，人物，人群，地点名，可读文字，UI，地图标签，"
        "裁切墙体，半个房间，主体越界，陈设堵塞入口，过度拥挤，细碎颗粒，抖色，噪点，复杂纹理，"
        "写实材质，抗锯齿，模糊，后期像素化滤镜，改变周边色板，改变光照方向"
    )
    return {
        "prompt": prompt,
        "negative_prompt": negative,
        "target_size": {"width": target_width, "height": target_height},
        "generation_size": {"width": request_width, "height": request_height},
        "location_id": slot.location_id,
        "location_name": name,
        "location_type": location_type,
        "patch_view": "rpg_top_down_cutaway",
        "entrance_port": dict(slot.entrance_port),
        "visual_profile": _patch_visual_profile(visual_profile),
    }


def _world_context(world_background: dict[str, Any]) -> str:
    parts = [
        world_background.get("world_name"),
        world_background.get("world_origin_summary"),
        world_background.get("primary"),
        world_background.get("secondary"),
        _join(world_background.get("tags") or []),
    ]
    return "；".join(str(part) for part in parts if str(part or "").strip())


def _visual_context(profile: dict[str, Any]) -> str:
    parts = []
    for key, value in _patch_visual_profile(profile).items():
        if value:
            parts.append(f"{key}={_join(value) if isinstance(value, list) else value}")
    return "；".join(parts)


def _patch_visual_profile(profile: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "art_style",
        "era_style",
        "color_palette",
        "lighting_weather",
        "material_texture",
        "atmosphere",
    ]
    return {key: profile.get(key) for key in keys if profile.get(key)}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _join(values: Any) -> str:
    if isinstance(values, list):
        return "、".join(str(value) for value in values if str(value or "").strip())
    return str(values or "")


def _compact_map_visual(value: str, *, max_chars: int = 800) -> str:
    blocked = (
        "平视", "斜俯视", "透视", "镜头", "焦距", "特写",
        "前景", "中景", "背景是", "构图上", "可读文字", "手写",
    )
    sentences = re.split(r"(?<=[。！？；])|\n+", value)
    kept = [
        sentence.strip()
        for sentence in sentences
        if sentence.strip() and not any(token in sentence for token in blocked)
    ]
    compact = "".join(kept) or value.strip()
    return compact[:max_chars].rstrip("，。； ")


def _entrance_description(port: dict[str, Any]) -> str:
    labels = {"north": "上边", "south": "下边", "west": "左边", "east": "右边"}
    side = str(port.get("side") or "south")
    offset = int(port.get("offset_tiles") or 0)
    width = max(1, int(port.get("width_tiles") or 1))
    depth = max(1, int(port.get("entry_depth_tiles") or 1))
    return (
        f"入口位于地点{labels.get(side, '下边')}第 {offset + 1} 格，"
        f"宽 {width} 格，向场景内部延伸 {depth} 格"
    )
