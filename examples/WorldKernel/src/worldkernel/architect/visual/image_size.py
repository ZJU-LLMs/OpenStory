from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from PIL import Image


def normalize_generated_image_size(
    image_path: str | Path,
    target_size: tuple[int, int],
    *,
    original_output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Normalize a model result before any mask, validation, or composition step."""

    path = Path(image_path)
    preserved_path = Path(original_output_path) if original_output_path is not None else None
    with Image.open(path) as source:
        original_size = source.size
        if original_size == target_size:
            if preserved_path is not None:
                preserved_path.unlink(missing_ok=True)
            return {
                "original_size": {"width": original_size[0], "height": original_size[1]},
                "target_size": {"width": target_size[0], "height": target_size[1]},
                "normalized": False,
                "resampling": "none",
                "original_output_path": "",
            }
        normalized = source.convert("RGBA").resize(target_size, Image.Resampling.NEAREST)

    if preserved_path is not None:
        preserved_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, preserved_path)
    normalized.save(path, format="PNG")
    return {
        "original_size": {"width": original_size[0], "height": original_size[1]},
        "target_size": {"width": target_size[0], "height": target_size[1]},
        "normalized": True,
        "resampling": "nearest_neighbor",
        "original_output_path": str(preserved_path) if preserved_path is not None else "",
    }
