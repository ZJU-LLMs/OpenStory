from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import sys
import uuid

from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from worldkernel.architect.init.models import (  # noqa: E402
    ExecutionDAG,
    InitBuildContext,
    ResolvedSeed,
    SeedCatalogEntry,
    WorldBackgroundArtifact,
)
from worldkernel.architect.semantic.bundle import FoundationBundleBuilder  # noqa: E402
from worldkernel.architect.semantic.state import SemanticGenerationState  # noqa: E402
from worldkernel.architect.spatial.pipeline_adapter import SpatialPipelineAdapter  # noqa: E402
from worldkernel.architect.tools.base import Stage2ToolResult  # noqa: E402
from worldkernel.architect.tools.generators.location_generator import (  # noqa: E402
    _restore_seed_importance,
)
from worldkernel.stage1.ontology_selector import _FIXED_DIMENSIONS  # noqa: E402
from worldkernel.stage1.pipeline import (  # noqa: E402
    _generate_pydantic_models,
    _save_entity_configs,
)
from worldkernel.stage1.types import EntityTemplate, TemplateDimension  # noqa: E402


class _IdentityWithImportance(BaseModel):
    id: str = ""
    name: str = ""
    importance: str = ""


class _LocationWithImportance(BaseModel):
    identity: _IdentityWithImportance


class _LegacyIdentity(BaseModel):
    id: str = ""
    name: str = ""


class _LegacyLocation(BaseModel):
    identity: _LegacyIdentity


def _seed(seed_id: str, importance: str) -> ResolvedSeed:
    return ResolvedSeed(
        entity_type="location",
        seed=SeedCatalogEntry(
            seed_id=seed_id,
            archetype_id="test_location",
            name=seed_id,
            importance=importance,
        ),
    )


def test_location_generator_restores_importance_from_seed_metadata() -> None:
    seeds = [_seed("central", "core"), _seed("side", "minor")]
    ids = {
        "central": "e:test:loc:001",
        "side": "e:test:loc:002",
    }
    items = [
        _LocationWithImportance(
            identity=_IdentityWithImportance(
                id="e:test:loc:001", name="central", importance="minor",
            )
        ),
        _LocationWithImportance(
            identity=_IdentityWithImportance(
                id="e:test:loc:002", name="side", importance="core",
            )
        ),
    ]

    _restore_seed_importance(items, seeds, ids)

    assert [item.identity.importance for item in items] == ["core", "minor"]


def test_generated_location_model_contains_importance() -> None:
    tmp_path = ROOT / "tests" / f".location-importance-{uuid.uuid4().hex}"
    templates = {
        "location": EntityTemplate(
            dimensions={
                name: TemplateDimension(fields=list(fields))
                for name, fields in _FIXED_DIMENSIONS["location"].items()
            }
        )
    }
    configs_dir = tmp_path / "configs"
    models_dir = tmp_path / "models"

    try:
        _save_entity_configs(configs_dir, templates)
        _generate_pydantic_models(models_dir, configs_dir)

        generated = (models_dir / "location_model.py").read_text(encoding="utf-8")
        assert "importance: str = \"\"" in generated
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_foundation_bundle_injects_importance_for_legacy_location_schema() -> None:
    context = InitBuildContext(
        world_background=WorldBackgroundArtifact(world_id="legacy-world"),
        execution_dag=ExecutionDAG(),
        resolved_location_seeds=[_seed("central", "core")],
    )
    state = SemanticGenerationState()
    result = Stage2ToolResult(
        artifact_type="location_profile",
        items=[
            _LegacyLocation(
                identity=_LegacyIdentity(
                    id="e:legacy:loc:001", name="central",
                )
            )
        ],
        provenance={
            "seed_to_entity_mapping": {
                "loc:central": "e:legacy:loc:001",
            }
        },
    )
    asyncio.run(state.result_store.add_result("generate_locations", result))
    asyncio.run(state.result_store.add_result(
        "generate_characters",
        Stage2ToolResult(artifact_type="character_profile", items=[{"id": "character-1"}]),
    ))

    bundle = FoundationBundleBuilder().build(context, state)

    assert bundle.locations[0]["identity"]["importance"] == "core"
    spatial_input = SpatialPipelineAdapter.from_foundation_bundle(bundle)
    assert spatial_input.locations[0].importance == "core"
