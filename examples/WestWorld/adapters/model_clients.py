"""Config-driven OpenAI-compatible clients for text, vision, and Image 2."""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests
import yaml
from openai import OpenAI


def _load_models(path: str) -> Dict[str, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    api_key = os.environ.get("WW_API_KEY", "").strip()
    base_url = os.environ.get("WW_BASE_URL", "").strip()
    model = os.environ.get("WW_MODEL", "").strip()
    for row in rows:
        if api_key:
            row["api_key"] = api_key
        if base_url:
            row["base_url"] = base_url
        if model and row.get("role") in ("text", "vision"):
            row["model"] = model
    return {row["role"]: row for row in rows}


class OpenAICompatibleLLM:
    def __init__(self, config: Dict[str, Any], trace: Optional[Callable[[Dict[str, Any]], None]] = None,
                 timeout_override: Optional[float] = None) -> None:
        self.config = config
        self.trace = trace
        self.last_usage: Dict[str, Any] = {}
        timeout = timeout_override if timeout_override is not None else float(
            config.get("timeout", os.environ.get("WW_LLM_TIMEOUT_SECONDS", "120"))
        )
        self.client = OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
            timeout=timeout,
            max_retries=int(config.get("max_retries", 0)),
        )

    def chat(self, prompt: str) -> str:
        kwargs: Dict[str, Any] = {
            "model": self.config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.get("temperature", 0),
        }
        if self.config.get("disable_thinking", True):
            # Qwen3.5 does not honour the /no_think soft switch; use the API-level parameter instead.
            kwargs["extra_body"] = {"enable_thinking": False}
        response = self.client.chat.completions.create(**kwargs)
        answer = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        self.last_usage = usage.model_dump() if usage and hasattr(usage, "model_dump") else {}
        if self.trace:
            self.trace({
                "call_type": "text_chat", "model": self.config["model"],
                "prompt": prompt, "response": answer, "usage": self.last_usage,
            })
        return answer


class OpenAICompatibleVLM(OpenAICompatibleLLM):
    def ask(self, image_handle: str, question: str) -> str:
        content = [{"type": "text", "text": question}, {"type": "image_url", "image_url": {"url": image_handle}}]
        response = self.client.chat.completions.create(
            model=self.config["model"],
            messages=[{"role": "user", "content": content}],
            temperature=self.config.get("temperature", 0),
        )
        answer = response.choices[0].message.content or ""
        if self.trace:
            self.trace({
                "call_type": "vision_chat",
                "model": self.config["model"],
                "question": question,
                "image_handle": image_handle if not image_handle.startswith("data:image/") else "data:image/[archived separately]",
                "response": answer,
            })
        return answer


class OpenAICompatibleImageGen:
    def __init__(self, config: Dict[str, Any], trace: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        self.config = config
        self.trace = trace
        self.client = OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
            timeout=float(config.get("timeout", os.environ.get("WW_LLM_TIMEOUT_SECONDS", "120"))),
            max_retries=int(config.get("max_retries", 0)),
        )

    @staticmethod
    def _handle(response: Any) -> str:
        item = response.data[0]
        if item.url:
            return item.url
        if item.b64_json:
            return f"data:image/png;base64,{item.b64_json}"
        raise RuntimeError("Image response contained neither URL nor base64 image data")

    @staticmethod
    def _image_file(handle: str) -> io.BytesIO:
        if handle.startswith("data:image/"):
            content = base64.b64decode(handle.split(",", 1)[1])
        elif handle.startswith(("http://", "https://")):
            response = requests.get(handle, timeout=60)
            response.raise_for_status()
            content = response.content
        else:
            content = Path(handle).read_bytes()
        image = io.BytesIO(content)
        image.name = "previous-state.png"
        return image

    def create_initial(self, prompt: str) -> str:
        response = self.client.images.generate(model=self.config["model"], prompt=prompt, size=self.config.get("size", "1024x1024"))
        handle = self._handle(response)
        if self.trace:
            self.trace({"call_type": "image_generate", "model": self.config["model"], "prompt": prompt, "response_image": "archived separately"})
        return handle

    def apply_event(self, previous_image: str, prompt: str) -> str:
        image = self._image_file(previous_image)
        response = self.client.images.edit(
            model=self.config["model"],
            image=image,
            prompt=prompt,
            size=self.config.get("size", "1024x1024"),
            input_fidelity=self.config.get("input_fidelity", "high"),
        )
        handle = self._handle(response)
        if self.trace:
            self.trace({
                "call_type": "image_edit",
                "model": self.config["model"],
                "prompt": prompt,
                "previous_image": previous_image if not previous_image.startswith("data:image/") else "data:image/[archived separately]",
                "response_image": "archived separately",
            })
        return handle


def build_llm(config_path: str, trace: Optional[Callable[[Dict[str, Any]], None]] = None,
              timeout_override: Optional[float] = None) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(_load_models(config_path)["text"], trace=trace, timeout_override=timeout_override)


def build_vlm(config_path: str, trace: Optional[Callable[[Dict[str, Any]], None]] = None) -> OpenAICompatibleVLM:
    return OpenAICompatibleVLM(_load_models(config_path)["vision"], trace=trace)


def build_image_gen(config_path: str, trace: Optional[Callable[[Dict[str, Any]], None]] = None) -> OpenAICompatibleImageGen:
    return OpenAICompatibleImageGen(_load_models(config_path)["image"], trace=trace)
