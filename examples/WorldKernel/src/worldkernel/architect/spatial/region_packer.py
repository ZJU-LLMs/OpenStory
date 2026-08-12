"""Phase C: RegionPacker — constrained rectangle placement for location regions."""

from __future__ import annotations

import math
import logging

from worldkernel.architect.spatial.config import SpatialGenerationConfig
from worldkernel.architect.spatial.models import (
    LocationLayout,
    LocationSpatialFact,
    LayoutPlan,
    RegionPackingResult,
    SpatialBuildInput,
    SpatialInputWarning,
    SpatialRegion,
)

logger = logging.getLogger(__name__)

# Importance → priority (lower = placed first)
_IMPORTANCE_PRIORITY: dict[str, int] = {
    "core": 0,
    "major": 1,
    "minor": 3,
}

class RegionPacker:
    """Places non-overlapping rectangles around location center points."""

    def pack(
        self,
        layout_plan: LayoutPlan,
        build_input: SpatialBuildInput,
        config: SpatialGenerationConfig,
    ) -> RegionPackingResult:
        warnings: list[SpatialInputWarning] = []
        canvas = config.canvas
        margin = canvas.margin_tiles
        grid_w = canvas.grid_width
        grid_h = canvas.grid_height
        hard_gap = max(1, canvas.corridor_width + 1)
        min_gap = max(0, config.layout.min_region_gap, hard_gap)
        preferred_gap = max(min_gap, config.layout.preferred_region_gap)
        edge_comfort_margin = max(
            margin,
            config.layout.edge_comfort_margin + preferred_gap,
        )
        candidate_limit = max(1, config.layout.candidate_limit)

        # Index location facts and layout by id
        loc_facts: dict[str, LocationSpatialFact] = {
            loc.location_id: loc for loc in build_input.locations
        }
        layout_map: dict[str, LocationLayout] = {
            loc.location_id: loc for loc in layout_plan.locations
        }

        # Build adjacency from paths
        adj: dict[str, set[str]] = {}
        for path in build_input.paths:
            adj.setdefault(path.from_location_id, set()).add(path.to_location_id)
            if path.bidirectional:
                adj.setdefault(path.to_location_id, set()).add(path.from_location_id)

        # Sort by priority then location_id for determinism
        sorted_ids = sorted(
            layout_map.keys(),
            key=lambda nid: (
                _IMPORTANCE_PRIORITY.get(loc_facts[nid].importance, 2) if nid in loc_facts else 2,
                nid,
            ),
        )

        # Size estimation
        min_w, min_h = canvas.default_region_min_size
        max_w, max_h = canvas.default_region_max_size

        placed: list[SpatialRegion] = []
        placed_rects: dict[str, tuple[int, int, int, int]] = {}  # id -> (x, y, w, h)
        placed_approaches: dict[str, tuple[int, int]] = {}
        for nid in sorted_ids:
            layout = layout_map[nid]
            fact = loc_facts.get(nid)
            importance = fact.importance if fact else ""
            tags = list(fact.tags) if fact else []
            name = fact.name if fact else nid

            target_w, target_h = self._estimate_size(importance, min_w, min_h, max_w, max_h)

            # Try to place at target size
            region = self._try_place(
                nid, name, tags, layout, target_w, target_h,
                margin, grid_w, grid_h, placed_rects, placed_approaches, adj, layout_map,
                config.layout.packing_max_attempts, min_gap, preferred_gap,
                edge_comfort_margin, candidate_limit, importance,
            )

            # If failed and non-core, try shrinking to min size
            if region is None and importance != "core":
                if target_w != min_w or target_h != min_h:
                    warnings.append(SpatialInputWarning(
                        code="region_shrunk",
                        message=(
                            f"location {nid!r} could not be placed at "
                            f"{target_w}x{target_h}; shrunk to {min_w}x{min_h}"
                        ),
                        source="region_packer",
                        item_id=nid,
                    ))
                    region = self._try_place(
                        nid, name, tags, layout, min_w, min_h,
                        margin, grid_w, grid_h, placed_rects, placed_approaches, adj, layout_map,
                        config.layout.packing_max_attempts, min_gap, preferred_gap,
                        edge_comfort_margin, candidate_limit, importance,
                    )

            if region is None:
                warnings.append(SpatialInputWarning(
                    code="region_placement_failed",
                    message=(
                        f"location {nid!r} could not be placed after "
                        f"{config.layout.packing_max_attempts} attempts; skipped"
                    ),
                    source="region_packer",
                    item_id=nid,
                ))
                continue

            placed.append(region)
            placed_rects[nid] = (region.x, region.y, region.width, region.height)
            placed_approaches[nid] = self._approach_point(region)

        used_centered_fallback = False
        effective_min_gap = min_gap
        if len(placed) != len(sorted_ids):
            centered = self._pack_centered_fallback(
                sorted_ids,
                layout_map,
                loc_facts,
                margin,
                grid_w,
                grid_h,
                min_gap,
                hard_gap,
                min_w,
                min_h,
                max_w,
                max_h,
            )
            if centered is not None:
                placed, effective_min_gap = centered
                placed_rects = {
                    region.location_id: (region.x, region.y, region.width, region.height)
                    for region in placed
                }
                used_centered_fallback = True
                warnings.append(SpatialInputWarning(
                    code="centered_repack_used",
                    message=(
                        "constraint placement left locations unplaced; "
                        "repacked every location around the canvas center"
                    ),
                    source="region_packer",
                ))

        placed = [
            self._repair_entrance_after_packing(
                region, placed_rects, grid_w, grid_h, margin, effective_min_gap,
            )
            for region in placed
        ]

        return RegionPackingResult(
            regions=placed,
            warnings=warnings,
            provenance={
                "algorithm": "constrained_rect_packing",
                "candidate_scoring": True,
                "placed_count": len(placed),
                "failed_count": len(sorted_ids) - len(placed),
                "margin_tiles": margin,
                "min_region_gap": effective_min_gap,
                "preferred_region_gap": preferred_gap,
                "centered_repack_used": used_centered_fallback,
                "near_edge_count": self._near_edge_count(placed, grid_w, grid_h, edge_comfort_margin),
                "avg_nearest_region_gap": self._avg_nearest_region_gap(placed),
            },
        )

    def _pack_centered_fallback(
        self,
        sorted_ids: list[str],
        layout_map: dict[str, LocationLayout],
        loc_facts: dict[str, LocationSpatialFact],
        margin: int,
        grid_w: int,
        grid_h: int,
        min_gap: int,
        hard_gap: int,
        min_w: int,
        min_h: int,
        max_w: int,
        max_h: int,
    ) -> tuple[list[SpatialRegion], int] | None:
        """Retry all regions around the center while preserving FR directions.

        The search is exhaustive over valid top-left positions, but candidate
        scores follow each location's force-layout direction. Stable jitter and
        row/column alignment penalties avoid a shelf-like visual result.
        """
        canvas_cx = grid_w / 2.0
        canvas_cy = grid_h / 2.0

        def _attempt(
            force_min_size: bool,
            gap: int,
            compression: float,
            ordered_ids: list[str],
        ) -> list[SpatialRegion] | None:
            result: list[SpatialRegion] = []
            placed_rects: dict[str, tuple[int, int, int, int]] = {}
            placed_centers: list[tuple[float, float]] = []
            for nid in ordered_ids:
                fact = loc_facts.get(nid)
                importance = fact.importance if fact else ""
                if force_min_size:
                    width, height = min_w, min_h
                else:
                    width, height = self._estimate_size(
                        importance, min_w, min_h, max_w, max_h,
                    )

                layout = layout_map[nid]
                seed = sum((index + 1) * ord(char) for index, char in enumerate(nid))
                jitter_span = max(2, min(6, gap))
                jitter_x = seed % (jitter_span * 2 + 1) - jitter_span
                jitter_y = (seed // 17) % (jitter_span * 2 + 1) - jitter_span
                target_cx = (
                    canvas_cx
                    + (layout.center_x - canvas_cx) * compression
                    + jitter_x
                )
                target_cy = (
                    canvas_cy
                    + (layout.center_y - canvas_cy) * compression
                    + jitter_y
                )

                candidates: list[tuple[float, int, int]] = []
                max_x = grid_w - margin - width
                max_y = grid_h - margin - height
                for y in range(margin, max_y + 1):
                    for x in range(margin, max_x + 1):
                        if not self._is_valid(
                            x, y, width, height, margin, grid_w, grid_h,
                            placed_rects, gap,
                        ):
                            continue
                        center_x = x + width / 2.0
                        center_y = y + height / 2.0
                        score = math.hypot(center_x - target_cx, center_y - target_cy)
                        for existing_x, existing_y in placed_centers:
                            x_alignment = abs(center_x - existing_x)
                            y_alignment = abs(center_y - existing_y)
                            if x_alignment < 4:
                                score += (4 - x_alignment) * 2.5
                            if y_alignment < 4:
                                score += (4 - y_alignment) * 2.5
                        candidates.append((score, y, x))

                if not candidates:
                    return None

                _, y, x = min(candidates)

                result.append(SpatialRegion(
                    location_id=nid,
                    name=fact.name if fact else nid,
                    layer_id=layout_map[nid].layer_id,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    entrance_x=x + width // 2,
                    entrance_y=y + height - 1,
                    tags=list(fact.tags) if fact else [],
                ))
                placed_rects[nid] = (x, y, width, height)
                placed_centers.append((x + width / 2.0, y + height / 2.0))
            return self._center_packed_regions(result, margin, grid_w, grid_h)

        center_first = sorted(
            sorted_ids,
            key=lambda nid: (
                math.hypot(
                    layout_map[nid].center_x - canvas_cx,
                    layout_map[nid].center_y - canvas_cy,
                ),
                sorted_ids.index(nid),
            ),
        )
        attempts = [
            (False, min_gap, 0.76, sorted_ids),
            (True, min_gap, 0.76, sorted_ids),
            (True, hard_gap, 0.82, sorted_ids),
            (True, hard_gap, 0.68, center_first),
        ]
        for force_min_size, gap, compression, ordered_ids in attempts:
            packed = _attempt(force_min_size, gap, compression, ordered_ids)
            if packed is not None:
                return packed, gap
        return None

    @staticmethod
    def _center_packed_regions(
        regions: list[SpatialRegion],
        margin: int,
        grid_w: int,
        grid_h: int,
    ) -> list[SpatialRegion]:
        if not regions:
            return []
        left = min(region.x for region in regions)
        top = min(region.y for region in regions)
        right = max(region.x + region.width for region in regions)
        bottom = max(region.y + region.height for region in regions)
        shift_x = round(grid_w / 2.0 - (left + right) / 2.0)
        shift_y = round(grid_h / 2.0 - (top + bottom) / 2.0)
        shift_x = max(margin - left, min(grid_w - margin - right, shift_x))
        shift_y = max(margin - top, min(grid_h - margin - bottom, shift_y))
        return [
            region.model_copy(update={
                "x": region.x + shift_x,
                "y": region.y + shift_y,
                "entrance_x": region.entrance_x + shift_x,
                "entrance_y": region.entrance_y + shift_y,
            })
            for region in regions
        ]

    # ------------------------------------------------------------------
    # Size estimation
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_size(
        importance: str,
        min_w: int, min_h: int,
        max_w: int, max_h: int,
    ) -> tuple[int, int]:
        if importance == "core":
            return max_w, max_h
        if importance == "minor":
            return min_w, min_h
        # major, unknown, etc.
        return (max_w + min_w) // 2, (max_h + min_h) // 2

    # ------------------------------------------------------------------
    # Placement attempt
    # ------------------------------------------------------------------

    def _try_place(
        self,
        nid: str,
        name: str,
        tags: list[str],
        layout: LocationLayout,
        w: int, h: int,
        margin: int,
        grid_w: int, grid_h: int,
        placed_rects: dict[str, tuple[int, int, int, int]],
        placed_approaches: dict[str, tuple[int, int]],
        adj: dict[str, set[str]],
        layout_map: dict[str, LocationLayout],
        max_attempts: int,
        min_gap: int,
        preferred_gap: int,
        edge_comfort_margin: int,
        candidate_limit: int,
        importance: str,
    ) -> SpatialRegion | None:
        """Collect valid rectangle candidates and choose the best-scored one."""
        anchor_x = layout.center_x - w // 2
        anchor_y = layout.center_y - h // 2
        candidates: list[tuple[float, int, int, int, tuple[int, int]]] = []
        min_search_radius = max(preferred_gap * 2, edge_comfort_margin // 2)

        def _try_candidate(cx: int, cy: int, attempts: int) -> None:
            entrance = self._compute_entrance(
                cx, cy, w, h, nid, adj, placed_rects, layout_map,
                grid_w, grid_h, margin, min_gap,
            )
            if not self._is_valid(
                cx, cy, w, h, margin, grid_w, grid_h, placed_rects, min_gap,
            ):
                return
            if not self._keeps_existing_approaches_clear(
                cx, cy, w, h, placed_approaches,
            ):
                return
            if not self._preserves_all_approaches(
                cx, cy, w, h, placed_rects, grid_w, grid_h, margin,
            ):
                return
            score = self._score_candidate(
                cx, cy, w, h, anchor_x, anchor_y, grid_w, grid_h,
                placed_rects, adj.get(nid, set()), layout_map, importance, tags,
                preferred_gap, edge_comfort_margin,
            )
            candidates.append((score, attempts, cx, cy, entrance))

        attempts = 0
        _try_candidate(anchor_x, anchor_y, attempts)
        for radius in range(1, max(grid_w, grid_h)):
            # Visit the complete Chebyshev ring. The previous implementation
            # checked only eight rays per radius and could report failure while
            # large valid areas between those rays remained unexplored.
            ring = [
                *((dx, -radius) for dx in range(-radius, radius + 1)),
                *((dx, radius) for dx in range(-radius, radius + 1)),
                *((-radius, dy) for dy in range(-radius + 1, radius)),
                *((radius, dy) for dy in range(-radius + 1, radius)),
            ]
            for dx, dy in ring:
                if attempts >= max_attempts:
                    break
                attempts += 1
                cx = anchor_x + dx * radius
                cy = anchor_y + dy * radius
                _try_candidate(cx, cy, attempts)
                if len(candidates) >= candidate_limit and radius >= min_search_radius:
                    break
            if attempts >= max_attempts or (
                len(candidates) >= candidate_limit and radius >= min_search_radius
            ):
                break

        if not candidates:
            return None

        _, _, best_x, best_y, entrance = min(candidates, key=lambda item: (item[0], item[1], item[2], item[3]))
        return SpatialRegion(
            location_id=nid, name=name, layer_id=layout.layer_id,
            x=best_x, y=best_y, width=w, height=h,
            entrance_x=entrance[0], entrance_y=entrance[1],
            tags=tags,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _is_valid(
        x: int, y: int, w: int, h: int,
        margin: int, grid_w: int, grid_h: int,
        placed_rects: dict[str, tuple[int, int, int, int]],
        min_gap: int,
    ) -> bool:
        # Canvas bounds with margin
        if x < margin or y < margin:
            return False
        if x + w > grid_w - margin or y + h > grid_h - margin:
            return False
        # Overlap and hard gap check
        for ox, oy, ow, oh in placed_rects.values():
            if not (
                x + w + min_gap <= ox
                or ox + ow + min_gap <= x
                or y + h + min_gap <= oy
                or oy + oh + min_gap <= y
            ):
                return False
        return True

    @classmethod
    def _keeps_existing_approaches_clear(
        cls,
        x: int,
        y: int,
        w: int,
        h: int,
        placed_approaches: dict[str, tuple[int, int]],
    ) -> bool:
        """Ensure a new rectangle does not occupy any existing entrance approach tile.

        Uses strict containment (0-gap) — the approach tile must not be inside
        the new rectangle, but the min_gap buffer around the rectangle is fine
        because approach tiles are already in the corridor zone guaranteed by _is_valid.
        """
        candidate = (x, y, w, h)
        for ax, ay in placed_approaches.values():
            if cls._point_too_close_to_rect(ax, ay, candidate, 0):
                return False
        return True

    @classmethod
    def _preserves_all_approaches(
        cls,
        nx: int, ny: int, nw: int, nh: int,
        placed_rects: dict[str, tuple[int, int, int, int]],
        grid_w: int, grid_h: int, margin: int,
    ) -> bool:
        """After placing the candidate, every existing rectangle must still
        have at least one edge whose approach tile (1 tile outside) is not
        inside any other rectangle (including the candidate).
        """
        # Build the hypothetical rect set: existing + candidate
        all_rects = list(placed_rects.values()) + [(nx, ny, nw, nh)]

        for ox, oy, ow, oh in placed_rects.values():
            # 4 edge approach tiles for this existing rect
            approaches = [
                (ox + ow // 2, oy - 1),           # top
                (ox + ow // 2, oy + oh),            # bottom
                (ox - 1, oy + oh // 2),             # left
                (ox + ow, oy + oh // 2),            # right
            ]
            has_clear = False
            for ax, ay in approaches:
                if ax < margin or ay < margin or ax >= grid_w - margin or ay >= grid_h - margin:
                    continue
                inside_any = False
                for rx, ry, rw, rh in all_rects:
                    if rx == ox and ry == oy and rw == ow and rh == oh:
                        continue  # skip self
                    if rx <= ax < rx + rw and ry <= ay < ry + rh:
                        inside_any = True
                        break
                if not inside_any:
                    has_clear = True
                    break
            if not has_clear:
                return False
        return True

    # ------------------------------------------------------------------
    # Candidate scoring
    # ------------------------------------------------------------------

    @classmethod
    def _score_candidate(
        cls,
        x: int, y: int, w: int, h: int,
        anchor_x: int, anchor_y: int,
        grid_w: int, grid_h: int,
        placed_rects: dict[str, tuple[int, int, int, int]],
        neighbors: set[str],
        layout_map: dict[str, LocationLayout],
        importance: str,
        tags: list[str],
        preferred_gap: int,
        edge_comfort_margin: int,
    ) -> float:
        cx = x + w / 2.0
        cy = y + h / 2.0
        anchor_cx = anchor_x + w / 2.0
        anchor_cy = anchor_y + h / 2.0
        score = math.hypot(cx - anchor_cx, cy - anchor_cy)

        canvas_cx = grid_w / 2.0
        canvas_cy = grid_h / 2.0
        center_dist = math.hypot(cx - canvas_cx, cy - canvas_cy)
        center_weight = cls._center_weight(importance, tags)
        score += center_dist * center_weight

        edge_gap = min(x, y, grid_w - (x + w), grid_h - (y + h))
        if edge_gap < edge_comfort_margin:
            score += (edge_comfort_margin - edge_gap) ** 2 * 2.0

        nearest_gap = cls._nearest_gap((x, y, w, h), list(placed_rects.values()))
        if nearest_gap is not None and nearest_gap < preferred_gap:
            score += (preferred_gap - nearest_gap) ** 2 * 3.0

        placed_neighbor_centers: list[tuple[float, float]] = []
        for neighbor_id in neighbors:
            if neighbor_id in placed_rects:
                nx, ny, nw, nh = placed_rects[neighbor_id]
                placed_neighbor_centers.append((nx + nw / 2.0, ny + nh / 2.0))
            elif neighbor_id in layout_map:
                nl = layout_map[neighbor_id]
                placed_neighbor_centers.append((float(nl.center_x), float(nl.center_y)))
        if placed_neighbor_centers:
            avg_dist = sum(math.hypot(cx - nx, cy - ny) for nx, ny in placed_neighbor_centers) / len(placed_neighbor_centers)
            score += max(0.0, avg_dist - 45.0) ** 2 * 0.002

        return score

    @staticmethod
    def _center_weight(importance: str, tags: list[str]) -> float:
        tag_set = set(tags)
        if "secret" in tag_set or "hidden" in tag_set or "restricted" in tag_set:
            return -0.08
        if importance == "core" or "public" in tag_set or "communal" in tag_set:
            return 0.22
        if importance == "major":
            return 0.10
        if importance == "minor":
            return 0.04
        return 0.06

    # ------------------------------------------------------------------
    # Entrance computation
    # ------------------------------------------------------------------

    @classmethod
    def _compute_entrance(
        cls,
        rx: int, ry: int, rw: int, rh: int,
        nid: str,
        adj: dict[str, set[str]],
        placed_rects: dict[str, tuple[int, int, int, int]],
        layout_map: dict[str, LocationLayout],
        grid_w: int,
        grid_h: int,
        margin: int,
        min_gap: int,
    ) -> tuple[int, int]:
        """Find an edge entrance. Every location is guaranteed to get one."""
        neighbors = adj.get(nid, set())

        # Find connected regions that are already placed
        connected_centers: list[tuple[float, float]] = []
        for neighbor_id in neighbors:
            if neighbor_id in placed_rects:
                nx, ny, nw, nh = placed_rects[neighbor_id]
                connected_centers.append((nx + nw / 2.0, ny + nh / 2.0))
            elif neighbor_id in layout_map:
                nl = layout_map[neighbor_id]
                connected_centers.append((float(nl.center_x), float(nl.center_y)))

        # Edge midpoint plus outside approach tile: top, bottom, left, right
        entrances = [
            ((rx + rw // 2, ry), (rx + rw // 2, ry - 1)),
            ((rx + rw // 2, ry + rh - 1), (rx + rw // 2, ry + rh)),
            ((rx, ry + rh // 2), (rx - 1, ry + rh // 2)),
            ((rx + rw - 1, ry + rh // 2), (rx + rw, ry + rh // 2)),
        ]
        valid_entrances = [
            (entrance, approach)
            for entrance, approach in entrances
            if cls._is_approach_clear(approach, placed_rects, grid_w, grid_h, margin, min_gap)
        ]

        def _pick_by_preference(candidates: list[tuple[tuple[int, int], tuple[int, int]]]) -> tuple[int, int]:
            if not connected_centers:
                # Prefer bottom, then right, left, top for stable defaults.
                for preferred in [entrances[1][0], entrances[3][0], entrances[2][0], entrances[0][0]]:
                    for entrance, _ in candidates:
                        if entrance == preferred:
                            return entrance
                return candidates[0][0]
            avg_cx = sum(c[0] for c in connected_centers) / len(connected_centers)
            avg_cy = sum(c[1] for c in connected_centers) / len(connected_centers)
            best, _ = min(
                candidates,
                key=lambda pair: (pair[0][0] - avg_cx) ** 2 + (pair[0][1] - avg_cy) ** 2,
            )
            return best

        if valid_entrances:
            return _pick_by_preference(valid_entrances)

        # Fallback: all approach tiles are blocked by other rectangles.
        # Pick the entrance whose approach tile is furthest from any rect center,
        # so it faces the most open space.
        def _approach_clearance_score(approach: tuple[int, int]) -> float:
            ax, ay = approach
            if not placed_rects:
                return 1e9
            min_dist = min(
                math.hypot(ax - (ox + ow / 2), ay - (oy + oh / 2))
                for ox, oy, ow, oh in placed_rects.values()
            )
            return min_dist

        best_entrance, _ = max(entrances, key=lambda pair: _approach_clearance_score(pair[1]))
        return best_entrance

    @staticmethod
    def _is_approach_clear(
        approach: tuple[int, int],
        placed_rects: dict[str, tuple[int, int, int, int]],
        grid_w: int,
        grid_h: int,
        margin: int,
        min_gap: int,
    ) -> bool:
        """Check that the approach tile (1 tile outside entrance) is not inside another rect.

        We only check strict containment (0-gap), NOT min_gap proximity.
        The min_gap corridor between rectangles is already guaranteed by _is_valid,
        so the approach tile at distance 1 from the entrance is always within that
        corridor and therefore always walkable.
        """
        ax, ay = approach
        if ax < margin or ay < margin or ax >= grid_w - margin or ay >= grid_h - margin:
            return False
        for ox, oy, ow, oh in placed_rects.values():
            if ox <= ax < ox + ow and oy <= ay < oy + oh:
                return False
        return True

    @staticmethod
    def _point_too_close_to_rect(
        px: int,
        py: int,
        rect: tuple[int, int, int, int],
        min_gap: int,
    ) -> bool:
        x, y, w, h = rect
        return (
            x - min_gap <= px <= x + w - 1 + min_gap
            and y - min_gap <= py <= y + h - 1 + min_gap
        )

    @staticmethod
    def _approach_point(region: SpatialRegion) -> tuple[int, int]:
        if region.entrance_y == region.y:
            return region.entrance_x, region.entrance_y - 1
        if region.entrance_y == region.y + region.height - 1:
            return region.entrance_x, region.entrance_y + 1
        if region.entrance_x == region.x:
            return region.entrance_x - 1, region.entrance_y
        return region.entrance_x + 1, region.entrance_y

    @classmethod
    def _repair_entrance_after_packing(
        cls,
        region: SpatialRegion,
        placed_rects: dict[str, tuple[int, int, int, int]],
        grid_w: int,
        grid_h: int,
        margin: int,
        min_gap: int,
    ) -> SpatialRegion:
        rx, ry, rw, rh = region.x, region.y, region.width, region.height
        own_rect = (rx, ry, rw, rh)
        entrances = [
            ((rx + rw // 2, ry + rh - 1), (rx + rw // 2, ry + rh)),
            ((rx + rw - 1, ry + rh // 2), (rx + rw, ry + rh // 2)),
            ((rx, ry + rh // 2), (rx - 1, ry + rh // 2)),
            ((rx + rw // 2, ry), (rx + rw // 2, ry - 1)),
        ]
        other_rects = [
            rect for loc_id, rect in placed_rects.items()
            if loc_id != region.location_id and rect != own_rect
        ]
        for entrance, approach in entrances:
            ax, ay = approach
            if ax < margin or ay < margin or ax >= grid_w - margin or ay >= grid_h - margin:
                continue
            if any(cls._point_too_close_to_rect(ax, ay, rect, min_gap) for rect in other_rects):
                continue
            return region.model_copy(update={"entrance_x": entrance[0], "entrance_y": entrance[1]})
        return region

    @staticmethod
    def _rect_gap(
        a: tuple[int, int, int, int],
        b: tuple[int, int, int, int],
    ) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        dx = max(bx - (ax + aw), ax - (bx + bw), 0)
        dy = max(by - (ay + ah), ay - (by + bh), 0)
        return math.hypot(dx, dy)

    @classmethod
    def _nearest_gap(
        cls,
        rect: tuple[int, int, int, int],
        placed_rects: list[tuple[int, int, int, int]],
    ) -> float | None:
        if not placed_rects:
            return None
        return min(cls._rect_gap(rect, other) for other in placed_rects)

    @classmethod
    def _avg_nearest_region_gap(cls, regions: list[SpatialRegion]) -> float:
        if len(regions) < 2:
            return 0.0
        rects = [(r.x, r.y, r.width, r.height) for r in regions]
        gaps = []
        for i, rect in enumerate(rects):
            others = rects[:i] + rects[i + 1:]
            nearest = cls._nearest_gap(rect, others)
            if nearest is not None:
                gaps.append(nearest)
        return sum(gaps) / len(gaps) if gaps else 0.0

    @staticmethod
    def _near_edge_count(
        regions: list[SpatialRegion],
        grid_w: int,
        grid_h: int,
        edge_comfort_margin: int,
    ) -> int:
        count = 0
        for region in regions:
            edge_gap = min(
                region.x,
                region.y,
                grid_w - (region.x + region.width),
                grid_h - (region.y + region.height),
            )
            if edge_gap < edge_comfort_margin:
                count += 1
        return count
