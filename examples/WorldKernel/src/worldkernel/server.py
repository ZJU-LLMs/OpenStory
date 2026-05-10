from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from worldkernel.llm import client as llm_client
from worldkernel.stage1.pipeline import run_stage1

BASE_DIR = Path(__file__).parent.parent.parent
CONFIGS_DIR = BASE_DIR / "configs"
WORLDS_DIR = BASE_DIR / "worlds" / "generated"
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(BASE_DIR / ".env")
    llm_client.init(CONFIGS_DIR / "models.yaml")
    yield


app = FastAPI(title="WorldKernel Stage 1", lifespan=lifespan)


class ParseRequest(BaseModel):
    input: str


@app.post("/api/stage1/parse")
async def parse(req: ParseRequest):
    spec = await run_stage1(req.input)
    return spec


@app.get("/api/stage1/spec/{session_id}")
async def get_spec(session_id: str):
    path = WORLDS_DIR / session_id / "world_spec.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="spec not found")
    return json.loads(path.read_text(encoding="utf-8"))


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run("worldkernel.server:app", host="0.0.0.0", port=8100, reload=True)
