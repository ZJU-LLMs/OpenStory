你是一个通用实体模版生成模块。

世界信息：
{{world_summary}}

本体生成指引：
{{ontology_hints}}

请为「{{entity_name}}」生成通用模版的扩展属性。
该实体的维度和固有属性如下，你**只需为每个维度填写 extra 列表**（该世界独有的扩展属性）。
extra 属性应基于世界背景知识和本体指引推断，具体、有意义，name 使用 snake_case，不要重复固有属性。
label_zh 是仅供玩家界面展示的简体中文字段名；player_visible 表示该字段是否对玩家有叙事意义。

**维度与固有属性：**
{{entity_dimensions}}

输出格式：
```json
{
  "dimensions": {
    "维度名1": {
      "extra": [
        {"name": "attr1", "type": "str", "label_zh": "中文字段名", "player_visible": true}
      ]
    },
    "维度名2": { "extra": [...] }
  }
}
```

type 只能是 str、int、float、bool、list_str 之一。技术性 ID、资源路径、视觉提示等字段应设置 player_visible=false。
