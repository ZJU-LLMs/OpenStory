## 世界背景

- 世界名称：{{world_name}}
- 来源与主题：{{world_origin_summary}}
- 主要类型：{{primary}}
- 规模：{{scope}}
- 标签：{{tags}}
- 仿真起始：{{simulation_start}}
- 世界约束：
{{world_constraints}}

## 角色种子（供参考，无需生成）
{{character_seed_summary}}

## 地点 Schema 结构

每个地点对象必须包含以下维度：
{{schema_description}}

## 待生成的地点种子（本批次 {{batch_index}}/{{total_batches}}）

{{seed_list}}

## visual 字段要求

每个地点对象必须在与 `identity`、`access`、`state` 同一层级的位置输出 `visual` 字段，值必须是一段完整自然语言提示词字符串，不能写成对象、数组，也不能拆成子字段。
`visual` 必须足够具体，可直接作为后续地点图、场景图或像素地图地点素材生成模型的参考依据。请在一段话中覆盖：建筑或空间结构、主体形状、可识别轮廓、主要材质、主色调、关键陈设或地标、光照氛围、环境装饰、适合图像生成的构图线索。
禁止只写抽象评价或空泛词，例如“很漂亮”“很神秘”“很有特色”“气氛很好”。必须写成具体可画的视觉内容，例如屋顶形状、门窗布局、墙面材质、地面纹理、标志性物件、光源位置和前中后景元素。

## 输出要求

**重要：本批次有 {{seed_count}} 个种子，你必须输出恰好 {{seed_count}} 个地点对象的 JSON 数组。不可遗漏任何种子。生成的地点必须是种子列表中的地点**
输出一个 JSON 数组，每个元素对应一个地点种子。
每个种子已有预分配的 id（见种子列表），生成时 identity.id 必须严格使用该预分配 id。
根据种子的 archetype_id、importance、role_in_world 填充各维度字段。
世界特有字段应结合世界背景知识合理填写。
core 级别的种子应有更丰富详细的描述，minor 级别可以相对简洁。

输出格式示例：
```json
[
  {{
    "identity": {{
      "id": "e:world_name:loc:001",
      "name": "地点名称",
      "type": "archetype_id",
      "description": "详细描述...",
      ...
    }},
    "access": {{
      "permissions": "...",
      "access_level": "...",
      ...
    }},
    "state": {{
      "current_state": "...",
      "ownership": "...",
      "capacity": 0,
      ...
    }}
  }}
]
```
