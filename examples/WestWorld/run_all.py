"""Unified WestWorld launcher for the free simulation and story mode.

Run from the OpenStory repository root:

    python -m examples.WestWorld.run_all

The two modes deliberately remain separate processes. They use independent
FastAPI/Ray runtime state while sharing the configured model credentials,
proxy settings, and Redis server.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAY_TEMP_ROOT = PROJECT_ROOT / ".westworld-runtime" / "ray"


def _runtime_env(mode: str) -> Dict[str, str]:
    """Build a child environment with an isolated local Ray temp directory."""
    env = os.environ.copy()
    python_paths = [str(PROJECT_ROOT), str(PROJECT_ROOT / "packages" / "agentkernel-distributed")]
    if existing := env.get("PYTHONPATH"):
        python_paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(python_paths)
    ray_temp_dir = RAY_TEMP_ROOT / mode
    ray_temp_dir.mkdir(parents=True, exist_ok=True)
    env["RAY_TMPDIR"] = str(ray_temp_dir)
    return env


def _spawn(module: str, mode: str) -> subprocess.Popen[bytes]:
    kwargs: Dict[str, object] = {
        "cwd": str(PROJECT_ROOT),
        "env": _runtime_env(mode),
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen([sys.executable, "-m", module], **kwargs)


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start the WestWorld free simulation and story mode together.",
    )
    parser.parse_args(argv)
    RAY_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    processes: List[tuple[str, subprocess.Popen[bytes]]] = []
    try:
        processes.append(("free", _spawn("examples.WestWorld.run_simulation", "free")))
        processes.append(("story", _spawn("examples.WestWorld.story.run_simulation", "story")))
        story_port = os.environ.get("WW_STORY_PORT", "8001")
        print("WestWorld services started:")
        print("  Mode selection / free simulation: http://localhost:8000/frontend/index.html")
        print(f"  Story mode:                     http://localhost:{story_port}/frontend/character_select.html")
        print("Press Ctrl+C to stop both services.")

        while True:
            finished = [(name, proc.returncode) for name, proc in processes if proc.poll() is not None]
            if finished:
                for name, code in finished:
                    print(f"{name} mode exited with code {code}.", file=sys.stderr)
                if any(code not in (0, None) for _, code in finished):
                    return 1
                processes = [(name, proc) for name, proc in processes if proc.poll() is None]
                if not processes:
                    return 0
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopping WestWorld services...")
        return 0
    finally:
        for _, process in processes:
            _stop(process)


if __name__ == "__main__":
    raise SystemExit(main())
