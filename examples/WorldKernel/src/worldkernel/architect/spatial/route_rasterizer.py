"""Phase D: RouteRasterizer — converts semantic path edges into walkable tile routes."""

from __future__ import annotations

import logging

from worldkernel.architect.spatial.config import SpatialGenerationConfig
from worldkernel.architect.spatial.graph_algorithms import (
    astar_weighted_orthogonal,
    bfs_components,
)
from worldkernel.architect.spatial.models import (
    GridPoint,
    LayoutPlan,
    PathSpatialFact,
    RegionPackingResult,
    RouteRasterizationResult,
    SpatialBuildInput,
    SpatialInputWarning,
    SpatialRegion,
    SpatialRoute,
)

logger = logging.getLogger(__name__)

_ROAD_BLOCKED = 0
_ROAD_REGION = 1
_ROAD_CORRIDOR = 2
_ROAD_ENTRANCE = 3
_ROAD_CENTERLINE = 4


class RouteRasterizer:
    """Converts semantic path edges into tile-level routes on a collision grid."""

    def rasterize(
        self,
        build_input: SpatialBuildInput,
        layout_plan: LayoutPlan,
        packing_result: RegionPackingResult,
        config: SpatialGenerationConfig,
    ) -> RouteRasterizationResult:
        warnings: list[SpatialInputWarning] = []
        grid_w = config.canvas.grid_width
        grid_h = config.canvas.grid_height
        corridor_w = config.canvas.corridor_width
        blocked = config.grid_values.blocked
        walkable = config.grid_values.walkable

        # 1. Initialize collision grid and internal road grid.
        # collision grid remains public: 0 = blocked, 1 = walkable.
        # road grid is internal and keeps richer routing semantics.
        grid = [[blocked] * grid_w for _ in range(grid_h)]
        road_grid = [[_ROAD_BLOCKED] * grid_w for _ in range(grid_h)]

        # 2. Index regions by location_id
        region_map: dict[str, SpatialRegion] = {
            r.location_id: r for r in packing_result.regions
        }

        # 3. Mark region interiors as walkable
        for region in packing_result.regions:
            self._fill_region(grid, region, walkable)
            self._fill_region(road_grid, region, _ROAD_REGION)

        # 4. Mark entrances as walkable
        for region in packing_result.regions:
            if self._in_bounds(region.entrance_x, region.entrance_y, grid_w, grid_h):
                grid[region.entrance_y][region.entrance_x] = walkable
                road_grid[region.entrance_y][region.entrance_x] = _ROAD_ENTRANCE

        # 5. A missing semantic graph must not create an isolated spatial map.
        # The final connectivity graph is built from routes that were actually
        # rasterized, not from the intended semantic edges.
        if not build_input.paths:
            warnings.append(SpatialInputWarning(
                code="no_semantic_paths",
                message="No semantic path edges found; spatial connectivity will be repaired",
                source="route_rasterizer",
            ))

        # 6. Route each semantic path edge
        routes: list[SpatialRoute] = []
        routed_edges: set[tuple[str, str]] = set()

        edges_to_route = self._ordered_edges(build_input, region_map)

        for path_id, from_id, to_id, bidirectional, is_secret in edges_to_route:
            edge_key = self._edge_key(from_id, to_id)
            if edge_key in routed_edges:
                continue

            from_region = region_map.get(from_id)
            to_region = region_map.get(to_id)

            if from_region is None or to_region is None:
                warnings.append(SpatialInputWarning(
                    code="route_missing_region",
                    message=(
                        f"path {path_id!r}: region not found for "
                        f"{from_id!r} or {to_id!r}; skipped"
                    ),
                    source="route_rasterizer",
                    item_id=path_id,
                ))
                continue

            route = self._route_single(
                path_id, from_id, to_id,
                from_region, to_region,
                grid, road_grid, grid_w, grid_h, corridor_w, walkable,
                bidirectional, is_secret,
                config.routing.secret_path_cost_multiplier,
            )

            if route is None:
                warnings.append(SpatialInputWarning(
                    code="route_generation_failed",
                    message=(
                        f"path {path_id!r}: A* failed between "
                        f"{from_id!r} and {to_id!r}"
                    ),
                    source="route_rasterizer",
                    item_id=path_id,
                ))
                continue

            routes.append(route)
            routed_edges.add(edge_key)

        # 7. Repair the graph formed by successfully rasterized routes. Seed
        # every placed location so route-less regions remain visible as
        # singleton components. Physical connectivity is undirected even when
        # a semantic path later restricts movement direction.
        actual_adj: dict[str, set[str]] = {location_id: set() for location_id in region_map}
        for route in routes:
            actual_adj[route.from_location_id].add(route.to_location_id)
            actual_adj[route.to_location_id].add(route.from_location_id)

        synth_routes, synth_warnings = self._repair_connectivity(
            actual_adj,
            layout_plan.synthetic_edges,
            region_map,
            grid,
            grid_w,
            grid_h,
            corridor_w,
            walkable,
            road_grid,
        )
        routes.extend(synth_routes)
        warnings.extend(synth_warnings)
        final_components = bfs_components(actual_adj)

        road_tiles = self._collect_road_tiles(road_grid)

        return RouteRasterizationResult(
            routes=routes,
            road_tiles=[GridPoint(x=x, y=y) for x, y in road_tiles],
            collision_grid=grid,
            warnings=warnings,
            provenance={
                "algorithm": "weighted_orthogonal_astar_reuse_roads",
                "corridor_width": corridor_w,
                "routes_generated": len(routes),
                "road_tile_count": len(road_tiles),
                "route_tile_total": sum(len(r.route_tiles) for r in routes),
                "synthetic_routes": sum(1 for r in routes if r.route_type == "synthetic"),
                "component_count": len(final_components),
            },
        )

    # ------------------------------------------------------------------
    # Route ordering
    # ------------------------------------------------------------------

    def _ordered_edges(
        self,
        build_input: SpatialBuildInput,
        region_map: dict[str, SpatialRegion],
    ) -> list[tuple[str, str, str, bool, bool]]:
        """Route a graph backbone first, then route extra semantic edges."""
        unique: dict[tuple[str, str], PathSpatialFact] = {}
        adj: dict[str, set[str]] = {}
        degree: dict[str, int] = {}
        for path in build_input.paths:
            if path.from_location_id not in region_map or path.to_location_id not in region_map:
                continue
            key = self._edge_key(path.from_location_id, path.to_location_id)
            unique.setdefault(key, path)
            adj.setdefault(path.from_location_id, set()).add(path.to_location_id)
            if path.bidirectional:
                adj.setdefault(path.to_location_id, set()).add(path.from_location_id)
            else:
                adj.setdefault(path.to_location_id, set())
            degree[path.from_location_id] = degree.get(path.from_location_id, 0) + 1
            degree[path.to_location_id] = degree.get(path.to_location_id, 0) + 1

        importance = {loc.location_id: loc.importance for loc in build_input.locations}

        def node_score(nid: str) -> tuple[int, int, str]:
            imp = {"core": 3, "major": 2, "minor": 1}.get(importance.get(nid, ""), 0)
            return (imp, degree.get(nid, 0), nid)

        backbone_keys: list[tuple[str, str]] = []
        visited: set[str] = set()
        for start in sorted(adj, key=node_score, reverse=True):
            if start in visited:
                continue
            visited.add(start)
            queue = [start]
            while queue:
                current = queue.pop(0)
                neighbors = sorted(adj.get(current, set()), key=node_score, reverse=True)
                for neighbor in neighbors:
                    if neighbor in visited:
                        continue
                    visited.add(neighbor)
                    queue.append(neighbor)
                    key = self._edge_key(current, neighbor)
                    if key in unique:
                        backbone_keys.append(key)

        backbone_set = set(backbone_keys)
        extra_keys = sorted(
            (key for key in unique if key not in backbone_set),
            key=lambda key: (
                -max(node_score(key[0])[0], node_score(key[1])[0]),
                -max(degree.get(key[0], 0), degree.get(key[1], 0)),
                unique[key].path_id,
            ),
        )

        ordered_paths = [unique[key] for key in backbone_keys + extra_keys]
        return [
            (
                path.path_id,
                path.from_location_id,
                path.to_location_id,
                path.bidirectional,
                path.is_secret,
            )
            for path in ordered_paths
        ]

    # ------------------------------------------------------------------
    # Single route
    # ------------------------------------------------------------------

    def _route_single(
        self,
        path_edge_id: str,
        from_id: str,
        to_id: str,
        from_region: SpatialRegion,
        to_region: SpatialRegion,
        grid: list[list[int]],
        road_grid: list[list[int]],
        grid_w: int, grid_h: int,
        corridor_w: int,
        walkable: int,
        bidirectional: bool,
        is_secret: bool,
        secret_cost_mult: float,
    ) -> SpatialRoute | None:
        """Route a single path edge from entrance to entrance."""
        start = (from_region.entrance_x, from_region.entrance_y)
        goal = (to_region.entrance_x, to_region.entrance_y)

        def cost_fn(x: int, y: int) -> float:
            tile = road_grid[y][x]
            if tile == _ROAD_CENTERLINE:
                return 0.05
            if tile == _ROAD_ENTRANCE:
                return 0.2
            if tile == _ROAD_CORRIDOR:
                return 2.5
            if tile == _ROAD_REGION:
                return 30.0
            return 20.0

        tile_path = astar_weighted_orthogonal(
            grid_w, grid_h, start, goal, cost_fn, min_step_cost=0.05,
        )
        if tile_path is None:
            return None

        # Widen corridor for collision, while preserving existing display centerlines.
        self._widen_and_mark(tile_path, corridor_w, grid, grid_w, grid_h, walkable)
        self._widen_road_corridor(tile_path, corridor_w, road_grid, grid_w, grid_h)
        self._mark_centerline(tile_path, road_grid, grid_w, grid_h)
        road_grid[start[1]][start[0]] = _ROAD_ENTRANCE
        road_grid[goal[1]][goal[0]] = _ROAD_ENTRANCE

        # Determine access tags
        access_tags: list[str] = []
        if is_secret:
            access_tags.append("secret")

        cost = 1.0 * (secret_cost_mult if is_secret else 1.0)

        return SpatialRoute(
            path_edge_id=path_edge_id,
            from_location_id=from_id,
            to_location_id=to_id,
            route_tiles=[GridPoint(x=x, y=y) for x, y in tile_path],
            route_type="corridor",
            bidirectional=bidirectional,
            movement_cost=cost,
            access_tags=access_tags,
        )

    # ------------------------------------------------------------------
    # Synthetic routes for disconnected components
    # ------------------------------------------------------------------

    def _repair_connectivity(
        self,
        actual_adj: dict[str, set[str]],
        preferred_edges: list[tuple[str, str]],
        region_map: dict[str, SpatialRegion],
        grid: list[list[int]],
        grid_w: int, grid_h: int,
        corridor_w: int,
        walkable: int,
        road_grid: list[list[int]],
    ) -> tuple[list[SpatialRoute], list[SpatialInputWarning]]:
        """Connect every placed region using routes that really rasterize.

        Layout-time synthetic edges are tried first. If they are unavailable or
        no longer connect different components, the nearest pair of entrances
        across all components is attempted. A failure is left as a warning here
        and becomes a hard validation error before blueprint export.
        """
        routes: list[SpatialRoute] = []
        warnings: list[SpatialInputWarning] = []

        preferred = {
            self._edge_key(a, b)
            for a, b in preferred_edges
            if a in region_map and b in region_map and a != b
        }

        while True:
            components = bfs_components(actual_adj)
            if len(components) <= 1:
                break

            component_index = {
                location_id: index
                for index, component in enumerate(components)
                for location_id in component
            }
            candidates: list[tuple[int, int, str, str]] = []
            seen: set[tuple[str, str]] = set()
            location_ids = sorted(region_map)
            for index, from_id in enumerate(location_ids):
                for to_id in location_ids[index + 1:]:
                    if component_index[from_id] == component_index[to_id]:
                        continue
                    edge_key = self._edge_key(from_id, to_id)
                    if edge_key in seen:
                        continue
                    seen.add(edge_key)
                    from_region = region_map[from_id]
                    to_region = region_map[to_id]
                    distance = (
                        abs(from_region.entrance_x - to_region.entrance_x)
                        + abs(from_region.entrance_y - to_region.entrance_y)
                    )
                    candidates.append(
                        (0 if edge_key in preferred else 1, distance, from_id, to_id)
                    )

            connected = False
            for _priority, _distance, from_id, to_id in sorted(candidates):
                route = self._route_single(
                    f"synthetic_{from_id}_{to_id}",
                    from_id,
                    to_id,
                    region_map[from_id],
                    region_map[to_id],
                    grid,
                    road_grid,
                    grid_w,
                    grid_h,
                    corridor_w,
                    walkable,
                    bidirectional=True,
                    is_secret=False,
                    secret_cost_mult=1.0,
                )
                if route is None:
                    continue

                route = route.model_copy(update={"route_type": "synthetic"})
                routes.append(route)
                actual_adj[from_id].add(to_id)
                actual_adj[to_id].add(from_id)
                warnings.append(SpatialInputWarning(
                    code="synthetic_route_added",
                    message=(
                        "Added spatial connectivity route between components: "
                        f"{from_id!r} -> {to_id!r}"
                    ),
                    source="route_rasterizer",
                    item_id=route.path_edge_id,
                ))
                connected = True
                break

            if not connected:
                warnings.append(SpatialInputWarning(
                    code="synthetic_route_failed",
                    message=f"Could not connect spatial components: {components}",
                    source="route_rasterizer",
                ))
                break

        return routes, warnings

    # ------------------------------------------------------------------
    # Grid helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fill_region(
        grid: list[list[int]],
        region: SpatialRegion,
        walkable: int,
    ) -> None:
        for dy in range(region.height):
            for dx in range(region.width):
                gx = region.x + dx
                gy = region.y + dy
                if 0 <= gy < len(grid) and 0 <= gx < len(grid[0]):
                    grid[gy][gx] = walkable

    @staticmethod
    def _widen_and_mark(
        path: list[tuple[int, int]],
        corridor_w: int,
        grid: list[list[int]],
        grid_w: int, grid_h: int,
        walkable: int,
    ) -> None:
        """Mark path tiles and surrounding corridor as walkable."""
        half = corridor_w // 2
        for px, py in path:
            for dx in range(-half, half + 1):
                for dy in range(-half, half + 1):
                    nx, ny = px + dx, py + dy
                    if 0 <= ny < grid_h and 0 <= nx < grid_w:
                        grid[ny][nx] = walkable

    @staticmethod
    def _widen_road_corridor(
        path: list[tuple[int, int]],
        corridor_w: int,
        road_grid: list[list[int]],
        grid_w: int,
        grid_h: int,
    ) -> None:
        """Mark corridor area without erasing existing centerlines or entrances."""
        half = corridor_w // 2
        preserved = {_ROAD_CENTERLINE, _ROAD_ENTRANCE}
        for px, py in path:
            for dx in range(-half, half + 1):
                for dy in range(-half, half + 1):
                    nx, ny = px + dx, py + dy
                    if 0 <= ny < grid_h and 0 <= nx < grid_w:
                        if road_grid[ny][nx] not in preserved:
                            road_grid[ny][nx] = _ROAD_CORRIDOR

    @staticmethod
    def _in_bounds(x: int, y: int, w: int, h: int) -> bool:
        return 0 <= x < w and 0 <= y < h

    @staticmethod
    def _edge_key(a: str, b: str) -> tuple[str, str]:
        return tuple(sorted([a, b]))

    @staticmethod
    def _collect_road_tiles(road_grid: list[list[int]]) -> list[tuple[int, int]]:
        tiles: list[tuple[int, int]] = []
        for y, row in enumerate(road_grid):
            for x, value in enumerate(row):
                if value == _ROAD_CENTERLINE:
                    tiles.append((x, y))
        return tiles

    @staticmethod
    def _mark_centerline(
        path: list[tuple[int, int]],
        road_grid: list[list[int]],
        grid_w: int,
        grid_h: int,
    ) -> None:
        for x, y in path:
            if 0 <= y < grid_h and 0 <= x < grid_w:
                road_grid[y][x] = _ROAD_CENTERLINE
