'python -m examples.deduction.run_simulation'
# http://localhost:8000/frontend/index.html
import os
import sys
import signal

# Add project root and packages directory to Python path to allow running the script directly
project_path = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(project_path, "..", ".."))
packages_root = os.path.join(project_root, "packages")

if project_root not in sys.path:
    sys.path.insert(0, project_root)

if os.path.exists(packages_root):
    for package in os.listdir(packages_root):
        package_path = os.path.join(packages_root, package)
        if os.path.isdir(package_path) and package_path not in sys.path:
            sys.path.insert(0, package_path)

os.environ["MAS_PROJECT_ABS_PATH"] = project_path
os.environ["MAS_PROJECT_REL_PATH"] = "examples.deduction"
os.environ["MAS_EVENT_LOG_DIR"] = project_path
import asyncio
import threading
import ray
import time
from pathlib import Path
from agentkernel_distributed.mas.builder import Builder
from agentkernel_distributed.mas.interface.server import start_server, broadcast_tick_data, broadcast_branch_event
import agentkernel_distributed.mas.interface.server as server_module
from examples.deduction.registry import RESOURCES_MAPS
from agentkernel_distributed.toolkit.logger import get_logger
from examples.deduction.plugins.agent.plan.BasicPlanPlugin import BasicPlanPlugin

logger = get_logger(__name__)


def parse_tmx_locations(tmx_path: str) -> list:
    """Parse all location names from the location layer groups in the TMX file."""
    import xml.etree.ElementTree as ET
    tree = ET.parse(tmx_path)
    root = tree.getroot()

    locations = []
    # Find the top-level group with name="地点" (Locations)
    for top_group in root.findall("group"):
        if top_group.get("name") == "地点":
            # Traverse child groups (e.g., Grand View Garden, Ningguo Mansion, Rongguo Mansion, etc.)
            for sub_group in top_group.findall("group"):
                for layer in sub_group.findall("layer"):
                    name = layer.get("name")
                    if name:
                        locations.append(name)
            # Also collect layers directly under the location group
            for layer in top_group.findall("layer"):
                name = layer.get("name")
                if name:
                        locations.append(name)
    return locations

async def main():
    pod_manager = None
    system = None
    total_duration = 0
    cumulative_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    try:
        logger.info(f'【System】Project path set to {project_path}.')

        # ===== Parse map locations and inject into PlanPlugin =====
        tmx_path = os.path.join(project_path, "map", "sos.tmx")
        locations = parse_tmx_locations(tmx_path)
        BasicPlanPlugin.set_locations(locations)
        logger.info(f'【System】Loaded {len(locations)} locations from map.')

        # ===== Step1 : Initialize Ray =====
        pythonpath_root = os.path.abspath(os.path.join(project_path, "..", ".."))
        packages_root = os.path.join(pythonpath_root, "packages")

        python_paths = [pythonpath_root]
        if os.path.exists(packages_root):
            for package in os.listdir(packages_root):
                package_path = os.path.join(packages_root, package)
                if os.path.isdir(package_path):
                    python_paths.append(package_path)

        current_pythonpath = os.environ.get("PYTHONPATH", "")
        if current_pythonpath:
            python_paths.append(current_pythonpath)

        new_pythonpath = os.pathsep.join(python_paths)
        runtime_env = {
            'working_dir': project_path,
            'env_vars': {
                "MAS_EVENT_LOG_DIR": os.environ.get("MAS_EVENT_LOG_DIR", ""),
                "PYTHONPATH": new_pythonpath,
            },
            'excludes':[
                '*.pyc',
                '__pycache__',
                'docs',
                'info_extraction'
            ]
        }

        logger.info(f'【System】Init Ray with runtime env: {runtime_env}.')

        ray.init(runtime_env = runtime_env)

        logger.info(f'【System】Ray is initialized.')

        # ===== Step2 : initialize the bulder, start all the simulation components =====
        logger.info(f'【System】Initialize the builder...')

        sim_builder = Builder(
            project_path = project_path,
            resource_maps = RESOURCES_MAPS
        )

        logger.info(f'【System】Start all the simulation components...')

        pod_manager, system = await sim_builder.init()

        # ===== Start API Server (Background Thread) =====
        api_cfg = sim_builder.config.api_server if hasattr(sim_builder.config, "api_server") else {}
        server_config = {
            "host": getattr(api_cfg, "host", "0.0.0.0") if api_cfg else "0.0.0.0",
            "port": getattr(api_cfg, "port", 8000) if api_cfg else 8000,
            "redis_settings": {
                "host": "localhost",
                "port": 6379,
                "db": 0,
            },
            "static_mounts": {
                "/frontend": os.path.join(project_path, "frontend"),
                "/map": os.path.join(project_path, "map"),
                "/data": os.path.join(project_path, "data"),
            }
        }
        
        # Create a thread-safe event to wait for the frontend to send the command to start the next tick
        # Note: The server runs in an independent thread (independent event loop), so threading.Event must be used instead of asyncio.Event
        tick_start_event = threading.Event()
        # Pass the event object to the server module so it can set() it when a specific message is received via websocket
        import agentkernel_distributed.mas.interface.server as server_module
        server_module._tick_start_event = tick_start_event
        # Pass the pod_manager reference to the server module to support dynamically adding agents
        server_module._pod_manager = pod_manager

        # ── Story server launcher endpoint ────────────────────────────────────────
        import subprocess as _subprocess
        import socket as _socket
        import atexit as _atexit
        import errno as _errno
        _story_process = None
        _story_pid_file = os.path.join(project_root, ".story_server.pid")
        _story_launch_lock = asyncio.Lock()

        def _is_port_open(port, host="127.0.0.1", timeout=0.5):
            try:
                with _socket.create_connection((host, port), timeout=timeout):
                    return True
            except OSError:
                return False

        def _is_pid_alive(pid):
            if not pid or pid <= 0:
                return False
            try:
                os.kill(pid, 0)
                return True
            except OSError as exc:
                if exc.errno == _errno.ESRCH:
                    return False
                return True

        def _read_story_pid():
            if not os.path.exists(_story_pid_file):
                return None
            try:
                with open(_story_pid_file, "r", encoding="utf-8") as f:
                    return int(f.read().strip())
            except (OSError, ValueError):
                return None

        def _owned_story_running():
            nonlocal _story_process
            if _story_process is not None and _story_process.poll() is None:
                return True
            pid = _read_story_pid()
            return _is_pid_alive(pid)

        async def _wait_for_story_ready(timeout_seconds=30.0):
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                if _is_port_open(8001):
                    return True
                if _story_process is not None and _story_process.poll() is not None:
                    return False
                await asyncio.sleep(0.25)
            return _is_port_open(8001)

        async def _wait_for_port_closed(port, timeout_seconds=10.0):
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                if not _is_port_open(port):
                    return True
                await asyncio.sleep(0.25)
            return not _is_port_open(port)

        def _kill_story_process():
            nonlocal _story_process
            if _story_process is not None and _story_process.poll() is None:
                _story_process.terminate()
                try:
                    _story_process.wait(timeout=5)
                except Exception:
                    _story_process.kill()
            _story_process = None
            if os.path.exists(_story_pid_file):
                try:
                    os.remove(_story_pid_file)
                except OSError:
                    pass

        def _kill_story_pid_from_file():
            if not os.path.exists(_story_pid_file):
                return
            try:
                with open(_story_pid_file, "r", encoding="utf-8") as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
            except (OSError, ValueError):
                pass
            finally:
                try:
                    os.remove(_story_pid_file)
                except OSError:
                    pass

        _atexit.register(_kill_story_process)

        from fastapi.responses import JSONResponse as _JSONResponse

        async def _shutdown_story_server():
            nonlocal _story_process
            if _story_process is not None and _story_process.poll() is None:
                _kill_story_process()
            else:
                _kill_story_pid_from_file()
                _story_process = None
            await _wait_for_port_closed(8001, timeout_seconds=10.0)
            return not _is_port_open(8001)

        @server_module.app.post("/api/launch-story")
        async def launch_story():
            nonlocal _story_process
            async with _story_launch_lock:
                # Reuse an existing story process we own. This avoids double-clicks or
                # repeated requests killing a server that is already starting normally.
                if _owned_story_running():
                    if await _wait_for_story_ready(timeout_seconds=30.0):
                        return _JSONResponse({"status": "ready"})
                    return _JSONResponse(
                        {
                            "status": "timeout",
                            "message": "Story service did not become ready in time."
                        },
                        status_code=503,
                    )

                # Clean stale pid bookkeeping from a previous crash/exit.
                _kill_story_pid_from_file()

                if _is_port_open(8001):
                    return _JSONResponse(
                        {
                            "status": "port_busy",
                            "message": "Port 8001 is already occupied by another process."
                        },
                        status_code=409,
                    )

                _story_process = _subprocess.Popen(
                    [sys.executable, "-m", "examples.deduction.story.run_simulation"],
                    cwd=project_root,
                )
                with open(_story_pid_file, "w", encoding="utf-8") as f:
                    f.write(str(_story_process.pid))

                if await _wait_for_story_ready(timeout_seconds=30.0):
                    return _JSONResponse({"status": "ready"})

                if _story_process is not None and _story_process.poll() is not None:
                    return _JSONResponse(
                        {
                            "status": "failed",
                            "message": f"Story service exited early with code {_story_process.poll()}."
                        },
                        status_code=500,
                    )

                return _JSONResponse(
                    {
                        "status": "timeout",
                        "message": "Story service startup timed out."
                    },
                    status_code=503,
                )

        @server_module.app.post("/api/shutdown-story")
        async def shutdown_story():
            async with _story_launch_lock:
                ok = await _shutdown_story_server()
                if ok:
                    return _JSONResponse({"status": "stopped"})
                return _JSONResponse(
                    {
                        "status": "timeout",
                        "message": "Story service did not stop in time."
                    },
                    status_code=503,
                )

        @server_module.app.get("/api/story-status")
        async def story_status():
            async with _story_launch_lock:
                pid = _read_story_pid()
                process_running = _owned_story_running()
                port_open = _is_port_open(8001)

                if process_running and port_open:
                    status = "running"
                    message = "剧情模式服务运行中"
                elif process_running and not port_open:
                    status = "starting"
                    message = "剧情模式服务启动中"
                elif (not process_running) and port_open:
                    status = "port_busy"
                    message = "8001 端口被其他进程占用"
                else:
                    status = "stopped"
                    message = "剧情模式服务未启动"

                return _JSONResponse({
                    "status": status,
                    "message": message,
                    "pid": pid,
                    "port_open": port_open,
                })
        # ─────────────────────────────────────────────────────────────────────────

        # Main service startup should always reclaim any leftover story subprocess
        # from an earlier session before exposing the launcher endpoint again.
        async with _story_launch_lock:
            startup_shutdown_ok = await _shutdown_story_server()
            if startup_shutdown_ok:
                logger.info("【System】Cleaned up any stale story service on port 8001 during startup.")
            elif _is_port_open(8001):
                logger.warning("【System】Port 8001 is still occupied after startup cleanup attempt.")

        server_thread = threading.Thread(
            target=start_server,
            args=[server_config],
            daemon=True,
        )
        server_thread.start()
        logger.info(f"【System】API Server started at http://{server_config['host']}:{server_config['port']}")

        # ===== Step3 : start the simulation =====
        start_tick = 0
        max_tick = sim_builder.config.simulation.max_ticks
        running_ticks = max_tick - start_tick
        for i in range(running_ticks):
            # Wait for the frontend to click start (threading.Event, use executor for non-blocking wait)
            logger.info(f"【System】Waiting for frontend signal to start Tick {i}...")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, tick_start_event.wait)
            tick_start_event.clear()  # Reset the event, ready for the next tick

            # ── 回溯分支检测 ─────────────────────────────────────────────────────────────
            if server_module._viewing_tick != -1:
                viewing_tick = server_module._viewing_tick
                viewing_branch_id = server_module._viewing_branch_id
                # 使用被查看的分支（而非当前活跃分支）来校验 tick 范围
                viewing_branch = next(
                    (b for b in server_module._branches if b["id"] == viewing_branch_id), None
                )
                if viewing_branch is None:
                    logger.warning(f"【Branch】Branch {viewing_branch_id} not found — skipping fork")
                else:
                    max_viewing_tick = max(viewing_branch["ticks"], default=-1)

                    is_frontier = (viewing_tick == max_viewing_tick)
                    is_current_branch = (viewing_branch_id == server_module._current_branch_id)

                    if is_frontier and is_current_branch:
                        # Frontier of the current branch — continue normally, no action.
                        pass
                    elif is_frontier and not is_current_branch:
                        # Frontier of another branch: switch to that branch and continue.
                        snapshot_key = (viewing_branch_id, viewing_tick)
                        if snapshot_key in server_module._tick_snapshots:
                            logger.info(f"【Branch】Switching to branch {viewing_branch_id} frontier (tick {viewing_tick}) — no new branch")
                            rollback_ok = await pod_manager.rollback_to_tick.remote(viewing_tick)
                            if not rollback_ok:
                                logger.warning(f"【Branch】Environment rollback to tick {viewing_tick} reported failure while switching branch")
                            await pod_manager.restore_all_agents.remote(server_module._tick_snapshots[snapshot_key])
                            await system.run('timer', 'set_tick', viewing_tick + 1)
                            server_module._current_branch_id = viewing_branch_id
                            server_module._first_tick_after_fork = False
                            logger.info(f"【Branch】Switched current to branch {viewing_branch_id}")
                            await broadcast_branch_event("branch_created", {
                                "new_branch_id": viewing_branch_id,
                                "fork_tick": viewing_tick
                            })
                        else:
                            logger.warning(f"【Branch】Snapshot {snapshot_key} not found — cannot switch to branch {viewing_branch_id}")
                    elif viewing_tick <= max_viewing_tick:
                        # Historical (non-frontier) tick: fork a new branch.
                        snapshot_key = (viewing_branch_id, viewing_tick)
                        if snapshot_key in server_module._tick_snapshots:
                            logger.info(f"【Branch】Forking new branch from tick {viewing_tick} on branch {viewing_branch_id}")
                            rollback_ok = await pod_manager.rollback_to_tick.remote(viewing_tick)
                            if not rollback_ok:
                                logger.warning(f"【Branch】Environment rollback to tick {viewing_tick} reported failure while forking branch")
                            await pod_manager.restore_all_agents.remote(server_module._tick_snapshots[snapshot_key])
                            # Resume from next tick to avoid replaying the viewed tick.
                            await system.run('timer', 'set_tick', viewing_tick + 1)

                            new_branch = {
                                "id": len(server_module._branches),
                                # parent 是被查看的分支，而非当前活跃分支
                                "parent_branch_id": viewing_branch_id,
                                "fork_tick": viewing_tick,
                                "ticks": [],
                            }
                            server_module._branches.append(new_branch)
                            server_module._current_branch_id = new_branch["id"]
                            server_module._first_tick_after_fork = False
                            logger.info(f"【Branch】Created branch {new_branch['id']} forking at tick {viewing_tick} from branch {viewing_branch_id}")

                            await broadcast_branch_event("branch_created", {"new_branch_id": new_branch["id"], "fork_tick": viewing_tick})
                        else:
                            logger.warning(f"【Branch】Snapshot ({viewing_branch_id}, {viewing_tick}) not found — skipping fork")

                server_module._viewing_tick = -1
                server_module._viewing_branch_id = -1
            # ── 回溯分支检测结束 ──────────────────────────────────────────────────────────

            tick_start_time = time.time()
            phase_timestamps = {"start": tick_start_time}

            # add_tick 之前获取 tick（主线从 T0 开始）
            current_tick = await system.run('timer', 'get_tick')

            # ===== Agent Step =====
            await pod_manager.step_agent.remote()
            phase_timestamps[f'Agent_Step_{i}'] = time.time()

            # ===== Collect token usage for this tick =====
            tick_token_usage = await pod_manager.collect_and_reset_token_usage.remote()

            # ===== Message Dispatch =====
            await system.run('messager', 'dispatch_messages')
            phase_timestamps[f'Message_Dispatch_{i}'] = time.time()

            # ===== Status Update =====
            await pod_manager.update_agents_status.remote()
            phase_timestamps[f'Status_Update_{i}'] = time.time()
            tick_end_time = time.time()

            tick_duration = tick_end_time - tick_start_time
            total_duration += tick_duration

            snapshot_ok = await pod_manager.make_snapshot.remote()
            if not snapshot_ok:
                logger.warning(f"【System】Adapter snapshot for Tick {current_tick} reported failure")

            await system.run('timer', 'add_tick', duration_seconds = tick_duration)

            # current_tick 已在 fork/switch 时设置为 viewing_tick+1；直接广播即可。
            broadcast_tick = current_tick

            # ===== Performance / Latency Metrics Calculation =====
            agent_step_latency = phase_timestamps[f'Agent_Step_{i}'] - phase_timestamps['start']
            msg_dispatch_latency = phase_timestamps[f'Message_Dispatch_{i}'] - phase_timestamps[f'Agent_Step_{i}']
            status_update_latency = phase_timestamps[f'Status_Update_{i}'] - phase_timestamps[f'Message_Dispatch_{i}']

            logger.info(f"【Performance】--- Tick {broadcast_tick} Performance Report ---")
            logger.info(f"【Performance】Total Tick Latency: {tick_duration:.4f}s")
            logger.info(f"【Performance】 - Agent Step Latency (Concurrency Execution): {agent_step_latency:.4f}s ({(agent_step_latency/tick_duration)*100:.1f}%)")
            logger.info(f"【Performance】 - Message Dispatch Latency: {msg_dispatch_latency:.4f}s ({(msg_dispatch_latency/tick_duration)*100:.1f}%)")
            logger.info(f"【Performance】 - Status Update Latency: {status_update_latency:.4f}s ({(status_update_latency/tick_duration)*100:.1f}%)")
            logger.info(f"【Performance】Token Usage - Prompt: {tick_token_usage['prompt_tokens']} | Completion: {tick_token_usage['completion_tokens']} | Total: {tick_token_usage['total_tokens']}")
            logger.info(f"【System】--- Tick {broadcast_tick} finished in {tick_duration:.4f} seconds ---")

            for k in cumulative_tokens:
                cumulative_tokens[k] += tick_token_usage.get(k, 0)

            # ===== Collect agent data and broadcast to frontend =====
            try:
                logger.info(f"【System】Collecting agents data for Tick {broadcast_tick}...")
                data_collect_start = time.time()
                agents_data = await pod_manager.collect_agents_data.remote()
                data_collect_latency = time.time() - data_collect_start

                logger.info(f"【System】Broadcasting data for Tick {broadcast_tick} (agents count: {len(agents_data)})...")
                broadcast_start = time.time()
                await broadcast_tick_data(broadcast_tick, agents_data)
                broadcast_latency = time.time() - broadcast_start

                logger.info(f"【Performance】 - Data Collection Latency: {data_collect_latency:.4f}s")
                logger.info(f"【Performance】 - WS Broadcast Latency: {broadcast_latency:.4f}s")
                logger.info(f"【Performance】-----------------------------------------")
                logger.info(f"【System】Tick {broadcast_tick} data broadcasted to frontend.")
            except Exception as broadcast_exc:
                logger.error(f"【System】Failed to collect or broadcast tick data: {broadcast_exc}", exc_info=True)


        if running_ticks > 0:
            logger.info(f'【System】Ran {running_ticks} ticks in total, average tick duration: {total_duration / running_ticks:.4f} seconds.')
            logger.info(f'【Performance】Total Token Usage - Prompt: {cumulative_tokens["prompt_tokens"]} | Completion: {cumulative_tokens["completion_tokens"]} | Total: {cumulative_tokens["total_tokens"]}')

        logger.info(f'【System】Simulation finished.')

        # ===== Step4 : Split logs by character =====
        from examples.deduction.map.scripts.split_logs_by_character import process_log_directory
        log_dir = Path(project_path) / "logs"
        output_dir = log_dir / "character"
        logger.info(f'【System】Splitting logs by character...')
        process_log_directory(log_dir=log_dir, output_dir=output_dir, keep_original=True)
        logger.info(f'【System】Log splitting completed.')

    except Exception as e:
        logger.error(f'【System】Failed to run the simulation: {e}.')

    # ===== Step5 : Stop the simulation =====

    finally:
        if "MAS_EVENT_LOG_DIR" in os.environ:
            del os.environ["MAS_EVENT_LOG_DIR"]
        if pod_manager:
            result = await pod_manager.close.remote()
            logger.info(f"【System】Pod Manager close result is {result}")
        if system:
            result = await system.close()
            logger.info(f"【System】System close result is {result}")
        if ray.is_initialized():
            ray.shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("【System】Simulation interrupted by user. Exiting.")
    finally:
        logger.info("【System】Simulation ended.")
