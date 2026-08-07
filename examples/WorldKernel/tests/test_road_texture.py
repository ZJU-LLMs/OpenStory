from __future__ import annotations

import unittest
import uuid
from pathlib import Path

from PIL import Image

from worldkernel.architect.spatial.models import (
    BlueprintGrid,
    BlueprintRegion,
    GridPoint,
    SpatialBlueprint,
)
from worldkernel.architect.visual.road_texture import (
    build_road_layer,
    compose_road_texture_prompt,
)


class RoadTextureTests(unittest.TestCase):
    def test_layer_uses_exact_unique_road_tile_mask(self) -> None:
        blueprint = self._blueprint()
        atlas_path, layer_path = self._temporary_paths("road-layer", 2)
        try:
            self._make_atlas(atlas_path)
            metadata = build_road_layer(
                atlas_path=atlas_path,
                output_path=layer_path,
                blueprint=blueprint,
                canvas_size=(128, 96),
            )

            with Image.open(layer_path) as image:
                layer = image.convert("RGBA")
            self.assertEqual(layer.size, (128, 96))
            alpha = layer.getchannel("A")
            expected = 7 * 16 * 16
            self.assertEqual(alpha.histogram()[255], expected)
            self.assertEqual(metadata["road_pixels"], expected)
            self.assertEqual(metadata["source_road_tile_count"], 8)
            self.assertEqual(metadata["visible_road_tile_count"], 7)
            self.assertEqual(metadata["location_clipped_road_tile_count"], 1)
            self.assertFalse(metadata["resized"])
            self.assertTrue(metadata["mirrored_tiling"])

            road_tiles = {(point.x, point.y) for point in blueprint.road_tiles}
            road_tiles.remove((0, 2))
            for y in range(blueprint.grid.height):
                for x in range(blueprint.grid.width):
                    sample = alpha.getpixel((x * 16 + 8, y * 16 + 8))
                    self.assertEqual(sample, 255 if (x, y) in road_tiles else 0)
        finally:
            self._remove_paths((atlas_path, layer_path))

    def test_missing_location_entrance_connection_fails(self) -> None:
        blueprint = self._blueprint()
        blueprint.regions[0].bounds = {"x": 7, "y": 4, "w": 1, "h": 1}
        blueprint.regions[0].entrance = {"x": 7, "y": 4}
        atlas_path, layer_path = self._temporary_paths("missing-entry", 2)
        try:
            self._make_atlas(atlas_path)
            with self.assertRaisesRegex(RuntimeError, "location-1"):
                build_road_layer(
                    atlas_path=atlas_path,
                    output_path=layer_path,
                    blueprint=blueprint,
                    canvas_size=(128, 96),
                )
        finally:
            self._remove_paths((atlas_path, layer_path))

    def test_prompt_is_world_aware_but_does_not_delegate_geometry(self) -> None:
        payload = compose_road_texture_prompt(
            {
                "world_name": "云端城",
                "world_origin_summary": "漂浮在云海中的未来城市",
            },
            {
                "art_style": "明亮卡通像素风",
                "era_style": "未来都市",
                "material_texture": ["金属", "发光晶体"],
            },
        )
        self.assertIn("云端城", payload["prompt"])
        self.assertIn("可平铺道路地表材质底图", payload["prompt"])
        self.assertIn("只表现同一种连续材质", payload["prompt"])
        self.assertIn("不要绘制道路路线", payload["prompt"])
        self.assertNotIn("Stage2", payload["prompt"])

    @staticmethod
    def _blueprint() -> SpatialBlueprint:
        road_tiles = [
            GridPoint(x=0, y=2),
            GridPoint(x=1, y=2),
            GridPoint(x=2, y=2),
            GridPoint(x=3, y=2),
            GridPoint(x=3, y=1),
            GridPoint(x=3, y=3),
            GridPoint(x=4, y=2),
            GridPoint(x=4, y=2),
            GridPoint(x=5, y=2),
        ]
        return SpatialBlueprint(
            world_id="road-test",
            grid=BlueprintGrid(width=8, height=6, tile_size=16),
            road_tiles=road_tiles,
            regions=[
                BlueprintRegion(
                    location_id="location-1",
                    name="测试地点",
                    bounds={"x": 0, "y": 1, "w": 1, "h": 2},
                    entrance={"x": 0, "y": 2},
                ),
                BlueprintRegion(
                    location_id="location-2",
                    name="另一个地点",
                    bounds={"x": 6, "y": 1, "w": 1, "h": 2},
                    entrance={"x": 6, "y": 2},
                ),
            ],
        )

    @staticmethod
    def _make_atlas(path: Path) -> None:
        image = Image.new("RGB", (32, 32))
        for y in range(32):
            for x in range(32):
                image.putpixel((x, y), (120 + x * 2, 80 + y * 2, 40))
        image.save(path, format="PNG")

    @staticmethod
    def _temporary_paths(label: str, count: int) -> tuple[Path, ...]:
        token = uuid.uuid4().hex
        root = Path(__file__).parent
        return tuple(root / f".{label}-{token}-{index}.png" for index in range(count))

    @staticmethod
    def _remove_paths(paths: tuple[Path, ...]) -> None:
        for path in paths:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
