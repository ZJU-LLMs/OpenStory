from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from worldkernel.architect.visual.character_atlas import (
    CharacterSpec,
    hydrate_existing_character_layer,
    InvalidCharacterBatchSelection,
    _generate_character_atlas_candidate,
    character_layout,
    postprocess_character_atlas,
    reconcile_character_batch_plan,
    run_character_atlas_pipeline,
)
from worldkernel.architect.visual.models import VisualLayoutManifest


class CharacterAtlasTests(unittest.TestCase):
    def test_transient_connection_failure_retries_same_request_once(self) -> None:
        root = self._root()
        root.mkdir()
        calls: list[tuple[str, bool]] = []

        class FlakyClient:
            def generate(self, prompt, output_path, **kwargs):
                calls.append((prompt, "size" in kwargs))
                if len(calls) == 1:
                    raise RuntimeError("API connection error: temporarily unavailable")
                return {"provider": "fake", "model": "fake-image"}

        try:
            with patch(
                "worldkernel.architect.visual.character_atlas.time.sleep"
            ) as sleep:
                metadata = _generate_character_atlas_candidate(
                    client=FlakyClient(),
                    prompt="same prompt",
                    output_path=root / "atlas_raw.png",
                )
            self.assertEqual(calls, [("same prompt", False)] * 2)
            self.assertEqual(metadata["transport_attempt_count"], 2)
            self.assertEqual(len(metadata["transport_failures"]), 1)
            sleep.assert_called_once()
        finally:
            self._remove_tree(root)

    def test_http_400_generation_failure_is_retried_once(self) -> None:
        calls = 0

        class InvalidRequestClient:
            def generate(self, _prompt, _output_path, **_kwargs):
                nonlocal calls
                calls += 1
                raise RuntimeError("Image API HTTP 400: invalid size")

        with patch("worldkernel.architect.visual.character_atlas.time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "invalid size"):
                _generate_character_atlas_candidate(
                    client=InvalidRequestClient(),
                    prompt="prompt",
                    output_path=Path("unused.png"),
                )
        self.assertEqual(calls, 2)
        sleep.assert_called_once()

    def test_cached_http_400_failure_is_retried_on_next_run(self) -> None:
        root = self._root()
        root.mkdir()
        failed_calls = 0
        recovered_calls = 0

        class OfflineClient:
            def __init__(self, _config):
                pass

            def generate(self, _prompt, _output_path, **_kwargs):
                nonlocal failed_calls
                failed_calls += 1
                raise RuntimeError(
                    "Image API HTTP 400: upstream provider request failed"
                )

        class RecoveredClient:
            def __init__(self, _config):
                pass

            def generate(self, _prompt, output_path, **_kwargs):
                nonlocal recovered_calls
                recovered_calls += 1
                Image.new("RGB", (1024, 1024), (0, 255, 0)).save(output_path)
                return {"provider": "fake", "model": "fake-image"}

        try:
            with (
                patch(
                    "worldkernel.architect.visual.character_atlas."
                    "load_model_config_by_capability",
                    return_value={"name": "fake", "model": "fake-image"},
                ),
                patch("worldkernel.architect.visual.character_atlas.time.sleep"),
            ):
                failed = self._run(root, self._characters(1), OfflineClient)
                self.assertEqual(failed_calls, 2)
                self.assertEqual(failed.character_layer.atlases[0].status, "failed")

                recovered = self._run(root, self._characters(1), RecoveredClient)
                self.assertEqual(recovered_calls, 1)
                self.assertEqual(recovered.character_layer.generated_batch_count, 1)
                self.assertEqual(recovered.character_layer.reused_batch_count, 0)
        finally:
            self._remove_tree(root)

    def test_zero_characters_does_not_load_image_model_or_call_client(self) -> None:
        root = self._root()
        root.mkdir()
        manifest = VisualLayoutManifest(
            world_id="empty-character-atlas-test",
            canvas={"width_px": 64, "height_px": 64},
        )
        try:
            with patch(
                "worldkernel.architect.visual.character_atlas.load_model_config_by_capability",
                side_effect=AssertionError("image config should not be loaded"),
            ):
                result = run_character_atlas_pipeline(
                    manifest=manifest,
                    semantic_characters=[],
                    root=root,
                    model_config_path=root / "missing.yaml",
                    generate=True,
                )
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["planned_batch_count"], 0)
            self.assertEqual(result["estimated_image_calls"], 0)
        finally:
            self._remove_tree(root)

    def test_dynamic_batch_counts_and_layouts(self) -> None:
        expected_batches = {
            0: 0,
            1: 1,
            2: 1,
            3: 1,
            4: 1,
            5: 1,
            6: 1,
            7: 2,
            12: 2,
            13: 3,
            30: 5,
        }
        for count, expected in expected_batches.items():
            with self.subTest(count=count):
                _, missing, batches, _ = reconcile_character_batch_plan(
                    self._characters(count),
                    max_batch_size=6,
                )
                self.assertEqual(missing, [])
                self.assertEqual(len(batches), expected)
                self.assertTrue(all(len(batch.character_ids) <= 6 for batch in batches))

        self.assertEqual(character_layout(1)["columns"], 1)
        self.assertEqual(character_layout(2)["columns"], 2)
        self.assertEqual(character_layout(3)["columns"], 3)
        self.assertEqual(character_layout(4)["rows"], 2)
        self.assertEqual(character_layout(5)["columns"], 3)
        self.assertEqual(character_layout(6)["rows"], 2)

    def test_reordering_is_stable_and_add_delete_only_changes_one_batch(self) -> None:
        characters = self._characters(13)
        _, _, original, plan = reconcile_character_batch_plan(
            characters, max_batch_size=6
        )
        _, _, reordered, reordered_plan = reconcile_character_batch_plan(
            list(reversed(characters)),
            plan,
            max_batch_size=6,
        )
        self.assertEqual(original, reordered)
        self.assertEqual(plan, reordered_plan)

        removed_id = original[0].character_ids[0]
        remaining = [
            item for item in characters if item["identity"]["id"] != removed_id
        ]
        remaining.append(
            {
                "identity": {"id": "char-new", "name": "New"},
                "visual": "new visual",
            }
        )
        _, _, updated, _ = reconcile_character_batch_plan(
            remaining,
            plan,
            max_batch_size=6,
        )
        self.assertEqual(updated[1:], original[1:])
        self.assertIn("char-new", updated[0].character_ids)
        self.assertNotIn(removed_id, updated[0].character_ids)

    def test_cache_generates_ceil_batches_then_only_changed_batch(self) -> None:
        root = self._root()
        root.mkdir()
        calls: list[str] = []
        postprocess_calls: list[str] = []

        class FakeClient:
            def __init__(self, _config):
                pass

            def generate(self, prompt, output_path, **_kwargs):
                calls.append(prompt)
                Image.new("RGB", (32, 32), (0, 255, 0)).save(output_path)
                return {"provider": "fake", "model": "fake-image"}

        def fake_postprocess(**kwargs):
            postprocess_calls.append(str(kwargs["raw_path"]))
            output = Path(kwargs["output_path"])
            preview = Path(kwargs["preview_path"])
            output.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (32, 32), (0, 0, 0, 0)).save(output)
            Image.new("RGB", (32, 32), (240, 240, 240)).save(preview)
            rows = []
            for index, character in enumerate(kwargs["characters"]):
                rows.append(
                    {
                        "character_id": character.character_id,
                        "name": character.name,
                        "batch_id": "",
                        "slot_index": index,
                        "status": "ready",
                        "source_rect": {"x": 0, "y": 0, "w": 16, "h": 16},
                        "content_rect": {"x": 2, "y": 2, "w": 12, "h": 12},
                        "portrait_rect": {"x": 2, "y": 2, "w": 12, "h": 6},
                        "error": "",
                    }
                )
            return {"status": "ready", "characters": rows, "error": "", "report": {}}

        try:
            characters = self._characters(13)
            with (
                patch(
                    "worldkernel.architect.visual.character_atlas.load_model_config_by_capability",
                    return_value={"name": "fake", "model": "fake-image"},
                ),
                patch(
                    "worldkernel.architect.visual.character_atlas.postprocess_character_atlas",
                    side_effect=fake_postprocess,
                ),
            ):
                first = self._run(root, characters, FakeClient)
                self.assertEqual(len(calls), 3)
                self.assertEqual(first.character_layer.generated_batch_count, 3)
                self.assertEqual(first.character_layer.estimated_image_calls, 3)

                legacy_metadata_path = next(
                    (root / "characters").glob("batch-*/metadata.json")
                )
                legacy_metadata = json.loads(legacy_metadata_path.read_text(encoding="utf-8"))
                legacy_metadata.pop("postprocess_version", None)
                legacy_metadata_path.write_text(
                    json.dumps(legacy_metadata, ensure_ascii=False),
                    encoding="utf-8",
                )

                second = self._run(root, list(reversed(characters)), FakeClient)
                self.assertEqual(len(calls), 3)
                self.assertEqual(len(postprocess_calls), 4)
                self.assertEqual(second.character_layer.generated_batch_count, 0)
                self.assertEqual(second.character_layer.reused_batch_count, 3)
                self.assertEqual(second.character_layer.estimated_image_calls, 0)

                characters[8]["visual"] = "changed visual"
                third = self._run(root, characters, FakeClient)
                self.assertEqual(len(calls), 4)
                self.assertEqual(third.character_layer.generated_batch_count, 1)
                self.assertEqual(third.character_layer.reused_batch_count, 2)
                self.assertEqual(third.character_layer.estimated_image_calls, 1)

                batch_id = third.character_layer.atlases[0].batch_id
                forced = self._run(
                    root,
                    characters,
                    FakeClient,
                    force_batch_ids=[batch_id],
                )
                self.assertEqual(len(calls), 5)
                self.assertEqual(forced.character_layer.generated_batch_count, 1)

                with self.assertRaises(InvalidCharacterBatchSelection):
                    self._run(
                        root,
                        characters,
                        FakeClient,
                        force_batch_ids=["batch-does-not-exist"],
                    )
        finally:
            self._remove_tree(root)

    def test_postprocessing_makes_key_background_transparent(self) -> None:
        root = self._root()
        root.mkdir()
        try:
            layout = character_layout(2)
            raw_path = root / "raw.png"
            output_path = root / "atlas.png"
            preview_path = root / "preview.png"
            image = Image.new(
                "RGB",
                (layout["width"], layout["height"]),
                (0, 255, 0),
            )
            draw = ImageDraw.Draw(image)
            cell_width = layout["width"] // 2
            draw.rectangle((140, 140, cell_width - 140, 900), fill=(180, 50, 30))
            draw.rectangle(
                (cell_width + 140, 140, layout["width"] - 140, 900),
                fill=(40, 80, 190),
            )
            image.save(raw_path)
            result = postprocess_character_atlas(
                raw_path=raw_path,
                output_path=output_path,
                preview_path=preview_path,
                characters=[
                    CharacterSpec("char-a", "A", "red"),
                    CharacterSpec("char-b", "B", "blue"),
                ],
                layout=layout,
                key_color="#00ff00",
                transparent_threshold=24,
                opaque_threshold=96,
            )
            self.assertEqual(result["status"], "ready")
            self.assertTrue(preview_path.is_file())
            with Image.open(output_path) as processed:
                rgba = processed.convert("RGBA")
                self.assertEqual(rgba.getpixel((10, 10))[3], 0)
                self.assertEqual(rgba.getpixel((200, 200))[3], 255)
                self.assertEqual(rgba.getpixel((cell_width + 200, 200))[3], 255)
        finally:
            self._remove_tree(root)

    def test_postprocessing_preserves_provider_native_alpha(self) -> None:
        root = self._root()
        root.mkdir()
        try:
            layout = character_layout(1)
            raw_path = root / "raw.png"
            output_path = root / "atlas.png"
            image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rectangle((330, 100, 690, 930), fill=(80, 40, 120, 255))
            image.save(raw_path)

            result = postprocess_character_atlas(
                raw_path=raw_path,
                output_path=output_path,
                preview_path=root / "preview.png",
                characters=[CharacterSpec("char-a", "A", "purple")],
                layout=layout,
                key_color="#00ffff",
                transparent_threshold=24,
                opaque_threshold=96,
            )

            self.assertEqual(result["status"], "ready")
            with Image.open(output_path) as processed:
                rgba = processed.convert("RGBA")
                self.assertEqual(rgba.getpixel((10, 10))[3], 0)
                self.assertEqual(rgba.getpixel((500, 500))[3], 255)
        finally:
            self._remove_tree(root)

    def test_postprocessing_ignores_low_alpha_key_color_noise_for_crop(self) -> None:
        root = self._root()
        root.mkdir()
        try:
            layout = character_layout(1)
            raw_path = root / "raw.png"
            output_path = root / "atlas.png"
            # This is visibly close to the configured key color, but far enough
            # away to have received a small non-zero alpha in the old soft mask.
            image = Image.new(
                "RGB",
                (layout["width"], layout["height"]),
                (18, 230, 18),
            )
            draw = ImageDraw.Draw(image)
            draw.rectangle((360, 120, 660, 900), fill=(180, 50, 30))
            image.save(raw_path)

            result = postprocess_character_atlas(
                raw_path=raw_path,
                output_path=output_path,
                preview_path=root / "preview.png",
                characters=[CharacterSpec("char-a", "A", "red")],
                layout=layout,
                key_color="#00ff00",
                transparent_threshold=24,
                opaque_threshold=96,
            )

            rect = result["characters"][0]["content_rect"]
            self.assertGreater(rect["x"], 300)
            self.assertLess(rect["w"], 400)
            self.assertLess(rect["h"], layout["height"])
            with Image.open(output_path) as processed:
                self.assertEqual(processed.convert("RGBA").getpixel((10, 10))[3], 0)
        finally:
            self._remove_tree(root)

    def test_postprocessing_removes_atlas_divider_from_character_crop(self) -> None:
        root = self._root()
        root.mkdir()
        try:
            layout = character_layout(1)
            raw_path = root / "raw.png"
            image = Image.new(
                "RGB",
                (layout["width"], layout["height"]),
                (0, 255, 0),
            )
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 24, layout["width"] - 1, 27), fill=(255, 255, 255))
            draw.rectangle((360, 120, 660, 900), fill=(180, 50, 30))
            image.save(raw_path)

            result = postprocess_character_atlas(
                raw_path=raw_path,
                output_path=root / "atlas.png",
                preview_path=root / "preview.png",
                characters=[CharacterSpec("char-a", "A", "red")],
                layout=layout,
                key_color="#00ff00",
                transparent_threshold=24,
                opaque_threshold=96,
            )

            rect = result["characters"][0]["content_rect"]
            self.assertGreater(rect["x"], 300)
            self.assertGreater(rect["y"], 80)
            self.assertLess(rect["w"], 400)
        finally:
            self._remove_tree(root)

    def test_postprocessing_keeps_complete_edge_touching_character_ready(self) -> None:
        root = self._root()
        root.mkdir()
        try:
            layout = character_layout(1)
            raw_path = root / "raw.png"
            image = Image.new(
                "RGB",
                (layout["width"], layout["height"]),
                (0, 255, 0),
            )
            draw = ImageDraw.Draw(image)
            draw.rectangle(
                (360, 160, 660, layout["height"] - 1),
                fill=(180, 50, 30),
            )
            image.save(raw_path)

            result = postprocess_character_atlas(
                raw_path=raw_path,
                output_path=root / "atlas.png",
                preview_path=root / "preview.png",
                characters=[CharacterSpec("char-a", "A", "red")],
                layout=layout,
                key_color="#00ff00",
                transparent_threshold=24,
                opaque_threshold=96,
            )

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["characters"][0]["status"], "ready")
            self.assertEqual(result["characters"][0]["error"], "")
            self.assertIn(
                "foreground_touches_slot_edge",
                result["report"]["characters"][0]["issues"],
            )
        finally:
            self._remove_tree(root)

    def test_postprocessing_keeps_character_with_detached_prop_ready(self) -> None:
        root = self._root()
        root.mkdir()
        try:
            layout = character_layout(1)
            raw_path = root / "raw.png"
            image = Image.new(
                "RGB",
                (layout["width"], layout["height"]),
                (0, 255, 0),
            )
            draw = ImageDraw.Draw(image)
            draw.rectangle((300, 140, 620, 920), fill=(180, 50, 30))
            draw.rectangle((700, 260, 790, 850), fill=(80, 60, 40))
            image.save(raw_path)

            result = postprocess_character_atlas(
                raw_path=raw_path,
                output_path=root / "atlas.png",
                preview_path=root / "preview.png",
                characters=[CharacterSpec("char-a", "A", "red")],
                layout=layout,
                key_color="#00ff00",
                transparent_threshold=24,
                opaque_threshold=96,
            )

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["characters"][0]["status"], "ready")
            self.assertEqual(result["characters"][0]["error"], "")
            self.assertIn(
                "multiple_major_components",
                result["report"]["characters"][0]["issues"],
            )
        finally:
            self._remove_tree(root)

    def test_postprocessing_preserves_model_output_size(self) -> None:
        root = self._root()
        root.mkdir()
        try:
            layout = character_layout(1)
            raw_path = root / "raw.png"
            image = Image.new("RGB", (1254, 1254), (0, 255, 0))
            draw = ImageDraw.Draw(image)
            draw.rectangle((400, 180, 820, 1160), fill=(180, 50, 30))
            image.save(raw_path)

            result = postprocess_character_atlas(
                raw_path=raw_path,
                output_path=root / "atlas.png",
                preview_path=root / "preview.png",
                characters=[CharacterSpec("char-a", "A", "red")],
                layout=layout,
                key_color="#00ff00",
                transparent_threshold=24,
                opaque_threshold=96,
            )

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["characters"][0]["status"], "ready")
            self.assertFalse(result["report"]["aspect_ratio_changed"])
            self.assertEqual(
                result["report"]["output_size"],
                {"width": 1254, "height": 1254},
            )
            self.assertIn(
                "model_output_size_differs",
                result["report"]["characters"][0]["issues"],
            )
            with Image.open(root / "atlas.png") as processed:
                self.assertEqual(processed.size, (1254, 1254))
        finally:
            self._remove_tree(root)

    def test_postprocessing_preserves_non_square_model_output_aspect_ratio(self) -> None:
        root = self._root()
        root.mkdir()
        try:
            layout = character_layout(3)
            raw_path = root / "raw.png"
            image = Image.new("RGB", (1774, 887), (0, 255, 255))
            draw = ImageDraw.Draw(image)
            for left, right in ((80, 480), (690, 1080), (1290, 1660)):
                draw.rectangle((left, 40, right, 840), fill=(180, 50, 30))
            image.save(raw_path)

            result = postprocess_character_atlas(
                raw_path=raw_path,
                output_path=root / "atlas.png",
                preview_path=root / "preview.png",
                characters=[
                    CharacterSpec("char-a", "A", "red"),
                    CharacterSpec("char-b", "B", "red"),
                    CharacterSpec("char-c", "C", "red"),
                ],
                layout=layout,
                key_color="#00ffff",
                transparent_threshold=24,
                opaque_threshold=96,
            )

            self.assertEqual(
                result["report"]["output_size"],
                {"width": 1774, "height": 887},
            )
            self.assertTrue(result["report"]["aspect_ratio_changed"])
            with Image.open(root / "atlas.png") as processed:
                self.assertEqual(processed.size, (1774, 887))
        finally:
            self._remove_tree(root)

    def test_postprocessing_removes_white_slot_frame(self) -> None:
        root = self._root()
        root.mkdir()
        try:
            layout = character_layout(1)
            raw_path = root / "raw.png"
            image = Image.new(
                "RGB",
                (layout["width"], layout["height"]),
                (0, 255, 0),
            )
            draw = ImageDraw.Draw(image)
            draw.rectangle(
                (0, 0, layout["width"] - 1, layout["height"] - 1),
                outline=(255, 255, 255),
                width=10,
            )
            draw.rectangle((360, 160, 660, 900), fill=(180, 50, 30))
            image.save(raw_path)

            output_path = root / "atlas.png"
            result = postprocess_character_atlas(
                raw_path=raw_path,
                output_path=output_path,
                preview_path=root / "preview.png",
                characters=[CharacterSpec("char-a", "A", "red")],
                layout=layout,
                key_color="#00ff00",
                transparent_threshold=24,
                opaque_threshold=96,
            )

            alpha = Image.open(output_path).convert("RGBA").getchannel("A")
            self.assertEqual(result["status"], "ready")
            self.assertIsNone(alpha.crop((0, 0, alpha.width, 1)).getbbox())
            self.assertIsNone(alpha.crop((0, 0, 1, alpha.height)).getbbox())
            self.assertIsNone(
                alpha.crop((0, alpha.height - 1, alpha.width, alpha.height)).getbbox()
            )
            self.assertIsNone(
                alpha.crop((alpha.width - 1, 0, alpha.width, alpha.height)).getbbox()
            )
        finally:
            self._remove_tree(root)

    def _run(
        self,
        root: Path,
        characters: list[dict],
        client_factory,
        *,
        force_batch_ids: list[str] | None = None,
    ) -> VisualLayoutManifest:
        manifest = VisualLayoutManifest(
            world_id="character-atlas-test",
            canvas={"width_px": 64, "height_px": 64},
        )
        run_character_atlas_pipeline(
            manifest=manifest,
            semantic_characters=characters,
            root=root,
            model_config_path=root / "image_models.yaml",
            generate=True,
            max_batch_size=6,
            force_batch_ids=force_batch_ids,
            progress_manifest_path=root / "visual_layout_manifest.json",
            client_factory=client_factory,
        )
        return manifest

    def test_hydrate_existing_character_layer_recovers_blueprint_fallback(self) -> None:
        root = self._root()
        try:
            atlas_path = root / "characters" / "batch-001" / "atlas.png"
            atlas_path.parent.mkdir(parents=True, exist_ok=True)
            atlas_path.write_bytes(b"generated-atlas")
            layer = {
                "status": "partial",
                "character_count": 2,
                "eligible_character_count": 2,
                "planned_batch_count": 1,
                "atlases": [
                    {
                        "batch_id": "batch-001",
                        "status": "needs_review",
                        "character_count": 2,
                        "url": "characters/batch-001/atlas.png",
                    }
                ],
                "characters": [
                    {
                        "character_id": f"char-{index}",
                        "name": f"Character {index}",
                        "batch_id": "batch-001",
                        "slot_index": index,
                        "status": "needs_review",
                    }
                    for index in range(2)
                ],
                "needs_review_character_ids": ["char-0", "char-1"],
            }
            (root / "spatial_blueprint.json").write_text(
                json.dumps({"visual": {"character_layer": layer}}),
                encoding="utf-8",
            )
            manifest = VisualLayoutManifest(
                world_id="character-recovery-test",
                canvas={"width_px": 64, "height_px": 64},
            )

            recovery = hydrate_existing_character_layer(manifest, root)

            self.assertEqual(recovery["status"], "restored")
            self.assertEqual(recovery["source"], "spatial_blueprint")
            self.assertEqual(recovery["displayable_character_count"], 2)
            self.assertEqual(len(manifest.character_layer.characters), 2)
        finally:
            self._remove_tree(root)

    @staticmethod
    def _characters(count: int) -> list[dict]:
        return [
            {
                "identity": {"id": f"char-{index:03d}", "name": f"Character {index}"},
                "visual": f"visual description {index}",
            }
            for index in range(count)
        ]

    @staticmethod
    def _root() -> Path:
        return Path(__file__).parent / f".character-atlas-{uuid.uuid4().hex}"

    @staticmethod
    def _remove_tree(root: Path) -> None:
        if not root.exists():
            return
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                path.rmdir()
        root.rmdir()


if __name__ == "__main__":
    unittest.main()
