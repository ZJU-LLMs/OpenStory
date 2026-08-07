(function () {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get('session_id');
  const canvas = document.getElementById('mapCanvas');
  const ctx = canvas.getContext('2d');
  const mapWrap = document.querySelector('.map-wrap');
  let tilePx = 16;

  let spatial = null;
  let runtime = null;
  let semanticCharacters = [];
  let semanticLocations = [];
  let worldBackground = null;
  let characterIndex = new Map();
  let locationIndex = new Map();
  let autoTimer = null;
  let autoPlaying = false;
  let tickInFlight = false;
  let runToken = 0;
  let selectedEntity = null;
  let mapZoom = 1;
  let mapFitScale = 1;
  let spatialBaseUrl = '';
  let visualBackgroundImage = null;
  let visualBackgroundSrc = '';
  let visualRoadLayerImage = null;
  let visualRoadLayerSrc = '';
  let visualLocationLayerImage = null;
  let visualLocationLayerSrc = '';
  let visualAssetErrors = new Map();
  let visualLayoutManifest = null;
  let visualManifestPollTimer = null;

  const keyLabels = {
    id: 'ID',
    name: '名称',
    role: '身份',
    type: '类型',
    description: '描述',
    identity: '身份信息',
    state: '状态',
    current_state: '当前状态',
    location: '地点',
    location_id: '地点 ID',
    position: '坐标',
    current_plan: '当前计划',
    current_action: '当前行动',
    current_plan_note: '行动提示',
    short_term_memory: '近期记忆',
    long_term_memory: '长期记忆',
    goals: '目标',
    short_term_goal: '短期目标',
    long_term_goal: '长期目标',
    motivation: '动机',
    personality: '性格',
    traits: '特质',
    values: '价值观',
    speech_style: '说话风格',
    capabilities: '能力',
    skills: '技能',
    level: '水平',
    weaknesses: '弱点',
    social_profile: '社会关系',
    group_id: '所属群体',
    reputation: '声望',
    access: '访问规则',
    permissions: '权限',
    access_level: '访问等级',
    access_conditions: '进入条件',
    ownership: '归属',
    capacity: '容量',
    tags: '标签',
    memories: '记忆',
    knowledge: '知识',
    background_summary: '背景摘要',
    key_events: '关键事件',
    secrets: '秘密',
  };

  initLabels();
  wireEvents();
  boot();

  function initLabels() {
    document.title = 'OpenStory WorldKernel Simulation';
    document.getElementById('sessionLabel').textContent = `一句生成世界，自主模拟角色命运与故事发展 · ${sessionId || '-'}`;
    setButtonLabel('tickBtn', '推进 Tick');
    setButtonLabel('autoBtn', '自动播放');
    setButtonLabel('stopBtn', '停止模拟');
  }

  function setButtonLabel(id, label) {
    const button = document.getElementById(id);
    if (!button) return;
    const labelNode = button.querySelector('.control-label');
    if (labelNode) labelNode.textContent = label;
    else button.textContent = label;
  }

  function wireEvents() {
    document.getElementById('tickBtn').addEventListener('click', tickOnce);
    document.getElementById('autoBtn').addEventListener('click', toggleAuto);
    document.getElementById('stopBtn').addEventListener('click', stopRuntime);
    document.getElementById('worldViewBtn').addEventListener('click', closeDetail);
    document.getElementById('worldSettingsBtn').addEventListener('click', openWorldDetail);
    document.getElementById('charactersBtn').addEventListener('click', openCharacterOverview);
    document.getElementById('zoomOutBtn').addEventListener('click', () => zoomMap(1 / 1.18));
    document.getElementById('zoomInBtn').addEventListener('click', () => zoomMap(1.18));
    document.getElementById('resetViewBtn').addEventListener('click', resetMapView);
    document.getElementById('detailClose').addEventListener('click', closeDetail);
    document.getElementById('detailOverlay').addEventListener('click', (event) => {
      if (event.target.id === 'detailOverlay') closeDetail();
    });
    window.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeDetail();
    });
    canvas.addEventListener('click', handleMapClick);
    canvas.addEventListener('mousemove', handleMapHover);
    mapWrap?.addEventListener('wheel', handleMapWheel, { passive: false });
    window.addEventListener('resize', applyMapZoom);
    window.addEventListener('beforeunload', stopVisualManifestPolling);
  }

  async function boot() {
    if (!sessionId) {
      showError('URL 缺少 session_id');
      return;
    }

    try {
      const spatialUrl = `/api/stage1/session/${encodeURIComponent(sessionId)}/generated/artifacts/spatial/spatial_blueprint.json`;
      spatialBaseUrl = spatialUrl.replace(/\/[^/]*$/, '/');
      const [spatialData, runtimeState, charData, locData, worldData, visualManifestData] = await Promise.all([
        fetchJson(spatialUrl),
        fetchJson('/api/stage3/runtime/state'),
        fetchOptionalJson(`/api/stage1/session/${encodeURIComponent(sessionId)}/generated/artifacts/semantic/characters/characters.json`),
        fetchOptionalJson(`/api/stage1/session/${encodeURIComponent(sessionId)}/generated/artifacts/semantic/locations/locations.json`),
        fetchOptionalJson(`/api/stage1/session/${encodeURIComponent(sessionId)}/generated/plan/world_background.json`),
        fetchOptionalJson(`/api/stage1/session/${encodeURIComponent(sessionId)}/generated/artifacts/spatial/visual_layout_manifest.json`),
      ]);

      spatial = spatialData;
      tilePx = Math.max(1, Number(spatial?.grid?.tile_size) || 16);
      runtime = runtimeState;
      semanticCharacters = normalizeItems(charData);
      semanticLocations = normalizeItems(locData);
      worldBackground = worldData;
      visualLayoutManifest = visualManifestData;
      rebuildSemanticIndexes();
      prepareVisualAssets();
      startVisualManifestPolling();
      render();
    } catch (error) {
      showError(error.message);
    }
  }

  async function tickOnce(options = {}) {
    if (tickInFlight) return runtime;
    const token = options.token ?? runToken;
    tickInFlight = true;
    setBusy(true);
    try {
      const nextRuntime = await fetchJson('/api/stage3/runtime/tick', { method: 'POST' });
      if (token === runToken && !options.ignoreResult) {
        runtime = nextRuntime;
        render();
        refreshOpenDetail();
      }
      return nextRuntime;
    } catch (error) {
      if (token === runToken) showError(error.message);
      return runtime;
    } finally {
      tickInFlight = false;
      setBusy(false);
    }
  }

  function toggleAuto() {
    if (autoPlaying) {
      stopAutoPlayback();
      return;
    }
    startAutoPlayback();
  }

  function startAutoPlayback() {
    autoPlaying = true;
    runToken += 1;
    document.body.classList.add('is-autoplaying');
    setButtonLabel('autoBtn', '暂停');
    renderState();
    scheduleAutoTick(runToken);
  }

  function stopAutoPlayback() {
    autoPlaying = false;
    runToken += 1;
    if (autoTimer) {
      clearTimeout(autoTimer);
      autoTimer = null;
    }
    document.body.classList.remove('is-autoplaying');
    setButtonLabel('autoBtn', '自动播放');
    renderState();
  }

  function scheduleAutoTick(token) {
    if (!autoPlaying || token !== runToken) return;
    autoTimer = setTimeout(async () => {
      autoTimer = null;
      await tickOnce({ token });
      scheduleAutoTick(token);
    }, 2500);
  }

  async function stopRuntime() {
    stopAutoPlayback();
    setBusy(true);
    try {
      runtime = await fetchJson('/api/stage3/runtime/stop', { method: 'POST' });
      selectedEntity = null;
      closeDetail();
      render();
    } catch (error) {
      showError(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || data.error || response.statusText);
    }
    return data;
  }

  async function fetchOptionalJson(url) {
    const response = await fetch(url);
    if (!response.ok) return null;
    return response.json().catch(() => null);
  }

  function normalizeItems(data) {
    if (!data) return [];
    if (Array.isArray(data)) return data;
    if (Array.isArray(data.items)) return data.items;
    return [];
  }

  function rebuildSemanticIndexes() {
    characterIndex = new Map();
    locationIndex = new Map();
    for (const character of semanticCharacters) {
      addIndex(characterIndex, character, [
        character.id,
        character.wk_entity_id,
        character.identity?.id,
        character.identity?.name,
        character.name,
      ]);
    }
    for (const location of semanticLocations) {
      addIndex(locationIndex, location, [
        location.id,
        location.location_id,
        location.identity?.id,
        location.identity?.name,
        location.name,
      ]);
    }
  }

  function addIndex(index, item, keys) {
    for (const key of keys) {
      if (key !== undefined && key !== null && key !== '') {
        index.set(String(key), item);
      }
    }
  }

  function prepareVisualAssets() {
    const visual = getActiveVisualManifest();
    const background = visual?.background || {};
    const backgroundFallbackVersion = [
      background.model || 'background',
      background.width_px || visual?.canvas?.width_px || 0,
      background.height_px || visual?.canvas?.height_px || 0,
      background.generation_strategy || '',
    ].join('-');
    const backgroundSrc = background.url && background.status === 'ready'
      ? resolveVersionedVisualUrl(
          background.url,
          background.asset_version || backgroundFallbackVersion
        )
      : '';
    if (backgroundSrc && backgroundSrc !== visualBackgroundSrc) {
      visualBackgroundSrc = backgroundSrc;
      visualBackgroundImage = new Image();
      visualBackgroundImage.onload = renderMap;
      visualBackgroundImage.onerror = renderMap;
      visualBackgroundImage.src = backgroundSrc;
    } else if (!backgroundSrc) {
      visualBackgroundSrc = '';
      visualBackgroundImage = null;
    }

    const routeLayer = visual?.route_layer || {};
    const routeFallbackVersion = [
      routeLayer.model || 'road',
      routeLayer.width_px || 0,
      routeLayer.height_px || 0,
    ].join('-');
    const routeLayerSrc = routeLayer.url && routeLayer.status === 'ready'
      ? resolveVersionedVisualUrl(
          routeLayer.url,
          routeLayer.asset_version || routeFallbackVersion
        )
      : '';
    if (routeLayerSrc && routeLayerSrc !== visualRoadLayerSrc) {
      visualRoadLayerSrc = routeLayerSrc;
      visualRoadLayerImage = new Image();
      visualRoadLayerImage.onload = () => {
        const expectedWidth = Number(routeLayer.width_px || visual?.canvas?.width_px || 0);
        const expectedHeight = Number(routeLayer.height_px || visual?.canvas?.height_px || 0);
        if (
          visualRoadLayerImage.naturalWidth !== expectedWidth ||
          visualRoadLayerImage.naturalHeight !== expectedHeight
        ) {
          reportVisualAssetError(
            'route-layer',
            `道路图层尺寸错误：${visualRoadLayerImage.naturalWidth}x${visualRoadLayerImage.naturalHeight}，应为 ${expectedWidth}x${expectedHeight}`
          );
          visualRoadLayerImage = null;
        } else {
          visualAssetErrors.delete('route-layer');
        }
        renderMap();
      };
      visualRoadLayerImage.onerror = () => {
        reportVisualAssetError('route-layer', `道路图层加载失败：${routeLayerSrc}`);
        visualRoadLayerImage = null;
        renderMap();
      };
      visualRoadLayerImage.src = routeLayerSrc;
    } else if (!routeLayerSrc) {
      visualRoadLayerSrc = '';
      visualRoadLayerImage = null;
      visualAssetErrors.delete('route-layer');
    }

    const locationLayer = visual?.location_layer || {};
    const locationFallbackVersion = [
      locationLayer.model || 'locations',
      locationLayer.width_px || 0,
      locationLayer.height_px || 0,
      (locationLayer.completed_location_ids || []).length,
    ].join('-');
    const locationLayerSrc = locationLayer.url && ['ready', 'partial'].includes(locationLayer.status)
      ? resolveVersionedVisualUrl(
          locationLayer.url,
          locationLayer.asset_version || locationFallbackVersion
        )
      : '';
    if (locationLayerSrc && locationLayerSrc !== visualLocationLayerSrc) {
      visualLocationLayerSrc = locationLayerSrc;
      visualLocationLayerImage = new Image();
      visualLocationLayerImage.onload = () => {
        const expectedWidth = Number(locationLayer.width_px || visual?.canvas?.width_px || 0);
        const expectedHeight = Number(locationLayer.height_px || visual?.canvas?.height_px || 0);
        if (
          visualLocationLayerImage.naturalWidth !== expectedWidth ||
          visualLocationLayerImage.naturalHeight !== expectedHeight
        ) {
          reportVisualAssetError(
            'location-layer',
            `地点图层尺寸错误：${visualLocationLayerImage.naturalWidth}x${visualLocationLayerImage.naturalHeight}，应为 ${expectedWidth}x${expectedHeight}`
          );
          visualLocationLayerImage = null;
        } else {
          visualAssetErrors.delete('location-layer');
        }
        renderMap();
      };
      visualLocationLayerImage.onerror = () => {
        reportVisualAssetError('location-layer', `地点图层加载失败：${locationLayerSrc}`);
        visualLocationLayerImage = null;
        renderMap();
      };
      visualLocationLayerImage.src = locationLayerSrc;
    } else if (!locationLayerSrc) {
      visualLocationLayerSrc = '';
      visualLocationLayerImage = null;
      visualAssetErrors.delete('location-layer');
    }
  }

  function reportVisualAssetError(key, message) {
    visualAssetErrors.set(key, message);
    console.error(`[WorldKernel visual] ${message}`);
  }

  function getActiveVisualManifest() {
    return visualLayoutManifest || spatial?.visual || {};
  }

  function startVisualManifestPolling() {
    stopVisualManifestPolling();
    visualManifestPollTimer = window.setInterval(refreshVisualManifest, 3500);
  }

  function stopVisualManifestPolling() {
    if (!visualManifestPollTimer) return;
    window.clearInterval(visualManifestPollTimer);
    visualManifestPollTimer = null;
  }

  async function refreshVisualManifest() {
    if (!sessionId || !spatialBaseUrl) return;
    const nextManifest = await fetchOptionalJson(`${spatialBaseUrl}visual_layout_manifest.json`);
    if (!nextManifest) return;
    const previousKey = buildVisualPatchStateKey(visualLayoutManifest);
    const nextKey = buildVisualPatchStateKey(nextManifest);
    visualLayoutManifest = nextManifest;
    if (previousKey !== nextKey) {
      prepareVisualAssets();
      renderMap();
    }
  }

  function buildVisualPatchStateKey(visual) {
    const background = visual?.background || {};
    const routeLayer = visual?.route_layer || {};
    const locationLayer = visual?.location_layer || {};
    return [
      background.status || '',
      background.url || '',
      background.asset_version || '',
      background.generation_strategy || '',
      (background.composited_layers || []).join(','),
      routeLayer.status || '',
      routeLayer.url || '',
      routeLayer.asset_version || '',
      locationLayer.status || '',
      locationLayer.url || '',
      locationLayer.asset_version || '',
      (locationLayer.completed_location_ids || []).join(','),
    ].join('|');
  }

  function resolveVisualUrl(url) {
    if (/^https?:\/\//.test(url) || url.startsWith('/')) return url;
    return `${spatialBaseUrl}${url}`;
  }

  function resolveVersionedVisualUrl(url, version) {
    const resolved = resolveVisualUrl(url);
    if (!version) return resolved;
    const separator = resolved.includes('?') ? '&' : '?';
    return `${resolved}${separator}v=${encodeURIComponent(version)}`;
  }

  function render() {
    renderMap();
    renderState();
    hideError();
  }

  function renderMap() {
    if (!spatial?.grid) return;
    const grid = spatial.grid;
    const regions = spatial.regions || [];
    const routes = spatial.routes || [];
    const roadTiles = spatial.road_tiles || [];
    const spawns = spatial.spawn_points || [];
    const agents = runtime?.agents || [];
    const visual = getActiveVisualManifest();
    const compositedLayers = new Set(visual?.background?.composited_layers || []);

    canvas.width = grid.width * tilePx;
    canvas.height = grid.height * tilePx;
    ctx.imageSmoothingEnabled = false;
    drawMapBase(grid);

    const hasGeneratedRoadLayer = Boolean(
      visualRoadLayerImage?.complete && visualRoadLayerImage.naturalWidth > 0
    );
    drawLocationLayer();
    if (hasGeneratedRoadLayer) {
      drawRoadTextureLayer();
    } else if (!compositedLayers.has('route_layer')) {
      drawRoutes(routes, roadTiles, regions);
    }
    for (const region of regions) {
      const hasPatch = hasReadyLocationVisual(region);
      drawRegion(
        region,
        selectedEntity?.type === 'location' && selectedEntity.id === region.location_id,
        compositedLayers.has('location_placeholder_layer') || hasPatch
      );
    }

    const spawnById = new Map();
    for (const spawn of spawns) {
      addIndex(spawnById, spawn, [spawn.character_id, spawn.character_name]);
    }
    for (const agent of agents) {
      const fallback = spawnById.get(agent.id) || spawnById.get(agent.profile?.name);
      drawAgent(
        getAgentPosition(agent, fallback),
        agent.profile?.name || agent.id,
        !agent.is_active,
        selectedEntity?.type === 'agent' && selectedEntity.id === agent.id
      );
    }

    document.getElementById('mapInfo').textContent =
      `${regions.length} 地点 · ${routes.length} 路线 · ${agents.length || spawns.length} 角色`;
    updateCount('locationCount', regions.length);
    updateCount('routeCount', routes.length);
    applyMapZoom();
  }

  function drawMapBase(grid) {
    if (visualBackgroundImage?.complete && visualBackgroundImage.naturalWidth > 0) {
      ctx.drawImage(visualBackgroundImage, 0, 0, canvas.width, canvas.height);
      return;
    }
    ctx.fillStyle = '#f5e4c0';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = 'rgba(255,255,255,0.22)';
    for (let y = 0; y < grid.height; y += 2) {
      ctx.fillRect(0, y * tilePx, canvas.width, tilePx);
    }
    ctx.strokeStyle = 'rgba(167,113,48,0.12)';
    ctx.lineWidth = 0.5;
    for (let x = 0; x <= grid.width; x += 4) {
      ctx.beginPath();
      ctx.moveTo(x * tilePx, 0);
      ctx.lineTo(x * tilePx, canvas.height);
      ctx.stroke();
    }
    for (let y = 0; y <= grid.height; y += 4) {
      ctx.beginPath();
      ctx.moveTo(0, y * tilePx);
      ctx.lineTo(canvas.width, y * tilePx);
      ctx.stroke();
    }
  }

  function drawLocationLayer() {
    if (!visualLocationLayerImage?.complete || visualLocationLayerImage.naturalWidth <= 0) return;
    if (
      visualLocationLayerImage.naturalWidth !== canvas.width ||
      visualLocationLayerImage.naturalHeight !== canvas.height
    ) return;
    ctx.drawImage(visualLocationLayerImage, 0, 0);
  }

  function hasReadyLocationVisual(region) {
    if (!visualLocationLayerImage?.complete || visualLocationLayerImage.naturalWidth <= 0) {
      return false;
    }
    const completed = getActiveVisualManifest()?.location_layer?.completed_location_ids || [];
    return completed.includes(String(region.location_id));
  }

  function drawRoadTextureLayer() {
    if (!visualRoadLayerImage?.complete || visualRoadLayerImage.naturalWidth <= 0) return;
    if (
      visualRoadLayerImage.naturalWidth !== canvas.width ||
      visualRoadLayerImage.naturalHeight !== canvas.height
    ) return;
    ctx.drawImage(visualRoadLayerImage, 0, 0);
  }

  function drawRegion(region, selected, precomposited) {
    const unit = tilePx / 4;
    const b = region.bounds || {};
    const location = getLocationProfile(region.location_id) || region;
    const placeholderStyle = getActiveVisualManifest()?.location_placeholder_layer?.style || {};
    const left = b.x * tilePx;
    const top = b.y * tilePx;
    const width = b.w * tilePx;
    const height = b.h * tilePx;
    if (!precomposited || selected) {
      ctx.fillStyle = selected
        ? (placeholderStyle.selected_fill_color || 'rgba(232,199,102,0.48)')
        : (placeholderStyle.fill_color || 'rgba(45,55,78,0.64)');
      ctx.fillRect(left, top, width, height);
    }
    if (!precomposited) {
      ctx.fillStyle = selected ? 'rgba(255,255,255,0.16)' : 'rgba(255,255,255,0.1)';
      for (let y = top + tilePx; y < top + height; y += tilePx) {
        ctx.fillRect(left, y, width, Math.max(1, unit / 2));
      }
    }
    if (!precomposited || selected) {
      ctx.strokeStyle = selected
        ? (placeholderStyle.selected_border_color || 'rgba(215,162,74,0.96)')
        : (placeholderStyle.border_color || 'rgba(230,235,245,0.72)');
      ctx.lineWidth = (selected ? 1.5 : 0.6) * unit;
      ctx.strokeRect(left, top, width, height);
    }
    const label = String(location.name || region.name || region.location_id || '地点');
    ctx.font = `700 ${7 * unit}px "Microsoft YaHei", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const centerX = (b.x + b.w / 2) * tilePx;
    const centerY = (b.y + b.h / 2) * tilePx;
    const labelWidth = Math.min(Math.max(24 * unit, ctx.measureText(label).width + 8 * unit), Math.max(30 * unit, b.w * tilePx - 3 * unit));
    ctx.fillStyle = selected ? 'rgba(88,61,30,0.9)' : 'rgba(27,34,49,0.84)';
    ctx.fillRect(centerX - labelWidth / 2, centerY - 6 * unit, labelWidth, 12 * unit);
    ctx.strokeStyle = selected ? 'rgba(246,201,99,0.9)' : 'rgba(230,235,245,0.46)';
    ctx.lineWidth = 0.7 * unit;
    ctx.strokeRect(centerX - labelWidth / 2 + 0.5 * unit, centerY - 5.5 * unit, labelWidth - unit, 11 * unit);
    ctx.fillStyle = placeholderStyle.label_color || '#f4f6fb';
    ctx.fillText(label, centerX, centerY, labelWidth - 5 * unit);
  }

  function drawRoutes(routes, roadTiles, regions) {
    const unit = tilePx / 4;
    const isInsideLocation = (point) => regions.some((region) => {
      const b = region.bounds || {};
      return point.x >= b.x && point.x < b.x + b.w && point.y >= b.y && point.y < b.y + b.h;
    });
    ctx.fillStyle = '#7fa6ba';
    for (const tile of roadTiles) {
      if (isInsideLocation(tile)) continue;
      ctx.fillRect(tile.x * tilePx, tile.y * tilePx, tilePx, tilePx);
    }
    ctx.strokeStyle = 'rgba(67,118,148,0.68)';
    ctx.lineWidth = unit;
    for (const route of routes) {
      const line = route.centerline || [];
      if (line.length < 2) continue;
      ctx.beginPath();
      let drawing = false;
      for (const point of line) {
        if (isInsideLocation(point)) {
          drawing = false;
          continue;
        }
        const x = point.x * tilePx + tilePx / 2;
        const y = point.y * tilePx + tilePx / 2;
        if (!drawing) {
          ctx.moveTo(x, y);
          drawing = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
    }
  }

  function drawAgent(position, name, inactive, selected) {
    const unit = tilePx / 4;
    const [x, y] = position;
    const px = x * tilePx + tilePx / 2;
    const py = y * tilePx + tilePx / 2;
    const size = (selected ? 12 : 10) * unit;
    const half = Math.floor(size / 2);
    ctx.fillStyle = 'rgba(103,69,29,0.22)';
    ctx.fillRect(px - half + 2 * unit, py + half, size, 3 * unit);
    ctx.fillStyle = selected ? '#f2c85c' : (inactive ? '#9aa3ad' : '#2aa69c');
    ctx.fillRect(px - half, py - half, size, size);
    ctx.fillStyle = inactive ? '#d6dce2' : '#fff7e8';
    ctx.fillRect(px - half + 2 * unit, py - half + 2 * unit, Math.max(3 * unit, size - 4 * unit), 2 * unit);
    ctx.strokeStyle = selected ? '#9b6b2f' : '#27345a';
    ctx.lineWidth = (selected ? 2 : 1) * unit;
    ctx.strokeRect(px - half - 0.5 * unit, py - half - 0.5 * unit, size + unit, size + unit);

    const label = String(name || '?').trim().slice(0, 1);
    ctx.font = `700 ${7 * unit}px "Microsoft YaHei", sans-serif`;
    ctx.fillStyle = inactive ? '#66708b' : '#27345a';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, px, py + 0.5 * unit, size - 2 * unit);
  }

  function renderState() {
    const agents = runtime?.agents || [];
    const isStarted = Boolean(runtime?.started);
    document.body.classList.toggle('runtime-active', isStarted);
    updateCount('tickValue', runtime?.current_tick ?? 0);
    updateCount('agentCount', agents.length);
    document.getElementById('runtimeStatus').textContent = isStarted
      ? (autoPlaying ? '自动推进中' : '模拟运行中')
      : '模拟未运行';
  }

  function updateCount(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  }

  function handleMapClick(event) {
    const hit = hitTestMap(event);
    if (!hit) return;
    if (hit.type === 'agent') {
      openAgentDetail(hit.agent);
    } else if (hit.type === 'location') {
      openLocationDetail(hit.region);
    }
  }

  function handleMapHover(event) {
    canvas.style.cursor = hitTestMap(event) ? 'pointer' : 'default';
  }

  function hitTestMap(event) {
    if (!spatial) return null;
    const point = eventToCanvasPoint(event);
    const agents = runtime?.agents || [];
    const spawns = spatial.spawn_points || [];
    const spawnById = new Map();
    for (const spawn of spawns) {
      addIndex(spawnById, spawn, [spawn.character_id, spawn.character_name]);
    }

    for (let i = agents.length - 1; i >= 0; i -= 1) {
      const agent = agents[i];
      const fallback = spawnById.get(agent.id) || spawnById.get(agent.profile?.name);
      const position = getAgentPosition(agent, fallback);
      const ax = position[0] * tilePx + tilePx / 2;
      const ay = position[1] * tilePx + tilePx / 2;
      if (Math.hypot(point.x - ax, point.y - ay) <= 9 * (tilePx / 4)) {
        return { type: 'agent', agent };
      }
    }

    const tx = Math.floor(point.x / tilePx);
    const ty = Math.floor(point.y / tilePx);
    const regions = spatial.regions || [];
    for (let i = regions.length - 1; i >= 0; i -= 1) {
      const region = regions[i];
      const b = region.bounds || {};
      if (tx >= b.x && tx < b.x + b.w && ty >= b.y && ty < b.y + b.h) {
        return { type: 'location', region };
      }
    }
    return null;
  }

  function eventToCanvasPoint(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) * (canvas.width / rect.width),
      y: (event.clientY - rect.top) * (canvas.height / rect.height),
    };
  }

  function handleMapWheel(event) {
    if (!spatial?.grid || !mapWrap) return;
    event.preventDefault();
    const rect = mapWrap.getBoundingClientRect();
    const anchor = {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
    const step = event.deltaY < 0 ? 1.12 : 1 / 1.12;
    mapZoom = clampMapZoom(mapZoom * step);
    applyMapZoom(anchor);
  }

  function zoomMap(factor) {
    if (!spatial?.grid || !mapWrap) return;
    mapZoom = clampMapZoom(mapZoom * factor);
    applyMapZoom({ x: mapWrap.clientWidth / 2, y: mapWrap.clientHeight / 2 });
  }

  function resetMapView() {
    mapZoom = 1;
    applyMapZoom();
    if (mapWrap) {
      mapWrap.scrollLeft = 0;
      mapWrap.scrollTop = 0;
    }
  }

  function applyMapZoom(anchor) {
    if (!mapWrap || !canvas.width || !canvas.height) return;
    const style = window.getComputedStyle(mapWrap);
    const padX = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
    const padY = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const availableWidth = Math.max(1, mapWrap.clientWidth - padX);
    const availableHeight = Math.max(1, mapWrap.clientHeight - padY);
    mapFitScale = Math.min(availableWidth / canvas.width, availableHeight / canvas.height);

    const previousRect = canvas.getBoundingClientRect();
    const previousWidth = previousRect.width || canvas.width * mapFitScale;
    const previousHeight = previousRect.height || canvas.height * mapFitScale;
    const scale = snapMapDisplayScale(Math.max(0.2, mapFitScale * mapZoom));
    canvas.style.width = `${Math.max(1, Math.round(canvas.width * scale))}px`;
    canvas.style.height = `${Math.max(1, Math.round(canvas.height * scale))}px`;

    if (anchor) {
      const nextWidth = canvas.getBoundingClientRect().width;
      const nextHeight = canvas.getBoundingClientRect().height;
      mapWrap.scrollLeft = (mapWrap.scrollLeft + anchor.x) * (nextWidth / previousWidth) - anchor.x;
      mapWrap.scrollTop = (mapWrap.scrollTop + anchor.y) * (nextHeight / previousHeight) - anchor.y;
    }
  }

  function clampMapZoom(value) {
    const fitScale = Math.max(0.01, mapFitScale || 1);
    const maxZoom = Math.max(3.2, 3 / fitScale);
    return Math.min(maxZoom, Math.max(0.65, value));
  }

  function snapMapDisplayScale(scale) {
    if (scale < 0.9) return scale;
    if (scale < 1.5) return 1;
    if (scale < 2.5) return 2;
    return 3;
  }

  function openWorldDetail() {
    setActiveNav('worldSettingsBtn');
    const world = worldBackground || {};
    const title = world.world_name || world.name || '世界设定';
    const summary = world.world_origin_summary || world.description || '';
    const sections = Object.entries(world)
      .filter(([key, value]) => !['world_name', 'name', 'world_origin_summary', 'description', 'raw'].includes(key) && !isEmptyValue(value))
      .map(([key, value]) => `
        <section class="detail-section ${typeof value === 'object' ? 'wide' : ''}">
          <div class="section-title">${escapeHtml(labelKey(key))}</div>
          ${renderObject(value)}
        </section>
      `).join('');

    setDetailHeader('World Setting', title, summary);
    document.getElementById('detailBody').innerHTML = `
      <div class="detail-grid world-detail">
        ${summary ? `<section class="detail-section wide world-summary"><div class="section-title">世界背景</div><div class="value">${escapeHtml(summary)}</div></section>` : ''}
        ${sections || '<section class="detail-section wide"><div class="muted">当前会话暂无世界背景资料</div></section>'}
      </div>
    `;
    openDetail();
  }

  function openCharacterOverview() {
    setActiveNav('charactersBtn');
    const runtimeAgents = runtime?.agents || [];
    const profiles = semanticCharacters.length
      ? semanticCharacters
      : runtimeAgents.map((agent) => agent.profile || { id: agent.id, name: agent.id });

    setDetailHeader('Characters', '角色总览', `${profiles.length} 位角色`);
    document.getElementById('detailBody').innerHTML = `
      <div class="character-overview">
        ${profiles.map((profile, index) => {
          const id = profile.id || profile.wk_entity_id || profile.identity?.id || `profile-${index}`;
          const name = profile.name || profile.identity?.name || id;
          const role = profile.role || profile.identity?.role || profile.identity?.rank || '角色';
          const runtimeAgent = findRuntimeAgentForProfile(profile);
          const locationName = runtimeAgent ? getLocationName(runtimeAgent.location_id || runtimeAgent.current_location) : '';
          return `
            <button class="character-entry" type="button" data-profile-id="${escapeHtml(id)}">
              <span class="character-portrait" aria-hidden="true"></span>
              <span class="character-copy">
                <strong>${escapeHtml(name)}</strong>
                <span>${escapeHtml([role, locationName].filter(Boolean).join(' · '))}</span>
              </span>
              <span class="character-arrow" aria-hidden="true">›</span>
            </button>
          `;
        }).join('') || '<div class="empty-state">当前会话暂无角色资料</div>'}
      </div>
    `;

    document.querySelectorAll('[data-profile-id]').forEach((button) => {
      button.addEventListener('click', () => {
        const profile = profiles.find((item, index) => (
          String(item.id || item.wk_entity_id || item.identity?.id || `profile-${index}`) === button.dataset.profileId
        ));
        if (profile) openAgentDetail(findRuntimeAgentForProfile(profile) || virtualAgentForProfile(profile));
      });
    });
    openDetail();
  }

  function findRuntimeAgentForProfile(profile) {
    const keys = [profile.id, profile.wk_entity_id, profile.identity?.id, profile.name, profile.identity?.name]
      .filter(Boolean).map(String);
    return (runtime?.agents || []).find((agent) => {
      const agentKeys = [agent.id, agent.profile?.id, agent.profile?.wk_entity_id, agent.profile?.name]
        .filter(Boolean).map(String);
      return agentKeys.some((key) => keys.includes(key));
    }) || null;
  }

  function virtualAgentForProfile(profile) {
    const id = profile.id || profile.wk_entity_id || profile.identity?.id || profile.name;
    return {
      id,
      profile: {
        id,
        wk_entity_id: profile.wk_entity_id || profile.identity?.id,
        name: profile.name || profile.identity?.name || id,
      },
      is_active: false,
      inactive_reason: '尚未进入运行状态',
      position: [],
      short_term_memory: [],
    };
  }

  function setActiveNav(id) {
    document.querySelectorAll('.nav-item').forEach((button) => {
      button.classList.toggle('active', button.id === id);
    });
  }

  function openAgentDetail(agent) {
    setActiveNav('charactersBtn');
    selectedEntity = { type: 'agent', id: agent.id };
    renderMap();
    renderState();

    const profile = getCharacterProfile(agent) || {};
    const name = agent.profile?.name || profile.name || profile.identity?.name || agent.id;
    const locationName = getLocationName(agent.location_id || agent.current_location);
    const recentMemory = normalizeMemory(agent.short_term_memory).slice(-5).reverse();

    setDetailHeader('Character', name, [agent.id, locationName].filter(Boolean).join(' · '));
    document.getElementById('detailBody').innerHTML = `
      <div class="detail-grid">
        <section class="detail-section wide">
          <div class="section-title">当前行动</div>
          ${renderKvRows({
            '所在地点': locationName || agent.location_id || '未知',
            '坐标': JSON.stringify(agent.position || []),
            '当前计划': normalizePlan(agent.current_plan) || '暂无',
            '当前行动': agent.current_action || '暂无',
            '行动提示': agent.current_plan_note || '',
            '状态': agent.is_active ? '活跃' : (agent.inactive_reason || '未激活'),
          })}
        </section>
        <section class="detail-section">
          <div class="section-title">身份信息</div>
          ${renderObject(profile.identity || pick(profile, ['name', 'role', 'type', 'description']))}
        </section>
        <section class="detail-section">
          <div class="section-title">目标与动机</div>
          ${renderObject(profile.goals || pick(profile, ['short_term_goal', 'long_term_goal', 'motivation']))}
        </section>
        <section class="detail-section">
          <div class="section-title">性格</div>
          ${renderObject(profile.personality || pick(profile, ['traits', 'values', 'speech_style']))}
        </section>
        <section class="detail-section">
          <div class="section-title">能力</div>
          ${renderObject(profile.capabilities || {})}
        </section>
        <section class="detail-section wide">
          <div class="section-title">近期记忆</div>
          ${recentMemory.length ? renderMemoryList(recentMemory) : '<div class="muted">暂无</div>'}
        </section>
      </div>
    `;
    openDetail();
  }

  function openLocationDetail(region) {
    setActiveNav('worldViewBtn');
    const location = getLocationProfile(region.location_id) || region;
    const agents = agentsAtLocation(region.location_id);
    selectedEntity = { type: 'location', id: region.location_id };
    renderMap();
    renderState();

    setDetailHeader('Location', location.name || region.name || region.location_id, region.location_id || location.id || '');
    document.getElementById('detailBody').innerHTML = `
      <div class="detail-grid">
        <section class="detail-section wide">
          <div class="section-title">地点概况</div>
          ${renderKvRows({
            '类型': location.type || '',
            '描述': location.description || location.identity?.description || '',
            '容量': location.capacity || location.state?.capacity || '',
            '坐标区域': formatBounds(region.bounds || location.bounds),
          })}
          ${renderTags(location.tags || region.tags || [])}
        </section>
        <section class="detail-section">
          <div class="section-title">当前状态</div>
          ${renderObject(location.state || {})}
        </section>
        <section class="detail-section">
          <div class="section-title">访问规则</div>
          ${renderObject(location.access || {})}
        </section>
        <section class="detail-section wide">
          <div class="section-title">在场角色</div>
          ${agents.length ? renderAgentRows(agents) : '<div class="muted">暂无角色停留</div>'}
        </section>
      </div>
    `;
    document.querySelectorAll('[data-modal-agent-id]').forEach((button) => {
      button.addEventListener('click', () => {
        const agent = (runtime?.agents || []).find((item) => item.id === button.dataset.modalAgentId);
        if (agent) openAgentDetail(agent);
      });
    });
    openDetail();
  }

  function refreshOpenDetail() {
    if (!selectedEntity) return;
    if (selectedEntity.type === 'agent') {
      const agent = (runtime?.agents || []).find((item) => item.id === selectedEntity.id);
      if (agent) openAgentDetail(agent);
    } else if (selectedEntity.type === 'location') {
      const region = (spatial?.regions || []).find((item) => item.location_id === selectedEntity.id);
      if (region) openLocationDetail(region);
    }
  }

  function setDetailHeader(kicker, title, subtitle) {
    document.getElementById('detailKicker').textContent = kicker;
    document.getElementById('detailTitle').textContent = title;
    document.getElementById('detailSubtitle').textContent = subtitle;
  }

  function openDetail() {
    const overlay = document.getElementById('detailOverlay');
    overlay.classList.add('active');
    overlay.setAttribute('aria-hidden', 'false');
  }

  function closeDetail() {
    const overlay = document.getElementById('detailOverlay');
    overlay.classList.remove('active');
    overlay.setAttribute('aria-hidden', 'true');
    setActiveNav('worldViewBtn');
    selectedEntity = null;
    renderMap();
    renderState();
  }

  function getCharacterProfile(agent) {
    return characterIndex.get(agent.id)
      || characterIndex.get(agent.profile?.id)
      || characterIndex.get(agent.profile?.wk_entity_id)
      || characterIndex.get(agent.profile?.name)
      || characterIndex.get(agent.id?.replaceAll('-', '_'));
  }

  function getLocationProfile(locationIdOrName) {
    if (!locationIdOrName) return null;
    return locationIndex.get(locationIdOrName)
      || locationIndex.get(String(locationIdOrName).replaceAll('-', '_'))
      || null;
  }

  function getLocationName(locationIdOrName) {
    const location = getLocationProfile(locationIdOrName);
    return location?.name || location?.identity?.name || locationIdOrName || '';
  }

  function getAgentPosition(agent, fallback) {
    const position = agent.position || fallback?.position || [0, 0];
    if (Array.isArray(position)) return position;
    if (typeof position === 'object') return [Number(position.x || 0), Number(position.y || 0)];
    return [0, 0];
  }

  function agentsAtLocation(locationId) {
    return (runtime?.agents || []).filter((agent) => {
      if (agent.location_id === locationId || agent.current_location === locationId) return true;
      const loc = getLocationProfile(agent.location_id || agent.current_location);
      return loc?.id === locationId || loc?.identity?.id === locationId;
    });
  }

  function normalizePlan(plan) {
    if (!plan) return '';
    if (Array.isArray(plan)) {
      const [action, time, target, location, importance] = plan;
      return [
        action ? `行动: ${action}` : '',
        time !== undefined ? `时段: ${time}` : '',
        target ? `对象: ${target}` : '',
        location ? `地点: ${getLocationName(location)}` : '',
        importance !== undefined ? `重要性: ${importance}` : '',
      ].filter(Boolean).join('\n');
    }
    if (typeof plan === 'object') return JSON.stringify(plan, null, 2);
    return String(plan);
  }

  function normalizeMemory(memory) {
    if (!memory) return [];
    if (Array.isArray(memory)) return memory;
    if (typeof memory === 'object') {
      return Object.entries(memory).map(([tick, content]) => ({ tick, content }));
    }
    return [{ content: String(memory) }];
  }

  function renderMemoryList(memories) {
    return `<div class="entity-list">${
      memories.map((memory) => `
        <div class="entity-row">
          <span>${escapeHtml(memory.tick !== undefined ? `Tick ${memory.tick}` : '记录')}</span>
          <span>${escapeHtml(memory.content || memory)}</span>
        </div>
      `).join('')
    }</div>`;
  }

  function renderAgentRows(agents) {
    return `<div class="entity-list">${
      agents.map((agent) => `
        <button class="entity-row" data-modal-agent-id="${escapeHtml(agent.id)}">
          <span>${escapeHtml(agent.profile?.name || agent.id)}</span>
          <span>${escapeHtml(agent.is_active ? '活跃' : '未激活')}</span>
        </button>
      `).join('')
    }</div>`;
  }

  function renderTags(tags) {
    if (!tags || !tags.length) return '';
    return `<div class="chips">${tags.map((tag) => `<span class="chip">${escapeHtml(tag)}</span>`).join('')}</div>`;
  }

  function renderObject(obj) {
    if (!obj || (typeof obj === 'object' && !Object.keys(obj).length)) {
      return '<div class="muted">暂无</div>';
    }
    if (Array.isArray(obj)) {
      return `<div class="value">${escapeHtml(obj.map(formatValue).join('\n'))}</div>`;
    }
    if (typeof obj !== 'object') {
      return `<div class="value">${escapeHtml(obj)}</div>`;
    }
    const rows = {};
    for (const [key, value] of Object.entries(obj)) {
      if (isEmptyValue(value) || key === 'raw') continue;
      rows[labelKey(key)] = formatValue(value);
    }
    return renderKvRows(rows);
  }

  function renderKvRows(rows) {
    const html = Object.entries(rows)
      .filter(([, value]) => !isEmptyValue(value))
      .map(([key, value]) => `
        <div class="kv">
          <div class="key">${escapeHtml(key)}</div>
          <div class="value">${escapeHtml(value)}</div>
        </div>
      `).join('');
    return html || '<div class="muted">暂无</div>';
  }

  function pick(obj, keys) {
    const out = {};
    for (const key of keys) {
      if (!isEmptyValue(obj?.[key])) out[key] = obj[key];
    }
    return out;
  }

  function formatValue(value) {
    if (value === true || value === 'true') return '是';
    if (value === false || value === 'false') return '否';
    if (Array.isArray(value)) return value.map(formatValue).join('\n');
    if (value && typeof value === 'object') {
      return Object.entries(value)
        .filter(([key, item]) => key !== 'raw' && !isEmptyValue(item))
        .map(([key, item]) => `${labelKey(key)}: ${formatValue(item)}`)
        .join('\n');
    }
    return String(value ?? '');
  }

  function formatBounds(bounds) {
    if (!bounds) return '';
    return `x:${bounds.x}, y:${bounds.y}, w:${bounds.w}, h:${bounds.h}`;
  }

  function labelKey(key) {
    return keyLabels[key] || key.split('_').map((part) => (
      part ? part[0].toUpperCase() + part.slice(1) : part
    )).join(' ');
  }

  function isEmptyValue(value) {
    return value === undefined
      || value === null
      || value === ''
      || (Array.isArray(value) && value.length === 0)
      || (typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 0);
  }

  function initialOf(name) {
    return String(name || '?').trim().slice(0, 1).toUpperCase() || '?';
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function regionColor(tags = []) {
    const joined = tags.join(' ').toLowerCase();
    if (joined.includes('restricted') || joined.includes('控制')) return 'rgba(210,83,63,0.30)';
    if (joined.includes('library') || joined.includes('archive')) return 'rgba(216,163,72,0.34)';
    if (joined.includes('water') || joined.includes('river')) return 'rgba(87,151,184,0.32)';
    if (joined.includes('forest') || joined.includes('garden')) return 'rgba(105,158,86,0.34)';
    return 'rgba(136,177,103,0.30)';
  }

  function setBusy(isBusy) {
    document.body.classList.toggle('is-busy', isBusy);
    document.getElementById('tickBtn').disabled = isBusy;
  }

  function showError(message) {
    const box = document.getElementById('errorBox');
    box.style.display = 'block';
    box.textContent = `错误: ${message}`;
  }

  function hideError() {
    document.getElementById('errorBox').style.display = 'none';
  }
}());
