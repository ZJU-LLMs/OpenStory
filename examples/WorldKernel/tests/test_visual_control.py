from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from worldkernel.architect.spatial.models import (
    BlueprintGrid,
    BlueprintRegion,
    GridPoint,
    SpatialBlueprint,
)
from worldkernel.architect.visual.control import (
    LOCATION_RESERVED_COLOR,
    ROAD_RESERVED_COLOR,
    finalize_generated_background,
    render_layout_control_assets,
)


class VisualControlTests(unittest.TestCase):
    def test_control_keeps_the_road_hard_mask(self) -> None:
        blueprint = self._blueprint()
        manifest = SimpleNamespace(
            canvas={
                "width_px": 24,
                "height_px": 16,
                "tile_size": 4,
                "visual_clearance_tiles": 0,
            }
        )
        directory = Path(__file__).parent / f".visual-control-{uuid.uuid4().hex}"
        directory.mkdir()
        try:
            metadata = render_layout_control_assets(blueprint, manifest, directory)
            with Image.open(metadata["edit_base_path"]) as base_image:
                base = base_image.convert("RGB")
            with Image.open(metadata["edit_mask_path"]) as mask_image:
                alpha = mask_image.convert("RGBA").getchannel("A")
        finally:
            for path in directory.iterdir():
                path.unlink(missing_ok=True)
            directory.rmdir()

        self.assertEqual(base.getpixel((5, 5)), ROAD_RESERVED_COLOR)
        self.assertEqual(alpha.getpixel((5, 5)), 255)
        self.assertEqual(base.getpixel((17, 5)), LOCATION_RESERVED_COLOR)
        self.assertEqual(alpha.getpixel((17, 5)), 255)

    def test_final_background_replaces_road_reservations_with_ground(self) -> None:
        blueprint = self._blueprint()
        raw = Image.new("RGB", (24, 16), (48, 96, 144))
        draw = ImageDraw.Draw(raw)
        for point in blueprint.road_tiles:
            draw.rectangle(
                (point.x * 4, point.y * 4, point.x * 4 + 3, point.y * 4 + 3),
                fill=ROAD_RESERVED_COLOR,
            )
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

            for x in (1, 2, 3):
                pixel = result.getpixel((x * 4 + 1, 5))
                self.assertNotEqual(pixel, ROAD_RESERVED_COLOR)
                self.assertNotIn(pixel, {(185, 157, 92), (143, 119, 68), (210, 187, 117)})
            self.assertEqual(metadata["road_reserved_pixels_cleaned"], 4 * 4 * 4)
            self.assertFalse(metadata["route_placeholder_composited"])
            self.assertEqual(metadata["composited_layers"], ["location_placeholder_layer"])
        finally:
            for path in paths:
                path.unlink(missing_ok=True)

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
