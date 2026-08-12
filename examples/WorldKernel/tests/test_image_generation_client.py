from __future__ import annotations

import base64
import unittest
from pathlib import Path
from unittest.mock import patch

from worldkernel.architect.visual.client import ImageGenerationClient


class ImageGenerationClientTests(unittest.TestCase):
    def _client(self) -> ImageGenerationClient:
        return ImageGenerationClient(
            {
                "name": "test-provider",
                "model": "gpt-image-2",
                "api_key": "test-key",
                "base_url": "https://example.test/v1",
                "api_style": "openai_compatible",
            }
        )

    def test_generation_sends_only_required_fields_and_size(self) -> None:
        client = self._client()
        with (
            patch.object(
                client,
                "_request_json",
                return_value={"data": [{"url": "https://example.test/image.png"}]},
            ) as request,
            patch.object(client, "_download"),
        ):
            client._generate_openai_compatible(
                "prompt",
                Path("ignored.png"),
                negative_prompt="",
                size="1024x1024",
            )

        payload = request.call_args.args[2]
        self.assertEqual(
            payload,
            {
                "model": "gpt-image-2",
                "prompt": "prompt",
                "size": "1024x1024",
            },
        )

    def test_generation_can_omit_size(self) -> None:
        client = self._client()
        with (
            patch.object(
                client,
                "_request_json",
                return_value={
                    "data": [
                        {"b64_json": base64.b64encode(b"ok").decode("ascii")}
                    ]
                },
            ) as request,
            patch.object(Path, "write_bytes"),
        ):
            result = client.generate("prompt", "ignored.png")

        payload = request.call_args.args[2]
        self.assertNotIn("size", payload)
        self.assertEqual(result["size"], "")

    def test_edit_sends_only_required_multipart_fields(self) -> None:
        client = self._client()
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(
                client,
                "_request_multipart_json",
                return_value={"data": [{"url": "https://example.test/image.png"}]},
            ) as request,
            patch.object(client, "_save_openai_result", return_value=""),
        ):
            client._generate_openai_edit(
                "prompt",
                Path("output.png"),
                input_image_path=Path("input.jpg"),
                mask_path=None,
                style_reference_paths=[],
                negative_prompt="",
                size="1024x1024",
            )

        fields = request.call_args.args[2]
        self.assertEqual(
            fields,
            {
                "model": "gpt-image-2",
                "prompt": "prompt",
                "size": "1024x1024",
            },
        )
        self.assertEqual(request.call_args.args[3], [("image", Path("input.jpg"))])

    def test_base64_result_is_saved_without_downloading_temporary_url(self) -> None:
        client = self._client()
        image_bytes = b"packy-image-result"
        output_path = Path("result.png")
        with (
            patch.object(client, "_download") as download,
            patch.object(Path, "mkdir"),
            patch.object(Path, "write_bytes") as write_bytes,
        ):
            image_url = client._save_openai_result(
                {
                    "data": [
                        {"b64_json": base64.b64encode(image_bytes).decode("ascii")}
                    ]
                },
                output_path,
            )

        self.assertEqual(image_url, "")
        write_bytes.assert_called_once_with(image_bytes)
        download.assert_not_called()

    def test_openai_request_rejects_unsupported_size_before_api_call(self) -> None:
        client = self._client()

        with self.assertRaisesRegex(RuntimeError, "total pixels"):
            client.generate("prompt", "ignored.png", size="240x176")

    def test_openai_request_accepts_full_map_size(self) -> None:
        client = self._client()
        with (
            patch.object(
                client,
                "_request_json",
                return_value={"data": [{"b64_json": base64.b64encode(b"ok").decode("ascii")}]},
            ),
            patch.object(Path, "write_bytes"),
        ):
            result = client.generate("prompt", "ignored.png", size="3840x2160")

        self.assertEqual(result["size"], "3840x2160")


if __name__ == "__main__":
    unittest.main()
