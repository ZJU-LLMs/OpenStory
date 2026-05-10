from __future__ import annotations

from pathlib import Path

import yaml

from worldkernel.models.stage1_types import TemplateMatch, WorldTypeResult

_WORLD_TYPES_DIR = Path(__file__).parent.parent.parent.parent / "configs" / "world_types"

_TYPE_FILE_MAP: dict[str, str] = {
    "school_simulation": "campus.yaml",
    "fictional_institution_world": "campus.yaml",
    "fantasy_world": "campus.yaml",
    "campus_life_world": "campus.yaml",
    "hospital_world": "hospital.yaml",
    "city_world": "town.yaml",
    "historical_society_world": "town.yaml",
    "survival_world": "closed_space.yaml",
    "market_world": "market.yaml",
}


def retrieve_templates(world_type: WorldTypeResult) -> list[TemplateMatch]:
    matches: list[TemplateMatch] = []
    seen: set[str] = set()

    for wtype in filter(None, [world_type.primary, world_type.secondary]):
        fname = _TYPE_FILE_MAP.get(wtype)
        if not fname or fname in seen:
            continue
        seen.add(fname)

        path = _WORLD_TYPES_DIR / fname
        if not path.exists():
            continue

        data: dict = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for ttype, tdata in data.items():
            matches.append(
                TemplateMatch(type=ttype, name=fname, source=str(path), data=tdata or {})
            )

    return matches
