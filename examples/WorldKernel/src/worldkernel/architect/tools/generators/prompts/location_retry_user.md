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
重写时必须覆盖建筑或空间结构、主体形状、可识别轮廓、主要材质、主色调、关键陈设或地标、光照氛围、环境装饰、适合图像生成的构图线索，并避免“很漂亮”“很神秘”“有特色”等空泛表达。

## 输出要求

**重要：本批次有 {{seed_count}} 个种子，你必须输出恰好 {{seed_count}} 个地点对象的 JSON 数组。不可遗漏任何种子。**
输出一个 JSON 数组，每个元素对应一个地点种子。
每个种子已有预分配的 id（见种子列表），生成时 identity.id 必须严格使用该预分配 id。
请特别注意审核反馈中提到的问题，针对性改进。
