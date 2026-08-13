from __future__ import annotations

import base64
import json
import math
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, ValidationError

from worldkernel.architect.spatial.models import SpatialBlueprint


SEVERE_STATUSES = {"major_shift", "missing", "incomplete", "merged"}
CRITICAL_LOCATION_STATUSES = {"missing", "merged"}
STATUS_SCORES = {
    "ok": 100,
    "minor_shift": 75,
    "major_shift": 30,
    "missing": 0,
    "incomplete": 20,
    "merged": 10,
    "marker_remaining": 20,
}
HARD_CONFIDENCE = 0.75
FULL_DISPLACEMENT_OVERLAP = 0.20
ROAD_SEVERE_STATUSES = {"major_shift", "missing", "disconnected"}
ROAD_STATUS_SCORES = {
    "ok": 100,
    "minor_shift": 75,
    "major_shift": 30,
    "missing": 0,
    "disconnected": 15,
    "marker_remaining": 20,
}


class LocationVisualEvaluation(BaseModel):
    number: int
    location_id: str
    status: Literal[
        "ok",
        "minor_shift",
        "major_shift",
        "missing",
        "incomplete",
        "merged",
        "marker_remaining",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_overlap_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    center_position: Literal["inside", "near", "outside", "uncertain"] = "uncertain"
    complete: bool = False
    semantic_match: Literal["yes", "no", "uncertain"] = "uncertain"
    entrance_alignment: Literal["ok", "minor", "blocked", "uncertain"] = "uncertain"
    direction: str = "none"
    merged_with: list[str] = Field(default_factory=list)
    reason: str = ""
    retry_instruction: str = ""


class RoadVisualEvaluation(BaseModel):
    status: Literal[
        "ok",
        "minor_shift",
        "major_shift",
        "missing",
        "disconnected",
        "marker_remaining",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_coverage_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    connected_location_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    continuous: bool = False
    reason: str = ""
    retry_instruction: str = ""


class VisualEvaluationReport(BaseModel):
    summary: str = ""
    locations: list[LocationVisualEvaluation]
    roads: RoadVisualEvaluation


class VisualEvaluationError(RuntimeError):
    pass


class VisualEvaluator:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.model = str(config.get("model") or "qwen3.7-plus")
        self.api_key = str(config.get("api_key") or "")
        base_url = str(config.get("base_url") or "").rstrip("/")
        self.endpoint = str(config.get("chat_endpoint") or "").strip()
        if not self.endpoint and base_url:
            self.endpoint = f"{base_url}/chat/completions"
        self.timeout_seconds = float(config.get("request_timeout_seconds") or 180)
        self.enable_thinking = bool(config.get("enable_thinking", False))
        self.max_tokens = int(config.get("max_tokens") or 6000)
        self.max_candidates = max(1, min(3, int(config.get("max_candidates") or 3)))
        if not bool(config.get("enabled", True)):
            raise VisualEvaluationError("Visual evaluation provider is disabled")
        if not self.api_key:
            raise VisualEvaluationError("Visual evaluation api_key is empty")
        if not self.endpoint:
            raise VisualEvaluationError("Visual evaluation chat endpoint is empty")

    def evaluate(
        self,
        *,
        overview_path: str | Path,
        details_path: str | Path,
        items: list[dict[str, Any]],
        blueprint: SpatialBlueprint,
        attempt: int,
        local_warnings: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        prompt = compose_evaluation_prompt(
            items=items,
            blueprint=blueprint,
            attempt=attempt,
            local_warnings=local_warnings or {},
        )
        content = [
            {"type": "image_url", "image_url": {"url": _image_data_url(Path(overview_path))}},
            {"type": "image_url", "image_url": {"url": _image_data_url(Path(details_path))}},
            {"type": "text", "text": prompt},
        ]
        raw = self._chat([{"role": "user", "content": content}])
        raw_content = _message_content(raw)
        repaired = False
        try:
            report = parse_evaluation_report(raw_content, items)
        except (ValueError, ValidationError) as first_error:
            repaired = True
            repair_prompt = compose_repair_prompt(raw_content, items, str(first_error))
            repair_raw = self._chat([{"role": "user", "content": repair_prompt}])
            try:
                report = parse_evaluation_report(_message_content(repair_raw), items)
            except (ValueError, ValidationError) as repair_error:
                raise VisualEvaluationError(
                    f"Visual evaluation JSON remained invalid after one repair: {repair_error}"
                ) from repair_error
            raw = repair_raw
        decision = decide_evaluation(report)
        return {
            "attempt": attempt,
            "model": self.model,
            "endpoint": self.endpoint,
            "summary": report.summary,
            "locations": [item.model_dump(mode="json") for item in report.locations],
            "roads": report.roads.model_dump(mode="json"),
            "decision": decision,
            "format_repaired": repaired,
            "usage": raw.get("usage") if isinstance(raw.get("usage"), dict) else {},
        }

    def _chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "max_tokens": self.max_tokens,
            "enable_thinking": self.enable_thinking,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise VisualEvaluationError(
                f"Visual evaluation HTTP {exc.code} at {self.endpoint}: {detail[:1000]}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise VisualEvaluationError(
                f"Visual evaluation request failed at {self.endpoint}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise VisualEvaluationError("Visual evaluation API returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise VisualEvaluationError("Visual evaluation API returned a non-object response")
        return result


def render_review_assets(
    *,
    candidate: Image.Image,
    items: list[dict[str, Any]],
    blueprint: SpatialBlueprint | None = None,
    overview_path: str | Path,
    details_path: str | Path,
) -> None:
    overview = candidate.convert("RGB").copy()
    draw = ImageDraw.Draw(overview)
    font = _font(28)
    if blueprint is not None:
        _draw_road_review_overlay(overview, blueprint)
        draw = ImageDraw.Draw(overview)
    for item in items:
        slot = item["slot"]
        bounds = slot.bounds_px
        x = int(bounds.get("x") or 0)
        y = int(bounds.get("y") or 0)
        width = int(bounds.get("w") or 0)
        height = int(bounds.get("h") or 0)
        line_width = max(4, min(8, min(width, height) // 24))
        draw.rectangle(
            (x, y, x + width - 1, y + height - 1),
            outline=(255, 38, 38),
            width=line_width,
        )
        _draw_badge(draw, x, y, str(item["number"]), font)
        _draw_entrance_marker(draw, slot.entrance_port)
    overview_file = Path(overview_path)
    overview_file.parent.mkdir(parents=True, exist_ok=True)
    overview.save(overview_file, format="PNG")
    _render_detail_sheet(overview, items, Path(details_path))


def parse_evaluation_report(
    content: str,
    items: list[dict[str, Any]],
) -> VisualEvaluationReport:
    payload = json.loads(_extract_json_object(content))
    report = VisualEvaluationReport.model_validate(payload)
    expected = {
        (int(item["number"]), str(item["slot"].location_id))
        for item in items
    }
    actual = {(item.number, item.location_id) for item in report.locations}
    if len(actual) != len(report.locations):
        raise ValueError("Visual evaluation report contains duplicate locations")
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(
            f"Visual evaluation locations do not match input; missing={missing}, unexpected={unexpected}"
        )
    return report


def decide_evaluation(report: VisualEvaluationReport) -> dict[str, Any]:
    locations: list[dict[str, Any]] = []
    for item in report.locations:
        effective_status = item.status
        if item.status in {"ok", "minor_shift"} and not item.complete:
            effective_status = "incomplete"
        elif item.status == "minor_shift" and (
            item.center_position == "outside" or item.estimated_overlap_ratio < 0.50
        ):
            effective_status = "major_shift"
        fully_displaced = (
            effective_status == "major_shift"
            and item.center_position == "outside"
            and item.estimated_overlap_ratio < FULL_DISPLACEMENT_OVERLAP
        )
        critical_incident = (
            effective_status in CRITICAL_LOCATION_STATUSES or fully_displaced
        )
        hard_failure = critical_incident or (
            effective_status in SEVERE_STATUSES and item.confidence >= HARD_CONFIDENCE
        )
        warning = (
            effective_status != "ok"
            or item.semantic_match != "yes"
            or item.entrance_alignment not in {"ok", "uncertain"}
        ) and not hard_failure
        score = STATUS_SCORES[effective_status]
        if (
            effective_status in SEVERE_STATUSES
            and item.confidence < HARD_CONFIDENCE
            and not critical_incident
        ):
            score = 60
        if item.entrance_alignment == "blocked":
            score -= 5
        if item.semantic_match == "no":
            score -= 10
        score = max(0, min(100, score))
        locations.append(
            {
                "location_id": item.location_id,
                "number": item.number,
                "hard_failure": hard_failure,
                "critical_incident": critical_incident,
                "fully_displaced": fully_displaced,
                "warning": warning,
                "score": score,
                "status": effective_status,
                "reported_status": item.status,
                "confidence": item.confidence,
            }
        )
    hard_ids = [item["location_id"] for item in locations if item["hard_failure"]]
    critical_ids = [item["location_id"] for item in locations if item["critical_incident"]]
    warning_ids = [item["location_id"] for item in locations if item["warning"]]
    ok_count = sum(1 for item in locations if item["status"] == "ok")
    allowed_warnings = max(2, math.ceil(len(locations) * 0.15))
    scores = [int(item["score"]) for item in locations]
    average = sum(scores) / len(scores) if scores else 0.0
    minimum = min(scores) if scores else 0
    road_status = report.roads.status
    if road_status == "ok" and not report.roads.continuous:
        road_status = "disconnected"
    elif road_status == "minor_shift" and (
        report.roads.estimated_coverage_ratio < 0.70
        or report.roads.connected_location_ratio < 0.70
    ):
        road_status = "major_shift"
    road_hard_failure = (
        road_status in ROAD_SEVERE_STATUSES
        and report.roads.confidence >= HARD_CONFIDENCE
    )
    road_warning = road_status != "ok" and not road_hard_failure
    road_score = ROAD_STATUS_SCORES[road_status]
    if road_status in ROAD_SEVERE_STATUSES and report.roads.confidence < HARD_CONFIDENCE:
        road_score = 60
    total_warning_count = len(warning_ids) + int(road_warning)
    total_hard_failure_count = len(hard_ids) + int(road_hard_failure)
    passed = (
        not hard_ids
        and not road_hard_failure
        and total_warning_count <= allowed_warnings
    )
    combined_alignment = average * 0.85 + road_score * 0.15
    return {
        "passed": passed,
        "hard_failure_location_ids": hard_ids,
        "critical_incident_location_ids": critical_ids,
        "critical_incident_count": len(critical_ids),
        "warning_location_ids": warning_ids,
        "hard_failure_count": total_hard_failure_count,
        "warning_count": total_warning_count,
        "allowed_warning_count": allowed_warnings,
        "ok_count": ok_count,
        "minimum_location_score": minimum,
        "average_location_score": round(average, 2),
        "road_hard_failure": road_hard_failure,
        "road_warning": road_warning,
        "road_status": road_status,
        "road_score": road_score,
        "road": report.roads.model_dump(mode="json"),
        "alignment_score": round(combined_alignment, 2),
        "locations": locations,
    }


def compose_evaluation_prompt(
    *,
    items: list[dict[str, Any]],
    blueprint: SpatialBlueprint,
    attempt: int,
    local_warnings: dict[str, list[str]],
) -> str:
    location_lines = []
    for item in items:
        location = item.get("location") if isinstance(item.get("location"), dict) else {}
        slot = item["slot"]
        name = str(location.get("name") or location.get("location_name") or slot.location_id)
        location_type = str(location.get("location_type") or location.get("type") or "未指定")
        warnings = "、".join(local_warnings.get(slot.location_id, [])) or "无"
        location_lines.append(
            f"{item['number']}. id={slot.location_id}；名称={name}；类型={location_type}；本地提示={warnings}"
        )
    schema = {
        "summary": "整体评价",
        "locations": [
            {
                "number": 1,
                "location_id": "必须原样返回",
                "status": "ok|minor_shift|major_shift|missing|incomplete|merged|marker_remaining",
                "confidence": 0.9,
                "estimated_overlap_ratio": 0.8,
                "center_position": "inside|near|outside|uncertain",
                "complete": True,
                "semantic_match": "yes|no|uncertain",
                "entrance_alignment": "ok|minor|blocked|uncertain",
                "direction": "none 或偏移方向",
                "merged_with": [],
                "reason": "简短理由",
                "retry_instruction": "需要重试时给出简短修正指令",
            }
        ],
        "roads": {
            "status": "ok|minor_shift|major_shift|missing|disconnected|marker_remaining",
            "confidence": 0.9,
            "estimated_coverage_ratio": 0.85,
            "connected_location_ratio": 0.9,
            "continuous": True,
            "reason": "简短理由",
            "retry_instruction": "需要重试时给出简短修正指令",
        },
    }
    return "\n".join(
        [
            f"你是2D游戏地图空间对齐评价员。当前是第 {attempt} 个候选。",
            "第一张图是完整地图，第二张图是相同地点的局部放大图集。",
            "红框表示后端规定的地点期望区域，不是墙体或UI；红色编号与地点清单一一对应。",
            "橙色点是入口格，蓝色半透明走廊和中心线表示后端规定的全部道路位置。",
            "除地点完整性外，还要评价生成道路是否沿蓝色走廊连续出现、是否严重偏移、是否漏掉主要路段，以及是否连接绝大多数地点入口。",
            "允许墙体、平台、屋檐和自然边缘向红框外延伸一格或单边15%，不要追求逐像素重合。",
            "主体中心在框外或主体与框重叠不足50%才评为major_shift；完整且中心仍在框内的少量外扩评为minor_shift。",
            (
                "如果规定红框内漏掉该地点，而对应地点主体完整出现在其他位置，必须评为major_shift，"
                "center_position填outside，estimated_overlap_ratio按原红框的实际重叠填写；"
                "重叠低于20%属于必须重试的完全错位重大事故。"
            ),
            "地点缺失missing或两个地点合并merged属于重大事故：一旦确认必须按该状态报告，不得因置信度较低而降级。",
            "公园、庭院、广场等低密度地点不能仅因内部空旷评为missing。入口和语义问题只需记录，不要单独升级为严重偏移。",
            "道路允许边缘自然起伏和少量装饰，不要求逐像素重合。覆盖主要走廊且连接至少70%地点可评为minor_shift；覆盖不足50%、大段断裂、整体错位或缺失才是严重问题。",
            "必须逐一评价清单中的所有地点，number和location_id必须原样返回，不得遗漏或增加地点。",
            f"道路基准共有 {len({(int(point.x), int(point.y)) for point in blueprint.road_tiles})} 个格子、{len(blueprint.routes)} 条逻辑路线。",
            "只输出一个JSON对象，不要Markdown代码块，不要解释文字。JSON结构示例：",
            json.dumps(schema, ensure_ascii=False),
            "地点清单：",
            *location_lines,
        ]
    )


def compose_repair_prompt(content: str, items: list[dict[str, Any]], error: str) -> str:
    expected = [
        {"number": int(item["number"]), "location_id": str(item["slot"].location_id)}
        for item in items
    ]
    return "\n".join(
        [
            "把下面的视觉评价内容修复为合法JSON。不要重新评价图片，不要添加或删除地点。",
            f"必须包含这些地点：{json.dumps(expected, ensure_ascii=False)}",
            f"校验错误：{error[:500]}",
            "只输出包含summary、locations和roads的JSON对象，不要Markdown。roads必须保留原评价中的道路结论。",
            "原始内容：",
            content[:12000],
        ]
    )


def _render_detail_sheet(overview: Image.Image, items: list[dict[str, Any]], path: Path) -> None:
    columns = max(1, min(4, len(items)))
    rows = max(1, math.ceil(len(items) / columns))
    cell_width = 600
    cell_height = 360
    header_height = 36
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), (22, 24, 28))
    draw = ImageDraw.Draw(sheet)
    font = _font(22)
    for index, item in enumerate(items):
        slot = item["slot"]
        bounds = slot.bounds_px
        tile_size = max(1, int(slot.entrance_port.get("tile_size_px") or 16))
        margin = tile_size * 2
        x = int(bounds.get("x") or 0)
        y = int(bounds.get("y") or 0)
        width = int(bounds.get("w") or 0)
        height = int(bounds.get("h") or 0)
        crop_box = (
            max(0, x - margin),
            max(0, y - margin),
            min(overview.width, x + width + margin),
            min(overview.height, y + height + margin),
        )
        crop = overview.crop(crop_box)
        available = (cell_width - 16, cell_height - header_height - 12)
        scale = min(available[0] / crop.width, available[1] / crop.height)
        resized = crop.resize(
            (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
            Image.Resampling.NEAREST,
        )
        column = index % columns
        row = index // columns
        left = column * cell_width
        top = row * cell_height
        location = item.get("location") if isinstance(item.get("location"), dict) else {}
        name = str(location.get("name") or location.get("location_name") or slot.location_id)
        draw.text((left + 8, top + 6), f"{item['number']}. {name}", fill=(255, 255, 255), font=font)
        paste_x = left + (cell_width - resized.width) // 2
        paste_y = top + header_height + (cell_height - header_height - resized.height) // 2
        sheet.paste(resized, (paste_x, paste_y))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, format="JPEG", quality=90, optimize=True)


def _draw_badge(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font: ImageFont.ImageFont) -> None:
    text_box = draw.textbbox((0, 0), text, font=font)
    width = max(36, text_box[2] - text_box[0] + 16)
    height = max(36, text_box[3] - text_box[1] + 12)
    draw.rectangle((x, y, x + width, y + height), fill=(196, 0, 0), outline=(255, 255, 255), width=2)
    draw.text((x + 8, y + 4 - text_box[1]), text, fill=(255, 255, 255), font=font)


def _draw_entrance_marker(draw: ImageDraw.ImageDraw, port: dict[str, Any]) -> None:
    point = port.get("grid_point") if isinstance(port.get("grid_point"), dict) else {}
    tile_size = max(1, int(port.get("tile_size_px") or 16))
    center_x = int(point.get("x") or 0) * tile_size + tile_size // 2
    center_y = int(point.get("y") or 0) * tile_size + tile_size // 2
    radius = max(5, tile_size // 3)
    draw.ellipse(
        (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
        fill=(255, 145, 0),
        outline=(255, 255, 255),
        width=2,
    )
    vectors = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
    dx, dy = vectors.get(str(port.get("side") or "south"), (0, 1))
    draw.line(
        (
            center_x,
            center_y,
            center_x + dx * tile_size * 2,
            center_y + dy * tile_size * 2,
        ),
        fill=(0, 210, 255),
        width=max(3, tile_size // 4),
    )


def _draw_road_review_overlay(image: Image.Image, blueprint: SpatialBlueprint) -> None:
    tile_size = max(1, int(blueprint.grid.tile_size))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    for point in {(int(point.x), int(point.y)) for point in blueprint.road_tiles}:
        x = point[0] * tile_size
        y = point[1] * tile_size
        draw.rectangle(
            (x, y, x + tile_size - 1, y + tile_size - 1),
            fill=(0, 185, 255, 58),
        )
    width = max(3, tile_size // 4)
    for route in blueprint.routes:
        points = [
            (int((point.x + 0.5) * tile_size), int((point.y + 0.5) * tile_size))
            for point in route.centerline
        ]
        if len(points) >= 2:
            draw.line(points, fill=(0, 225, 255, 230), width=width)
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"))


def _message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise VisualEvaluationError("Visual evaluation API returned no choices")
    message = choices[0].get("message")
    if not isinstance(message, dict) or not str(message.get("content") or "").strip():
        raise VisualEvaluationError("Visual evaluation API returned empty content")
    return str(message["content"])


def _extract_json_object(content: str) -> str:
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Visual evaluation response does not contain a JSON object")
    return cleaned[start : end + 1]


def _image_data_url(path: Path) -> str:
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()
