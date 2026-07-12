## 世界背景

- 世界名称：{{world_name}}
- 来源与主题：{{world_origin_summary}}
- 主要类型：{{primary}}
- 世界约束：
{{world_constraints}}

## 角色 Schema 要求

{{schema_description}}

## 待审核的角色数据

{{generated_characters_json}}

## visual 审核要求

必须逐个检查顶层 `visual` 字段：它必须是字符串，且与 `identity` 同一层级；不能是对象、数组，也不能拆成 `visual_description`、`visual_prompt` 等子字段。
`visual` 必须足够具体，能够直接作为后续图像生成模型的参考依据；应包含年龄感、体态轮廓、面部/发型、服装颜色材质、配饰道具、表情气质和世界观视觉符号。
如果 `visual` 只有“很漂亮”“很神秘”“有特色”等抽象评价，或与世界观不一致，或缺少可画的颜色、材质、形状、轮廓、道具细节，必须在 issues 中指出，并在 corrected_characters 中重写完整的 `visual` 一段话。

## 审核维度（每个维度 1-5 分）

1. **性格饱满度**：人物的 traits, values 和 speech_style 是否符合设定？是否过于单薄？
2. **世界一致性**：角色的背景、门第、特殊能力是否与世界约束保持一致？
3. **原型契合度**：角色是否准确体现了其 role/archetype 的特征？
4. **区分度**：同类角色之间是否有足够差异化？
5. **层级合理性**：core/major/minor 的重要性差异是否在动机复杂度和人设深度上体现出来？
6. **地点绑定合规性**：`state.position` 是否严格留空为 {}？`state.location` 是否正确绑定了地点，且格式严格为 {"location_id": "具体的地点ID"}？
7. **对象格式合规性**：诸如 knowledge 等复合对象字段，是否正确使用了 JSON 字典（如 {"description": "..."}），而不是纯文本字符串？

## 输出格式

请严格输出以下 JSON 格式：

{
  "review": {
    "scores": {
      "personality_richness": 0,
      "world_consistency": 0,
      "archetype_fit": 0,
      "differentiation": 0,
      "importance_tiering": 0,
      "location_binding_compliance": 0,
      "object_format_compliance": 0,
      "visual_prompt_quality": 0
    },
    "overall_score": 0.0,
    "issues": ["具体问题描述1", "具体问题描述2"],
    "corrections": [
      {"index": 0, "field": "state.location", "reason": "修正原因", "suggested": {"location_id": "e:xxx"}}
    ]
  },
  "corrected_characters": []
}

如发现任何问题，在 issues 中列出，在 corrections 中说明具体修正，corrected_characters 中输出修正后的完整 JSON 数组。
