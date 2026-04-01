"""FastAPI server exposing simulation data and WebSocket streaming."""

import asyncio
import os
import yaml
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .manager import ConnectionManager

manager = ConnectionManager()
redis_pool: Optional[aioredis.ConnectionPool] = None
api_config: Dict[str, Any] = {}

app = FastAPI(title="MAS Simulation API")


class AgentIdList(BaseModel):
    """Request payload describing a list of agent identifiers.

    Attributes:
        agent_ids (List[str]): List of agent identifiers.
    """

    agent_ids: List[str]


class ModelConfigUpdate(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


@app.get("/api/config/model", summary="Get model configuration")
async def get_model_config() -> Dict[str, Any]:
    project_abs_path = os.environ.get("MAS_PROJECT_ABS_PATH", "")
    if not project_abs_path:
        raise HTTPException(status_code=500, detail="MAS_PROJECT_ABS_PATH environment variable is not set")
    config_path = os.path.join(project_abs_path, "configs", "models_config.yaml")
    if not os.path.exists(config_path):
        raise HTTPException(status_code=404, detail="models_config.yaml not found")
    
    with open(config_path, "r", encoding="utf-8") as f:
        models = yaml.safe_load(f)
    
    if models and isinstance(models, list) and len(models) > 0:
        first_model = models[0]
        return {
            "base_url": first_model.get("base_url", ""),
            "api_key": first_model.get("api_key", ""),
            "model": first_model.get("model", "")
        }
    return {}

@app.post("/api/config/model", summary="Update model configuration")
async def update_model_config(config: ModelConfigUpdate) -> Dict[str, Any]:
    project_abs_path = os.environ.get("MAS_PROJECT_ABS_PATH", "")
    if not project_abs_path:
        raise HTTPException(status_code=500, detail="MAS_PROJECT_ABS_PATH environment variable is not set")
    config_path = os.path.join(project_abs_path, "configs", "models_config.yaml")
    if not os.path.exists(config_path):
        raise HTTPException(status_code=404, detail="models_config.yaml not found")
    
    with open(config_path, "r", encoding="utf-8") as f:
        models = yaml.safe_load(f)
    
    if models and isinstance(models, list):
        for model_entry in models:
            if config.base_url is not None:
                model_entry["base_url"] = config.base_url
            if config.api_key is not None:
                model_entry["api_key"] = config.api_key
            if config.model is not None:
                model_entry["model"] = config.model
        
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(models, f, allow_unicode=True, sort_keys=False)
            
        # 安排重启
        import threading
        import time
        import sys
        def restart_server():
            time.sleep(1) # 给前端留出返回响应的时间
            print("Restarting server to apply new configuration...")
            os.execv(sys.executable, ['python'] + sys.argv)
            
        threading.Thread(target=restart_server).start()
            
        return {"status": "success"}
    else:
        raise HTTPException(status_code=400, detail="Invalid models_config.yaml format")

@app.post("/api/reset", summary="Reset simulation and clear data")
async def reset_simulation() -> Dict[str, Any]:
    global redis_pool
    if redis_pool:
        try:
            redis_client = aioredis.Redis(connection_pool=redis_pool)
            await redis_client.flushdb()
            print("Redis database flushed by reset request.")
        except Exception as e:
            print(f"Failed to flush Redis database: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to clear database: {str(e)}")
            
    # 重启后端以彻底重置内存状态
    import threading
    import time
    import sys
    def restart_server():
        time.sleep(1) # 给前端留出返回响应的时间
        print("Restarting server for full reset...")
        os.execv(sys.executable, ['python'] + sys.argv)
        
    threading.Thread(target=restart_server).start()
    
    return {"status": "success", "message": "Simulation data cleared and restarting"}

async def redis_listener() -> None:
    """Listen to Redis pub/sub channels and broadcast messages to connected clients."""
    global redis_pool

    if not redis_pool:
        print("Redis pool not initialized. Listener cannot start.")
        return

    redis_client = aioredis.Redis(connection_pool=redis_pool)
    pubsub = redis_client.pubsub()
    channel_pattern = "sim_events:*"

    await pubsub.psubscribe(channel_pattern)
    print(f"Background listener started. Subscribed to '{channel_pattern}'")

    while True:
        try:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "pmessage":
                await manager.broadcast(message["data"].decode("utf-8"))
        except asyncio.CancelledError:
            print("Redis listener task cancelled.")
            break
        except Exception as exc:
            print(f"Error in Redis listener: {exc}")
            await asyncio.sleep(5)


@app.on_event("startup")
async def startup_event() -> None:
    """Start the Redis listener background task when the application launches."""
    asyncio.create_task(redis_listener())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    Accept WebSocket connections and keep them alive for outbound events.

    Args:
        websocket (WebSocket): Active WebSocket connection.
    """
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/agents/ids", response_model=List[str], summary="Get all agent identifiers")
async def get_all_agent_ids() -> List[str]:
    """
    Retrieve the identifiers of every agent known to the simulation.

    Returns:
        List[str]: Agent identifiers discovered in Redis.

    Raises:
        HTTPException: When the Redis pool has not been initialized.
    """
    global redis_pool
    if redis_pool is None:
        raise HTTPException(status_code=500, detail="Redis pool is not initialized.")

    redis_client = aioredis.Redis(connection_pool=redis_pool, decode_responses=True)
    agent_ids: List[str] = []
    async for key in redis_client.scan_iter("*:profile"):
        agent_id = key.split(":")[0]
        agent_ids.append(agent_id)
    return agent_ids


@app.get("/api/agents/{agent_id}", summary="Get a single agent profile")
async def get_agent_profile(agent_id: str) -> Dict[str, str]:
    """
    Retrieve the profile stored for a single agent.

    Args:
        agent_id (str): Identifier of the agent to describe.

    Returns:
        Dict[str, str]: Profile fields stored for the agent.

    Raises:
        HTTPException: When the agent profile cannot be found.
    """
    global redis_pool
    if redis_pool is None:
        raise HTTPException(status_code=500, detail="Redis pool is not initialized.")

    redis_client = aioredis.Redis(connection_pool=redis_pool, decode_responses=True)
    profile_key = f"{agent_id}:profile"

    if not await redis_client.exists(profile_key):
        raise HTTPException(status_code=404, detail=f"Agent with id '{agent_id}' not found.")

    return await redis_client.hgetall(profile_key)


@app.post("/api/agents/profiles_by_ids", summary="Get agent profiles by identifier list")
async def get_agent_profiles_by_ids(id_list: AgentIdList) -> Dict[str, Dict[str, str]]:
    """
    Retrieve profiles for the requested agent identifiers.

    Args:
        id_list (AgentIdList): Request payload containing agent identifiers.

    Returns:
        Dict[str, Dict[str, str]]: Mapping of agent identifiers to their profile data.

    Raises:
        HTTPException: When the Redis pool has not been initialized.
    """
    global redis_pool
    if redis_pool is None:
        raise HTTPException(status_code=500, detail="Redis pool is not initialized.")

    redis_client = aioredis.Redis(connection_pool=redis_pool, decode_responses=True)
    agent_profiles: Dict[str, Dict[str, str]] = {}

    async with redis_client.pipeline() as pipe:
        for agent_id in id_list.agent_ids:
            pipe.hgetall(f"{agent_id}:profile")
        results = await pipe.execute()

    for agent_id, profile_data in zip(id_list.agent_ids, results):
        if profile_data:
            agent_profiles[agent_id] = profile_data

    return agent_profiles


def start_server(config: Dict[str, Any]) -> None:
    """
    Launch the FastAPI server with the provided configuration.

    Args:
        config (Dict[str, Any]): Settings dictionary containing host, port, and Redis details.
    """
    global redis_pool, api_config

    api_config = config

    redis_settings = config.get("redis_settings", {})
    redis_settings["decode_responses"] = False
    redis_pool = aioredis.ConnectionPool(**redis_settings)

    uvicorn.run(
        "agentkernel_standalone.mas.interface.server:app",
        host=config.get("host", "127.0.0.1"),
        port=config.get("port", 8000),
        log_level="info",
    )
