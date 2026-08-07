## 世界背景

- 世界名称：{{world_name}}
- 来源与主题：{{world_origin_summary}}
- 主要类型：{{primary}}
- 世界约束：
{{world_constraints}}

## 上一轮审核发现的问题

{{review_issues}}

## 地点 Schema 结构

{{schema_description}}

## 角色种子（供参考）
{{character_seed_summary}}

## 待重新生成的地点种子

{{seed_list}}

## visual 重写要求

如果审核反馈涉及 `visual`，必须重写完整的顶层 `visual` 字符串，不要只追加一句补充说明。
`visual` 与 `identity`、`access`、`state` 同一层级，值只能是一段自然语言提示词字符串；不能输出对象、数组或 `visual_description`、`visual_prompt` 子字段。
重写后的 `visual` 必须专门描述可贴入世界地图的 2D RPG 地点素材：明确室内剖面房间或开放场景、平面结构、地面与墙体或边界、主要材质和主色、3 至 5 个完整标志性陈设、装饰密度、照明色调和可行走空间。
禁止平视、斜俯视、透视纵深、前景/中景/背景叙事、镜头语言、写实污渍、微小文字、复杂材质、密集碎物、高频纹理、固定人物和地点标签。地点差异应由结构、配色和少量标志物体现。

## 输出要求

**重要：本批次有 {{seed_count}} 个种子，你必须输出恰好 {{seed_count}} 个地点对象的 JSON 数组。不可遗漏任何种子。**
输出一个 JSON 数组，每个元素对应一个地点种子。
每个种子已有预分配的 id（见种子列表），生成时 identity.id 必须严格使用该预分配 id。
请特别注意审核反馈中提到的问题，针对性改进。
