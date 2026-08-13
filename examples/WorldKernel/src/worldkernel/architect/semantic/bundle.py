from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from worldkernel.architect.init.models import InitBuildContext
from worldkernel.architect.semantic.models import FoundationBundle
from worldkernel.architect.semantic.state import SemanticGenerationState


class FoundationBundleBuildError(RuntimeError):
    pass


def _flatten_items(state: SemanticGenerationState, artifact_type: str) -> list[Any]:
    items: list[Any] = []
    for result in state.result_store.list_by_artifact_type(artifact_type):
        items.extend(result.items)
    return items


def _normalize_importance(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"core", "major", "minor"} else "major"


def _location_importance_by_entity_id(
    init_context: InitBuildContext,
    generation_state: SemanticGenerationState,
) -> dict[str, str]:
    seed_mapping: dict[str, str] = {}
    for result in generation_state.result_store.list_by_artifact_type("location_profile"):
        raw_mapping = result.provenance.get("seed_to_entity_mapping")
        if isinstance(raw_mapping, dict):
            seed_mapping.update({str(key): str(value) for key, value in raw_mapping.items()})

    importance_by_id: dict[str, str] = {}
    for resolved_seed in init_context.resolved_location_seeds:
        entity_id = (
            seed_mapping.get(f"loc:{resolved_seed.seed_id}")
            or seed_mapping.get(resolved_seed.seed_id)
        )
        if entity_id:
            importance_by_id[entity_id] = _normalize_importance(resolved_seed.importance)
    return importance_by_id


def _enrich_location_importance(
    locations: list[Any],
    importance_by_id: dict[str, str],
) -> list[Any]:
    """Persist seed importance even for older generated schemas without the field."""
    enriched: list[Any] = []
    for item in locations:
        if isinstance(item, BaseModel):
            identity_model = getattr(item, "identity", None)
            entity_id = str(getattr(identity_model, "id", "") or "")
            importance = importance_by_id.get(entity_id)
            if importance and identity_model is not None and hasattr(identity_model, "importance"):
                identity_model.importance = importance
                enriched.append(item)
                continue
            payload = item.model_dump(mode="python")
        elif isinstance(item, dict):
            payload = deepcopy(item)
        else:
            enriched.append(item)
            continue

        identity = payload.get("identity")
        if isinstance(identity, dict):
            entity_id = str(identity.get("id") or "")
            importance = importance_by_id.get(entity_id)
            if importance:
                identity["importance"] = importance
        enriched.append(payload)
    return enriched


class FoundationBundleBuilder:
    def build(
        self,
        init_context: InitBuildContext,
        generation_state: SemanticGenerationState,
    ) -> FoundationBundle:
        locations = _enrich_location_importance(
            _flatten_items(generation_state, "location_profile"),
            _location_importance_by_entity_id(init_context, generation_state),
        )
        characters = _flatten_items(generation_state, "character_profile")
        path_graph = _flatten_items(generation_state, "path_edge")
        relation_graph = _flatten_items(generation_state, "relation_edge")

        if not locations:
            raise FoundationBundleBuildError("missing location_profile artifacts for foundation bundle")
        if not characters:
            raise FoundationBundleBuildError("missing character_profile artifacts for foundation bundle")

        return FoundationBundle(
            world_id=init_context.world_background.world_id,
            locations=locations,
            characters=characters,
            path_graph=path_graph,
            relation_graph=relation_graph,
            constraints=init_context.world_background.world_constraints,
            provenance={
                "source_id": init_context.world_background.source_id,
                "execution_order": list(generation_state.execution_order),
                "completed_steps": list(generation_state.completed_steps),
            },
        )


def build_foundation_bundle(
    init_context: InitBuildContext,
    generation_state: SemanticGenerationState,
) -> FoundationBundle:
    return FoundationBundleBuilder().build(init_context, generation_state)
