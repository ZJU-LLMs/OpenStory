from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EXAMPLE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = EXAMPLE_ROOT.parent.parent
SRC_ROOT = EXAMPLE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from worldkernel.architect.visual.regenerate import regenerate_visual_from_template
from worldkernel.architect.visual.validation_preview import (
    render_visual_validation_preview,
)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    template_root = _resolve_template(args.template)
    debug_root = template_root / "generated" / "debug" / "visual_validation"
    preview_path = Path(args.preview) if args.preview else debug_root / "visual_validation_preview.png"
    report_path = Path(args.report) if args.report else debug_root / "visual_validation_report.json"

    requested_layers = {"background", "locations", "roads"}
    result = regenerate_visual_from_template(
        template_root=template_root,
        config_path=Path(args.architect_config),
        image_model_config_path=Path(args.image_model_config),
        generate_background=True,
        generate_location_layer=True,
        reuse_existing_spatial=True,
        force_visual_regeneration=True,
        visual_debug_root=debug_root / "intermediates",
    )
    blueprint = result.blueprint
    spatial_root = Path(result.spatial_output_root)
    preview_report = render_visual_validation_preview(
        blueprint=blueprint,
        spatial_root=spatial_root,
        output_path=preview_path,
        report_path=report_path,
        required_layers=requested_layers,
    )

    summary = {
        "world_id": blueprint.world_id,
        "template_root": str(template_root),
        "spatial_source": result.spatial_source,
        "generated": {
            "background": True,
            "locations": True,
            "roads": "integrated_into_location_layer",
            "force": True,
        },
        "spatial_counts": result.spatial_counts,
        "preview_path": preview_report["preview_path"],
        "report_path": preview_report["report_path"],
        "validation_passed": preview_report["passed"],
        "issues": preview_report["issues"],
        "artifacts": {
            "background_raw": str(spatial_root / "background_raw.png"),
            "background_mask_restored": str(spatial_root / "background_mask_restored.png"),
            "background": str(spatial_root / "background.png"),
            "background_prompt": str(spatial_root / "background_prompt.json"),
            "background_metadata": str(spatial_root / "background_metadata.json"),
            "location_layer": str(spatial_root / "location_layer.png"),
            "location_metadata": str(spatial_root / "location_layer_metadata.json"),
            "location_evaluation": str(spatial_root / "location_alignment_report.json"),
            "location_prompts": str(spatial_root / "location_batch_prompts"),
            "location_attempts": str(debug_root / "intermediates" / "location_attempts"),
            "roads": str(spatial_root / "location_layer.png"),
            "validation_preview": preview_report["preview_path"],
            "validation_report": preview_report["report_path"],
        },
    }
    run_summary_path = debug_root / "visual_validation_run.json"
    summary["run_summary_path"] = str(run_summary_path)
    run_summary_path.parent.mkdir(parents=True, exist_ok=True)
    run_summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if preview_report["passed"] else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate WorldKernel visual assets from an existing template and "
            "write a debug-only preview with Stage2 coordinate overlays."
        )
    )
    parser.add_argument(
        "template",
        help="Template UUID or template directory path",
    )
    parser.add_argument(
        "--architect-config",
        default=str(EXAMPLE_ROOT / "configs" / "architect.yaml"),
    )
    parser.add_argument(
        "--image-model-config",
        default=str(EXAMPLE_ROOT / "configs" / "image_models.yaml"),
    )
    parser.add_argument(
        "--preview",
        default="",
        help="Optional output path for the overlay preview PNG",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Optional output path for the validation report JSON",
    )
    return parser


def _resolve_template(value: str) -> Path:
    direct = Path(value).expanduser()
    if direct.exists():
        return direct.resolve()
    repository_relative = (REPOSITORY_ROOT / direct).resolve()
    if repository_relative.exists():
        return repository_relative
    by_id = (EXAMPLE_ROOT / "templates" / value).resolve()
    if by_id.exists():
        return by_id
    raise FileNotFoundError(f"Template not found: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
