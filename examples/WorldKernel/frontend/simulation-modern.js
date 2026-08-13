(function () {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get('session_id');
  const canvas = document.getElementById('mapCanvas');
  const ctx = canvas.getContext('2d');
  const mapWrap = document.querySelector('.map-wrap');
  const mapSurface = document.getElementById('mapSurface');
  const mapAgentLayer = document.getElementById('mapAgentLayer');
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
  let mapDisplayScale = 1;
  let mapWorldWidth = 0;
  let mapWorldHeight = 0;
  let mapPixelRatio = 1;
  let spatialBaseUrl = '';
  let visualBackgroundImage = null;
  let visualBackgroundSrc = '';
  let visualLocationLayerImage = null;
  let visualLocationLayerSrc = '';
  let characterAtlasDefinitions = new Map();
  let characterAtlasImages = new Map();
  let characterVisualIndex = new Map();
  let visualAssetErrors = new Map();
  let visualLayoutManifest = null;
  let visualManifestPollTimer = null;
  let fieldPresentation = { status: 'pending', revision: 0, fields: {} };
  let presentationPollTimer = null;
  let dialoguePlaybackTimer = null;
  let dialoguePlaybackToken = 0;
  let eventMarkerTimer = null;
  let visibleEventMarkerIds = new Set();
  let activeAgentMotions = new Map();

  const EVENT_MARKER_VISIBLE_MS = 4500;
  const EVENT_MARKER_SIZE = 24;
  const ROUTE_MOTION_MS_PER_TILE = 115;
  const ROUTE_MOTION_MIN_MS = 2400;
  const ROUTE_MOTION_MAX_MS = 7600;
  const LOCAL_MOTION_MS_PER_TILE = 140;
  const LOCAL_MOTION_MIN_MS = 1100;
  const LOCAL_MOTION_MAX_MS = 2400;

  const hiddenWorldSettingKeys = new Set(['visual_profile']);
  const hiddenCharacterDetailKeys = new Set([
    'id',
    'wk_entity_id',
    'entity_id',
    'agent_id',
    'character_id',
  ]);

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
    event_log: '事件记录',
    dialogues: '对话记录',
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
    else {
      button.setAttribute('aria-label', label);
      button.title = label;
    }
  }

  function wireEvents() {
    document.getElementById('tickBtn')?.addEventListener('click', tickOnce);
    document.getElementById('autoBtn')?.addEventListener('click', toggleAuto);
    document.getElementById('stopBtn')?.addEventListener('click', stopRuntime);
    document.getElementById('worldViewBtn')?.addEventListener('click', closeDetail);
    document.getElementById('worldSettingsBtn')?.addEventListener('click', openWorldDetail);
    document.getElementById('charactersBtn')?.addEventListener('click', openCharacterOverview);
    document.getElementById('zoomOutBtn')?.addEventListener('click', () => zoomMap(1 / 1.18));
    document.getElementById('zoomInBtn')?.addEventListener('click', () => zoomMap(1.18));
    document.getElementById('resetViewBtn')?.addEventListener('click', resetMapView);
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
    window.addEventListener('resize', renderMap);
    window.addEventListener('beforeunload', () => {
      stopVisualManifestPolling();
      stopPresentationPolling();
      hideEventMarkers({ render: false });
    });
  }

  async function boot() {
    if (!sessionId) {
      showError('URL 缺少 session_id');
      return;
    }

    try {
      const spatialUrl = `/api/stage1/session/${encodeURIComponent(sessionId)}/generated/artifacts/spatial/spatial_blueprint.json`;
      spatialBaseUrl = spatialUrl.replace(/\/[^/]*$/, '/');
      const [spatialData, runtimeState, charData, locData, worldData, visualManifestData, presentationData] = await Promise.all([
        fetchJson(spatialUrl),
        fetchJson('/api/stage3/runtime/state'),
        fetchOptionalJson(`/api/stage1/session/${encodeURIComponent(sessionId)}/generated/artifacts/semantic/characters/characters.json`),
        fetchOptionalJson(`/api/stage1/session/${encodeURIComponent(sessionId)}/generated/artifacts/semantic/locations/locations.json`),
        fetchOptionalJson(`/api/stage1/session/${encodeURIComponent(sessionId)}/generated/plan/world_background.json`),
        fetchOptionalJson(`/api/stage1/session/${encodeURIComponent(sessionId)}/generated/artifacts/spatial/visual_layout_manifest.json`),
        fetchOptionalJson(`/api/presentation/${encodeURIComponent(sessionId)}/field-labels?locale=zh-CN`),
      ]);

      spatial = spatialData;
      tilePx = Math.max(1, Number(spatial?.grid?.tile_size) || 16);
      runtime = runtimeState;
      semanticCharacters = normalizeItems(charData);
      semanticLocations = normalizeItems(locData);
      worldBackground = worldData;
      visualLayoutManifest = visualManifestData;
      fieldPresentation = presentationData || fieldPresentation;
      rebuildSemanticIndexes();
      prepareVisualAssets();
      startVisualManifestPolling();
      updatePresentationPolling();
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
        queueAgentMotions(runtime, nextRuntime);
        runtime = nextRuntime;
        await refreshPresentationLabels();
        render();
        refreshOpenDetail();
        startEventPlayback();
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

  async function refreshPresentationLabels() {
    if (!sessionId) return fieldPresentation;
    try {
      const next = await fetchJson(`/api/presentation/${encodeURIComponent(sessionId)}/field-labels?locale=zh-CN`);
      fieldPresentation = next || fieldPresentation;
      updatePresentationPolling();
    } catch (_error) {
      // Entity details keep known Chinese labels and never fall back to English keys.
    }
    return fieldPresentation;
  }

  function updatePresentationPolling() {
    if (fieldPresentation?.status === 'ready') {
      stopPresentationPolling();
      return;
    }
    if (presentationPollTimer) return;
    presentationPollTimer = window.setInterval(async () => {
      const previousRevision = fieldPresentation?.revision || 0;
      await refreshPresentationLabels();
      if ((fieldPresentation?.revision || 0) !== previousRevision) {
        refreshOpenDetail();
      }
    }, 2000);
  }

  function stopPresentationPolling() {
    if (presentationPollTimer) {
      clearInterval(presentationPollTimer);
      presentationPollTimer = null;
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
    const lineCount = getGlobalEvents()
      .filter((event) => Number(event.tick) === Number(runtime?.current_tick))
      .reduce((total, event) => total + (event.lines?.length || 0), 0);
    const delay = Math.max(2500, Math.min(7000, lineCount * 850 + 500));
    autoTimer = setTimeout(async () => {
      autoTimer = null;
      await tickOnce({ token });
      scheduleAutoTick(token);
    }, delay);
  }

  async function stopRuntime() {
    stopAutoPlayback();
    stopEventPlayback();
    hideEventMarkers();
    activeAgentMotions.clear();
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

    prepareCharacterAssets(visual?.character_layer || {});
  }

  function prepareCharacterAssets(characterLayer) {
    const nextDefinitions = new Map();
    for (const atlas of characterLayer?.atlases || []) {
      if (!atlas?.batch_id || atlas.status !== 'ready' || !atlas.url) continue;
      const version = atlas.asset_version || atlas.signature || '';
      nextDefinitions.set(String(atlas.batch_id), {
        ...atlas,
        src: resolveVersionedVisualUrl(atlas.url, version),
      });
    }

    for (const [batchId, loaded] of characterAtlasImages.entries()) {
      const definition = nextDefinitions.get(batchId);
      if (!definition || definition.src !== loaded.src) {
        characterAtlasImages.delete(batchId);
      }
    }
    characterAtlasDefinitions = nextDefinitions;
    characterVisualIndex = new Map();
    for (const asset of characterLayer?.characters || []) {
      if (asset?.status !== 'ready' || !nextDefinitions.has(String(asset.batch_id))) continue;
      addIndex(characterVisualIndex, asset, [asset.character_id, asset.name]);
    }
  }

  function ensureCharacterAtlas(asset) {
    if (!asset?.batch_id) return null;
    const batchId = String(asset.batch_id);
    const definition = characterAtlasDefinitions.get(batchId);
    if (!definition) return null;
    const existing = characterAtlasImages.get(batchId);
    if (existing?.src === definition.src) return existing;

    const record = { src: definition.src, status: 'loading', image: new Image() };
    characterAtlasImages.set(batchId, record);
    record.image.onload = () => {
      record.status = 'ready';
      visualAssetErrors.delete(`character-atlas-${batchId}`);
      hydrateCharacterArt(document);
      renderMap();
    };
    record.image.onerror = () => {
      record.status = 'failed';
      reportVisualAssetError(
        `character-atlas-${batchId}`,
        `角色图集加载失败：${definition.src}`
      );
      renderMap();
    };
    record.image.src = definition.src;
    return record;
  }

  function getCharacterVisual(subject) {
    const keys = typeof subject === 'string'
      ? [subject]
      : [
          subject?.character_id,
          subject?.id,
          subject?.wk_entity_id,
          subject?.name,
          subject?.identity?.id,
          subject?.identity?.name,
          subject?.profile?.id,
          subject?.profile?.wk_entity_id,
          subject?.profile?.name,
        ];
    for (const key of keys) {
      if (key === undefined || key === null || key === '') continue;
      const asset = characterVisualIndex.get(String(key));
      if (asset) return { asset, atlas: ensureCharacterAtlas(asset) };
    }
    return null;
  }

  function hydrateCharacterArt(root) {
    if (!root?.querySelectorAll) return;
    root.querySelectorAll('[data-character-art-id]').forEach((canvasNode) => {
      if (!(canvasNode instanceof HTMLCanvasElement)) return;
      const variant = canvasNode.dataset.characterArtVariant === 'full' ? 'full' : 'portrait';
      const width = variant === 'full' ? 336 : 96;
      const height = variant === 'full' ? 420 : 96;
      if (canvasNode.width !== width) canvasNode.width = width;
      if (canvasNode.height !== height) canvasNode.height = height;
      const context = canvasNode.getContext('2d');
      context.clearRect(0, 0, width, height);
      context.imageSmoothingEnabled = false;
      canvasNode.classList.remove('loaded');

      const visual = getCharacterVisual(canvasNode.dataset.characterArtId || '');
      const atlas = visual?.atlas;
      const rect = variant === 'full'
        ? visual?.asset?.content_rect
        : visual?.asset?.portrait_rect;
      if (
        atlas?.status !== 'ready' || !atlas.image?.complete ||
        !rect || Number(rect.w) <= 0 || Number(rect.h) <= 0
      ) return;

      const sourceWidth = Number(rect.w);
      const sourceHeight = Number(rect.h);
      const scale = variant === 'portrait'
        ? Math.max(width / sourceWidth, height / sourceHeight)
        : Math.min(width / sourceWidth, height / sourceHeight);
      const drawWidth = sourceWidth * scale;
      const drawHeight = sourceHeight * scale;
      const drawX = (width - drawWidth) / 2;
      const drawY = variant === 'portrait' ? 0 : height - drawHeight;
      context.drawImage(
        atlas.image,
        Number(rect.x), Number(rect.y), sourceWidth, sourceHeight,
        drawX, drawY, drawWidth, drawHeight
      );
      canvasNode.classList.add('loaded');
    });
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
    const locationLayer = visual?.location_layer || {};
    const characterLayer = visual?.character_layer || {};
    return [
      background.status || '',
      background.url || '',
      background.asset_version || '',
      background.generation_strategy || '',
      (background.composited_layers || []).join(','),
      locationLayer.status || '',
      locationLayer.url || '',
      locationLayer.asset_version || '',
      (locationLayer.completed_location_ids || []).join(','),
      characterLayer.status || '',
      (characterLayer.atlases || []).map((atlas) => [
        atlas.batch_id || '',
        atlas.status || '',
        atlas.asset_version || '',
        atlas.signature || '',
      ].join(':')).join(','),
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
    renderWorldName();
    renderMap();
    renderState();
    hideError();
  }

  function renderWorldName() {
    const element = document.getElementById('worldName');
    if (!element) return;
    const name = worldBackground?.world_name
      || worldBackground?.name
      || worldBackground?.identity?.name
      || spatial?.world_name
      || spatial?.name
      || '未命名世界';
    element.textContent = name;
    element.title = `当前世界：${name}`;
  }

  function renderMap({ applyZoom = true } = {}) {
    if (!spatial?.grid) return;
    const grid = spatial.grid;
    const regions = spatial.regions || [];
    const routes = spatial.routes || [];
    const roadTiles = spatial.road_tiles || [];
    const spawns = spatial.spawn_points || [];
    const agents = getDrawableMapAgents(spawns);
    const visual = getActiveVisualManifest();
    const compositedLayers = new Set(visual?.background?.composited_layers || []);

    mapWorldWidth = grid.width * tilePx;
    mapWorldHeight = grid.height * tilePx;
    mapPixelRatio = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
    const backingWidth = Math.round(mapWorldWidth * mapPixelRatio);
    const backingHeight = Math.round(mapWorldHeight * mapPixelRatio);
    if (canvas.width !== backingWidth) canvas.width = backingWidth;
    if (canvas.height !== backingHeight) canvas.height = backingHeight;
    ctx.setTransform(mapPixelRatio, 0, 0, mapPixelRatio, 0, 0);
    ctx.imageSmoothingEnabled = false;
    drawMapBase(grid);

    drawLocationLayer();
    const locationIncludesRoads = Boolean(
      visualLocationLayerImage?.complete && visual?.location_layer?.includes_roads
    );
    if (!locationIncludesRoads && !compositedLayers.has('route_layer')) {
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
    const drawableAgents = agents.map((agent) => {
      const fallback = spawnById.get(agent.id) || spawnById.get(agent.profile?.name);
      return { agent, fallback, position: getAgentPosition(agent, fallback) };
    }).sort((left, right) => left.position[1] - right.position[1]);
    for (const { agent, position } of drawableAgents) {
      drawAgent(
        position,
        agent.profile?.name || '未命名角色',
        !agent.is_active,
        selectedEntity?.type === 'agent' && selectedEntity.id === agent.id,
        agent
      );
    }

    const mapInfo = document.getElementById('mapInfo');
    if (mapInfo) {
      mapInfo.textContent =
        `${regions.length} 地点 · ${routes.length} 路线 · ${agents.length || spawns.length} 角色`;
    }
    updateCount('locationCount', regions.length);
    updateCount('routeCount', routes.length);
    if (applyZoom) applyMapZoom();
  }

  function drawMapBase(grid) {
    if (visualBackgroundImage?.complete && visualBackgroundImage.naturalWidth > 0) {
      ctx.drawImage(visualBackgroundImage, 0, 0, mapWorldWidth, mapWorldHeight);
      return;
    }
    ctx.fillStyle = '#f5e4c0';
    ctx.fillRect(0, 0, mapWorldWidth, mapWorldHeight);
    ctx.fillStyle = 'rgba(255,255,255,0.22)';
    for (let y = 0; y < grid.height; y += 2) {
      ctx.fillRect(0, y * tilePx, mapWorldWidth, tilePx);
    }
    ctx.strokeStyle = 'rgba(167,113,48,0.12)';
    ctx.lineWidth = 0.5;
    for (let x = 0; x <= grid.width; x += 4) {
      ctx.beginPath();
      ctx.moveTo(x * tilePx, 0);
      ctx.lineTo(x * tilePx, mapWorldHeight);
      ctx.stroke();
    }
    for (let y = 0; y <= grid.height; y += 4) {
      ctx.beginPath();
      ctx.moveTo(0, y * tilePx);
      ctx.lineTo(mapWorldWidth, y * tilePx);
      ctx.stroke();
    }
  }

  function drawLocationLayer() {
    if (!visualLocationLayerImage?.complete || visualLocationLayerImage.naturalWidth <= 0) return;
    if (
      visualLocationLayerImage.naturalWidth !== mapWorldWidth ||
      visualLocationLayerImage.naturalHeight !== mapWorldHeight
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
    if (!shouldShowLocationLabels()) return;
    const label = String(location.name || location.identity?.name || region.name || '地点');
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

  function shouldShowLocationLabels() {
    return mapZoom <= 1.001;
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

  function drawAgent(position, name, inactive, selected, agent) {
    const unit = tilePx / 4;
    const [x, y] = position;
    const px = x * tilePx + tilePx / 2;
    const py = y * tilePx + tilePx / 2;
    const visual = getCharacterVisual(agent);
    const rect = visual?.asset?.content_rect || {};
    const atlasImage = visual?.atlas?.status === 'ready' ? visual.atlas.image : null;
    if (
      atlasImage?.complete && atlasImage.naturalWidth > 0 &&
      Number(rect.w) > 0 && Number(rect.h) > 0
    ) {
      // Ready character art is rendered in a dedicated high-DPI overlay.
      // Keeping it out of the map bitmap avoids shrinking it once and then
      // enlarging those already-lost pixels when the user zooms the map.
      return;
    }

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

  function renderMapAgentLayer() {
    if (!mapAgentLayer || !spatial?.grid) return;
    const spawns = spatial.spawn_points || [];
    const agents = getDrawableMapAgents(spawns);
    const spawnById = new Map();
    for (const spawn of spawns) {
      addIndex(spawnById, spawn, [spawn.character_id, spawn.character_name]);
    }

    const drawableAgents = agents.map((agent) => {
      const fallback = spawnById.get(agent.id) || spawnById.get(agent.profile?.name);
      return { agent, position: getAgentPosition(agent, fallback) };
    }).sort((left, right) => left.position[1] - right.position[1]);

    const fragment = document.createDocumentFragment();
    const displayScale = estimateMapDisplayScale();
    const pixelRatio = Math.min(3, Math.max(1, window.devicePixelRatio || 1));
    const renderedSpriteMetrics = new Map();
    const animationsToStart = [];
    const motionNow = performance.now();
    pruneAgentMotions(motionNow);

    for (const { agent, position } of drawableAgents) {
      const visual = getCharacterVisual(agent);
      const rect = visual?.asset?.content_rect || {};
      const atlasImage = visual?.atlas?.status === 'ready' ? visual.atlas.image : null;
      const sourceWidth = Number(rect.w);
      const sourceHeight = Number(rect.h);
      if (
        !atlasImage?.complete || atlasImage.naturalWidth <= 0 ||
        sourceWidth <= 0 || sourceHeight <= 0
      ) continue;

      const selected = selectedEntity?.type === 'agent' && selectedEntity.id === agent.id;
      const motion = activeAgentMotions.get(String(agent.id));
      const minScreenHeight = selected ? 34 : 28;
      const minScreenWidth = selected ? 24 : 20;
      const maxScreenHeight = selected ? 112 : 96;
      const maxScreenWidth = selected ? 84 : 72;
      const baseWorldHeight = tilePx * (selected ? 3.2 : 2.75);
      const baseWorldWidth = tilePx * (selected ? 2.35 : 2);
      const targetScreenHeight = Math.min(
        maxScreenHeight,
        Math.max(minScreenHeight, baseWorldHeight * displayScale)
      );
      const targetScreenWidth = Math.min(
        maxScreenWidth,
        Math.max(minScreenWidth, baseWorldWidth * displayScale)
      );
      const spriteScale = Math.min(
        targetScreenWidth / sourceWidth,
        targetScreenHeight / sourceHeight
      );
      const cssWidth = Math.max(1, sourceWidth * spriteScale);
      const cssHeight = Math.max(1, sourceHeight * spriteScale);
      const [x, y] = position;
      const surfaceWidth = mapWorldWidth * displayScale;
      const surfaceHeight = mapWorldHeight * displayScale;
      const rawAnchorX = (x * tilePx + tilePx / 2) * displayScale;
      const rawAnchorY = (y * tilePx + tilePx * 0.92) * displayScale;
      const anchorX = clamp(rawAnchorX, cssWidth / 2 + 2, surfaceWidth - cssWidth / 2 - 2);
      const anchorY = clamp(rawAnchorY, cssHeight + 2, surfaceHeight - 2);

      const sprite = document.createElement('div');
      sprite.className = `map-agent-sprite${agent.is_active ? '' : ' inactive'}${selected ? ' selected' : ''}${motion ? ' moving' : ''}`;
      sprite.dataset.agentId = agent.id;
      sprite.dataset.motion = motion ? 'route' : 'wander';
      sprite.style.left = `${anchorX}px`;
      sprite.style.top = `${anchorY}px`;
      sprite.style.width = `${cssWidth}px`;
      sprite.style.height = `${cssHeight}px`;
      renderedSpriteMetrics.set(String(agent.id), {
        anchorX,
        anchorY,
        height: cssHeight,
      });

      const spriteCanvas = document.createElement('canvas');
      spriteCanvas.width = Math.max(1, Math.ceil(cssWidth * pixelRatio));
      spriteCanvas.height = Math.max(1, Math.ceil(cssHeight * pixelRatio));
      const spriteContext = spriteCanvas.getContext('2d');
      spriteContext.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      spriteContext.imageSmoothingEnabled = true;
      spriteContext.imageSmoothingQuality = 'high';
      spriteContext.drawImage(
        atlasImage,
        Number(rect.x), Number(rect.y), sourceWidth, sourceHeight,
        0, 0, cssWidth, cssHeight
      );
      sprite.appendChild(spriteCanvas);
      fragment.appendChild(sprite);
      if (motion) {
        animationsToStart.push(() => animateAgentMotion(
          sprite,
          motion,
          displayScale,
          cssWidth,
          cssHeight,
          surfaceWidth,
          surfaceHeight
        ));
      } else {
        applyAgentWanderStyle(sprite, agent.id);
      }
    }

    const drawableById = new Map(drawableAgents.map((item) => [String(item.agent.id), item]));
    const currentEvents = getGlobalEvents().filter((event) => {
      const eventId = event.event_id || legacyEventId(event);
      return Number(event.tick) === Number(runtime?.current_tick)
        && visibleEventMarkerIds.has(eventId);
    });
    const markerCountByAgent = new Map();
    const markerOffsets = [0, 28, -28, 56, -56];
    currentEvents.forEach((event) => {
      const anchorAgentId = event.initiator || event.participants?.[0];
      const anchor = drawableById.get(String(anchorAgentId));
      if (!anchor) return;
      const [x, y] = anchor.position;
      const markerIndex = markerCountByAgent.get(String(anchorAgentId)) || 0;
      markerCountByAgent.set(String(anchorAgentId), markerIndex + 1);
      const offsetX = markerOffsets[markerIndex % markerOffsets.length];
      const spriteMetrics = renderedSpriteMetrics.get(String(anchorAgentId));
      const defaultMarkerX = (x * tilePx + tilePx / 2) * displayScale;
      const defaultMarkerY = (y * tilePx - tilePx * 1.45) * displayScale;
      const markerAboveSprite = spriteMetrics
        ? spriteMetrics.anchorY - spriteMetrics.height - EVENT_MARKER_SIZE / 2 - 4
        : defaultMarkerY;
      const preferredMarkerY = markerAboveSprite >= EVENT_MARKER_SIZE / 2 + 2
        ? markerAboveSprite
        : (spriteMetrics?.anchorY || defaultMarkerY) + EVENT_MARKER_SIZE / 2 + 4;
      const markerX = clamp(
        (spriteMetrics?.anchorX || defaultMarkerX) + offsetX,
        EVENT_MARKER_SIZE / 2 + 2,
        mapWorldWidth * displayScale - EVENT_MARKER_SIZE / 2 - 2
      );
      const markerY = clamp(
        preferredMarkerY,
        EVENT_MARKER_SIZE / 2 + 2,
        mapWorldHeight * displayScale - EVENT_MARKER_SIZE / 2 - 2
      );
      const marker = document.createElement('button');
      const summary = event.summary || event.current_action || '事件发生';
      marker.type = 'button';
      marker.className = `map-event-marker event-${event.type || 'action'}`;
      marker.dataset.eventId = event.event_id || legacyEventId(event);
      marker.style.left = `${markerX}px`;
      marker.style.top = `${markerY}px`;
      marker.setAttribute('aria-label', `查看事件详情：${summary}`);
      marker.title = summary;
      marker.addEventListener('click', () => openEventDetail(event));
      fragment.appendChild(marker);
    });

    mapAgentLayer.replaceChildren(fragment);
    animationsToStart.forEach((start) => start());
  }

  function applyAgentWanderStyle(sprite, agentId) {
    const seed = stableStringHash(String(agentId || 'agent'));
    sprite.style.setProperty('--wander-x', `${2 + seed % 3}px`);
    sprite.style.setProperty('--wander-y', `${1 + (seed >>> 3) % 3}px`);
    sprite.style.setProperty('--wander-duration', `${4.2 + (seed % 29) / 10}s`);
    sprite.style.setProperty('--wander-delay', `${-((seed % 37) / 10)}s`);
  }

  function stableStringHash(value) {
    let hash = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  function queueAgentMotions(previousRuntime, nextRuntime) {
    if (!spatial?.grid || !previousRuntime?.agents?.length || !nextRuntime?.agents?.length) return;
    const previousById = new Map(previousRuntime.agents.map((agent) => [String(agent.id), agent]));
    const spawnById = new Map();
    for (const spawn of spatial?.spawn_points || []) {
      addIndex(spawnById, spawn, [spawn.character_id, spawn.character_name]);
    }
    const startTime = performance.now();

    for (const agent of nextRuntime.agents) {
      const previous = previousById.get(String(agent.id));
      if (!previous) continue;
      const fallback = spawnById.get(agent.id)
        || spawnById.get(agent.profile?.wk_entity_id)
        || spawnById.get(agent.profile?.name);
      const from = getAgentPosition(previous, fallback);
      const to = getAgentPosition(agent, fallback);
      const fromLocation = previous.location_id || previous.current_location;
      const toLocation = agent.location_id || agent.current_location;
      const locationChanged = Boolean(fromLocation && toLocation && fromLocation !== toLocation);
      const directDistance = Math.hypot(to[0] - from[0], to[1] - from[1]);
      if (!locationChanged && directDistance < 0.75) continue;

      let points = locationChanged
        ? buildRouteMotionPoints(fromLocation, toLocation, from, to)
        : [toPoint(from), toPoint(to)];
      const existingMotion = activeAgentMotions.get(String(agent.id));
      const existingMotionActive = existingMotion
        && startTime < existingMotion.startTime + existingMotion.duration;
      if (existingMotionActive) {
        const elapsed = clamp(startTime - existingMotion.startTime, 0, existingMotion.duration);
        const travelled = existingMotion.totalDistance * (elapsed / existingMotion.duration);
        const currentPoint = pointAtMotionDistance(existingMotion, travelled);
        const continuousPoints = [];
        appendMotionPoint(continuousPoints, currentPoint);
        existingMotion.points
          .slice(currentPoint.nextIndex)
          .forEach((point) => appendMotionPoint(continuousPoints, point));
        points.forEach((point) => appendMotionPoint(continuousPoints, point));
        points = simplifyMotionPoints(continuousPoints);
      }
      const motion = createAgentMotion(
        points,
        startTime,
        locationChanged || Boolean(existingMotionActive && existingMotion.followsRoute)
      );
      if (!motion) continue;
      activeAgentMotions.set(String(agent.id), motion);
    }
  }

  function buildRouteMotionPoints(fromLocation, toLocation, fromPosition, toPosition) {
    const routes = spatial?.routes || [];
    const adjacency = new Map();
    const addEdge = (from, to, route, reversed) => {
      if (!from || !to) return;
      if (!adjacency.has(String(from))) adjacency.set(String(from), []);
      adjacency.get(String(from)).push({ to: String(to), route, reversed });
    };
    for (const route of routes) {
      addEdge(route.from_location_id, route.to_location_id, route, false);
      addEdge(route.to_location_id, route.from_location_id, route, true);
    }

    const start = String(fromLocation || '');
    const target = String(toLocation || '');
    const queue = [start];
    const visited = new Set([start]);
    const cameFrom = new Map();
    while (queue.length && !visited.has(target)) {
      const current = queue.shift();
      for (const edge of adjacency.get(current) || []) {
        if (visited.has(edge.to)) continue;
        visited.add(edge.to);
        cameFrom.set(edge.to, { previous: current, edge });
        queue.push(edge.to);
      }
    }

    if (!visited.has(target)) return [toPoint(fromPosition), toPoint(toPosition)];
    const edges = [];
    for (let cursor = target; cursor !== start;) {
      const step = cameFrom.get(cursor);
      if (!step) return [toPoint(fromPosition), toPoint(toPosition)];
      edges.unshift(step.edge);
      cursor = step.previous;
    }

    const points = [toPoint(fromPosition)];
    for (const edge of edges) {
      const centerline = (edge.route.centerline || []).map(toPoint);
      if (edge.reversed) centerline.reverse();
      centerline.forEach((point) => appendMotionPoint(points, point));
    }
    appendMotionPoint(points, toPoint(toPosition));
    return simplifyMotionPoints(points);
  }

  function toPoint(value) {
    if (Array.isArray(value)) return { x: Number(value[0]) || 0, y: Number(value[1]) || 0 };
    return { x: Number(value?.x) || 0, y: Number(value?.y) || 0 };
  }

  function appendMotionPoint(points, point) {
    const previous = points.at(-1);
    if (!previous || previous.x !== point.x || previous.y !== point.y) points.push(point);
  }

  function simplifyMotionPoints(points) {
    if (points.length <= 3) return points;
    const simplified = [points[0]];
    for (let index = 1; index < points.length - 1; index += 1) {
      const previous = points[index - 1];
      const current = points[index];
      const next = points[index + 1];
      const incoming = [Math.sign(current.x - previous.x), Math.sign(current.y - previous.y)];
      const outgoing = [Math.sign(next.x - current.x), Math.sign(next.y - current.y)];
      if (incoming[0] !== outgoing[0] || incoming[1] !== outgoing[1] || index % 8 === 0) {
        simplified.push(current);
      }
    }
    simplified.push(points.at(-1));
    return simplified;
  }

  function createAgentMotion(points, startTime, followsRoute) {
    if (!Array.isArray(points) || points.length < 2) return null;
    const cumulative = [0];
    for (let index = 1; index < points.length; index += 1) {
      const previous = points[index - 1];
      const current = points[index];
      cumulative.push(cumulative.at(-1) + Math.hypot(current.x - previous.x, current.y - previous.y));
    }
    const totalDistance = cumulative.at(-1);
    if (totalDistance < 0.1) return null;
    const duration = followsRoute
      ? clamp(
        1200 + totalDistance * ROUTE_MOTION_MS_PER_TILE,
        ROUTE_MOTION_MIN_MS,
        ROUTE_MOTION_MAX_MS
      )
      : clamp(
        650 + totalDistance * LOCAL_MOTION_MS_PER_TILE,
        LOCAL_MOTION_MIN_MS,
        LOCAL_MOTION_MAX_MS
      );
    return { points, cumulative, totalDistance, startTime, duration, followsRoute };
  }

  function pruneAgentMotions(now = performance.now()) {
    for (const [agentId, motion] of activeAgentMotions) {
      if (now >= motion.startTime + motion.duration) activeAgentMotions.delete(agentId);
    }
  }

  function pointAtMotionDistance(motion, distance) {
    const clampedDistance = clamp(distance, 0, motion.totalDistance);
    let index = 1;
    while (index < motion.cumulative.length && motion.cumulative[index] < clampedDistance) index += 1;
    if (index >= motion.points.length) return { ...motion.points.at(-1), nextIndex: motion.points.length };
    const startDistance = motion.cumulative[index - 1];
    const endDistance = motion.cumulative[index];
    const ratio = endDistance === startDistance ? 1 : (clampedDistance - startDistance) / (endDistance - startDistance);
    const from = motion.points[index - 1];
    const to = motion.points[index];
    return {
      x: from.x + (to.x - from.x) * ratio,
      y: from.y + (to.y - from.y) * ratio,
      nextIndex: index,
    };
  }

  function animateAgentMotion(sprite, motion, displayScale, cssWidth, cssHeight, surfaceWidth, surfaceHeight) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      activeAgentMotions.delete(String(sprite.dataset.agentId));
      sprite.classList.remove('moving');
      sprite.dataset.motion = 'wander';
      applyAgentWanderStyle(sprite, sprite.dataset.agentId);
      return;
    }
    const now = performance.now();
    const elapsed = clamp(now - motion.startTime, 0, motion.duration);
    const travelled = motion.totalDistance * (elapsed / motion.duration);
    const current = pointAtMotionDistance(motion, travelled);
    const remainingPoints = [current, ...motion.points.slice(current.nextIndex)];
    const remainingDistance = Math.max(0.001, motion.totalDistance - travelled);
    let covered = 0;
    const keyframes = remainingPoints.map((point, index) => {
      if (index > 0) {
        const previous = remainingPoints[index - 1];
        covered += Math.hypot(point.x - previous.x, point.y - previous.y);
      }
      const rawX = (point.x * tilePx + tilePx / 2) * displayScale;
      const rawY = (point.y * tilePx + tilePx * 0.92) * displayScale;
      return {
        left: `${clamp(rawX, cssWidth / 2 + 2, surfaceWidth - cssWidth / 2 - 2)}px`,
        top: `${clamp(rawY, cssHeight + 2, surfaceHeight - 2)}px`,
        offset: clamp(covered / remainingDistance, 0, 1),
      };
    });
    if (keyframes.length < 2) return;
    keyframes[0].offset = 0;
    keyframes.at(-1).offset = 1;
    const animation = sprite.animate(keyframes, {
      duration: Math.max(80, motion.duration - elapsed),
      easing: 'linear',
    });
    animation.onfinish = () => {
      if (activeAgentMotions.get(String(sprite.dataset.agentId)) !== motion) return;
      activeAgentMotions.delete(String(sprite.dataset.agentId));
      pruneAgentMotions();
      sprite.classList.remove('moving');
      sprite.dataset.motion = 'wander';
      applyAgentWanderStyle(sprite, sprite.dataset.agentId);
    };
  }

  function getDrawableMapAgents(spawns = spatial?.spawn_points || []) {
    const runtimeAgents = runtime?.agents || [];
    if (runtimeAgents.length) return runtimeAgents;
    return spawns.map((spawn) => ({
      id: spawn.character_id || spawn.character_name,
      character_id: spawn.character_id,
      location_id: spawn.location_id,
      position: spawn.position,
      is_active: true,
      profile: {
        id: spawn.character_id,
        wk_entity_id: spawn.character_id,
        name: spawn.character_name || '未命名角色',
      },
    }));
  }

  function estimateMapDisplayScale() {
    if (Number.isFinite(mapDisplayScale) && mapDisplayScale > 0) return mapDisplayScale;
    if (!mapWrap || !mapWorldWidth || !mapWorldHeight) return 1;
    const style = window.getComputedStyle(mapWrap);
    const padX = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
    const padY = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const availableWidth = Math.max(1, mapWrap.clientWidth - padX);
    const availableHeight = Math.max(1, mapWrap.clientHeight - padY);
    const fitScale = Math.min(
      availableWidth / mapWorldWidth,
      availableHeight / mapWorldHeight
    );
    return Math.max(0.2, snapMapDisplayScale(fitScale * mapZoom));
  }

  function renderState() {
    const agents = runtime?.agents || [];
    const isStarted = Boolean(runtime?.started);
    document.body.classList.toggle('runtime-active', isStarted);
    updateCount('tickValue', runtime?.current_tick ?? 0);
    updateCount('agentCount', agents.length);
    const runtimeStatus = document.getElementById('runtimeStatus');
    if (runtimeStatus) {
      runtimeStatus.textContent = isStarted
        ? (autoPlaying ? '自动推进中' : '模拟运行中')
        : '模拟未运行';
    }
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
    const spawns = spatial.spawn_points || [];
    const agents = getDrawableMapAgents(spawns);
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
      x: (event.clientX - rect.left) * (mapWorldWidth / rect.width),
      y: (event.clientY - rect.top) * (mapWorldHeight / rect.height),
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
    if (!mapWrap || !mapSurface || !mapWorldWidth || !mapWorldHeight) return;
    const style = window.getComputedStyle(mapWrap);
    const padX = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
    const padY = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const availableWidth = Math.max(1, mapWrap.clientWidth - padX);
    const availableHeight = Math.max(1, mapWrap.clientHeight - padY);
    mapFitScale = Math.min(availableWidth / mapWorldWidth, availableHeight / mapWorldHeight);

    const previousRect = canvas.getBoundingClientRect();
    const previousWidth = previousRect.width || mapWorldWidth * mapFitScale;
    const previousHeight = previousRect.height || mapWorldHeight * mapFitScale;
    const scale = snapMapDisplayScale(Math.max(0.2, mapFitScale * mapZoom));
    mapDisplayScale = scale;
    const displayWidth = Math.max(1, Math.round(mapWorldWidth * scale));
    const displayHeight = Math.max(1, Math.round(mapWorldHeight * scale));
    canvas.style.width = `${displayWidth}px`;
    canvas.style.height = `${displayHeight}px`;
    mapSurface.style.width = `${displayWidth}px`;
    mapSurface.style.height = `${displayHeight}px`;
    const surfaceOuterHeight = mapSurface.offsetHeight || displayHeight;
    const verticalInset = Math.max(0, Math.floor((availableHeight - surfaceOuterHeight) / 2));
    mapSurface.style.marginTop = `${verticalInset}px`;
    mapSurface.style.marginBottom = `${verticalInset}px`;
    mapSurface.classList.toggle('location-labels-hidden', !shouldShowLocationLabels());
    canvas.style.imageRendering = scale < 1 ? 'auto' : 'pixelated';
    renderMap({ applyZoom: false });
    renderMapAgentLayer();

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

  function clamp(value, minimum, maximum) {
    if (maximum < minimum) return (minimum + maximum) / 2;
    return Math.min(maximum, Math.max(minimum, value));
  }

  function openWorldDetail() {
    setActiveNav('worldSettingsBtn');
    const world = worldBackground || {};
    const title = world.world_name || world.name || '世界设定';
    const summary = world.world_origin_summary || world.description || '';
    const sections = Object.entries(world)
      .filter(([key, value]) => (
        !['world_name', 'name', 'world_origin_summary', 'description', 'raw'].includes(key)
        && !hiddenWorldSettingKeys.has(key)
        && isPresentedField('world', `world.${key}`, key)
        && !isEmptyValue(value)
      ))
      .map(([key, value]) => `
        <section class="detail-section ${typeof value === 'object' ? 'wide' : ''}">
          <div class="section-title">${escapeHtml(labelKey('world', `world.${key}`, key))}</div>
          ${renderObject(value, 'world', `world.${key}`)}
        </section>
      `).join('');

    setDetailHeader('世界设定', title, summary);
    document.getElementById('detailBody').innerHTML = `
      ${renderLocalizationNotice()}
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
      : runtimeAgents.map((agent) => agent.profile || { id: agent.id, name: '未命名角色' });

    setDetailHeader('角色', '角色总览', `${profiles.length} 位角色`);
    document.getElementById('detailBody').innerHTML = `
      <div class="character-overview">
        ${profiles.map((profile, index) => {
          const id = profile.id || profile.wk_entity_id || profile.identity?.id || `profile-${index}`;
          const name = profile.name || profile.identity?.name || '未命名角色';
          const role = profile.role || profile.identity?.role || profile.identity?.rank || '角色';
          const runtimeAgent = findRuntimeAgentForProfile(profile);
          const locationName = runtimeAgent ? getLocationName(runtimeAgent.location_id || runtimeAgent.current_location) : '';
          return `
            <button class="character-entry" type="button" data-profile-id="${escapeHtml(id)}">
              <canvas class="character-portrait character-art-canvas" data-character-art-id="${escapeHtml(id)}" data-character-art-variant="portrait" role="img" aria-label="${escapeHtml(name)}头像"></canvas>
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
    hydrateCharacterArt(document.getElementById('detailBody'));
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
        name: profile.name || profile.identity?.name || '未命名角色',
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
    const name = agent.profile?.name || profile.name || profile.identity?.name || '未命名角色';
    const locationName = getLocationName(agent.location_id || agent.current_location);
    const recentMemory = normalizeMemory(agent.short_term_memory).slice(-5).reverse();
    const recentEvents = normalizeEvents(agent.event_log, agent.dialogues, agent.short_term_memory)
      .slice(-6)
      .reverse();
    const profileId = profile.id || profile.wk_entity_id || profile.identity?.id || agent.profile?.wk_entity_id || agent.id;

    setDetailHeader('角色', name, locationName);
    document.getElementById('detailBody').innerHTML = `
      ${renderLocalizationNotice()}
      <div class="detail-grid">
        <section class="detail-section character-art-section">
          <div class="section-title">人物形象</div>
          <div class="character-art-stage">
            <canvas class="character-full-art character-art-canvas" data-character-art-id="${escapeHtml(profileId)}" data-character-art-variant="full" role="img" aria-label="${escapeHtml(name)}完整正面形象"></canvas>
          </div>
        </section>
        <section class="detail-section character-current-section">
          <div class="section-title">当前计划与实际行动</div>
          ${renderKvRows({
            '所在地点': locationName || agent.location_id || '未知',
            '坐标': JSON.stringify(agent.position || []),
            '计划意图': normalizePlan(agent.current_plan) || '暂无',
            '行动提示': agent.current_plan_note || '',
            '状态': agent.is_active ? '活跃' : (agent.inactive_reason || '未激活'),
            '情绪': agent.mood || '',
            '角色状态': agent.status || '',
            '当前目标': agent.active_goal || '',
          })}
          <button class="current-action-link" type="button" data-latest-agent-event="${escapeHtml(agent.id)}">
            <span>实际行动</span><strong>${escapeHtml(agent.current_action || '暂无')}</strong>
          </button>
          ${renderNextActionForm(agent)}
        </section>
        <section class="detail-section">
          <div class="section-title">身份信息</div>
          ${renderObject(
            profile.identity || pick(profile, ['name', 'role', 'type', 'description']),
            'character',
            profile.identity ? 'character.identity' : 'character',
            hiddenCharacterDetailKeys
          )}
        </section>
        <section class="detail-section">
          <div class="section-title">目标与动机</div>
          ${renderObject(profile.goals || pick(profile, ['short_term_goal', 'long_term_goal', 'motivation']), 'character', profile.goals ? 'character.goals' : 'character')}
        </section>
        <section class="detail-section">
          <div class="section-title">性格</div>
          ${renderObject(profile.personality || pick(profile, ['traits', 'values', 'speech_style']), 'character', profile.personality ? 'character.personality' : 'character')}
        </section>
        <section class="detail-section">
          <div class="section-title">能力</div>
          ${renderObject(profile.capabilities || {}, 'character', 'character.capabilities')}
        </section>
        <section class="detail-section wide event-log-section">
          <div class="section-title">事件记录</div>
          ${recentEvents.length ? renderEventLog(recentEvents) : '<div class="muted">推进模拟后，这里会以对话形式记录实际发生的事件。</div>'}
        </section>
        <section class="detail-section wide">
          <div class="section-title">近期记忆</div>
          ${recentMemory.length ? renderMemoryList(recentMemory) : '<div class="muted">暂无</div>'}
        </section>
      </div>
    `;
    openDetail();
    hydrateCharacterArt(document.getElementById('detailBody'));
    bindEventLinks(document.getElementById('detailBody'));
    bindNextActionForm(agent);
  }

  function renderNextActionForm(agent) {
    if (!runtime?.started || !agent.is_active) return '';
    const targets = (runtime.agents || []).filter((item) => item.id !== agent.id && item.is_active);
    const locations = (spatial?.regions || []).map((region) => {
      const profile = getLocationProfile(region.location_id) || {};
      return {
        id: region.location_id,
        name: profile.name || profile.identity?.name || region.name || '未命名地点',
      };
    });
    return `
      <form class="next-action-form" data-next-action-agent="${escapeHtml(agent.id)}">
        <div class="section-title">指派任务</div>
        <label>任务内容<textarea name="action" maxlength="300" required placeholder="输入希望角色优先执行的任务"></textarea></label>
        <div class="next-action-grid">
          <label>互动对象<select name="target">
            <option value="">独自行动</option>
            ${targets.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.profile?.name || '未命名角色')}</option>`).join('')}
          </select></label>
          <label>地点<select name="location" required>
            ${locations.map((item) => {
              const id = item.id || item.identity?.id || item.name;
              const name = item.name || item.identity?.name || '未命名地点';
              return `<option value="${escapeHtml(id)}"${id === agent.location_id ? ' selected' : ''}>${escapeHtml(name)}</option>`;
            }).join('')}
          </select></label>
        </div>
        <button type="submit">指派任务</button>
        ${agent.pending_user_action ? `<div class="pending-action">已排队：${escapeHtml(agent.pending_user_action.action || '')}</div>` : ''}
      </form>
    `;
  }

  function bindNextActionForm(agent) {
    const form = document.querySelector(`[data-next-action-agent="${CSS.escape(agent.id)}"]`);
    if (!form) return;
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submit = form.querySelector('button[type="submit"]');
      submit.disabled = true;
      const data = new FormData(form);
      try {
        await fetchJson(`/api/stage3/runtime/agents/${encodeURIComponent(agent.id)}/next-action`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: data.get('action'),
            target: data.get('target') || null,
            location: data.get('location'),
          }),
        });
        runtime = await fetchJson('/api/stage3/runtime/state');
        refreshOpenDetail();
      } catch (error) {
        showError(error.message);
      } finally {
        submit.disabled = false;
      }
    });
  }

  function openLocationDetail(region) {
    setActiveNav('worldViewBtn');
    const location = getLocationProfile(region.location_id) || region;
    const agents = agentsAtLocation(region.location_id);
    selectedEntity = { type: 'location', id: region.location_id };
    renderMap();
    renderState();

    setDetailHeader(
      '地点',
      location.name || location.identity?.name || region.name || '未命名地点',
      location.type || location.identity?.type || ''
    );
    document.getElementById('detailBody').innerHTML = `
      ${renderLocalizationNotice()}
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
          ${renderObject(location.state || {}, 'location', 'location.state')}
        </section>
        <section class="detail-section">
          <div class="section-title">访问规则</div>
          ${renderObject(location.access || {}, 'location', 'location.access')}
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

  function openEventDetail(event) {
    const eventId = event.event_id || legacyEventId(event);
    selectedEntity = { type: 'event', id: eventId };
    const location = normalizeEventLocation(event.location);
    const participants = event.participants || [];
    const absent = event.absent_participants || [];
    setDetailHeader('World Event', `Tick ${event.tick ?? '-'} · ${eventTypeLabel(event.type)}`, location.name || '地点未知');
    document.getElementById('detailBody').innerHTML = `
      <div class="event-detail-layout">
        <section class="detail-section event-cast">
          <div class="section-title">参与角色</div>
          <div class="event-cast-list">
            ${participants.map((agentId) => {
              const agent = (runtime?.agents || []).find((item) => item.id === agentId);
              const name = agent?.profile?.name || agentId;
              return `<div class="event-cast-member" data-event-speaker="${escapeHtml(agentId)}">
                <canvas class="character-portrait character-art-canvas" data-character-art-id="${escapeHtml(agentId)}" data-character-art-variant="portrait" role="img" aria-label="${escapeHtml(name)}头像"></canvas>
                <strong>${escapeHtml(name)}</strong>
                <span>${escapeHtml(event.current_actions?.[agentId] || '')}</span>
              </div>`;
            }).join('')}
          </div>
          ${absent.length ? `<div class="event-absent">未能到场：${escapeHtml(absent.join('、'))}</div>` : ''}
        </section>
        <section class="detail-section event-place">
          <div class="section-title">真实事件地点</div>
          <canvas id="eventMapPreview" class="event-map-preview" width="520" height="240"></canvas>
          <div class="muted">${escapeHtml(location.name || location.id || '未知地点')}</div>
        </section>
        <section class="detail-section wide">
          <div class="section-title">事件结果</div>
          <p class="event-summary">${escapeHtml(event.summary || '')}</p>
          ${renderEffectResults(event.effect_results || [])}
        </section>
        <section class="detail-section wide">
          <div class="section-title">对话详录</div>
          <div class="event-dialogue event-dialogue-full">${(event.lines || []).map((line, index) => renderEventLine(line, index)).join('')}</div>
        </section>
      </div>
    `;
    openDetail();
    hydrateCharacterArt(document.getElementById('detailBody'));
    renderEventMapPreview(event);
  }

  function renderEffectResults(results) {
    if (!results.length) return '<div class="muted">没有产生受控状态变化</div>';
    return `<div class="effect-results">${results.map((result) => `
      <div class="effect-result ${result.applied ? 'applied' : 'rejected'}">
        <strong>${result.applied ? '已应用' : '已拒绝'}</strong>
        <span>${escapeHtml(result.reason || result.type || result.effect?.type || '状态效果')}</span>
      </div>`).join('')}</div>`;
  }

  function renderEventMapPreview(event) {
    const preview = document.getElementById('eventMapPreview');
    if (!preview || !canvas.width || !canvas.height) return;
    const previewContext = preview.getContext('2d');
    const location = normalizeEventLocation(event.location);
    const region = (spatial?.regions || []).find((item) => (
      item.location_id === location.id || getLocationName(item.location_id) === location.name
    ));
    const initiator = (runtime?.agents || []).find((item) => item.id === (event.initiator || event.participants?.[0]));
    const position = region?.bounds
      ? [region.bounds.x + region.bounds.w / 2, region.bounds.y + region.bounds.h / 2]
      : getAgentPosition(initiator || {}, null);
    const centerX = position[0] * tilePx;
    const centerY = position[1] * tilePx;
    const sourceWidth = Math.min(mapWorldWidth, Math.max(tilePx * 18, region?.bounds?.w * tilePx * 1.8 || tilePx * 18));
    const sourceHeight = Math.min(mapWorldHeight, sourceWidth * (preview.height / preview.width));
    const sourceX = Math.max(0, Math.min(mapWorldWidth - sourceWidth, centerX - sourceWidth / 2));
    const sourceY = Math.max(0, Math.min(mapWorldHeight - sourceHeight, centerY - sourceHeight / 2));
    previewContext.drawImage(
      canvas,
      sourceX * mapPixelRatio, sourceY * mapPixelRatio,
      sourceWidth * mapPixelRatio, sourceHeight * mapPixelRatio,
      0, 0, preview.width, preview.height
    );
    const markerX = ((centerX - sourceX) / sourceWidth) * preview.width;
    const markerY = ((centerY - sourceY) / sourceHeight) * preview.height;
    previewContext.fillStyle = '#df4f43';
    previewContext.beginPath();
    previewContext.arc(markerX, markerY, 8, 0, Math.PI * 2);
    previewContext.fill();
    previewContext.strokeStyle = '#fff7e8';
    previewContext.lineWidth = 3;
    previewContext.stroke();
  }

  function refreshOpenDetail() {
    if (!selectedEntity) return;
    if (selectedEntity.type === 'agent') {
      const agent = (runtime?.agents || []).find((item) => item.id === selectedEntity.id);
      if (agent) openAgentDetail(agent);
    } else if (selectedEntity.type === 'location') {
      const region = (spatial?.regions || []).find((item) => item.location_id === selectedEntity.id);
      if (region) openLocationDetail(region);
    } else if (selectedEntity.type === 'event') {
      const event = getGlobalEvents().find((item) => (
        (item.event_id || legacyEventId(item)) === selectedEntity.id
      ));
      if (event) openEventDetail(event);
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
    const semanticProfile = characterIndex.get(agent.id)
      || characterIndex.get(agent.profile?.id)
      || characterIndex.get(agent.profile?.wk_entity_id)
      || characterIndex.get(agent.profile?.name)
      || characterIndex.get(agent.id?.replaceAll('-', '_'))
      || {};
    return deepMerge(semanticProfile, agent.profile || {});
  }

  function getLocationProfile(locationIdOrName) {
    if (!locationIdOrName) return null;
    const semanticLocation = locationIndex.get(locationIdOrName)
      || locationIndex.get(String(locationIdOrName).replaceAll('-', '_'))
      || {};
    const lookupKeys = new Set([
      String(locationIdOrName),
      semanticLocation.id,
      semanticLocation.location_id,
      semanticLocation.identity?.id,
      semanticLocation.name,
      semanticLocation.identity?.name,
    ].filter(Boolean).map(String));
    const runtimeLocation = (runtime?.locations || []).find((item) => (
      [item.id, item.location_id, item.identity?.id, item.name, item.identity?.name]
        .filter(Boolean)
        .map(String)
        .some((key) => lookupKeys.has(key))
    ));
    if (!Object.keys(semanticLocation).length && !runtimeLocation) return null;
    return deepMerge(semanticLocation, runtimeLocation || {});
  }

  function deepMerge(base, overlay) {
    if (!base || typeof base !== 'object' || Array.isArray(base)) return overlay;
    if (!overlay || typeof overlay !== 'object' || Array.isArray(overlay)) return overlay ?? base;
    const result = { ...base };
    for (const [key, value] of Object.entries(overlay)) {
      if (
        value && typeof value === 'object' && !Array.isArray(value)
        && result[key] && typeof result[key] === 'object' && !Array.isArray(result[key])
      ) {
        result[key] = deepMerge(result[key], value);
      } else if (value !== undefined) {
        result[key] = value;
      }
    }
    return result;
  }

  function getLocationName(locationIdOrName) {
    const location = getLocationProfile(locationIdOrName);
    if (location) return location.name || location.identity?.name || '未命名地点';
    const raw = String(locationIdOrName || '');
    if (!raw) return '';
    if (raw.includes(':') || /^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(raw)) return '未知地点';
    return raw;
  }

  function getAgentPosition(agent, fallback) {
    const locationId = String(agent.location_id || agent.current_location || '');
    const fallbackLocationId = String(fallback?.location_id || '');
    const position = agent.position || fallback?.position || [0, 0];
    // Runtime position is only the initial presentation anchor. Once the
    // logical location changes, derive the display destination from the
    // spatial blueprint; Stage3 never needs route geometry or map bounds.
    if (!fallback || !locationId || locationId !== fallbackLocationId) {
      const region = (spatial?.regions || []).find((item) => (
        String(item.location_id || '') === locationId
      ));
      const entrance = region?.entrance;
      if (entrance && Number.isFinite(Number(entrance.x)) && Number.isFinite(Number(entrance.y))) {
        return [Number(entrance.x), Number(entrance.y)];
      }
    }
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
        action ? `${action}` : '',
        time !== undefined ? `时段: ${time}` : '',
        target ? `对象: ${target}` : '',
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

  function normalizeEvents(eventLog, dialogues, shortTermMemory) {
    let events = [];
    if (Array.isArray(eventLog)) {
      events = eventLog.filter((event) => event && typeof event === 'object');
    } else if (eventLog && typeof eventLog === 'object') {
      events = Object.entries(eventLog).flatMap(([tick, bucket]) => {
        const values = Array.isArray(bucket) ? bucket : [bucket];
        return values.filter((event) => event && typeof event === 'object')
          .map((event) => ({ tick: Number(event.tick ?? tick), ...event }));
      });
    }
    if (events.length) {
      return events.sort((left, right) => Number(left.tick || 0) - Number(right.tick || 0));
    }

    const memoryByTick = new Map(
      normalizeMemory(shortTermMemory).map((item) => [String(item.tick), item.content])
    );
    return Object.entries(dialogues || {}).map(([tick, lines]) => ({
      tick: Number(tick),
      type: 'interaction',
      summary: memoryByTick.get(String(tick)) || '',
      lines: Array.isArray(lines) ? lines : [String(lines)],
    })).sort((left, right) => Number(left.tick || 0) - Number(right.tick || 0));
  }

  function getGlobalEvents() {
    const source = Array.isArray(runtime?.events)
      ? runtime.events
      : (runtime?.agents || []).flatMap((agent) => normalizeEvents(
        agent.event_log, agent.dialogues, agent.short_term_memory
      ));
    const unique = new Map();
    source.forEach((event) => unique.set(event.event_id || legacyEventId(event), event));
    return [...unique.values()].sort((left, right) => (
      Number(left.tick || 0) - Number(right.tick || 0)
    ));
  }

  function legacyEventId(event) {
    return `legacy:${event.tick ?? ''}:${event.initiator || event.participants?.[0] || ''}:${event.summary || ''}`;
  }

  function eventTypeLabel(type) {
    return ({
      action: '行动事件',
      interaction: '互动事件',
      blocked: '受阻事件',
      idle: '间歇事件',
    })[type] || '世界事件';
  }

  function normalizeEventLocation(location) {
    if (location && typeof location === 'object') {
      return { id: location.id || location.location_id || '', name: location.name || location.location || '' };
    }
    return { id: String(location || ''), name: getLocationName(location) };
  }

  function startEventPlayback() {
    stopEventPlayback();
    const events = getGlobalEvents().filter((event) => (
      Number(event.tick) === Number(runtime?.current_tick)
    ));
    showEventMarkers(events);
    const steps = events.flatMap((event) => (event.lines || []).map((line) => ({ event, line })));
    if (!steps.length) return;
    const token = ++dialoguePlaybackToken;
    let index = 0;
    const advance = () => {
      if (token !== dialoguePlaybackToken || index >= steps.length) {
        stopEventPlayback();
        renderMapAgentLayer();
        return;
      }
      document.querySelectorAll('.speaking').forEach((element) => element.classList.remove('speaking'));
      const { event, line } = steps[index];
      const normalized = line && typeof line === 'object'
        ? line
        : { speaker: String(line || '').split(/[：:]/, 1)[0], text: String(line || '') };
      const speaker = normalized.speaker || '旁白';
      const eventId = event.event_id || legacyEventId(event);
      const marker = mapAgentLayer.querySelector(`[data-event-id="${CSS.escape(eventId)}"]`);
      if (marker) {
        marker.classList.add('speaking');
      }
      mapAgentLayer.querySelector(`[data-agent-id="${CSS.escape(speaker)}"]`)?.classList.add('speaking');
      document.querySelector(`[data-event-speaker="${CSS.escape(speaker)}"]`)?.classList.add('speaking');
      document.querySelector(`[data-dialogue-line="${index}"]`)?.classList.add('speaking');
      index += 1;
      dialoguePlaybackTimer = setTimeout(advance, 850);
    };
    advance();
  }

  function stopEventPlayback() {
    dialoguePlaybackToken += 1;
    if (dialoguePlaybackTimer) {
      clearTimeout(dialoguePlaybackTimer);
      dialoguePlaybackTimer = null;
    }
    document.querySelectorAll('.speaking').forEach((element) => element.classList.remove('speaking'));
  }

  function showEventMarkers(events) {
    hideEventMarkers({ render: false });
    visibleEventMarkerIds = new Set(
      events.map((event) => event.event_id || legacyEventId(event))
    );
    renderMapAgentLayer();
    if (!visibleEventMarkerIds.size) return;
    eventMarkerTimer = window.setTimeout(() => hideEventMarkers(), EVENT_MARKER_VISIBLE_MS);
  }

  function hideEventMarkers({ render = true } = {}) {
    if (eventMarkerTimer) {
      window.clearTimeout(eventMarkerTimer);
      eventMarkerTimer = null;
    }
    const hadVisibleMarkers = visibleEventMarkerIds.size > 0;
    visibleEventMarkerIds.clear();
    if (render && hadVisibleMarkers) renderMapAgentLayer();
  }

  function renderEventLog(events) {
    return `<div class="event-log">${events.map((event) => {
      const lines = Array.isArray(event.lines) ? event.lines : [];
      return `
        <button type="button" class="event-card" data-event-id="${escapeHtml(event.event_id || legacyEventId(event))}">
          <div class="event-meta">
            <span>Tick ${escapeHtml(event.tick ?? '-')}</span>
            <span>${escapeHtml(eventTypeLabel(event.type))}</span>
          </div>
          ${event.summary ? `<p class="event-summary">${escapeHtml(event.summary)}</p>` : ''}
          <div class="event-dialogue">
            ${lines.map(renderEventLine).join('') || '<div class="muted">暂无事件详录</div>'}
          </div>
        </button>
      `;
    }).join('')}</div>`;
  }

  function renderEventLine(line, index = -1) {
    if (line && typeof line === 'object') {
      return `
        <div class="event-line" data-dialogue-line="${index}" data-line-speaker="${escapeHtml(line.speaker || '旁白')}">
          <strong class="event-speaker">${escapeHtml(line.speaker || '旁白')}</strong>
          ${line.action ? `<span class="event-action">[${escapeHtml(line.action)}]</span>` : ''}
          <span class="event-text">${escapeHtml(line.text || '')}</span>
        </div>
      `;
    }
    const text = String(line || '');
    const match = text.match(/^([^：:]+)[：:]\s*(?:\[([^\]]+)\])?\s*(.*)$/);
    if (!match) return `<div class="event-line"><span class="event-text">${escapeHtml(text)}</span></div>`;
    const [, speaker, action, dialogue] = match;
    return `
      <div class="event-line">
        <strong class="event-speaker">${escapeHtml(speaker)}</strong>
        ${action ? `<span class="event-action">[${escapeHtml(action)}]</span>` : ''}
        <span class="event-text">${escapeHtml(dialogue)}</span>
      </div>
    `;
  }

  function bindEventLinks(root = document) {
    root.querySelectorAll('[data-event-id]').forEach((element) => {
      element.addEventListener('click', () => {
        const event = getGlobalEvents().find((item) => (
          (item.event_id || legacyEventId(item)) === element.dataset.eventId
        ));
        if (event) openEventDetail(event);
      });
    });
    root.querySelectorAll('[data-latest-agent-event]').forEach((element) => {
      element.addEventListener('click', () => {
        const agentId = element.dataset.latestAgentEvent;
        const event = getGlobalEvents().filter((item) => (
          (item.participants || []).includes(agentId)
        )).at(-1);
        if (event) openEventDetail(event);
      });
    });
  }

  function renderAgentRows(agents) {
    return `<div class="entity-list">${
      agents.map((agent) => `
        <button class="entity-row" data-modal-agent-id="${escapeHtml(agent.id)}">
          <span>${escapeHtml(agent.profile?.name || '未命名角色')}</span>
          <span>${escapeHtml(agent.is_active ? '活跃' : '未激活')}</span>
        </button>
      `).join('')
    }</div>`;
  }

  function renderTags(tags) {
    if (!tags || !tags.length) return '';
    return `<div class="chips">${tags.map((tag) => `<span class="chip">${escapeHtml(tag)}</span>`).join('')}</div>`;
  }

  function renderLocalizationNotice() {
    if (fieldPresentation?.status === 'ready' || !fieldPresentation?.unresolved_count) return '';
    return '<div class="muted presentation-localization-notice">部分字段名称正在本地化，完成后将自动显示。</div>';
  }

  function renderObject(obj, entityType, path, hiddenKeys = new Set()) {
    if (!obj || (typeof obj === 'object' && !Object.keys(obj).length)) {
      return '<div class="muted">暂无</div>';
    }
    if (Array.isArray(obj)) {
      return `<div class="value">${escapeHtml(obj.map((item) => formatValue(item, entityType, `${path}[]`, hiddenKeys)).filter(Boolean).join('\n'))}</div>`;
    }
    if (typeof obj !== 'object') {
      return `<div class="value">${escapeHtml(obj)}</div>`;
    }
    const rows = {};
    for (const [key, value] of Object.entries(obj)) {
      if (isEmptyValue(value) || key === 'raw' || hiddenKeys.has(key)) continue;
      const fieldPath = `${path}.${key}`;
      if (!isPresentedField(entityType, fieldPath, key)) continue;
      rows[labelKey(entityType, fieldPath, key)] = formatValue(value, entityType, fieldPath, hiddenKeys);
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

  function formatValue(value, entityType, path, hiddenKeys = new Set()) {
    if (value === true || value === 'true') return '是';
    if (value === false || value === 'false') return '否';
    if (Array.isArray(value)) {
      return value.map((item) => formatValue(item, entityType, `${path}[]`, hiddenKeys)).filter(Boolean).join('\n');
    }
    if (value && typeof value === 'object') {
      return Object.entries(value)
        .filter(([key, item]) => (
          key !== 'raw'
          && !hiddenKeys.has(key)
          && !isEmptyValue(item)
          && isPresentedField(entityType, `${path}.${key}`, key)
        ))
        .map(([key, item]) => {
          const fieldPath = `${path}.${key}`;
          return `${labelKey(entityType, fieldPath, key)}: ${formatValue(item, entityType, fieldPath, hiddenKeys)}`;
        })
        .filter(Boolean)
        .join('\n');
    }
    return String(value ?? '');
  }

  function formatBounds(bounds) {
    if (!bounds) return '';
    return `x:${bounds.x}, y:${bounds.y}, w:${bounds.w}, h:${bounds.h}`;
  }

  function presentationEntry(path) {
    const entry = fieldPresentation?.fields?.[path];
    return entry && typeof entry === 'object' ? entry : null;
  }

  function isPresentedField(_entityType, path, key) {
    const entry = presentationEntry(path);
    if (entry) return entry.visible !== false && Boolean(entry.label);
    return Boolean(keyLabels[key] || /[\u3400-\u9fff]/.test(key));
  }

  function labelKey(_entityType, path, key) {
    const entry = presentationEntry(path);
    if (entry?.visible !== false && entry?.label) return entry.label;
    return keyLabels[key] || (/[\u3400-\u9fff]/.test(key) ? key : '');
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
    const tickButton = document.getElementById('tickBtn');
    if (tickButton) tickButton.disabled = isBusy;
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
