"""FastAPI server exposing simulation data and WebSocket streaming."""

import asyncio
import json
import os
import yaml
import threading
from typing import Any, Dict, List, Optional, Union

import redis.asyncio as aioredis
import uvicorn
import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pydantic import BaseModel
from contextlib import asynccontextmanager

from .manager import ConnectionManager

manager = ConnectionManager()
redis_pool: Optional[aioredis.ConnectionPool] = None
api_config: Dict[str, Any] = {}

# 内存缓存：存储最新一次 tick 的所有 agent 数据
_agents_snapshot: Dict[str, Any] = {}
_snapshot_tick: int = -1

# 用于控制主循环的事件对象（由外部注入，threading.Event）
_tick_start_event: Optional[threading.Event] = None

# Pod Manager 引用（由外部注入，用于动态添加 agent）
_pod_manager: Optional[Any] = None
_tts_voice_cache: Dict[str, str] = {}
_tts_style_cache: Dict[str, str] = {}

VOICE_DESIGN_MODEL = "qwen-voice-design"
VOICE_DESIGN_TARGET_MODEL = "qwen3-tts-vd-2026-01-26"
DEFAULT_VOICE_STYLE = "中性温和的声线，音色自然，吐字清晰，语速适中，适合日常人物对白。"


def _stable_hash(text: str) -> int:
    value = 0
    for ch in text:
        value = ord(ch) + ((value << 5) - value)
    return abs(value)


def _load_primary_model_config() -> Dict[str, str]:
    project_abs_path = os.environ.get("MAS_PROJECT_ABS_PATH", "")
    if not project_abs_path:
        return {}

    config_path = os.path.join(project_abs_path, "configs", "models_config.yaml")
    if not os.path.exists(config_path):
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            models = yaml.safe_load(f)
        if models and isinstance(models, list) and len(models) > 0:
            first_model = models[0]
            return {
                "base_url": first_model.get("base_url", ""),
                "api_key": first_model.get("api_key", ""),
                "model": first_model.get("model", ""),
            }
    except Exception:
        return {}

    return {}


async def _infer_voice_style_with_llm(speaker: str, gender_hint: Optional[str]) -> str:
    cache_key = f"{speaker}|{gender_hint or ''}"
    if cache_key in _tts_style_cache:
        return _tts_style_cache[cache_key]

    model_config = _load_primary_model_config()
    base_url = str(model_config.get("base_url", "")).rstrip("/")
    api_key = str(model_config.get("api_key", "")).strip()
    model = str(model_config.get("model", "")).strip()

    if not base_url or not api_key or not model:
        return DEFAULT_VOICE_STYLE

    if not api_key.startswith("Bearer "):
        api_key = f"Bearer {api_key}"

    system_prompt = (
        "你是一个中文配音导演。"
        "请根据人物名字和已知档案线索，为语音合成生成一句中文说话风格描述。"
        "只输出一句风格描述，不要解释，不要分点，不要加引号。"
        "描述中应包含声线特征、语气、语速或气质，适合用于角色对白配音。"
    )
    user_prompt = (
        f"人物名：{speaker or '未知'}\n"
        f"档案中的原始性别线索：{gender_hint or '无'}\n"
        "请输出一句适合这个人物的说话风格描述。"
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 80,
                },
                timeout=30.0,
            )
        if response.status_code != 200:
            return DEFAULT_VOICE_STYLE
        content = response.json()["choices"][0]["message"]["content"].strip()
        result = content or DEFAULT_VOICE_STYLE
    except Exception:
        result = DEFAULT_VOICE_STYLE

    _tts_style_cache[cache_key] = result
    return result


def _build_voice_prompt(speaker: str, style_prompt: str) -> str:
    style = (style_prompt or "").strip()
    if style:
        return style
    return DEFAULT_VOICE_STYLE


def _build_safe_preferred_name(speaker: str) -> str:
    seed = speaker or "default"
    return f"voice_{_stable_hash(seed)}"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 清空 Redis 数据库
    if redis_pool:
        try:
            redis_client = aioredis.Redis(connection_pool=redis_pool)
            await redis_client.flushdb()
            print("Redis database flushed on startup.")
        except Exception as e:
            print(f"Failed to flush Redis database: {e}")

    asyncio.create_task(redis_listener())
    yield

app = FastAPI(title="MAS Simulation API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AgentIdList(BaseModel):
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
            import ray
            if ray.is_initialized():
                ray.shutdown()
            os.execv(sys.executable, ['python'] + sys.argv)
            
        threading.Thread(target=restart_server).start()
            
        return {"status": "success"}
    else:
        raise HTTPException(status_code=400, detail="Invalid models_config.yaml format")

@app.post("/api/tts", summary="Proxy for DashScope TTS to bypass CORS")
async def tts_proxy(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    api_key = request.headers.get("Authorization")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
        
    # Check if Authorization has Bearer prefix, if not add it
    if not api_key.startswith("Bearer "):
        api_key = f"Bearer {api_key}"

    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        if body.get("model") == VOICE_DESIGN_MODEL:
            speaker = body.get("input", {}).get("speaker", "")
            text = body.get("input", {}).get("text", "")
            gender_hint = body.get("input", {}).get("gender", "")
            if not text:
                raise HTTPException(status_code=400, detail="TTS text is required")

            cache_key = speaker or "__default__"
            voice_name = _tts_voice_cache.get(cache_key)

            if not voice_name:
                style_prompt = await _infer_voice_style_with_llm(speaker, gender_hint)
                create_payload = {
                    "model": VOICE_DESIGN_MODEL,
                    "input": {
                        "action": "create",
                        "target_model": VOICE_DESIGN_TARGET_MODEL,
                        "voice_prompt": _build_voice_prompt(speaker, style_prompt),
                        "preview_text": text,
                        "preferred_name": _build_safe_preferred_name(cache_key),
                        "language": "zh"
                    },
                    "parameters": {
                        "sample_rate": 24000,
                        "response_format": "wav"
                    }
                }
                create_response = await client.post(
                    "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization",
                    headers=headers,
                    json=create_payload,
                    timeout=60.0,
                )
                if create_response.status_code != 200:
                    err_text = create_response.content.decode("utf-8", errors="ignore")
                    raise HTTPException(status_code=create_response.status_code, detail=f"DashScope Error: {err_text}")
                try:
                    voice_name = create_response.json()["output"]["voice"]
                except Exception:
                    raise HTTPException(status_code=500, detail="Failed to parse designed voice from DashScope response")
                _tts_voice_cache[cache_key] = voice_name

            synth_payload = {
                "model": VOICE_DESIGN_TARGET_MODEL,
                "input": {
                    "text": text,
                    "voice": voice_name
                }
            }
            response = await client.post(
                "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
                headers=headers,
                json=synth_payload,
                timeout=60.0,
            )
        else:
            response = await client.post(
                "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
                headers=headers,
                json=body,
                timeout=60.0,
            )

        if response.status_code != 200:
            err_text = response.content.decode('utf-8', errors='ignore')
            raise HTTPException(status_code=response.status_code, detail=f"DashScope Error: {err_text}")

        return Response(
            content=response.content,
            media_type=response.headers.get("content-type", "application/json")
        )

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
        import ray
        if ray.is_initialized():
            ray.shutdown()
        os.execv(sys.executable, ['python'] + sys.argv)
        
    threading.Thread(target=restart_server).start()
    
    return {"status": "success", "message": "Simulation data cleared and restarting"}

async def redis_listener() -> None:
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
                await manager.broadcast(message["data"])
        except asyncio.CancelledError:
            print("Redis listener task cancelled.")
            break
        except Exception as exc:
            print(f"Error in Redis listener: {exc}")
            await asyncio.sleep(5)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    # 新连接时推送当前快照
    if _agents_snapshot:
        await websocket.send_text(json.dumps({
            "type": "snapshot",
            "tick": _snapshot_tick,
            "data": _agents_snapshot,
        }))
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type")

                if msg_type == "start_tick":
                    if _tick_start_event:
                        _tick_start_event.set()
                        print("Received start_tick from frontend. Resuming simulation.")
                    else:
                        print("start_tick event received but not wired to simulation loop.")

                elif msg_type == "set_plan":
                    agent_id = msg.get("agent_id")
                    action = msg.get("action")
                    location = msg.get("location")
                    target = msg.get("target")
                    tick = _snapshot_tick + 1 if _snapshot_tick >= 0 else 0

                    if agent_id and redis_pool:
                        try:
                            redis_client = aioredis.Redis(connection_pool=redis_pool)
                            plan_data = {
                                "action": action,
                                "location": location,
                                "target": target,
                                "tick": tick
                            }
                            await redis_client.set(f"user_plan:{agent_id}", json.dumps(plan_data))
                            print(f"Successfully set user plan for '{agent_id}' at tick {tick}.")
                            
                            await websocket.send_text(json.dumps({
                                "type": "set_plan_response",
                                "success": True,
                                "agent_id": agent_id
                            }))
                        except Exception as e:
                            print(f"Error setting plan for '{agent_id}': {e}")
                            await websocket.send_text(json.dumps({
                                "type": "set_plan_response",
                                "success": False,
                                "error": str(e)
                            }))
                    else:
                        await websocket.send_text(json.dumps({
                            "type": "set_plan_response",
                            "success": False,
                            "error": "agent_id missing or redis_pool not initialized"
                        }))

                elif msg_type == "add_agent":
                    # 动态添加 agent
                    agent_id = msg.get("agent_id")
                    template_name = msg.get("template_name", "default")
                    profile = msg.get("profile", {})
                    memory = msg.get("memory", [])

                    if not agent_id:
                        await websocket.send_text(json.dumps({
                            "type": "add_agent_response",
                            "success": False,
                            "error": "agent_id is required"
                        }))
                        continue

                    if _pod_manager is None:
                        await websocket.send_text(json.dumps({
                            "type": "add_agent_response",
                            "success": False,
                            "error": "Pod manager not initialized"
                        }))
                        continue

                    try:
                        # 构建初始化数据 - 键名需要与 agents_config.yaml 中的配置匹配
                        # profile_data: "agent_profiles" -> 使用 "agent_profiles" 作为键
                        # state_data: "agent_states" -> 使用 "agent_states" 作为键
                        # 初始记忆合并为一条长期记忆
                        long_term_memory = [{"tick": 0, "content": "\n".join(memory)}] if memory else []
                        init_data = {
                            "agent_profiles": profile,
                            "agent_states": {
                                "long_term_memory": long_term_memory,
                            },
                        }

                        # 调用 pod_manager 的 add_agent 方法
                        success = await _pod_manager.add_agent.remote(
                            agent_id=agent_id,
                            template_name=template_name,
                            data=init_data
                        )

                        if success:
                            print(f"Successfully added agent '{agent_id}' via frontend request.")

                            # 收集新 agent 的数据并更新快照
                            try:
                                new_agent_data = await _pod_manager.collect_single_agent_data.remote(agent_id)
                                if new_agent_data:
                                    _agents_snapshot[agent_id] = new_agent_data

                                    # 广播更新后的数据给所有前端
                                    payload = json.dumps({
                                        "type": "agent_added",
                                        "tick": _snapshot_tick,
                                        "agent_id": agent_id,
                                        "data": new_agent_data,
                                    }, ensure_ascii=False, default=str)
                                    await manager.broadcast(payload)
                            except Exception as e:
                                print(f"Warning: Failed to collect data for new agent '{agent_id}': {e}")

                            await websocket.send_text(json.dumps({
                                "type": "add_agent_response",
                                "success": True,
                                "agent_id": agent_id
                            }))
                        else:
                            await websocket.send_text(json.dumps({
                                "type": "add_agent_response",
                                "success": False,
                                "error": f"Failed to add agent '{agent_id}'"
                            }))
                    except Exception as e:
                        print(f"Error adding agent '{agent_id}': {e}")
                        await websocket.send_text(json.dumps({
                            "type": "add_agent_response",
                            "success": False,
                            "error": str(e)
                        }))

            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── 原有 profile 端点 ──────────────────────────────────────────────────────────

@app.get("/api/agents/ids", response_model=List[str], summary="Get all agent identifiers")
async def get_all_agent_ids() -> List[str]:
    global redis_pool
    if redis_pool is None:
        raise HTTPException(status_code=500, detail="Redis pool is not initialized.")
    redis_client = aioredis.Redis(connection_pool=redis_pool)
    agent_ids: List[str] = []
    async for key in redis_client.scan_iter("*:profile"):
        agent_id = key.split(":")[0]
        agent_ids.append(agent_id)
    return agent_ids


@app.get("/api/agents/{agent_id}", summary="Get a single agent profile")
async def get_agent_profile(agent_id: str) -> Dict[str, str]:
    global redis_pool
    if redis_pool is None:
        raise HTTPException(status_code=500, detail="Redis pool is not initialized.")
    redis_client = aioredis.Redis(connection_pool=redis_pool)
    profile_key = f"{agent_id}:profile"
    if not await redis_client.exists(profile_key):
        raise HTTPException(status_code=404, detail=f"Agent with id '{agent_id}' not found.")
    return await redis_client.hgetall(profile_key)


@app.post("/api/agents/profiles_by_ids", summary="Get agent profiles by identifier list")
async def get_agent_profiles_by_ids(id_list: AgentIdList) -> Dict[str, Dict[str, str]]:
    global redis_pool
    if redis_pool is None:
        raise HTTPException(status_code=500, detail="Redis pool is not initialized.")
    redis_client = aioredis.Redis(connection_pool=redis_pool)
    agent_profiles: Dict[str, Dict[str, str]] = {}
    async with redis_client.pipeline() as pipe:
        for agent_id in id_list.agent_ids:
            pipe.hgetall(f"{agent_id}:profile")
        results = await pipe.execute()
    for agent_id, profile_data in zip(id_list.agent_ids, results):
        if profile_data:
            agent_profiles[agent_id] = profile_data
    return agent_profiles


# ── Agent 状态端点 ─────────────────────────────────────────────────────────────

@app.get("/api/state/snapshot", summary="Get latest agents state snapshot")
async def get_snapshot() -> Dict[str, Any]:
    """返回最新一次 tick 的所有 agent 状态快照。"""
    return {"tick": _snapshot_tick, "data": _agents_snapshot}


@app.get("/api/state/{agent_id}", summary="Get single agent state")
async def get_agent_state(agent_id: str) -> Dict[str, Any]:
    """返回指定 agent 的最新状态。"""
    if agent_id not in _agents_snapshot:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not in snapshot.")
    return _agents_snapshot[agent_id]


# ── 供仿真循环调用的广播函数 ───────────────────────────────────────────────────

async def broadcast_tick_data(tick: int, agents_data: Dict[str, Any]) -> None:
    """
    更新内存快照并通过 WebSocket 广播给所有前端连接。

    Args:
        tick: 当前 tick 编号。
        agents_data: collect_agents_data() 返回的字典。
    """
    global _agents_snapshot, _snapshot_tick
    _agents_snapshot = agents_data
    _snapshot_tick = tick

    payload = json.dumps({
        "type": "tick_update",
        "tick": tick,
        "data": agents_data,
    }, ensure_ascii=False, default=str)
    await manager.broadcast(payload)


# ── 服务器启动 ─────────────────────────────────────────────────────────────────

def start_server(config: Dict[str, Any]) -> None:
    """
    Launch the FastAPI server with the provided configuration.

    Args:
        config: Settings dict containing host, port, and optional redis_settings.
    """
    global redis_pool, api_config
    api_config = config

    # 处理静态文件挂载
    static_mounts = config.get("static_mounts", {})
    for path, directory in static_mounts.items():
        if os.path.exists(directory):
            app.mount(path, StaticFiles(directory=directory), name=os.path.basename(directory))
            print(f"Mounted static directory '{directory}' at '{path}'")

    redis_settings = config.get("redis_settings", {})
    if redis_settings:
        if "decode_responses" not in redis_settings:
            redis_settings["decode_responses"] = True
        redis_pool = aioredis.ConnectionPool(**redis_settings)

    uvicorn.run(
        "agentkernel_distributed.mas.interface.server:app",
        host=config.get("host", "127.0.0.1"),
        port=config.get("port", 8000),
        log_level="info",
    )
