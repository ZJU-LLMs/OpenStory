'python -m examples.deduction.run_simulation'
# http://localhost:8000/frontend/index.html
import os
import sys

# 添加项目根目录和 packages 目录到 Python 路径，以便直接运行脚本
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
from agentkernel_distributed.mas.interface.server import start_server, broadcast_tick_data
from examples.deduction.registry import RESOURCES_MAPS
from agentkernel_distributed.toolkit.logger import get_logger
from examples.deduction.plugins.agent.plan.BasicPlanPlugin import BasicPlanPlugin

logger = get_logger(__name__)


def parse_tmx_locations(tmx_path: str) -> list:
    """从 TMX 文件的地点图层组中解析所有地点名称"""
    import xml.etree.ElementTree as ET
    tree = ET.parse(tmx_path)
    root = tree.getroot()

    locations = []
    # 找到 name="地点" 的顶层 group
    for top_group in root.findall("group"):
        if top_group.get("name") == "地点":
            # 遍历子 group（大观园、宁国府、荣国府等）
            for sub_group in top_group.findall("group"):
                for layer in sub_group.findall("layer"):
                    name = layer.get("name")
                    if name:
                        locations.append(name)
            # 也收集直接挂在地点 group 下的 layer
            for layer in top_group.findall("layer"):
                name = layer.get("name")
                if name:
                    locations.append(name)
    return locations

async def main():
    pod_manager = None
    system = None
    total_duration = 0
    try:
        logger.info(f'【System】Project path set to {project_path}.')

        # ===== 解析地图地点并注入到 PlanPlugin =====
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

        # ===== 启动 API Server（后台线程）=====
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
        
        # 建立一个线程安全事件，用于等待前端发送开始下一个 tick 的指令
        # 注意：server 运行在独立线程（独立 event loop），必须用 threading.Event 而非 asyncio.Event
        tick_start_event = threading.Event()
        # 把事件对象传递给 server 模块，以便在 websocket 收到特定消息时 set() 它
        import agentkernel_distributed.mas.interface.server as server_module
        server_module._tick_start_event = tick_start_event
        # 把 pod_manager 引用传递给 server 模块，以便支持动态添加 agent
        server_module._pod_manager = pod_manager
        
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
            # 等待前端点击开始（threading.Event，用 executor 非阻塞等待）
            logger.info(f"【System】Waiting for frontend signal to start Tick {i}...")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, tick_start_event.wait)
            tick_start_event.clear()  # 重置事件，为下一个 tick 准备
            
            tick_start_time = time.time()
            phase_timestamps = {"start": tick_start_time}

            current_tick = await system.run('timer', 'get_tick')

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

            await system.run('timer', 'add_tick', duration_seconds = tick_duration)
            
            # ===== 性能/延迟指标计算 =====
            agent_step_latency = phase_timestamps[f'Agent_Step_{i}'] - phase_timestamps['start']
            msg_dispatch_latency = phase_timestamps[f'Message_Dispatch_{i}'] - phase_timestamps[f'Agent_Step_{i}']
            status_update_latency = phase_timestamps[f'Status_Update_{i}'] - phase_timestamps[f'Message_Dispatch_{i}']
            
            logger.info(f"【Performance】--- Tick {current_tick} Performance Report ---")
            logger.info(f"【Performance】Total Tick Latency: {tick_duration:.4f}s")
            logger.info(f"【Performance】 - Agent Step Latency (Concurrency Execution): {agent_step_latency:.4f}s ({(agent_step_latency/tick_duration)*100:.1f}%)")
            logger.info(f"【Performance】 - Message Dispatch Latency: {msg_dispatch_latency:.4f}s ({(msg_dispatch_latency/tick_duration)*100:.1f}%)")
            logger.info(f"【Performance】 - Status Update Latency: {status_update_latency:.4f}s ({(status_update_latency/tick_duration)*100:.1f}%)")
            logger.info(f"【System】--- Tick {current_tick} finished in {tick_duration:.4f} seconds ---")

            # ===== 收集 agent 数据并广播给前端 =====
            try:
                logger.info(f"【System】Collecting agents data for Tick {current_tick}...")
                data_collect_start = time.time()
                agents_data = await pod_manager.collect_agents_data.remote()
                data_collect_latency = time.time() - data_collect_start
                
                logger.info(f"【System】Broadcasting data for Tick {current_tick} (agents count: {len(agents_data)})...")
                broadcast_start = time.time()
                await broadcast_tick_data(current_tick, agents_data)
                broadcast_latency = time.time() - broadcast_start
                
                logger.info(f"【Performance】 - Data Collection Latency: {data_collect_latency:.4f}s")
                logger.info(f"【Performance】 - WS Broadcast Latency: {broadcast_latency:.4f}s")
                logger.info(f"【Performance】-----------------------------------------")
                logger.info(f"【System】Tick {current_tick} data broadcasted to frontend.")
            except Exception as broadcast_exc:
                logger.error(f"【System】Failed to collect or broadcast tick data: {broadcast_exc}", exc_info=True)


        if running_ticks > 0:
            logger.info(f'【System】Ran {running_ticks} ticks in total, average tick duration: {total_duration / running_ticks:.4f} seconds.')

        logger.info(f'【System】Simulation finished.')

        # ===== Step4 : Split logs by character =====
        from examples.deduction.scripts.split_logs_by_character import process_log_directory
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
