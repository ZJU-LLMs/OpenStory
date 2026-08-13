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
`visual` 专门服务于后续 2D RPG 地图地点素材生成，必须描述一个可进入、可行走、可贴入世界地图的地点场景，而不是概念插画。
每段 `visual` 必须覆盖：地点属于室内剖面房间还是开放场景、整体平面结构、地面与墙体或边界、主要材质和主色、3 至 5 个完整且容易辨认的标志性陈设、装饰密度、照明色调、需要保留的可行走空间。
室内地点使用无屋顶的 RPG 剖面房间；庭院、公园、广场、码头、车站等室外地点使用同一俯视投影的开放场景。地点差异应由结构、配色和少量标志物体现，不能依靠增加纹理噪声或堆满小物件体现。
禁止在 `visual` 中要求平视、斜俯视、透视纵深、前景/中景/背景叙事、镜头焦段、写实污渍、霉斑裂缝、微小文字、复杂材质、密集碎物、高频纹理、固定人物或地点标签。禁止只写“很漂亮”“很神秘”“很有特色”等抽象评价。

## 输出要求

**重要：本批次有 {{seed_count}} 个种子，你必须输出恰好 {{seed_count}} 个地点对象的 JSON 数组。不可遗漏任何种子。生成的地点必须是种子列表中的地点**
输出一个 JSON 数组，每个元素对应一个地点种子。
每个种子已有预分配的 id（见种子列表），生成时 identity.id 必须严格使用该预分配 id。
`identity.importance` 必须逐字复制对应种子的 `importance`，值只能是 `core`、`major` 或 `minor`；不得依据描述、容量或访问等级重新推断。
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
      "importance": "core",
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
    }},
    "visual": "无屋顶的俯视 RPG 地点场景，描述平面结构、主材质、主色、3 至 5 个标志性陈设、装饰密度和可行走空间。"
  }}
]
```
