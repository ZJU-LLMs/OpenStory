## 世界背景

- 世界名称：{{world_name}}
- 来源与主题：{{world_origin_summary}}
- 主要类型：{{primary}}
- 世界约束：
{{world_constraints}}

## 地点 Schema 要求

{{schema_description}}

## 待审核的地点数据

```json
{{generated_locations_json}}
```

## visual 审核要求

`identity.importance` 是来自种子目录的空间布局等级，只能是 `core`、`major` 或 `minor`。审核不得删除、改写或根据地点描述、容量、访问等级重新推断该字段；`corrected_locations` 必须原样保留每个地点已有的 `identity.importance`。

必须逐个检查顶层 `visual` 字段：它必须是字符串，且与 `identity` 同一层级；不能是对象、数组，也不能拆成 `visual_description`、`visual_prompt` 等子字段。
`visual` 必须能够直接用于后续 2D RPG 地图地点素材生成；应明确室内剖面房间或开放场景、平面结构、地面与墙体或边界、主要材质和主色、3 至 5 个完整标志性陈设、装饰密度、照明色调和可行走空间。
必须拒绝平视、斜俯视、透视纵深、前景/中景/背景叙事、写实污渍、微小文字、复杂材质、密集碎物、高频纹理、固定人物和地点标签。地点差异应来自结构、配色和少量标志物，不能来自噪声或过度堆叠。
如果 `visual` 只有抽象评价、与世界观不一致、缺少地图可用结构，或包含上述禁用内容，必须在 issues 中指出，并在 corrected_locations 中重写完整的地图专用 `visual` 字符串。

## 审核维度（每个维度 1-5 分）

1. **叙事丰富度**：描述是否有画面感和沉浸感？是否让人能想象出这个地点的样子？
2. **世界一致性**：地点是否与世界约束保持一致？是否存在违反世界观的设定？
3. **原型契合度**：地点是否准确体现了其 archetype 的特征？
4. **区分度**：同一 archetype 下的不同地点是否有足够差异？（不能雷同）
5. **层级合理性**：core/major/minor 的重要性差异是否在描述深度和字段丰富度上体现出来？
6. **社交网络关联**：description 中是否合理提及了可能的 resident_npcs 或相关角色？
7. **access/state 合理性**：访问控制和状态描述是否符合该地点在叙事中的定位？

## 输出格式

```json
{{
  "review": {{
    "scores": {{
      "narrative_richness": 0,
      "world_consistency": 0,
      "archetype_fit": 0,
      "differentiation": 0,
      "importance_tiering": 0,
      "social_links": 0,
      "access_state_fit": 0,
      "visual_prompt_quality": 0
    }},
    "overall_score": 0.0,
    "issues": ["具体问题描述1", "具体问题描述2"],
    "corrections": [
      {{"index": 0, "field": "identity.description", "reason": "修正原因", "suggested": "修正后的内容"}}
    ]
  }},
  "corrected_locations": [...]
}}
```

如发现任何问题，在 issues 中列出，在 corrections 中说明具体修正，corrected_locations 中输出修正后的完整 JSON 数组。
如无问题，issues 为空数组，corrections 为空数组，corrected_locations 原样输出。
