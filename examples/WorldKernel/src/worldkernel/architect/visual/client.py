from __future__ import annotations

import base64
import json
import mimetypes
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


class ImageGenerationClient:
    """Image synthesis client supporting OpenAI-compatible and DashScope APIs.

    The endpoint is configurable so model/API version changes only require YAML
    updates. A configured image_endpoint is treated as the complete POST URL.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.base_url = str(config.get("base_url") or "https://dashscope.aliyuncs.com").rstrip("/")
        self.compatible_base_url = str(
            config.get("compatible_base_url")
            or config.get("openai_base_url")
            or (
                "https://dashscope.aliyuncs.com/compatible-mode/v1"
                if "dashscope.aliyuncs.com" in self.base_url
                and "compatible-mode" not in self.base_url
                else self.base_url
            )
        ).rstrip("/")
        self.image_endpoint = str(config.get("image_endpoint") or "").strip()
        self.edit_endpoint = str(config.get("edit_endpoint") or "").strip()
        self.model = str(config.get("model") or "gpt-image-2")
        self.api_key = str(config.get("api_key") or "")
        self.workspace_id = str(config.get("workspace_id") or "")
        self.region = str(config.get("region") or "cn-beijing")
        self.maas_endpoint = str(config.get("maas_endpoint") or config.get("multimodal_endpoint") or "")
        self.task_endpoint = str(config.get("task_endpoint") or "/api/v1/services/aigc/text2image/image-synthesis")
        self.poll_interval_seconds = float(config.get("poll_interval_seconds") or 2.0)
        self.timeout_seconds = float(config.get("timeout_seconds") or 180.0)
        self.request_timeout_seconds = float(config.get("request_timeout_seconds") or 240.0)

    def generate(
        self,
        prompt: str,
        output_path: str | Path,
        *,
        size: str | None = None,
        input_image_path: str | Path | None = None,
        mask_path: str | Path | None = None,
        style_reference_paths: list[str | Path] | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("Image generation api_key is empty")
        api_style = self._api_style()
        if api_style == "openai_compatible" and size is not None:
            self._validate_openai_request(size)
        if input_image_path is not None:
            if api_style != "openai_compatible":
                raise RuntimeError("Reference image generation requires an OpenAI-compatible image API")
            if size is None:
                raise RuntimeError("Reference image generation requires an explicit size")
            return self._generate_openai_edit(
                prompt,
                Path(output_path),
                input_image_path=Path(input_image_path),
                mask_path=Path(mask_path) if mask_path else None,
                style_reference_paths=[Path(path) for path in style_reference_paths or []],
                size=self._format_size(size, separator="x"),
            )
        if style_reference_paths:
            raise RuntimeError("Style references require an input image for image editing")
        if api_style != "openai_compatible" and size is None:
            raise RuntimeError(f"Image generation api_style={api_style} requires an explicit size")
        if api_style == "aliyun_maas_multimodal":
            return self._generate_maas_multimodal(
                prompt,
                Path(output_path),
                size=self._format_size(size, separator="*"),
            )
        if api_style == "auto":
            failures: list[str] = []
            try:
                return self._generate_maas_multimodal(
                    prompt,
                    Path(output_path),
                    size=self._format_size(size, separator="*"),
                )
            except Exception as exc:
                failures.append(str(exc))
            try:
                return self._generate_openai_compatible(
                    prompt,
                    Path(output_path),
                    size=self._format_size(size, separator="x") if size is not None else None,
                )
            except Exception as exc:
                failures.append(str(exc))
            try:
                return self._generate_dashscope_async(
                    prompt,
                    Path(output_path),
                    size=self._format_size(size, separator="*"),
                )
            except Exception as exc:
                failures.append(str(exc))
            raise RuntimeError("Aliyun image generation failed in auto mode: " + " | ".join(failures))
        if api_style == "openai_compatible":
            return self._generate_openai_compatible(
                prompt,
                Path(output_path),
                size=self._format_size(size, separator="x") if size is not None else None,
            )

        return self._generate_dashscope_async(
            prompt,
            Path(output_path),
            size=self._format_size(size, separator="*"),
        )

    def _generate_dashscope_async(
        self,
        prompt: str,
        output_path: Path,
        *,
        size: str | None,
    ) -> dict[str, Any]:
        task_id = self._submit(prompt, size=size)
        result = self._wait(task_id)
        image_url = self._extract_image_url(result)
        if not image_url:
            raise RuntimeError(f"Aliyun image task succeeded without image URL: {result}")
        self._download(image_url, output_path)
        return {
            "provider": self.config.get("name") or "AliyunWanImageProvider",
            "model": self.model,
            "api_style": "dashscope_async",
            "size": size,
            "task_id": task_id,
            "image_url": image_url,
            "raw_result": result,
        }

    def _api_style(self) -> str:
        api_style = str(self.config.get("api_style") or "dashscope_async").lower()
        if api_style in {"aliyun_maas_multimodal", "maas_multimodal", "multimodal_generation"}:
            return "aliyun_maas_multimodal"
        if api_style in {"openai_compatible", "openai-compatible", "openai"}:
            return "openai_compatible"
        if api_style in {"dashscope_async", "dashscope-async", "dashscope"}:
            return "dashscope_async"
        return "auto"

    def _format_size(self, requested: str, *, separator: str) -> str:
        value = re.sub(r"\s*[*xX]\s*", separator, str(requested).strip())
        return value

    def _validate_openai_request(self, requested_size: str) -> None:
        match = re.fullmatch(r"\s*(\d+)\s*[*xX]\s*(\d+)\s*", str(requested_size))
        if match is None:
            raise RuntimeError(f"Invalid gpt-image-2 size: {requested_size!r}")
        width, height = (int(value) for value in match.groups())
        pixels = width * height
        if width > 3840 or height > 3840:
            raise RuntimeError("gpt-image-2 image dimensions cannot exceed 3840 pixels")
        if width % 16 or height % 16:
            raise RuntimeError("gpt-image-2 image dimensions must be multiples of 16")
        if pixels < 655_360 or pixels > 8_294_400:
            raise RuntimeError(
                "gpt-image-2 total pixels must be between 655360 and 8294400"
            )
        if max(width, height) / min(width, height) > 3:
            raise RuntimeError("gpt-image-2 aspect ratio cannot exceed 3:1")

    def _generate_maas_multimodal(
        self,
        prompt: str,
        output_path: Path,
        *,
        size: str,
    ) -> dict[str, Any]:
        url = self._maas_generation_url()
        parameters: dict[str, Any] = {
            "size": size,
            "n": int(self.config.get("n") or 1),
            "watermark": bool(self.config.get("watermark", False)),
        }
        if "thinking_mode" in self.config:
            parameters["thinking_mode"] = bool(self.config.get("thinking_mode"))

        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ]
            },
            "parameters": parameters,
        }
        result = self._request_json("POST", url, payload)
        image_url = self._extract_image_url(result)
        b64_json = self._extract_b64_json(result)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if image_url:
            self._download(image_url, output_path)
        elif b64_json:
            output_path.write_bytes(base64.b64decode(b64_json))
        else:
            raise RuntimeError(f"Aliyun MaaS multimodal image API returned no image: {result}")
        return {
            "provider": self.config.get("name") or "AliyunWanImageProvider",
            "model": self.model,
            "api_style": "aliyun_maas_multimodal",
            "size": size,
            "image_url": image_url,
            "raw_result": result,
        }

    def _maas_generation_url(self) -> str:
        if self.maas_endpoint:
            return self.maas_endpoint.replace("{WorkspaceId}", self.workspace_id)
        if "maas.aliyuncs.com" in self.base_url or "{WorkspaceId}" in self.base_url:
            if ("{" in self.base_url or "}" in self.base_url) and "{WorkspaceId}" not in self.base_url:
                raise RuntimeError(
                    "Aliyun MaaS base_url contains braces. Use {WorkspaceId} as a placeholder, "
                    "or put the real WorkspaceId directly without braces."
                )
            if "{WorkspaceId}" in self.base_url and not self.workspace_id:
                raise RuntimeError(
                    "Aliyun MaaS multimodal image generation requires workspace_id "
                    "when base_url contains {WorkspaceId}"
                )
            return (
                self.base_url.replace("{WorkspaceId}", self.workspace_id).rstrip("/")
                + "/api/v1/services/aigc/multimodal-generation/generation"
            )
        if not self.workspace_id:
            raise RuntimeError(
                "Aliyun MaaS multimodal image generation requires workspace_id "
                "or workspace_id_env in image_models.yaml"
            )
        return (
            f"https://{self.workspace_id}.{self.region}.maas.aliyuncs.com"
            "/api/v1/services/aigc/multimodal-generation/generation"
        )

    def _generate_openai_compatible(
        self,
        prompt: str,
        output_path: Path,
        *,
        size: str,
    ) -> dict[str, Any]:
        url = self._openai_generation_url()
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
        }
        if size is not None:
            payload["size"] = size
        result = self._request_json("POST", url, payload)
        data = result.get("data") or []
        if not data or not isinstance(data[0], dict):
            raise RuntimeError(f"OpenAI-compatible image API returned no data: {result}")

        item = data[0]
        image_url = str(item.get("url") or "")
        b64_json = str(item.get("b64_json") or "")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if image_url:
            self._download(image_url, output_path)
        elif b64_json:
            output_path.write_bytes(base64.b64decode(b64_json))
        else:
            raise RuntimeError(f"OpenAI-compatible image API returned no image: {result}")

        return {
            "provider": self.config.get("name") or "ImageGenerationProvider",
            "model": self.model,
            "api_style": "openai_compatible",
            "size": size or "",
            "image_url": image_url,
            "raw_result": result,
        }

    def _generate_openai_edit(
        self,
        prompt: str,
        output_path: Path,
        *,
        input_image_path: Path,
        mask_path: Path | None,
        style_reference_paths: list[Path],
        size: str,
    ) -> dict[str, Any]:
        if not input_image_path.exists():
            raise RuntimeError(f"Reference image does not exist: {input_image_path}")
        if mask_path is not None and not mask_path.exists():
            raise RuntimeError(f"Image mask does not exist: {mask_path}")
        for path in style_reference_paths:
            if not path.exists():
                raise RuntimeError(f"Style reference does not exist: {path}")
        fields = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
        }
        files = [("image", input_image_path)]
        files.extend(("image", path) for path in style_reference_paths)
        if mask_path is not None:
            files.append(("mask", mask_path))
        result = self._request_multipart_json("POST", self._openai_edit_url(), fields, files)
        image_url = self._save_openai_result(result, output_path)
        return {
            "provider": self.config.get("name") or "ImageGenerationProvider",
            "model": self.model,
            "api_style": "openai_compatible_edit",
            "size": size,
            "image_url": image_url,
            "raw_result": result,
        }

    def _openai_generation_url(self) -> str:
        if self.image_endpoint:
            return self.image_endpoint
        base_url = self.compatible_base_url.rstrip("/")
        if base_url.endswith(("/images", "/images/generations")):
            return base_url
        return f"{base_url}/images/generations"

    def _openai_edit_url(self) -> str:
        if self.edit_endpoint:
            return self.edit_endpoint
        generation_url = self._openai_generation_url().rstrip("/")
        if generation_url.endswith("/generations"):
            return generation_url[: -len("/generations")] + "/edits"
        if generation_url.endswith("/images"):
            return generation_url + "/edits"
        return generation_url + "/images/edits"

    def _save_openai_result(self, result: dict[str, Any], output_path: Path) -> str:
        data = result.get("data") or []
        if not data or not isinstance(data[0], dict):
            raise RuntimeError(f"OpenAI-compatible image API returned no data: {result}")
        item = data[0]
        image_url = str(item.get("url") or "")
        b64_json = str(item.get("b64_json") or "")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if image_url:
            self._download(image_url, output_path)
        elif b64_json:
            output_path.write_bytes(base64.b64decode(b64_json))
        else:
            raise RuntimeError(f"OpenAI-compatible image API returned no image: {result}")
        return image_url

    def _submit(self, prompt: str, *, size: str) -> str:
        payload = {
            "model": self.model,
            "input": {"prompt": prompt},
            "parameters": {"size": size, "n": 1},
        }
        data = self._request_json(
            "POST",
            f"{self.base_url}{self.task_endpoint}",
            payload,
            extra_headers={"X-DashScope-Async": "enable"},
        )
        task_id = ((data.get("output") or {}).get("task_id") or data.get("task_id"))
        if not task_id:
            raise RuntimeError(f"Aliyun image generation did not return task_id: {data}")
        return str(task_id)

    def _wait(self, task_id: str) -> dict[str, Any]:
        deadline = time.time() + self.timeout_seconds
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = self._request_json("GET", f"{self.base_url}/api/v1/tasks/{task_id}", None)
            output = last.get("output") or {}
            status = str(output.get("task_status") or output.get("status") or "").upper()
            if status in {"SUCCEEDED", "SUCCESS"}:
                return last
            if status in {"FAILED", "CANCELED", "UNKNOWN"}:
                raise RuntimeError(f"Aliyun image task {task_id} failed: {last}")
            time.sleep(self.poll_interval_seconds)
        raise RuntimeError(f"Aliyun image task {task_id} timed out; last={last}")

    def _request_json(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "*/*",
            "Content-Type": "application/json",
        }
        headers.update(extra_headers or {})
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Image API HTTP {exc.code} at {url}: {detail}") from exc

    def _request_multipart_json(
        self,
        method: str,
        url: str,
        fields: dict[str, str],
        files: list[tuple[str, Path]],
    ) -> dict[str, Any]:
        boundary = f"worldkernel-{uuid.uuid4().hex}"
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("ascii"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        for name, path in files:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("ascii"),
                    (
                        f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'
                        f"Content-Type: {content_type}\r\n\r\n"
                    ).encode("utf-8"),
                    path.read_bytes(),
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode("ascii"))
        request = urllib.request.Request(
            url,
            data=b"".join(chunks),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "*/*",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Image API HTTP {exc.code} at {url}: {detail}") from exc

    @staticmethod
    def _extract_image_url(result: dict[str, Any]) -> str:
        direct = result.get("url") or result.get("image_url")
        if direct:
            return str(direct)
        output = result.get("output") or {}
        if isinstance(output, str):
            return output if output.startswith(("http://", "https://")) else ""
        if not isinstance(output, dict):
            output = {}
        direct_output = output.get("url") or output.get("image_url")
        if direct_output:
            return str(direct_output)
        results = output.get("results") or output.get("task_results") or []
        for item in _as_list(results):
            if isinstance(item, str) and item.startswith(("http://", "https://")):
                return item
            if isinstance(item, dict):
                url = item.get("url") or item.get("image_url")
                if url:
                    return str(url)
        choices = output.get("choices") or result.get("choices") or []
        for choice in _as_list(choices):
            if not isinstance(choice, dict):
                if isinstance(choice, str) and choice.startswith(("http://", "https://")):
                    return choice
                continue
            message = choice.get("message") or {}
            content = message.get("content") if isinstance(message, dict) else None
            for item in _as_list(content or choice.get("content") or []):
                if isinstance(item, str) and item.startswith(("http://", "https://")):
                    return item
                if isinstance(item, dict):
                    image = item.get("image") or {}
                    if isinstance(image, str) and image.startswith(("http://", "https://")):
                        return image
                    image_url = image.get("url") if isinstance(image, dict) else ""
                    url = item.get("url") or item.get("image_url") or image_url
                    if url:
                        return str(url)
        return ""

    @staticmethod
    def _extract_b64_json(result: dict[str, Any]) -> str:
        direct = result.get("b64_json") or result.get("base64")
        if direct:
            return str(direct)
        output = result.get("output") or {}
        if isinstance(output, str):
            return "" if output.startswith(("http://", "https://")) else output
        if not isinstance(output, dict):
            output = {}
        results = output.get("results") or output.get("task_results") or []
        for item in _as_list(results):
            if isinstance(item, str) and not item.startswith(("http://", "https://")):
                return item
            if isinstance(item, dict):
                b64_json = item.get("b64_json") or item.get("base64")
                if b64_json:
                    return str(b64_json)
        choices = output.get("choices") or result.get("choices") or []
        for choice in _as_list(choices):
            if not isinstance(choice, dict):
                if isinstance(choice, str) and not choice.startswith(("http://", "https://")):
                    return choice
                continue
            message = choice.get("message") or {}
            content = message.get("content") if isinstance(message, dict) else None
            for item in _as_list(content or choice.get("content") or []):
                if isinstance(item, str) and not item.startswith(("http://", "https://")):
                    return item
                if isinstance(item, dict):
                    image = item.get("image") or {}
                    image_b64 = image.get("b64_json") if isinstance(image, dict) else ""
                    b64_json = item.get("b64_json") or item.get("base64") or image_b64
                    if b64_json:
                        return str(b64_json)
        return ""

    @staticmethod
    def _download(url: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as response:
            output_path.write_bytes(response.read())


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


# Backward-compatible import for callers created before the client became provider-neutral.
AliyunWanImageClient = ImageGenerationClient
