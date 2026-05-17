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

_TEMPLATES_DIR = _ROOT / "templates"
_SERVER_URL = "http://localhost:8100"

_EXPECTED_PATHS = [
    "generated/world_template.json",
    "generated/plan/steps.json",
    "generated/plan/ontology_hints.json",
    "generated/plan/entity_plan/locations",
    "generated/plan/entity_plan/characters",
    "generated/plan/entity_plan/institutions",
    "generated/plan/entity_plan/rules",
    "generated/templates/character/index.json",
    "generated/templates/location/index.json",
    "generated/templates/relation/index.json",
    "generated/templates/institution/index.json",
    "generated/templates/rule/index.json",
    "generated/templates/action/index.json",
    "configs/agent/agent.yaml",
    "configs/agent/dims",
]


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


def _load(session_dir: Path, rel_path: str) -> dict | list | None:
    p = session_dir / rel_path
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _get_existing_sessions() -> set[str]:
    if not _TEMPLATES_DIR.exists():
        return set()
    return {d.name for d in _TEMPLATES_DIR.iterdir()
            if d.is_dir() and not d.name.startswith("agent_kernel")}


def _wait_for_new_session(before: set[str], timeout: float = 600.0) -> str | None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        current = _get_existing_sessions()
        new = current - before
        if new:
            return new.pop()
        time.sleep(1.0)
    return None


def _wait_for_stable(session_dir: Path, timeout: float = 300.0) -> None:
    """等待 session 目录文件数量稳定。"""
    t0 = time.time()
    prev_count = 0
    stable_since = 0.0

    while time.time() - t0 < timeout:
        count = sum(1 for _ in session_dir.rglob("*.json"))
        if count != prev_count:
            prev_count = count
            stable_since = time.time()
        elif time.time() - stable_since > 5.0 and prev_count > 0:
            return
        time.sleep(1.0)


def _validate_world_template(session_dir: Path, stats: _Stats) -> None:
    _sep("world_template.json")
    data = _load(session_dir, "generated/world_template.json")
    if data is None:
        stats.fail("world_template.json 不存在")
        return

    if data.get("primary"):
        stats.ok(f"primary = {data['primary']}")
    else:
        stats.fail("primary 为空")

    for arch_field in ("location_archetypes", "character_archetypes", "rule_archetypes"):
        val = data.get(arch_field, [])
        if len(val) >= 2:
            stats.ok(f"{arch_field} 有 {len(val)} 种类型")
        elif len(val) == 1:
            stats.ok(f"{arch_field} 有 1 种类型（偏少）")
        else:
            stats.fail(f"{arch_field} 为空")
        if val:
            first = val[0]
            seed_keys = [k for k in first if k.startswith("candidate_")]
            if seed_keys and first.get(seed_keys[0]):
                stats.ok(f"{arch_field}[0] 含候选 seed")
            else:
                stats.fail(f"{arch_field}[0] 缺少候选 seed")

    sim = data.get("simulation_start", {})
    if sim.get("trigger_event"):
        stats.ok("simulation_start.trigger_event 非空")
    else:
        stats.fail("simulation_start.trigger_event 为空")

    constraints = data.get("world_constraints", [])
    if len(constraints) >= 2:
        stats.ok(f"world_constraints 有 {len(constraints)} 条")
    else:
        stats.fail("world_constraints 不足 2 条")


def _validate_plan(session_dir: Path, stats: _Stats) -> None:
    _sep("plan/")

    steps = _load(session_dir, "generated/plan/steps.json")
    if steps is None:
        stats.fail("plan/steps.json 不存在")
    elif len(steps) >= 2:
        stats.ok(f"steps.json: {len(steps)} 个步骤")
        s0 = steps[0]
        if s0.get("step_id") and s0.get("generator_type"):
            stats.ok(f"steps[0]: step_id={s0['step_id']}, generator_type={s0['generator_type']}")
        else:
            stats.fail("steps[0] 缺少 step_id 或 generator_type")
    else:
        stats.fail(f"steps.json: 步骤数不足 ({len(steps)})")

    hints = _load(session_dir, "generated/plan/ontology_hints.json")
    if hints is None:
        stats.fail("plan/ontology_hints.json 不存在")
    elif hints.get("character_hints"):
        stats.ok("ontology_hints.character_hints 非空")
    else:
        stats.fail("ontology_hints.character_hints 为空")

    ep_dir = session_dir / "generated" / "plan" / "entity_plan"
    for category in ("locations", "characters", "institutions", "rules"):
        cat_dir = ep_dir / category
        if not cat_dir.exists():
            stats.fail(f"entity_plan/{category}/ 不存在")
            continue
        archetype_files = list(cat_dir.glob("*.json"))
        if len(archetype_files) >= 2:
            stats.ok(f"entity_plan/{category}/: {len(archetype_files)} 个 archetype 文件")
        elif len(archetype_files) == 1:
            stats.ok(f"entity_plan/{category}/: 1 个 archetype 文件（偏少）")
        else:
            stats.fail(f"entity_plan/{category}/: 无 archetype 文件")

        if archetype_files:
            seeds = json.loads(archetype_files[0].read_text(encoding="utf-8"))
            if seeds and seeds[0].get("seed_id"):
                stats.ok(f"entity_plan/{category}/{archetype_files[0].name}: seed_id 非空")
            else:
                stats.fail(f"entity_plan/{category}/{archetype_files[0].name}: 缺少 seed_id")


def _validate_templates(session_dir: Path, stats: _Stats) -> None:
    _sep("templates/")
    expected_dims = {"character": 9, "location": 5, "institution": 6,
                     "rule": 4, "action": 4, "relation": 2}

    templates_dir = session_dir / "generated" / "templates"
    if not templates_dir.exists():
        stats.fail("templates/ 目录不存在")
        return

    for entity, min_dims in expected_dims.items():
        ent_dir = templates_dir / entity
        index_path = ent_dir / "index.json"
        if not index_path.exists():
            stats.fail(f"templates/{entity}/index.json 不存在")
            continue

        index = json.loads(index_path.read_text(encoding="utf-8"))
        dims = index.get("dimensions", [])
        if len(dims) >= min_dims:
            stats.ok(f"{entity}: {len(dims)} 个维度")
        else:
            stats.fail(f"{entity}: 维度数不足 ({len(dims)}，期望 ≥{min_dims})")

        for dim_name in dims:
            dim_path = ent_dir / f"{dim_name}.json"
            if not dim_path.exists():
                stats.fail(f"{entity}/{dim_name}.json 不存在")
                continue
            dim_data = json.loads(dim_path.read_text(encoding="utf-8"))
            fields = dim_data.get("fields", [])
            if len(fields) >= 1:
                f0 = fields[0]
                if isinstance(f0, dict) and f0.get("name") and "type" in f0:
                    stats.ok(f"{entity}/{dim_name}: {len(fields)} 个 FieldDef 字段")
                else:
                    stats.fail(f"{entity}/{dim_name}: fields[0] 不是 FieldDef 格式")
            else:
                stats.fail(f"{entity}/{dim_name}: fields 为空")


def _run_validation(session_id: str) -> None:
    stats = _Stats()
    session_dir = _TEMPLATES_DIR / session_id
    t0 = time.time()

    _sep(f"检测到新 session: {session_id}")

    print("  等待文件写入完成...")
    _wait_for_stable(session_dir)
    elapsed = time.time() - t0

    all_files = sorted(
        str(f.relative_to(session_dir)).replace("\\", "/")
        for f in session_dir.rglob("*.json")
    )
    print(f"  共 {len(all_files)} 个文件, 耗时 {elapsed:.1f}s")

    _sep("结构完整性检查")
    for expected in _EXPECTED_PATHS:
        p = session_dir / expected
        if p.exists():
            stats.ok(f"存在: {expected}")
        else:
            stats.fail(f"缺失: {expected}")

    _validate_world_template(session_dir, stats)
    _validate_plan(session_dir, stats)
    _validate_templates(session_dir, stats)

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
    print("脚本正在监测 templates/ 目录，检测到新 session 后自动校验...")
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
