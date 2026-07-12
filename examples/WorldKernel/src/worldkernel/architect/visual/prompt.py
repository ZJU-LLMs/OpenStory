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
    motifs = _join(profile.get("environmental_motifs") or [])
    slot_count = len(manifest.slots)
    visual_clearance_tiles = int(manifest.canvas.get("visual_clearance_tiles") or 0)
    if slot_count:
        slot_instruction = (
            f"布局控制参考图共有 {slot_count} 个带编号的地点体块。必须从 1 到 {slot_count} 逐个确认，"
            "不得遗漏任何编号对应的占用区域。编号仅用于核对布局，不得把数字、编号颜色或标记画进背景。"
        )
    else:
        slot_instruction = "本次布局没有地点体块，不需要预留建筑位置；仍须遵守道路蒙版和整体构图约束。"
    prompt_lines = [
        "根据输入的中性地形底板、透明保护蒙版和布局控制参考图，一次性生成连续、完整的世界地图背景。",
        (
            "布局控制参考图中每个完整的矩形建筑体块都表示一处已经被未来建筑、院落或场所占用的位置，狭长连通走廊表示"
            "已经确定的道路位置。这些体块和走廊与蒙版完全重合，是必须保留的真实空间约束，不是空白区域。"
            "只能围绕它们组织背景环境，不得在它们背后、下方或上方继续铺设其他建筑。体块的灰色只是控制图标记，"
            "后端会在最终地图中用连续地形替换，不得把灰色体块扩散、复制或当作背景美术风格。"
        ),
        slot_instruction,
        (
            f"每个地点体块外侧的橙色框表示 {visual_clearance_tiles} 个网格宽的视觉净空环。净空环只用于降低装饰密度，"
            "不是地点蒙版，也不会改变地点贴片尺寸。净空环内优先保持连续地面、或水面，尽量不要有装饰。"
    
        ),
        (
            "蒙版已经由接口和后端精确处理，不得重画、复制、移动、扩展或近似复现其形状。"
            "可编辑区域允许保留明显的连续开阔地面或水面，不要求风物覆盖每一处。"
            "不得在原始位置旁边生成第二个偏移建筑体块、偏移道路、灰白矩形、空白方块或布局草图。"
        ),
        (
            "构图时应把每个地点体块理解为一座已经存在的完整地点主体，背景只负责地点主体之间的环境。"
            "不得先设计跨越体块的大型建筑或设施，再让蒙版把其中间部分遮掉。"
        ),
        f"固定全局画风（最高优先级）：{FIXED_PIXEL_ART_STYLE}",
        f"世界设定：{_world_context(world_background, profile)}",
    ]
    if motifs:
        prompt_lines.append(f"世界通用风物参考：{motifs}")
    prompt_lines.extend(
        [
            "构图要求：",
            "1. 在可编辑区域内整体规划地表、水体、低矮植被、通用建筑、公共设施、交通元素、生活器具和景观装饰。装饰保持中等密度、较为丰富但疏密有致；完整性优先于数量，允许保留较大开阔区域，严禁为了填满画面而增加主体。",
            "2. 文明世界应使用符合时代的建筑、设施和生活风物建立辨识度，但这些元素只需分散点缀，不得密集铺满地图。所有元素必须符合当前世界的时代与文化，不要混用其他时代。",
            "3. 保护区域就是后续地点素材和程序道路的精确尺寸，由接口自动保留。不得改变、覆盖或缩放这些区域；更不得在可编辑区域内另画一套保护区域。地点矩形的边缘就是未来地点主体的精确边缘，不得把背景建筑延伸到矩形内部或藏在矩形下方。",
            "4. 每一栋背景建筑、亭台、桥梁、围墙、车辆和大型树木都必须在可编辑区域内形成独立、完整、闭合且清晰可辨的整体。先确认其屋顶、墙体、底座、轮廓、附属结构和阴影全部位于可编辑区域，再绘制主体；严禁出现被地点矩形挖去一块的建筑、半栋建筑或突然中断的结构。",
            "5. 地点视觉净空环内优先保持为开阔地表、水岸、草地或水面，尽量不要有装饰。不要在净空环内排列屋顶、围墙、门廊、桥身、大型岩石、树干、树冠或其他装饰；这只是构图引导，不得扩大或改变保护区域。",
            "6. 视觉丰富度来自完整风物、明确轮廓和有限色阶，而不是写实材质或细碎像素纹理。",
            "7. 使用严格垂直向下的正交俯视视角。不绘制道路和通行路线；道路稍后由程序按照第二阶段生成的坐标叠加。",
            "8. 不绘制人物、可读文字、地点名称、地图标签或界面元素。",
        ]
    )
    negative = (
        "重复蒙版，偏移蒙版，复制蒙版形状，第二套地点占位，第二套道路占位，灰色矩形，白色矩形，空白方块，"
        "占位底板，狭长空白带，空白道路网络，布局草图，主体跨越保护区，建筑藏在地点矩形下方，"
        "装饰过度密集，风物铺满画面，为填满空地而增加主体，大型主体紧贴地点边界，"
        "建筑进入视觉净空环，围墙进入视觉净空环，亭子进入视觉净空环，树木进入视觉净空环，"
        "被地点矩形挖空的建筑，残缺建筑，半栋建筑，缺失建筑中部，"
        "被截断屋顶，被截断墙体，被截断底座，被截断围墙，被截断桥梁，突然中断的门廊，物体贴住保护边界，"
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
