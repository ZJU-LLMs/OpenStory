from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from worldkernel.llm import client as llm_client
from worldkernel.stage1.pipeline import Stage1Error, run_stage1

BASE_DIR = Path(__file__).parent.parent.parent
CONFIGS_DIR = BASE_DIR / "configs"
TEMPLATES_DIR = BASE_DIR / "templates"
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(BASE_DIR / ".env")
    llm_client.init(CONFIGS_DIR / "models.yaml")
    yield


app = FastAPI(title="WorldKernel Stage 1", lifespan=lifespan)


@app.exception_handler(Stage1Error)
async def stage1_error_handler(request: Request, exc: Stage1Error) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": str(exc), "step": exc.step, "detail": str(exc.cause)},
    )


class ParseRequest(BaseModel):
    input: str


@app.post("/api/stage1/parse")
async def parse(req: ParseRequest):
    session = await run_stage1(req.input)
    return session


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
    if not file_path.exists() or file_path.suffix not in (".json", ".yaml"):
        raise HTTPException(status_code=404, detail="file not found")
    import json
    if file_path.suffix == ".yaml":
        import yaml
        return yaml.safe_load(file_path.read_text(encoding="utf-8"))
    return json.loads(file_path.read_text(encoding="utf-8"))


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run("worldkernel.server:app", host="0.0.0.0", port=8100, reload=True)
