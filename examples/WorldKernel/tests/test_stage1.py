"""
Stage 1 端到端集成测试（真实服务器 + 浏览器前端）

启动 uvicorn → 打开浏览器 → 监测 worlds/generated/ 目录 → 新 session 出现后自动校验。

用法：
    cd examples/WorldKernel
    python tests/test_stage1.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

_WORLDS_DIR = _ROOT / "worlds" / "generated"
_SERVER_URL = "http://localhost:8100"

_EXPECTED_FILES = [
    "world_template.json",
    "generation_plan.json",
    "character_template.json",
    "location_template.json",
    "relation_template.json",
    "institution_template.json",
    "rule_template.json",
    "action_template.json",
]

_VALIDATORS: dict[str, list[str]] = {
    "world_template.json": ["primary", "location_types", "character_roles", "macro_rules"],
    "generation_plan.json": ["steps"],
    "character_template.json": ["dimensions"],
    "location_template.json": ["dimensions"],
    "relation_template.json": ["dimensions"],
    "institution_template.json": ["dimensions"],
    "rule_template.json": ["dimensions"],
    "action_template.json": ["dimensions"],
}


class _Stats:
    def __init__(self) -> None:
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def ok(self, msg: str) -> None:
        self.total += 1
        self.passed += 1
        print(f"  [PASS] {msg}")

    def fail(self, msg: str) -> None:
        self.total += 1
        self.failed += 1
        self.errors.append(msg)
        print(f"  [FAIL] {msg}")


def _sep(title: str = "", width: int = 70) -> None:
    if title:
        pad = max((width - len(title) - 2) // 2, 1)
        print(f"\n{'─' * pad} {title} {'─' * pad}")
    else:
        print("─" * width)


def _preview(data: dict | list, max_lines: int = 20) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    half = max_lines // 2
    return "\n".join(lines[:half] + [f"  ... ({len(lines) - max_lines} lines omitted) ..."] + lines[-half:])


def _get_existing_sessions() -> set[str]:
    if not _WORLDS_DIR.exists():
        return set()
    return {d.name for d in _WORLDS_DIR.iterdir() if d.is_dir()}


def _wait_for_new_session(before: set[str], timeout: float = 600.0) -> str | None:
    """轮询 worlds/generated/ 等待新 session 目录出现。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        current = _get_existing_sessions()
        new = current - before
        if new:
            return new.pop()
        time.sleep(1.0)
    return None


def _wait_for_files(session_dir: Path, timeout: float = 300.0) -> list[str]:
    """等待 session 目录中文件数量稳定（pipeline 写完）。"""
    t0 = time.time()
    prev_count = 0
    stable_since = 0.0

    while time.time() - t0 < timeout:
        files = [f.name for f in session_dir.iterdir() if f.suffix == ".json"]
        if len(files) != prev_count:
            prev_count = len(files)
            stable_since = time.time()
        elif time.time() - stable_since > 5.0 and prev_count > 0:
            return sorted(files)
        time.sleep(1.0)

    return sorted(f.name for f in session_dir.iterdir() if f.suffix == ".json")


def _validate_content(fname: str, data: dict, stats: _Stats) -> None:
    if fname == "world_template.json":
        if data.get("primary"):
            stats.ok(f"{fname}: primary = {data['primary']}")
        else:
            stats.fail(f"{fname}: primary 为空")

        for list_field in ("location_types", "character_roles", "macro_rules"):
            val = data.get(list_field, [])
            if val and len(val) > 0:
                stats.ok(f"{fname}: {list_field} 有 {len(val)} 项")
            else:
                stats.fail(f"{fname}: {list_field} 为空")

    elif fname == "generation_plan.json":
        steps = data.get("steps", [])
        if len(steps) >= 2:
            stats.ok(f"{fname}: {len(steps)} 个生成步骤")
        else:
            stats.fail(f"{fname}: 步骤数不足 ({len(steps)})")

        for i, step in enumerate(steps):
            if not (step.get("name") and step.get("target")):
                stats.fail(f"{fname}: steps[{i}] 缺少 name 或 target")

    elif fname.endswith("_template.json"):
        dims = data.get("dimensions", {})
        if len(dims) >= 2:
            stats.ok(f"{fname}: {len(dims)} 个维度")
        else:
            stats.fail(f"{fname}: 维度数不足 ({len(dims)})")

        for dim_name, dim_data in dims.items():
            fixed = dim_data.get("fixed", [])
            special = dim_data.get("special", [])
            if not fixed:
                stats.fail(f"{fname}: {dim_name}.fixed 为空")
            if not special:
                stats.fail(f"{fname}: {dim_name}.special 为空（LLM 未生成特殊属性）")


def _run_validation(session_id: str) -> None:
    """对一个 session 目录执行完整校验。"""
    stats = _Stats()
    session_dir = _WORLDS_DIR / session_id
    t0 = time.time()

    _sep(f"检测到新 session: {session_id}")

    print("  等待文件写入完成...")
    files = _wait_for_files(session_dir)
    elapsed = time.time() - t0
    print(f"  生成文件: {files}")

    _sep("文件完整性检查")
    for expected in _EXPECTED_FILES:
        if expected in files:
            stats.ok(f"文件存在: {expected}")
        else:
            stats.fail(f"文件缺失: {expected}")

    _sep("内容校验")
    for fname in _EXPECTED_FILES:
        fpath = session_dir / fname
        if not fpath.exists():
            continue

        data = json.loads(fpath.read_text(encoding="utf-8"))
        required_keys = _VALIDATORS.get(fname, [])
        missing = [k for k in required_keys if k not in data]
        if missing:
            stats.fail(f"{fname} 缺少必需字段: {missing}")
        else:
            stats.ok(f"{fname} 字段校验通过")

        _validate_content(fname, data, stats)

        _sep(fname)
        print(_preview(data))

    _sep("测试结果")
    print(f"  总计: {stats.total}  通过: {stats.passed}  失败: {stats.failed}  耗时: {elapsed:.1f}s")
    if stats.errors:
        print(f"\n  失败项:")
        for err in stats.errors:
            print(f"    - {err}")
    if stats.failed == 0:
        print("\n  Stage 1 端到端测试全部通过")
    else:
        print(f"\n  有 {stats.failed} 项失败，请检查")
    _sep()


def _start_server() -> threading.Thread:
    """在后台线程启动 uvicorn。"""
    import uvicorn
    from worldkernel.server import app

    config = uvicorn.Config(app, host="0.0.0.0", port=8100, log_level="info")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return thread


def main() -> None:
    print("启动 WorldKernel 服务器...")
    _start_server()

    time.sleep(2.0)

    before = _get_existing_sessions()

    url = _SERVER_URL
    print(f"打开浏览器: {url}")
    webbrowser.open(url)

    print("\n在浏览器中输入世界创建需求并点击「开始生成」")
    print("脚本正在监测 worlds/generated/ 目录，检测到新 session 后自动校验...")
    print("按 Ctrl+C 退出\n")

    try:
        while True:
            session_id = _wait_for_new_session(before, timeout=30.0)
            if session_id:
                _run_validation(session_id)
                before.add(session_id)
                print("\n继续监测中... 可在浏览器中再次提交，或按 Ctrl+C 退出\n")
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
