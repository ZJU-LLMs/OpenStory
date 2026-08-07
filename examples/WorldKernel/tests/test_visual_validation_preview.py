from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path

from PIL import Image, ImageDraw

from worldkernel.architect.spatial.models import (
    BlueprintGrid,
    BlueprintRegion,
    BlueprintRoute,
    GridPoint,
    SpatialBlueprint,
)
from worldkernel.architect.visual.layout import build_visual_layout_manifest
from worldkernel.architect.visual.validation_preview import (
    render_visual_validation_preview,
)


class VisualValidationPreviewTests(unittest.TestCase):
    def test_preview_adds_debug_overlay_without_changing_formal_assets(self) -> None:
        root = Path(__file__).parent / f".visual-preview-{uuid.uuid4().hex}"
        root.mkdir()
        try:
            blueprint = self._blueprint()
            manifest = self._write_assets(root, blueprint)
            background_before = (root / "background.png").read_bytes()
            location_before = (root / "location_layer.png").read_bytes()
            road_before = (root / "road_layer.png").read_bytes()

            preview_path = root / "debug" / "preview.png"
            report = render_visual_validation_preview(
                blueprint=blueprint,
                spatial_root=root,
                output_path=preview_path,
            )

            self.assertTrue(report["passed"])
            self.assertTrue(preview_path.is_file())
            self.assertTrue(Path(report["report_path"]).is_file())
            self.assertEqual(report["spatial_counts"]["regions"], 1)
            self.assertEqual(report["location_index"][0]["bounds"], {"x": 4, "y": 1, "w": 1, "h": 2})
            self.assertFalse(report["formal_assets_modified_by_preview"])
            self.assertEqual((root / "background.png").read_bytes(), background_before)
            self.assertEqual((root / "location_layer.png").read_bytes(), location_before)
            self.assertEqual((root / "road_layer.png").read_bytes(), road_before)

            with Image.open(preview_path) as preview:
                self.assertEqual(preview.size, (24, 16))
                pixel = preview.convert("RGB").getpixel((19, 11))
                self.assertGreater(pixel[0], pixel[1] * 3)
                self.assertGreater(pixel[0], pixel[2] * 3)
        finally:
            self._remove_tree(root)

    def test_preview_fails_when_manifest_slot_differs_from_stage2(self) -> None:
        root = Path(__file__).parent / f".visual-preview-{uuid.uuid4().hex}"
        root.mkdir()
        try:
            blueprint = self._blueprint()
            manifest = self._write_assets(root, blueprint)
            manifest.slots[0].bounds_px["x"] += 4
            (root / "visual_layout_manifest.json").write_text(
                json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            report = render_visual_validation_preview(
                blueprint=blueprint,
                spatial_root=root,
                output_path=root / "debug" / "preview.png",
            )

            self.assertFalse(report["passed"])
            self.assertIn(
                "location_bounds_mismatch",
                {issue["code"] for issue in report["issues"]},
            )
        finally:
            self._remove_tree(root)

    @staticmethod
    def _write_assets(root: Path, blueprint: SpatialBlueprint):
        manifest = build_visual_layout_manifest(
            blueprint=blueprint,
            world_background={},
            output_root=root,
        )
        manifest.background.status = "ready"
        manifest.background.path = str(root / "background.png")
        manifest.location_layer.status = "ready"
        manifest.location_layer.path = str(root / "location_layer.png")
        manifest.route_layer.status = "ready"
        manifest.route_layer.path = str(root / "road_layer.png")

        Image.new("RGB", (24, 16), (20, 40, 80)).save(root / "background.png")
        location = Image.new("RGBA", (24, 16), (0, 0, 0, 0))
        ImageDraw.Draw(location).rectangle((16, 4, 19, 11), fill=(40, 150, 80, 255))
        location.save(root / "location_layer.png")
        road = Image.new("RGBA", (24, 16), (0, 0, 0, 0))
        ImageDraw.Draw(road).rectangle((4, 4, 15, 7), fill=(210, 180, 80, 255))
        road.save(root / "road_layer.png")
        (root / "visual_layout_manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest

    @staticmethod
    def _blueprint() -> SpatialBlueprint:
        return SpatialBlueprint(
            world_id="visual-preview-test",
            grid=BlueprintGrid(width=6, height=4, tile_size=4),
            regions=[
                BlueprintRegion(
                    location_id="location-1",
                    name="Test Location",
                    bounds={"x": 4, "y": 1, "w": 1, "h": 2},
                    entrance={"x": 4, "y": 1},
                )
            ],
            routes=[
                BlueprintRoute(
                    path_edge_id="path-1",
                    from_location_id="location-1",
                    to_location_id="location-1",
                    centerline=[GridPoint(x=1, y=1), GridPoint(x=4, y=1)],
                )
            ],
            road_tiles=[
                GridPoint(x=1, y=1),
                GridPoint(x=2, y=1),
                GridPoint(x=3, y=1),
                GridPoint(x=4, y=1),
            ],
        )

    @staticmethod
    def _remove_tree(root: Path) -> None:
        if not root.exists():
            return
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        root.rmdir()


if __name__ == "__main__":
    unittest.main()
