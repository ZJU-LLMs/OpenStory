from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from worldkernel import server


class CharacterVisualDevRouteTests(unittest.TestCase):
    def test_character_only_route_reuses_spatial_and_returns_frontend_urls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_root = Path(temp_dir)
            session_id = "world dev"
            spatial_root = (
                templates_root
                / session_id
                / "generated"
                / "artifacts"
                / "spatial"
            )
            spatial_root.mkdir(parents=True)
            (spatial_root / "spatial_blueprint.json").write_text(
                "{}", encoding="utf-8"
            )

            result = SimpleNamespace(
                world_id="world-dev",
                template_root=str(templates_root / session_id),
                semantic_root=str(templates_root / session_id / "semantic"),
                spatial_output_root=str(spatial_root),
                spatial_source="existing_spatial_blueprint",
                spatial_counts={
                    "character_count": 7,
                    "eligible_character_count": 7,
                    "planned_character_batches": 2,
                    "generated_character_batches": 1,
                    "reused_character_batches": 1,
                    "estimated_character_image_calls": 1,
                },
                blueprint=SimpleNamespace(
                    visual={"character_layer": {"status": "ready"}}
                ),
            )

            with (
                patch.object(server, "TEMPLATES_DIR", templates_root),
                patch(
                    "worldkernel.architect.visual.regenerate."
                    "regenerate_visual_from_template",
                    return_value=result,
                ) as regenerate,
            ):
                response = asyncio.run(
                    server.dev_generate_character_visuals(
                        session_id,
                        server.CharacterVisualDevGenerateRequest(
                            force_character_batch_ids=["batch-0001"]
                        ),
                    )
                )

            kwargs = regenerate.call_args.kwargs
            self.assertFalse(kwargs["generate_background"])
            self.assertFalse(kwargs["generate_location_layer"])
            self.assertTrue(kwargs["generate_characters"])
            self.assertTrue(kwargs["reuse_existing_spatial"])
            self.assertEqual(kwargs["force_character_batch_ids"], ["batch-0001"])
            self.assertEqual(response["counts"]["estimated_image_calls"], 1)
            self.assertEqual(
                response["frontend_url"],
                "/simulation.html?session_id=world%20dev",
            )
            self.assertTrue(response["character_output_root"].endswith("characters"))

    def test_character_only_route_requires_existing_spatial_blueprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_root = Path(temp_dir)
            (templates_root / "semantic-only").mkdir()

            with patch.object(server, "TEMPLATES_DIR", templates_root):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(
                        server.dev_generate_character_visuals("semantic-only")
                    )

            self.assertEqual(raised.exception.status_code, 409)
            self.assertIn("generate the map first", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
