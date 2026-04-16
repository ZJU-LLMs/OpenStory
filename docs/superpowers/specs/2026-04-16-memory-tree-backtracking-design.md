# Memory Tree Backtracking Feature Design

**Date:** 2026-04-16  
**Scope:** `examples/deduction` + `examples/deduction_en`  
**Status:** Approved

---

## Overview

Add a branching/backtracking feature to the deduction simulation UI. Users can open a "Memory Tree" panel to view the history of all simulation ticks, jump back to any past tick to inspect it, and optionally resume simulation from that point — automatically creating a new branch. Multiple branches can coexist, each displayed in a distinct color in the tree.

---

## User Experience

### Entry Point

A **"🌳 记忆树 / Memory Tree"** button is added to the top toolbar. Clicking it opens/closes a floating modal overlay on top of the main simulation view.

### Memory Tree Modal

The modal displays:
- An **SVG tree diagram** laid out horizontally (time flows left → right)
- The **main branch** as a horizontal spine of tick nodes
- **Sub-branches** forking off at their fork point, rendered in distinct colors
- A **diamond-shaped node** at each fork point
- A **pulsing red circle** on the current running tick
- A **dashed purple ring** around the tick currently being viewed (if in history mode)
- A **color legend** for branches

Each node displays only its **tick number** (minimal). No additional metadata shown on the node itself.

### Viewing a Historical Tick

Clicking any past node in the tree:
1. Sends `view_tick` message to backend
2. Backend returns the saved snapshot for that tick
3. Frontend renders the historical agent state (map, character panels) exactly as it was at that tick
4. A **yellow banner** appears at the top of the simulation: "正在查看 Tick N · 推进将从此处创建新分支 / Viewing Tick N — advancing will create a new branch"
5. The user can freely navigate without triggering any branch

### Creating a New Branch

When the user is viewing a historical tick and clicks **"开始模拟 / Start Simulation"**:
1. The existing `start_tick` WebSocket message is sent (no change to frontend trigger)
2. Backend detects the user is advancing from an old tick → automatically forks a new branch
3. All agents are restored to the historical tick's state
4. Simulation continues; new ticks are recorded under the new branch
5. Frontend receives `branch_created` message, updates the tree, clears the banner

**No explicit "create branch" button is needed.** The branch is implicit in the act of advancing from a historical tick.

---

## Architecture

### Backend Changes (`server.py`)

#### New In-Memory Structures

```python
_tick_snapshots: Dict[int, Dict[str, Any]] = {}
# Maps tick_number → { agent_id → full agent state dict }
# Written after every tick broadcast

_branches: List[dict] = [
    {
        "id": 0,
        "parent_branch_id": None,
        "fork_tick": 0,
        "ticks": []          # list of tick numbers belonging to this branch
    }
]
_current_branch_id: int = 0
_viewing_tick: int = -1      # -1 means "viewing latest"
```

#### Snapshot Saving

In `broadcast_tick_data(tick, agents_data)`, after updating `_agents_snapshot`:

```python
import copy
_tick_snapshots[tick] = copy.deepcopy(agents_data)
_branches[_current_branch_id]["ticks"].append(tick)
```

#### Branch Fork Logic (in `start_tick` handler)

```python
max_tick_in_branch = max(_branches[_current_branch_id]["ticks"], default=-1)

if _viewing_tick != -1 and _viewing_tick < max_tick_in_branch:
    # Auto-fork: create new branch from viewing tick
    new_branch = {
        "id": len(_branches),
        "parent_branch_id": _current_branch_id,
        "fork_tick": _viewing_tick,
        "ticks": []
    }
    _branches.append(new_branch)
    _current_branch_id = new_branch["id"]

    # Restore all agents to the snapshot at viewing_tick
    await restore_all_agents(_tick_snapshots[_viewing_tick])
    await timer.set_tick.remote(_viewing_tick)
    _viewing_tick = -1

    # Notify frontend
    await broadcast_json({
        "type": "branch_created",
        "new_branch_id": new_branch["id"],
        "fork_tick": new_branch["fork_tick"],
        "branches": _branches,
        "current_branch_id": _current_branch_id
    })

# Proceed with normal tick signal
next_tick_event.set()
```

#### New Helper: `restore_all_agents`

```python
async def restore_all_agents(snapshot: Dict[str, Any]):
    """Restore all Ray actor agents to a saved snapshot state."""
    refs = [
        pod_manager.restore_agent_state.remote(agent_id, state)
        for agent_id, state in snapshot.items()
    ]
    await asyncio.get_event_loop().run_in_executor(None, ray.get, refs)
```

`restore_all_agents` follows the same Ray actor invocation pattern as the existing `collect_agents_data` helper (semaphore-guarded `.remote()` calls gathered via `ray.get`). The exact concurrency strategy (semaphore limit) should mirror `collect_agents_data`.

### New WebSocket Message Protocol

#### Frontend → Backend

| Message | Purpose |
|---------|---------|
| `{ type: "view_tick", tick: N }` | Jump to view historical tick N (read-only) |
| `{ type: "get_branch_tree" }` | Request full branch tree (sent on connect) |
| `{ type: "start_tick" }` | Existing — extended to detect fork condition |

#### Backend → Frontend

| Message | Purpose |
|---------|---------|
| `{ type: "view_tick_ack", tick: N, data: {...} }` | Historical snapshot data for rendering |
| `{ type: "branch_tree", branches: [...], current_branch_id, current_tick }` | Full tree state, sent on connect and after each branch event |
| `{ type: "branch_created", new_branch_id, fork_tick, branches, current_branch_id }` | Notifies frontend a new branch was forked |

### Plugin Changes (`BasicStatePlugin.py`)

Add a new method `restore_state(snapshot: dict)` that accepts a full state dictionary and writes back all fields:

```python
async def restore_state(self, snapshot: dict) -> None:
    """Restore agent state from a tick snapshot dict."""
    for key, value in snapshot.items():
        await self.set_state(key, value)
```

This method is called per-agent by `BasicPodManager.restore_agent_state`, a new Ray remote method added to `BasicPodManager`:

```python
async def restore_agent_state(self, agent_id: str, state: dict) -> None:
    """Restore a single agent's state from a snapshot dict."""
    agent = self._agents.get(agent_id)
    if agent is None:
        return
    state_plugin = agent.get_plugin("BasicStatePlugin")
    await state_plugin.restore_state(state)
```

`BasicPodManager` holds a dict `_agents: Dict[str, Agent]` (same as existing structure). `get_plugin` retrieves the plugin instance by class name.

### Frontend Changes

#### New State Variables (`app.js`)

```javascript
let branchTree = [];           // Full branch tree from backend
let currentBranchId = 0;
let viewingTick = -1;          // -1 = viewing latest
let isViewingHistory = false;
let memoryTreeOpen = false;
```

#### New Functions

- `openMemoryTree()` / `closeMemoryTree()` — toggle modal visibility
- `renderBranchTree(branches, currentBranchId, currentTick, viewingTick)` — pure function, generates SVG from branch data
- `handleViewTickAck(data)` — apply historical snapshot to UI
- `handleBranchTree(data)` — update `branchTree`, re-render SVG
- `handleBranchCreated(data)` — update tree, clear history banner

#### History Mode Banner

When `isViewingHistory === true`, show a dismissible yellow banner inside or above the simulation canvas. Cleared when a new tick is received on the current branch or when user clicks the current-tick node.

---

## File Change Summary

| File | Changes |
|------|---------|
| `server.py` (both projects) | Add `_tick_snapshots`, `_branches`, `_viewing_tick`; extend `start_tick` handler; add `view_tick`, `get_branch_tree` handlers; add `restore_all_agents()` |
| `plugins/agent/state/BasicStatePlugin.py` (both) | Add `restore_state(snapshot)` method |
| `BasicPodManager.py` (both) | Add `restore_agent_state(agent_id, state)` remote method |
| `frontend/app.js` (both) | New state vars, message handlers, `renderBranchTree()`, modal toggle |
| `frontend/index.html` (both) | Memory tree button in toolbar; modal HTML structure |
| `frontend/style.css` (both) | Modal overlay, SVG tree, banner, legend styles |

---

## Constraints & Non-Goals

- **Memory only:** Snapshots are not persisted to disk. History is lost on server restart.
- **No branch merging:** Branches are read-only after creation; no merge UI.
- **No branch deletion:** Branches persist for the lifetime of the server session.
- **No branch naming:** Branches are identified by color + ID only.
- **deduction and deduction_en** receive identical changes; only UI text differs (Chinese vs English).

---

## Open Questions (Resolved)

| Question | Decision |
|----------|----------|
| UI layout | Floating modal triggered by toolbar button |
| Branch trigger | Automatic on advancing from historical tick |
| Persistence | Memory only |
| Node info | Tick number only (minimal) |
| State restoration | Backend in-memory snapshots, `restore_state()` injects into Ray actors |
