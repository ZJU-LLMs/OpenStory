from __future__ import annotations

import base64
import shutil
from pathlib import Path
from uuid import uuid4

from worldkernel.architect.visual.client import ImageGenerationClient
from worldkernel.llm.config_loader import load_model_config_by_capability


def test_image_model_config_has_no_global_size():
    config_path = Path(__file__).resolve().parents[1] / "configs" / "image_models.yaml"
    config = load_model_config_by_capability(config_path, "image_generation")

    assert config["model"] == "gpt-image-2"
    assert config["api_style"] == "openai_compatible"
    assert config["image_endpoint"] == "http://111.231.53.131:8090/v1/images/generations"
    assert config["edit_endpoint"] == "http://111.231.53.131:8090/v1/images/edits"
    assert config["style_reference_path"] == "frontend/assets/pixel_style_reference.png"
    assert (config_path.parent.parent / config["style_reference_path"]).is_file()
    assert "size" not in config
    assert "image_size" not in config
    assert config["api_key"]


def test_generation_uses_call_size_instead_of_config_size():
    output_root = Path(__file__).resolve().parent / f".tmp_image_client_{uuid4().hex}"
    output_path = output_root / "background.png"
    calls: list[tuple[str, str, dict]] = []
    client = _client(size="512x512")

    def fake_request(method: str, url: str, payload: dict, **_: object) -> dict:
        calls.append((method, url, payload))
        return {"data": [{"b64_json": base64.b64encode(b"test-image").decode("ascii")}]}

    client._request_json = fake_request  # type: ignore[method-assign]
    try:
        client.generate("俯视像素地图", output_path, size="2560x1600")
        assert calls[0][2]["size"] == "2560x1600"
        assert output_path.read_bytes() == b"test-image"
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_reference_generation_uses_edit_endpoint_and_dynamic_size():
    output_root = Path(__file__).resolve().parent / f".tmp_image_edit_{uuid4().hex}"
    output_root.mkdir(parents=True)
    input_path = output_root / "base.png"
    mask_path = output_root / "mask.png"
    style_path = output_root / "style.png"
    output_path = output_root / "result.png"
    input_path.write_bytes(b"base")
    mask_path.write_bytes(b"mask")
    style_path.write_bytes(b"style")
    calls: list[tuple[str, str, dict, list]] = []
    client = _client()

    def fake_multipart(method: str, url: str, fields: dict, files: list) -> dict:
        calls.append((method, url, fields, files))
        return {"data": [{"b64_json": base64.b64encode(b"edited-image").decode("ascii")}]}

    client._request_multipart_json = fake_multipart  # type: ignore[method-assign]
    try:
        result = client.generate(
            "按保护遮罩生成地图",
            output_path,
            size="800x600",
            input_image_path=input_path,
            mask_path=mask_path,
            style_reference_paths=[style_path],
        )
        assert calls[0][1] == "http://111.231.53.131:8090/v1/images/edits"
        assert calls[0][2]["size"] == "800x600"
        assert calls[0][3] == [("image", input_path), ("image", style_path), ("mask", mask_path)]
        assert output_path.read_bytes() == b"edited-image"
        assert result["api_style"] == "openai_compatible_edit"
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def _client(**overrides: object) -> ImageGenerationClient:
    config = {
        "name": "OpenAIProvider",
        "model": "gpt-image-2",
        "api_key": "test-key",
        "base_url": "http://111.231.53.131:8090/v1/images",
        "image_endpoint": "http://111.231.53.131:8090/v1/images/generations",
        "edit_endpoint": "http://111.231.53.131:8090/v1/images/edits",
        "api_style": "openai_compatible",
    }
    config.update(overrides)
    return ImageGenerationClient(config)
