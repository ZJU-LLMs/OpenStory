from __future__ import annotations

from pathlib import Path

from openai import AsyncOpenAI

from worldkernel.llm.config_loader import load_model_config

_openai: AsyncOpenAI | None = None
_model: str = ""


def init(config_path: Path) -> None:
    global _openai, _model
    cfg = load_model_config(config_path)
    _openai = AsyncOpenAI(
        api_key=cfg.get("api_key") or "placeholder",
        base_url=cfg.get("base_url"),
    )
    _model = cfg["model"]


async def chat(prompt: str, system: str = "") -> str:
    assert _openai is not None, "llm.client not initialized — call init() first"
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = await _openai.chat.completions.create(model=_model, messages=messages)
    return resp.choices[0].message.content or ""
