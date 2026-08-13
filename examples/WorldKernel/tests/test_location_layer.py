from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageOps

from worldkernel.architect.spatial.models import (
    BlueprintGrid,
    BlueprintRegion,
    GridPoint,
    SpatialBlueprint,
)
from worldkernel.architect.visual.layout import build_visual_layout_manifest
from worldkernel.architect.visual.location_layer import (
    _draw_location_marker,
    build_initial_location_edit_mask,
    compose_location_correction_prompt,
    compose_location_map_prompt,
    generate_location_layer,
)
from worldkernel.architect.visual.pipeline import run_visual_pipeline


class _FakeImageClient:
    calls: list[dict[str, object]] = []
    attempt_count = 0
    failures_remaining = 0
    model_output_size: tuple[int, int] | None = None

    def __init__(self, config: dict[str, object]):
        self.config = config

    def generate(
        self,
        prompt: str,
        output_path: str | Path,
        *,
        size: str,
        input_image_path: str | Path | None = None,
        mask_path: str | Path | None = None,
        **_: object,
    ) -> dict[str, object]:
        type(self).attempt_count += 1
        if type(self).failures_remaining > 0:
            type(self).failures_remaining -= 1
            raise RuntimeError("Image API HTTP 502 at fake endpoint")
        if input_image_path is None:
            raise AssertionError("full-canvas location editing requires an input image")
        mask_size = None
        mask_mode = None
        if mask_path is not None:
            with Image.open(mask_path) as mask_image:
                mask_size = mask_image.size
                mask_mode = mask_image.mode
        with Image.open(input_image_path) as source_image:
            result = ImageOps.invert(source_image.convert("RGB"))
        if type(self).model_output_size is not None:
            result = result.resize(type(self).model_output_size, Image.Resampling.NEAREST)
        result.save(output_path, format="PNG")
        self.calls.append(
            {
                "size": size,
                "input_size": result.size,
                "prompt": prompt,
                "has_mask": mask_path is not None,
                "mask_size": mask_size,
                "mask_mode": mask_mode,
            }
        )
        return {
            "provider": "fake",
            "model": "fake-image-2",
            "api_style": "openai_compatible_edit",
            "size": size,
        }


class _FakeVisualEvaluator:
    calls: list[dict[str, object]] = []
    pass_on_attempt = 1

    def __init__(self, config: dict[str, object]):
        self.config = config
        self.model = "fake-qwen"
        self.max_candidates = 3

    def evaluate(
        self,
        *,
        items: list[dict[str, object]],
        attempt: int,
        **_: object,
    ) -> dict[str, object]:
        locations = []
        decisions = []
        hard_ids = []
        for item in items:
            slot = item["slot"]
            location_id = slot.location_id
            failed = attempt < self.pass_on_attempt and not hard_ids
            status = "major_shift" if failed else "ok"
            score = 30 if failed else 100
            if failed:
                hard_ids.append(location_id)
            locations.append(
                {
                    "number": item["number"],
                    "location_id": location_id,
                    "status": status,
                    "confidence": 0.95,
                    "estimated_overlap_ratio": 0.3 if failed else 0.9,
                    "center_position": "outside" if failed else "inside",
                    "complete": True,
                    "semantic_match": "yes",
                    "entrance_alignment": "ok",
                    "direction": "none",
                    "merged_with": [],
                    "reason": "shifted" if failed else "aligned",
                    "retry_instruction": "将完整主体移回红框中心" if failed else "",
                }
            )
            decisions.append(
                {
                    "location_id": location_id,
                    "number": item["number"],
                    "hard_failure": failed,
                    "warning": False,
                    "score": score,
                    "status": status,
                    "confidence": 0.95,
                }
            )
        self.calls.append({"attempt": attempt, "location_count": len(items)})
        return {
            "attempt": attempt,
            "model": self.model,
            "endpoint": "fake",
            "summary": "all aligned",
            "locations": locations,
            "roads": {
                "status": "ok",
                "confidence": 0.95,
                "estimated_coverage_ratio": 0.9,
                "connected_location_ratio": 0.9,
                "continuous": True,
                "reason": "aligned",
                "retry_instruction": "",
            },
            "decision": {
                "passed": not hard_ids,
                "hard_failure_location_ids": hard_ids,
                "warning_location_ids": [],
                "hard_failure_count": len(hard_ids),
                "warning_count": 0,
                "allowed_warning_count": 2,
                "ok_count": len(items) - len(hard_ids),
                "minimum_location_score": 30 if hard_ids else 100,
                "average_location_score": 82.5 if hard_ids else 100.0,
                "alignment_score": 82.5 if hard_ids else 100.0,
                "road_hard_failure": False,
                "road_warning": False,
                "road_status": "ok",
                "road_score": 100,
                "locations": decisions,
            },
            "format_repaired": False,
            "usage": {},
        }


class LocationLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeImageClient.calls = []
        _FakeImageClient.attempt_count = 0
        _FakeImageClient.failures_remaining = 0
        _FakeImageClient.model_output_size = None
        _FakeVisualEvaluator.calls = []
        _FakeVisualEvaluator.pass_on_attempt = 1

    def test_prompt_includes_every_dynamic_location(self) -> None:
        blueprint = self._blueprint(extra_locations=3)
        manifest = build_visual_layout_manifest(blueprint, {}, None)
        items = [
            {
                "number": index,
                "slot": slot,
                "location": {"name": f"地点 {index}", "visual": "完整房间"},
            }
            for index, slot in enumerate(manifest.slots, start=1)
        ]
        payload = compose_location_map_prompt(
            world_background={"world_name": "测试世界"},
            visual_profile={"camera_projection": "严格正交俯视"},
            items=items,
            canvas_size=(640, 400),
        )
        self.assertIn("640×400 像素", payload["prompt"])
        self.assertIn("不得缩小、放大、裁剪、扩边", payload["prompt"])
        self.assertEqual(len(payload["locations"]), 7)
        self.assertTrue(all(f"{index}｜地点 {index}｜" in payload["prompt"] for index in range(1, 8)))
        self.assertIn("同时完成全部地点与连接道路", payload["prompt"])
        self.assertIn("道路必须沿青绿色走廊连续生成", payload["prompt"])
        self.assertIn("尺寸较大且容易辨认的标志性陈设", payload["prompt"])
        self.assertIn("不用密集小物件或细碎纹理", payload["prompt"])
        self.assertTrue(
            payload["prompt"].endswith(
                "最终输出图片的物理画布必须严格保持为 640×400 像素，"
                "不得缩小、放大、裁剪、扩边或改成近似尺寸。"
            )
        )

    def test_correction_prompt_repeats_physical_canvas_size(self) -> None:
        payload = compose_location_correction_prompt(
            base_payload={"canvas_size": {"width": 640, "height": 400}},
            items=[],
            evaluation={},
            attempt=2,
        )

        self.assertIn("640×400 像素", payload["prompt"])
        self.assertIn("不得缩小、放大、裁剪、扩边", payload["prompt"])
        self.assertTrue(
            payload["prompt"].endswith(
                "最终输出图片的物理画布必须严格保持为 640×400 像素，"
                "不得缩小、放大、裁剪、扩边或改成近似尺寸。"
            )
        )

    def test_prompt_keeps_structure_and_landmarks_without_full_narrative(self) -> None:
        blueprint = self._blueprint()
        manifest = build_visual_layout_manifest(blueprint, {}, None)
        location = {
            "name": "记忆结算厅",
            "location_type": "室内",
            "visual": (
                "无屋顶的RPG剖面房间：大厅呈圆形同心结构，中央保留环形通道。"
                "地面是浅灰金属板，墙体是低纹理银灰合金。"
                "标志性陈设：中央结算晶柱、环形柜台、记忆胶囊架、入口安检闸机。"
                "照明冷白，背景历史极其复杂但不影响可画结构。"
            ),
        }
        payload = compose_location_map_prompt(
            world_background={"world_name": "测试世界"},
            visual_profile={"camera_projection": "严格正交俯视"},
            items=[{"number": 1, "slot": manifest.slots[0], "location": location}],
            canvas_size=(640, 400),
        )
        prompt = payload["prompt"]
        self.assertIn("圆形同心结构", prompt)
        self.assertIn("中央结算晶柱", prompt)
        self.assertIn("环形柜台", prompt)
        self.assertIn("浅灰金属板", prompt)
        self.assertNotIn("背景历史极其复杂", prompt)
        self.assertIn("名称只用于理解语义，不得画进图中", prompt)
        self.assertEqual(payload["prompt_role"], "location_full_map_edit")
        self.assertFalse(payload["background_prompt_reused"])

    def test_location_number_marker_is_small_and_kept_out_of_center(self) -> None:
        blueprint = self._blueprint()
        manifest = build_visual_layout_manifest(blueprint, {}, None)
        image = Image.new("RGB", (640, 400), (20, 30, 40))
        slot = manifest.slots[0]
        _draw_location_marker(image, slot, 1)
        bounds = slot.bounds_px
        center = (
            int(bounds["x"]) + int(bounds["w"]) // 2,
            int(bounds["y"]) + int(bounds["h"]) // 2,
        )
        self.assertEqual(image.getpixel(center), (20, 30, 40))

    def test_generation_uses_one_full_canvas_pass_without_resize_or_crop(self) -> None:
        blueprint = self._blueprint()
        manifest = build_visual_layout_manifest(
            blueprint,
            {
                "visual_profile": {
                    "art_style": "明亮整洁的卡通像素游戏风格",
                    "camera_projection": "严格正交俯视",
                }
            },
            None,
        )
        root = Path(__file__).parent / f".location-layer-{uuid.uuid4().hex}"
        root.mkdir()
        try:
            background_path = root / "background.png"
            debug_root = root / "debug" / "location_attempts"
            Image.new("RGB", (640, 400), (48, 80, 64)).save(background_path)
            manifest_path = root / "visual_layout_manifest.json"
            semantic_locations = [
                {
                    "id": slot.location_id,
                    "name": f"地点 {index}",
                    "location_type": "室内",
                    "visual": "完整的无屋顶像素房间，少量标志性陈设",
                }
                for index, slot in enumerate(manifest.slots, start=1)
            ]
            semantic_locations.append(
                {
                    "id": "semantic-only-location",
                    "name": "未进入空间蓝图的语义地点",
                    "location_type": "室内",
                    "visual": "该地点不应阻塞或进入视觉生成",
                }
            )
            with (
                patch(
                    "worldkernel.architect.visual.location_layer.load_model_config_by_capability",
                    return_value={"name": "fake", "model": "fake-image-2"},
                ),
                patch(
                    "worldkernel.architect.visual.location_layer.ImageGenerationClient",
                    _FakeImageClient,
                ),
                patch(
                    "worldkernel.architect.visual.location_layer.VisualEvaluator",
                    _FakeVisualEvaluator,
                ),
            ):
                metadata = generate_location_layer(
                    blueprint=blueprint,
                    manifest=manifest,
                    world_background={"world_name": "测试世界"},
                    semantic_locations=semantic_locations,
                    root=root,
                    model_config_path=root / "unused.yaml",
                    background_reference_path=background_path,
                    progress_manifest_path=manifest_path,
                    debug_artifact_root=debug_root,
                )

            self.assertEqual(len(_FakeImageClient.calls), 1)
            self.assertEqual(_FakeImageClient.calls[0]["size"], "640x400")
            self.assertEqual(_FakeImageClient.calls[0]["input_size"], (640, 400))
            self.assertTrue(_FakeImageClient.calls[0]["has_mask"])
            self.assertEqual(_FakeImageClient.calls[0]["mask_size"], (640, 400))
            self.assertEqual(_FakeImageClient.calls[0]["mask_mode"], "RGBA")
            self.assertIn("青框和左上角小编号只是位置索引", _FakeImageClient.calls[0]["prompt"])
            self.assertTrue(metadata["resize_or_crop"] is False)
            self.assertFalse(metadata["single_pass"])
            self.assertFalse(metadata["mask_commit"])
            self.assertTrue(metadata["initial_request_mask_used"])
            self.assertEqual(metadata["initial_request_mask"]["expansion_tiles"], 1)
            self.assertEqual(metadata["layer_mode"], "full_canvas_locations_and_roads_replacement")
            self.assertTrue(metadata["includes_roads"])
            self.assertEqual(metadata["evaluation_status"], "passed")
            self.assertEqual(metadata["attempt_count"], 1)
            self.assertEqual(metadata["selected_attempt"], 1)
            self.assertEqual(len(_FakeVisualEvaluator.calls), 1)
            self.assertEqual(_FakeVisualEvaluator.calls[0]["location_count"], 4)
            self.assertEqual(metadata["ready_location_count"], 4)
            self.assertEqual(metadata["failed_location_count"], 0)
            self.assertTrue(metadata["debug_artifacts_retained"])
            self.assertEqual(metadata["debug_artifact_root"], str(debug_root))
            self.assertTrue((debug_root / "location_attempt_1_input.png").is_file())
            self.assertTrue((debug_root / "location_attempt_1_mask.png").is_file())
            self.assertTrue((debug_root / "location_attempt_1.png").is_file())
            self.assertTrue((debug_root / "location_attempt_1_overview.png").is_file())
            self.assertTrue((debug_root / "location_attempt_1_details.jpg").is_file())
            self.assertEqual(manifest.location_layer.status, "ready")
            self.assertEqual(manifest.location_patches if hasattr(manifest, "location_patches") else [], [])

            with Image.open(root / "location_layer.png") as layer_image:
                layer = layer_image.convert("RGBA")
            self.assertEqual(layer.size, (640, 400))
            self.assertEqual(layer.getpixel((0, 0))[3], 255)
            self.assertEqual(layer.getpixel((0, 0))[:3], (207, 175, 191))
            self.assertEqual(layer.getpixel((3 * 16, 3 * 16))[3], 255)
            saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn("location_patches", saved_manifest)
            self.assertEqual(saved_manifest["location_layer"]["status"], "ready")
        finally:
            for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()

    def test_generation_normalizes_candidate_before_visual_review(self) -> None:
        blueprint = self._blueprint()
        manifest = build_visual_layout_manifest(blueprint, {}, None)
        root = Path(__file__).parent / f".location-layer-{uuid.uuid4().hex}"
        root.mkdir()
        try:
            background_path = root / "background.png"
            debug_root = root / "debug" / "location_attempts"
            Image.new("RGB", (640, 400), (48, 80, 64)).save(background_path)
            semantic_locations = [
                {
                    "id": slot.location_id,
                    "name": f"地点 {index}",
                    "location_type": "室内",
                    "visual": "完整的无屋顶像素房间",
                }
                for index, slot in enumerate(manifest.slots, start=1)
            ]
            _FakeImageClient.model_output_size = (320, 200)
            with (
                patch(
                    "worldkernel.architect.visual.location_layer.load_model_config_by_capability",
                    return_value={"name": "fake", "model": "fake-image-2"},
                ),
                patch(
                    "worldkernel.architect.visual.location_layer.ImageGenerationClient",
                    _FakeImageClient,
                ),
                patch(
                    "worldkernel.architect.visual.location_layer.VisualEvaluator",
                    _FakeVisualEvaluator,
                ),
            ):
                metadata = generate_location_layer(
                    blueprint=blueprint,
                    manifest=manifest,
                    world_background={"world_name": "测试世界"},
                    semantic_locations=semantic_locations,
                    root=root,
                    model_config_path=root / "unused.yaml",
                    background_reference_path=background_path,
                    debug_artifact_root=debug_root,
                )

            with Image.open(debug_root / "location_attempt_1_model_output.png") as original:
                self.assertEqual(original.size, (320, 200))
            with Image.open(debug_root / "location_attempt_1.png") as normalized:
                self.assertEqual(normalized.size, (640, 400))
            with Image.open(root / "location_layer.png") as layer:
                self.assertEqual(layer.size, (640, 400))
            self.assertTrue(metadata["resize_or_crop"])
            self.assertTrue(metadata["size_normalization"]["normalized"])
            self.assertEqual(len(_FakeVisualEvaluator.calls), 1)
        finally:
            for path in sorted(root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()

    def test_failed_visual_review_retries_and_selects_second_candidate(self) -> None:
        blueprint = self._blueprint()
        manifest = build_visual_layout_manifest(blueprint, {}, None)
        root = Path(__file__).parent / f".location-layer-retry-{uuid.uuid4().hex}"
        root.mkdir()
        try:
            background_path = root / "background.png"
            Image.new("RGB", (640, 400), (48, 80, 64)).save(background_path)
            semantic_locations = [
                {"id": slot.location_id, "name": slot.location_id, "visual": "完整地点"}
                for slot in manifest.slots
            ]
            _FakeVisualEvaluator.pass_on_attempt = 2
            with (
                patch(
                    "worldkernel.architect.visual.location_layer.load_model_config_by_capability",
                    return_value={"name": "fake", "model": "fake-image-2"},
                ),
                patch(
                    "worldkernel.architect.visual.location_layer.ImageGenerationClient",
                    _FakeImageClient,
                ),
                patch(
                    "worldkernel.architect.visual.location_layer.VisualEvaluator",
                    _FakeVisualEvaluator,
                ),
            ):
                metadata = generate_location_layer(
                    blueprint=blueprint,
                    manifest=manifest,
                    world_background={"world_name": "测试世界"},
                    semantic_locations=semantic_locations,
                    root=root,
                    model_config_path=root / "unused.yaml",
                    background_reference_path=background_path,
                )
            self.assertEqual(len(_FakeImageClient.calls), 2)
            self.assertTrue(_FakeImageClient.calls[0]["has_mask"])
            self.assertFalse(_FakeImageClient.calls[1]["has_mask"])
            self.assertEqual(len(_FakeVisualEvaluator.calls), 2)
            self.assertEqual(metadata["selected_attempt"], 2)
            self.assertEqual(metadata["attempt_count"], 2)
            self.assertEqual(metadata["status"], "ready")
            report = json.loads((root / "location_alignment_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["selected_attempt"], 2)
        finally:
            for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()

    def test_transient_502_retries_same_location_request_once(self) -> None:
        blueprint = self._blueprint()
        manifest = build_visual_layout_manifest(blueprint, {}, None)
        root = Path(__file__).parent / f".location-layer-transport-{uuid.uuid4().hex}"
        root.mkdir()
        try:
            background_path = root / "background.png"
            Image.new("RGB", (640, 400), (48, 80, 64)).save(background_path)
            semantic_locations = [
                {"id": slot.location_id, "name": slot.location_id, "visual": "完整地点"}
                for slot in manifest.slots
            ]
            _FakeImageClient.failures_remaining = 1
            with (
                patch(
                    "worldkernel.architect.visual.location_layer.load_model_config_by_capability",
                    return_value={"name": "fake", "model": "fake-image-2"},
                ),
                patch(
                    "worldkernel.architect.visual.location_layer.ImageGenerationClient",
                    _FakeImageClient,
                ),
                patch(
                    "worldkernel.architect.visual.location_layer.VisualEvaluator",
                    _FakeVisualEvaluator,
                ),
                patch("worldkernel.architect.visual.location_layer.time.sleep", return_value=None),
            ):
                metadata = generate_location_layer(
                    blueprint=blueprint,
                    manifest=manifest,
                    world_background={"world_name": "测试世界"},
                    semantic_locations=semantic_locations,
                    root=root,
                    model_config_path=root / "unused.yaml",
                    background_reference_path=background_path,
                )
            self.assertEqual(_FakeImageClient.attempt_count, 2)
            self.assertEqual(len(_FakeImageClient.calls), 1)
            self.assertEqual(metadata["status"], "ready")
        finally:
            for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()

    def test_initial_inverse_mask_exposes_all_locations_and_roads(self) -> None:
        tile_size = 16
        regions = [
            BlueprintRegion(
                location_id="north",
                name="北入口",
                bounds={"x": 3, "y": 3, "w": 4, "h": 4},
                entrance={"x": 4, "y": 3},
            ),
            BlueprintRegion(
                location_id="south",
                name="南入口",
                bounds={"x": 10, "y": 3, "w": 4, "h": 4},
                entrance={"x": 11, "y": 6},
            ),
            BlueprintRegion(
                location_id="west",
                name="西入口",
                bounds={"x": 3, "y": 12, "w": 4, "h": 4},
                entrance={"x": 3, "y": 13},
            ),
            BlueprintRegion(
                location_id="east",
                name="东入口",
                bounds={"x": 10, "y": 12, "w": 4, "h": 4},
                entrance={"x": 13, "y": 13},
            ),
        ]
        road_tiles = [
            GridPoint(x=4, y=2),
            GridPoint(x=11, y=7),
            GridPoint(x=2, y=13),
            GridPoint(x=14, y=13),
            GridPoint(x=4, y=4),
            GridPoint(x=7, y=4),
        ]
        blueprint = SpatialBlueprint(
            world_id="inverse-mask-test",
            grid=BlueprintGrid(width=20, height=20, tile_size=tile_size),
            regions=regions,
            road_tiles=road_tiles,
        )
        manifest = build_visual_layout_manifest(blueprint, {}, None)
        mask, metadata = build_initial_location_edit_mask(
            blueprint=blueprint,
            manifest=manifest,
            canvas_size=(320, 320),
        )
        alpha = mask.getchannel("A")

        def tile_alpha(x: int, y: int) -> int:
            return alpha.getpixel((x * tile_size + tile_size // 2, y * tile_size + tile_size // 2))

        self.assertEqual(mask.mode, "RGBA")
        self.assertEqual(mask.size, (320, 320))
        self.assertEqual(tile_alpha(0, 0), 255)
        self.assertEqual(tile_alpha(2, 3), 0)
        self.assertEqual(tile_alpha(4, 2), 0)
        self.assertEqual(tile_alpha(11, 7), 0)
        self.assertEqual(tile_alpha(2, 13), 0)
        self.assertEqual(tile_alpha(14, 13), 0)
        self.assertEqual(tile_alpha(4, 4), 0)
        self.assertEqual(tile_alpha(7, 4), 0)
        self.assertEqual(metadata["location_count"], 4)
        self.assertEqual(metadata["entrance_connector_tile_count"], 4)
        self.assertEqual(metadata["protected_road_pixels"], 0)
        self.assertEqual(metadata["road_tile_count"], len(road_tiles))
        self.assertEqual(metadata["editable_road_pixels"], len(road_tiles) * tile_size * tile_size)

    def test_pipeline_does_not_publish_an_unreviewed_existing_layer_after_failure(self) -> None:
        blueprint = self._blueprint()
        root = Path(__file__).parent / f".location-layer-failure-{uuid.uuid4().hex}"
        root.mkdir()
        try:
            Image.new("RGB", (640, 400), (48, 80, 64)).save(root / "background.png")
            Image.new("RGBA", (640, 400), (255, 0, 0, 255)).save(root / "location_layer.png")
            semantic_locations = [
                {"id": region.location_id, "name": region.name, "visual": "完整地点"}
                for region in blueprint.regions
            ]
            with patch(
                "worldkernel.architect.visual.pipeline.generate_location_layer_asset",
                side_effect=RuntimeError("evaluation unavailable"),
            ):
                manifest = run_visual_pipeline(
                    blueprint=blueprint,
                    world_background={},
                    output_root=root,
                    model_config_path=root / "unused.yaml",
                    generate_background=False,
                    generate_location_layer=True,
                    semantic_locations=semantic_locations,
                )

            self.assertEqual(manifest.location_layer.status, "failed")
            self.assertEqual(manifest.location_layer.evaluation_status, "failed")
            self.assertEqual(manifest.location_layer.path, "")
            self.assertEqual(manifest.location_layer.url, "")
            self.assertEqual(manifest.location_layer.completed_location_ids, [])
            self.assertEqual(
                set(manifest.location_layer.failed_location_ids),
                {region.location_id for region in blueprint.regions},
            )
            saved = json.loads((root / "visual_layout_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["location_layer"]["status"], "failed")
            self.assertEqual(saved["location_layer"]["url"], "")
        finally:
            for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()

    @staticmethod
    def _blueprint(*, extra_locations: int = 0) -> SpatialBlueprint:
        regions = [
            BlueprintRegion(
                location_id="location-1",
                name="地点一",
                bounds={"x": 2, "y": 2, "w": 8, "h": 6},
                entrance={"x": 9, "y": 4},
            ),
            BlueprintRegion(
                location_id="location-2",
                name="地点二",
                bounds={"x": 28, "y": 2, "w": 8, "h": 6},
                entrance={"x": 28, "y": 4},
            ),
            BlueprintRegion(
                location_id="location-3",
                name="地点三",
                bounds={"x": 2, "y": 16, "w": 8, "h": 6},
                entrance={"x": 9, "y": 18},
            ),
            BlueprintRegion(
                location_id="location-4",
                name="地点四",
                bounds={"x": 28, "y": 16, "w": 8, "h": 6},
                entrance={"x": 28, "y": 18},
            ),
        ]
        extra_bounds = [
            (14, 2),
            (14, 9),
            (14, 16),
        ]
        for index in range(extra_locations):
            x, y = extra_bounds[index]
            regions.append(
                BlueprintRegion(
                    location_id=f"location-{index + 5}",
                    name=f"地点{index + 5}",
                    bounds={"x": x, "y": y, "w": 6, "h": 5},
                    entrance={"x": x + 5, "y": y + 2},
                )
            )
        return SpatialBlueprint(
            world_id="location-layer-test",
            grid=BlueprintGrid(width=40, height=25, tile_size=16),
            road_tiles=[GridPoint(x=10, y=y) for y in range(1, 24)],
            regions=regions,
        )


if __name__ == "__main__":
    unittest.main()
