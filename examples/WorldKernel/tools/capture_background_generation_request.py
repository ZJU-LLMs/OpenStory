from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from unittest.mock import patch


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send one real background edit request and save a redacted wire-level capture."
    )
    parser.add_argument("--template-root", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    return parser.parse_args()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _redacted_headers(request: urllib.request.Request) -> dict[str, str]:
    headers = dict(request.header_items())
    for name in list(headers):
        if name.lower() == "authorization":
            scheme = headers[name].split(" ", 1)[0] or "Bearer"
            headers[name] = f"{scheme} ***REDACTED***"
    return headers


def _capture_multipart_request(
    request: urllib.request.Request,
    *,
    source_files: dict[tuple[str, str], Path],
) -> dict[str, object]:
    body = request.data or b""
    headers = _redacted_headers(request)
    content_type = next(
        (value for name, value in headers.items() if name.lower() == "content-type"),
        "",
    )
    parsed = BytesParser(policy=default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii")
        + body
    )
    fields: dict[str, str] = {}
    files: list[dict[str, object]] = []
    for part in parsed.iter_parts():
        name = part.get_param("name", header="content-disposition") or ""
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename is None:
            fields[name] = payload.decode("utf-8")
            continue
        source_path = source_files.get((name, filename))
        files.append(
            {
                "field_name": name,
                "filename": filename,
                "content_type": part.get_content_type(),
                "size_bytes": len(payload),
                "sha256": _sha256(payload),
                "source_path": str(source_path.resolve()) if source_path else "",
                "wire_placeholder": f"<binary {filename}: {len(payload)} bytes, sha256={_sha256(payload)}>",
            }
        )
    boundary = parsed.get_boundary() or ""
    return {
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "method": request.get_method(),
        "url": request.full_url,
        "headers": headers,
        "content_length_bytes": len(body),
        "body_sha256": _sha256(body),
        "multipart_boundary": boundary,
        "multipart_fields": fields,
        "multipart_files": files,
        "security_note": "Authorization is deliberately redacted; no API key is stored in this capture.",
    }


def main() -> int:
    args = _parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository_root / "src"))

    from worldkernel.architect.visual.client import ImageGenerationClient
    from worldkernel.llm.config_loader import load_model_config_by_capability

    template_root = args.template_root.resolve()
    spatial_root = template_root / "generated" / "artifacts" / "spatial"
    prompt_path = spatial_root / "background_prompt.json"
    prompt_payload = json.loads(prompt_path.read_text(encoding="utf-8"))
    input_image = Path(
        prompt_payload.get("input_image") or spatial_root / "generation_edit_base.png"
    ).resolve()
    edit_mask = Path(
        prompt_payload.get("edit_mask") or spatial_root / "generation_edit_mask.png"
    ).resolve()
    width = int(prompt_payload["target_size"]["width"])
    height = int(prompt_payload["target_size"]["height"])

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    generated_image_path = output_root / "background_real_response.png"
    capture_path = output_root / "background_generation_request_message.json"
    result_path = output_root / "background_generation_result.json"

    config = load_model_config_by_capability(args.model_config.resolve(), "image_generation")
    client = ImageGenerationClient(config)
    original_urlopen = urllib.request.urlopen
    captured_request: dict[str, object] = {}
    source_files = {
        ("image", input_image.name): input_image,
        ("mask", edit_mask.name): edit_mask,
    }

    def capture_then_send(request, *call_args, **call_kwargs):
        nonlocal captured_request
        if (
            isinstance(request, urllib.request.Request)
            and request.get_method() == "POST"
            and "multipart/form-data" in (request.get_header("Content-type") or "")
        ):
            captured_request = _capture_multipart_request(
                request,
                source_files=source_files,
            )
            captured_request.update(
                {
                    "source_template_root": str(template_root),
                    "source_prompt_path": str(prompt_path.resolve()),
                    "response_image_path": str(generated_image_path),
                }
            )
            capture_path.write_text(
                json.dumps(captured_request, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return original_urlopen(request, *call_args, **call_kwargs)

    outcome: dict[str, object]
    try:
        with patch(
            "worldkernel.architect.visual.client.urllib.request.urlopen",
            side_effect=capture_then_send,
        ):
            result = client.generate(
                prompt_payload["prompt"],
                generated_image_path,
                size=f"{width}x{height}",
                input_image_path=input_image,
                mask_path=edit_mask,
            )
        outcome = {
            "status": "succeeded",
            "provider": result.get("provider", ""),
            "model": result.get("model", ""),
            "api_style": result.get("api_style", ""),
            "size": result.get("size", ""),
            "image_url": result.get("image_url", ""),
            "output_path": str(generated_image_path),
            "output_size_bytes": generated_image_path.stat().st_size,
            "output_sha256": _sha256(generated_image_path.read_bytes()),
        }
    except Exception as exc:
        outcome = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "request_was_captured": bool(captured_request),
        }
    result_path.write_text(
        json.dumps(outcome, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(outcome, ensure_ascii=False))
    print(f"request_capture={capture_path}")
    print(f"result={result_path}")
    return 0 if outcome["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
