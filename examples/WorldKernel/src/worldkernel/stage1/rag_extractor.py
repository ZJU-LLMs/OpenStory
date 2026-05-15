from __future__ import annotations

import json
from pathlib import Path

from worldkernel.llm.client import chat_json
from worldkernel.models.stage1_types import KnowledgeChunk

EXTRACT_PROMPT = """
你是一个世界构建数据分析师。请阅读以下提供的参考资料文本，并从中提取出构建世界所需的关键信息。
你需要将信息严格分类为四类：人物、地点、事件(按时间顺序)、全局规则/背景。

参考资料：
'''
{source_text}
'''

请务必输出纯 JSON 格式，不要包含任何代码块标记（如 ```json ），数据结构必须严格符合以下 schema:
{{
  "characters": [{{"name": "姓名", "description": "身份描述", "affiliations": ["阵营"]}}],
  "locations": [{{"name": "地名", "description": "地点特征", "parent_location": "父级地名"}}],
  "events": [{{"time_node": "时间点", "event_summary": "发生了什么", "involved_entities": ["相关人/地"]}}],
  "global_rules": [{{"category": "类别", "description": "背景或规则细节"}}]
}}
"""

async def extract_knowledge(source_text: str) -> KnowledgeChunk:
    """
    核心抽取逻辑：将原著文本段落转化为结构化分类数据
    """
    prompt = EXTRACT_PROMPT.format(source_text=source_text)
    
    # 调用现成的防腐层，chat_json 会自动剥离 markdown 符号并返回纯 json 字符串
    response_json_str = await chat_json(prompt=prompt, system="你是一个严谨的 JSON 数据抽取引擎。")
    
    try:
        # 使用 Pydantic 的解析能力，将 JSON 字符串直接反序列化为我们定义的对象
        parsed_data = json.loads(response_json_str)
        knowledge = KnowledgeChunk(**parsed_data)
        
        # 可选：如果你需要对事件进行时间排序，可以在这里基于 time_node 进行一次 sorting
        
        return knowledge
    except Exception as e:
        raise ValueError(f"解析 RAG 抽取数据失败: {e}\n模型返回原文: {response_json_str}") from e