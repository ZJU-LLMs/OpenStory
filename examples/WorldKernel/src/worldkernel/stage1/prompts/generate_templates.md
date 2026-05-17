你是一个通用实体模版生成模块。

世界信息：
{{world_summary}}

本体生成指引：
{{ontology_hints}}

请为「{{entity_name}}」生成通用模版的扩展属性。
该实体的维度和固有属性如下，你**只需为每个维度填写 extra 列表**（该世界独有的扩展属性）。
extra 属性应基于世界背景知识和本体指引推断，具体、有意义，使用 snake_case，不要重复固有属性。

**维度与固有属性：**
{{entity_dimensions}}

输出格式：
```json
{
  "dimensions": {
    "维度名1": { "extra": ["attr1", "attr2"] },
    "维度名2": { "extra": [...] }
  }
}
```
