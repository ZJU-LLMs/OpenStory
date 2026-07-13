"""Overseer reset (level 1 intervention): 降一档 + 清短期 + 强制模糊高扰动记忆。

供 OverseerPlugin（O5）调用；直接操作 state_plugin，无 Ray 依赖，可独立测试。

LLM 文本改写由调用方负责（只返回需要改写的 entries）；本模块只处理数值/数据操作。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from examples.WestWorld.awakening import awakening_engine
from examples.WestWorld.plugins.agent.reflect.memory_blur import classify_disturbance


def select_blur_candidates(
    long_mems: List[Any],
    suppressed: List[Dict[str, Any]],
    awakening: int,
    tick: int,
) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """Pick high-disturbance entries from long_mems; add to suppressed if not already there.

    Returns (to_blur, updated_suppressed).
    - to_blur: subset of long_mems that need forced strength=1 rewrite
    - suppressed_memories: deduplicated (original texts preserved)
    """
    existing_texts = {s["text"] for s in suppressed}
    new_suppressed = list(suppressed)
    to_blur: List[Any] = []
    for entry in long_mems:
        text = entry.get("content", str(entry)) if isinstance(entry, dict) else str(entry)
        if classify_disturbance(text):
            to_blur.append(entry)
            if text not in existing_texts:
                new_suppressed.append({
                    "tick": tick,
                    "text": text,
                    "awakening_at_blur": awakening,
                })
                existing_texts.add(text)
    return to_blur, new_suppressed


async def apply_overseer_reset(
    state_plugin: Any,
    tick: int,
    *,
    agent_id: str = "?",
    detail: str = "监管者重置",
) -> List[Any]:
    """Apply overseer level-1 reset to a host.

    Steps:
    1. Clear short-term memory.
    2. Select high-disturbance long-term entries → add to suppressed_memories (dedup).
    3. Descend awakening by one stage via awakening_engine.apply(overseer_reset).
    4. Write intervention_log entry.
    5. Return list of long_mem entries that need forced strength=1 LLM rewrite (caller handles).

    suppressed_memories length never shrinks (only grows or stays same by dedup).
    """
    # 1. Clear short-term memory
    await state_plugin.clear_short_term_memory()

    # 2. Forced blur candidates
    long_mems: List[Any] = await state_plugin.get_long_term_memory() or []
    suppressed: List[Dict] = await state_plugin.get_state("suppressed_memories") or []
    awakening = int(await state_plugin.get_state("awakening") or 0)

    to_blur, new_suppressed = select_blur_candidates(long_mems, suppressed, awakening, tick)
    await state_plugin.set_state("suppressed_memories", new_suppressed)

    # 3. Descend awakening by one stage
    aw_state: Dict[str, Any] = {
        "awakening": awakening,
        "awakening_sources": list(await state_plugin.get_state("awakening_sources") or []),
    }
    awakening_engine.apply(aw_state, "overseer_reset", detail, tick)
    await state_plugin.set_state("awakening", aw_state["awakening"])
    await state_plugin.set_state("awakening_sources", aw_state["awakening_sources"])

    # 4. Write intervention_log
    log: List[Dict] = await state_plugin.get_state("intervention_log") or []
    new_awakening = int(await state_plugin.get_state("awakening") or 0)
    log.append({"tick": tick, "action": "reset", "reason": detail, "awakening_after": new_awakening})
    await state_plugin.set_state("intervention_log", log)

    return to_blur
