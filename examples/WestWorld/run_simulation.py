"""西部世界正式仿真入口（M3 版：Recorder 联动）。

用法（仓库根目录，需 Redis 在线）：
    PYTHONPATH=$PWD:$PWD/packages/agentkernel-distributed \\
        python -m examples.WestWorld.run_simulation

支持环境变量：
    WW_MAX_TICKS=5  覆盖 configs 里的 max_ticks（方便快速冒烟）
    WW_RUN_DIR=/tmp/west-world-run  指定本次运行日志目录
    WW_OUTPUT_DIR=/tmp/west-world-runs  覆盖默认日志根目录
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(PROJECT_PATH, "..", ".."))
PACKAGES_ROOT = os.path.join(PROJECT_ROOT, "packages")


def _ensure_import_paths() -> str:
    python_paths = [PROJECT_ROOT]
    if os.path.exists(PACKAGES_ROOT):
        for package in os.listdir(PACKAGES_ROOT):
            package_path = os.path.join(PACKAGES_ROOT, package)
            if os.path.isdir(package_path):
                python_paths.append(package_path)

    for path in reversed(python_paths):
        if path not in sys.path:
            sys.path.insert(0, path)

    current_pythonpath = os.environ.get("PYTHONPATH")
    if current_pythonpath:
        python_paths.append(current_pythonpath)
    return os.pathsep.join(python_paths)


RUNTIME_PYTHONPATH = _ensure_import_paths()
os.environ["MAS_PROJECT_ABS_PATH"] = PROJECT_PATH
os.environ["MAS_PROJECT_REL_PATH"] = "examples.WestWorld"
os.environ["MAS_EVENT_LOG_DIR"] = PROJECT_PATH

import ray
import yaml as _yaml

from agentkernel_distributed.mas.builder import Builder
from agentkernel_distributed.mas.interface.server import broadcast_tick_data, start_server
import agentkernel_distributed.mas.interface.server as server_module
from agentkernel_distributed.toolkit.logger import get_logger

from examples.WestWorld.registry import RESOURCES_MAPS
from examples.WestWorld.simulation_logging import SimulationLogArchive

logger = get_logger(__name__)
TICK_DURATION = 0.1  # seconds per tick for smoke test

# 活跃地点 ID 列表（从 locations.yaml 加载）
_ACTIVE_LIDS = sorted(
    loc["id"] for loc in _yaml.safe_load(
        open(os.path.join(PROJECT_PATH, "data/map/locations.yaml"), encoding="utf-8"))
    if loc.get("active")
)
_AGENT_IDS = sorted(
    json.loads(line)["id"]
    for line in Path(PROJECT_PATH, "data/agents/states_sim.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
)


async def _collect_agent_states(pod_manager) -> Dict[str, Dict[str, Any]]:
    states: Dict[str, Dict[str, Any]] = {}
    for agent_id in _AGENT_IDS:
        state = await pod_manager.run_agent_method.remote(agent_id, "state", "get_state")
        states[agent_id] = state or {}
    return states


async def _collect_scene_snapshots(pod_manager, internal: bool) -> Dict[str, Dict[str, Any]]:
    snapshots: Dict[str, Dict[str, Any]] = {}
    for location_id in _ACTIVE_LIDS:
        snapshots[location_id] = await pod_manager.run_environment.remote(
            f"scene_{location_id}", "snapshot",
            internal, internal, internal,
        )
    return snapshots


async def _collect_world_objects(pod_manager) -> Dict[str, Any]:
    any_scene = _ACTIVE_LIDS[0]
    return await pod_manager.run_environment.remote(
        f"scene_{any_scene}", "world_snapshot",
    )


async def _synchronize_initial_presence(pod_manager, agent_states: Dict[str, Dict[str, Any]]) -> None:
    by_location: Dict[str, list[str]] = {location_id: [] for location_id in _ACTIVE_LIDS}
    for agent_id, state in agent_states.items():
        location = state.get("location")
        if location not in by_location:
            raise ValueError(f"agent {agent_id} has non-active or unknown initial location: {location}")
        by_location[location].append(agent_id)
    for location_id, agent_ids in by_location.items():
        await pod_manager.run_environment.remote(
            f"scene_{location_id}", "set_present_agents", agent_ids,
        )


def _build_frontend_payload(
    *,
    tick: int,
    agents: Dict[str, Dict[str, Any]],
    scenes: Dict[str, Dict[str, Any]],
    world_objects: Dict[str, Any],
    timings: Dict[str, float] | None = None,
    consistency: Dict[str, Any] | None = None,
    phase: str = "tick",
) -> Dict[str, Any]:
    return {
        "agents": agents,
        "scenes": scenes,
        "world_objects": world_objects,
        "phase": phase,
        "tick": tick,
        "timings": timings or {},
        "consistency": consistency or {},
    }


def _start_api_server(pod_manager, tick_start_event: threading.Event) -> Dict[str, Any]:
    server_module._tick_start_event = tick_start_event
    server_module._pod_manager = pod_manager

    server_config = {
        "host": "0.0.0.0",
        "port": 8000,
        "redis_settings": {
            "host": "localhost",
            "port": 6379,
            "db": 0,
        },
        "static_mounts": {
            "/frontend": os.path.join(PROJECT_PATH, "frontend"),
            "/map_total": os.path.join(PROJECT_PATH, "map_total"),
            "/data": os.path.join(PROJECT_PATH, "data"),
        },
    }
    server_thread = threading.Thread(
        target=start_server,
        args=[server_config],
        daemon=True,
    )
    server_thread.start()
    return server_config


async def _wait_for_frontend_tick(tick_start_event: threading.Event, tick: int) -> None:
    logger.info("Waiting for frontend signal to start tick %s...", tick)
    server_module._waiting_for_tick = True
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, tick_start_event.wait)
    tick_start_event.clear()
    server_module._waiting_for_tick = False


async def main() -> None:
    configured_ticks = _yaml.safe_load(
        Path(PROJECT_PATH, "configs/simulation_config.yaml").read_text(encoding="utf-8")
    )["simulation"]["max_ticks"]
    max_ticks = int(os.environ.get("WW_MAX_TICKS", "") or configured_ticks)
    archive = SimulationLogArchive(PROJECT_PATH, max_ticks, _AGENT_IDS, _ACTIVE_LIDS)
    pod_manager = None
    tick_start_event = threading.Event()
    logger.info("Simulation starting: max_ticks=%s, active_lids=%s", max_ticks, _ACTIVE_LIDS)
    try:
        init_started = time.perf_counter()
        if not ray.is_initialized():
            ray.init(
                runtime_env={
                    "working_dir": PROJECT_PATH,
                    "env_vars": {
                        "PYTHONPATH": RUNTIME_PYTHONPATH,
                    },
                    "excludes": [
                        "output/",
                        "output/**",
                        "logs/",
                        "logs/**",
                        "__pycache__/",
                        "**/__pycache__/**",
                    ],
                },
                _system_config={"memory_monitor_refresh_ms": 0},
            )
        builder = Builder(PROJECT_PATH, RESOURCES_MAPS, configs_dirname="configs")
        pod_manager, system = await builder.init()
        archive.record_event("kernel_initialized", duration_seconds=time.perf_counter() - init_started)
        initial_agents = await _collect_agent_states(pod_manager)
        await _synchronize_initial_presence(pod_manager, initial_agents)
        initial_public_scenes = await _collect_scene_snapshots(pod_manager, internal=False)
        initial_internal_scenes = await _collect_scene_snapshots(pod_manager, internal=True)
        initial_world_objects = await _collect_world_objects(pod_manager)
        initial_consistency = archive.record_tick(
            -1, initial_agents, initial_public_scenes, initial_internal_scenes,
            {"initialization": time.perf_counter() - init_started}, [],
            phase="initial", count_completed_tick=False,
        )
        archive.record_world_objects(-1, initial_world_objects)
        archive.record_event("initial_snapshot_recorded", tick=-1, consistency=initial_consistency)

        await broadcast_tick_data(
            -1,
            _build_frontend_payload(
                tick=-1,
                agents=initial_agents,
                scenes=initial_public_scenes,
                world_objects=initial_world_objects,
                timings={"initialization": time.perf_counter() - init_started},
                consistency=initial_consistency,
                phase="initial",
            ),
        )
        server_config = _start_api_server(pod_manager, tick_start_event)
        logger.info("API server started at http://%s:%s/frontend/index.html", server_config["host"], server_config["port"])

        for i in range(max_ticks):
            tick = await system.run("timer", "get_tick")
            await _wait_for_frontend_tick(tick_start_event, tick)
            logger.info("===== tick %s =====", tick)
            archive.record_event("tick_started", tick=tick)
            timings: Dict[str, float] = {}

            started = time.perf_counter()
            await pod_manager.step_agent.remote()
            timings["agent_step"] = time.perf_counter() - started
            archive.record_model_attempts(
                tick, await pod_manager.drain_model_attempt_traces.remote()
            )
            archive.record_event("agent_step_completed", tick=tick, duration_seconds=timings["agent_step"])

            started = time.perf_counter()
            await system.run("messager", "dispatch_messages")
            timings["message_dispatch"] = time.perf_counter() - started
            archive.record_event("message_dispatch_completed", tick=tick, duration_seconds=timings["message_dispatch"])

            # scene execute 已移入 WestWorldPodManager.step_agent（tick_update 栅栏）
            scene_errors: list = []
            timings["scene_updates"] = 0.0
            archive.record_model_attempts(
                tick, await pod_manager.drain_model_attempt_traces.remote()
            )

            started = time.perf_counter()
            agent_states = await _collect_agent_states(pod_manager)
            public_scenes = await _collect_scene_snapshots(pod_manager, internal=False)
            internal_scenes = await _collect_scene_snapshots(pod_manager, internal=True)
            world_objects = await _collect_world_objects(pod_manager)
            timings["snapshot_collection"] = time.perf_counter() - started
            consistency = archive.record_tick(
                tick, agent_states, public_scenes, internal_scenes, timings, scene_errors,
            )
            archive.record_world_objects(tick, world_objects)
            archive.record_event("tick_snapshot_recorded", tick=tick, consistency=consistency)

            await broadcast_tick_data(
                tick,
                _build_frontend_payload(
                    tick=tick,
                    agents=agent_states,
                    scenes=public_scenes,
                    world_objects=world_objects,
                    timings=timings,
                    consistency=consistency,
                ),
            )

            await system.run("timer", "add_tick", duration_seconds=TICK_DURATION)
            archive.record_event("tick_completed", tick=tick)
        server_module._waiting_for_tick = False
        await server_module.manager.broadcast(json.dumps({
            "type": "simulation_finished",
            "tick": await system.run("timer", "get_tick"),
        }, ensure_ascii=False))
    except BaseException as exc:
        archive.fail(exc)
        raise
    finally:
        server_module._waiting_for_tick = False
        close_error = None
        try:
            if pod_manager is not None:
                await pod_manager.close.remote()
                archive.record_event("kernel_shutdown_completed")
        except BaseException as exc:
            close_error = exc
            archive.record_event("kernel_shutdown_failed", error=f"{type(exc).__name__}: {exc}")
        finally:
            ray.shutdown()
        if archive.manifest["status"] == "running":
            if close_error is not None:
                archive.fail(close_error)
                raise close_error
            archive.complete()
        logger.info("Simulation log archived at %s", archive.run_dir)


if __name__ == "__main__":
    asyncio.run(main())
