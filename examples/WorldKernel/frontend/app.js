let currentSessionId = null;
let currentStage2 = null;
let generatedWorlds = [];

async function loadGeneratedWorlds() {
  const select = document.getElementById('generatedWorldSelect');
  const info = document.getElementById('generatedWorldInfo');
  const enterBtn = document.getElementById('enterSelectedSimulationBtn');
  const viewerBtn = document.getElementById('selectedWorldViewerBtn');
  const refreshBtn = document.getElementById('refreshWorldsBtn');

  if (!select) return;
  refreshBtn.disabled = true;
  select.disabled = true;
  enterBtn.disabled = true;
  viewerBtn.style.display = 'none';
  select.innerHTML = '<option value="">正在加载本地世界...</option>';
  info.textContent = '正在扫描 templates 目录...';

  try {
    const resp = await fetch('/api/stage3/sessions');
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.detail || data.error || '本地世界列表加载失败');
    }

    generatedWorlds = data.sessions || [];
    if (!generatedWorlds.length) {
      select.innerHTML = '<option value="">暂无可直接进入的世界</option>';
      info.textContent = '没有找到同时包含语义数据和空间地图的本地世界。';
      return;
    }

    select.innerHTML = [
      '<option value="">请选择一个世界</option>',
      ...generatedWorlds.map((world) => {
        const label = `${world.world_name || world.session_id} (${world.session_id})`;
        return `<option value="${escapeHtml(world.session_id)}">${escapeHtml(label)}</option>`;
      }),
    ].join('');
    select.disabled = false;
    info.textContent = `找到 ${generatedWorlds.length} 个可进入 Stage3 的本地世界。`;
  } catch (error) {
    select.innerHTML = '<option value="">加载失败</option>';
    info.textContent = error.message === 'Failed to fetch'
      ? '本地世界服务未连接。启动 WorldKernel 服务后可读取已生成世界。'
      : error.message;
  } finally {
    refreshBtn.disabled = false;
  }
}

function selectGeneratedWorld() {
  const select = document.getElementById('generatedWorldSelect');
  const info = document.getElementById('generatedWorldInfo');
  const enterBtn = document.getElementById('enterSelectedSimulationBtn');
  const viewerBtn = document.getElementById('selectedWorldViewerBtn');
  const world = generatedWorlds.find((item) => item.session_id === select.value);

  if (!world) {
    enterBtn.disabled = true;
    viewerBtn.style.display = 'none';
    info.textContent = generatedWorlds.length ? '尚未选择世界。' : '暂无可直接进入的世界。';
    return;
  }

  const counts = world.counts || {};
  const modifiedAt = world.modified_at
    ? new Date(world.modified_at * 1000).toLocaleString()
    : '未知时间';
  info.textContent = [
    `世界: ${world.world_name || world.world_id}`,
    `角色 ${counts.characters || 0}, 地点 ${counts.locations || 0}, 路径 ${counts.paths || 0}`,
    `地图区域 ${counts.regions || 0}, 出生点 ${counts.spawn_points || 0}`,
    `更新时间: ${modifiedAt}`,
  ].join('\n');
  viewerBtn.href = `/viewer.html?session_id=${encodeURIComponent(world.session_id)}`;
  viewerBtn.style.display = 'inline-flex';
  enterBtn.disabled = false;
}

function enterSelectedSimulation() {
  const select = document.getElementById('generatedWorldSelect');
  const btn = document.getElementById('enterSelectedSimulationBtn');
  if (!select.value) return;
  enterSimulation(select.value, btn);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

async function submitInput() {
  const input = document.getElementById('worldInput').value.trim();
  if (!input) return;

  setStatus(true, '正在解析世界设定...');
  hideResult();
  hideError();
  hideMap();

  try {
    const stage1Resp = await fetch('/api/stage1/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input }),
    });
    const stage1 = await stage1Resp.json().catch(() => ({}));
    if (!stage1Resp.ok) {
      throw new Error(stage1.detail || stage1.error || 'Stage1 执行失败');
    }

    setStatus(true, 'Stage1 完成，正在生成语义数据和空间地图...');
    const stage2Resp = await fetch(`/api/stage2/run/${stage1.session_id}`, { method: 'POST' });
    const stage2 = await stage2Resp.json().catch(() => ({}));
    if (!stage2Resp.ok) {
      throw new Error(stage2.detail || stage2.error || 'Stage2 执行失败');
    }

    currentSessionId = stage1.session_id;
    currentStage2 = stage2;
    setStatus(false);
    showResult(stage1, stage2);
    if (stage2.spatial) {
      renderBlueprint(stage2.spatial);
    }
  } catch (error) {
    setStatus(false);
    showError(error.message);
  }
}

async function enterSimulation(sessionId = currentSessionId, btn = document.getElementById('enterSimulationBtn')) {
  if (!sessionId) return;
  btn.disabled = true;
  setStatus(true, '正在同步 Stage3 数据并启动模拟...');
  hideError();

  try {
    const adapterResp = await fetch(`/api/stage3/agentkernel/${encodeURIComponent(sessionId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_ticks: 100 }),
    });
    const adapter = await adapterResp.json().catch(() => ({}));
    if (!adapterResp.ok) {
      throw new Error(adapter.detail || adapter.error || 'Stage3 adapter 同步失败');
    }
    if (adapter.dry_validation_passed === false) {
      throw new Error('Stage3 adapter dry validation 未通过');
    }

    const startResp = await fetch(`/api/stage3/runtime/start/${encodeURIComponent(sessionId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_ticks: 100 }),
    });
    const started = await startResp.json().catch(() => ({}));
    if (!startResp.ok) {
      throw new Error(started.detail || started.error || 'Stage3 runtime 启动失败');
    }

    window.location.href = `/simulation.html?session_id=${encodeURIComponent(sessionId)}`;
  } catch (error) {
    btn.disabled = false;
    setStatus(false);
    showError(error.message);
  }
}

async function generateSpatial() {
  if (!currentSessionId) return;
  setStatus(true, '正在生成空间地图...');
  try {
    const resp = await fetch(`/api/spatial/generate/${currentSessionId}`, { method: 'POST' });
    const spatial = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(spatial.detail || '空间地图生成失败');
    currentStage2 = { ...(currentStage2 || {}), spatial };
    setStatus(false);
    renderBlueprint(spatial);
  } catch (error) {
    setStatus(false);
    showError(error.message);
  }
}

function setStatus(loading, text = '') {
  const section = document.getElementById('statusSection');
  const btn = document.getElementById('submitBtn');
  section.style.display = loading ? 'flex' : 'none';
  document.getElementById('statusText').textContent = text;
  btn.disabled = loading;
}

function hideResult() {
  document.getElementById('resultSection').style.display = 'none';
}

function hideMap() {
  document.getElementById('mapSection').style.display = 'none';
}

function hideError() {
  document.getElementById('errorSection').style.display = 'none';
}

function showError(message) {
  const section = document.getElementById('errorSection');
  section.style.display = 'block';
  document.getElementById('errorText').textContent = `错误：${message}`;
}

function showResult(session, stage2) {
  const section = document.getElementById('resultSection');
  const semantic = stage2.semantic || {};
  const spatial = stage2.spatial || {};
  const validation = spatial.validation || {};
  const locationVisual = spatial.visual?.location_layer || {};
  const visualStatus = locationVisual.status || 'missing';
  const visualMessage = visualStatus === 'ready'
    ? '地点与道路视觉: 已生成并通过评价'
    : visualStatus === 'partial'
      ? `地点与道路视觉: 部分通过${locationVisual.error ? ` (${locationVisual.error})` : ''}`
      : visualStatus === 'failed'
        ? `地点与道路视觉: 生成失败 (${locationVisual.error || '未提供错误信息'})`
        : '地点与道路视觉: 尚未生成';

  section.style.display = 'block';
  document.getElementById('sessionId').textContent = `session: ${session.session_id}`;
  document.getElementById('resultMsg').textContent = [
    'Stage1 + Stage2 已完成',
    `语义数据: ${semantic.location_count || 0} 个地点, ${semantic.path_count || 0} 条路径, ${semantic.character_count || 0} 个角色`,
    `空间地图: ${(spatial.regions || []).length} 个区域, ${(spatial.routes || []).length} 条路线`,
    `地图校验: ${validation.passed ? '通过' : '未通过'}`,
    visualMessage,
  ].join('\n');

  const viewerBtn = document.getElementById('jump-to-viewer-btn');
  if (viewerBtn) {
    viewerBtn.href = `/viewer.html?session_id=${encodeURIComponent(session.session_id)}`;
    viewerBtn.style.display = 'inline-flex';
  }

  const simulationBtn = document.getElementById('enterSimulationBtn');
  if (simulationBtn) {
    simulationBtn.disabled = false;
    simulationBtn.style.display = 'inline-flex';
  }

  const spatialBtn = document.getElementById('spatialBtn');
  if (spatialBtn) spatialBtn.style.display = 'none';
}

function renderBlueprint(spatial) {
  const section = document.getElementById('mapSection');
  const canvas = document.getElementById('mapCanvas');
  const info = document.getElementById('mapInfo');
  const warnings = document.getElementById('mapWarnings');
  const grid = spatial.grid;
  if (!grid || !canvas) return;

  section.style.display = 'block';
  const regions = spatial.regions || [];
  const routes = spatial.routes || [];
  const roadTiles = spatial.road_tiles || [];
  const spawns = spatial.spawn_points || [];
  const tilePx = 4;
  const ctx = canvas.getContext('2d');

  canvas.width = grid.width * tilePx;
  canvas.height = grid.height * tilePx;
  ctx.fillStyle = '#1a1a2e';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.strokeStyle = '#2a2a4a';
  ctx.lineWidth = 0.5;
  for (let x = 0; x <= grid.width; x++) {
    ctx.beginPath();
    ctx.moveTo(x * tilePx, 0);
    ctx.lineTo(x * tilePx, canvas.height);
    ctx.stroke();
  }
  for (let y = 0; y <= grid.height; y++) {
    ctx.beginPath();
    ctx.moveTo(0, y * tilePx);
    ctx.lineTo(canvas.width, y * tilePx);
    ctx.stroke();
  }

  const tagColors = {
    core: 'rgba(168,85,247,0.45)',
    major: 'rgba(59,130,246,0.4)',
    minor: 'rgba(34,197,94,0.35)',
    secret: 'rgba(239,68,68,0.4)',
    public: 'rgba(251,191,36,0.3)',
  };
  for (const region of regions) {
    const b = region.bounds || {};
    let color = 'rgba(100,116,139,0.35)';
    for (const tag of region.tags || []) {
      if (tagColors[tag]) {
        color = tagColors[tag];
        break;
      }
    }
    ctx.fillStyle = color;
    ctx.fillRect(b.x * tilePx, b.y * tilePx, b.w * tilePx, b.h * tilePx);
    ctx.strokeStyle = 'rgba(255,255,255,0.2)';
    ctx.lineWidth = 1;
    ctx.strokeRect(b.x * tilePx, b.y * tilePx, b.w * tilePx, b.h * tilePx);
    ctx.fillStyle = '#fff';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(region.name || region.location_id, (b.x + b.w / 2) * tilePx, (b.y + b.h / 2) * tilePx);
  }

  ctx.fillStyle = '#38bdf8';
  for (const tile of roadTiles) {
    ctx.fillRect(tile.x * tilePx, tile.y * tilePx, tilePx, tilePx);
  }

  ctx.strokeStyle = 'rgba(56,189,248,0.5)';
  ctx.lineWidth = 1;
  for (const route of routes) {
    const line = route.centerline || [];
    if (line.length < 2) continue;
    ctx.beginPath();
    ctx.moveTo(line[0].x * tilePx + tilePx / 2, line[0].y * tilePx + tilePx / 2);
    for (let i = 1; i < line.length; i += 1) {
      ctx.lineTo(line[i].x * tilePx + tilePx / 2, line[i].y * tilePx + tilePx / 2);
    }
    ctx.stroke();
  }

  ctx.fillStyle = '#34d399';
  for (const spawn of spawns) {
    const [sx, sy] = spawn.position || [0, 0];
    ctx.beginPath();
    ctx.arc(sx * tilePx + tilePx / 2, sy * tilePx + tilePx / 2, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  const validation = spatial.validation || {};
  info.textContent = `${regions.length} 地点, ${routes.length} 路线, ${spawns.length} 角色, ${grid.width}x${grid.height} 网格`;
  const issues = validation.issues || [];
  warnings.style.display = issues.length ? 'block' : 'none';
  warnings.textContent = issues.length ? `地图校验问题: ${issues.map((issue) => issue.message).join('; ')}` : '';
}

document.getElementById('worldInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) submitInput();
});

document.querySelectorAll('.prompt-chip').forEach((button) => {
  button.addEventListener('click', () => {
    const input = document.getElementById('worldInput');
    input.value = button.dataset.prompt || button.textContent.trim();
    input.focus();
  });
});

window.addEventListener('pageshow', () => {
  setStatus(false);
  const submitBtn = document.getElementById('submitBtn');
  if (submitBtn) submitBtn.disabled = false;
  const simulationBtn = document.getElementById('enterSimulationBtn');
  if (simulationBtn) simulationBtn.disabled = false;
  loadGeneratedWorlds();
});
