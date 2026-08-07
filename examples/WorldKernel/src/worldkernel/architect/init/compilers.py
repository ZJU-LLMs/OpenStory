from __future__ import annotations

import logging
from typing import Any

from worldkernel.architect.init.models import (
    ExecutionDAG,
    ExecutionDAGNode,
    ResolvedSeed,
    SeedCatalogEntry,
    Stage1ArtifactBundle,
    WorldBackgroundArtifact,
)
from worldkernel.architect.registry.core import ToolRegistry

logger = logging.getLogger(__name__)


class InitCompileError(Exception):
    pass


class ContractCompiler:
    def compile(self, bundle: Stage1ArtifactBundle) -> WorldBackgroundArtifact:
        world_background = bundle.world_background
        if not isinstance(world_background.world_constraints, list):
            raise InitCompileError("world_background.world_constraints must be a list")
        if not isinstance(world_background.simulation_start, dict):
            raise InitCompileError("world_background.simulation_start must be an object")
        return world_background.model_copy(
            update={
                "world_id": bundle.world_id,
                "source_id": bundle.source_id,
                "provenance": {
                    "source": "stage1.world_background",
                    **world_background.provenance,
                },
            }
        )


class ExecutionDAGCompiler:
    REQUIRED_TARGETS_BY_TARGET = {
        "path": ("location",),
        "relation": ("character",),
    }

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tool_registry = tool_registry

    def compile(self, bundle: Stage1ArtifactBundle) -> ExecutionDAG:
        normalized_steps: list[tuple[int, Any]] = []
        seen_step_ids: set[str] = set()
        for index, step in enumerate(bundle.execution_plan.steps):
            step_id = step.step_id.strip()
            if not step_id:
                raise InitCompileError(f"execution_plan.steps[{index}] missing step_id")
            if step_id in seen_step_ids:
                raise InitCompileError(f"duplicate execution step_id: {step_id}")
            seen_step_ids.add(step_id)
            priority = self._positive_int(step.priority, f"step {step_id} priority")
            batch_size = self._positive_int(step.batch_size, f"step {step_id} batch_size")
            generator_type = step.generator_type.strip()
            if not generator_type:
                raise InitCompileError(f"step {step_id} missing generator_type")
            target_entity_type = step.target_entity_type.strip()
            if not target_entity_type:
                raise InitCompileError(f"step {step_id} missing target_entity_type")
            batch_size = min(batch_size, self._max_batch_size(target_entity_type))
            self._tool_registry.get_by_generator_type(generator_type)
            normalized_steps.append(
                (
                    index,
                    step.model_copy(
                        update={
                            "step_id": step_id,
                            "priority": priority,
                            "batch_size": batch_size,
                            "generator_type": generator_type,
                            "target_entity_type": target_entity_type,
                        }
                    ),
                )
            )

        sorted_steps = sorted(normalized_steps, key=lambda item: (item[1].priority, item[0]))
        target_to_step_id: dict[str, str] = {}
        nodes: list[ExecutionDAGNode] = []
        for sorted_index, (original_index, step) in enumerate(sorted_steps):
            depends_on: list[str] = []
            for required_target in self.REQUIRED_TARGETS_BY_TARGET.get(step.target_entity_type, ()):
                dependency_step_id = target_to_step_id.get(required_target)
                if dependency_step_id is None:
                    raise InitCompileError(
                        f"step {step.step_id} requires prior target '{required_target}'"
                    )
                depends_on.append(dependency_step_id)

            tool = self._tool_registry.get_by_generator_type(step.generator_type)
            nodes.append(
                ExecutionDAGNode(
                    **step.model_dump(),
                    depends_on=depends_on,
                    tool_id=tool.tool_id,
                    output_schema_alias=tool.output_schema_alias,
                    provenance={
                        "source": "stage1.execution_plan",
                        "original_index": original_index,
                        "execution_index": sorted_index,
                    },
                )
            )
            target_to_step_id.setdefault(step.target_entity_type, step.step_id)

        return ExecutionDAG(
            nodes=nodes,
            execution_order=[node.step_id for node in nodes],
            provenance={"source": "stage1.execution_plan"},
        )

    @staticmethod
    def _positive_int(value: Any, label: str) -> int:
        if isinstance(value, bool):
            raise InitCompileError(f"{label} must be a positive integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise InitCompileError(f"{label} must be a positive integer") from exc
        if parsed <= 0:
            raise InitCompileError(f"{label} must be a positive integer")
        return parsed

    @staticmethod
    def _max_batch_size(target_entity_type: str) -> int:
        """Per-entity-type batch size caps to prevent LLM output truncation."""
        caps = {
            "character": 4,
            "location": 4,
        }
        return caps.get(target_entity_type, 10)


class SeedResolver:
    SUPPORTED_ENTITY_TYPES = ("location", "character")

    def resolve(
        self,
        bundle: Stage1ArtifactBundle,
        constraints: Any | None = None,
    ) -> tuple[list[ResolvedSeed], list[ResolvedSeed]]:
        resolved_by_type: dict[str, list[ResolvedSeed]] = {}
        seed_buckets = bundle.seed_catalog.instance_seeds
        for entity_type in self.SUPPORTED_ENTITY_TYPES:
            seeds = getattr(seed_buckets, entity_type)
            resolved_by_type[entity_type] = self._resolve_entity_seeds(bundle, entity_type, seeds)

        resolved_locations = resolved_by_type["location"]
        resolved_characters = resolved_by_type["character"]

        if constraints is not None:
            from worldkernel.constraints import truncate_seeds
            resolved_locations, loc_warns = truncate_seeds(
                resolved_locations, constraints.max_locations, "location",
            )
            resolved_characters, char_warns = truncate_seeds(
                resolved_characters, constraints.max_characters, "character",
            )
            for w in loc_warns + char_warns:
                logger.warning(w)

        # Cross-type seed_id uniqueness check
        loc_ids = {s.seed_id for s in resolved_locations}
        char_ids = {s.seed_id for s in resolved_characters}
        overlap = loc_ids & char_ids
        if overlap:
            raise InitCompileError(f"seed_id collision across entity types: {overlap}")

        return resolved_locations, resolved_characters

    def _resolve_entity_seeds(
        self,
        bundle: Stage1ArtifactBundle,
        entity_type: str,
        seeds: list[SeedCatalogEntry],
    ) -> list[ResolvedSeed]:
        resolved: list[ResolvedSeed] = []
        seen_ids: set[str] = set()
        for index, seed in enumerate(seeds):
            if not seed.seed_id.strip():
                raise InitCompileError(f"{entity_type} seed at index {index} missing seed_id")
            if not seed.archetype_id.strip():
                raise InitCompileError(f"{entity_type} seed {seed.seed_id} missing archetype_id")
            if seed.seed_id in seen_ids:
                raise InitCompileError(f"duplicate seed_id within {entity_type}: {seed.seed_id}")
            seen_ids.add(seed.seed_id)
            priority = ExecutionDAGCompiler._positive_int(
                seed.generation_priority,
                f"{entity_type} seed {seed.seed_id} generation_priority",
            )
            normalized_seed = seed.model_copy(update={"generation_priority": priority})
            resolved.append(
                ResolvedSeed(
                    seed=normalized_seed,
                    entity_type=entity_type,
                    provenance={
                        "source": "stage1.instance_seed_catalog",
                        "seed_index": index,
                    },
                )
            )
        return resolved
