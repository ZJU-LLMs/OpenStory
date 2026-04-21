# Return to Main Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "🏠 主菜单" header button to both free mode (port 8000) and story mode (port 8001) game UIs that resets the current game and returns the user to the initial mode selection screen.

**Architecture:** Each mode gets an independent `returnToMainMenu()` function that: (1) shows a confirm dialog, (2) POSTs to the local `/api/reset` endpoint, (3) on success navigates back — free mode re-shows the `#modeSelectionScreen` overlay while story mode redirects to `http://localhost:8000/frontend/index.html`. No shared code between the two modes.

**Tech Stack:** Vanilla JS, HTML, existing `/api/reset` endpoints on port 8000 and 8001.

---

### Task 1: Add "主菜单" button to free mode (deduction) HTML

**Files:**
- Modify: `examples/deduction/frontend/index.html:82-85`

- [ ] **Step 1: Insert button before `#settingsBtn`**

In `examples/deduction/frontend/index.html`, find this block (lines 82–85):

```html
        <!-- 设置按钮 -->
        <button id="settingsBtn" class="control-btn settings-btn" onclick="openSettingsModal()" title="设置" data-i18n-title="btn_settings">
```

Insert one new line immediately before the `<!-- 设置按钮 -->` comment:

```html
        <button id="returnHomeBtn" class="control-btn" onclick="returnToMainMenu()" title="返回主菜单">🏠</button>
        <!-- 设置按钮 -->
        <button id="settingsBtn" class="control-btn settings-btn" onclick="openSettingsModal()" title="设置" data-i18n-title="btn_settings">
```

- [ ] **Step 2: Verify HTML is valid**

Open `examples/deduction/frontend/index.html` and confirm:
- `id="returnHomeBtn"` appears exactly once
- It sits between `id="memoryTreeBtn"` and `id="settingsBtn"`

- [ ] **Step 3: Commit**

```bash
git add examples/deduction/frontend/index.html
git commit -m "feat(deduction): add return-to-main-menu button in header"
```

---

### Task 2: Implement `returnToMainMenu()` in free mode JS

**Files:**
- Modify: `examples/deduction/frontend/app.js` — append after the existing `confirmReset()` function (around line 4483)

- [ ] **Step 1: Locate insertion point**

In `examples/deduction/frontend/app.js`, find this block (around line 4483):

```javascript
}

// ── Memory Tree Functions ──────────────────────────────────────────────────
```

- [ ] **Step 2: Insert `returnToMainMenu()` between `confirmReset` closing brace and the Memory Tree comment**

```javascript
async function returnToMainMenu() {
  if (!confirm('确认返回主菜单？\n当前推演进度将重置，所有记忆和状态将清空。')) return;
  try {
    const res = await fetch('http://localhost:8000/api/reset', { method: 'POST' });
    if (!res.ok) { alert('重置失败：' + (await res.text())); return; }
  } catch (e) {
    alert('重置请求发送失败，请检查网络连接');
    return;
  }
  clearTimeout(reconnectTimer);
  if (ws) { ws.close(); ws = null; }
  document.getElementById('appCoreUI').classList.add('hidden');
  document.getElementById('modeSelectionScreen').classList.remove('hidden');
}
window.returnToMainMenu = returnToMainMenu;

// ── Memory Tree Functions ──────────────────────────────────────────────────
```

- [ ] **Step 3: Verify `window.returnToMainMenu` is exported**

Search the file for `window.returnToMainMenu` — should appear exactly once.

- [ ] **Step 4: Commit**

```bash
git add examples/deduction/frontend/app.js
git commit -m "feat(deduction): implement returnToMainMenu with reset and nav"
```

---

### Task 3: Add "主菜单" button to story mode HTML

**Files:**
- Modify: `examples/story/frontend/index.html:47-55`

- [ ] **Step 1: Insert button before `#settingsBtn`**

In `examples/story/frontend/index.html`, find this block (lines 47–50):

```html
      <button id="memoryTreeBtn" class="control-btn memory-tree-btn" onclick="toggleMemoryTree()" title="回溯树">
        🌳 回溯树
      </button>
      <button id="settingsBtn" class="control-btn settings-btn" onclick="openSettingsModal()" title="设置">
```

Insert one new line immediately after the closing `</button>` of `#memoryTreeBtn`:

```html
      <button id="memoryTreeBtn" class="control-btn memory-tree-btn" onclick="toggleMemoryTree()" title="回溯树">
        🌳 回溯树
      </button>
      <button id="returnHomeBtn" class="control-btn" onclick="returnToMainMenu()" title="返回主菜单">🏠</button>
      <button id="settingsBtn" class="control-btn settings-btn" onclick="openSettingsModal()" title="设置">
```

- [ ] **Step 2: Verify HTML is valid**

Open `examples/story/frontend/index.html` and confirm:
- `id="returnHomeBtn"` appears exactly once
- It sits between `id="memoryTreeBtn"` and `id="settingsBtn"`

- [ ] **Step 3: Commit**

```bash
git add examples/story/frontend/index.html
git commit -m "feat(story): add return-to-main-menu button in header"
```

---

### Task 4: Implement `returnToMainMenu()` in story mode JS

**Files:**
- Modify: `examples/story/frontend/app.js` — append after the existing `confirmReset()` function (around line 4635)

- [ ] **Step 1: Locate insertion point**

In `examples/story/frontend/app.js`, find this block (around line 4637):

```javascript
}

// ── 回溯树函数 ─────────────────────────────────────────────────────────────────
```

- [ ] **Step 2: Insert `returnToMainMenu()` between `confirmReset` closing brace and the 回溯树 comment**

```javascript
async function returnToMainMenu() {
  if (!confirm('确认返回主菜单？\n当前剧情推演进度将重置。')) return;
  try {
    const res = await fetch('http://localhost:8001/api/reset', { method: 'POST' });
    if (!res.ok) { alert('重置失败：' + (await res.text())); return; }
  } catch (e) {
    alert('重置请求发送失败，请检查网络连接');
    return;
  }
  window.location.href = 'http://localhost:8000/frontend/index.html';
}
window.returnToMainMenu = returnToMainMenu;

// ── 回溯树函数 ─────────────────────────────────────────────────────────────────
```

- [ ] **Step 3: Verify `window.returnToMainMenu` is exported**

Search the file for `window.returnToMainMenu` — should appear exactly once.

- [ ] **Step 4: Commit**

```bash
git add examples/story/frontend/app.js
git commit -m "feat(story): implement returnToMainMenu with reset and redirect"
```

---

### Task 5: Manual smoke test

- [ ] **Step 1: Test free mode return**

1. Open `http://localhost:8000/frontend/index.html`
2. Click "自由模式" to enter the game
3. Verify "🏠" button appears in the header toolbar between 🌳 and the gear icon
4. Click "🏠"
5. Confirm dialog appears with text "确认返回主菜单？\n当前推演进度将重置，所有记忆和状态将清空。"
6. Click "取消" → nothing happens, game stays visible
7. Click "🏠" again → click "确定"
8. Expected: `#appCoreUI` hides, `#modeSelectionScreen` shows again

- [ ] **Step 2: Test story mode return**

1. From mode selection, click "剧情模式" to launch story server
2. Select a character and enter the story game at `http://localhost:8001/frontend/index.html`
3. Verify "🏠" button appears in the header toolbar
4. Click "🏠"
5. Confirm dialog appears with text "确认返回主菜单？\n当前剧情推演进度将重置。"
6. Click "取消" → nothing happens
7. Click "🏠" again → click "确定"
8. Expected: page redirects to `http://localhost:8000/frontend/index.html` and mode selection screen is shown

- [ ] **Step 3: Test reset failure path (optional)**

Temporarily stop the backend (Ctrl+C the server), then click "🏠" and confirm. Expected: alert "重置请求发送失败，请检查网络连接" and no navigation occurs.
