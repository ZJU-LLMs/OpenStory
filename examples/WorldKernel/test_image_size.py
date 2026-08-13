from __future__ import annotations

import argparse
import base64
import json
import os
import struct
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml
from PIL import Image


EXAMPLE_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = EXAMPLE_ROOT / "configs" / "image_models.yaml"
DEFAULT_OUTPUT_ROOT = EXAMPLE_ROOT / "generated" / "image_size_probe"
DEFAULT_PROMPT = "保持完整画布尺寸，在纯色背景中央绘制一个简单的红色圆形。"


def main() -> int:
    args = _build_parser().parse_args()
    requested_size = _parse_size(args.size)
    requested_size_text = f"{requested_size[0]}x{requested_size[1]}"
    prompt = (
        f"{args.prompt.strip()} "
        f"输出图片画布必须严格保持为 {requested_size_text} 像素。"
    )
    config = _load_image_model_config(Path(args.config).expanduser().resolve())
    api_key = _resolve_api_key(config)
    endpoint = _resolve_endpoint(config, args.mode)
    model = str(config.get("model") or "gpt-image-2")
    output_dir = _create_output_dir(args.output_dir, args.mode)

    request_summary: dict[str, Any] = {
        "mode": args.mode,
        "endpoint": endpoint,
        "model": model,
        "prompt": prompt,
        "requested_size": requested_size_text,
        "api_key": "<redacted>",
    }
    input_path: Path | None = None
    if args.mode == "edit":
        input_path = output_dir / "simple_input.png"
        _create_simple_input(input_path, requested_size)
        request_summary["input_image"] = str(input_path)
        request_summary["input_size"] = _size_payload(_image_size(input_path))

    _write_json(output_dir / "request_summary.json", request_summary)
    print(f"Mode:             {args.mode}")
    print(f"Endpoint:         {endpoint}")
    print(f"Requested size:   {requested_size_text}")
    print(f"Prompt:           {prompt}")
    print(f"API size field:   size={requested_size_text}")
    if input_path is not None:
        print(f"Simple input:     {input_path}")
    print(f"Output directory: {output_dir}")
    print("Sending one image request...")

    started = time.monotonic()
    if args.mode == "generation":
        response = requests.post(
            endpoint,
            headers=_headers(api_key),
            json={
                "model": model,
                "prompt": prompt,
                "size": requested_size_text,
            },
            timeout=args.timeout,
        )
    else:
        assert input_path is not None
        with input_path.open("rb") as image_file:
            response = requests.post(
                endpoint,
                headers=_headers(api_key),
                data={
                    "model": model,
                    "prompt": prompt,
                    "size": requested_size_text,
                },
                files={"image": (input_path.name, image_file, "image/png")},
                timeout=args.timeout,
            )
    elapsed = time.monotonic() - started
    response.raise_for_status()
    payload = _parse_json_response(response)
    _write_json(output_dir / "response_metadata.json", _sanitize_response(payload))

    output_path = output_dir / "result.png"
    _save_image(payload, output_path)
    actual_size = _image_size(output_path)
    ihdr_size = _png_ihdr_size(output_path)
    declared_size = str(payload.get("size") or "").strip()
    exact_match = actual_size == requested_size

    report = {
        **request_summary,
        "http_status": response.status_code,
        "elapsed_seconds": round(elapsed, 3),
        "declared_response_size": declared_size,
        "actual_image_size": _size_payload(actual_size),
        "png_ihdr_size": _size_payload(ihdr_size) if ihdr_size else None,
        "exact_size_match": exact_match,
        "result_path": str(output_path),
        "request_id": _request_id(response.headers),
    }
    _write_json(output_dir / "size_report.json", report)

    print()
    print(f"HTTP status:      {response.status_code}")
    print(f"Elapsed:          {elapsed:.1f}s")
    print(f"Declared size:    {declared_size or '<missing>'}")
    print(f"Actual size:      {actual_size[0]}x{actual_size[1]}")
    if ihdr_size is not None:
        print(f"PNG IHDR size:    {ihdr_size[0]}x{ihdr_size[1]}")
    print(f"Exact match:      {exact_match}")
    print(f"Result image:     {output_path}")
    print(f"Detailed report:  {output_dir / 'size_report.json'}")
    if report["request_id"]:
        print(f"Request ID:       {report['request_id']}")
    if not exact_match:
        print(
            "\nSIZE MISMATCH: API 返回图片的物理画布尺寸与请求尺寸不一致。",
            file=sys.stderr,
        )
        return 2
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用一张简单图片和简单 prompt 测试 gpt-image-2 的指定输出尺寸。"
    )
    parser.add_argument(
        "--mode",
        choices=("edit", "generation"),
        default="edit",
        help="默认 edit，更接近 WorldKernel 背景生成调用。",
    )
    parser.add_argument("--size", default="3840x2160")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--output-dir", default="")
    return parser


def _create_simple_input(path: Path, size: tuple[int, int]) -> None:
    image = Image.new("RGB", size, (224, 228, 232))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def _load_image_model_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Image model config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    providers = payload if isinstance(payload, list) else []
    for provider in providers:
        if "image_generation" in (provider.get("capabilities") or []):
            return dict(provider)
    raise ValueError(f"No image_generation provider found in {path}")


def _resolve_api_key(config: dict[str, Any]) -> str:
    literal = str(config.get("api_key") or "").strip()
    if literal:
        return literal
    env_name = str(config.get("api_key_env") or "").strip()
    value = str(os.getenv(env_name, "") if env_name else "").strip()
    if not value:
        raise ValueError("Image API key is empty")
    return value


def _resolve_endpoint(config: dict[str, Any], mode: str) -> str:
    explicit_key = "edit_endpoint" if mode == "edit" else "image_endpoint"
    explicit = str(config.get(explicit_key) or "").strip()
    if explicit:
        return explicit
    base = str(config.get("base_url") or "").rstrip("/")
    if not base:
        raise ValueError(f"Neither {explicit_key} nor base_url is configured")
    if base.endswith("/images"):
        return f"{base}/{'edits' if mode == 'edit' else 'generations'}"
    return f"{base}/images/{'edits' if mode == 'edit' else 'generations'}"


def _parse_json_response(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Image API returned non-JSON content: {response.text[:500]}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected JSON response: {type(payload).__name__}")
    return payload


def _save_image(payload: dict[str, Any], output_path: Path) -> None:
    data = payload.get("data") or []
    item = data[0] if data and isinstance(data[0], dict) else {}
    image_url = str(item.get("url") or "").strip()
    encoded = str(item.get("b64_json") or "")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if image_url:
        response = requests.get(image_url, timeout=120)
        response.raise_for_status()
        output_path.write_bytes(response.content)
    elif encoded:
        output_path.write_bytes(base64.b64decode(encoded, validate=True))
    else:
        raise RuntimeError("Image API response does not contain data[0].url or data[0].b64_json")


def _sanitize_response(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    items = []
    for raw in payload.get("data") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        encoded = str(item.pop("b64_json", "") or "")
        if encoded:
            item["b64_json_length"] = len(encoded)
        items.append(item)
    sanitized["data"] = items
    return sanitized


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Accept": "*/*"}


def _create_output_dir(configured: str, mode: str) -> Path:
    if configured:
        path = Path(configured).expanduser().resolve()
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = DEFAULT_OUTPUT_ROOT / f"{timestamp}-{mode}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_size(value: str) -> tuple[int, int]:
    parts = str(value).lower().replace("*", "x").split("x")
    if len(parts) != 2:
        raise ValueError(f"Invalid size: {value!r}; expected WIDTHxHEIGHT")
    width, height = (int(part.strip()) for part in parts)
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid size: {value!r}")
    return width, height


def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def _png_ihdr_size(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as handle:
        header = handle.read(24)
    if (
        len(header) < 24
        or header[:8] != b"\x89PNG\r\n\x1a\n"
        or header[12:16] != b"IHDR"
    ):
        return None
    return struct.unpack(">II", header[16:24])


def _size_payload(size: tuple[int, int]) -> dict[str, int]:
    return {"width": size[0], "height": size[1]}


def _request_id(headers: requests.structures.CaseInsensitiveDict[str]) -> str:
    for name in ("Ah-Request-Id", "X-Request-Id", "Request-Id"):
        value = str(headers.get(name) or "").strip()
        if value:
            return value
    return ""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
