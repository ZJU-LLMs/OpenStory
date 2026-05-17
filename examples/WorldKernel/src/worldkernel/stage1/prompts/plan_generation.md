你是一个世界生成计划制定模块。

世界信息：
- 用户目标：{{user_goal}}
- 世界类型：{{world_type_summary}}
- 标签：{{tags}}
- 地点类型：{{location_archetypes}}
- 人物身份类型：{{character_archetypes}}
- 规则类型：{{rule_archetypes}}
- 世界约束：{{world_constraints}}

请完成以下三项任务，输出一个 JSON 对象。

---

**任务一：扩展实体种子列表（entity_plan）**

基于上方每种 archetype 中的候选实例，**按 archetype 分组**将每类实体扩充为该世界的完整列表。
每种 archetype 下覆盖该类型所有值得生成的典型实例，数量视世界规模而定（单一场所 3-8 个/archetype，城市级 5-15 个/archetype）。

结构：以 archetype_id 为 key，值为该类型下的种子列表。

- locations：按地点类型分组（如 teaching_space、communal_space、dormitory 各自一个列表）
- characters：按人物身份类型分组（如 student、faculty、death_eater_staff 各自一个列表）
- institutions：按推断的机构类型分组
- rules：按规则类型分组

每个种子字段：
- seed_id（snake_case，全局唯一）
- name（实体名称）
- entity_type（location / character / institution / rule）
- importance（core / major / minor）
- source_type（canonical=原著有 / inferred=合理推断 / original=原创补充）
- confidence（0 到 1）
- generation_priority（1 最高优先）
- role_in_world（该实体在世界中的叙事作用，一句话）

---

**任务二：制定机器可执行生成步骤（steps）**

每个步骤对应一类实体的生成任务，步骤须严格按依赖顺序排列。
`target_seeds` 只能引用 entity_plan 中已有的 seed_id，不得凭空创建。

典型顺序：world_background → locations → characters → institutions → relations → rules → actions

每个步骤字段：
- step_id（snake_case，如 generate_locations）
- generator_type（world_background_generator / location_generator / character_generator / relation_generator / institution_generator / rule_generator / action_generator）
- depends_on（必须先完成的 step_id 列表，world_background 为空）
- target_entity_type（world_background / location / character / relation / institution / rule / action）
- target_seeds（该步骤生成的 seed_id 列表，world_background 步骤为空数组）
- context_refs（该步骤需要作为上下文输入的 step_id 列表）
- batch_size（建议每次 LLM 调用生成的实体数，通常 3-8）
- priority（1 最高）
- description（人可读的步骤说明）

---

**任务三：实体模版生成指引（ontology_hints）**

根据世界信息，为六类实体模版生成器提供语义指引：
- character_hints：Character 模版应重点关注的字段或特性
- location_hints：Location 模版应重点关注的要素
- relation_hints：Relation 模版应重点关注的关系类型
- institution_hints：Institution 模版应重点关注的要素
- rule_hints：Rule 模版应重点关注的规则维度

---

**输出格式：**
```json
{
  "entity_plan": {
    "locations": {
      "teaching_space": [
        {
          "seed_id": "dark_arts_classroom",
          "name": "黑魔法防御课教室",
          "entity_type": "location",
          "importance": "core",
          "source_type": "canonical",
          "confidence": 0.98,
          "generation_priority": 1,
          "role_in_world": "卡罗兄妹实施惩罚的主要场所"
        },
        {
          "seed_id": "potions_classroom",
          "name": "魔药课教室",
          "entity_type": "location",
          "importance": "major",
          "source_type": "canonical",
          "confidence": 0.95,
          "generation_priority": 2,
          "role_in_world": "斯拉格霍恩主持的教室"
        }
      ],
      "communal_space": [
        {
          "seed_id": "great_hall",
          "name": "大礼堂",
          "entity_type": "location",
          "importance": "core",
          "source_type": "canonical",
          "confidence": 0.99,
          "generation_priority": 1,
          "role_in_world": "全校集会与用餐的核心场所"
        }
      ]
    },
    "characters": {
      "student": [ ... ],
      "faculty": [ ... ],
      "death_eater_staff": [ ... ]
    },
    "institutions": {
      "house": [ ... ],
      "resistance_group": [ ... ]
    },
    "rules": {
      "disciplinary_rule": [ ... ],
      "access_control": [ ... ]
    }
  },
  "steps": [
    {
      "step_id": "generate_world_background",
      "generator_type": "world_background_generator",
      "depends_on": [],
      "target_entity_type": "world_background",
      "target_seeds": [],
      "context_refs": [],
      "batch_size": 1,
      "priority": 1,
      "description": "生成世界背景、历史与宏观叙事"
    },
    {
      "step_id": "generate_locations",
      "generator_type": "location_generator",
      "depends_on": ["generate_world_background"],
      "target_entity_type": "location",
      "target_seeds": ["dark_arts_classroom", "potions_classroom", "great_hall"],
      "context_refs": ["generate_world_background"],
      "batch_size": 5,
      "priority": 2,
      "description": "生成所有地点实体"
    }
  ],
  "ontology_hints": {
    "character_hints": ["..."],
    "location_hints": ["..."],
    "relation_hints": ["..."],
    "institution_hints": ["..."],
    "rule_hints": ["..."]
  }
}
```
