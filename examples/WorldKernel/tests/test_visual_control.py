from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from worldkernel.architect.spatial.models import (
    BlueprintGrid,
    BlueprintRegion,
    GridPoint,
    SpatialBlueprint,
)
from worldkernel.architect.visual.control import (
    EDITABLE_BASE_COLOR,
    LOCATION_RESERVED_COLOR,
    ROAD_RESERVED_COLOR,
    finalize_generated_background,
    render_layout_control_assets,
    validate_protected_regions,
)
from worldkernel.architect.visual.prompt import compose_background_prompt
from worldkernel.architect.visual.layout import build_visual_layout_manifest
from worldkernel.architect.visual.pipeline import _generate_background


class VisualControlTests(unittest.TestCase):
    def test_background_generation_retries_one_transient_failure(self) -> None:
        blueprint = self._blueprint()
        directory = Path(__file__).parent / f".visual-control-{uuid.uuid4().hex}"
        directory.mkdir()
        calls = 0
        try:
            manifest = build_visual_layout_manifest(blueprint, {}, directory)
            render_layout_control_assets(blueprint, manifest, directory)
            prompt = compose_background_prompt({}, manifest)

            class FlakyImageClient:
                def __init__(self, _cfg):
                    pass

                def generate(self, _prompt, output_path, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        raise RuntimeError("Image API HTTP 502: temporary gateway failure")
                    width, height = (int(value) for value in kwargs["size"].split("x"))
                    Image.new("RGB", (width, height), (40, 80, 120)).save(output_path)
                    return {"provider": "fake", "model": "fake-image"}

            with (
                patch(
                    "worldkernel.architect.visual.pipeline.load_model_config_by_capability",
                    return_value={"name": "fake", "model": "fake-image"},
                ),
                patch(
                    "worldkernel.architect.visual.pipeline.ImageGenerationClient",
                    FlakyImageClient,
                ),
                patch("worldkernel.architect.visual.pipeline.time.sleep"),
            ):
                metadata = _generate_background(
                    blueprint=blueprint,
                    manifest=manifest,
                    prompt_payload=prompt,
                    root=directory,
                    model_config_path=directory / "unused.yaml",
                )

            self.assertEqual(calls, 2)
            self.assertEqual(metadata["model"]["transport_attempt_count"], 2)
            self.assertEqual(len(metadata["attempt_failures"]), 1)
            self.assertTrue((directory / "background.png").exists())
        finally:
            for path in sorted(directory.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            directory.rmdir()

    def test_background_pipeline_retains_untouched_model_output(self) -> None:
        blueprint = self._blueprint()
        directory = Path(__file__).parent / f".visual-control-{uuid.uuid4().hex}"
        directory.mkdir()
        try:
            manifest = build_visual_layout_manifest(blueprint, {}, directory)
            render_layout_control_assets(blueprint, manifest, directory)
            prompt = compose_background_prompt({}, manifest)

            class FakeImageClient:
                def __init__(self, _cfg):
                    pass

                def generate(self, _prompt, output_path, **kwargs):
                    width, height = (int(value) for value in kwargs["size"].split("x"))
                    Image.new("RGB", (width, height), (220, 20, 20)).save(output_path)
                    return {"provider": "fake", "model": "fake-image"}

            with (
                patch(
                    "worldkernel.architect.visual.pipeline.load_model_config_by_capability",
                    return_value={"name": "fake", "model": "fake-image"},
                ),
                patch(
                    "worldkernel.architect.visual.pipeline.ImageGenerationClient",
                    FakeImageClient,
                ),
            ):
                metadata = _generate_background(
                    blueprint=blueprint,
                    manifest=manifest,
                    prompt_payload=prompt,
                    root=directory,
                    model_config_path=directory / "unused.yaml",
                )

            with Image.open(directory / "background_raw.png") as image:
                raw = image.convert("RGB")
            with Image.open(directory / "background_mask_restored.png") as image:
                restored = image.convert("RGB")
            with Image.open(directory / "background.png") as image:
                published = image.convert("RGB")
            self.assertEqual(raw.getpixel((17, 5)), (220, 20, 20))
            self.assertEqual(restored.getpixel((17, 5)), LOCATION_RESERVED_COLOR)
            self.assertEqual(published.getpixel((17, 5)), LOCATION_RESERVED_COLOR)
            self.assertNotEqual(raw.tobytes(), restored.tobytes())
            self.assertEqual(
                metadata["raw_model_output_path"],
                str(directory / "background_raw.png"),
            )
        finally:
            for path in sorted(directory.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            directory.rmdir()

    def test_background_prompt_requires_sparse_clearance_without_expanding_slots(self) -> None:
        manifest = SimpleNamespace(
            canvas={"width_px": 24, "height_px": 16, "visual_clearance_tiles": 2},
            slots=[SimpleNamespace(location_id="location-1")],
            asset_contract={},
        )
        payload = compose_background_prompt(
            {
                "world_name": "测试世界",
                "visual_profile": {
                    "environmental_motifs": [f"风物{i}" for i in range(8)],
                },
            },
            manifest,
        )

        prompt = payload["prompt"]
        self.assertIn("约 2 个网格宽", prompt)
        self.assertIn("开阔地表、水面和低矮铺装的面积必须明显多于", prompt)
        self.assertIn("不要求逐项画出", prompt)
        self.assertIn("风物5", prompt)
        self.assertNotIn("风物6", prompt)

    def test_control_uses_reserved_base_and_submitted_hard_mask(self) -> None:
        blueprint = self._blueprint()
        manifest = SimpleNamespace(
            canvas={
                "width_px": 24,
                "height_px": 16,
                "tile_size": 4,
                "visual_clearance_tiles": 0,
            },
            visual_profile={},
        )
        directory = Path(__file__).parent / f".visual-control-{uuid.uuid4().hex}"
        directory.mkdir()
        try:
            metadata = render_layout_control_assets(blueprint, manifest, directory)
            with Image.open(metadata["edit_base_path"]) as base_image:
                base = base_image.convert("RGB")
            with Image.open(metadata["edit_mask_path"]) as mask_image:
                alpha = mask_image.convert("RGBA").getchannel("A")
            self.assertFalse((directory / "generation_layout_guide.png").exists())
        finally:
            for path in directory.iterdir():
                path.unlink(missing_ok=True)
            directory.rmdir()

        self.assertEqual(base.getpixel((5, 5)), ROAD_RESERVED_COLOR)
        self.assertEqual(base.getpixel((17, 5)), LOCATION_RESERVED_COLOR)
        self.assertEqual(base.getpixel((1, 1)), EDITABLE_BASE_COLOR)
        self.assertEqual(alpha.getpixel((5, 5)), 255)
        self.assertEqual(alpha.getpixel((17, 5)), 255)
        self.assertEqual(alpha.getpixel((1, 1)), 0)
        self.assertTrue(metadata["edit_mask_path"].endswith("generation_edit_mask.png"))
        self.assertTrue(metadata["stage2_layout_used"])
        self.assertEqual(metadata["location_region_count"], 1)
        self.assertEqual(metadata["road_tile_count"], 4)

    def test_final_background_is_an_exact_copy_without_placeholder_processing(self) -> None:
        blueprint = self._blueprint()
        raw = Image.new("RGB", (24, 16), (48, 96, 144))
        raw.putpixel((17, 5), (123, 45, 67))
        paths = self._temporary_paths()
        raw_path, output_path = paths
        try:
            raw.save(raw_path, format="PNG")
            metadata = finalize_generated_background(
                raw_path,
                output_path,
                target_size=(24, 16),
                blueprint=blueprint,
                placeholder_style={
                    "fill_color": "#2d374e",
                    "border_color": "#e6ebf5",
                },
            )
            with Image.open(output_path) as image:
                result = image.convert("RGB")

            self.assertEqual(result.tobytes(), raw.tobytes())
            self.assertEqual(metadata["road_reserved_pixels_cleaned"], 0)
            self.assertFalse(metadata["location_reserved_pixels_postprocessed"])
            self.assertFalse(metadata["route_placeholder_composited"])
            self.assertEqual(metadata["composited_layers"], [])
            self.assertEqual(metadata["location_placeholder_count"], 0)
            self.assertEqual(metadata["postprocessing"], "none")
        finally:
            for path in paths:
                path.unlink(missing_ok=True)

    def test_non_strict_mask_validation_restores_protected_pixels(self) -> None:
        blueprint = self._blueprint()
        manifest = SimpleNamespace(
            canvas={"width_px": 24, "height_px": 16, "tile_size": 4},
        )
        directory = Path(__file__).parent / f".visual-control-{uuid.uuid4().hex}"
        directory.mkdir()
        try:
            metadata = render_layout_control_assets(blueprint, manifest, directory)
            generated_path = directory / "generated.png"
            Image.new("RGB", (24, 16), (220, 20, 20)).save(generated_path)
            result = validate_protected_regions(
                metadata["edit_base_path"],
                generated_path,
                metadata["edit_mask_path"],
                expected_size=(24, 16),
                blueprint=blueprint,
                max_location_changed_ratio=0.0,
                max_road_changed_ratio=0.0,
                fail_on_excessive_change=False,
            )
            with Image.open(generated_path) as image:
                restored = image.convert("RGB")
            self.assertFalse(result["passed"])
            self.assertEqual(restored.getpixel((17, 5)), LOCATION_RESERVED_COLOR)
            self.assertEqual(restored.getpixel((5, 5)), ROAD_RESERVED_COLOR)
            self.assertEqual(restored.getpixel((1, 1)), (220, 20, 20))
        finally:
            for path in directory.iterdir():
                path.unlink(missing_ok=True)
            directory.rmdir()

    @staticmethod
    def _blueprint() -> SpatialBlueprint:
        return SpatialBlueprint(
            world_id="visual-control-test",
            grid=BlueprintGrid(width=6, height=4, tile_size=4),
            road_tiles=[
                GridPoint(x=1, y=1),
                GridPoint(x=2, y=1),
                GridPoint(x=3, y=1),
                GridPoint(x=4, y=1),
            ],
            regions=[
                BlueprintRegion(
                    location_id="location-1",
                    name="测试地点",
                    bounds={"x": 4, "y": 1, "w": 1, "h": 2},
                    entrance={"x": 4, "y": 1},
                )
            ],
        )

    @staticmethod
    def _temporary_paths() -> tuple[Path, Path]:
        root = Path(__file__).parent
        token = uuid.uuid4().hex
        return root / f"visual-control-{token}-raw.png", root / f"visual-control-{token}-out.png"


if __name__ == "__main__":
    unittest.main()
