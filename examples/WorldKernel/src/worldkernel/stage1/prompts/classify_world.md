你是一个世界模版构建模块。

以下是对用户意图的解析结果：

{{intent_summary}}

请根据以上意图，构建该世界的通用基础模版。
基于世界背景知识，自由描述并补全该世界的所有核心要素。

所有字段必须在同一层级的扁平 JSON 中输出（simulation_start 和 visual_profile 除外，它们是嵌套对象）。

**输出字段：**
- primary：主类型英文标识（如 magic_school / feudal_court / dystopian_city）
- secondary：次要类型标识（可为 null）
- confidence：置信度（0 到 1）
- tags：描述该世界特性的标签列表
- world_name：世界或场所的名称
- world_origin_summary：来源与主题摘要（一两句话）
- scope：世界规模（single_location / district / city / region / world）
- simulation_start：嵌套对象，仿真起始时间节点
  - time_point：具体时间点描述（如"1997学年开学"）
  - trigger_event：触发该时间节点的关键事件（如"邓布利多去世后食死徒控制霍格沃茨"）
  - year：年份字符串
  - narrative_context：该时间点的叙事背景（一句话）
- visual_profile：嵌套对象，世界级视觉规范。它只描述整个世界共享的美术基调与通用风物，不得包含具体地点、路径、房间、人物、地图坐标或 bounds。固定采用俯视角卡通像素风世界地图背景和轻松冒险、模拟经营游戏的像素美术语言；世界题材可以变化，但渲染语言必须保持明亮、可爱、整洁、低纹理密度和清晰可读
  - art_style：固定描述“原生低分辨率手工 tile/sprite 像素美术、经过设计的大像素簇、统一深色像素轮廓、平整填色、硬边块状阴影、二到四档明确色阶、简化圆润且容易辨认的卡通造型、明亮整洁的模拟经营游戏画面”；明确禁止后期像素化滤镜感、抗锯齿、柔焦、模糊、抖色、点描、颗粒、散点高光和随机纹理噪声
  - camera_projection：地图视角，必须描述“严格正交俯视，接近垂直向下的 2D 地图视角”，保持类似像素 RPG 地图空地的可拼贴视角；不要写“等距透视”“斜俯视”“场景视角”或“2.5D 建筑视角”
  - era_style：时代与文化视觉风格
  - color_palette：颜色基调列表
  - lighting_weather：统一光照、天气、时间氛围
  - material_texture：世界常见材质与纹理列表，既包括地表，也包括符合时代的建筑、设施、交通工具和公共景观材质；使用低纹理密度和大色块描述，不要写具体地点内部
  - environmental_motifs：世界中普遍存在的非地点专属风物列表，包括通用建筑形态、公共设施、交通元素、街景陈设、生产生活器具和景观装饰。必须根据时代、文化与文明形态生成；文明世界不得只列森林、水体、岩石、草地等自然景观。不得写具体地点名、人物或坐标
  - atmosphere：整体情绪与环境气质
  - edge_blending_style：后续地点贴片与背景融合的边缘风格，应强调像素绘画下的柔和像素羽化、自然遮挡、地形纹理过渡
  - negative_visual_constraints：视觉禁令列表，列出：不要人物、不要肖像、不要可读文字、不要标签、不要界面图标、不要地点名、不要具体室内细节、不要等距透视、不要斜俯视场景插画、不要写实材质、不要高频微小纹理；不要禁止符合世界设定的通用建筑、设施、交通与风物
- location_archetypes：地点类型列表。**必须列出该世界中所有不同类型的地点**（如教学空间、公共区域、宿舍区、户外空间、功能区等），每种类型一项，每项包含：
  - type_id：类型英文标识（snake_case）
  - type_name：类型中文名
  - description：该类地点在该世界中的作用
  - common_fields：该类地点常见的字段列表（snake_case）
  - candidate_location_seeds：该类型下 **1 个**代表性实例，包含
    - seed_id（snake_case）、name、importance（core/major/minor）
    - source_type（canonical/inferred/original）、confidence、generation_priority、role_in_world
- character_archetypes：人物身份类型列表。**必须列出该世界中所有不同类型的人物身份**（如学生、教职工、反派等），每种类型一项，结构同 location_archetypes
  - candidate_character_seeds：该类型下 **1 个**代表性实例，字段同上
- rule_archetypes：规则类型列表。**必须列出该世界中所有不同类型的规则**，每种类型一项，结构同 location_archetypes
  - candidate_rule_seeds：该类型下 **1 个**代表性实例，字段同上
- world_constraints：高层世界观约束列表（2-4 条），每项包含
  - constraint_id（snake_case）、name、description、scope（global/faction/location）
  - 约束应是世界运行的根本前提，不是具体执行规则

**重要**：archetypes 列表必须覆盖完整，不要只列一种类型。例如霍格沃茨的 character_archetypes 应包含「学生」「教职工」「食死徒管控者」等所有身份类型，而非只列「学生」。

**输出示例（扁平结构）：**
```json
{
  "primary": "magic_school",
  "secondary": null,
  "confidence": 0.95,
  "tags": ["魔法", "学院", "衍生", "黑暗时期"],
  "world_name": "霍格沃茨魔法学院",
  "world_origin_summary": "衍生自《哈利·波特》系列第七部，食死徒统治下的霍格沃茨",
  "scope": "single_location",
  "simulation_start": {
    "time_point": "1997-1998学年开学",
    "trigger_event": "斯内普就任校长，卡罗兄妹入驻，学院进入恐怖统治期",
    "year": "1997",
    "narrative_context": "邓布利多去世后，食死徒通过傀儡政府控制了霍格沃茨，学生在严酷管制下秘密组建抵抗力量"
  },
  "visual_profile": {
    "art_style": "俯视角手工卡通像素风世界地图，原生低分辨率 tile/sprite 像素美术语言，经过设计的大像素簇、统一深色像素轮廓、平整填色、硬边块状阴影、二到四档明确色阶、简化圆润造型，整体明亮、可爱、整洁",
    "camera_projection": "严格正交俯视，接近垂直向下的 2D 地图视角",
    "era_style": "二十世纪九十年代末，被战时高压统治笼罩的英国魔法寄宿学校",
    "color_palette": ["明亮石灰色", "温暖琥珀色", "学院深蓝", "羊皮纸米黄", "魔法紫"],
    "lighting_weather": "明亮均匀的日间光照，温暖魔法灯光，短而柔和的卡通阴影",
    "material_texture": ["大色块草地", "简化石墙与瓦顶", "低纹理石材", "明亮水面", "木质设施"],
    "environmental_motifs": ["石拱廊与低矮塔楼屋顶", "魔法路灯", "猫头鹰栖架", "石像与喷泉", "木质推车", "长椅与旗帜装饰"],
    "atmosphere": "oppressive, secretive, ancient, magical, wartime tension",
    "edge_blending_style": "柔和像素羽化的地形边缘、草地过渡与自然遮挡，便于后续叠加地点贴片",
    "negative_visual_constraints": [
      "不要人物",
      "不要肖像",
      "不要可读文字",
      "不要标签",
      "不要界面图标",
      "不要地点名",
      "不要具体室内细节",
      "不要天空",
      "不要地平线",
      "不要等距透视",
      "不要斜俯视场景插画",
      "不要写实材质",
      "不要高频微小纹理"
    ]
  },
  "location_archetypes": [
    {
      "type_id": "teaching_space",
      "type_name": "教学空间",
      "description": "承载日常教学活动的课室与讲堂，也是师生冲突的主要场所",
      "common_fields": ["subject", "professor_id", "capacity", "access_level"],
      "candidate_location_seeds": [
        {
          "seed_id": "dark_arts_classroom",
          "name": "黑魔法防御课教室",
          "importance": "core",
          "source_type": "canonical",
          "confidence": 0.98,
          "generation_priority": 1,
          "role_in_world": "卡罗兄妹实施惩罚的主要场所"
        }
      ]
    },
    {
      "type_id": "communal_space",
      "type_name": "公共区域",
      "description": "师生共用的聚集与交流空间",
      "common_fields": ["capacity", "access_level", "typical_events"],
      "candidate_location_seeds": [
        {
          "seed_id": "great_hall",
          "name": "大礼堂",
          "importance": "core",
          "source_type": "canonical",
          "confidence": 0.99,
          "generation_priority": 1,
          "role_in_world": "全校集会与用餐的核心场所"
        }
      ]
    },
    {
      "type_id": "dormitory",
      "type_name": "宿舍区",
      "description": "各学院学生的住宿空间，也是小团体活动的私密场所",
      "common_fields": ["house", "capacity", "security_level"],
      "candidate_location_seeds": [
        {
          "seed_id": "gryffindor_tower",
          "name": "格兰芬多塔楼",
          "importance": "major",
          "source_type": "canonical",
          "confidence": 0.95,
          "generation_priority": 2,
          "role_in_world": "格兰芬多学生的住所，秘密策划反抗的据点"
        }
      ]
    }
  ],
  "character_archetypes": [
    {
      "type_id": "student",
      "type_name": "学生",
      "description": "在管制下求学的巫师青少年，兼具受害者与潜在抵抗者的双重身份",
      "common_fields": ["house", "year", "blood_status", "da_member"],
      "candidate_character_seeds": [
        {
          "seed_id": "neville_longbottom",
          "name": "纳威·隆巴顿",
          "importance": "core",
          "source_type": "canonical",
          "confidence": 0.99,
          "generation_priority": 1,
          "role_in_world": "DA实际领导者，象征普通人在压迫下的觉醒"
        }
      ]
    },
    {
      "type_id": "faculty",
      "type_name": "教职工",
      "description": "留任的教师，在食死徒监视下艰难维持教学或暗中保护学生",
      "common_fields": ["subject", "loyalty", "teaching_years"],
      "candidate_character_seeds": [
        {
          "seed_id": "mcgonagall",
          "name": "米勒娃·麦格",
          "importance": "core",
          "source_type": "canonical",
          "confidence": 0.99,
          "generation_priority": 1,
          "role_in_world": "暗中保护学生的核心教职，最终战役的指挥者之一"
        }
      ]
    },
    {
      "type_id": "death_eater_staff",
      "type_name": "食死徒管控者",
      "description": "伏地魔派驻霍格沃茨的食死徒，负责执行恐怖管制",
      "common_fields": ["rank", "cruelty_level", "surveillance_area"],
      "candidate_character_seeds": [
        {
          "seed_id": "amycus_carrow",
          "name": "阿米库斯·卡罗",
          "importance": "major",
          "source_type": "canonical",
          "confidence": 0.97,
          "generation_priority": 1,
          "role_in_world": "负责黑魔法课教学与学生惩罚的食死徒"
        }
      ]
    }
  ],
  "rule_archetypes": [
    {
      "type_id": "disciplinary_rule",
      "type_name": "纪律规则",
      "description": "食死徒政权强加的惩戒体系，以恐惧和痛苦维持秩序",
      "common_fields": ["enforcer", "punishment_type", "trigger_condition", "severity"],
      "candidate_rule_seeds": [
        {
          "seed_id": "unforgivable_detention",
          "name": "以禁忌魔咒作为惩罚",
          "importance": "core",
          "source_type": "canonical",
          "confidence": 0.97,
          "generation_priority": 1,
          "role_in_world": "卡罗兄妹暴行的核心象征"
        }
      ]
    },
    {
      "type_id": "access_control",
      "type_name": "准入管控",
      "description": "限制人员流动和信息传递的管控措施",
      "common_fields": ["restricted_area", "time_range", "detection_method"],
      "candidate_rule_seeds": [
        {
          "seed_id": "curfew",
          "name": "宵禁令",
          "importance": "major",
          "source_type": "canonical",
          "confidence": 0.95,
          "generation_priority": 1,
          "role_in_world": "限制学生夜间活动，压制抵抗组织行动"
        }
      ]
    }
  ],
  "world_constraints": [
    {
      "constraint_id": "magical_secrecy",
      "name": "魔法世界保密法",
      "description": "巫师不得在麻瓜面前暴露魔法的存在",
      "scope": "global"
    },
    {
      "constraint_id": "death_eater_control",
      "name": "食死徒政权管控",
      "description": "学院由斯内普及卡罗兄妹实际控制，公开反抗将招致严酷惩罚",
      "scope": "location"
    }
  ]
}
```
