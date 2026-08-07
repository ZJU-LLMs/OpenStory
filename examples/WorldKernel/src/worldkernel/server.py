from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from worldkernel.constraints import load_generation_constraints
from worldkernel.llm import client as llm_client
from worldkernel.stage1.pipeline import Stage1Error, run_stage1
from worldkernel.stage3.runtime import Stage3RuntimeManager
from worldkernel.stage3.sessions import list_stage3_ready_session_summaries

BASE_DIR = Path(__file__).parent.parent.parent
CONFIGS_DIR = BASE_DIR / "configs"
TEMPLATES_DIR = BASE_DIR / "templates"
FRONTEND_DIR = BASE_DIR / "frontend"

_constraints = None
_stage3_runtime = Stage3RuntimeManager(BASE_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _constraints
    load_dotenv(BASE_DIR / ".env")
    llm_client.init(CONFIGS_DIR / "models.yaml")
    _constraints = load_generation_constraints(CONFIGS_DIR / "architect.yaml")
    try:
        yield
    finally:
        await _stage3_runtime.stop(shutdown_ray=True)


app = FastAPI(title="WorldKernel Stage 1", lifespan=lifespan)


@app.exception_handler(Stage1Error)
async def stage1_error_handler(request: Request, exc: Stage1Error) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": str(exc) or repr(exc),
            "step": exc.step,
            "detail": str(exc.cause) or repr(exc.cause),
        },
    )


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc) or repr(exc),
            "step": "unknown",
            "detail": type(exc).__name__,
        },
    )

#添加前端的翻译模块
class TranslateRequest(BaseModel):
    text: str

@app.post("/api/utils/translate")
async def translate_text(req: TranslateRequest):
    """供前端使用的动态文本翻译接口"""
    prompt = f"请将以下英文世界观设定翻译为极其精简的简体中文词组或短句。只需返回最终的翻译结果，不要任何解释、引号或多余的标点：\n{req.text}"
    
    try:
        response = await llm_client.chat(prompt)
        return {"translated": response.strip()}
    except Exception as e:
        import logging
        logging.getLogger("worldkernel.server").error(f"Translation API failed: {e}")
        return {"translated": req.text}

class ParseRequest(BaseModel):
    input: str


class VisualGenerateRequest(BaseModel):
    generate_background: bool = True
    generate_location_patches: bool | None = None
    reuse_existing_spatial: bool = True


@app.post("/api/stage1/parse")
async def parse(req: ParseRequest):
    session = await run_stage1(req.input, constraints=_constraints)
    return session


@app.get("/api/stage3/sessions")
async def list_stage3_ready_sessions():
    """List local sessions that already have the artifacts needed to enter Stage3."""
    return {"sessions": list_stage3_ready_session_summaries(TEMPLATES_DIR)}


@app.get("/api/stage1/session/{session_id}")
async def get_session(session_id: str):
    session_dir = TEMPLATES_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="session not found")
    files = sorted(
        str(f.relative_to(session_dir)).replace("\\", "/")
        for f in session_dir.rglob("*.json")
    )
    return {"session_id": session_id, "files": files}


@app.get("/api/stage1/session/{session_id}/{path:path}")
async def get_session_file(session_id: str, path: str):
    file_path = TEMPLATES_DIR / session_id / path
    if not file_path.exists() or file_path.suffix not in (".json", ".yaml", ".png"):
        raise HTTPException(status_code=404, detail="file not found")
    if file_path.suffix == ".png":
        return FileResponse(file_path, media_type="image/png")
    if file_path.suffix == ".yaml":
        import yaml
        return yaml.safe_load(file_path.read_text(encoding="utf-8"))
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if path.replace("\\", "/").endswith("generated/artifacts/spatial/visual_layout_manifest.json"):
        data = _hydrate_visual_manifest_response(data, file_path.parent)
    return data


def _hydrate_visual_manifest_response(data: object, spatial_root: Path) -> object:
    if not isinstance(data, dict):
        return data
    try:
        from worldkernel.architect.visual.location_patches import hydrate_existing_location_patches
        from worldkernel.architect.visual.models import VisualLayoutManifest

        manifest = VisualLayoutManifest.model_validate(data)
        hydrate_existing_location_patches(manifest, spatial_root)
        return manifest.model_dump(mode="json")
    except Exception:
        return data


@app.post("/api/stage2/generate/{session_id}")
async def stage2_generate(session_id: str):
    session_dir = TEMPLATES_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="session not found")

    from worldkernel.architect import (
        compile_stage1_init_context,
        create_default_schema_registry,
        create_default_tool_registry,
        load_stage1_session_schema_source,
        save_semantic_artifacts,
    )
    from worldkernel.architect.semantic.runner import InitDAGRunner

    sr = create_default_schema_registry()
    load_stage1_session_schema_source(
        session_dir, sr, source_id="visual-e2e", world_id=session_id,
    )
    tr = create_default_tool_registry(sr)
    ctx = compile_stage1_init_context(
        session_dir, tool_registry=tr, source_id="visual-e2e", world_id=session_id,
        constraints=_constraints,
    )

    runner = InitDAGRunner(schema_registry=sr, tool_registry=tr)
    state = await runner.run_async(ctx)

    loc_result = (
        state.result_store.get_step_result("generate_locations")
        if state.result_store.has_step_result("generate_locations")
        else None
    )
    report = save_semantic_artifacts(
        session_id, ctx, state,
        output_root=session_dir / "generated" / "artifacts",
    )

    return {
        "completed_steps": state.completed_steps,
        "errors": state.errors,
        "locations": {
            "count": len(loc_result.items) if loc_result else 0,
            "avg_score": (
                loc_result.provenance.get("quality_summary", {}).get("avg_review_score")
                if loc_result else None
            ),
        },
        "report": {"success": report.success, "counts": report.counts},
    }


@app.post("/api/spatial/generate/{session_id}")
async def spatial_generate(session_id: str):
    """Standalone spatial generation from disk-based semantic artifacts."""
    semantic_root = _resolve_session_semantic_root(session_id)
    if not semantic_root.exists():
        raise HTTPException(status_code=404, detail="semantic artifacts not found; run Stage2 first")

    from worldkernel.architect.spatial import (
        SpatialInputAssembler,
        SpatialInputAssemblyError,
        SpatialPipeline,
    )
    from worldkernel.architect.spatial.config import load_spatial_generation_config

    config = load_spatial_generation_config(CONFIGS_DIR / "architect.yaml")

    try:
        assembler = SpatialInputAssembler()
        build_input = assembler.assemble(world_id=session_id, semantic_root=semantic_root)
    except SpatialInputAssemblyError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    pipeline = SpatialPipeline(config)
    result = pipeline.run(build_input)
    spatial_output_root = TEMPLATES_DIR / session_id / "generated" / "artifacts" / "spatial"
    world_background = _load_session_world_background(session_id)

    try:
        from worldkernel.architect.pipeline import save_spatial_blueprint
        from worldkernel.architect.visual import run_visual_pipeline

        visual_manifest = run_visual_pipeline(
            blueprint=result.blueprint,
            world_background=world_background,
            output_root=spatial_output_root,
            model_config_path=CONFIGS_DIR / "image_models.yaml",
            generate_background=config.rendering.ai_art_enabled,
            generate_location_patches=(
                config.rendering.ai_art_enabled
                and config.rendering.location_patches_enabled
            ),
            generate_road_texture=(
                config.rendering.ai_art_enabled
                and config.rendering.road_texture_enabled
            ),
            semantic_locations=[location.raw for location in build_input.locations],
        )
        result.blueprint.visual = visual_manifest.model_dump(mode="json")
        save_spatial_blueprint(result.blueprint, spatial_output_root)
    except Exception as exc:
        result.blueprint.visual = {"status": "failed", "error": str(exc)}

    validation = result.validation.report

    return {
        "world_id": session_id,
        "grid": {
            "width": result.blueprint.grid.width,
            "height": result.blueprint.grid.height,
            "tile_size": result.blueprint.grid.tile_size,
        },
        "regions": [r.model_dump(mode="json") for r in result.blueprint.regions],
        "routes": [
            {
                "path_edge_id": r.path_edge_id,
                "from_location_id": r.from_location_id,
                "to_location_id": r.to_location_id,
                "centerline": [{"x": t.x, "y": t.y} for t in r.centerline],
                "movement_cost": r.movement_cost,
                "access_tags": r.access_tags,
            }
            for r in result.blueprint.routes
        ],
        "road_tiles": [{"x": t.x, "y": t.y} for t in result.blueprint.road_tiles],
        "spawn_points": [sp.model_dump(mode="json") for sp in result.blueprint.spawn_points],
        "visual": result.blueprint.visual,
        "validation": {
            "passed": validation.passed,
            "issues": [i.model_dump(mode="json") for i in validation.issues],
        },
    }


def _load_session_world_background(session_id: str) -> dict:
    path = TEMPLATES_DIR / session_id / "generated" / "plan" / "world_background.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _resolve_session_semantic_root(session_id: str) -> Path:
    artifacts_root = TEMPLATES_DIR / session_id / "generated" / "artifacts"
    semantic_root = artifacts_root / "semantic"
    if (semantic_root / "metadata" / "semantic_manifest.json").exists():
        return semantic_root
    return artifacts_root


@app.post("/api/visual/generate/{session_id}")
async def visual_generate(session_id: str, req: VisualGenerateRequest | None = None):
    """Regenerate image assets from an existing semantic template.

    This test channel skips Stage1 and semantic generation. It reuses the saved
    spatial blueprint by default, and only rebuilds spatial data when no
    blueprint exists or reuse_existing_spatial is false.
    """
    session_dir = TEMPLATES_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="session not found")

    request = req or VisualGenerateRequest()
    from worldkernel.architect.visual.regenerate import regenerate_visual_from_template

    try:
        result = regenerate_visual_from_template(
            template_root=session_dir,
            config_path=CONFIGS_DIR / "architect.yaml",
            image_model_config_path=CONFIGS_DIR / "image_models.yaml",
            generate_background=request.generate_background,
            generate_location_patches=request.generate_location_patches,
            reuse_existing_spatial=request.reuse_existing_spatial,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    blueprint = result.blueprint
    return {
        "world_id": result.world_id,
        "template_root": result.template_root,
        "semantic_root": result.semantic_root,
        "spatial_output_root": result.spatial_output_root,
        "spatial_source": result.spatial_source,
        "semantic": result.semantic_counts,
        "spatial": {
            "grid": {
                "width": blueprint.grid.width,
                "height": blueprint.grid.height,
                "tile_size": blueprint.grid.tile_size,
            },
            "regions": [r.model_dump(mode="json") for r in blueprint.regions],
            "routes": [
                {
                    "path_edge_id": r.path_edge_id,
                    "from_location_id": r.from_location_id,
                    "to_location_id": r.to_location_id,
                    "centerline": [{"x": t.x, "y": t.y} for t in r.centerline],
                    "movement_cost": r.movement_cost,
                    "access_tags": r.access_tags,
                }
                for r in blueprint.routes
            ],
            "road_tiles": [{"x": t.x, "y": t.y} for t in blueprint.road_tiles],
            "spawn_points": [sp.model_dump(mode="json") for sp in blueprint.spawn_points],
            "visual": blueprint.visual,
            "validation": result.validation,
        },
        "counts": result.spatial_counts,
    }


@app.post("/api/stage2/run/{session_id}")
async def stage2_run(session_id: str):
    """Unified Stage 2: semantic generation + spatial generation in one call."""
    session_dir = TEMPLATES_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="session not found")

    from worldkernel.architect.pipeline import run_stage2

    try:
        result = await run_stage2(
            session_root=session_dir,
            output_root=session_dir / "generated" / "artifacts",
            config_path=CONFIGS_DIR / "architect.yaml",
            constraints=_constraints,
            save_semantic=True,
            save_spatial=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    spatial = result.spatial
    validation = spatial.validation.report

    return {
        "world_id": result.world_id,
        "semantic": {
            "location_count": len(result.foundation.locations),
            "path_count": len(result.foundation.path_graph),
            "character_count": len(result.foundation.characters),
        },
        "spatial": {
            "grid": {
                "width": spatial.blueprint.grid.width,
                "height": spatial.blueprint.grid.height,
                "tile_size": spatial.blueprint.grid.tile_size,
            },
            "regions": [r.model_dump(mode="json") for r in spatial.blueprint.regions],
            "routes": [
                {
                    "path_edge_id": r.path_edge_id,
                    "from_location_id": r.from_location_id,
                    "to_location_id": r.to_location_id,
                    "centerline": [{"x": t.x, "y": t.y} for t in r.centerline],
                    "movement_cost": r.movement_cost,
                    "access_tags": r.access_tags,
                }
                for r in spatial.blueprint.routes
            ],
            "road_tiles": [{"x": t.x, "y": t.y} for t in spatial.blueprint.road_tiles],
            "spawn_points": [sp.model_dump(mode="json") for sp in spatial.blueprint.spawn_points],
            "visual": spatial.blueprint.visual,
            "validation": {
                "passed": validation.passed,
                "issues": [i.model_dump(mode="json") for i in validation.issues],
            },
        },
    }


class Stage3AdapterRequest(BaseModel):
    max_ticks: int = 100


@app.post("/api/stage3/agentkernel/{session_id}")
async def stage3_agentkernel(session_id: str, req: Stage3AdapterRequest | None = None):
    """Sync completed Stage2 semantic + spatial artifacts into the WorldKernel Agent-Kernel runtime."""
    session_dir = TEMPLATES_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="session not found")

    from worldkernel.stage3 import build_agentkernel_project

    request = req or Stage3AdapterRequest()
    try:
        result = build_agentkernel_project(
            session_root=session_dir,
            max_ticks=request.max_ticks,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result.model_dump(mode="json")


class Stage3RuntimeStartRequest(BaseModel):
    max_ticks: int = 100


@app.post("/api/stage3/runtime/start/{session_id}")
async def stage3_runtime_start(session_id: str, req: Stage3RuntimeStartRequest | None = None):
    """Start the single active Stage3 Agent-Kernel runtime for a completed session."""
    session_dir = TEMPLATES_DIR / session_id
    request = req or Stage3RuntimeStartRequest()
    try:
        return await _stage3_runtime.start(session_dir, max_ticks=request.max_ticks)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/stage3/runtime/tick")
async def stage3_runtime_tick():
    """Advance the active Stage3 runtime by one tick."""
    try:
        return await _stage3_runtime.tick()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/stage3/runtime/state")
async def stage3_runtime_state():
    """Return the latest collected Stage3 runtime state."""
    return _stage3_runtime.state()


@app.post("/api/stage3/runtime/stop")
async def stage3_runtime_stop():
    """Stop the active Stage3 runtime. Safe to call repeatedly."""
    try:
        return await _stage3_runtime.stop(shutdown_ray=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "worldkernel.server:app",
        host="0.0.0.0",
        port=8100,
        reload=True,
        reload_dirs=[str(Path(__file__).parent)],
        reload_excludes=[
            "*/templates/*",
            "*__pycache__*",
            "*/architect/spatial/*",
            "*/architect/pipeline*",
            "*/architect/init/*",
            "*/architect/semantic/*",
            "*/architect/registry/*",
            "*/architect/tools/*",
        ],
    )
