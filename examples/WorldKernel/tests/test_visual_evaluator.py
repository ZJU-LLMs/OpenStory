from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from worldkernel.architect.spatial.models import BlueprintGrid, SpatialBlueprint
from worldkernel.architect.visual.models import VisualSlot
from worldkernel.architect.visual.visual_evaluator import (
    LocationVisualEvaluation,
    RoadVisualEvaluation,
    VisualEvaluator,
    VisualEvaluationReport,
    decide_evaluation,
    parse_evaluation_report,
    render_review_assets,
)


class VisualEvaluatorTests(unittest.TestCase):
    def test_review_assets_use_exact_dynamic_slot_coordinates(self) -> None:
        items = self._items(3)
        root = Path(__file__).parent / f".visual-evaluator-{uuid.uuid4().hex}"
        root.mkdir()
        try:
            overview_path = root / "overview.png"
            details_path = root / "details.jpg"
            render_review_assets(
                candidate=Image.new("RGB", (640, 400), (40, 60, 80)),
                items=items,
                overview_path=overview_path,
                details_path=details_path,
            )
            with Image.open(overview_path) as image:
                overview = image.convert("RGB")
            for item in items:
                bounds = item["slot"].bounds_px
                pixel = overview.getpixel((bounds["x"] + bounds["w"] - 1, bounds["y"]))
                self.assertGreater(pixel[0], 220)
                self.assertLess(pixel[1], 90)
            with Image.open(details_path) as details:
                self.assertEqual(details.width, 1800)
                self.assertEqual(details.height, 360)
        finally:
            for path in root.iterdir():
                path.unlink(missing_ok=True)
            root.rmdir()

    def test_report_parser_accepts_fenced_json_and_requires_all_locations(self) -> None:
        items = self._items(2)
        payload = {
            "summary": "正常",
            "locations": [self._evaluation(index, item["slot"].location_id).model_dump(mode="json") for index, item in enumerate(items, start=1)],
            "roads": self._road_evaluation().model_dump(mode="json"),
        }
        report = parse_evaluation_report(
            "说明文字\n```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```",
            items,
        )
        self.assertEqual(len(report.locations), 2)
        payload["locations"].pop()
        with self.assertRaises(ValueError):
            parse_evaluation_report(json.dumps(payload, ensure_ascii=False), items)

    def test_confidence_and_overlap_boundaries_are_balanced(self) -> None:
        low_confidence = self._evaluation(
            1,
            "location-1",
            status="major_shift",
            confidence=0.74,
            overlap=0.49,
            center="outside",
        )
        decision = decide_evaluation(VisualEvaluationReport(locations=[low_confidence], roads=self._road_evaluation()))
        self.assertFalse(decision["hard_failure_location_ids"])
        self.assertEqual(decision["warning_location_ids"], ["location-1"])

        high_confidence = low_confidence.model_copy(update={"confidence": 0.75})
        decision = decide_evaluation(VisualEvaluationReport(locations=[high_confidence], roads=self._road_evaluation()))
        self.assertEqual(decision["hard_failure_location_ids"], ["location-1"])

        overlap_49 = self._evaluation(
            1,
            "location-1",
            status="minor_shift",
            confidence=0.9,
            overlap=0.49,
            center="near",
        )
        decision = decide_evaluation(VisualEvaluationReport(locations=[overlap_49], roads=self._road_evaluation()))
        self.assertEqual(decision["locations"][0]["status"], "major_shift")

        overlap_50 = overlap_49.model_copy(update={"estimated_overlap_ratio": 0.50})
        decision = decide_evaluation(VisualEvaluationReport(locations=[overlap_50], roads=self._road_evaluation()))
        self.assertEqual(decision["locations"][0]["status"], "minor_shift")

    def test_low_density_complete_location_is_not_rejected(self) -> None:
        courtyard = self._evaluation(
            1,
            "location-1",
            status="ok",
            confidence=0.83,
            overlap=0.72,
            center="inside",
            complete=True,
        )
        decision = decide_evaluation(VisualEvaluationReport(locations=[courtyard], roads=self._road_evaluation()))
        self.assertTrue(decision["passed"])
        self.assertEqual(decision["alignment_score"], 100.0)

    def test_high_confidence_disconnected_roads_trigger_retry(self) -> None:
        location = self._evaluation(1, "location-1")
        roads = self._road_evaluation(
            status="disconnected",
            confidence=0.82,
            estimated_coverage_ratio=0.72,
            connected_location_ratio=0.55,
            continuous=False,
        )
        decision = decide_evaluation(
            VisualEvaluationReport(locations=[location], roads=roads)
        )
        self.assertFalse(decision["passed"])
        self.assertTrue(decision["road_hard_failure"])
        self.assertEqual(decision["road_status"], "disconnected")

    def test_low_confidence_minor_road_shift_remains_a_warning(self) -> None:
        location = self._evaluation(1, "location-1")
        roads = self._road_evaluation(
            status="minor_shift",
            confidence=0.6,
            estimated_coverage_ratio=0.75,
            connected_location_ratio=0.85,
            continuous=True,
        )
        decision = decide_evaluation(
            VisualEvaluationReport(locations=[location], roads=roads)
        )
        self.assertTrue(decision["passed"])
        self.assertFalse(decision["road_hard_failure"])
        self.assertTrue(decision["road_warning"])

    def test_missing_and_merged_locations_are_critical_regardless_of_confidence(self) -> None:
        missing = self._evaluation(
            1,
            "location-1",
            status="missing",
            confidence=0.31,
            overlap=0.0,
            center="uncertain",
            complete=False,
        )
        merged = self._evaluation(
            2,
            "location-2",
            status="merged",
            confidence=0.42,
            overlap=0.7,
            center="inside",
        )
        decision = decide_evaluation(
            VisualEvaluationReport(
                locations=[missing, merged],
                roads=self._road_evaluation(),
            )
        )
        self.assertFalse(decision["passed"])
        self.assertEqual(
            decision["critical_incident_location_ids"],
            ["location-1", "location-2"],
        )
        self.assertEqual(decision["hard_failure_count"], 2)
        self.assertEqual(decision["locations"][0]["score"], 0)
        self.assertEqual(decision["locations"][1]["score"], 10)

    def test_invalid_json_is_repaired_once(self) -> None:
        items = self._items(1)
        root = Path(__file__).parent / f".visual-evaluator-repair-{uuid.uuid4().hex}"
        root.mkdir()
        try:
            overview = root / "overview.png"
            details = root / "details.jpg"
            Image.new("RGB", (32, 32), (0, 0, 0)).save(overview)
            Image.new("RGB", (32, 32), (0, 0, 0)).save(details)
            valid_payload = {
                "summary": "已修复",
                "locations": [self._evaluation(1, "location-1").model_dump(mode="json")],
                "roads": self._road_evaluation().model_dump(mode="json"),
            }
            client = VisualEvaluator(
                {
                    "model": "fake-qwen",
                    "api_key": "test-key",
                    "chat_endpoint": "https://example.invalid/v1/chat/completions",
                }
            )
            with patch.object(
                client,
                "_chat",
                side_effect=[
                    {"choices": [{"message": {"content": "not-json"}}]},
                    {"choices": [{"message": {"content": json.dumps(valid_payload, ensure_ascii=False)}}]},
                ],
            ) as chat:
                result = client.evaluate(
                    overview_path=overview,
                    details_path=details,
                    items=items,
                    blueprint=SpatialBlueprint(
                        world_id="evaluation-test",
                        grid=BlueprintGrid(width=40, height=25, tile_size=16),
                    ),
                    attempt=1,
                )
            self.assertTrue(result["format_repaired"])
            self.assertEqual(chat.call_count, 2)
            self.assertTrue(result["decision"]["passed"])
        finally:
            for path in root.iterdir():
                path.unlink(missing_ok=True)
            root.rmdir()

    @staticmethod
    def _items(count: int) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for index in range(count):
            slot = VisualSlot(
                location_id=f"location-{index + 1}",
                bounds_px={"x": 48 + index * 180, "y": 64, "w": 128, "h": 96},
                safe_padding_px=0,
                blend_margin_px=0,
                z_index=100,
                expected_projection="top-down",
                entrance_port={
                    "side": "south",
                    "offset_tiles": 4,
                    "width_tiles": 1,
                    "tile_size_px": 16,
                    "grid_point": {"x": 7 + index * 11, "y": 9},
                },
            )
            items.append(
                {
                    "number": index + 1,
                    "slot": slot,
                    "location": {"name": f"地点{index + 1}", "location_type": "庭院"},
                }
            )
        return items

    @staticmethod
    def _evaluation(
        number: int,
        location_id: str,
        *,
        status: str = "ok",
        confidence: float = 0.9,
        overlap: float = 0.8,
        center: str = "inside",
        complete: bool = True,
    ) -> LocationVisualEvaluation:
        return LocationVisualEvaluation(
            number=number,
            location_id=location_id,
            status=status,
            confidence=confidence,
            estimated_overlap_ratio=overlap,
            center_position=center,
            complete=complete,
            semantic_match="yes",
            entrance_alignment="ok",
            direction="none",
            merged_with=[],
            reason="测试",
            retry_instruction="",
        )

    @staticmethod
    def _road_evaluation(**updates: object) -> RoadVisualEvaluation:
        payload = {
            "status": "ok",
            "confidence": 0.9,
            "estimated_coverage_ratio": 0.9,
            "connected_location_ratio": 0.9,
            "continuous": True,
            "reason": "道路连续",
            "retry_instruction": "",
        }
        payload.update(updates)
        return RoadVisualEvaluation(**payload)


if __name__ == "__main__":
    unittest.main()
