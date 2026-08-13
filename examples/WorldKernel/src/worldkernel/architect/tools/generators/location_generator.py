"""LocationGenerationTool — generates location profiles via LLM with quality review."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from worldkernel.architect.tools.base import (
    BaseStage2Tool,
    Stage2ToolContext,
    Stage2ToolRequest,
    Stage2ToolResult,
)
from worldkernel.architect.tools.generators.base_generator import (
    assign_entity_ids,
    batch_seeds,
    build_character_summary,
    build_generation_prompt,
    build_seed_list,
    build_world_context,
    introspect_schema,
    parse_and_validate,
)
from worldkernel.architect.tools.identity_allocator import IdentityRegistry
from worldkernel.llm.client import chat_json

logger = logging.getLogger(__name__)

_LOCATION_IMPORTANCE_LEVELS = {"core", "major", "minor"}


def _restore_seed_importance(
    items: list[Any],
    seeds: list[Any],
    pre_allocated_ids: dict[str, str],
) -> None:
    """Restore spatial importance from deterministic Stage1 seed metadata."""
    importance_by_id = {
        pre_allocated_ids[seed.seed_id]: (
            str(seed.importance).strip().lower()
            if str(seed.importance).strip().lower() in _LOCATION_IMPORTANCE_LEVELS
            else "major"
        )
        for seed in seeds
        if seed.seed_id in pre_allocated_ids
    }
    for item in items:
        identity = getattr(item, "identity", None)
        entity_id = getattr(identity, "id", "") if identity is not None else ""
        importance = importance_by_id.get(entity_id)
        if importance is not None and identity is not None and hasattr(identity, "importance"):
            identity.importance = importance


def _safe_json_loads(text: str) -> Any:
    """Parse JSON with multiple fallback strategies for LLM output."""
    # Strategy 1: strict=False
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        pass
    # Strategy 2: remove trailing commas before } or ]
    import re
    cleaned = re.sub(r',\s*([}\]])', r'\1', text)
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        pass
    # Strategy 3: try to find the outermost array/object and parse just that
    for open_ch, close_ch in [('[', ']'), ('{', '}')]:
        start = text.find(open_ch)
        if start == -1:
            continue
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1], strict=False)
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"Failed to parse JSON: {text[:200]}...")


# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


_GENERATION_SYSTEM = (
    "你是一个世界地点生成器。"
    "根据世界背景和地点种子信息，为每个种子生成完整的地点档案。"
    "每个地点必须严格遵循给定的 schema 结构，包含所有维度。"
    "identity.id 必须使用种子列表中提供的预分配 id，不可自行编造。"
    "描述必须具体、有画面感，不能泛泛而谈。"
    "必须体现种子的 archetype 特征和 importance 级别差异。"
    "世界特有字段必须与世界观一致。"
    "core 级种子需要丰富详细的描述，minor 级可以相对简洁。"
    "只输出合法 JSON，不输出任何解释、标注或额外文字。"
)

_GENERATION_USER_TEMPLATE = _load_prompt("location_generation_user.md")

_REVIEW_SYSTEM = (
    "你是一个世界构建质量评审专家。"
    "你的任务是对生成的地点数据进行深度质量反思，从多个维度评估并打分。"
    "如发现问题，必须在 corrected_locations 中提供修正后的完整数据。"
    "如无问题，corrected_locations 与输入保持一致。"
    "只输出合法 JSON，不输出任何解释、标注或额外文字。"
)

_REVIEW_USER_TEMPLATE = _load_prompt("location_review_user.md")

_RETRY_SYSTEM = (
    "你是一个世界地点生成器。"
    "之前生成的地点数据质量不达标，请根据审核反馈重新生成。"
    "identity.id 必须使用种子列表中提供的预分配 id，不可自行编造。"
    "只输出合法 JSON，不输出任何解释、标注或额外文字。"
)

_RETRY_USER_TEMPLATE = _load_prompt("location_retry_user.md")


# ---------------------------------------------------------------------------
# Quality threshold
# ---------------------------------------------------------------------------

_QUALITY_THRESHOLD = 3.0


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------

class LocationGenerationTool(BaseStage2Tool):
    tool_id = "stage2.location_generator.v1"
    generator_type = "location_generator"
    output_schema_alias = "location_profile"
    capabilities = ("generate_locations",)

    async def run(
        self,
        request: Stage2ToolRequest,
        context: Stage2ToolContext,
    ) -> Stage2ToolResult:
        # 0. Get registry
        registry = context.identity_registry
        if registry is None:
            raise RuntimeError("IdentityRegistry not provided in context")

        # 1. Resolve schema model
        entry = context.schema_registry.get(
            self.output_schema_alias, source_id=context.source_id,
        )
        ModelClass: type[BaseModel] = entry.model_type

        # 2. Introspect schema (with template metadata for required/optional distinction)
        schema_desc = introspect_schema(ModelClass, schema_entry=entry)

        # 3. Prepare world context
        world_ctx = build_world_context(request)
        char_summary = build_character_summary(request.resolved_character_seeds)

        # 4. Batch seeds
        batches = batch_seeds(request.resolved_location_seeds, request.batch_size)
        total_batches = len(batches)

        all_items: list[Any] = []
        all_refs: list[str] = []
        all_warnings: list[str] = []
        all_review_scores: list[float] = []
        retry_count = 0
        failed_batches = 0

        # 5. Process each batch
        for batch_index, batch in enumerate(batches, 1):
            try:
                items, refs, warnings, review_score, retried = await self._process_batch(
                    batch=batch,
                    batch_index=batch_index,
                    total_batches=total_batches,
                    world_ctx=world_ctx,
                    schema_desc=schema_desc,
                    char_summary=char_summary,
                    ModelClass=ModelClass,
                    registry=registry,
                )
                all_items.extend(items)
                all_refs.extend(refs)
                all_warnings.extend(warnings)
                if review_score is not None:
                    all_review_scores.append(review_score)
                if retried:
                    retry_count += 1

            except Exception as exc:
                failed_batches += 1
                all_warnings.append(f"batch {batch_index}/{total_batches} failed: {exc}")

        # 6. Fail if nothing generated
        if not all_items:
            raise RuntimeError(
                f"LocationGenerationTool: all {total_batches} batches failed, "
                "no locations generated"
            )

        # 6.5. Overall completeness check + consolidated retry
        total_seeds = len(request.resolved_location_seeds)
        if len(all_items) < total_seeds:
            # Collect missing seeds
            generated_ids: set[str] = set()
            for item in all_items:
                identity = getattr(item, "identity", None)
                if identity and hasattr(identity, "id") and identity.id:
                    generated_ids.add(identity.id)

            all_seeds = request.resolved_location_seeds
            pre_ids = registry.lookup(all_seeds, "loc")
            missing_seeds = [
                s for s in all_seeds
                if pre_ids.get(s.seed_id) not in generated_ids
            ]

            if missing_seeds:
                all_warnings.append(
                    f"consolidated retry: {len(missing_seeds)} seeds missing, "
                    f"retrying as one batch"
                )
                try:
                    items, refs, retry_warnings, _score, _retried = await self._process_batch(
                        batch=missing_seeds,
                        batch_index=total_batches + 1,
                        total_batches=total_batches + 1,
                        world_ctx=world_ctx,
                        schema_desc=schema_desc,
                        char_summary=char_summary,
                        ModelClass=ModelClass,
                        registry=registry,
                    )
                    all_items.extend(items)
                    all_refs.extend(refs)
                    all_warnings.extend(retry_warnings)
                except Exception as exc:
                    all_warnings.append(f"consolidated retry failed: {exc}")

            # Final check
            if len(all_items) < total_seeds:
                raise RuntimeError(
                    f"LocationGenerationTool: generated {len(all_items)}/{total_seeds} locations, "
                    f"{total_seeds - len(all_items)} seeds missing after all retries. "
                    f"Warnings: {'; '.join(all_warnings)}"
                )

        # 7. Build quality summary
        quality_summary = self._build_quality_summary(
            total_seeds=len(request.resolved_location_seeds),
            total_generated=len(all_items),
            total_batches=total_batches,
            failed_batches=failed_batches,
            review_scores=all_review_scores,
            retry_count=retry_count,
            warnings=all_warnings,
        )

        return Stage2ToolResult(
            artifact_type=self.output_schema_alias,
            items=all_items,
            produced_refs=all_refs,
            warnings=all_warnings,
            provenance={
                "tool_id": self.tool_id,
                "total_batches": total_batches,
                "failed_batches": failed_batches,
                "total_seeds": len(request.resolved_location_seeds),
                "total_generated": len(all_items),
                "quality_summary": quality_summary,
                "seed_to_entity_mapping": registry.seed_mapping,
            },
        )

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    async def _process_batch(
        self,
        batch: list,
        batch_index: int,
        total_batches: int,
        world_ctx: dict[str, str],
        schema_desc: str,
        char_summary: str,
        ModelClass: type[BaseModel],
        registry: IdentityRegistry,
    ) -> tuple[list[Any], list[str], list[str], float | None, bool]:
        """Generate, review, and validate a single batch. Returns (items, refs, warnings, score, retried)."""
        warnings: list[str] = []
        retried = False

        # --- Phase 0: Register batch (idempotent) ---
        pre_ids = registry.lookup(batch, "loc")

        # --- Phase 1: Generate ---
        gen_prompt = build_generation_prompt(_GENERATION_USER_TEMPLATE, {
            **world_ctx,
            "schema_description": schema_desc,
            "character_seed_summary": char_summary,
            "seed_list": build_seed_list(batch, pre_ids),
            "batch_index": str(batch_index),
            "total_batches": str(total_batches),
            "seed_count": str(len(batch)),
        })

        raw_gen = await chat_json(gen_prompt, system=_GENERATION_SYSTEM)
        gen_data = _safe_json_loads(raw_gen)
        if not isinstance(gen_data, list):
            gen_data = [gen_data]

        # --- Phase 2: Quality review ---
        review_score: float | None = None
        try:
            review_prompt = build_generation_prompt(_REVIEW_USER_TEMPLATE, {
                **world_ctx,
                "schema_description": schema_desc,
                "generated_locations_json": json.dumps(gen_data, ensure_ascii=False, indent=2),
            })
            raw_review = await chat_json(review_prompt, system=_REVIEW_SYSTEM)
            review_result = _safe_json_loads(raw_review)

            if isinstance(review_result, dict) and "review" in review_result:
                review_info = review_result["review"]
                review_score = review_info.get("overall_score")
                issues = review_info.get("issues", [])

                # Use corrected locations if available
                corrected = review_result.get("corrected_locations")
                if issues:
                    if isinstance(corrected, list) and corrected:
                        gen_data = corrected
                        warnings.append(
                            f"batch {batch_index} review (score={review_score}): "
                            f"发现 {len(issues)} 个问题并已自动修正"
                        )
                    else:
                        warnings.append(
                            f"batch {batch_index} review (score={review_score}): "
                            + "; ".join(str(i) for i in issues)
                        )
                        warnings.append(
                            f"batch {batch_index}: review returned no corrected_locations, "
                            "using generation output"
                        )
                elif isinstance(corrected, list) and corrected:
                    gen_data = corrected

                # Retry if quality is below threshold
                if review_score is not None and review_score < _QUALITY_THRESHOLD:
                    retried = True
                    retry_items, retry_refs, retry_warnings = await self._retry_batch(
                        batch=batch,
                        batch_index=batch_index,
                        total_batches=total_batches,
                        world_ctx=world_ctx,
                        schema_desc=schema_desc,
                        char_summary=char_summary,
                        ModelClass=ModelClass,
                        review_issues=issues,
                        registry=registry,
                        pre_ids=pre_ids,
                    )
                    if retry_items:
                        warnings.extend(retry_warnings)
                        return retry_items, retry_refs, warnings, review_score, retried
                    else:
                        warnings.append(
                            f"batch {batch_index}: retry also failed, using original output"
                        )

            else:
                warnings.append(
                    f"batch {batch_index}: review returned unexpected format, "
                    "using generation output"
                )

        except Exception as review_exc:
            warnings.append(
                f"batch {batch_index}: review step failed ({review_exc}), "
                "using unreviewed output"
            )

        # --- Phase 3: Validate ---
        validated, val_warnings = parse_and_validate(gen_data, ModelClass, batch)
        warnings.extend(val_warnings)

        # --- Phase 3.5: Completeness check + retry for missing seeds ---
        if len(validated) < len(batch):
            missing_count = len(batch) - len(validated)
            warnings.append(
                f"batch {batch_index}: generated {len(validated)}/{len(batch)} items, "
                f"{missing_count} missing; retrying for missing seeds"
            )
            generated_ids: set[str] = set()
            for item in validated:
                identity = getattr(item, "identity", None)
                if identity and hasattr(identity, "id") and identity.id:
                    generated_ids.add(identity.id)
            missing_seeds = [
                s for s in batch
                if pre_ids.get(s.seed_id) not in generated_ids
            ]
            if missing_seeds:
                retry_items, retry_refs, retry_warnings = await self._retry_batch(
                    batch=missing_seeds,
                    batch_index=batch_index,
                    total_batches=total_batches,
                    world_ctx=world_ctx,
                    schema_desc=schema_desc,
                    char_summary=char_summary,
                    ModelClass=ModelClass,
                    review_issues=[f"上一轮缺少 {missing_count} 个地点，请为以下种子生成地点"],
                    registry=registry,
                    pre_ids=pre_ids,
                )
                if retry_items:
                    validated.extend(retry_items)
                    warnings.extend(retry_warnings)
                else:
                    raise RuntimeError(
                        f"LocationGenerationTool: batch {batch_index} completeness retry failed, "
                        f"{missing_count} seeds still missing. Warnings: {'; '.join(warnings)}"
                    )

        # --- Phase 4: Verify & fix entity IDs ---
        refs = assign_entity_ids(validated, batch, registry, "loc")
        _restore_seed_importance(validated, batch, pre_ids)

        return validated, refs, warnings, review_score, retried

    # ------------------------------------------------------------------
    # Retry on low quality
    # ------------------------------------------------------------------

    async def _retry_batch(
        self,
        batch: list,
        batch_index: int,
        total_batches: int,
        world_ctx: dict[str, str],
        schema_desc: str,
        char_summary: str,
        ModelClass: type[BaseModel],
        review_issues: list[Any],
        registry: IdentityRegistry,
        pre_ids: dict[str, str],
    ) -> tuple[list[Any], list[str], list[str]]:
        """Retry generation with review feedback incorporated into the prompt."""
        warnings: list[str] = []
        issues_str = "\n".join(f"  - {i}" for i in review_issues) if review_issues else "  无具体问题"

        retry_prompt = build_generation_prompt(_RETRY_USER_TEMPLATE, {
            **world_ctx,
            "schema_description": schema_desc,
            "character_seed_summary": char_summary,
            "seed_list": build_seed_list(batch, pre_ids),
            "review_issues": issues_str,
            "seed_count": str(len(batch)),
        })

        try:
            raw_retry = await chat_json(retry_prompt, system=_RETRY_SYSTEM)
            retry_data = _safe_json_loads(raw_retry)
            if not isinstance(retry_data, list):
                retry_data = [retry_data]

            validated, val_warnings = parse_and_validate(retry_data, ModelClass, batch)
            warnings.extend(val_warnings)
            warnings.append(f"batch {batch_index}: retried due to low quality score")

            refs = assign_entity_ids(validated, batch, registry, "loc")
            _restore_seed_importance(validated, batch, pre_ids)

            return validated, refs, warnings

        except Exception as exc:
            warnings.append(f"batch {batch_index}: retry failed ({exc})")
            return [], [], warnings

    # ------------------------------------------------------------------
    # Quality summary
    # ------------------------------------------------------------------

    @staticmethod
    def _build_quality_summary(
        total_seeds: int,
        total_generated: int,
        total_batches: int,
        failed_batches: int,
        review_scores: list[float],
        retry_count: int,
        warnings: list[str],
    ) -> dict[str, Any]:
        avg_score = sum(review_scores) / len(review_scores) if review_scores else 0.0
        # Extract key issues from warnings (review-related)
        key_issues: list[str] = []
        for w in warnings:
            if "review" in w.lower() and "score=" in w.lower():
                key_issues.append(w)
        return {
            "total_seeds": total_seeds,
            "total_generated": total_generated,
            "batches_processed": total_batches - failed_batches,
            "avg_review_score": round(avg_score, 2),
            "retry_count": retry_count,
            "key_issues": key_issues[:5],
        }
