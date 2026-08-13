## 世界背景

- 世界名称：{{world_name}}
- 来源与主题：{{world_origin_summary}}
- 主要类型：{{primary}}
- 规模：{{scope}}
- 标签：{{tags}}
- 仿真起始：{{simulation_start}}
- 世界约束：
{{world_constraints}}

## 核心地点参考（用于为角色分配 state.location）
{{location_seed_summary}}

## 角色 Schema 结构

每个角色对象必须包含以下维度：
{{schema_description}}

## 待生成的角色种子（本批次 {{batch_index}}/{{total_batches}}）

{{seed_list}}

## visual 字段要求

每个角色对象必须在与 `identity`、`personality`、`state` 同一层级的位置输出 `visual` 字段，值必须是一段完整自然语言提示词字符串，不能写成对象、数组，也不能拆成子字段。
`visual` 必须足够具体，可直接作为后续人物立绘、像素角色或角色形象生成模型的参考依据。请用一段话描述：年龄感、体态轮廓、面部特征、发型、服装款式、服装主色与材质、代表性配饰或随身道具、气质表情、与世界观相关的视觉符号等。长度控制在50字以内。
禁止只写抽象评价或空泛词，例如“很漂亮”“很神秘”“很有特色”“气质独特”。必须写成具体可画的视觉内容，例如颜色、形状、材质、轮廓、道具、姿态和可识别细节。

## 输出要求

**重要：本批次有 {{seed_count}} 个种子，你必须输出恰好 {{seed_count}} 个角色对象的 JSON 数组。不可遗漏任何种子。**
输出一个 JSON 数组，每个元素对应一个角色种子。
1. **自身 ID 严格绑定：** 必须严格使用上方种子列表中的预分配 id。
2. **地点绑定与坐标留空：**
   - `state.position`（具体坐标 x/y）：**必须留空**，严格填入空对象 {}。
   - `state.location`（逻辑地点）：**必须绑定**！请根据上方的”核心地点参考”，选择最符合该角色背景的地点，并提取其 ID（例如 e:world_name:loc:001），格式必须严格为 {“location_id”: “你选择的地点ID”}。
3. **复杂嵌套对象必须是字典：** 凡是类型为 XXXGroup（如 KnowledgeGroup）或明显需要嵌套对象的字段，绝不能只填一个纯文本字符串或列表，必须填入一个合理的 JSON 字典。例如 `memories.knowledge` 字段必须为：
   ```json
   {“world_knowledge”: [“魔法知识条目1”, “条目2”], “social_knowledge”: [“社交关系条目1”]}
   ```
   **不能是列表 `[{“description”: “...”}]`，也不能是纯字符串。**

输出格式示例：
[
  {
    “identity”: {
      “id”: “e:world_name:char:001”,
      “name”: “角色名称”,
      “role”: “archetype_id”
    },
    “personality”: {
      “traits”: [“...”],
      “values”: [“...”]
    },
    “memories”: {
      “knowledge”: {
        “world_knowledge”: [“魔法知识条目1”, “条目2”],
        “social_knowledge”: [“社交关系条目1”]
      }
    },
    “state”: {
      “position”: {},
      “location”: {
        “location_id”: “e:world_name:loc:003”
      }
    }
  }
]
