from __future__ import annotations

from worldkernel.architect.spatial.models import SpatialBlueprint
from worldkernel.architect.visual.models import VisualDecoration


DECORATION_KINDS = (
    "grass_clump",
    "small_flower",
    "pebble",
    "ground_speckle",
    "low_bush",
    "stump",
    "fallen_leaf",
)


def build_decorable_mask(blueprint: SpatialBlueprint, *, slot_padding_tiles: int = 2, route_padding_tiles: int = 2) -> list[list[bool]]:
    width = max(1, blueprint.grid.width)
    height = max(1, blueprint.grid.height)
    mask = [[True for _ in range(width)] for _ in range(height)]

    for region in blueprint.regions:
        bounds = region.bounds or {}
        _clear_rect(
            mask,
            int(bounds.get("x", 0)) - slot_padding_tiles,
            int(bounds.get("y", 0)) - slot_padding_tiles,
            int(bounds.get("w", 0)) + slot_padding_tiles * 2,
            int(bounds.get("h", 0)) + slot_padding_tiles * 2,
        )
        entrance = region.entrance or {}
        _clear_rect(
            mask,
            int(entrance.get("x", 0)) - route_padding_tiles,
            int(entrance.get("y", 0)) - route_padding_tiles,
            route_padding_tiles * 2 + 1,
            route_padding_tiles * 2 + 1,
        )

    for tile in blueprint.road_tiles:
        _clear_rect(
            mask,
            int(tile.x) - route_padding_tiles,
            int(tile.y) - route_padding_tiles,
            route_padding_tiles * 2 + 1,
            route_padding_tiles * 2 + 1,
        )

    return mask


def generate_safe_decorations(blueprint: SpatialBlueprint, *, max_density: float = 0.025) -> list[VisualDecoration]:
    mask = build_decorable_mask(blueprint)
    tile = max(1, blueprint.grid.tile_size)
    candidates: list[tuple[int, int, int]] = []
    for y, row in enumerate(mask):
        for x, allowed in enumerate(row):
            if not allowed:
                continue
            seed = _stable_seed(blueprint.world_id, x, y)
            if seed % 17 == 0:
                candidates.append((seed, x, y))

    max_count = max(0, int(blueprint.grid.width * blueprint.grid.height * max_density))
    selected = sorted(candidates, key=lambda item: item[0])[:max_count]
    decorations: list[VisualDecoration] = []
    for index, (seed, x, y) in enumerate(selected):
        kind = DECORATION_KINDS[seed % len(DECORATION_KINDS)]
        size_tiles = 1 + (1 if kind in {"low_bush", "stump"} and seed % 5 == 0 else 0)
        decorations.append(
            VisualDecoration(
                decoration_id=f"decor-{index:04d}",
                kind=kind,
                x_px=x * tile,
                y_px=y * tile,
                w_px=size_tiles * tile,
                h_px=size_tiles * tile,
                z_index=20,
                variant=(seed // 17) % 6,
            )
        )
    return decorations


def _clear_rect(mask: list[list[bool]], x: int, y: int, w: int, h: int) -> None:
    if not mask or not mask[0]:
        return
    max_y = len(mask)
    max_x = len(mask[0])
    for yy in range(max(0, y), min(max_y, y + max(0, h))):
        for xx in range(max(0, x), min(max_x, x + max(0, w))):
            mask[yy][xx] = False


def _stable_seed(world_id: str, x: int, y: int) -> int:
    value = 2166136261
    for ch in world_id:
        value = (value ^ ord(ch)) * 16777619 & 0xFFFFFFFF
    value ^= x * 374761393
    value ^= y * 668265263
    return value & 0xFFFFFFFF
