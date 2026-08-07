# Visual Layer Validation

The validation script reuses an existing template's semantic artifacts and
`spatial_blueprint.json`. Every run regenerates the complete visual layer
without rerunning Stage1 or changing the Stage2 layout.

## Regenerate the complete visual layer

```powershell
C:\Users\ASUS\.conda\envs\openstory\python.exe examples/WorldKernel/validate_visual.py `
  766462e7-ca0e-41de-ab26-782690a0125e
```

Every run regenerates:

1. `background.png`
2. `location_layer.png`
3. `road_atlas.png` and `road_layer.png`
4. A debug-only visual validation preview

The saved Stage2 spatial blueprint is always reused. The accepted location layer
cache is always bypassed so prompt and generation-code changes are exercised.
The CLI intentionally has no partial-generation or preview-only switch.

The image model's untouched background output is saved as `background_raw.png`.
The hard-mask-restored intermediate is saved separately as
`background_mask_restored.png`, and the published asset remains `background.png`.

## Debug outputs

Debug files are written outside the formal spatial asset directory:

```text
generated/debug/visual_validation/visual_validation_preview.png
generated/debug/visual_validation/visual_validation_report.json
generated/debug/visual_validation/visual_validation_run.json
generated/debug/visual_validation/intermediates/location_attempts/
```

The preview is not referenced by `visual_layout_manifest.json` and is never
loaded by the frontend. It is a copy of the composed map with these overlays:

- Red rectangle and number: Stage2 location bounds
- Orange point: Stage2 entrance
- Cyan area and line: Stage2 road tiles and route centerline

The JSON report also verifies that manifest slot IDs and pixel bounds match the
saved Stage2 regions and that all generated layers use the original canvas size.
The run summary indexes every background, location, evaluator, road, and preview
artifact. Location candidate images, masks, evaluator overviews, and evaluator
detail sheets are retained for every attempt.
