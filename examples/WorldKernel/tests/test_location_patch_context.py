from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from worldkernel.architect.visual.layout import _build_entrance_port
from worldkernel.architect.visual.location_prompt import compose_location_patch_prompt
from worldkernel.architect.visual.location_patches import (
    _location_edit_config,
    _prepare_location_context,
    _save_full_context_patch,
    _validate_protected_context,
)
from worldkernel.architect.visual.models import VisualSlot


class LocationPatchContextTests(unittest.TestCase):
    def test_entrance_contract_supports_all_sides(self) -> None:
        bounds = {"x": 10, "y": 20, "w": 8, "h": 6}
        cases = {
            "north": {"x": 13, "y": 20},
            "south": {"x": 13, "y": 25},
            "west": {"x": 10, "y": 22},
            "east": {"x": 17, "y": 22},
        }
        for expected_side, entrance in cases.items():
            with self.subTest(side=expected_side):
                region = SimpleNamespace(bounds=bounds, entrance=entrance)
                port = _build_entrance_port(region, 16)
                self.assertEqual(port["side"], expected_side)
                self.assertEqual(port["width_tiles"], 1)
                self.assertEqual(port["entry_depth_tiles"], 1)

    def test_context_mask_keeps_the_entire_slot_editable(self) -> None:
        background = Image.new("RGB", (800, 600), (32, 48, 64))
        ImageDraw.Draw(background).rectangle((0, 0, 799, 599), outline=(80, 96, 112), width=8)
        slot = self._slot(side="south")
        context = _prepare_location_context(
            background=background,
            slot=slot,
            context_size=512,
            tile_size=16,
        )
        self.assertEqual(context["image"].size, (512, 512))
        self.assertEqual(context["mask"].size, (512, 512))
        alpha = context["mask"].getchannel("A")
        editable_pixels = alpha.histogram()[0]
        self.assertEqual(editable_pixels, 240 * 176)
        self.assertNotIn("entrance_box", context)
        pixels = (
            context["image"].get_flattened_data()
            if hasattr(context["image"], "get_flattened_data")
            else context["image"].getdata()
        )
        self.assertNotIn((185, 157, 92), set(pixels))

    def test_full_context_patch_is_kept_without_slot_crop(self) -> None:
        slot = self._slot(side="east")
        context = _prepare_location_context(
            background=Image.new("RGB", (800, 600), (48, 64, 80)),
            slot=slot,
            context_size=512,
            tile_size=16,
        )
        request_image = context["image"].resize((1024, 1024), Image.Resampling.NEAREST)
        request_mask = context["mask"].resize((1024, 1024), Image.Resampling.NEAREST)
        editable = request_mask.getchannel("A").point(lambda value: 255 if value == 0 else 0)
        generated = request_image.copy()
        generated.paste((120, 80, 40), mask=editable)

        paths = self._temporary_paths("extract", 4)
        input_path, mask_path, generated_path, output_path = paths
        try:
            request_image.save(input_path)
            request_mask.save(mask_path)
            generated.save(generated_path)
            validation = _validate_protected_context(input_path, generated_path, mask_path)
            self.assertTrue(validation["exact_preservation"])
            _save_full_context_patch(
                generated_path=generated_path,
                output_path=output_path,
                native_context_size=(512, 512),
            )
            with Image.open(output_path) as patch:
                self.assertEqual(patch.size, (512, 512))
        finally:
            self._remove_paths(paths)

    def test_small_protected_pixel_change_is_measured(self) -> None:
        image = Image.new("RGB", (16, 16), (10, 20, 30))
        generated = image.copy()
        generated.putpixel((0, 0), (11, 20, 30))
        mask = Image.new("RGBA", (16, 16), (255, 255, 255, 255))
        paths = self._temporary_paths("protected", 3)
        input_path, generated_path, mask_path = paths
        try:
            image.save(input_path)
            generated.save(generated_path)
            mask.save(mask_path)
            validation = _validate_protected_context(input_path, generated_path, mask_path)
            self.assertFalse(validation["exact_preservation"])
            self.assertTrue(validation["passed"])
            self.assertEqual(validation["changed_pixels"], 1)
        finally:
            self._remove_paths(paths)

    def test_large_protected_context_change_is_only_recorded(self) -> None:
        image = Image.new("RGB", (32, 32), (10, 20, 30))
        generated = Image.new("RGB", (32, 32), (220, 210, 200))
        mask = Image.new("RGBA", (32, 32), (255, 255, 255, 255))
        paths = self._temporary_paths("unrelated", 3)
        input_path, generated_path, mask_path = paths
        try:
            image.save(input_path)
            generated.save(generated_path)
            mask.save(mask_path)
            validation = _validate_protected_context(input_path, generated_path, mask_path)
            self.assertTrue(validation["passed"])
            self.assertFalse(validation["within_guideline"])
            self.assertEqual(validation["validation_mode"], "diagnostic_only")
        finally:
            self._remove_paths(paths)

    def test_request_size_must_be_an_integer_context_scale(self) -> None:
        self.assertEqual(
            _location_edit_config(
                {
                    "location_patch_context_size": 512,
                    "location_patch_request_scale": 2,
                    "location_patch_request_size": "1024x1024",
                }
            ),
            (512, (1024, 1024), 2),
        )
        with self.assertRaisesRegex(ValueError, "must equal"):
            _location_edit_config(
                {
                    "location_patch_context_size": 512,
                    "location_patch_request_scale": 2,
                    "location_patch_request_size": "768x768",
                }
            )

    def test_prompt_uses_coordinate_only_entrance_guidance(self) -> None:
        payload = compose_location_patch_prompt(
            world_background={"world_name": "测试世界"},
            visual_profile={"art_style": "明亮卡通像素风"},
            location={"name": "测试地点", "visual": "无屋顶的档案室"},
            slot=self._slot(side="south"),
            generation_size=(1024, 1024),
        )
        self.assertIn("已经清除临时道路颜色", payload["prompt"])
        self.assertIn("最终道路会在后续图层中连接", payload["prompt"])
        self.assertIn("不要自行绘制道路", payload["prompt"])
        self.assertNotIn("输入图已经包含地点最终所在位置的周边环境和道路", payload["prompt"])

    @staticmethod
    def _slot(*, side: str) -> VisualSlot:
        return VisualSlot(
            location_id="location-1",
            bounds_px={"x": 120, "y": 96, "w": 240, "h": 176},
            safe_padding_px=0,
            blend_margin_px=32,
            z_index=100,
            expected_projection="top-down",
            entrance_port={
                "side": side,
                "offset_tiles": 7 if side in {"north", "south"} else 5,
                "width_tiles": 1,
                "entry_depth_tiles": 1,
                "tile_size_px": 16,
            },
        )

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
