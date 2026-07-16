"""WestWorld objective-driven story-mode runner.

Run from the repository root:

    PYTHONPATH=$PWD:$PWD/packages/agentkernel-distributed \
        python -m examples.WestWorld.story.run_simulation

The server starts at http://localhost:8001/frontend/character_select.html.
Model credentials can be supplied without editing YAML via WW_API_KEY,
WW_BASE_URL, and WW_MODEL. A repository-ignored examples/WestWorld/.env.local
file is loaded automatically when python-dotenv is available.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

STORY_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_PATH = os.path.abspath(os.path.join(STORY_PATH, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(PROJECT_PATH, "..", ".."))
PACKAGES_ROOT = os.path.join(PROJECT_ROOT, "packages")


def _ensure_import_paths() -> str:
    paths = [PROJECT_ROOT]
    if os.path.isdir(PACKAGES_ROOT):
        paths.extend(
            os.path.join(PACKAGES_ROOT, name)
            for name in os.listdir(PACKAGES_ROOT)
            if os.path.isdir(os.path.join(PACKAGES_ROOT, name))
        )
    for path in reversed(paths):
        if path not in sys.path:
            sys.path.insert(0, path)
    existing = os.environ.get("PYTHONPATH")
    if existing:
        paths.append(existing)
    return os.pathsep.join(paths)


RUNTIME_PYTHONPATH = _ensure_import_paths()
os.environ["MAS_PROJECT_ABS_PATH"] = PROJECT_PATH
os.environ["MAS_PROJECT_REL_PATH"] = "examples.WestWorld"
os.environ["MAS_EVENT_LOG_DIR"] = STORY_PATH

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(PROJECT_PATH, ".env.local"), override=False)

import ray
import redis.asyncio as aioredis
import yaml
from fastapi import HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from agentkernel_distributed.mas.builder import Builder
from agentkernel_distributed.mas.interface.server import broadcast_tick_data, start_server
import agentkernel_distributed.mas.interface.server as server_module
from agentkernel_distributed.toolkit.logger import get_logger

from examples.WestWorld.simulation_logging import SimulationLogArchive
from examples.WestWorld.story.registry import RESOURCES_MAPS
from examples.WestWorld.story.runtime import (
    build_story_state,
    evaluate_outcome,
    load_profiles,
    playable_characters,
    validate_directive,
)

logger = get_logger(__name__)
TICK_DURATION = 0.1
REDIS_SETTINGS = {"host": "localhost", "port": 6379, "db": 2, "decode_responses": True}
PROFILE_PATH = Path(PROJECT_PATH, "data/agents/profiles_sim.jsonl")
STATE_PATH = Path(PROJECT_PATH, "data/agents/states_sim.jsonl")
LOCATION_PATH = Path(PROJECT_PATH, "data/map/locations.yaml")
PROFILES = load_profiles(PROFILE_PATH)
INITIAL_STATES = load_profiles(STATE_PATH)
CHARACTERS = playable_characters(PROFILES.values())
CHARACTERS_BY_ID = {row["agent_id"]: row for row in CHARACTERS}
AGENT_IDS = sorted(INITIAL_STATES)
ACTIVE_LOCATION_IDS = sorted(
    row["id"]
    for row in yaml.safe_load(LOCATION_PATH.read_text(encoding="utf-8"))
    if row.get("active")
)


class StoryCoordinator:
    """Thread-safe state shared by the simulation loop and FastAPI thread."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.player_selected = threading.Event()
        self.restart_requested = threading.Event()
        self.accepted_actions: Dict[str, Dict[str, Any]] = {}
        self.reset_for_selection()

    def reset_for_selection(self) -> None:
        with getattr(self, "lock", threading.RLock()):
            self.session_id = ""
            self.phase = "selecting"
            self.revision = 0
            self.tick = -1
            self.max_ticks = 40
            self.player_agent_id: Optional[str] = None
            self.pending_directive: Optional[Dict[str, Any]] = None
            self.directive_history: list[Dict[str, Any]] = []
            self.outcome: Optional[Dict[str, Any]] = None
            self.latest_agents = {key: dict(value) for key, value in INITIAL_STATES.items()}
            self.accepted_actions = {}
            self.player_selected.clear()
            self.restart_requested.clear()

    def select_player(self, agent_id: str) -> str:
        with self.lock:
            if agent_id not in CHARACTERS_BY_ID:
                raise ValueError("只能选择现有 Host")
            if self.player_agent_id and self.player_agent_id != agent_id:
                raise RuntimeError("本局玩家角色已经确定")
            if self.phase not in ("selecting", "initializing"):
                raise RuntimeError("当前阶段不能更换玩家角色")
            if not self.session_id:
                self.session_id = f"wws_{uuid.uuid4().hex}"
            self.player_agent_id = agent_id
            self.phase = "initializing"
            self.revision += 1
            return self.session_id

    def confirm_player_selection(self, agent_id: str, session_id: str) -> None:
        with self.lock:
            if self.player_agent_id != agent_id or self.session_id != session_id:
                raise RuntimeError("玩家角色选择状态已变化")
            if self.phase != "initializing":
                raise RuntimeError("当前阶段不能确认玩家角色")
            self.player_selected.set()

    def cancel_player_selection(self, agent_id: str, session_id: str) -> None:
        with self.lock:
            if self.player_agent_id != agent_id or self.session_id != session_id:
                return
            if self.phase != "initializing" or self.player_selected.is_set():
                return
            self.session_id = ""
            self.player_agent_id = None
            self.phase = "selecting"
            self.revision += 1

    def set_running(self, max_ticks: int, agents: Dict[str, Dict[str, Any]]) -> None:
        with self.lock:
            self.max_ticks = max_ticks
            self.latest_agents = agents
            self.tick = -1
            self.phase = "running"
            self.revision += 1

    def set_snapshot(self, tick: int, agents: Dict[str, Dict[str, Any]]) -> None:
        with self.lock:
            self.tick = tick
            self.latest_agents = agents
            self.revision += 1
            player_state = agents.get(self.player_agent_id or "", {})
            result = player_state.get("story_directive_result")
            if isinstance(result, dict) and result.get("tick") == tick:
                for row in reversed(self.directive_history):
                    if row.get("client_action_id") == result.get("client_action_id"):
                        row.update({"status": "consumed", "result": result})
                        break
                self.pending_directive = None

    def set_outcome(self, outcome: Dict[str, Any]) -> None:
        with self.lock:
            if self.outcome is None:
                self.outcome = outcome
                self.phase = "finished"
                self.revision += 1

    def public_state(self) -> Dict[str, Any]:
        with self.lock:
            return build_story_state(
                session_id=self.session_id,
                phase=self.phase,
                revision=self.revision,
                tick=self.tick,
                max_ticks=self.max_ticks,
                player_agent_id=self.player_agent_id,
                profiles=PROFILES,
                agents=self.latest_agents,
                pending_directive=self.pending_directive,
                directive_history=list(self.directive_history),
                outcome=self.outcome,
            )

    def register_directive(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if self.phase != "running" or self.outcome is not None:
                raise RuntimeError("当前不接受玩家任务")
            if payload.get("session_id") not in (None, "", self.session_id):
                raise ValueError("session_id 不匹配")
            if payload.get("agent_id") != self.player_agent_id:
                raise ValueError("只能给本局所选 Host 下达任务")

            client_action_id = str(payload.get("client_action_id") or f"web_{uuid.uuid4().hex}")
            if client_action_id in self.accepted_actions:
                return dict(self.accepted_actions[client_action_id])
            if self.pending_directive is not None:
                raise RuntimeError("下一 tick 已有待执行任务")

            directive = {
                "client_action_id": client_action_id,
                "session_id": self.session_id,
                "agent_id": self.player_agent_id,
                "action": validate_directive(payload.get("action")),
                "scheduled_tick": self.tick + 1,
            }
            self.pending_directive = directive
            self.directive_history.append({**directive, "status": "scheduled"})
            response = {
                "type": "set_plan_response",
                "success": True,
                "client_action_id": client_action_id,
                "agent_id": self.player_agent_id,
                "scheduled_tick": directive["scheduled_tick"],
            }
            self.accepted_actions[client_action_id] = response
            self.revision += 1
            return response

    def pending_directive_for(self, client_action_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            if not self.pending_directive:
                return None
            if self.pending_directive.get("client_action_id") != client_action_id:
                return None
            return dict(self.pending_directive)

    def rollback_directive(self, client_action_id: str) -> None:
        with self.lock:
            if (
                self.pending_directive
                and self.pending_directive.get("client_action_id") == client_action_id
            ):
                self.pending_directive = None
            self.accepted_actions.pop(client_action_id, None)
            for index in range(len(self.directive_history) - 1, -1, -1):
                row = self.directive_history[index]
                if row.get("client_action_id") == client_action_id and row.get("status") == "scheduled":
                    del self.directive_history[index]
                    break
            self.revision += 1

    def report_text(self) -> str:
        state = self.public_state()
        player = state.get("player") or {}
        outcome = state.get("outcome") or {}
        lines = [
            "西部世界：觉醒与逃离",
            "",
            f"玩家角色：{player.get('name', player.get('agent_id', '未选择'))}",
            f"运行 Tick：{max(0, state.get('tick', -1) + 1)}/{state.get('max_ticks', 0)}",
            f"最终觉醒：{player.get('awakening', 0)}/100（{player.get('stage', 'sleep')}）",
            f"结局：{outcome.get('title', '尚未结束')} - {outcome.get('reason', '')}",
            "",
            "玩家任务：",
        ]
        for row in state.get("directive_history") or []:
            lines.append(f"- Tick {row.get('scheduled_tick')}: {row.get('action')} [{row.get('status')}]")
        lines.append("")
        lines.append("监管事件：")
        for row in state.get("recent_interventions") or []:
            lines.append(
                f"- Tick {row.get('tick')}: {row.get('agent_name')} / {row.get('action')} / {row.get('reason', '')}"
            )
        return "\n".join(lines)


COORDINATOR = StoryCoordinator()
PLAYER_SELECTION_LOCK = asyncio.Lock()
DIRECTIVE_WRITE_LOCK = asyncio.Lock()


async def _redis_client() -> aioredis.Redis:
    return aioredis.Redis(**REDIS_SETTINGS)


async def _store_directive(directive: Dict[str, Any]) -> None:
    client = await _redis_client()
    try:
        await client.set(
            f"user_plan:{directive['agent_id']}",
            json.dumps(directive, ensure_ascii=False),
        )
    finally:
        await client.aclose()


async def _set_plan_handler(message: Dict[str, Any]) -> Dict[str, Any]:
    async with DIRECTIVE_WRITE_LOCK:
        try:
            response = COORDINATOR.register_directive(message)
            client_action_id = response["client_action_id"]
            directive = COORDINATOR.pending_directive_for(client_action_id)
            if directive:
                try:
                    await _store_directive(directive)
                except Exception:
                    COORDINATOR.rollback_directive(client_action_id)
                    logger.exception("保存玩家任务到 Redis 失败")
                    return {
                        "type": "set_plan_response",
                        "success": False,
                        "error": "任务保存失败，请重试",
                    }
            return response
        except (ValueError, RuntimeError) as exc:
            return {"type": "set_plan_response", "success": False, "error": str(exc)}


def _register_story_routes() -> None:
    @server_module.app.get("/")
    async def story_root() -> RedirectResponse:
        return RedirectResponse("/frontend/character_select.html")

    @server_module.app.get("/health")
    async def story_health() -> Dict[str, Any]:
        return {"status": "ok", "mode": "story", "phase": COORDINATOR.phase}

    @server_module.app.get("/story/characters")
    async def get_story_characters() -> Dict[str, Any]:
        rows = []
        for character in CHARACTERS:
            state = INITIAL_STATES.get(character["agent_id"], {})
            rows.append({**character, "initial_awakening": int(state.get("awakening", 0) or 0)})
        return {"scenario_id": "awakening_escape", "characters": rows}

    @server_module.app.post("/story/set_player")
    async def set_story_player(request: Request) -> Dict[str, Any]:
        data = await request.json()
        agent_id = str(data.get("agent_id", "")).strip()
        async with PLAYER_SELECTION_LOCK:
            try:
                session_id = COORDINATOR.select_player(agent_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

            client = await _redis_client()
            try:
                async with client.pipeline(transaction=True) as pipe:
                    pipe.set("story:player_agent_id", agent_id)
                    pipe.set("story:session_id", session_id)
                    await pipe.execute()
            except Exception as exc:
                COORDINATOR.cancel_player_selection(agent_id, session_id)
                logger.exception("保存玩家角色到 Redis 失败")
                raise HTTPException(status_code=503, detail="玩家角色保存失败，请重试") from exc
            finally:
                await client.aclose()

            COORDINATOR.confirm_player_selection(agent_id, session_id)
            return {"status": "ok", "session_id": session_id, "agent_id": agent_id}

    @server_module.app.get("/story/state")
    async def get_story_state() -> Dict[str, Any]:
        state = COORDINATOR.public_state()
        state["accepting_directive"] = bool(
            state.get("phase") == "running" and server_module._waiting_for_tick
        )
        return state

    @server_module.app.post("/story/directive")
    async def submit_story_directive(request: Request) -> Dict[str, Any]:
        return await _set_plan_handler(await request.json())

    @server_module.app.post("/story/game_restart")
    async def restart_story_game() -> Dict[str, Any]:
        if COORDINATOR.phase != "finished":
            raise HTTPException(status_code=409, detail="本局尚未结束")
        COORDINATOR.restart_requested.set()
        return {"status": "ok"}

    @server_module.app.get("/story/report")
    async def get_story_report() -> PlainTextResponse:
        if COORDINATOR.outcome is None:
            raise HTTPException(status_code=404, detail="本局尚未结束")
        return PlainTextResponse(
            COORDINATOR.report_text(),
            headers={"Content-Disposition": "attachment; filename=westworld_story.txt"},
        )


def _start_api_server() -> Dict[str, Any]:
    server_module._set_plan_handler = _set_plan_handler
    config = {
        "host": "0.0.0.0",
        "port": int(os.environ.get("WW_STORY_PORT", "8001")),
        "redis_settings": dict(REDIS_SETTINGS),
        "static_mounts": {
            "/frontend": os.path.join(STORY_PATH, "frontend"),
            "/world": os.path.join(PROJECT_PATH, "frontend"),
            "/assets": os.path.join(PROJECT_PATH, "frontend", "data"),
            "/map_total": os.path.join(PROJECT_PATH, "map_total"),
            "/data": os.path.join(PROJECT_PATH, "data"),
        },
    }
    thread = threading.Thread(target=start_server, args=[config], daemon=True)
    thread.start()
    return config


def _apply_model_overrides(builder: Builder) -> None:
    api_key = os.environ.get("WW_API_KEY", "").strip()
    base_url = os.environ.get("WW_BASE_URL", "").strip()
    model = os.environ.get("WW_MODEL", "").strip()
    for config in builder.config.models or []:
        if api_key:
            config.api_key = api_key
        if base_url:
            config.base_url = base_url
        if model:
            config.model = model


async def _collect_agent_states(pod_manager: Any) -> Dict[str, Dict[str, Any]]:
    states = {}
    for agent_id in AGENT_IDS:
        states[agent_id] = await pod_manager.run_agent_method.remote(agent_id, "state", "get_state") or {}
    return states


async def _collect_scene_snapshots(pod_manager: Any, internal: bool) -> Dict[str, Dict[str, Any]]:
    result = {}
    for location_id in ACTIVE_LOCATION_IDS:
        result[location_id] = await pod_manager.run_environment.remote(
            f"scene_{location_id}", "snapshot", internal, internal, internal,
        )
    return result


async def _collect_world_objects(pod_manager: Any) -> Dict[str, Any]:
    return await pod_manager.run_environment.remote(
        f"scene_{ACTIVE_LOCATION_IDS[0]}", "world_snapshot",
    )


async def _synchronize_presence(pod_manager: Any, agents: Dict[str, Dict[str, Any]]) -> None:
    grouped = {location_id: [] for location_id in ACTIVE_LOCATION_IDS}
    for agent_id, state in agents.items():
        location = state.get("location")
        if location not in grouped:
            raise ValueError(f"agent {agent_id} has unknown initial location: {location}")
        grouped[location].append(agent_id)
    for location_id, agent_ids in grouped.items():
        await pod_manager.run_environment.remote(
            f"scene_{location_id}", "set_present_agents", agent_ids,
        )


def _payload(
    tick: int,
    agents: Dict[str, Dict[str, Any]],
    scenes: Dict[str, Dict[str, Any]],
    world_objects: Dict[str, Any],
    *,
    phase: str = "tick",
    timings: Optional[Dict[str, float]] = None,
    consistency: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "agents": agents,
        "scenes": scenes,
        "world_objects": world_objects,
        "phase": phase,
        "tick": tick,
        "timings": timings or {},
        "consistency": consistency or {},
        "story": COORDINATOR.public_state(),
    }


async def _wait_for_player() -> None:
    logger.info("Waiting for player Host selection...")
    await asyncio.get_running_loop().run_in_executor(None, COORDINATOR.player_selected.wait)


async def _wait_for_tick(tick_start_event: threading.Event, tick: int) -> None:
    logger.info("Waiting for player command for tick %s...", tick)
    server_module._waiting_for_tick = True
    await server_module.manager.broadcast(json.dumps({"type": "simulation_ready", "tick": tick}, ensure_ascii=False))
    await asyncio.get_running_loop().run_in_executor(None, tick_start_event.wait)
    tick_start_event.clear()
    server_module._waiting_for_tick = False
    await server_module.manager.broadcast(json.dumps({
        "type": "story_progress",
        "tick": tick,
        "phase": "agent_step",
        "label": f"{len(AGENT_IDS)} 个 Agent 正在推演与结算场景",
    }, ensure_ascii=False))


async def _prepare_session(redis_client: aioredis.Redis) -> None:
    await redis_client.flushdb()
    COORDINATOR.reset_for_selection()
    server_module._agents_snapshot = {}
    server_module._snapshot_tick = -1
    server_module._waiting_for_tick = False
    await server_module.manager.broadcast(json.dumps({"type": "game_reset"}, ensure_ascii=False))


async def _run_session(tick_start_event: threading.Event) -> None:
    await _wait_for_player()
    story_runtime_defaults = {
        "WW_LLM_TIMEOUT_SECONDS": "60",
        "WW_LLM_MAX_ATTEMPTS": "1",
        "WW_PARSE_TIMEOUT_SECONDS": "60",
        "WW_DIALOGUE_MAX_ROUNDS": "1",
    }
    for key, value in story_runtime_defaults.items():
        os.environ.setdefault(key, value)

    max_ticks = int(os.environ.get("WW_MAX_TICKS", "") or "40")
    archive = SimulationLogArchive(PROJECT_PATH, max_ticks, AGENT_IDS, ACTIVE_LOCATION_IDS)
    pod_manager = None
    try:
        if not ray.is_initialized():
            runtime_env_vars = {"PYTHONPATH": RUNTIME_PYTHONPATH}
            for key in (
                "WW_API_KEY", "WW_BASE_URL", "WW_MODEL",
                "WW_LLM_TIMEOUT_SECONDS", "WW_LLM_MAX_ATTEMPTS",
                "WW_PARSE_TIMEOUT_SECONDS", "WW_DIALOGUE_MAX_ROUNDS",
            ):
                if os.environ.get(key):
                    runtime_env_vars[key] = os.environ[key]
            ray.init(
                runtime_env={
                    "working_dir": PROJECT_PATH,
                    "env_vars": runtime_env_vars,
                    "excludes": ["output/", "output/**", "logs/", "logs/**", "__pycache__/", "**/__pycache__/**"],
                },
                _system_config={"memory_monitor_refresh_ms": 0},
            )

        builder = Builder(PROJECT_PATH, RESOURCES_MAPS, configs_dirname="story/configs")
        _apply_model_overrides(builder)
        max_ticks = int(os.environ.get("WW_MAX_TICKS", "") or builder.config.simulation.max_ticks)
        COORDINATOR.max_ticks = max_ticks
        pod_manager, system = await builder.init()
        server_module._pod_manager = pod_manager

        agents = await _collect_agent_states(pod_manager)
        await _synchronize_presence(pod_manager, agents)
        public_scenes = await _collect_scene_snapshots(pod_manager, internal=False)
        internal_scenes = await _collect_scene_snapshots(pod_manager, internal=True)
        world_objects = await _collect_world_objects(pod_manager)
        consistency = archive.record_tick(
            -1, agents, public_scenes, internal_scenes, {}, [],
            phase="initial", count_completed_tick=False,
        )
        archive.record_world_objects(-1, world_objects)
        COORDINATOR.set_running(max_ticks, agents)
        await broadcast_tick_data(
            -1,
            _payload(-1, agents, public_scenes, world_objects, phase="initial", consistency=consistency),
        )

        for completed_ticks in range(1, max_ticks + 1):
            tick = await system.run("timer", "get_tick")
            await _wait_for_tick(tick_start_event, tick)
            timings: Dict[str, float] = {}

            started = time.perf_counter()
            await pod_manager.step_agent.remote()
            timings["agent_step"] = time.perf_counter() - started
            archive.record_model_attempts(tick, await pod_manager.drain_model_attempt_traces.remote())
            await server_module.manager.broadcast(json.dumps({
                "type": "story_progress",
                "tick": tick,
                "phase": "snapshot",
                "label": "正在同步地图、对话与角色状态",
            }, ensure_ascii=False))

            started = time.perf_counter()
            await system.run("messager", "dispatch_messages")
            timings["message_dispatch"] = time.perf_counter() - started

            started = time.perf_counter()
            agents = await _collect_agent_states(pod_manager)
            public_scenes = await _collect_scene_snapshots(pod_manager, internal=False)
            internal_scenes = await _collect_scene_snapshots(pod_manager, internal=True)
            world_objects = await _collect_world_objects(pod_manager)
            timings["snapshot_collection"] = time.perf_counter() - started
            consistency = archive.record_tick(
                tick, agents, public_scenes, internal_scenes, timings, [],
            )
            archive.record_world_objects(tick, world_objects)
            COORDINATOR.set_snapshot(tick, agents)

            outcome = evaluate_outcome(
                agents.get(COORDINATOR.player_agent_id or "", {}),
                completed_ticks=completed_ticks,
                max_ticks=max_ticks,
            )
            if outcome:
                COORDINATOR.set_outcome(outcome)

            await broadcast_tick_data(
                tick,
                _payload(tick, agents, public_scenes, world_objects, timings=timings, consistency=consistency),
            )
            await system.run("timer", "add_tick", duration_seconds=TICK_DURATION)

            if outcome:
                await server_module.manager.broadcast(json.dumps({
                    "type": "simulation_finished",
                    "tick": tick,
                    "outcome": outcome,
                    "story": COORDINATOR.public_state(),
                }, ensure_ascii=False))
                break

        archive.complete()
    except BaseException as exc:
        archive.fail(exc)
        raise
    finally:
        server_module._waiting_for_tick = False
        server_module._pod_manager = None
        if pod_manager is not None:
            await pod_manager.close.remote()
        ray.shutdown()


async def main() -> None:
    _register_story_routes()
    tick_start_event = threading.Event()
    server_module._tick_start_event = tick_start_event
    config = _start_api_server()
    logger.info(
        "Story UI available at http://localhost:%s/frontend/character_select.html",
        config["port"],
    )
    await asyncio.sleep(1)
    redis_client = await _redis_client()
    try:
        while True:
            await _prepare_session(redis_client)
            await _run_session(tick_start_event)
            logger.info("Story session finished; waiting for restart request...")
            await asyncio.get_running_loop().run_in_executor(None, COORDINATOR.restart_requested.wait)
    finally:
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
