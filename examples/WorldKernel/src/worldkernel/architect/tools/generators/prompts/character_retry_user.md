## 世界背景

- 世界名称：{{world_name}}
- 来源与主题：{{world_origin_summary}}
- 主要类型：{{primary}}
- 世界约束：
{{world_constraints}}

## 上一轮审核发现的问题

{{review_issues}}

## 角色 Schema 结构

{{schema_description}}

## 核心地点参考（用于为角色分配 state.location）
{{location_seed_summary}}

## 待重新生成的角色种子

{{seed_list}}

## visual 重写要求

如果审核反馈涉及 `visual`，必须重写完整的顶层 `visual` 字符串，不要只追加一句补充说明。
`visual` 与 `identity`、`state` 同一层级，值只能是一段自然语言提示词字符串；不能输出对象、数组或 `visual_description`、`visual_prompt` 子字段。
重写时必须覆盖年龄感、体态轮廓、面部/发型、服装款式、服装主色与材质、代表性配饰或随身道具、气质表情、与世界观相关的视觉符号，并避免“很漂亮”“很神秘”“有特色”等空泛表达。

## 输出要求

**重要：本批次有 {{seed_count}} 个种子，你必须输出恰好 {{seed_count}} 个角色对象的 JSON 数组。不可遗漏任何种子。**
输出一个 JSON 数组，每个元素对应一个角色种子。
1. `identity.id` 必须严格使用预分配 id。
2. **`state.position` 必须严格填入空对象 {}！**
3. **`state.location` 必须绑定具体地点，格式必须为 {"location_id": "对应的地点ID"}！**
4. **所有需要嵌套对象的字段（如 knowledge 等），必须输出为合法的 JSON 字典，绝不能直接输出纯文本字符串或列表！** 例如 `memories.knowledge` 必须为：
   ```json
   {"world_knowledge": ["条目1", "条目2"], "social_knowledge": ["条目1"]}
   ```

请特别注意审核反馈中提到的问题，针对性改进。
