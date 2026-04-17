'python -m examples.story.run_simulation'
# http://localhost:8000/frontend/index.html
import os
import sys

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
os.environ["MAS_PROJECT_REL_PATH"] = "examples.story"
os.environ["MAS_EVENT_LOG_DIR"] = project_path
import asyncio
import threading
import ray
import time
import json as _json_global
from pathlib import Path
from agentkernel_distributed.mas.builder import Builder
from agentkernel_distributed.mas.interface.server import start_server, broadcast_tick_data, broadcast_branch_event
import agentkernel_distributed.mas.interface.server as server_module
from typing import Dict, Any, Tuple
_score_snapshots: Dict[Tuple, Dict[str, Any]] = {}
from examples.story.registry import RESOURCES_MAPS
from agentkernel_distributed.toolkit.logger import get_logger
from examples.story.plugins.agent.plan.BasicPlanPlugin import BasicPlanPlugin

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
    # ===== One-time setup =====
    logger.info(f'【System】Project path set to {project_path}.')

    # ===== Parse map locations and inject into PlanPlugin =====
    tmx_path = os.path.join(project_path, "map", "sos.tmx")
    locations = parse_tmx_locations(tmx_path)
    BasicPlanPlugin.set_locations(locations)
    logger.info(f'【System】Loaded {len(locations)} locations from map.')

    # ===== Step1 : Initialize Ray (once for the whole process lifetime) =====
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
    ray.init(runtime_env=runtime_env)
    logger.info(f'【System】Ray is initialized.')

    # ===== Read server config from a temporary Builder (no init, just config) =====
    _config_builder = Builder(project_path=project_path, resource_maps=RESOURCES_MAPS)
    api_cfg = _config_builder.config.api_server if hasattr(_config_builder.config, "api_server") else {}
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
            "/map": os.path.join(project_path, "..", "deduction", "map"),
            "/data": os.path.join(project_path, "data"),
        }
    }

    # ===== Shared events (reused across game sessions) =====
    # threading.Event because the server runs in a separate thread with its own event loop
    tick_start_event = threading.Event()
    game_restart_event = threading.Event()

    from fastapi import Request as _Request
    import redis.asyncio as _aioredis
    from fastapi.responses import PlainTextResponse as _PlainTextResponse

    server_module._tick_start_event = tick_start_event
    server_module._story_report_cache = None
    server_module._story_report_outcome = None

    # ===== Register FastAPI endpoints ONCE (before server starts) =====

    @server_module.app.post("/story/set_player")
    async def set_player_character(request: _Request):
        """游戏开始时存储玩家角色到 Redis，供 InvokePlugin 校验"""
        data = await request.json()
        if server_module.redis_pool:
            rc = _aioredis.Redis(connection_pool=server_module.redis_pool)
            await rc.set('story:player_character', _json_global.dumps(data, ensure_ascii=False))
        return {"status": "ok"}

    @server_module.app.post("/story/game_restart")
    async def game_restart():
        """游戏结束后，前端点击重新开始时调用，通知主循环开始新一局"""
        game_restart_event.set()
        return {"status": "ok", "message": "Restart signal received"}

    @server_module.app.get("/story/report")
    async def download_story_report():
        """下载故事报告为 txt"""
        report = getattr(server_module, '_story_report_cache', None)
        if not report:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="报告尚未生成")
        outcome = getattr(server_module, '_story_report_outcome', '')
        filename = f"红楼梦续写_{outcome}.txt"
        return _PlainTextResponse(
            content=report,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode().hex()}"}
        )

    # ===== Start API server thread ONCE =====
    server_thread = threading.Thread(
        target=start_server,
        args=[server_config],
        daemon=True,
    )
    server_thread.start()
    logger.info(f"【System】API Server started at http://{server_config['host']}:{server_config['port']}")

    # 等待 FastAPI server lifespan 完成（含 flushdb），给 1 秒缓冲
    import time as _time
    _time.sleep(1)

    # Redis client (reused across games, created after server lifespan flushdb)
    _story_redis = _aioredis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

    # Log splitter import (done once)
    from examples.story.map.scripts.split_logs_by_character import process_log_directory

    # ===== Game loop: each iteration is one full game session =====
    while True:
        pod_manager = None
        system = None
        total_duration = 0

        try:
            # Reset per-game state
            logger.info('【System】=== Starting new game session ===')
            server_module._story_report_cache = None
            server_module._story_report_outcome = None
            server_module._agents_snapshot = {}
            server_module._snapshot_tick = -1
            # Reset branch / backtrack state for new session
            server_module._tick_snapshots = {}
            server_module._branches = [{"id": 0, "parent_branch_id": None, "fork_tick": 0, "ticks": []}]
            server_module._current_branch_id = 0
            server_module._viewing_tick = -1
            server_module._viewing_branch_id = -1
            server_module._first_tick_after_fork = False
            _score_snapshots.clear()
            game_restart_event.clear()
            tick_start_event.clear()

            # Full Redis flush — clears ALL stale keys from the previous session:
            # occupation:{tick}:{agent_id}, user_plan:{agent_id}, history:kv/graph
            # snapshots, story:player_character, etc.
            # pub/sub channels are not affected by flushdb.
            await _story_redis.flushdb()
            await _story_redis.set('story:score', 50)
            logger.info("【Story】Redis flushed. Initialized story:score = 50")

            # ===== Build and init simulation components for this session =====
            logger.info(f'【System】Initialize the builder...')
            sim_builder = Builder(
                project_path=project_path,
                resource_maps=RESOURCES_MAPS
            )
            logger.info(f'【System】Start all the simulation components...')
            pod_manager, system = await sim_builder.init()

            # Update server module reference to the new pod_manager
            server_module._pod_manager = pod_manager

            # ===== Step3 : start the simulation =====
            max_tick = sim_builder.config.simulation.max_ticks
            running_ticks = max_tick
            for i in range(running_ticks):
                # Wait for the frontend to click start (threading.Event, use executor for non-blocking wait)
                logger.info(f"【System】Waiting for frontend signal to start Tick {i}...")
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, tick_start_event.wait)
                tick_start_event.clear()  # Reset the event, ready for the next tick

                # ── 回溯分支检测 ─────────────────────────────────────────────────
                if server_module._viewing_tick != -1:
                    viewing_tick = server_module._viewing_tick
                    viewing_branch_id = server_module._viewing_branch_id
                    viewing_branch = server_module._branches[viewing_branch_id]
                    max_viewing_tick = max(viewing_branch["ticks"], default=-1)

                    is_current_tip = (
                        viewing_branch_id == server_module._current_branch_id
                        and viewing_tick == max_viewing_tick
                    )

                    if viewing_tick <= max_viewing_tick and not is_current_tip:
                        snapshot_key = (viewing_branch_id, viewing_tick)
                        if snapshot_key in server_module._tick_snapshots:
                            logger.info(f"【Branch】Forking new branch from tick {viewing_tick} on branch {viewing_branch_id}")
                            # 1. Restore agent states
                            await pod_manager.restore_all_agents.remote(server_module._tick_snapshots[snapshot_key])
                            # 2. Reset simulation timer
                            await system.run('timer', 'set_tick', viewing_tick)
                            # 3. Restore score + score_events to Redis
                            if snapshot_key in _score_snapshots:
                                score_snap = _score_snapshots[snapshot_key]
                                await _story_redis.set('story:score', score_snap["score"])
                                await _story_redis.delete('story:score_events')
                                if score_snap["events"]:
                                    await _story_redis.rpush('story:score_events', *reversed(score_snap["events"]))
                                logger.info(f"【Branch】Restored story:score={score_snap['score']} with {len(score_snap['events'])} events")
                            # 4. Clear all player-assigned tasks
                            async for key in _story_redis.scan_iter('user_plan:*'):
                                await _story_redis.delete(key)
                            logger.info("【Branch】Cleared all user_plan:* keys")
                            # 5. Create new branch metadata
                            new_branch = {
                                "id": len(server_module._branches),
                                "parent_branch_id": viewing_branch_id,
                                "fork_tick": viewing_tick,
                                "ticks": [],
                            }
                            server_module._branches.append(new_branch)
                            server_module._current_branch_id = new_branch["id"]
                            server_module._first_tick_after_fork = True
                            logger.info(f"【Branch】Created branch {new_branch['id']} forking at tick {viewing_tick} from branch {viewing_branch_id}")
                            await broadcast_branch_event("branch_created", {"new_branch_id": new_branch["id"], "fork_tick": viewing_tick})
                        else:
                            logger.warning(f"【Branch】Snapshot {snapshot_key} not found — skipping fork")

                    server_module._viewing_tick = -1
                    server_module._viewing_branch_id = -1
                # ── 回溯分支检测结束 ─────────────────────────────────────────────

                tick_start_time = time.time()
                phase_timestamps = {"start": tick_start_time}

                current_tick = await system.run('timer', 'get_tick')

                # fork 后第一次广播：tick 编号 = fork_tick + 1，避免与父分支节点重叠
                if server_module._first_tick_after_fork:
                    server_module._first_tick_after_fork = False
                    broadcast_tick = current_tick + 1
                else:
                    broadcast_tick = current_tick

                # ===== Agent Step =====
                await pod_manager.step_agent.remote()
                phase_timestamps[f'Agent_Step_{i}'] = time.time()

                # ===== Message Dispatch =====
                await system.run('messager', 'dispatch_messages')
                phase_timestamps[f'Message_Dispatch_{i}'] = time.time()

                # ===== Status Update =====
                await pod_manager.update_agents_status.remote()
                phase_timestamps[f'Status_Update_{i}'] = time.time()
                tick_end_time = time.time()

                tick_duration = tick_end_time - tick_start_time
                total_duration += tick_duration

                await system.run('timer', 'add_tick', duration_seconds=tick_duration)

                # ===== Performance / Latency Metrics Calculation =====
                agent_step_latency = phase_timestamps[f'Agent_Step_{i}'] - phase_timestamps['start']
                msg_dispatch_latency = phase_timestamps[f'Message_Dispatch_{i}'] - phase_timestamps[f'Agent_Step_{i}']
                status_update_latency = phase_timestamps[f'Status_Update_{i}'] - phase_timestamps[f'Message_Dispatch_{i}']

                logger.info(f"【Performance】--- Tick {broadcast_tick} Performance Report ---")
                logger.info(f"【Performance】Total Tick Latency: {tick_duration:.4f}s")
                logger.info(f"【Performance】 - Agent Step Latency (Concurrency Execution): {agent_step_latency:.4f}s ({(agent_step_latency/tick_duration)*100:.1f}%)")
                logger.info(f"【Performance】 - Message Dispatch Latency: {msg_dispatch_latency:.4f}s ({(msg_dispatch_latency/tick_duration)*100:.1f}%)")
                logger.info(f"【Performance】 - Status Update Latency: {status_update_latency:.4f}s ({(status_update_latency/tick_duration)*100:.1f}%)")
                logger.info(f"【System】--- Tick {broadcast_tick} finished in {tick_duration:.4f} seconds ---")

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

                    # ===== 追加广播：故事稳定度 =====
                    story_score_raw = await _story_redis.get('story:score')
                    story_score = int(story_score_raw or 50)
                    story_score = max(0, min(100, story_score))
                    await _story_redis.set('story:score', story_score)  # 回写钳制后的值

                    # 读取本 tick 产生的事件（最多10条）
                    raw_events = await _story_redis.lrange('story:score_events', 0, 9)
                    score_events = []
                    for ev_raw in raw_events:
                        try:
                            ev = _json_global.loads(ev_raw)
                            if ev.get('tick') == broadcast_tick:
                                score_events.append(ev)
                        except Exception:
                            pass

                    # 广播分数消息
                    score_payload = _json_global.dumps({
                        'type': 'story_score_update',
                        'story_score': story_score,
                        'score_events': score_events
                    }, ensure_ascii=False)
                    await server_module.manager.broadcast(score_payload)
                    logger.info(f"【Story】Tick {broadcast_tick}: story:score = {story_score}")

                    # Save score snapshot for this (branch, tick)
                    all_events_raw = await _story_redis.lrange('story:score_events', 0, -1)
                    _score_snapshots[(server_module._current_branch_id, broadcast_tick)] = {
                        "score": story_score,
                        "events": list(all_events_raw),
                    }

                    # ===== 胜负检测 =====
                    if story_score >= 100:
                        logger.info("【Story】Victory! story:score >= 100. Stopping simulation.")
                        break
                    elif story_score <= 0:
                        logger.info("【Story】Defeat. story:score <= 0. Stopping simulation.")
                        break

                except Exception as broadcast_exc:
                    logger.error(f"【System】Failed to collect or broadcast tick data: {broadcast_exc}", exc_info=True)

            if running_ticks > 0:
                logger.info(f'【System】Ran {running_ticks} ticks in total, average tick duration: {total_duration / running_ticks:.4f} seconds.')

            logger.info(f'【System】Simulation finished.')

            # ===== Step3.5 : Generate story report =====
            try:
                story_score_raw = await _story_redis.get('story:score')
                final_score = int(story_score_raw or 50)
                is_victory = final_score >= 100

                # Collect dialogue logs from invoke.log
                invoke_log_path = Path(project_path) / "logs" / "app" / "agent" / "invoke.log"
                dialogue_excerpts = []
                if invoke_log_path.exists():
                    with open(invoke_log_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            if '对话摘要' in line or 'dialogue' in line.lower() or '说：' in line or '道：' in line:
                                dialogue_excerpts.append(line.strip())
                # Limit to last 200 lines to avoid token overflow
                dialogue_text = '\n'.join(dialogue_excerpts[-200:]) if dialogue_excerpts else '（无对话记录）'

                outcome_text = '大观园在众人努力下重焕生机，稳定度达到顶峰。' if is_victory else '大观园稳定度跌至谷底，终究走向衰败。'

                report_prompt = f"""你是一位精通《红楼梦》的文学家。以下是一段大观园模拟推演的交互日志摘录：

{dialogue_text}

推演结局：{outcome_text}（最终稳定度：{final_score}/100）

请根据以上日志，以《红楼梦》的文风续写一段故事（800-1200字），描绘大观园中人物的命运走向与情感纠葛，呼应推演结局。文风典雅，富有诗意，可引用诗词。"""

                # Call LLM via httpx using primary model config
                import httpx as _httpx
                import yaml as _yaml
                models_cfg_path = Path(project_path) / "configs" / "models_config.yaml"
                with open(models_cfg_path, 'r', encoding='utf-8') as f:
                    models_cfg = _yaml.safe_load(f)
                m = models_cfg[0]
                base_url = m.get('base_url', '').rstrip('/')
                api_key = m.get('api_key', '')
                model_name = m.get('model', 'gpt-4o')

                logger.info("【Story】Generating story report via LLM...")
                async with _httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={"model": model_name, "messages": [{"role": "user", "content": report_prompt}], "temperature": 0.9}
                    )
                    resp.raise_for_status()
                    report_text = resp.json()['choices'][0]['message']['content']

                # Cache report for download
                server_module._story_report_cache = report_text
                server_module._story_report_outcome = '胜利' if is_victory else '失败'

                # Broadcast to frontend
                report_payload = _json_global.dumps({
                    'type': 'story_report',
                    'report': report_text,
                    'outcome': '胜利' if is_victory else '失败',
                    'final_score': final_score
                }, ensure_ascii=False)
                await server_module.manager.broadcast(report_payload)
                logger.info("【Story】Story report generated and broadcasted.")
            except Exception as report_exc:
                logger.error(f"【Story】Failed to generate story report: {report_exc}", exc_info=True)

            # ===== Step4 : Split logs by character =====
            log_dir = Path(project_path) / "logs"
            output_dir = log_dir / "character"
            logger.info(f'【System】Splitting logs by character...')
            process_log_directory(log_dir=log_dir, output_dir=output_dir, keep_original=True)
            logger.info(f'【System】Log splitting completed.')

        except Exception as e:
            logger.error(f'【System】Failed to run the simulation: {e}.', exc_info=True)

        finally:
            # Clean up this session's Ray actors (Ray itself stays alive)
            if pod_manager:
                try:
                    result = await pod_manager.close.remote()
                    logger.info(f"【System】Pod Manager close result is {result}")
                except Exception as e:
                    logger.error(f"【System】Error closing pod manager: {e}")
                try:
                    ray.kill(pod_manager, no_restart=True)
                    logger.info("【System】Pod Manager actor killed from Ray registry.")
                except Exception as e:
                    logger.error(f"【System】Error killing pod manager actor: {e}")
            if system:
                try:
                    result = await system.close()
                    logger.info(f"【System】System close result is {result}")
                except Exception as e:
                    logger.error(f"【System】Error closing system: {e}")
            pod_manager = None
            system = None

        # ===== Wait for restart signal =====
        logger.info('【System】Game over. Waiting for restart signal (timeout: 30 min)...')
        loop = asyncio.get_running_loop()
        got_restart = await loop.run_in_executor(None, lambda: game_restart_event.wait(timeout=1800))
        if not got_restart:
            logger.info('【System】Restart timeout. Exiting.')
            break
        logger.info('【System】Restart signal received. Starting new game session...')

    # ===== Final teardown (only reached on timeout or after last game) =====
    if "MAS_EVENT_LOG_DIR" in os.environ:
        del os.environ["MAS_EVENT_LOG_DIR"]
    if ray.is_initialized():
        ray.shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("【System】Simulation interrupted by user. Exiting.")
    finally:
        logger.info("【System】Simulation ended.")
