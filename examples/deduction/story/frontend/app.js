/* ===== 红楼梦 · 群像志 · app.js ===== */

// ===== 剧情模式：玩家角色初始化 =====
let playerCharacter = null;
let pendingTaskTick = null; // 玩家等待下达任务的 tick

function initPlayerCharacter() {
  const stored = localStorage.getItem('story_player_character');
  if (!stored) {
    window.location.href = 'character_select.html';
    return;
  }
  playerCharacter = JSON.parse(stored);
  document.getElementById('playerName').textContent = playerCharacter.id;
  const sprite = document.getElementById('playerSprite');
  sprite.src = playerCharacter.sprite || '../map/sprite/普通人.png';
  sprite.onerror = () => { sprite.src = '../map/sprite/普通人.png'; };
  document.getElementById('assignTaskCharName').textContent = playerCharacter.id;

  // 通知服务器记录玩家角色（用于 InvokePlugin 校验）
  fetch('http://localhost:8001/story/set_player', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(playerCharacter)
  }).catch(e => console.warn('Failed to set player character on server:', e));
}

// ===== 下达任务 =====
function openAssignTaskModal() {
  document.getElementById('assignTaskAction').value = '';
  document.getElementById('assignTaskTarget').value = '';
  document.getElementById('assignTaskLocation').value = '';
  document.getElementById('assignTaskModal').style.display = 'flex';
}

function closeAssignTaskModal() {
  document.getElementById('assignTaskModal').style.display = 'none';
}

async function submitAssignTask() {
  const action = document.getElementById('assignTaskAction').value.trim();
  if (!action) { alert('请输入行动内容'); return; }
  const target = document.getElementById('assignTaskTarget').value.trim();
  const location = document.getElementById('assignTaskLocation').value.trim();

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'set_plan',
      agent_id: playerCharacter.id,
      action: action,
      target: target || null,
      location: location || ''
    }));
    closeAssignTaskModal();
    showToast(`已为 ${playerCharacter.id} 下达任务`);
  } else {
    alert('WebSocket 未连接，请检查服务器状态');
  }
}

function skipTask() {
  showToast('已跳过本轮任务下达，将由 AI 自动规划');
}

function openPlayerDetail() {
  if (!playerCharacter) return;
  const id = playerCharacter.id;
  selectedAgent = id;
  renderDetail(id);
  showAgentDetail();
  const box = document.getElementById('agentDetailBox');
  if (box) {
    const panel = box.querySelector('.detail-panel-content, #detailPanel');
    if (panel) panel.scrollTop = 0;
  }
}

// ===== 目标面板：分数更新 =====
// forHistory=true：只更新显示，不触发胜负判断
function updateGoalPanel(score, events, forHistory = false) {
  if (score === undefined || score === null) return;

  // Remove the initial "等待推演开始" placeholder on first real update
  const placeholder = document.querySelector('.goal-event-placeholder');
  if (placeholder) placeholder.remove();

  const scoreNum = document.getElementById('goalScoreNum');
  const fill = document.getElementById('goalProgressFill');

  scoreNum.textContent = score;
  const pct = Math.max(0, Math.min(100, score));
  fill.style.width = pct + '%';

  fill.classList.remove('danger', 'success');
  if (score <= 20) fill.classList.add('danger');
  else if (score >= 80) fill.classList.add('success');

  // 更新历史事件
  if (events && events.length > 0) {
    const list = document.getElementById('goalEventsList');
    events.forEach(ev => {
      const item = document.createElement('div');
      const delta = ev.delta > 0 ? `+${ev.delta}` : `${ev.delta}`;
      const cls = ev.delta > 0 ? 'plus' : 'minus';
      item.innerHTML = `
        <span class="event-delta ${cls}">${delta}</span>
        <span class="event-text">${ev.reason}</span>
      `;

      // 若事件关联了某个角色，允许点击跳转到该角色的详情面板
      if (ev.agent) {
        item.className = 'goal-event-item clickable';
        item.title = `点击查看 ${ev.agent} 的详情`;
        item.addEventListener('click', () => {
          // 如果 agentsData 里有这个角色（包括已离场的），就打开详情
          if (agentsData[ev.agent]) {
            selectedAgent = ev.agent;
            renderDetail(ev.agent);
          }
          showAgentDetail();
          const box = document.getElementById('agentDetailBox');
          if (box) {
            const panel = box.querySelector('.detail-panel-content, #detailPanel');
            if (panel) panel.scrollTop = 0;
          }
        });
      } else {
        item.className = 'goal-event-item';
      }

      list.insertBefore(item, list.firstChild);
    });
    // 最多保留30条
    while (list.children.length > 30) list.removeChild(list.lastChild);
  }

  // 胜负判断（历史查看模式下不触发）
  if (!forHistory) {
    if (score >= 100) showGameResult(true);
    else if (score <= 0) showGameResult(false);
  }
}

// 用快照中的历史事件（newest-first 数组）重建目标面板
function restoreGoalPanelFromSnapshot(score, eventsNewestFirst) {
  if (score === null || score === undefined) return;
  const list = document.getElementById('goalEventsList');
  if (list) list.innerHTML = '';
  // insertBefore(firstChild) 会把每个新条目置顶，所以需从最旧到最新依次添加
  const eventsOldestFirst = (eventsNewestFirst || []).slice().reverse();
  updateGoalPanel(score, eventsOldestFirst, true);
}

// ===== 胜负结局 =====
function showGameResult(isWin) {
  const overlay = document.getElementById('gameResultOverlay');
  const title = document.getElementById('gameResultTitle');
  const desc = document.getElementById('gameResultDesc');

  if (isWin) {
    title.textContent = '复兴成功';
    title.className = 'game-result-title';
    desc.textContent = '大观园在众人努力下重焕生机，往日的诗意繁华再度降临。';
  } else {
    title.textContent = '大观园衰败';
    title.className = 'game-result-title fail';
    desc.textContent = '稳定度跌至谷底，大观园终究未能逃脱颓败的命运。';
  }
  overlay.classList.add('show');
  document.getElementById('reportBtn').style.display = 'inline-block';
}

let _storyReportText = '';

function requestStoryReport() {
  document.getElementById('reportBtn').style.display = 'none';
  document.getElementById('storyReportPanel').style.display = 'block';
  document.getElementById('storyReportLoading').style.display = 'block';
  document.getElementById('storyReportContent').textContent = '';
}

function showStoryReport(report, outcome, finalScore) {
  _storyReportText = report;
  document.getElementById('storyReportLoading').style.display = 'none';
  document.getElementById('storyReportPanel').style.display = 'block';
  const content = document.getElementById('storyReportContent');
  content.textContent = report;
  document.getElementById('exportReportBtn').style.display = 'inline-block';
}

function exportStoryReport() {
  if (!_storyReportText) return;
  const blob = new Blob([_storyReportText], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = '红楼梦续写.txt';
  a.click();
  URL.revokeObjectURL(url);
}

async function restartGame() {
  try {
    await fetch('http://localhost:8001/story/game_restart', { method: 'POST' });
  } catch (e) {
    console.warn('Failed to signal game restart to server:', e);
  }
  localStorage.removeItem('story_player_character');
  window.location.href = 'character_select.html';
}

function showToast(msg) {
  const t = document.createElement('div');
  t.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:rgba(30,20,10,0.9);border:1px solid rgba(200,169,110,0.4);color:#c8a96e;padding:8px 20px;border-radius:6px;font-size:0.82rem;z-index:9999;pointer-events:none;';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2500);
}

const WS_URL = 'ws://localhost:8001/ws';
const SHICHEN = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'];

let ws = null;
let reconnectTimer = null;
let agentsData = {};
let selectedAgent = null;
let currentTick = -1;
let viewDays = {}; // 记录每个智能体当前查看的是第几天的计划
let pendingTickData = null; // 缓存后端推理完成的数据，等待用户手动触发展示
let agentsWithNewAction = new Set(); // 有未读新行动的 agent，头顶显示感叹号
let eventBubbles = []; // 当前 tick 的事件气泡列表 [{participants, text, createdAt}]
let activeDialogueContext = null; // 当前打开的对话对应的地图地点与侧栏信息
let activeDialogueReplay = null; // 当前地图上的自动循环对话回放状态

let tickHistory = []; // 记录已经模拟的 tick 数据历史
let currentHistoryIndex = -1; // 当前展示的历史索引
let _simulationAgentsSynced = false; // 首次 tick_update 后同步一次 agentsData 与实际模拟角色

// ── 回溯树 / 分支状态 ──────────────────────────────────────────────────────────
const BRANCH_COLORS = [
  '#ffd700','#4fc3f7','#81c784','#ff8a65',
  '#ce93d8','#80deea','#ffb74d','#f48fb1',
];
let branchTree = [];
let currentBranchId = 0;
let viewingTick = -1;
let viewingBranchId = -1;
let isViewingHistory = false;
let memoryTreeOpen = false;

// ===== 预设人物模板 =====
// 官方预设（不可删除）
const OFFICIAL_PRESETS = {
  sunwukong: {
    name: '孙悟空',
    isOfficial: true,
    avatarType: 'builtin',
    avatarSource: '../map/sprite/孙悟空.png',
    profile: {
      '家族': '花果山水帘洞',
      '性格': '桀骜不驯、嫉恶如仇、机智多变、重情重义',
      '核心驱动': '追寻自由与真理，看透红尘虚妄，在贾府中寻找有缘人',
      '语言风格': '直率豪放，常有惊人之语，不拘礼法，喜怒形于色',
      '背景经历': '五百年前大闹天宫的齐天大圣，因一场意外穿越至这红楼梦境。初来乍到，对贾府的繁文缛节颇感不适，却被大观园中真挚的情感所打动。隐去神通，化作凡人模样，想要看看这"情"字究竟有何魔力，能让世人如此痴迷。'
    },
    memory: [
      '初入贾府，只见亭台楼阁，花木扶疏，倒有些花果山的意趣',
      '听闻宝玉衔玉而生，心中暗笑：俺老孙当年也是石中蹦出，倒是有缘',
      '黛玉葬花之举，令俺想起当年被压五行山下，独自望月的孤寂',
      '贾府众人礼数繁多，俺且按捺性子，静观其变',
      '闻说此间有一"通灵宝玉"，不知与俺的金箍棒相比如何'
    ]
  },
  putongren: {
    name: '普通人',
    isOfficial: true,
    avatarType: 'builtin',
    avatarSource: '../map/sprite/普通人.png',
    profile: {
      '家族': '平民',
      '性格': '勤劳朴实、随遇而安',
      '核心驱动': '在这繁华的贾府中谋得一席之地，安稳度日',
      '语言风格': '朴实无华，言简意赅',
      '背景经历': '一个普通的百姓，因缘际会来到贾府谋生。虽无显赫家世，却有一颗善良的心。在这个大家族中小心翼翼地生活，见证着贾府的兴衰。'
    },
    memory: [
      '刚来到贾府，这里比我想象中大得多',
      '听说这里的主人都是些达官贵人，做事要小心',
      '希望能在这里安稳地工作生活'
    ]
  }
};

// 合并官方预设和用户自定义预设
function getAllPresets() {
  const userPresets = loadUserPresets();
  return { ...OFFICIAL_PRESETS, ...userPresets };
}

// 从 localStorage 加载用户自定义预设
function loadUserPresets() {
  try {
    const saved = localStorage.getItem('customAgentPresets');
    return saved ? JSON.parse(saved) : {};
  } catch (e) {
    console.error('Failed to load user presets:', e);
    return {};
  }
}

// 保存用户自定义预设到 localStorage
function saveUserPresets(presets) {
  try {
    localStorage.setItem('customAgentPresets', JSON.stringify(presets));
    return true;
  } catch (e) {
    console.error('Failed to save user presets:', e);
    return false;
  }
}

// 当前选中的头像信息
let currentAvatar = {
  type: 'builtin',
  source: '../map/sprite/普通人.png',
  name: '普通人'
};

// 选择头像
function selectAvatar(type, source, name, clickedBtn) {
  currentAvatar = { type, source, name };

  document.getElementById('avatarType').value = type;
  document.getElementById('avatarSource').value = source;

  const previewImg = document.getElementById('selectedAvatarImg');
  previewImg.src = source;
  previewImg.alt = name;

  // 更新选中状态
  document.querySelectorAll('.avatar-option-btn').forEach(btn => btn.classList.remove('selected'));
  if (clickedBtn) {
    clickedBtn.classList.add('selected');
  }
}

// 处理图片上传
function handleAvatarUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  if (!file.type.startsWith('image/')) {
    alert(t('upload_image_error'));
    return;
  }

  const reader = new FileReader();
  reader.onload = function(e) {
    const base64 = e.target.result;
    currentAvatar = {
      type: 'custom',
      source: base64,
      name: file.name.replace(/\.[^/.]+$/, '')
    };

    document.getElementById('avatarType').value = 'custom';
    document.getElementById('avatarSource').value = base64;

    const previewImg = document.getElementById('selectedAvatarImg');
    previewImg.src = base64;
    previewImg.alt = currentAvatar.name;

    // 取消其他选中状态
    document.querySelectorAll('.avatar-option-btn').forEach(btn => btn.classList.remove('selected'));
  };
  reader.readAsDataURL(file);
}

// 渲染预设按钮
function renderPresetButtons() {
  const grid = document.getElementById('presetGrid');
  if (!grid) return;

  const presets = getAllPresets();
  grid.innerHTML = '';

  Object.entries(presets).forEach(([key, preset]) => {
    const isOfficial = preset.isOfficial;

    // 用 div 包裹，避免 button 嵌套 button 的 HTML 非法问题
    const wrapper = document.createElement('div');
    wrapper.className = 'preset-btn';
    wrapper.dataset.presetKey = key;

    const img = document.createElement('img');
    img.src = preset.avatarSource || '../map/sprite/普通人.png';
    img.alt = preset.name;
    img.className = 'preset-avatar';
    img.onerror = function() { this.src = '../map/sprite/普通人.png'; };

    const nameSpan = document.createElement('span');
    nameSpan.className = 'preset-name';
    nameSpan.textContent = preset.name;

    const tagSpan = document.createElement('span');
    tagSpan.className = 'preset-tag';
    tagSpan.textContent = isOfficial ? t('official') : t('custom');

    wrapper.appendChild(img);
    wrapper.appendChild(nameSpan);
    wrapper.appendChild(tagSpan);

    // 非官方预设才有删除按钮
    if (!isOfficial) {
      const deleteBtn = document.createElement('button');
      deleteBtn.type = 'button';
      deleteBtn.className = 'preset-delete-btn';
      deleteBtn.textContent = '×';
      deleteBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        deletePreset(key);
      });
      wrapper.appendChild(deleteBtn);
    }

    // 点击整个卡片选择预设
    wrapper.addEventListener('click', function() {
      selectPresetTemplate(key, wrapper);
    });

    grid.appendChild(wrapper);
  });
}

// 选择预设模板
function selectPresetTemplate(templateKey, clickedBtn) {
  const presets = getAllPresets();
  const template = presets[templateKey];
  if (!template) {
    console.error('Template not found:', templateKey);
    return;
  }

  console.log('Selecting preset:', templateKey, template);

  // 填充表单
  document.getElementById('agentId').value = template.name;
  document.getElementById('profileFamily').value = template.profile['家族'] || '';
  document.getElementById('profilePersonality').value = template.profile['性格'] || '';
  document.getElementById('profileDrive').value = template.profile['核心驱动'] || '';
  document.getElementById('profileStyle').value = template.profile['语言风格'] || '';
  document.getElementById('profileBackground').value = template.profile['背景经历'] || '';
  document.getElementById('agentMemory').value = (template.memory || []).join('\n');

  // 设置头像
  if (template.avatarType && template.avatarSource) {
    currentAvatar = {
      type: template.avatarType,
      source: template.avatarSource,
      name: template.name
    };
    document.getElementById('avatarType').value = template.avatarType;
    document.getElementById('avatarSource').value = template.avatarSource;
    document.getElementById('selectedAvatarImg').src = template.avatarSource;
  }

  // 高亮选中的按钮
  document.querySelectorAll('.preset-btn').forEach(btn => btn.classList.remove('selected'));
  if (clickedBtn) {
    clickedBtn.classList.add('selected');
  }
}

// 保存当前表单为预设
function saveAsPreset() {
  const name = document.getElementById('agentId').value.trim();
  if (!name) {
    alert(t('error_no_name'));
    return;
  }

  const profile = {};
  const family = document.getElementById('profileFamily').value.trim();
  const personality = document.getElementById('profilePersonality').value.trim();
  const drive = document.getElementById('profileDrive').value.trim();
  const style = document.getElementById('profileStyle').value.trim();
  const background = document.getElementById('profileBackground').value.trim();

  if (family) profile['家族'] = family;
  if (personality) profile['性格'] = personality;
  if (drive) profile['核心驱动'] = drive;
  if (style) profile['语言风格'] = style;
  if (background) profile['背景经历'] = background;

  const memoryText = document.getElementById('agentMemory').value.trim();
  const memory = memoryText ? memoryText.split('\n').filter(line => line.trim()) : [];

  // 检查是否已存在同名预设
  const userPresets = loadUserPresets();
  const presetKey = 'custom_' + Date.now();

  // 生成唯一key
  const existingKeys = Object.keys(userPresets);
  let finalKey = presetKey;
  let counter = 1;
  while (userPresets[finalKey]) {
    finalKey = `custom_${Date.now()}_${counter}`;
    counter++;
  }

  const newPreset = {
    name,
    isOfficial: false,
    avatarType: currentAvatar.type,
    avatarSource: currentAvatar.source,
    profile,
    memory,
    createdAt: Date.now()
  };

  userPresets[finalKey] = newPreset;

  if (saveUserPresets(userPresets)) {
    alert(t('save_preset_success'));
    renderPresetButtons();
  } else {
    alert(t('save_preset_error'));
  }
}

// 删除预设
function deletePreset(presetKey) {
  const presets = getAllPresets();
  const preset = presets[presetKey];

  if (preset && preset.isOfficial) {
    alert(t('official_cannot_delete'));
    return;
  }

  if (!confirm(t('confirm_delete_preset'))) {
    return;
  }

  const userPresets = loadUserPresets();
  delete userPresets[presetKey];

  if (saveUserPresets(userPresets)) {
    renderPresetButtons();
  }
}



// ===== WebSocket =====
let isReconnectingAfterRestart = false;

function connect() {
  clearTimeout(reconnectTimer);
  setStatus('connecting');
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    setStatus('connected');
    if (isReconnectingAfterRestart) {
      isReconnectingAfterRestart = false;
      window.location.reload();
    }
    ws.send(JSON.stringify({ type: 'get_branch_tree' }));
  };

  ws.onmessage = (e) => {
    console.log('Received message:', e.data);
    try {
      const msg = JSON.parse(e.data);
      console.log('Parsed message type:', msg.type);
      if (msg.type === 'snapshot' || msg.type === 'tick_update') {
        // 缓存后端数据，等待用户点击”开始模拟”后再展示
        pendingTickData = msg;

        // 剧情模式：不隐藏设置按钮

        document.getElementById('startTickBtn').disabled = true;
        document.getElementById('applyTickBtn').disabled = false;

        // 推演完成，更新状态文本提示用户可以开始模拟
        const statusTxt = document.getElementById('statusText');
        if (statusTxt) statusTxt.textContent = '推演完成';
        const statusDot = document.getElementById('statusDot');
        if (statusDot) {
          statusDot.className = 'status-dot connected';
        }
      } else if (msg.type === 'game_reset') {
        // Backend flushed Redis for a new game session (may have wiped the player character
        // that was registered before the flush). Re-register so the backend can proceed.
        if (playerCharacter) {
          fetch('http://localhost:8001/story/set_player', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(playerCharacter)
          }).catch(e => console.warn('Re-register player after game_reset failed:', e));
        }
      } else if (msg.type === 'simulation_ready') {
        // Backend tick loop is now waiting for user input — enable the start button.
        if (!pendingTickData) {
          const startBtn = document.getElementById('startTickBtn');
          if (startBtn) startBtn.disabled = false;
          const statusTxt = document.getElementById('statusText');
          if (statusTxt) statusTxt.textContent = '已连接';
        }
      } else if (msg.type === 'story_score_update') {
        // 剧情模式：稳定度分数更新
        updateGoalPanel(msg.story_score, msg.score_events || []);
      } else if (msg.type === 'story_report') {
        showStoryReport(msg.report, msg.outcome, msg.final_score);
      } else if (msg.type === 'add_agent_response') {
        // 处理添加人物的响应
        handleAddAgentResponse(msg);
      } else if (msg.type === 'agent_added') {
        // 新 agent 添加成功，更新前端显示
        const newAgentData = msg.data;
        if (newAgentData && msg.agent_id) {
          agentsData[msg.agent_id] = newAgentData;

          // 如果有头像信息，保存
          if (msg.avatar) {
            customAgentAvatars[msg.agent_id] = msg.avatar;
            saveCustomAvatars();
          }

          // 初始化闲逛状态
          if (newAgentData.profile && newAgentData.profile.position && (newAgentData.profile.position[0] !== 0 || newAgentData.profile.position[1] !== 0)) {
            // 如果已有有效位置，使用它
            const startX = newAgentData.profile.position[0] * mapData.tileWidth;
            const startY = newAgentData.profile.position[1] * mapData.tileHeight;
            agentIdleStates[msg.agent_id] = {
              currentX: startX,
              currentY: startY,
              targetX: startX,
              targetY: startY,
              lastUpdate: Date.now(),
              nextMoveTime: Date.now() + Math.random() * 2000
            };
          } else if (mapData) {
            // 如果没有有效位置，分配随机可通行位置
            assignRandomPositionToAgent(msg.agent_id);
          }

          // 预加载人物图片
          const name = formatAgentName(msg.agent_id);
          const customAvatar = customAgentAvatars[msg.agent_id];

          if (customAvatar && customAvatar.type === 'custom') {
            // 自定义头像
            if (!agentSprites[msg.agent_id]) {
              const img = new Image();
              img.src = customAvatar.source;
              agentSprites[msg.agent_id] = img;
            }
          } else {
            // 默认头像
            if (!agentSprites[name]) {
              const img = new Image();
              img.src = `../map/sprite/${name}.png`;
              agentSprites[name] = img;
            }
          }

          // 刷新人物列表
          renderAgentList();
          console.log(`Agent '${msg.agent_id}' added and displayed.`);
        }
      } else if (msg.type === 'branch_tree') {
        const newTreeStr = JSON.stringify(msg.branches || []);
        const oldTreeStr = JSON.stringify(branchTree);
        const newBranchId = msg.current_branch_id ?? 0;
        const branchIdChanged = newBranchId !== currentBranchId;
        branchTree = msg.branches || [];
        currentBranchId = newBranchId;
        if (newTreeStr !== oldTreeStr || branchIdChanged) {
          renderBranchTree();
        }
      } else if (msg.type === 'branch_created') {
        branchTree = msg.branches || [];
        currentBranchId = msg.current_branch_id ?? 0;
        isViewingHistory = false;
        viewingTick = -1;
        viewingBranchId = -1;
        // 重置稳定度面板到 fork 点的历史分数
        if (msg.restored_score !== null && msg.restored_score !== undefined) {
          restoreGoalPanelFromSnapshot(msg.restored_score, msg.restored_events || []);
        } else {
          const list = document.getElementById('goalEventsList');
          if (list) list.innerHTML = '';
        }
        updateHistoryModeBanner();
        renderBranchTree();
        renderAgentList();
        if (selectedAgent && agentsData[selectedAgent]) {
          renderDetail(selectedAgent);
        }
      } else if (msg.type === 'view_tick_ack') {
        if (msg.data) {
          viewingTick = msg.tick;
          viewingBranchId = msg.branch_id;
          isViewingHistory = true;
          const newData = msg.data;
          Object.keys(agentsData).forEach(id => {
            if (!newData[id]) delete agentsData[id];
          });
          if (selectedAgent && newData[selectedAgent]) {
            const snapTick = newData[selectedAgent].current_tick ?? msg.tick;
            viewDays[selectedAgent] = Math.floor(snapTick / 12) + 1;
          }
          applyAgentsData(newData, msg.tick);
          // 恢复该历史节点的稳定度分数与事件列表
          if (msg.score !== null && msg.score !== undefined) {
            restoreGoalPanelFromSnapshot(msg.score, msg.score_events || []);
          }
          if (selectedAgent) {
            if (agentsData[selectedAgent]) {
              renderDetail(selectedAgent);
            } else {
              const panel = document.getElementById('detailPanel');
              if (panel) panel.innerHTML = '<div class="empty-state"><div class="empty-icon">卷</div><p>该角色在此时间线中尚未出现</p></div>';
            }
          }
          updateHistoryModeBanner();
          renderBranchTree();
        }
      }
    } catch (err) { console.error('parse error', err); }
  };

  ws.onerror = () => setStatus('error');
  ws.onclose = () => {
    setStatus('error');
    reconnectTimer = setTimeout(connect, 3000);
  };
}

let agentSprites = {}; // 缓存人物图片对象
let agentIdleStates = {}; // 存储人物的闲逛状态 (currentX/Y, targetX/Y, lastUpdate)
let npcs = []; // 存储虚拟小厮数据
let agentScreenPositions = {}; // 每帧记录各 agent 的屏幕坐标，用于点击检测
// 将 tick 转换为中文日期（起点：1784年1月1日，每 tick = 2小时）
function tickToChineseDate(tick) {
  const HOURS_PER_TICK = 2;
  const START_YEAR = 1784;
  // 乾隆四十九年 = 1784年
  const QIANLONG_BASE = 49;

  const totalHours = tick * HOURS_PER_TICK;
  const days = Math.floor(totalHours / 24);
  const hour = (totalHours % 24);

  // 计算年月日（简化：每月30天，每年12月）
  const year = START_YEAR + Math.floor(days / 360);
  const dayOfYear = days % 360;
  const month = Math.floor(dayOfYear / 30) + 1;
  const day = (dayOfYear % 30) + 1;

  const qianlongYear = QIANLONG_BASE + (year - START_YEAR);
  const monthNames = ['正','二','三','四','五','六','七','八','九','十','冬','腊'];
  const dayNames = ['初一','初二','初三','初四','初五','初六','初七','初八','初九','初十',
    '十一','十二','十三','十四','十五','十六','十七','十八','十九','二十',
    '廿一','廿二','廿三','廿四','廿五','廿六','廿七','廿八','廿九','三十'];
  const shiChen = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'];
  const shiIdx = Math.floor(hour / 2) % 12;

  return `乾隆${qianlongYear}年 ${monthNames[month - 1]}月${dayNames[day - 1]} ${shiChen[shiIdx]}时`;
}


let citizens = []; // 存储边缘市民数据
let citizenSpriteNames = ['市民1', '市民2', '市民3', '市民4', '市民5'];
let lastCitizenSpawnTime = 0;
const CITIZEN_SPAWN_INTERVAL = 2000; // 每2秒尝试生成一个市民
const MAX_CITIZENS = 20; // 最多同时存在的市民数量

// 首次 tick_update 时，将 agentsData 与实际模拟角色同步：
// 删除预加载进来但后端没有实际运行的角色（如孙悟空未被选中时）。
// 自定义角色（isCustom: true）不删除。
function syncSimulationAgents(tickData) {
  if (_simulationAgentsSynced || !tickData) return;
  _simulationAgentsSynced = true;
  const simulationIds = new Set(Object.keys(tickData));
  Object.keys(agentsData).forEach(id => {
    if (!simulationIds.has(id)) {
      const isCustom = agentsData[id] && agentsData[id].profile && agentsData[id].profile.isCustom;
      if (!isCustom) {
        delete agentsData[id];
        delete agentIdleStates[id];
      }
    }
  });
}

function mergeData(data) {
  if (!data) return;
  let needsReinit = false;
  const now = Date.now();

  for (const [id, d] of Object.entries(data)) {
    if (!agentsData[id]) {
      needsReinit = true;
    }
    
    // 如果位置发生了真实变化（后端发来的新位置），重置闲逛起点为新位置
    if (agentsData[id] && agentsData[id].profile && agentsData[id].profile.position && 
        d.profile && d.profile.position && 
        (agentsData[id].profile.position[0] !== d.profile.position[0] || 
         agentsData[id].profile.position[1] !== d.profile.position[1])) {
      if (agentIdleStates[id]) {
        agentIdleStates[id].currentX = d.profile.position[0] * mapData.tileWidth;
        agentIdleStates[id].currentY = d.profile.position[1] * mapData.tileHeight;
        agentIdleStates[id].targetX = agentIdleStates[id].currentX;
        agentIdleStates[id].targetY = agentIdleStates[id].currentY;
      }
    }

    // 如果后端 profile 没有 position，保留旧的 position（防止 agent 从地图消失）
    const oldPosition = agentsData[id]?.profile?.position;
    agentsData[id] = d;
    if (d.profile && !d.profile.position && oldPosition) {
      d.profile.position = oldPosition;
    }

    // 将静态人物志合并进 profile，后端字段优先
    const agentName = formatAgentName(id);
    const staticP = staticProfiles[agentName];
    if (staticP) {
      if (!d.profile) d.profile = {};
      for (const [k, v] of Object.entries(staticP)) {
        if (!d.profile[k]) d.profile[k] = v;
      }
    }

    // 初始化闲逛状态
    if (!agentIdleStates[id] && d.profile && d.profile.position) {
      const startX = d.profile.position[0] * mapData.tileWidth;
      const startY = d.profile.position[1] * mapData.tileHeight;
      agentIdleStates[id] = {
        currentX: startX,
        currentY: startY,
        targetX: startX,
        targetY: startY,
        lastUpdate: now,
        nextMoveTime: now + Math.random() * 2000
      };
    }

    // 如果没有记录该智能体的查看天数，或者它是新生成的（当前tick对应的天）
    const day = Math.floor((d.current_tick || 0) / 12) + 1;
    if (viewDays[id] === undefined) {
      viewDays[id] = day;
    }
    
    // 预加载人物图片
    const name = formatAgentName(id);
    if (!agentSprites[name]) {
      const img = new Image();
      img.src = `../map/sprite/${name}.png`;
      agentSprites[name] = img;
    }

    // 收到后端的当前时辰目标地点，模糊匹配并触发移动
    if (d.current_location && mapData && mapData.locations && agentIdleStates[id]) {
      const targetLocName = d.current_location;
      // 模糊匹配：优先完全匹配，其次包含关系
      let matched = mapData.locations.find(l => l.name === targetLocName);
      if (!matched) {
        matched = mapData.locations.find(l => l.name.includes(targetLocName) || targetLocName.includes(l.name));
      }
      if (!matched && mapData.locations.length > 0) {
        // 最后兜底：找名称中有最多公共字符的地点
        let bestScore = 0;
        for (const loc of mapData.locations) {
          let score = 0;
          for (const ch of targetLocName) {
            if (loc.name.includes(ch)) score++;
          }
          if (score > bestScore) { bestScore = score; matched = loc; }
        }
      }
      if (matched && matched.tiles && matched.tiles.length > 0) {
        const state = agentIdleStates[id];
        // 从目标地点的可通行格子中随机选一个
        let candidates = matched.tiles;
        if (mapData.passableGids) {
          const passable = matched.tiles.filter(idx => mapData.passableGids[idx] !== 0);
          if (passable.length > 0) candidates = passable;
        }
        const tileIdx = candidates[Math.floor(Math.random() * candidates.length)];
        const destX = (tileIdx % mapData.width);
        const destY = Math.floor(tileIdx / mapData.width);
        const startX = Math.floor(state.currentX / mapData.tileWidth);
        const startY = Math.floor(state.currentY / mapData.tileHeight);
        state.targetX = destX * mapData.tileWidth;
        state.targetY = destY * mapData.tileHeight;
        state.path = findPath(startX, startY, destX, destY);
        state.pathIndex = 0;
        // 禁止闲逛，直到到达目的地后再开始
        state.movingToTarget = true;
        state.nextMoveTime = Infinity;
      }
    }
  }
  
  // 如果有新人物加入，且地图已加载，重新初始化位置
  if (needsReinit && mapData) {
    initializeAgentPositions();
  }
}

function setStatus(state) {
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');
  const list = document.getElementById('agentList');
  const startBtn = document.getElementById('startTickBtn');
  const applyBtn = document.getElementById('applyTickBtn');
  const addAgentBtn = document.getElementById('addAgentBtn');
  const resetBtn = document.getElementById('resetBtn');
  const settingsBtn = document.getElementById('settingsBtn');
  const restartingOverlay = document.getElementById('restartingOverlay');
  
  dot.className = 'status-dot';
  if (state === 'connected') { 
    dot.classList.add('connected'); 
    txt.textContent = '已连接'; 
    if (Object.keys(agentsData).length === 0) {
      list.innerHTML = '<div class="agent-placeholder">已连接，等待角色数据…</div>';
    }
    if (startBtn && applyBtn) {
      const canApply = !!pendingTickData;
      // startTickBtn is only re-enabled via simulation_ready, not on mere WS connect,
      // to prevent the user from clicking before the backend tick loop is ready.
      startBtn.disabled = true;
      applyBtn.disabled = !canApply;
    }
    if (addAgentBtn) addAgentBtn.disabled = false;
    if (resetBtn) resetBtn.disabled = false;
    if (settingsBtn) settingsBtn.disabled = false;
    if (restartingOverlay) restartingOverlay.classList.remove('active');
  }
  else if (state === 'error') { 
    dot.classList.add('error'); 
    txt.textContent = '断开连接'; 
    if (startBtn) startBtn.disabled = true;
    if (applyBtn) applyBtn.disabled = true;
    if (addAgentBtn) addAgentBtn.disabled = true;
    if (resetBtn) resetBtn.disabled = true;
    if (settingsBtn) settingsBtn.disabled = true;
    if (restartingOverlay) restartingOverlay.classList.add('active');
  }
  else { 
    txt.textContent = '连接中…'; 
    if (startBtn) startBtn.disabled = true;
    if (applyBtn) applyBtn.disabled = true;
    if (addAgentBtn) addAgentBtn.disabled = true;
    if (resetBtn) resetBtn.disabled = true;
    if (settingsBtn) settingsBtn.disabled = true;
    if (restartingOverlay) restartingOverlay.classList.add('active');
  }
}

// 发送开始推演信号给后端
function sendStartTick() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    // If we are viewing history, jump to latest before starting next tick
    if (currentHistoryIndex !== -1 && currentHistoryIndex < tickHistory.length - 1) {
      currentHistoryIndex = tickHistory.length - 1;
      applyHistoryTick(tickHistory[currentHistoryIndex]);
    }
    
    ws.send(JSON.stringify({ type: 'start_tick' }));
    // 禁用开始推演按钮，表示正在推演中
    document.getElementById('startTickBtn').disabled = true;
    const applyBtn = document.getElementById('applyTickBtn');
    if (applyBtn) {
      applyBtn.disabled = true;
    }
    
    // 更新状态文本为“正在推演”
    const txt = document.getElementById('statusText');
    if (txt) {
      txt.textContent = '正在推演...';
    }
  }
}

function updateTickNavButtons() {
  const prevBtn = document.getElementById('prevTickBtn');
  const nextBtn = document.getElementById('nextTickBtn');
  if (prevBtn) prevBtn.disabled = currentHistoryIndex <= 0;
  if (nextBtn) nextBtn.disabled = currentHistoryIndex >= tickHistory.length - 1;
}

function applyHistoryTick(msg) {
  currentTick = msg.tick;
  document.getElementById('tickNum').textContent = msg.tick >= 0 ? msg.tick : '—';
  if (msg.tick >= 0) {
    const timeString = tickToChineseDate(msg.tick);
    document.getElementById('simDate').textContent = timeString;
  }
  
  // Create a deep copy to prevent modifications from affecting history
  const historyData = JSON.parse(JSON.stringify(msg.data));
  mergeData(historyData);
  Object.keys(agentsData).forEach(id => agentsWithNewAction.add(id));
  buildEventBubbles();
  renderAgentList();
  if (selectedAgent && agentsData[selectedAgent]) {
    renderDetail(selectedAgent);
  }
  updateTickNavButtons();
}

function prevTick() {
  if (currentHistoryIndex > 0) {
    currentHistoryIndex--;
    applyHistoryTick(tickHistory[currentHistoryIndex]);
  }
}

function nextTick() {
  if (currentHistoryIndex < tickHistory.length - 1) {
    currentHistoryIndex++;
    applyHistoryTick(tickHistory[currentHistoryIndex]);
  }
}

// 应用缓存的回合数据，开始展示动画
function applyPendingTick() {
  if (!pendingTickData) return;
  const msg = pendingTickData;
  pendingTickData = null;
  
  // 保存到历史记录
  const msgCopy = JSON.parse(JSON.stringify(msg));
  tickHistory.push(msgCopy);
  currentHistoryIndex = tickHistory.length - 1;
  updateTickNavButtons();

  const btn = document.getElementById('applyTickBtn');
  btn.disabled = true;
  document.getElementById('startTickBtn').disabled = false;

  // 获取即将应用的新时间字符串
  const timeString = msg.tick >= 0 ? tickToChineseDate(msg.tick) : null;

  // 触发大字全屏动画
  const overlay = document.getElementById('timeTransitionOverlay');
  const textEl = document.getElementById('timeTransitionText');
  
  if (overlay && textEl && timeString) {
    // 提取年月日和时辰，分行显示，更具古风
    // "乾隆四十九年 正月初一 子时" -> ["乾隆四十九年", "正月初一", "子时"]
    const parts = timeString.split(' ');
    textEl.innerHTML = parts.join('<br/>');
    
    overlay.classList.add('active');
    
    // 在遮罩不透明时，悄悄更新底层数据
    setTimeout(() => {
      currentTick = msg.tick;
      document.getElementById('tickNum').textContent = msg.tick >= 0 ? msg.tick : '—';
      if (msg.tick >= 0) document.getElementById('simDate').textContent = timeString;
      syncSimulationAgents(msg.data);
      mergeData(msg.data);
      // 新 tick 数据应用后，所有 agent 标记为有新行动，并生成事件气泡
      Object.keys(agentsData).forEach(id => agentsWithNewAction.add(id));
      buildEventBubbles();
      renderAgentList();
      if (selectedAgent && agentsData[selectedAgent]) {
        renderDetail(selectedAgent);
      }
      
      // 遮罩淡出
      setTimeout(() => {
        overlay.classList.remove('active');
        document.getElementById('startTickBtn').disabled = false;
        const applyBtn = document.getElementById('applyTickBtn');
        if (applyBtn) {
          applyBtn.disabled = true;
        }
      }, 1500); // 大字展示 1.5 秒后淡出
      
    }, 800); // 等待遮罩淡入 0.8 秒
  } else {
    // 如果找不到遮罩元素，回退到原来的直接更新逻辑
    currentTick = msg.tick;
    document.getElementById('tickNum').textContent = msg.tick >= 0 ? msg.tick : '—';
    if (msg.tick >= 0) document.getElementById('simDate').textContent = timeString;
    syncSimulationAgents(msg.data);
    mergeData(msg.data);
    Object.keys(agentsData).forEach(id => agentsWithNewAction.add(id));
    buildEventBubbles();
    renderAgentList();
    if (selectedAgent && agentsData[selectedAgent]) {
      renderDetail(selectedAgent);
    }
    document.getElementById('startTickBtn').disabled = false;
    const applyBtn = document.getElementById('applyTickBtn');
    if (applyBtn) {
      applyBtn.disabled = true;
    }
  }
}

// 根据当前 agentsData 构建事件气泡（有 target 的互动）
function buildEventBubbles() {
  eventBubbles = [];
  const seen = new Set(); // 避免重复（A→B 和 B→A 只显示一次）

  for (const [id, d] of Object.entries(agentsData)) {
    const plan = d.current_plan;
    if (!Array.isArray(plan) || !plan[2] || plan[2] === '无' || plan[2] === '自己') continue;
    const target = plan[2];
    const action = plan[0] || '';
    const text = d.current_action || action;
    if (!text) continue;

    const key = [id, target].sort().join('|');
    if (seen.has(key)) continue;
    seen.add(key);

    const mems = d.short_term_memory;
    const mem = mems && mems.length ? mems[mems.length - 1] : null;
    const hasDialogue = !!(mem && mem.tick !== null && d.dialogues && d.dialogues[mem.tick]);

    eventBubbles.push({
      participants: [id, target],
      text,
      agentId: id,
      hasDialogue,
      createdAt: performance.now(),
    });
  }

  syncAutoDialogueReplay();
}

// 推断角色当前状态文字，优先使用后端数据，兜底用前端移动状态
function getAgentStatusText(id) {
  const d = agentsData[id];
  if (!d) return t('status_idle');

  // 1. 被他人占用（协助/聊天）
  if (d.occupied_by) {
    const who = formatAgentName(d.occupied_by.occupier || '');
    const act = d.occupied_by.action || '';
    if (act) return truncate(act, 16);
    return who ? `正与${who}交谈` : '正在交谈';
  }

  // 2. 当前计划
  if (Array.isArray(d.current_plan) && d.current_plan[0]) {
    return truncate(d.current_plan[0], 16);
  }
  if (typeof d.current_plan === 'string' && d.current_plan) {
    return truncate(d.current_plan, 16);
  }

  // 3. 前端移动状态
  const state = agentIdleStates[id];
  if (state && state.path && state.pathIndex < (state.path.length || 0)) {
    // 找目标地点名
    const tx = state.targetX / mapData.tileWidth;
    const ty = state.targetY / mapData.tileHeight;
    const tileIdx = Math.round(ty) * mapData.width + Math.round(tx);
    const loc = mapData.locations && mapData.locations.find(l => l.tiles && l.tiles.includes(tileIdx));
    return loc ? `前往${loc.name}` : '移动中';
  }

  return t('status_idle');
}


// 返回状态灯颜色：green=闲逛 blue=移动 yellow=执行计划 red=被占用/交谈
function getAgentStatusColor(id) {
  const d = agentsData[id];
  if (!d) return 'green';
  if (d.is_active === false) return 'grey';
  if (d.occupied_by) return 'red';
  if (Array.isArray(d.current_plan) && d.current_plan[0]) return 'yellow';
  if (typeof d.current_plan === 'string' && d.current_plan) return 'yellow';
  const state = agentIdleStates[id];
  if (state && state.path && state.pathIndex < (state.path.length || 0)) return 'blue';
  return 'green';
}

function renderAgentList() {
  const list = document.getElementById('agentList');
  // 剧情模式：过滤掉玩家自己的角色
  const allIds = Object.keys(agentsData);
  const ids = allIds.filter(id => !playerCharacter || id !== playerCharacter.id);
  if (!ids.length) { list.innerHTML = '<div class="agent-placeholder">等待数据…</div>'; return; }

  // 清空列表
  list.innerHTML = '';

  ids.forEach(id => {
    const d = agentsData[id];
    const active = id === selectedAgent;
    const name = formatAgentName(id);
    const task = getAgentStatusText(id);
    const inactiveClass = d.is_active === false ? ' agent-inactive' : '';

    const card = document.createElement('div');
    card.className = `agent-card${active ? ' active' : ''}${inactiveClass}`;
    card.onclick = () => selectAgent(id);

    // 头像
    const avatar = document.createElement('img');
    avatar.className = 'agent-card-avatar';
    avatar.alt = name;
    avatar.onerror = () => {
      avatar.onerror = null;
      avatar.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"%3E%3Cpath fill="%23888" d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/%3E%3C/svg%3E';
    };

    // 检查是否有自定义头像
    const customAvatar = customAgentAvatars[id];
    if (customAvatar && customAvatar.type === 'custom') {
      avatar.src = customAvatar.source;
    } else {
      avatar.src = `../map/sprite/${name}.png`;
    }

    const contentDiv = document.createElement('div');
    contentDiv.className = 'agent-card-content';

    const nameDiv = document.createElement('div');
    nameDiv.className = 'agent-card-name';
    nameDiv.textContent = name + (d.is_active === false ? ' (已离场)' : '');

    const taskDiv = document.createElement('div');
    taskDiv.className = 'agent-card-task';

    const taskText = document.createElement('span');
    taskText.textContent = task;
    taskDiv.appendChild(taskText);

    const dot = document.createElement('span');
    const dotColor = { green: '#4caf50', blue: '#42a5f5', yellow: '#ffc107', red: '#ef5350', grey: '#666' }[getAgentStatusColor(id)] || '#4caf50';
    dot.style.cssText = `display:inline-block;width:8px;height:8px;border-radius:50%;background:${dotColor};box-shadow:0 0 5px ${dotColor};flex-shrink:0;align-self:center;margin-left:auto;`;

    contentDiv.appendChild(nameDiv);
    contentDiv.appendChild(taskDiv);

    card.appendChild(avatar);
    card.appendChild(contentDiv);
    card.appendChild(dot);
    list.appendChild(card);
  });
}

function formatAgentName(id) {
  // Try to extract a readable name from agent id (split by . _ or -)
  const parts = id.split(/[\._\-]/);
  return parts[parts.length - 1] || id;
}

function selectAgent(id) {
  selectedAgent = id;
  agentsWithNewAction.delete(id); // 点击后清除感叹号
  // 切换智能体时，默认显示该智能体最新的天数
  const d = agentsData[id];
  if (d) {
    viewDays[id] = Math.floor((d.current_tick || 0) / 12) + 1;
  }
  
  // 聚焦相机到该人物 (考虑左右面板，并自动放大)
  const idleState = agentIdleStates[id];
  const hasLivePos = idleState && idleState.currentX !== undefined;
  if (hasLivePos || (d && d.profile && d.profile.position)) {
    let targetWorldX, targetWorldY;
    if (hasLivePos) {
      targetWorldX = idleState.currentX + mapData.tileWidth / 2;
      targetWorldY = idleState.currentY + mapData.tileHeight / 2;
    } else {
      const [px, py] = d.profile.position;
      targetWorldX = px * mapData.tileWidth + mapData.tileWidth / 2;
      targetWorldY = py * mapData.tileHeight + mapData.tileHeight / 2;
    }

    const canvas = document.getElementById('mapCanvas');
    
    // 自动放大地图到 1.0 (如果当前太小)，这样人物大小比较合适
    if (camera.zoom < 0.8) {
      camera.zoom = 1.0;
    }

    // 获取侧边栏和详情面板的宽度
    const sidebarWidth = document.querySelector('.sidebar')?.offsetWidth || 300;
    const detailPanelWidth = 400; // 详情面板通常是固定宽度，如果未展开则预估
    const totalWidth = window.innerWidth;
    
    // 计算剩余可用空间的中心在屏幕上的偏移
    // 偏向左侧一些：我们将中心偏移设为可用空间的 45% 处，而不是 50%
    const availableWidth = totalWidth - sidebarWidth - detailPanelWidth;
    const centerOffsetInScreen = sidebarWidth + availableWidth * 0.45;
    
    const canvasWidth = canvas.width;
    const canvasHeight = canvas.height;
    
    // 计算相机目标位置
    camera.targetX = targetWorldX - (centerOffsetInScreen - canvasWidth / 2) / camera.zoom;
    camera.targetY = targetWorldY;
    
    // 注意：这里移除了硬赋值 (camera.x = camera.targetX)
    // 而是让 renderLoop 里的动画去平滑插值移动
  }

  renderAgentList();
  renderDetail(id);
  
  // 显示详情框并使滚动条回到顶部
  showAgentDetail();
  const detailPanel = document.getElementById('detailPanel');
  if (detailPanel) {
    detailPanel.scrollTop = 0;
  }
}

function showAgentDetail() {
  const box = document.getElementById('agentDetailBox');
  if (box) box.classList.add('show');
  const goalPanel = document.getElementById('goalPanel');
  if (goalPanel) goalPanel.classList.add('shifted');
}

function closeAgentDetail() {
  const box = document.getElementById('agentDetailBox');
  if (box) box.classList.remove('show');
  const goalPanel = document.getElementById('goalPanel');
  if (goalPanel) goalPanel.classList.remove('shifted');
  selectedAgent = null;
  renderAgentList();
}

function switchDay(event, id, day) {
  if (event) event.stopPropagation();
  viewDays[id] = day;
  renderDetail(id);
}

// ===== TTS 功能 =====
function getSpeakerGender(speaker) {
  const speakerName = String(speaker || '').trim();
  if (!speakerName) return '';

  for (const [id, data] of Object.entries(agentsData || {})) {
    const profile = data && data.profile ? data.profile : {};
    const candidateNames = [
      id,
      formatAgentName(id),
      profile.id,
      profile.name,
      profile['姓名']
    ].filter(Boolean).map(v => String(v).trim());

    if (!candidateNames.includes(speakerName)) continue;

    return String(
      profile['性别'] ??
      profile.gender ??
      profile['gender'] ??
      ''
    ).trim();
  }

  return '';
}

async function playTts(btnElement, speaker, text) {
  const apiKey = localStorage.getItem('dashscope_tts_api_key');
  if (!apiKey) {
    alert('请先在设置中配置 DashScope API Key');
    return;
  }

  // 避免重复点击
  if (btnElement.disabled) return;
  
  const originalText = btnElement.innerText;
  btnElement.innerText = '⏳';
  btnElement.disabled = true;

  try {
    const gender = getSpeakerGender(speaker);

    // 通过本地后端代理请求，后端会按人物先设计/缓存音色，再执行合成
    const response = await fetch('http://localhost:8001/api/tts', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'qwen-voice-design',
        input: {
          text: text,
          speaker: speaker,
          gender: gender
        }
      })
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`TTS 请求失败: ${response.status} ${errText}`);
    }

    const contentType = response.headers.get('content-type') || '';
    let audioUrl;
    let isBlob = false;

    if (contentType.includes('application/json')) {
      const data = await response.json();
      if (data.output && data.output.audio && data.output.audio.url) {
        audioUrl = data.output.audio.url;
      } else {
        throw new Error('未获取到音频 URL');
      }
    } else {
      const audioBlob = await response.blob();
      audioUrl = URL.createObjectURL(audioBlob);
      isBlob = true;
    }
    
    const audio = new Audio(audioUrl);
    audio.onended = () => {
      btnElement.innerText = originalText;
      btnElement.disabled = false;
      if (isBlob) URL.revokeObjectURL(audioUrl);
    };
    audio.onerror = () => {
      alert('音频播放失败');
      btnElement.innerText = originalText;
      btnElement.disabled = false;
      if (isBlob) URL.revokeObjectURL(audioUrl);
    };
    
    await audio.play();
    btnElement.innerText = '🔊'; // 播放中保持小喇叭图标，直到播放完毕
  } catch (error) {
    console.error('TTS Error:', error);
    alert(error.message);
    btnElement.innerText = originalText;
    btnElement.disabled = false;
  }
}

// ===== Modal Handlers =====
function openBubbleModal(bubble) {
  const id = bubble.agentId;
  const d = agentsData[id];
  if (!d) return;

  // 找最新一条 short_term_memory
  const mems = d.short_term_memory;
  const mem = mems && mems.length ? mems[mems.length - 1] : null;
  const tick = mem ? mem.tick : null;

  // 有对话记录则用 openModal，否则只展示总结
  if (tick !== null && d.dialogues && d.dialogues[tick]) {
    openModal(null, id, tick);
    return;
  }

  // 没有对话，只展示总结文字
  const modal = document.getElementById('dialogueModal');
  const content = document.getElementById('dialogueContent');
  const summaryEl = document.getElementById('dialogueSummary');

  summaryEl.textContent = mem ? mem.content : bubble.text;
  summaryEl.style.display = 'block';
  content.innerHTML = '<div class="empty-text" style="padding:16px;opacity:0.5;">暂无对话记录</div>';
  setActiveDialogueContext(id, tick);
  modal.classList.add('open');
}

function getHourlyPlanForTick(hourlyPlans, tick) {
  if (tick === null || tick === undefined) return null;

  const day = Math.floor(Number(tick) / 12) + 1;
  const hour = Number(tick) % 12;

  if (Array.isArray(hourlyPlans)) {
    return hourlyPlans.find(plan => Array.isArray(plan) && Number(plan[1]) === hour) || null;
  }

  if (hourlyPlans && typeof hourlyPlans === 'object') {
    const dayPlans = hourlyPlans[day] || hourlyPlans[String(day)] || [];
    if (Array.isArray(dayPlans)) {
      return dayPlans.find(plan => Array.isArray(plan) && Number(plan[1]) === hour) || null;
    }
  }

  return null;
}

function normalizeLocationName(name) {
  return String(name || '')
    .trim()
    .replace(/[，。、“”‘’《》〈〉（）()【】\[\]\s\-_,.;:：]/g, '');
}

function findMapLocationByName(locationName) {
  const targetLocName = String(locationName || '').trim();
  if (!targetLocName || !mapData || !Array.isArray(mapData.locations)) return null;

  const normalizedTarget = normalizeLocationName(targetLocName);
  let matched = mapData.locations.find(l => normalizeLocationName(l.name) === normalizedTarget);
  if (!matched) {
    matched = mapData.locations.find(l => {
      const normalizedName = normalizeLocationName(l.name);
      return normalizedName.includes(normalizedTarget) || normalizedTarget.includes(normalizedName);
    });
  }

  return matched || null;
}

function getDialogueLocationContext(agentId, tick) {
  const d = agentsData[agentId];
  if (!d) return null;

  let rawLocation = '';
  let sourceKey = '';

  // 仅在当前 tick 有明确实时位置时，才认为拿到了“实际执行地点”
  if (Number(d.current_tick) === Number(tick) && d.current_location) {
    rawLocation = String(d.current_location).trim();
    sourceKey = rawLocation ? 'dialogue_location_source_current' : '';
  }

  const matchedLocation = findMapLocationByName(rawLocation);

  return {
    agentId,
    tick,
    rawLocation,
    displayName: matchedLocation ? matchedLocation.name : rawLocation,
    matchedLocation,
    sourceKey
  };
}

function refreshDialogueSidebar() {
  const nameEl = document.getElementById('dialogueLocationName');
  const metaEl = document.getElementById('dialogueLocationMeta');
  const overlayEl = document.querySelector('.dream-location-overlay');
  if (!nameEl || !metaEl || !overlayEl) return;

  const hasActualLocation = !!(activeDialogueContext && activeDialogueContext.matchedLocation && activeDialogueContext.rawLocation);
  overlayEl.classList.toggle('is-hidden', !hasActualLocation);
  metaEl.classList.toggle('is-hidden', !hasActualLocation);

  if (!activeDialogueContext || !hasActualLocation) {
    nameEl.textContent = t('dialogue_location_pending');
    metaEl.textContent = t('dialogue_location_hint');
    return;
  }

  nameEl.textContent = activeDialogueContext.displayName || t('dialogue_location_unknown');

  const sourceText = activeDialogueContext.sourceKey ? ` ${t(activeDialogueContext.sourceKey)}` : '';
  metaEl.textContent = `${t('dialogue_location_marked')}${sourceText}`;
}

function focusCameraOnLocation(location) {
  if (!location || !mapData) return;

  camera.targetX = location.x + mapData.tileWidth / 2;
  camera.targetY = location.y + mapData.tileHeight / 2;
}

function findAgentIdBySpeakerName(speakerName) {
  const normalizedSpeaker = String(speakerName || '').trim();
  if (!normalizedSpeaker) return null;

  for (const [id, data] of Object.entries(agentsData || {})) {
    const profile = data?.profile || {};
    const candidateNames = [
      id,
      formatAgentName(id),
      profile.id,
      profile.name,
      profile['姓名']
    ].filter(Boolean).map(v => String(v).trim());

    if (candidateNames.includes(normalizedSpeaker)) {
      return id;
    }
  }

  return null;
}

function getSpeakerAvatarSource(speakerName) {
  const agentId = findAgentIdBySpeakerName(speakerName);
  if (agentId) {
    const customAvatar = customAgentAvatars[agentId];
    if (customAvatar && customAvatar.type === 'custom' && customAvatar.source) {
      return customAvatar.source;
    }

    return `../map/sprite/${formatAgentName(agentId)}.png`;
  }

  return `../map/sprite/${speakerName}.png`;
}

function parseDialogueHistoryEntries(history) {
  return (history || []).map(line => {
    const rawLine = String(line || '');
    const match = rawLine.match(/^(.+?)：(?:\[(.+?)\])?(.*)$/);
    if (!match) {
      return {
        raw: rawLine,
        speaker: '',
        action: '',
        text: rawLine.trim(),
        speakerId: null
      };
    }

    const [, speaker, action, text] = match;
    return {
      raw: rawLine,
      speaker: String(speaker || '').trim(),
      action: String(action || '').trim(),
      text: String(text || '').trim(),
      speakerId: findAgentIdBySpeakerName(speaker)
    };
  }).filter(entry => entry.text);
}

function createDialogueReplayScene({ sceneKey, agentId, tick, history, participantIds = [], lastSwitchAt = Date.now(), currentIndex = 0, intervalMs = 2600 }) {
  const entries = parseDialogueHistoryEntries(history);
  if (!entries.length) return null;

  const resolvedParticipantIds = participantIds.length
    ? [...new Set(participantIds.filter(Boolean))]
    : [...new Set(entries.map(entry => entry.speakerId).filter(Boolean))];
  if (!resolvedParticipantIds.length && agentId) {
    resolvedParticipantIds.push(agentId);
  }

  return {
    sceneKey,
    agentId,
    tick,
    entries,
    participantIds: resolvedParticipantIds,
    currentIndex,
    lastSwitchAt,
    intervalMs
  };
}

function getDialogueTickForAgent(agentId) {
  const d = agentsData[agentId];
  if (!d || !d.dialogues) return null;

  if (currentTick !== null && currentTick !== undefined && d.dialogues[currentTick]) {
    return currentTick;
  }

  const mems = d.short_term_memory;
  const mem = mems && mems.length ? mems[mems.length - 1] : null;
  if (mem && mem.tick !== null && d.dialogues[mem.tick]) {
    return mem.tick;
  }

  return null;
}

function syncAutoDialogueReplay() {
  const previousScenes = new Map((activeDialogueReplay?.scenes || []).map(scene => [scene.sceneKey, scene]));
  const scenes = [];
  const seen = new Set();
  const now = Date.now();

  for (const bubble of eventBubbles) {
    if (!bubble.hasDialogue) continue;

    const participantIds = [...new Set((bubble.participants || []).filter(Boolean))];
    const candidates = [bubble.agentId, ...participantIds].filter(Boolean);

    let sourceAgentId = null;
    let dialogueTick = null;
    let history = null;

    for (const candidateId of candidates) {
      const tick = getDialogueTickForAgent(candidateId);
      const candidateHistory = tick !== null ? agentsData[candidateId]?.dialogues?.[tick] : null;
      if (tick !== null && Array.isArray(candidateHistory) && candidateHistory.length) {
        sourceAgentId = candidateId;
        dialogueTick = tick;
        history = candidateHistory;
        break;
      }
    }

    if (!sourceAgentId || dialogueTick === null || !history) continue;

    const sceneKey = `${participantIds.slice().sort().join('|')}|${dialogueTick}`;
    if (seen.has(sceneKey)) continue;
    seen.add(sceneKey);

    const prev = previousScenes.get(sceneKey);
    const scene = createDialogueReplayScene({
      sceneKey,
      agentId: sourceAgentId,
      tick: dialogueTick,
      history,
      participantIds,
      currentIndex: prev ? prev.currentIndex % Math.max(parseDialogueHistoryEntries(history).length, 1) : 0,
      lastSwitchAt: prev ? prev.lastSwitchAt : now + scenes.length * 500,
      intervalMs: prev ? prev.intervalMs : 2600
    });

    if (scene) scenes.push(scene);
  }

  activeDialogueReplay = scenes.length ? { scenes } : null;
}

function setActiveDialogueSpeaker(speakerName) {
  const normalized = String(speakerName || '').trim();
  const lineEls = document.querySelectorAll('#dialogueContent .dialogue-line[data-speaker]');
  const cardEls = document.querySelectorAll('#dialogueParticipants .dialogue-participant[data-speaker]');

  lineEls.forEach(el => {
    const isActive = normalized && el.dataset.speaker === normalized;
    el.classList.toggle('is-speaker-active', !!isActive);
    el.classList.toggle('is-speaker-dimmed', !!normalized && !isActive);
  });

  cardEls.forEach(el => {
    const isActive = normalized && el.dataset.speaker === normalized;
    el.classList.toggle('is-speaker-active', !!isActive);
    el.classList.toggle('is-speaker-dimmed', !!normalized && !isActive);
  });
}

function clearActiveDialogueSpeaker() {
  setActiveDialogueSpeaker('');
}

function bindDialogueHighlightInteractions() {
  document.querySelectorAll('#dialogueContent .dialogue-line[data-speaker]').forEach(el => {
    const speaker = el.dataset.speaker;
    el.addEventListener('mouseenter', () => setActiveDialogueSpeaker(speaker));
    el.addEventListener('mouseleave', () => clearActiveDialogueSpeaker());
  });

  document.querySelectorAll('#dialogueParticipants .dialogue-participant[data-speaker]').forEach(el => {
    const speaker = el.dataset.speaker;
    el.addEventListener('mouseenter', () => setActiveDialogueSpeaker(speaker));
    el.addEventListener('mouseleave', () => clearActiveDialogueSpeaker());
  });
}

function renderDialogueParticipants(history) {
  const cardEl = document.getElementById('dialogueParticipantsCard');
  const listEl = document.getElementById('dialogueParticipants');
  if (!cardEl || !listEl) return;

  const speakers = [];
  const seen = new Set();

  for (const line of history || []) {
    const match = String(line).match(/^(.+?)：(?:\[(.+?)\])?(.*)$/);
    if (!match) continue;
    const speaker = String(match[1] || '').trim();
    if (!speaker || seen.has(speaker)) continue;
    seen.add(speaker);
    speakers.push(speaker);
    if (speakers.length >= 2) break;
  }

  if (!speakers.length) {
    listEl.innerHTML = '';
    cardEl.classList.add('is-hidden');
    return;
  }

  listEl.innerHTML = speakers.map(name => {
    const safeName = escHtml(name);
    const safeSrc = escHtml(getSpeakerAvatarSource(name));
    return `
      <div class="dialogue-participant" data-speaker="${safeName}">
        <div class="dialogue-participant-frame">
          <div class="dialogue-participant-corner corner-tl"></div>
          <div class="dialogue-participant-corner corner-tr"></div>
          <div class="dialogue-participant-corner corner-bl"></div>
          <div class="dialogue-participant-corner corner-br"></div>
          <div class="dialogue-participant-sprite-wrap">
            <div class="dialogue-participant-halo"></div>
            <div class="dialogue-participant-floor"></div>
            <div class="dialogue-participant-badge">绘</div>
          <img
            class="dialogue-participant-sprite"
            src="${safeSrc}"
            alt="${safeName}"
            onerror="this.src='../map/sprite/普通人.png'"
          />
          </div>
          <div class="dialogue-participant-nameplate">
            <div class="dialogue-participant-name">${safeName}</div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  cardEl.classList.remove('is-hidden');
}

function setActiveDialogueContext(agentId, tick) {
  activeDialogueContext = getDialogueLocationContext(agentId, tick);
  refreshDialogueSidebar();

  if (activeDialogueContext && activeDialogueContext.matchedLocation) {
    focusCameraOnLocation(activeDialogueContext.matchedLocation);
  }

  renderDialogueMiniMap(Date.now());
}

function openModal(event, agentId, tick) {
  if (event) event.stopPropagation();

  const d = agentsData[agentId];
  if (!d || !d.dialogues || !d.dialogues[tick]) return;

  const history = d.dialogues[tick];
  const modal = document.getElementById('dialogueModal');
  const content = document.getElementById('dialogueContent');
  const summaryEl = document.getElementById('dialogueSummary');

  // 填充经历总结
  const mem = d.short_term_memory ? d.short_term_memory.find(m => m.tick === tick) : null;
  if (mem && mem.content) {
    summaryEl.textContent = mem.content;
    summaryEl.style.display = 'block';
  } else {
    summaryEl.style.display = 'none';
  }

  content.innerHTML = history.map((line, index) => {
    const match = line.match(/^(.+?)：(?:\[(.+?)\])?(.*)$/);
    if (!match) return `<div class="dialogue-line">${escHtml(line)}</div>`;

    const [_, speaker, action, text] = match;
    const ttsApiKey = localStorage.getItem('dashscope_tts_api_key');
    const safeSpeaker = encodeURIComponent(speaker).replace(/'/g, "%27");
    const safeText = encodeURIComponent(text).replace(/'/g, "%27");
    const speakerBtn = ttsApiKey ? `<button class="tts-speaker-btn" onclick="playTts(this, decodeURIComponent('${safeSpeaker}'), decodeURIComponent('${safeText}'))">🔊</button>` : '';

    return `
      <div class="dialogue-line" data-speaker="${escHtml(speaker)}">
        <span class="dialogue-speaker">${escHtml(speaker)}</span>
        ${action ? `<span class="dialogue-action">[${escHtml(action)}]</span>` : ''}
        <span class="dialogue-text">${escHtml(text)}</span>
        ${speakerBtn}
      </div>
    `;
  }).join('');

  renderDialogueParticipants(history);
  bindDialogueHighlightInteractions();
  setActiveDialogueContext(agentId, tick);
  modal.classList.add('open');
}

function closeModal() {
  activeDialogueContext = null;
  clearActiveDialogueSpeaker();
  refreshDialogueSidebar();
  renderDialogueParticipants([]);
  renderDialogueMiniMap(Date.now());
  document.getElementById('dialogueModal').classList.remove('open');
}

// ===== 添加人物功能 =====
function openAddAgentModal() {
  document.getElementById('addAgentModal').style.display = 'block';
  renderPresetButtons();
  resetAvatarSelection();
}

function resetAvatarSelection() {
  currentAvatar = {
    type: 'builtin',
    source: '../map/sprite/普通人.png',
    name: '普通人'
  };
  document.getElementById('avatarType').value = 'builtin';
  document.getElementById('avatarSource').value = '../map/sprite/普通人.png';
  document.getElementById('selectedAvatarImg').src = '../map/sprite/普通人.png';
  document.getElementById('customAvatarInput').value = '';
  document.querySelectorAll('.avatar-option-btn').forEach(btn => btn.classList.remove('selected'));
}

function closeAddAgentModal() {
  document.getElementById('addAgentModal').style.display = 'none';
  // 清空表单
  document.getElementById('agentId').value = '';
  document.getElementById('templateName').value = '';
  document.getElementById('profileFamily').value = '';
  document.getElementById('profilePersonality').value = '';
  document.getElementById('profileDrive').value = '';
  document.getElementById('profileStyle').value = '';
  document.getElementById('profileBackground').value = '';
  document.getElementById('agentMemory').value = '';
  document.querySelectorAll('.preset-btn').forEach(btn => btn.classList.remove('selected'));
  resetAvatarSelection();
}

// 管理预设弹窗
function openManagePresetModal() {
  document.getElementById('managePresetModal').style.display = 'block';
  renderManagePresetList();
}

function closeManagePresetModal() {
  document.getElementById('managePresetModal').style.display = 'none';
}

function renderManagePresetList() {
  const list = document.getElementById('managePresetList');
  if (!list) return;

  const presets = getAllPresets();
  list.innerHTML = '';

  if (Object.keys(presets).length === 0) {
    list.innerHTML = '<div class="empty-text">暂无预设</div>';
    return;
  }

  Object.entries(presets).forEach(([key, preset]) => {
    const item = document.createElement('div');
    item.className = 'preset-manage-item';

    item.innerHTML = `
      <img src="${preset.avatarSource || '../map/sprite/普通人.png'}" alt="${preset.name}" class="preset-manage-avatar" onerror="this.src='../map/sprite/普通人.png'" />
      <div class="preset-manage-info">
        <span class="preset-manage-name">${preset.name}</span>
        <span class="preset-manage-tag">${preset.isOfficial ? t('official') : t('custom')}</span>
      </div>
      <div class="preset-manage-actions">
        ${!preset.isOfficial ? `<button class="btn-delete-preset" onclick="deletePreset('${key}'); renderManagePresetList();">删除</button>` : ''}
      </div>
    `;

    list.appendChild(item);
  });
}

async function submitAddAgent() {
  const agentId = document.getElementById('agentId').value.trim();
  if (!agentId) {
    alert('请输入人物名称');
    return;
  }

  const templateName = document.getElementById('templateName').value.trim();

  // 构建 profile
  const profile = {};
  const family = document.getElementById('profileFamily').value.trim();
  const personality = document.getElementById('profilePersonality').value.trim();
  const drive = document.getElementById('profileDrive').value.trim();
  const style = document.getElementById('profileStyle').value.trim();
  const background = document.getElementById('profileBackground').value.trim();

  if (family) profile['家族'] = family;
  if (personality) profile['性格'] = personality;
  if (drive) profile['核心驱动'] = drive;
  if (style) profile['语言风格'] = style;
  if (background) profile['背景经历'] = background;

  // 构建初始记忆
  const memoryText = document.getElementById('agentMemory').value.trim();
  const memory = memoryText ? memoryText.split('\n').filter(line => line.trim()) : [];

  // 发送 WebSocket 消息
  if (ws && ws.readyState === WebSocket.OPEN) {
    const message = {
      type: 'add_agent',
      agent_id: agentId,
      template_name: templateName,
      profile: profile,
      memory: memory,
      avatar: {
        type: currentAvatar.type,
        source: currentAvatar.source,
        name: currentAvatar.name
      }
    };
    ws.send(JSON.stringify(message));
    console.log('Sent add_agent request:', message);

    // 缓存头像信息，用于后续渲染
    customAgentAvatars[agentId] = {
      type: currentAvatar.type,
      source: currentAvatar.source
    };
    // 保存到 localStorage
    saveCustomAvatars();

    // 预加载自定义头像
    if (currentAvatar.type === 'custom') {
      const img = new Image();
      img.src = currentAvatar.source;
      agentSprites[agentId] = img;
    }

    // 等待响应
    // 响应会在 onmessage 中处理
  } else {
    alert('WebSocket 未连接，无法添加人物');
  }
}

// 存储自定义头像映射
let customAgentAvatars = {};

// 从 localStorage 加载自定义头像映射
function loadCustomAvatars() {
  try {
    const saved = localStorage.getItem('customAgentAvatars');
    if (saved) {
      customAgentAvatars = JSON.parse(saved);
      // 预加载所有自定义头像
      Object.entries(customAgentAvatars).forEach(([agentId, avatar]) => {
        if (avatar.type === 'custom' && avatar.source) {
          const img = new Image();
          img.src = avatar.source;
          agentSprites[agentId] = img;
        }
      });
    }
  } catch (e) {
    console.error('Failed to load custom avatars:', e);
  }
}

// 保存自定义头像映射到 localStorage
function saveCustomAvatars() {
  try {
    localStorage.setItem('customAgentAvatars', JSON.stringify(customAgentAvatars));
  } catch (e) {
    console.error('Failed to save custom avatars:', e);
  }
}

// 处理 add_agent 响应
function handleAddAgentResponse(msg) {
  if (msg.success) {
    alert(`人物 "${msg.agent_id}" 添加成功！`);
    closeAddAgentModal();
  } else {
    alert(`添加失败: ${msg.error || '未知错误'}`);
  }
}

window.onclick = function(event) {
  const addAgentModal = document.getElementById('addAgentModal');
  const managePresetModal = document.getElementById('managePresetModal');
  if (event.target === addAgentModal) closeAddAgentModal();
  if (event.target === managePresetModal) closeManagePresetModal();
};

// ===== Detail Panel =====
function renderDetail(id) {
  const d = agentsData[id];
  if (!d) return;
  const panel = document.getElementById('detailPanel');
  const name = formatAgentName(id);

  // 检查是否有自定义头像
  const customAvatar = customAgentAvatars[id];
  let avatarSrc = `../map/sprite/${name}.png`;
  if (customAvatar && customAvatar.type === 'custom') {
    avatarSrc = customAvatar.source;
  }

  panel.innerHTML = `
    <div class="detail-header">
      <div class="detail-avatar-container" id="detailAvatarContainer">
        <img src="${avatarSrc}" class="detail-avatar" onerror="document.getElementById('detailAvatarContainer').style.display='none'">
      </div>
      <div class="detail-name-row">
        <span class="detail-ornament">✦</span>
        <span class="detail-name">${name}</span>
        <span class="detail-ornament">✦</span>
      </div>
    </div>
    ${renderProfile(d.profile)}
    <div class="section-divider"><span>✧</span></div>
    ${renderLongTask(d.long_task)}
    <div class="section-divider"><span>✧</span></div>
    ${renderCurrentPlan(d.current_plan, d.current_action, d.occupied_by, d.dialogues, id, d.current_plan_note, d.current_tick)}
    <div class="section-divider"><span>✧</span></div>
    ${renderMemory('短期记忆', d.short_term_memory, 'short')}
    <div class="section-divider"><span>✧</span></div>
    ${renderExperiences(d.dialogues, d.short_term_memory, id)}
    <div class="section-divider"><span>✧</span></div>
    ${renderHourlyPlans(d.hourly_plans, d.dialogues, id, d.occupied_by, d.current_plan_note, d.current_tick, d.replan_log, d.long_task_adj_log)}
    <div class="section-divider"><span>✧</span></div>
    ${renderMemory('长期记忆', d.long_term_memory, 'long')}
  `;
}

// ===== Section Renderers =====
function renderSetPlan(id) {
  return `<section class="info-section">
    <div class="section-title"><span class="section-icon">命</span>指派行动 (下一时辰)</div>
    <div class="set-plan-box">
      <div class="form-group" style="margin-bottom:8px">
        <input type="text" id="customPlanAction_${id}" placeholder="计划内容 (如: 游园)" style="width:100%; padding:6px; font-family: inherit; background: rgba(255,255,255,0.85); border: 1px solid rgba(207,168,94,0.4); color: #1a1410; border-radius: 4px; box-sizing: border-box;" />
      </div>
      <div class="form-group" style="margin-bottom:8px; display:flex; gap:8px;">
        <input type="text" id="customPlanLocation_${id}" placeholder="地点 (如: 大观园)" style="flex:1; padding:6px; font-family: inherit; background: rgba(255,255,255,0.85); border: 1px solid rgba(207,168,94,0.4); color: #1a1410; border-radius: 4px; box-sizing: border-box;" />
        <input type="text" id="customPlanTarget_${id}" placeholder="目标人物 (选填)" style="flex:1; padding:6px; font-family: inherit; background: rgba(255,255,255,0.85); border: 1px solid rgba(207,168,94,0.4); color: #1a1410; border-radius: 4px; box-sizing: border-box;" />
      </div>
      <button class="control-btn" style="width:100%; padding:6px; font-size:14px; margin-top: 4px;" onclick="sendCustomPlan('${id}')">下达最高优先级计划</button>
    </div>
  </section>`;
}

function sendCustomPlan(id) {
  const action = document.getElementById(`customPlanAction_${id}`).value.trim();
  const location = document.getElementById(`customPlanLocation_${id}`).value.trim();
  const target = document.getElementById(`customPlanTarget_${id}`).value.trim() || "无";
  
  if (!action || !location) {
    alert("请至少填写计划内容和地点");
    return;
  }
  
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "set_plan",
      agent_id: id,
      action: action,
      location: location,
      target: target
    }));
    alert("计划已下达！将在下一回合执行且不可被抢占。");
    // 清空输入框
    document.getElementById(`customPlanAction_${id}`).value = '';
    document.getElementById(`customPlanLocation_${id}`).value = '';
    document.getElementById(`customPlanTarget_${id}`).value = '';
  } else {
    alert("连接已断开，无法下达计划。");
  }
}

function renderProfile(profile) {
  if (!profile) return '';
  const fields = [
    { label: t('family_label'), key: '家族' },
    { label: t('personality_label'), key: '性格' },
    { label: t('drive_label'), key: '核心驱动' },
    { label: t('style_label'), key: '语言风格' }
  ];
  
  const items = fields.map(f => {
    const val = profile[f.key] || t('unknown');
    return `<div class="profile-item">
      <span class="profile-label">${f.label}：</span>
      <span class="profile-value">${escHtml(val)}</span>
    </div>`;
  }).join('');

  return `<section class="info-section">
    <div class="section-title"><span class="section-icon">志</span>人物志</div>
    <div class="profile-grid">${items}</div>
    ${profile['背景经历'] ? `<div class="profile-bio"><strong>${t('profile_background')}</strong>${escHtml(profile['背景经历'])}</div>` : ''}
  </section>`;
}

function renderExperiences(dialogues, shortTermMemory, agentId) {
  if (!dialogues || Object.keys(dialogues).length === 0) {
    return `<section class="info-section">
      <div class="section-title">人物经历</div>
      <div class="empty-text">尚无重要经历</div>
    </section>`;
  }
  
  // 获取所有有对话的 tick，并倒序排列
  const ticks = Object.keys(dialogues).map(Number).sort((a, b) => b - a);
  
  const items = ticks.map(tick => {
    // 从短期记忆中寻找该 tick 对应的总结
    const mem = shortTermMemory ? shortTermMemory.find(m => m.tick === tick) : null;
    const summary = mem ? mem.content : '一段往事记录...';
    
    return `
      <div class="experience-card clickable-plan" onclick="openModal(event, '${agentId.replace(/'/g, "\\'")}', ${tick})">
        <div class="experience-header">
          <span class="experience-tick">${t('time_tick')} ${tick}</span>
          <span class="experience-tag">对话录</span>
        </div>
        <div class="experience-summary">${escHtml(truncate(summary, 80))}</div>
        <div class="experience-footer">
          <span class="experience-hint">点击阅览全篇 ❧</span>
        </div>
      </div>
    `;
  }).join('');

  return `<section class="info-section">
    <div class="section-title">人物经历</div>
    <div class="experience-list">${items}</div>
  </section>`;
}
function renderLongTask(task) {
  return `<section class="info-section">
    <div class="section-title"><span class="section-icon">志</span>长期志向</div>
    <div class="long-task-box">${task ? escHtml(task) : '<span class="empty-text">尚无志向</span>'}</div>
  </section>`;
}

function renderCurrentPlan(plan, actionDetail, occupiedBy, dialogues, agentId, planNote, tick) {
  let content = '';
  const hasDialogue = dialogues && dialogues[tick];
  const clickableClass = hasDialogue ? ' clickable-plan' : '';
  const dialogueHint = hasDialogue ? '<span class="dialogue-hint">点击查看对话详录 ❧</span>' : '';
  
  const noteHtml = planNote ? `<div class="plan-note-fail">⚠️ ${escHtml(planNote)}</div>` : '';

  if (!plan && !actionDetail && !occupiedBy) {
    content = '<span class="empty-text">暂无行动</span>';
  } else if (occupiedBy) {
    // 处理被占用的情况
    const originalAction = Array.isArray(plan) ? plan[0] : (plan || '原计划');
    const occupierName = formatAgentName(occupiedBy.occupier);
    const newAction = occupiedBy.action || '协助他人';
    
    content = `
      <div class="current-plan-detail occupied${clickableClass}" onclick="openModal(event, '${agentId.replace(/'/g, "\\'")}', ${tick})">
        <div class="plan-conflict-badge">计划变更</div>
        <div class="original-plan-crossed">${escHtml(originalAction)}</div>
        <div class="arrow-down">↓</div>
        <div class="new-plan-box">
          <div class="new-plan-main">${escHtml(newAction)}</div>
          <div class="new-plan-meta">因 <strong>${escHtml(occupierName)}</strong> 的更重要事务而调整</div>
          ${dialogueHint}
        </div>
      </div>
    `;
  } else if (Array.isArray(plan)) {
    const [action, time, target, location, importance] = plan;
    const targetStr = target && target !== '无' && target !== '自己' ? ` 与 <strong>${escHtml(target)}</strong>` : '';
    content = `
      <div class="current-plan-detail${clickableClass}" onclick="openModal(event, '${agentId.replace(/'/g, "\\'")}', ${tick})">
        <div class="current-plan-main">${escHtml(actionDetail || action)}</div>
        <div class="current-plan-meta">
          <span>地点：${escHtml(location)}</span>
          ${targetStr ? `<span>人员：${targetStr}</span>` : ''}
          <span class="importance-tag imp-${importance <= 3 ? 'low' : importance <= 6 ? 'mid' : importance <= 8 ? 'high' : 'crit'}">重要性：${importance}</span>
        </div>
        ${noteHtml}
        ${dialogueHint}
      </div>
    `;
  } else if (actionDetail || typeof plan === 'string') {
    content = `<div class="${clickableClass}" onclick="openModal(event, '${agentId.replace(/'/g, "\\'")}', ${tick})">
      ${escHtml(actionDetail || plan)}
      ${noteHtml}
      ${dialogueHint}
    </div>`;
  } else {
    content = `<pre>${escHtml(JSON.stringify(plan, null, 2))}</pre>`;
  }
  return `<section class="info-section">
    <div class="section-title"><span class="section-icon">行</span>当前行动</div>
    <div class="current-plan-box">${content}</div>
  </section>`;
}

function renderHourlyPlans(plans, dialogues, agentId, currentOccupiedBy, currentPlanNote, tick, replanLog, longTaskAdjLog) {
  const currentDay = Math.floor((tick || 0) / 12) + 1;
  const viewingDay = viewDays[agentId] || currentDay;
  const currentHour = (tick || 0) % 12;

  // Build a lookup: day -> list of replan events, for quick access in rendering
  const replanByDay = {};
  if (Array.isArray(replanLog)) {
    for (const ev of replanLog) {
      const d = ev.day;
      if (!replanByDay[d]) replanByDay[d] = [];
      replanByDay[d].push(ev);
    }
  }

  // 获取特定天的计划
  let dayPlans = [];
  let availableDays = [];

  if (Array.isArray(plans)) {
    // 兼容旧格式
    dayPlans = plans;
    availableDays = [1];
  } else if (typeof plans === 'object' && plans !== null) {
    // 新格式：{ "1": [...], "2": [...] }
    availableDays = Object.keys(plans).map(Number).sort((a, b) => a - b);
    dayPlans = plans[viewingDay] || [];
  }

  // 渲染日期选择器
  let daySelector = '';
  if (availableDays.length > 1) {
    const dayButtons = availableDays.map(d => {
      const active = d === viewingDay ? ' active' : '';
      const isCurrent = d === currentDay ? ' (今日)' : '';
      return `<button class="day-btn${active}" onclick="switchDay(event, '${agentId.replace(/'/g, "\\'")}', ${d})">第${d}天${isCurrent}</button>`;
    }).join('');
    daySelector = `<div class="day-selector">${dayButtons}</div>`;
  }

  // Build replan notice banner for the day being viewed (mid-day replans)
  const dayReplanEvents = replanByDay[viewingDay] || [];
  let replanBanner = '';
  if (dayReplanEvents.length > 0) {
    const notices = dayReplanEvents.map(ev =>
      `<div class="replan-notice-item">⚡ 第${ev.from_hour}时辰起重新规划：${escHtml(ev.reason)}</div>`
    ).join('');
    replanBanner = `<div class="replan-banner">${notices}</div>`;
  }

  // Build long-task adjustment banner: show when viewing a day affected by a prior LongTask change
  let longTaskAdjBanner = '';
  if (Array.isArray(longTaskAdjLog)) {
    // Find all adjustment events that affect this day (from_day <= viewingDay)
    const affectingAdjs = longTaskAdjLog.filter(ev => ev.from_day <= viewingDay);
    if (affectingAdjs.length > 0) {
      // Use the latest adjustment that affects this day
      const ev = affectingAdjs[affectingAdjs.length - 1];
      const adjDay = Math.floor(ev.tick / 12) + 1;
      const adjHour = ev.tick % 12;
      longTaskAdjBanner = `<div class="replan-banner longtask-adj-banner">
        <div class="replan-notice-item">🔄 自第${ev.from_day}天起重新制定计划（因长期目标于第${adjDay}天第${adjHour}时辰调整）</div>
      </div>`;
    }
  }

  if (!dayPlans || !dayPlans.length) {
    return `<section class="info-section">
      <div class="section-title">一日计划</div>
      ${daySelector}
      ${longTaskAdjBanner}
      ${replanBanner}
      <div class="empty-text" style="padding:12px 0">第 ${viewingDay} 天暂无计划</div>
    </section>`;
  }

  // Build set of hours that were replanned (for badge display)
  const replanedHours = new Set();
  for (const ev of dayReplanEvents) {
    for (let h = ev.from_hour; h < 12; h++) replanedHours.add(h);
  }

  const items = dayPlans.map(p => {
    const [action, time, target, location, importance] = p;
    const shi = SHICHEN[time] || '?';
    const imp = parseInt(importance) || 1;
    const impClass = imp <= 3 ? 'imp-low' : imp <= 6 ? 'imp-mid' : imp <= 8 ? 'imp-high' : 'imp-crit';
    const targetStr = target && target !== '无' && target !== '自己' ? `→ ${escHtml(target)}` : '';

    // Badge shown on replanned hours
    const replanBadge = replanedHours.has(time) ? '<span class="replan-badge">重规划</span>' : '';

    // 检查该时辰是否被占用
    const isCurrentlyOccupied = (viewingDay === currentDay && time === currentHour) && currentOccupiedBy;
    // 检查该时辰是否有注释
    const hasNote = (viewingDay === currentDay && time === currentHour) && currentPlanNote;
    
    // 寻找该时辰是否有对话历史
    let dialogueTick = -1;
    if (dialogues) {
      const ticks = Object.keys(dialogues).map(Number).sort((a, b) => b - a);
      // 这里的 tick 计算需要考虑天数
      dialogueTick = ticks.find(t => {
        const d = Math.floor(t / 12) + 1;
        const h = t % 12;
        return d === viewingDay && h === time;
      }) || -1;
    }

    const hasDialogue = dialogueTick !== -1;
    const clickableClass = hasDialogue ? ' clickable-plan' : '';
    const clickHandler = hasDialogue ? `onclick="openModal(event, '${agentId.replace(/'/g, "\\'")}', ${dialogueTick})"` : '';
    const dialogueHint = hasDialogue ? '<div class="dialogue-hint">点击回看对话 ❧</div>' : '';

    let contentHtml = '';
    if (isCurrentlyOccupied) {
      const occupierName = formatAgentName(currentOccupiedBy.occupier);
      const newAction = currentOccupiedBy.action || '协助他人';
      contentHtml = `
        <div class="hourly-action original-plan-crossed">${escHtml(action)}</div>
        <div class="hourly-conflict-desc">
          <span class="conflict-arrow">↓</span> 
          <strong>${escHtml(newAction)}</strong>
          <div class="conflict-meta">因 ${escHtml(occupierName)} 的事务调整</div>
        </div>
      `;
    } else {
      contentHtml = `
        <div class="hourly-action">${escHtml(action)}</div>
        <div class="hourly-meta">${escHtml(location)}${targetStr ? ' <span class="hourly-target">' + targetStr + '</span>' : ''}</div>
        ${hasNote ? `<div class="plan-note-fail small">⚠️ ${escHtml(currentPlanNote)}</div>` : ''}
      `;
    }

    const isNow = (viewingDay === currentDay && time === currentHour);

    return `<div class="hourly-item${clickableClass}${isNow ? ' current-hour' : ''}" ${clickHandler}>
      <div class="hourly-time"><span class="shichen">${shi}时</span>${replanBadge}</div>
      <div class="hourly-line"><div class="hourly-dot ${impClass}"></div></div>
      <div class="hourly-content">
        ${contentHtml}
        ${dialogueHint}
      </div>
    </div>`;
  }).join('');

  return `<section class="info-section">
    <div class="section-title">一日计划</div>
    ${daySelector}
    ${longTaskAdjBanner}
    ${replanBanner}
    <div class="hourly-list">${items}</div>
  </section>`;
}

function renderMemory(title, memories, type) {
  const icon = type === 'short' ? '念' : '忆';
  if (!memories || !memories.length) {
    return `<section class="info-section">
      <div class="section-title"><span class="section-icon">${icon}</span>${title}</div>
      <div class="empty-text" style="padding:12px 0">暂无记忆</div>
    </section>`;
  }
  // newest first
  const sorted = [...memories].sort((a, b) => (b.tick ?? 0) - (a.tick ?? 0));
  const items = sorted.map(m => `
    <div class="memory-card ${type}-memory">
      <span class="memory-tick">${t('time_tick')} ${m.tick ?? '?'}</span>
      <div class="memory-content">${escHtml(m.content ?? '')}</div>
    </div>`).join('');
  return `<section class="info-section">
    <div class="section-title"><span class="section-icon">${icon}</span>${title}</div>
    <div class="memory-list">${items}</div>
  </section>`;
}

// ===== Utilities =====
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function truncate(s, n) {
  return s.length > n ? s.slice(0, n) + '…' : s;
}

// 加载初始人物配置
async function loadInitialProfiles() {
  try {
    // Load full character profiles from characters.json (includes 性格, 核心驱动, sprite, etc.)
    const response = await fetch('/data/characters.json');
    if (!response.ok) throw new Error('characters.json not found');
    const characters = await response.json();
    const initialData = {};

    characters.forEach(char => {
      const id = char.id;
      if (!id) return;
      // Skip 孙悟空 unless the player selected them — backend excludes them from the simulation
      // when not selected, so preloading would show a ghost character until first tick_update.
      if (id === '孙悟空' && (!playerCharacter || playerCharacter.id !== id)) return;
      initialData[id] = {
        profile: {
          ...char,
          position: [0, 0] // 初始占位，会被 initializeAgentPositions 修正
        },
        current_tick: 0,
        is_active: true
      };

      // 初始化闲逛状态
      if (!agentIdleStates[id]) {
        agentIdleStates[id] = {
          currentX: 0,
          currentY: 0,
          targetX: 0,
          targetY: 0,
          lastUpdate: Date.now(),
          nextMoveTime: Date.now() + Math.random() * 2000
        };
      }
    });

    mergeData(initialData);
    renderAgentList();
    console.log('Initial profiles loaded from characters.json:', Object.keys(initialData).length);
  } catch (err) {
    console.error('Failed to load initial profiles:', err);
  }
}

// ===== 新开场加载与动画逻辑 =====
const introOverlay = document.getElementById('newIntroOverlay');

// 挑选用于加载动画的角色（排除小厮和市民）
const coreAgents = [
  '贾宝玉', '林黛玉', '薛宝钗', '史湘云', '王熙凤', 
  '贾母', '王夫人', '贾探春', '妙玉', '晴雯', '袭人',
  '贾政', '贾迎春', '贾惜春', '李纨', '贾琏', '薛蟠'
];

function initLoadingRing() {
  const ring = document.getElementById('loadingRing');
  if (!ring) return;
  
  // 随机挑选12个角色
  const shuffled = [...coreAgents].sort(() => 0.5 - Math.random());
  const selected = shuffled.slice(0, 12);
  
  const radius = 220; // 圈的半径（根据12个小人的140px宽度调整，使他们手拉手没有太大空隙）
  selected.forEach((name, index) => {
    const angle = (index / selected.length) * Math.PI * 2;
    const x = Math.cos(angle) * radius;
    const y = Math.sin(angle) * radius;
    
    const img = document.createElement('img');
    img.src = `../map/sprite/${name}.png`;
    img.className = 'ring-avatar';
    // 设置位置，并通过旋转使人物脚部指向圆心
    // angle是弧度，+ Math.PI / 2 (-90度，因为图片默认是头朝上，也就是朝向-y轴。要让脚朝向圆心，即头朝外，需要旋转使得头的方向与向外的法线方向一致)
    // 向外的法线方向就是 angle。图片默认头指向上方（-y方向，即角度为 -90 度 或 270 度）。
    // 所以需要旋转的角度 = angle - (-Math.PI/2) = angle + Math.PI/2
    const rotationDeg = (angle + Math.PI / 2) * (180 / Math.PI);
    img.style.left = `calc(50% + ${x}px)`;
    img.style.top = `calc(50% + ${y}px)`;
    img.style.transform = `rotate(${rotationDeg}deg)`;
    
    // 错误处理：如果图片加载失败，使用兜底SVG
    img.onerror = () => {
      img.onerror = null;
      img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"%3E%3Cpath fill="%23888" d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/%3E%3C/svg%3E';
    };
    
    ring.appendChild(img);
  });
}

// 模拟加载进度
function startLoadingProgress() {
  const fill = document.getElementById('introProgressFill');
  if (!fill) return;
  
  let progress = 0;
  const interval = setInterval(() => {
    // 随机增加进度
    progress += Math.random() * 15;
    if (progress >= 100) {
      progress = 100;
      clearInterval(interval);
      fill.style.height = '100%';
      
      // 加载完成，触发后续动画
      setTimeout(finishLoadingAnimation, 500);
    } else {
      fill.style.height = `${progress}%`;
    }
  }, 200);
}

function finishLoadingAnimation() {
  const ring = document.getElementById('loadingRing');
  const slidePanel = document.getElementById('introSlidePanel');
  
  if (ring) ring.classList.add('fade-out');
  
  // 延迟让角色圈淡出后，开始滑屏
  setTimeout(() => {
    if (slidePanel) slidePanel.classList.add('open');
    
    // 标题展示一段时间后，整个遮罩淡出进入主界面
    setTimeout(() => {
      if (introOverlay) {
        introOverlay.classList.add('hidden');
        setTimeout(() => {
          introOverlay.remove();
        }, 1500);
      }
    }, 4500); // 1.5s滑屏 + 3s展示
    
  }, 800);
}

// ===== Init =====
async function startApp() {
  // 加载自定义头像
  loadCustomAvatars();

  // 开始播放新加载动画
  if (introOverlay) {
    initLoadingRing();
    startLoadingProgress();
  }

  await initMap();
  await loadInitialProfiles();
  // 再次确保位置初始化（在地图和数据都加载完后）
  if (mapData) initializeAgentPositions();
  connect();
}

startApp();

// ===== Map Rendering (Basic TMX Parser & Canvas) =====
let mapData = null;
let tilesets = [];
let layerCanvases = []; // 存储预渲染的图层离线画布
let camera = { x: 0, y: 0, zoom: 1, minZoom: 0.1 };
let isDragging = false;
let lastMousePos = { x: 0, y: 0 };

async function initMap() {
  const canvas = document.getElementById('mapCanvas');
  const container = document.getElementById('mapContainer');
  if (!canvas || !container) return;

  // 响应式画布
  window.addEventListener('resize', () => {
    resizeCanvas();
    if (mapData) fitMapToContainer();
  });
  resizeCanvas();

  try {
    const tmxPath = '../map/sos.tmx'; // 假设 TMX 路径
    const response = await fetch(tmxPath);
    const tmxText = await response.text();
    const parser = new DOMParser();
    const xmlDoc = parser.parseFromString(tmxText, "text/xml");
    
    const mapNode = xmlDoc.getElementsByTagName('map')[0];
    mapData = {
      width: parseInt(mapNode.getAttribute('width')),
      height: parseInt(mapNode.getAttribute('height')),
      tileWidth: parseInt(mapNode.getAttribute('tilewidth')),
      tileHeight: parseInt(mapNode.getAttribute('tileheight')),
      layers: []
    };
    mapData.pixelWidth = mapData.width * mapData.tileWidth;
    mapData.pixelHeight = mapData.height * mapData.tileHeight;

    // 解析瓦片集
    const tilesetNodes = xmlDoc.getElementsByTagName('tileset');
    for (let ts of tilesetNodes) {
      const firstgid = parseInt(ts.getAttribute('firstgid'));
      const source = ts.getAttribute('source');
      // 解析 TSX
      const tsxPath = `../map/${source}`;
      const tsxResponse = await fetch(tsxPath);
      const tsxText = await tsxResponse.text();
      const tsxDoc = parser.parseFromString(tsxText, "text/xml");
      const tsxNode = tsxDoc.getElementsByTagName('tileset')[0];
      const imageNode = tsxDoc.getElementsByTagName('image')[0];
      
      // 获取 TSX 所在目录，用于解析图片的相对路径
      const tsxDir = tsxPath.substring(0, tsxPath.lastIndexOf('/') + 1);
      let rawImageSource = imageNode.getAttribute('source');
      
      // 核心修复：处理 TSX 文件中可能存在的错误外部路径
      if (rawImageSource.includes('Hospital/source/')) {
        rawImageSource = 'Tiles/' + rawImageSource.split('Hospital/source/')[1];
      } else if (rawImageSource.includes('../Tiles/')) {
        // 已经是正确的相对路径，但为了保险我们统一处理
        rawImageSource = rawImageSource.substring(rawImageSource.indexOf('Tiles/'));
      }
      
      // 统一映射到 /map/Tiles 目录下
      const imageSource = `../map/${rawImageSource}`;

      const tileset = {
        firstgid,
        name: tsxNode.getAttribute('name'),
        tileWidth: parseInt(tsxNode.getAttribute('tilewidth')),
        tileHeight: parseInt(tsxNode.getAttribute('tileheight')),
        columns: parseInt(tsxNode.getAttribute('columns')),
        imageSource: imageSource,
        width: parseInt(imageNode.getAttribute('width')),
        height: parseInt(imageNode.getAttribute('height'))
      };
      
      // 加载图片
      tileset.image = await loadImage(tileset.imageSource);
      tilesets.push(tileset);
    }

    // 解析图层和地点
    mapData.layers = [];
    mapData.locations = [];
    mapData.passableGids = null; // 存储可通行区域的数据

    // 辅助函数：递归解析图层和组
    function parseLayers(node, isLocationGroup = false) {
      const children = Array.from(node.children || []);
      for (let child of children) {
        const name = child.getAttribute('name');
        
        // 解析可通行区域
        if ((name === '可通行' || name === '可通行区域') && child.nodeName === 'layer') {
          const dataNode = child.getElementsByTagName('data')[0];
          if (dataNode) {
            const csv = dataNode.textContent.trim();
            mapData.passableGids = csv.split(',').map(s => parseInt(s.trim()));
          }
          continue;
        }

        // 显式忽略特定图层 (可通行区域不渲染)，但不跳过group，需要递归解析其内部的layer
        if ((name === '可通行' || name === '可通行区域') && child.nodeName === 'layer') continue;

        if (child.nodeName === 'layer') {
          const visible = child.getAttribute('visible') !== '0';
          const dataNode = child.getElementsByTagName('data')[0];
          if (!dataNode) continue;
          
          const csv = dataNode.textContent.trim();
          const gids = csv.split(',').map(s => parseInt(s.trim()));

          // 如果是在“地点”组内，或者是“仆役群房”，解析为地点标记
          if (isLocationGroup || name === '仆役群房') {
            let sumX = 0, sumY = 0, count = 0;
            const validTiles = [];
            for (let i = 0; i < gids.length; i++) {
              if (gids[i] !== 0) {
                const tx = i % mapData.width;
                const ty = Math.floor(i / mapData.width);
                sumX += tx;
                sumY += ty;
                count++;
                validTiles.push(i);
              }
            }
            if (count > 0) {
              // 检查是否已经存在同名地点（如多个仆役群房图层）
              const existingLoc = mapData.locations.find(l => l.name === name);
              if (existingLoc) {
                // 合并瓦片数据
                existingLoc.tiles = existingLoc.tiles.concat(validTiles);
                // 重新计算中心点（作为文字标签显示位置，仆役群房不显示所以无所谓）
                const totalCount = existingLoc.tiles.length;
                existingLoc.x = ((existingLoc.x * (totalCount - count)) + sumX * mapData.tileWidth) / totalCount;
                existingLoc.y = ((existingLoc.y * (totalCount - count)) + sumY * mapData.tileHeight) / totalCount;
              } else {
                mapData.locations.push({
                  name: name,
                  x: (sumX / count) * mapData.tileWidth,
                  y: (sumY / count) * mapData.tileHeight,
                  tiles: validTiles
                });
              }
            }
            // 所有地点图层（包括仆役群房）解析完位置后都不作为普通图层渲染，保持透明
            continue;
          }

          if (visible) {
            // 否则，如果图层可见，解析为普通图层
            mapData.layers.push({
              name: name,
              gids: gids
            });
          }
        } else if (child.nodeName === 'group') {
          const isLocGroup = isLocationGroup || (name === '地点' || name === '大观园' || name === '荣国府' || name === '宁国府');
          parseLayers(child, isLocGroup);
        }
      }
    }
    parseLayers(mapNode);

    // 在预渲染之前，为没有位置的人物初始化位置
    initializeAgentPositions();

    // 预渲染所有图层到离线画布
    preRenderLayers();

    // 初始化地图适配
    fitMapToContainer();

    document.getElementById('mapLoading').style.display = 'none';
    requestAnimationFrame(renderLoop);

    // 交互逻辑
    let mouseDownPos = null;
    container.addEventListener('mousedown', e => {
      isDragging = true;
      mouseDownPos = { x: e.clientX, y: e.clientY };
      lastMousePos = { x: e.clientX, y: e.clientY };
      // 用户手动拖拽时，取消相机的自动追随
      camera.targetX = undefined;
      camera.targetY = undefined;
    });
    window.addEventListener('mousemove', e => {
      if (!isDragging) return;
      const dx = e.clientX - lastMousePos.x;
      const dy = e.clientY - lastMousePos.y;
      camera.x -= dx / camera.zoom;
      camera.y -= dy / camera.zoom;
      clampCamera();
      lastMousePos = { x: e.clientX, y: e.clientY };
    });
    window.addEventListener('mouseup', e => {
      isDragging = false;
      // 区分点击和拖拽：移动距离小于5px视为点击
      if (mouseDownPos) {
        const dist = Math.hypot(e.clientX - mouseDownPos.x, e.clientY - mouseDownPos.y);
        if (dist < 5) {
          handleCanvasClick(e, canvas);
        }
        mouseDownPos = null;
      }
    });
    container.addEventListener('wheel', e => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? 0.9 : 1.1;
      camera.zoom *= delta;
      camera.zoom = Math.max(camera.minZoom, Math.min(5, camera.zoom));
      clampCamera();
    }, { passive: false });

  } catch (err) {
    console.error('Map init error:', err);
    document.getElementById('mapLoading').textContent = '地图加载失败: ' + err.message;
  }
}

function fitMapToContainer() {
  const container = document.getElementById('mapContainer');
  const cw = container.clientWidth;
  const ch = container.clientHeight;
  
  // 计算最小缩放比例：使其完全覆盖容器
  const scaleX = cw / mapData.pixelWidth;
  const scaleY = ch / mapData.pixelHeight;
  
  // 使用较大的比例以确保“无缝隙”（Cover模式）
  camera.minZoom = Math.max(scaleX, scaleY);
  camera.zoom = camera.minZoom;
  
  // 初始位置居中
  camera.x = mapData.pixelWidth / 2;
  camera.y = mapData.pixelHeight / 2;
  clampCamera();
}

function clampCamera() {
  if (!mapData) return;
  const canvas = document.getElementById('mapCanvas');
  
  // 视口在缩放下的逻辑尺寸
  const vw = canvas.width / camera.zoom;
  const vh = canvas.height / camera.zoom;
  
  // 限制摄像机范围，防止地图边缘露出黑边
  const minX = vw / 2;
  const maxX = mapData.pixelWidth - vw / 2;
  const minY = vh / 2;
  const maxY = mapData.pixelHeight - vh / 2;
  
  // 如果地图尺寸小于视口（通常不会发生，因为我们设置了 minZoom）
  if (maxX < minX) camera.x = mapData.pixelWidth / 2;
  else camera.x = Math.max(minX, Math.min(maxX, camera.x));
  
  if (maxY < minY) camera.y = mapData.pixelHeight / 2;
  else camera.y = Math.max(minY, Math.min(maxY, camera.y));
}

function resizeCanvas() {
  const canvas = document.getElementById('mapCanvas');
  const container = document.getElementById('mapContainer');
  canvas.width = container.clientWidth;
  canvas.height = container.clientHeight;
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('Failed to load image: ' + src));
    img.src = src;
  });
}

// 静态人物志：后端数据到来时会覆盖同名字段，此处仅作兜底
const staticProfiles = {
  '贾宝玉':  { '家族':'荣国府', '性格':'多情善感、叛逆不羁', '核心驱动':'追求真情与自由，厌恶仕途经济', '语言风格':'温柔细腻，常以诗词抒情', '背景经历':'荣国府衔玉而生的嫡孙，贾政之子。自幼在女儿堆中长大，与林黛玉青梅竹马。厌恶八股文章，视功名为粪土，对诗词儿女情长极为痴迷。' },
  '林黛玉':  { '家族':'林家（寄居荣国府）', '性格':'敏感多愁、才情横溢', '核心驱动':'渴望被真正理解与爱，护卫内心的纯粹', '语言风格':'尖锐犀利，诗意盎然，常含讽刺', '背景经历':'扬州巡盐御史林如海之女，母亲贾敏早逝后寄居外祖母贾母处。体弱多病，才华出众，与贾宝玉心意相通，却因身世飘零而常感忧郁。' },
  '薛宝钗':  { '家族':'薛家', '性格':'端庄稳重、处事圆融', '核心驱动':'维护家族利益，以德行赢得众人认可', '语言风格':'温婉得体，言辞周全，少有锋芒', '背景经历':'皇商薛家之女，随母薛姨妈入住荣国府梨香院。博学多才，行事稳妥，深得长辈喜爱，心怀金玉良缘之说。' },
  '史湘云':  { '家族':'史家（保龄侯府）', '性格':'豪爽率真、乐观开朗', '核心驱动':'享受当下，以真性情待人', '语言风格':'爽朗直白，不拘小节，常带笑意', '背景经历':'史侯府千金，父母早亡，由叔婶抚养。性格豪迈，常女扮男装嬉戏，与贾宝玉情同兄妹，是大观园中最无忧无虑的存在。' },
  '贾母':    { '家族':'荣国府', '性格':'慈爱威严、精明练达', '核心驱动':'守护贾家荣耀，庇护子孙', '语言风格':'和蔼中带权威，一言九鼎', '背景经历':'荣国公贾代善之妻，贾府最高权威。历经荣辱，见多识广，对宝玉溺爱有加，是贾府内外一切事务的最终裁决者。' },
  '王夫人':  { '家族':'王家（嫁入荣国府）', '性格':'表面慈善、内心保守强硬', '核心驱动':'维护嫡系地位，为宝玉谋划前程', '语言风格':'平静少言，偶发雷霆', '背景经历':'王家千金，贾政之妻，宝玉生母。信佛吃斋，表面宽厚，实则对威胁宝玉的人毫不手软。金钏之死与晴雯被逐皆与其决断有关。' },
  '王熙凤':  { '家族':'王家（嫁入荣国府）', '性格':'精明强干、泼辣果决', '核心驱动':'掌控权力，维持自身地位与荣华', '语言风格':'伶牙俐齿，笑里藏刀，极具感染力', '背景经历':'王家出身，贾琏之妻，实际掌管荣国府内务。手腕强硬，善于逢迎，却也贪财弄权。协理宁国府一事令其声望达到顶峰。' },
  '薛姨妈':  { '家族':'薛家', '性格':'和善宽厚、护短溺爱', '核心驱动':'为子女谋得好前程', '语言风格':'亲切随和，常以长辈姿态说话', '背景经历':'王夫人之妹，薛蟠与薛宝钗之母。随子女寄居荣国府，与贾母、王夫人关系亲密，对薛蟠的劣行多有包庇。' },
  '贾政':    { '家族':'荣国府', '性格':'迂腐守旧、严肃刻板', '核心驱动':'光耀门楣，以儒家礼法约束子孙', '语言风格':'正经严肃，引经据典，令人生畏', '背景经历':'荣国府二老爷，宝玉之父。一生以仕途为重，对宝玉寄予厚望却屡屡失望，内心深处亦爱子，只是表达方式令宝玉望而生畏。' },
  '贾元春':  { '家族':'荣国府', '性格':'端庄贤淑、深沉内敛', '核心驱动':'以贵妃之位庇护贾家，却深陷宫廷孤寂', '语言风格':'庄重典雅，字字斟酌', '背景经历':'贾政长女，入宫为女史后晋封贤德妃。省亲归来时荣耀无比，却在深宫中倍感孤独。大观园即为迎接其省亲而建。' },
  '贾探春':  { '家族':'荣国府', '性格':'精明能干、志向高远', '核心驱动':'突破庶出身份的局限，以才干证明自身价值', '语言风格':'直率果断，条理清晰，有大局观', '背景经历':'贾政与赵姨娘所生庶女，自幼不认生母以求上进。曾短暂主持荣国府事务，推行改革颇有成效，被誉为"玫瑰花"。' },
  '贾迎春':  { '家族':'荣国府', '性格':'懦弱温顺、逆来顺受', '核心驱动':'求得平静，避免冲突', '语言风格':'轻声细语，少有主见', '背景经历':'贾赦庶女，性格懦弱，常被人欺负也不反抗，人称"二木头"。后嫁给中山狼孙绍祖，受尽虐待，命运悲苦。' },
  '贾惜春':  { '家族':'宁国府', '性格':'冷漠孤僻、心如铁石', '核心驱动':'以出世之心逃离污浊的贾府', '语言风格':'冷淡简短，不近人情', '背景经历':'宁国府贾珍之妹，自幼在荣国府长大。目睹贾府种种丑事，心灰意冷，最终选择出家为尼，是大观园中最早看破红尘之人。' },
  '李纨':    { '家族':'荣国府（寡居）', '性格':'守节自持、温柔沉静', '核心驱动':'抚育贾兰成才，以节妇之名自保', '语言风格':'温和克制，少言寡语', '背景经历':'贾珠之妻，贾珠早逝后独自抚养儿子贾兰。以槁木死灰自比，深居简出，主持诗社时却展现出温柔的一面。' },
  '贾琏':    { '家族':'荣国府', '性格':'风流好色、外表体面', '核心驱动':'享乐，维持表面的体面', '语言风格':'圆滑世故，善于应酬', '背景经历':'贾赦之子，王熙凤之夫。负责荣国府对外事务，能力平平却好色成性，与多女有染，惧内却屡屡背着凤姐偷腥。' },
  '贾珍':    { '家族':'宁国府', '性格':'荒淫无度、仗势欺人', '核心驱动':'纵情享乐，维持宁国府的表面威严', '语言风格':'豪横霸道，不拘礼法', '背景经历':'宁国府族长，贾蓉之父。生活糜烂，与儿媳秦可卿之间传有丑闻。秦可卿丧事大操大办，极尽奢华，令人侧目。' },
  '贾蓉':    { '家族':'宁国府', '性格':'软弱无能、唯父命是从', '核心驱动':'在父亲贾珍的阴影下苟且度日', '语言风格':'唯唯诺诺，少有自主', '背景经历':'贾珍之子，秦可卿之夫。妻子早逝后续娶，本人才能平庸，完全活在父亲的掌控之下。' },
  '贾环':    { '家族':'荣国府', '性格':'阴险小气、自卑嫉妒', '核心驱动':'争夺在贾府中的地位，报复轻视他的人', '语言风格':'阴阳怪气，小人得志时嚣张', '背景经历':'贾政与赵姨娘所生庶子，自幼受人轻视。性格扭曲，曾故意烫伤宝玉，向贾政诬告宝玉，是贾府中令人厌恶的存在。' },
  '赵姨娘':  { '家族':'荣国府（姨娘）', '性格':'泼辣粗鄙、心胸狭窄', '核心驱动':'为贾环争得地位，对抗王夫人一系', '语言风格':'粗俗直白，常大吵大闹', '背景经历':'贾政之妾，贾环与探春之母。地位低下，性格粗鄙，常与丫鬟发生冲突。曾勾结马道婆用魔法害宝玉和凤姐，是贾府中的搅事者。' },
  '薛蟠':    { '家族':'薛家', '性格':'横行霸道、胸无点墨', '核心驱动':'纵情声色，为所欲为', '语言风格':'粗鲁直白，常闹笑话', '背景经历':'薛家长子，人称"呆霸王"。幼年仗势打死冯渊，后又因争香菱打死人命。虽粗鄙，偶有憨直可爱之处，是书中重要的喜剧人物。' },
  '袭人':    { '家族':'怡红院（丫鬟）', '性格':'温柔体贴、工于心计', '核心驱动':'以贤惠之名稳固在宝玉身边的地位', '语言风格':'温柔婉转，善于规劝', '背景经历':'宝玉首席大丫鬟，原名珍珠，因宝玉爱读《西厢记》中"花气袭人知昼暖"而改名。与宝玉关系亲密，曾向王夫人进言，被视为宝玉的准姨娘。' },
  '晴雯':    { '家族':'怡红院（丫鬟）', '性格':'刚烈率真、心高气傲', '核心驱动':'以真性情处世，不肯低头媚俗', '语言风格':'伶俐尖刻，快人快语', '背景经历':'宝玉最宠爱的丫鬟，容貌出众，针线活极好。因性格刚烈得罪人，被王夫人以"狐媚子"之名撵出，含冤病逝。宝玉为其作《芙蓉女儿诔》。' },
  '紫鹃':    { '家族':'潇湘馆（丫鬟）', '性格':'忠诚细心、重情重义', '核心驱动':'全心守护林黛玉，为其谋划终身', '语言风格':'温柔体贴，偶有机智', '背景经历':'林黛玉的贴身丫鬟，原是贾母房中的鹦哥，后拨给黛玉。对黛玉忠心耿耿，曾试探宝玉对黛玉的心意，是黛玉在贾府中最可信赖的人。' },
  '麝月':    { '家族':'怡红院（丫鬟）', '性格':'稳重平和、任劳任怨', '核心驱动':'尽职守护怡红院的秩序', '语言风格':'平实稳重，不多言语', '背景经历':'怡红院丫鬟，性格稳重，不似晴雯张扬也不似袭人心机深。宝玉曾为其梳头，是怡红院中最踏实可靠的存在。' },
  '平儿':    { '家族':'王熙凤院（通房丫鬟）', '性格':'聪慧善良、左右逢源', '核心驱动':'在凤姐与贾琏之间维持平衡，以善心化解矛盾', '语言风格':'机智圆滑，善解人意', '背景经历':'王熙凤的陪嫁丫鬟，贾琏的通房。夹在凤姐与贾琏之间两面受气，却以善良和智慧赢得众人好感。宝玉视其为难得的好人。' },
  '鸳鸯':    { '家族':'贾母院（丫鬟）', '性格':'刚烈忠贞、机智勇敢', '核心驱动':'守护贾母，捍卫自身尊严', '语言风格':'直率有力，敢于抗争', '背景经历':'贾母最信任的贴身丫鬟，掌管贾母的钥匙和财物。贾赦欲纳其为妾，她当众拒绝并立誓终身不嫁，是贾府丫鬟中最有骨气的一个。' },
  '妙玉':    { '家族':'无（出家人）', '性格':'孤高自许、洁癖偏执', '核心驱动':'在尘世中守护内心的清净与高洁', '语言风格':'清冷高傲，言辞中带禅意', '背景经历':'苏州官宦之女，因体弱多病被送入空门。随师父进京后住进大观园栊翠庵。才华横溢，却性格孤僻，以"槛外人"自居，对宝玉有一份说不清道不明的情愫。' }
};

const agentToHome = {
  '贾宝玉': '怡红院',
  '林黛玉': '潇湘馆',
  '薛宝钗': '蘅芜院',
  '贾母': '贾母院',
  '王夫人': '王夫人院',
  '王熙凤': '王熙凤院',
  '李纨': '稻香村',
  '贾兰': '稻香村',
  '贾探春': '晓翠堂',
  '贾迎春': '紫凌洲',
  '贾惜春': '暖乡坞',
  '妙玉': '达摩庵',
  '袭人': '怡红院',
  '晴雯': '怡红院',
  '麝月': '怡红院',
  '紫鹃': '潇湘馆',
  '平儿': '王熙凤院',
  '鸳鸯': '贾母院',
  '史湘云': '蘅芜院',
  '薛姨妈': '薛姨妈院',
  '薛蟠': '薛姨妈院',
  '贾政': '贾政内书房',
  '贾琏': '王熙凤院',
  '贾珍': '宁国府正院',
  '贾蓉': '贾蓉院',
  '尤氏': '尤氏院',
  '贾元春': '顾恩思义殿',
  '赵姨娘': '王夫人院',
  '贾环': '王夫人院',
  '彩云': '王夫人院',
  '彩霞': '王夫人院',
  '金钏': '王夫人院',
  '玉钏': '王夫人院',
  '司棋': '紫凌洲',
  '侍书': '晓翠堂',
  '入画': '暖乡坞',
  '翠缕': '蘅芜院',
  '小红': '怡红院',
  '雪雁': '潇湘馆',
  '秋纹': '怡红院',
  '碧痕': '怡红院',
  '莺儿': '蘅芜院',
  '香菱': '梨香院',
  '琥珀': '贾母院',
  '素云': '稻香村',
  '丰儿': '王熙凤院',
  '焦大': '宁国府正院',
  '赖大': '仆役群房',
  '周瑞': '周瑞院',
  '林之孝': '仆役群房'
};

function isServant(name) {
  const servantList = ['袭人','晴雯','麝月','紫鹃','平儿','鸳鸯','彩云','彩霞','金钏','玉钏','司棋','侍书','入画','翠缕','小红','雪雁','秋纹','碧痕','莺儿','香菱','琥珀','素云','丰儿','焦大','赖大','周瑞','林之孝'];
  return servantList.includes(name);
}

function initializeAgentPositions() {
  if (!mapData || !mapData.locations) return;

  const servantFallback = mapData.locations.find(l => l.name === '仆役群房');
  const masterFallback = mapData.locations.find(l => l.name === '荣国府') || mapData.locations.find(l => l.name === '大观园');

  let count = 0;
  Object.keys(agentsData).forEach(id => {
    const d = agentsData[id];
    const name = formatAgentName(id);

    // 如果人物已经有有效位置（不是 [0,0] 且来自后端快照），则跳过
    if (d.profile && d.profile.position && (d.profile.position[0] !== 0 || d.profile.position[1] !== 0)) return;

    if (assignRandomPositionToAgent(id, name, servantFallback, masterFallback)) {
      count++;
    }
  });
  console.log(`Initialized ${count} agent positions`);

  // 初始化虚拟小厮
  initializeNPCs(servantFallback);
}

// 为单个agent分配随机可通行位置
function assignRandomPositionToAgent(agentId, agentName, servantFallback, masterFallback) {
  if (!mapData || !mapData.locations) return false;

  const d = agentsData[agentId];
  if (!d) return false;

  const name = agentName || formatAgentName(agentId);

  // 如果没有传入兜底地点，则查找
  if (!servantFallback) {
    servantFallback = mapData.locations.find(l => l.name === '仆役群房');
  }
  if (!masterFallback) {
    masterFallback = mapData.locations.find(l => l.name === '荣国府') || mapData.locations.find(l => l.name === '大观园');
  }

  // 随机选择一个地点
  let location = null;

  // 尝试根据角色住处匹配
  const homeName = agentToHome[name];
  if (homeName) {
    location = mapData.locations.find(l => l.name === homeName || l.name.includes(homeName) || homeName.includes(l.name));
  }

  // 如果没有匹配的住处，随机选择一个地点
  if (!location && mapData.locations.length > 0) {
    location = mapData.locations[Math.floor(Math.random() * mapData.locations.length)];
  }

  // 智能兜底逻辑
  if (!location) {
    if (isServant(name)) {
      location = servantFallback;
    } else {
      location = masterFallback;
    }
  }

  if (location && location.tiles) {
    let tx, ty;

    // 优先尝试寻找可通行瓦片
    if (mapData.passableGids) {
      const passableTiles = location.tiles.filter(tileIdx => mapData.passableGids[tileIdx] !== 0);
      if (passableTiles.length > 0) {
        const randomTileIdx = passableTiles[Math.floor(Math.random() * passableTiles.length)];
        tx = randomTileIdx % mapData.width;
        ty = Math.floor(randomTileIdx / mapData.width);
      }
    }

    // 兜底1：如果该地点没有标记可通行区域，就在该地点的所有瓦片中随机选一个
    if (tx === undefined && location.tiles.length > 0) {
      const randomTileIdx = location.tiles[Math.floor(Math.random() * location.tiles.length)];
      tx = randomTileIdx % mapData.width;
      ty = Math.floor(randomTileIdx / mapData.width);
    }

    // 兜底2：使用地点中心位置（仅当没有瓦片数据时）
    if (tx === undefined) {
      tx = Math.floor(location.x / mapData.tileWidth);
      ty = Math.floor(location.y / mapData.tileHeight);
    }

    if (!d.profile) d.profile = {};
    d.profile.position = [tx, ty];

    // 更新闲逛状态
    const worldX = tx * mapData.tileWidth;
    const worldY = ty * mapData.tileHeight;
    agentIdleStates[agentId] = {
      currentX: worldX,
      currentY: worldY,
      targetX: worldX,
      targetY: worldY,
      lastUpdate: Date.now(),
      nextMoveTime: Date.now() + Math.random() * 2000
    };

    console.log(`Assigned random position [${tx}, ${ty}] at "${location.name}" to agent "${agentId}"`);
    return true;
  }

  return false;
}

// 获取地点中随机的可通行坐标
function getRandomLocationPos(location) {
  if (!location || !location.tiles) return null;
  let tx, ty;
  if (mapData.passableGids) {
    const passableTiles = location.tiles.filter(tileIdx => mapData.passableGids[tileIdx] !== 0);
    if (passableTiles.length > 0) {
      const randomTileIdx = passableTiles[Math.floor(Math.random() * passableTiles.length)];
      tx = randomTileIdx % mapData.width;
      ty = Math.floor(randomTileIdx / mapData.width);
      return { x: tx * mapData.tileWidth, y: ty * mapData.tileHeight };
    }
  }
  // 兜底
  if (location.tiles.length > 0) {
    const randomTileIdx = location.tiles[Math.floor(Math.random() * location.tiles.length)];
    tx = randomTileIdx % mapData.width;
    ty = Math.floor(randomTileIdx / mapData.width);
    return { x: tx * mapData.tileWidth, y: ty * mapData.tileHeight };
  }
  return { x: location.x, y: location.y };
}

function getRandomLocation() {
  const validLocs = mapData.locations.filter(l => l.name !== '仆役群房' && l.tiles && l.tiles.length > 0);
  if (validLocs.length === 0) return null;
  return validLocs[Math.floor(Math.random() * validLocs.length)];
}

// A* Pathfinding implementation
class MinHeap {
  constructor() { this.heap = []; }
  push(node) {
    this.heap.push(node);
    this.bubbleUp(this.heap.length - 1);
  }
  pop() {
    if (this.heap.length === 0) return null;
    const top = this.heap[0];
    const bottom = this.heap.pop();
    if (this.heap.length > 0) {
      this.heap[0] = bottom;
      this.sinkDown(0);
    }
    return top;
  }
  isEmpty() { return this.heap.length === 0; }
  bubbleUp(n) {
    let element = this.heap[n];
    while (n > 0) {
      let parentN = Math.floor((n + 1) / 2) - 1;
      let parent = this.heap[parentN];
      if (element.priority >= parent.priority) break;
      this.heap[parentN] = element;
      this.heap[n] = parent;
      n = parentN;
    }
  }
  sinkDown(n) {
    let length = this.heap.length;
    let element = this.heap[n];
    while (true) {
      let child2N = (n + 1) * 2;
      let child1N = child2N - 1;
      let swap = null;
      if (child1N < length) {
        let child1 = this.heap[child1N];
        if (child1.priority < element.priority) swap = child1N;
      }
      if (child2N < length) {
        let child2 = this.heap[child2N];
        if (child2.priority < (swap === null ? element.priority : this.heap[child1N].priority)) swap = child2N;
      }
      if (swap === null) break;
      this.heap[n] = this.heap[swap];
      this.heap[swap] = element;
      n = swap;
    }
  }
}

function findPath(startX, startY, endX, endY) {
  if (!mapData || !mapData.passableGids) return null;
  const width = mapData.width;
  const height = mapData.height;
  
  if (startX < 0 || startX >= width || startY < 0 || startY >= height) return null;
  if (endX < 0 || endX >= width || endY < 0 || endY >= height) return null;
  
  const startIdx = startY * width + startX;
  const endIdx = endY * width + endX;

  // 如果起点不可通行，找附近可通行的点
  let actualStartIdx = startIdx;
  if (mapData.passableGids[startIdx] === 0) {
    let found = false;
    const queue = [startIdx];
    const visited = new Set([startIdx]);
    while(queue.length > 0) {
      const curr = queue.shift();
      if (mapData.passableGids[curr] !== 0) {
        actualStartIdx = curr;
        found = true;
        break;
      }
      const cx = curr % width;
      const cy = Math.floor(curr / width);
      const neighbors = [
        {x: cx+1, y: cy}, {x: cx-1, y: cy},
        {x: cx, y: cy+1}, {x: cx, y: cy-1}
      ];
      for (const n of neighbors) {
        if (n.x >= 0 && n.x < width && n.y >= 0 && n.y < height) {
          const nIdx = n.y * width + n.x;
          if (!visited.has(nIdx)) {
            visited.add(nIdx);
            queue.push(nIdx);
          }
        }
      }
      if (visited.size > 100) break;
    }
    if (!found) return null;
  }

  let actualEndIdx = endIdx;
  if (mapData.passableGids[actualEndIdx] === 0) {
     let found = false;
     const queue = [actualEndIdx];
     const visited = new Set([actualEndIdx]);
     while(queue.length > 0) {
       const curr = queue.shift();
       if (mapData.passableGids[curr] !== 0) {
         actualEndIdx = curr;
         found = true;
         break;
       }
       const cx = curr % width;
       const cy = Math.floor(curr / width);
       const neighbors = [
         {x: cx+1, y: cy}, {x: cx-1, y: cy},
         {x: cx, y: cy+1}, {x: cx, y: cy-1}
       ];
       for (const n of neighbors) {
         if (n.x >= 0 && n.x < width && n.y >= 0 && n.y < height) {
           const nIdx = n.y * width + n.x;
           if (!visited.has(nIdx)) {
             visited.add(nIdx);
             queue.push(nIdx);
           }
         }
       }
       if (visited.size > 100) break;
     }
     if (!found) return null;
  }

  const actualEndX = actualEndIdx % width;
  const actualEndY = Math.floor(actualEndIdx / width);

  const frontier = new MinHeap();
  frontier.push({idx: actualStartIdx, priority: 0});

  const cameFrom = new Map();
  const costSoFar = new Map();
  cameFrom.set(actualStartIdx, null);
  costSoFar.set(actualStartIdx, 0);
  
  const heuristic = (aIdx, bIdx) => {
    const ax = aIdx % width;
    const ay = Math.floor(aIdx / width);
    const bx = bIdx % width;
    const by = Math.floor(bIdx / width);
    // 曼哈顿距离
    return Math.abs(ax - bx) + Math.abs(ay - by);
  };
  
  let pathFound = false;
  
  while (!frontier.isEmpty()) {
    const currentObj = frontier.pop();
    const current = currentObj.idx;
    
    if (current === actualEndIdx) {
      pathFound = true;
      break;
    }
    
    const cx = current % width;
    const cy = Math.floor(current / width);
    
    const dirs = [
      {dx: 0, dy: -1, cost: 1}, {dx: 1, dy: 0, cost: 1},
      {dx: 0, dy: 1, cost: 1}, {dx: -1, dy: 0, cost: 1},
      {dx: 1, dy: -1, cost: 1.414}, {dx: 1, dy: 1, cost: 1.414},
      {dx: -1, dy: 1, cost: 1.414}, {dx: -1, dy: -1, cost: 1.414}
    ];
    
    for (const dir of dirs) {
      const nx = cx + dir.dx;
      const ny = cy + dir.dy;
      if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
        const nIdx = ny * width + nx;
        if (mapData.passableGids[nIdx] !== 0) {
           if (Math.abs(dir.dx) === 1 && Math.abs(dir.dy) === 1) {
             const idx1 = cy * width + nx;
             const idx2 = ny * width + cx;
             if (mapData.passableGids[idx1] === 0 || mapData.passableGids[idx2] === 0) continue;
           }
           
           const newCost = costSoFar.get(current) + dir.cost;
           if (!costSoFar.has(nIdx) || newCost < costSoFar.get(nIdx)) {
             costSoFar.set(nIdx, newCost);
             const priority = newCost + heuristic(nIdx, actualEndIdx);
             frontier.push({idx: nIdx, priority: priority});
             cameFrom.set(nIdx, current);
           }
        }
      }
    }
  }
  
  if (!pathFound) return null;
  
  const path = [];
  let current = actualEndIdx;
  while (current !== actualStartIdx) {
    path.push({ x: current % width, y: Math.floor(current / width) });
    current = cameFrom.get(current);
  }
  path.reverse();
  return path;
}

function initializeNPCs(servantFallback) {
  if (npcs.length > 0) return; // 防止重复初始化

  // 确保小厮图片被加载
  const spriteName = '小厮';
  if (!agentSprites[spriteName]) {
    const img = new Image();
    img.src = `../map/sprite/${spriteName}.png`;
    agentSprites[spriteName] = img;
  }

  // 预加载市民图片
  citizenSpriteNames.forEach(name => {
    if (!agentSprites[name]) {
      const img = new Image();
      img.src = `../map/sprite/${name}.png`;
      agentSprites[name] = img;
    }
  });

  for (let i = 0; i < 25; i++) {
    // 30% 的小厮随机初始化在地图上的某个地点，而非仆役群房
    const useRandomLoc = Math.random() < 0.3;
    const initLoc = useRandomLoc ? getRandomLocation() : servantFallback;
    const startPos = getRandomLocationPos(initLoc || servantFallback);
    if (!startPos) continue;

    npcs.push({
      id: `npc_${i}`,
      name: spriteName,
      currentX: startPos.x,
      currentY: startPos.y,
      targetX: startPos.x,
      targetY: startPos.y,
      state: 'wait_at_home', // 状态机: wait_at_home -> move_to_start -> wait_at_start -> move_to_end -> wait_at_end -> move_to_home -> wait_at_home
      waitTimeEnd: Date.now() + Math.random() * 20000,
      speed: 0.8 + Math.random() * 0.8,
      facingLeft: false,
      homeLoc: servantFallback
    });
  }
  console.log(`Initialized ${npcs.length} NPCs`);
}

function preRenderLayers() {
  layerCanvases = mapData.layers.map(layer => {
    const offCanvas = document.createElement('canvas');
    offCanvas.width = mapData.pixelWidth;
    offCanvas.height = mapData.pixelHeight;
    const offCtx = offCanvas.getContext('2d');
    
    // 渲染该层所有瓦片
    for (let y = 0; y < mapData.height; y++) {
      for (let x = 0; x < mapData.width; x++) {
        const gid = layer.gids[y * mapData.width + x];
        if (gid === 0) continue;
        drawTileToCtx(offCtx, gid, x * mapData.tileWidth, y * mapData.tileHeight);
      }
    }
    return offCanvas;
  });
}

function drawTileToCtx(ctx, gid, x, y) {
  let tileset = null;
  for (let i = tilesets.length - 1; i >= 0; i--) {
    if (gid >= tilesets[i].firstgid) {
      tileset = tilesets[i];
      break;
    }
  }
  if (!tileset) return;

  const localId = gid - tileset.firstgid;
  const tx = (localId % tileset.columns) * tileset.tileWidth;
  const ty = Math.floor(localId / tileset.columns) * tileset.tileHeight;

  ctx.drawImage(
    tileset.image,
    tx, ty, tileset.tileWidth, tileset.tileHeight,
    x, y, tileset.tileWidth, tileset.tileHeight
  );
}

function renderLoop() {
  const canvas = document.getElementById('mapCanvas');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  renderDialogueMiniMap(Date.now());

  if (!mapData || layerCanvases.length === 0) return;

  // 相机平滑追随逻辑 (阻尼移动)
  if (camera.targetX !== undefined && camera.targetY !== undefined) {
    const dx = camera.targetX - camera.x;
    const dy = camera.targetY - camera.y;
    // 如果距离很小，直接吸附；否则按比例平滑移动
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) {
      camera.x = camera.targetX;
      camera.y = camera.targetY;
    } else {
      camera.x += dx * 0.05; // 0.05 是平滑系数，越小越平滑
      camera.y += dy * 0.05;
    }
  }

  ctx.save();
  // 核心：视口转换
  ctx.translate(canvas.width / 2, canvas.height / 2);
  ctx.scale(camera.zoom, camera.zoom);
  ctx.translate(-camera.x, -camera.y);

  // 1. 视口剔除（Viewport Culling）计算
  const vw = canvas.width / camera.zoom;
  const vh = canvas.height / camera.zoom;
  const viewLeft = camera.x - vw / 2;
  const viewTop = camera.y - vh / 2;

  // 1. 绘制地图背景 (预渲染的所有图层)
  for (let i = 0; i < layerCanvases.length; i++) {
    ctx.drawImage(
      layerCanvases[i],
      viewLeft, viewTop, vw, vh,
      viewLeft, viewTop, vw, vh
    );
  }

  // 2. 绘制动态人物 (在所有图层之上)
  const now = Date.now();
  const cellOccupants = {}; // 记录每个格子的人物 ID 列表
  Object.keys(agentsData).forEach(id => {
    const d = agentsData[id];
    if (d.profile && d.profile.position) {
      // 这里的 px, py 是他们在地图上的"逻辑格子"位置
      // 我们用闲逛后的物理位置反推当前视觉上的格子，以便避让更自然
      const state = agentIdleStates[id];
      let cx = d.profile.position[0];
      let cy = d.profile.position[1];
      if (state) {
        cx = Math.floor(state.currentX / mapData.tileWidth);
        cy = Math.floor(state.currentY / mapData.tileHeight);
      }
      
      const cellKey = `${cx},${cy}`;
      if (!cellOccupants[cellKey]) cellOccupants[cellKey] = [];
      cellOccupants[cellKey].push(id);
    }
  });

  Object.keys(agentsData).forEach(id => {
    const d = agentsData[id];
    if (d.profile && d.profile.position) {
      const [logicPx, logicPy] = d.profile.position;
      const ax = logicPx * mapData.tileWidth;
      const ay = logicPy * mapData.tileHeight;
      
      // 更新闲逛状态逻辑
      const state = agentIdleStates[id];
      let drawX = ax;
      let drawY = ay;

      if (state) {
        // 1. 定期设定一个新的随机目标格子（在同地点内）
        if (now > state.nextMoveTime) {
          // 查找该人物所在的地点
          const name = formatAgentName(id);
          const homeName = agentToHome[name];
          let location = null;
          if (homeName) {
            location = mapData.locations.find(l => l.name === homeName || l.name.includes(homeName) || homeName.includes(l.name));
          }
          if (!location) {
            location = mapData.locations.find(l => l.name === '仆役群房');
          }

          if (location && location.tiles) {
            // 优先找可通行瓦片
            let candidateTiles = [];
            if (mapData.passableGids) {
              candidateTiles = location.tiles.filter(tileIdx => mapData.passableGids[tileIdx] !== 0);
            }
            // 如果没有可通行瓦片，则使用该地点的所有瓦片
            if (candidateTiles.length === 0) {
              candidateTiles = location.tiles;
            }

            if (candidateTiles.length > 0) {
              // 随机选一个格子，并且保证这个格子在当前位置的附近，不要选太远的格子导致穿墙
              // 将候选格子按距离当前位置排序，选最近的几个之一
              const currentLogicX = Math.floor(state.currentX / mapData.tileWidth);
              const currentLogicY = Math.floor(state.currentY / mapData.tileHeight);
              
              const nearbyTiles = candidateTiles.filter(tileIdx => {
                const px = tileIdx % mapData.width;
                const py = Math.floor(tileIdx / mapData.width);
                
                // 1. 限制在曼哈顿距离 2 格以内
                const dist = Math.abs(px - currentLogicX) + Math.abs(py - currentLogicY);
                if (dist > 2) return false;
                
                // 2. 简单的直线碰撞检测（确保没有穿过不可通行的格子）
                if (dist === 2) {
                  // 如果是斜向移动，检查相邻的两个格子是否可通行
                  if (px !== currentLogicX && py !== currentLogicY) {
                    const idx1 = py * mapData.width + currentLogicX;
                    const idx2 = currentLogicY * mapData.width + px;
                    if (mapData.passableGids && mapData.passableGids[idx1] === 0 && mapData.passableGids[idx2] === 0) {
                      return false; // 两个方向都被堵死，无法斜穿
                    }
                  } else {
                    // 如果是直线走两格，检查中间那一格是否可通行
                    const midX = (px + currentLogicX) / 2;
                    const midY = (py + currentLogicY) / 2;
                    const midIdx = midY * mapData.width + midX;
                    if (mapData.passableGids && mapData.passableGids[midIdx] === 0) {
                      return false; // 中间被堵死，无法穿墙
                    }
                  }
                }
                return true;
              });

              // 如果附近没有可通行的路（可能被堵在死角），就留在原地或者选一个最近的
              const pool = nearbyTiles.length > 0 ? nearbyTiles : [currentLogicY * mapData.width + currentLogicX];
              const randomTileIdx = pool[Math.floor(Math.random() * pool.length)];
              
              const targetPx = randomTileIdx % mapData.width;
              const targetPy = Math.floor(randomTileIdx / mapData.width);
              
              state.targetX = targetPx * mapData.tileWidth;
              state.targetY = targetPy * mapData.tileHeight;
              state.path = findPath(currentLogicX, currentLogicY, targetPx, targetPy);
              state.pathIndex = 0;
            } else {
              // 如果地点连瓦片都没有，就在附近 1 格内随机走动
              const moveX = (Math.floor(Math.random() * 3) - 1) * mapData.tileWidth;
              const moveY = (Math.floor(Math.random() * 3) - 1) * mapData.tileHeight;
              state.targetX = state.currentX + moveX;
              state.targetY = state.currentY + moveY;
              state.path = null;
            }
          } else {
            // 如果找不到地点信息，就在附近 1 格内随机走动
            const moveX = (Math.floor(Math.random() * 3) - 1) * mapData.tileWidth;
            const moveY = (Math.floor(Math.random() * 3) - 1) * mapData.tileHeight;
            state.targetX = state.currentX + moveX;
            state.targetY = state.currentY + moveY;
            state.path = null;
          }
          
          state.nextMoveTime = now + 5000 + Math.random() * 5000;
        }
        
        // 2. 匀速平移到目标位置
        if (state.path && state.pathIndex < state.path.length) {
          const nextNode = state.path[state.pathIndex];
          const targetNodeX = nextNode.x * mapData.tileWidth;
          const targetNodeY = nextNode.y * mapData.tileHeight;
          const dx = targetNodeX - state.currentX;
          const dy = targetNodeY - state.currentY;
          const distance = Math.sqrt(dx * dx + dy * dy);

          if (distance < 1) {
            state.pathIndex++;
            // 走完路径最后一步，到达目的地
            if (state.pathIndex >= state.path.length && state.movingToTarget) {
              state.movingToTarget = false;
              state.nextMoveTime = now + 1000 + Math.random() * 2000;
            }
          } else {
            const speed = 0.5; // 设置移动速度（像素/帧）
            const moveRatio = Math.min(speed / distance, 1.0); // 确保不会冲过头
            state.currentX += dx * moveRatio;
            state.currentY += dy * moveRatio;
            if (Math.abs(dx) > 0.1) {
              state.facingLeft = dx < 0;
            }
          }
        } else {
          const dx = state.targetX - state.currentX;
          const dy = state.targetY - state.currentY;
          const distance = Math.sqrt(dx * dx + dy * dy);
          
          if (distance > 1) { // 只要没到目标点就继续移动
            const speed = 0.5; // 设置移动速度（像素/帧）
            const moveRatio = Math.min(speed / distance, 1.0); // 确保不会冲过头
            state.currentX += dx * moveRatio;
            state.currentY += dy * moveRatio;

            // 记录移动方向，用于 Sprite 翻转
            if (Math.abs(dx) > 0.1) {
              state.facingLeft = dx < 0;
            }
          } else if (state.movingToTarget) {
            // 无路径直接移动，到达目标点后开始闲逛
            state.movingToTarget = false;
            state.nextMoveTime = now + 1000 + Math.random() * 2000;
          }
        }
        
        drawX = state.currentX;
        drawY = state.currentY;
      }

      // 视口剔除判断
      if (drawX > viewLeft - 100 && drawX < viewLeft + vw + 100 && 
          drawY > viewTop - 100 && drawY < viewTop + vh + 100) {
        
        drawAgentOnMap(ctx, id, drawX, drawY, state ? state.facingLeft : false);
      }
    }
  });

  // 2.5 绘制虚拟小厮 (带有状态机逻辑)
  npcs.forEach(npc => {
    // 状态机更新
    if (npc.state.startsWith('wait_')) {
      if (now > npc.waitTimeEnd) {
        // 等待结束，决定下一个状态和目标
        let nextState = '';
        let pos = null;
        if (npc.state === 'wait_at_home') {
          nextState = 'move_to_start';
          const loc = getRandomLocation();
          pos = getRandomLocationPos(loc);
        } else if (npc.state === 'wait_at_start') {
          nextState = 'move_to_end';
          const loc = getRandomLocation();
          pos = getRandomLocationPos(loc);
        } else if (npc.state === 'wait_at_end') {
          nextState = 'move_to_home';
          pos = getRandomLocationPos(npc.homeLoc);
        }
        
        if (pos) {
          npc.state = nextState;
          npc.targetX = pos.x; 
          npc.targetY = pos.y;
          const startX = Math.floor(npc.currentX / mapData.tileWidth);
          const startY = Math.floor(npc.currentY / mapData.tileHeight);
          const endX = Math.floor(pos.x / mapData.tileWidth);
          const endY = Math.floor(pos.y / mapData.tileHeight);
          npc.path = findPath(startX, startY, endX, endY);
          npc.pathIndex = 0;
        }
      }
    } else if (npc.state.startsWith('move_')) {
      // 移动逻辑
      let reachedTarget = false;
      if (npc.path && npc.pathIndex < npc.path.length) {
         const nextNode = npc.path[npc.pathIndex];
         const targetNodeX = nextNode.x * mapData.tileWidth;
         const targetNodeY = nextNode.y * mapData.tileHeight;
         const dx = targetNodeX - npc.currentX;
         const dy = targetNodeY - npc.currentY;
         const distance = Math.sqrt(dx * dx + dy * dy);
         
         if (distance < 2) {
            npc.pathIndex++;
            if (npc.pathIndex >= npc.path.length) {
              reachedTarget = true;
            }
         } else {
            const speed = npc.speed;
            const moveRatio = Math.min(speed / distance, 1.0);
            npc.currentX += dx * moveRatio;
            npc.currentY += dy * moveRatio;
            if (Math.abs(dx) > 0.1) npc.facingLeft = dx < 0;
         }
      } else {
         // 如果没有路径或者已经到达最后节点，则回退到直接移动或直接判定到达
         const dx = npc.targetX - npc.currentX;
         const dy = npc.targetY - npc.currentY;
         const distance = Math.sqrt(dx * dx + dy * dy);
         if (distance < 2) {
            reachedTarget = true;
         } else {
            const speed = npc.speed;
            const moveRatio = Math.min(speed / distance, 1.0);
            npc.currentX += dx * moveRatio;
            npc.currentY += dy * moveRatio;
            if (Math.abs(dx) > 0.1) npc.facingLeft = dx < 0;
         }
      }

      if (reachedTarget) {
        // 到达目标，进入下一个等待状态
        if (npc.state === 'move_to_start') {
          npc.state = 'wait_at_start';
          npc.waitTimeEnd = now + 8000 + Math.random() * 20000;
        } else if (npc.state === 'move_to_end') {
          npc.state = 'wait_at_end';
          npc.waitTimeEnd = now + 8000 + Math.random() * 20000;
        } else if (npc.state === 'move_to_home') {
          npc.state = 'wait_at_home';
          npc.waitTimeEnd = now + 15000 + Math.random() * 30000;
        }
      }
    }

    // 视口剔除与渲染
    if (npc.currentX > viewLeft - 100 && npc.currentX < viewLeft + vw + 100 && 
        npc.currentY > viewTop - 100 && npc.currentY < viewTop + vh + 100) {
      
      // 为了避让，将物理坐标转为网格坐标
      const cx = Math.floor(npc.currentX / mapData.tileWidth);
      const cy = Math.floor(npc.currentY / mapData.tileHeight);
      const cellKey = `${cx},${cy}`;
      
      // 将小厮也加入当前帧的避让计算
      if (!cellOccupants[cellKey]) cellOccupants[cellKey] = [];
      cellOccupants[cellKey].push(npc.id);

      drawAgentOnMap(ctx, npc.id, npc.currentX, npc.currentY, npc.facingLeft, true);
    }
  });

  // 2.6 绘制边缘市民
  updateAndDrawCitizens(ctx, now);

  // 2.7 绘制事件气泡
  drawEventBubbles(ctx);

  // 2.8 绘制当前打开对话在地图上的循环气泡
  drawDialogueReplayBubble(ctx, now);

  // 2.9 绘制当前打开对话对应的地点标记
  drawDialogueLocationMarker(ctx);

  // 3. 绘制地点名称 (当缩放到接近最小时)
  if (camera.zoom <= camera.minZoom * 1.2) {
    drawLocationLabels(ctx);
  }

  ctx.restore();
  requestAnimationFrame(renderLoop);
}

function drawLocationLabels(ctx) {
  if (!mapData.locations) return;

  // 补偿缩放：屏幕上始终显示为 22px，缩得越小字越大（世界坐标系中）
  const screenFontSize = 22;
  const fontSize = screenFontSize / camera.zoom;
  
  // 缩放到最小时（接近 minZoom）使用中国风字体
  const isMinZoom = camera.zoom <= camera.minZoom * 1.2;
  const fontFamily = isMinZoom ? '"Ma Shan Zheng", "STKaiti", cursive' : '"ZCOOL XiaoWei"';
  ctx.font = `${isMinZoom ? '' : 'bold '}${fontSize}px ${fontFamily}`;
  ctx.fillStyle = '#fff';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  mapData.locations.forEach(loc => {
    // 不显示”仆役群房”的文字标签
    if (loc.name === '仆役群房') return;

    // 绘制半透明背景，提升文字可读性
    const metrics = ctx.measureText(loc.name);
    const bgPad = 16 / camera.zoom;
    const bgHeight = (fontSize + 8) / camera.zoom * camera.zoom + 8 / camera.zoom;
    const bgWidth = metrics.width + bgPad;
    const bgH = fontSize * 1.6;

    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
    if (ctx.roundRect) {
      ctx.beginPath();
      ctx.roundRect(loc.x - bgWidth / 2, loc.y - bgH / 2, bgWidth, bgH, 8 / camera.zoom);
      ctx.fill();
    } else {
      ctx.fillRect(loc.x - bgWidth / 2, loc.y - bgH / 2, bgWidth, bgH);
    }

    ctx.fillStyle = '#f1c40f'; // 金色
    ctx.shadowColor = 'rgba(0,0,0,0.8)';
    ctx.shadowBlur = 4 / camera.zoom;
    ctx.fillText(loc.name, loc.x, loc.y);
    ctx.shadowBlur = 0;
  });
}

function drawAnimatedSignalMarker(ctx, markerX, markerY, options = {}) {
  const now = options.now ?? Date.now();
  const coreRadius = options.coreRadius ?? 8;
  const ringRadius = options.ringRadius ?? 28;
  const label = options.label || '';
  const showLabel = !!options.showLabel;
  const font = options.font || 'bold 16px "Noto Serif SC", serif';
  const lineWidth = options.lineWidth ?? 2;
  const crosshairWidth = options.crosshairWidth ?? lineWidth;

  const waveA = (Math.sin(now / 260) + 1) / 2;
  const waveB = (Math.sin(now / 420 + 1.4) + 1) / 2;

  ctx.save();
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  ctx.beginPath();
  ctx.fillStyle = `rgba(192, 57, 43, ${0.10 + waveA * 0.14})`;
  ctx.arc(markerX, markerY, ringRadius * (1.45 + waveA * 0.35), 0, Math.PI * 2);
  ctx.fill();

  const ringConfigs = [
    { radius: ringRadius * (0.95 + waveA * 0.28), alpha: 0.95, width: lineWidth * 1.2 },
    { radius: ringRadius * (1.45 + waveB * 0.34), alpha: 0.52 - waveB * 0.16, width: lineWidth },
    { radius: ringRadius * (1.95 + waveA * 0.42), alpha: 0.28 - waveA * 0.1, width: lineWidth * 0.9 }
  ];

  for (const ring of ringConfigs) {
    if (ring.alpha <= 0) continue;
    ctx.beginPath();
    ctx.lineWidth = ring.width;
    ctx.strokeStyle = `rgba(192, 57, 43, ${ring.alpha})`;
    ctx.arc(markerX, markerY, ring.radius, 0, Math.PI * 2);
    ctx.stroke();
  }

  const crossGap = coreRadius * 1.7;
  const crossLen = ringRadius * 0.9 + waveA * ringRadius * 0.25;
  ctx.beginPath();
  ctx.lineWidth = crosshairWidth;
  ctx.strokeStyle = 'rgba(255, 248, 220, 0.95)';
  ctx.moveTo(markerX - crossLen, markerY);
  ctx.lineTo(markerX - crossGap, markerY);
  ctx.moveTo(markerX + crossGap, markerY);
  ctx.lineTo(markerX + crossLen, markerY);
  ctx.moveTo(markerX, markerY - crossLen);
  ctx.lineTo(markerX, markerY - crossGap);
  ctx.moveTo(markerX, markerY + crossGap);
  ctx.lineTo(markerX, markerY + crossLen);
  ctx.stroke();

  ctx.beginPath();
  ctx.fillStyle = '#c0392b';
  ctx.arc(markerX, markerY, coreRadius, 0, Math.PI * 2);
  ctx.fill();

  ctx.beginPath();
  ctx.fillStyle = 'rgba(255, 248, 220, 0.96)';
  ctx.arc(markerX, markerY, coreRadius * 0.38, 0, Math.PI * 2);
  ctx.fill();

  if (showLabel && label) {
    const labelY = markerY - ringRadius * 1.55;
    ctx.beginPath();
    ctx.moveTo(markerX, markerY - coreRadius - 4 * (lineWidth / 2));
    ctx.lineTo(markerX, labelY + ringRadius * 0.35);
    ctx.lineWidth = lineWidth;
    ctx.strokeStyle = 'rgba(192, 57, 43, 0.92)';
    ctx.stroke();

    ctx.font = font;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const textWidth = ctx.measureText(label).width;
    const boxWidth = textWidth + ringRadius * 0.9;
    const boxHeight = ringRadius * 0.95;

    ctx.fillStyle = 'rgba(26, 20, 16, 0.9)';
    if (ctx.roundRect) {
      ctx.beginPath();
      ctx.roundRect(markerX - boxWidth / 2, labelY - boxHeight / 2, boxWidth, boxHeight, ringRadius * 0.22);
      ctx.fill();
    } else {
      ctx.fillRect(markerX - boxWidth / 2, labelY - boxHeight / 2, boxWidth, boxHeight);
    }

    ctx.fillStyle = '#f7d794';
    ctx.fillText(label, markerX, labelY);
  }

  ctx.restore();
}

function drawDialogueLocationMarker(ctx) {
  if (!activeDialogueContext || !activeDialogueContext.matchedLocation || !mapData) return;

  const loc = activeDialogueContext.matchedLocation;
  const markerX = loc.x + mapData.tileWidth / 2;
  const markerY = loc.y + mapData.tileHeight / 2;
  const scaleUnit = 1 / camera.zoom;

  drawAnimatedSignalMarker(ctx, markerX, markerY, {
    now: Date.now(),
    coreRadius: 8 * scaleUnit,
    ringRadius: 32 * scaleUnit,
    lineWidth: 2.8 * scaleUnit,
    crosshairWidth: 2.4 * scaleUnit,
    label: activeDialogueContext.displayName || loc.name,
    showLabel: true,
    font: `bold ${16 * scaleUnit}px "Noto Serif SC", serif`
  });
}

function renderDialogueMiniMap(now = Date.now()) {
  const canvas = document.getElementById('dialogueMiniMapCanvas');
  if (!canvas) return;

  const cssWidth = Math.max(canvas.clientWidth || 0, 1);
  const cssHeight = Math.max(canvas.clientHeight || 0, 1);
  const dpr = window.devicePixelRatio || 1;

  if (canvas.width !== Math.round(cssWidth * dpr) || canvas.height !== Math.round(cssHeight * dpr)) {
    canvas.width = Math.round(cssWidth * dpr);
    canvas.height = Math.round(cssHeight * dpr);
  }

  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  ctx.fillStyle = '#efe4d2';
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  if (!mapData || !layerCanvases.length) return;

  const scale = Math.min(cssHeight / mapData.pixelWidth, cssWidth / mapData.pixelHeight);
  const drawWidth = mapData.pixelWidth * scale;
  const drawHeight = mapData.pixelHeight * scale;
  const drawX = (cssHeight - drawWidth) / 2;
  const drawY = (cssWidth - drawHeight) / 2;

  ctx.save();
  ctx.translate(0, cssHeight);
  ctx.rotate(-Math.PI / 2);

  for (const layerCanvas of layerCanvases) {
    ctx.drawImage(layerCanvas, 0, 0, mapData.pixelWidth, mapData.pixelHeight, drawX, drawY, drawWidth, drawHeight);
  }

  if (activeDialogueContext && activeDialogueContext.matchedLocation) {
    const loc = activeDialogueContext.matchedLocation;
    const markerX = drawX + loc.x * scale;
    const markerY = drawY + loc.y * scale;
    drawAnimatedSignalMarker(ctx, markerX, markerY, {
      now,
      coreRadius: 5.2,
      ringRadius: 16,
      lineWidth: 2,
      crosshairWidth: 1.8
    });
  }

  ctx.restore();
}

function drawTile(ctx, gid, x, y) {
  // 此函数在预渲染模式下不再被 renderLoop 频繁调用
  drawTileToCtx(ctx, gid, x, y);
}

// 获取 agent 的头顶世界坐标（用于连线）
function getAgentHeadPos(id) {
  const pos = agentScreenPositions[id];
  if (!pos) return null;
  const tileH = mapData ? mapData.tileHeight : 32;
  const tileW = mapData ? mapData.tileWidth : 32;
  return {
    x: pos.worldX + tileW / 2,
    y: pos.worldY + tileH - tileH * 2, // 头顶（sprite 高度约 2 格）
  };
}

// 将长文本按最大宽度换行（canvas 用）
function wrapText(ctx, text, maxWidth) {
  const words = text.split('');
  const lines = [];
  let line = '';
  for (const ch of words) {
    const test = line + ch;
    if (ctx.measureText(test).width > maxWidth && line.length > 0) {
      lines.push(line);
      line = ch;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  return lines;
}

// 绘制所有事件气泡
function drawEventBubbles(ctx) {
  if (!eventBubbles.length || !mapData) return;

  const tileW = mapData.tileWidth;
  const tileH = mapData.tileHeight;
  const fontSize = Math.max(11, 13 / camera.zoom);
  const padding = 10 / camera.zoom;
  const maxBubbleW = 160 / camera.zoom;
  const lineH = fontSize * 1.4;
  const cornerR = 6 / camera.zoom;

  ctx.save();
  ctx.font = `${fontSize}px "ZCOOL XiaoWei", "Noto Serif SC", serif`;

  for (const bubble of eventBubbles) {
    const [idA, idB] = bubble.participants;
    const posA = agentScreenPositions[idA];
    const posB = agentScreenPositions[idB];

    // 至少有一个参与者在屏幕上才绘制
    const anchorA = posA ? { x: posA.worldX + tileW / 2, y: posA.worldY + tileH - tileH * 2 } : null;
    const anchorB = posB ? { x: posB.worldX + tileW / 2, y: posB.worldY + tileH - tileH * 2 } : null;
    if (!anchorA && !anchorB) continue;

    // 气泡中心 = 两个参与者的中点（若只有一个则偏移）
    let cx, cy;
    if (anchorA && anchorB) {
      cx = (anchorA.x + anchorB.x) / 2;
      cy = (anchorA.y + anchorB.y) / 2 - 40 / camera.zoom;
    } else {
      const anchor = anchorA || anchorB;
      cx = anchor.x;
      cy = anchor.y - 40 / camera.zoom;
    }

    // 截断文字，最多12字
    const displayText = bubble.text.length > 12 ? bubble.text.slice(0, 12) + '…' : bubble.text;

    // 换行文本
    const lines = wrapText(ctx, displayText, maxBubbleW - padding * 2);
    const bubbleW = maxBubbleW;
    const bubbleH = lines.length * lineH + padding * 2;
    const bx = cx - bubbleW / 2;
    const by = cy - bubbleH / 2;

    // 连线：从气泡底部到各参与者头顶
    ctx.strokeStyle = 'rgba(200,180,120,0.55)';
    ctx.lineWidth = 1.2 / camera.zoom;
    ctx.setLineDash([4 / camera.zoom, 3 / camera.zoom]);
    const bubbleBottomX = cx;
    const bubbleBottomY = by + bubbleH;
    if (anchorA) {
      ctx.beginPath();
      ctx.moveTo(bubbleBottomX, bubbleBottomY);
      ctx.lineTo(anchorA.x, anchorA.y);
      ctx.stroke();
    }
    if (anchorB) {
      ctx.beginPath();
      ctx.moveTo(bubbleBottomX, bubbleBottomY);
      ctx.lineTo(anchorB.x, anchorB.y);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    // 气泡背景（圆角矩形）
    ctx.beginPath();
    ctx.moveTo(bx + cornerR, by);
    ctx.lineTo(bx + bubbleW - cornerR, by);
    ctx.arcTo(bx + bubbleW, by, bx + bubbleW, by + cornerR, cornerR);
    ctx.lineTo(bx + bubbleW, by + bubbleH - cornerR);
    ctx.arcTo(bx + bubbleW, by + bubbleH, bx + bubbleW - cornerR, by + bubbleH, cornerR);
    ctx.lineTo(bx + cornerR, by + bubbleH);
    ctx.arcTo(bx, by + bubbleH, bx, by + bubbleH - cornerR, cornerR);
    ctx.lineTo(bx, by + cornerR);
    ctx.arcTo(bx, by, bx + cornerR, by, cornerR);
    ctx.closePath();

    ctx.fillStyle = bubble.hasDialogue ? 'rgba(30, 20, 10, 0.82)' : 'rgba(60, 55, 45, 0.82)';
    ctx.shadowColor = 'rgba(0,0,0,0.5)';
    ctx.shadowBlur = 8 / camera.zoom;
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = bubble.hasDialogue ? 'rgba(200,170,90,0.7)' : 'rgba(160,155,140,0.7)';
    ctx.lineWidth = 1 / camera.zoom;
    ctx.stroke();

    // 记录气泡世界坐标，供点击检测
    bubble._rect = { bx, by, bw: bubbleW, bh: bubbleH };

    // 文字
    ctx.fillStyle = bubble.hasDialogue ? 'rgba(240,220,170,0.95)' : 'rgba(190,185,175,0.95)';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    lines.forEach((line, i) => {
      ctx.fillText(line, cx, by + padding + i * lineH);
    });
    ctx.textBaseline = 'alphabetic';
  }

  ctx.restore();
}

function drawDialogueReplayScene(ctx, replay, now = Date.now()) {
  if (!replay || !mapData || !replay.entries.length) return;

  if (now - replay.lastSwitchAt >= replay.intervalMs) {
    replay.currentIndex = (replay.currentIndex + 1) % replay.entries.length;
    replay.lastSwitchAt = now;
  }

  const entry = replay.entries[replay.currentIndex];
  if (!entry) return;

  const tileW = mapData.tileWidth;
  const tileH = mapData.tileHeight;
  const fontSize = Math.max(11, 14 / camera.zoom);
  const nameSize = Math.max(10, 12 / camera.zoom);
  const paddingX = 14 / camera.zoom;
  const paddingY = 12 / camera.zoom;
  const maxBubbleW = 220 / camera.zoom;
  const lineH = fontSize * 1.35;
  const cornerR = 10 / camera.zoom;
  const pulse = (Math.sin(now / 260) + 1) / 2;

  let anchor = null;
  if (entry.speakerId && agentScreenPositions[entry.speakerId]) {
    const pos = agentScreenPositions[entry.speakerId];
    anchor = { x: pos.worldX + tileW / 2, y: pos.worldY + tileH - tileH * 2 };
  }

  if (!anchor && replay.participantIds.length) {
    const anchors = replay.participantIds
      .map(id => agentScreenPositions[id])
      .filter(Boolean)
      .map(pos => ({ x: pos.worldX + tileW / 2, y: pos.worldY + tileH - tileH * 2 }));
    if (anchors.length === 1) {
      anchor = anchors[0];
    } else if (anchors.length > 1) {
      anchor = {
        x: anchors.reduce((sum, item) => sum + item.x, 0) / anchors.length,
        y: anchors.reduce((sum, item) => sum + item.y, 0) / anchors.length
      };
    }
  }

  if (!anchor) return;

  const displayText = entry.text.length > 28 ? entry.text.slice(0, 28) + '…' : entry.text;

  ctx.save();
  ctx.font = `${fontSize}px "ZCOOL XiaoWei", "Noto Serif SC", serif`;
  const lines = wrapText(ctx, displayText, maxBubbleW - paddingX * 2);
  ctx.font = `bold ${nameSize}px "Noto Serif SC", serif`;
  const speakerLabel = entry.speaker || '对话';
  const speakerWidth = ctx.measureText(speakerLabel).width;
  ctx.font = `${fontSize}px "ZCOOL XiaoWei", "Noto Serif SC", serif`;

  const contentWidth = Math.max(
    ...lines.map(line => ctx.measureText(line).width),
    speakerWidth + 28 / camera.zoom
  );
  const bubbleW = Math.min(maxBubbleW, contentWidth + paddingX * 2);
  const bubbleH = paddingY * 2 + lines.length * lineH + nameSize + 12 / camera.zoom;
  const bx = anchor.x - bubbleW / 2;
  const by = anchor.y - bubbleH - 52 / camera.zoom;
  const tailX = anchor.x;
  const tailTopY = by + bubbleH - 2 / camera.zoom;
  const tailTipY = anchor.y - 8 / camera.zoom;

  ctx.beginPath();
  ctx.moveTo(tailX - 10 / camera.zoom, tailTopY);
  ctx.lineTo(tailX, tailTipY);
  ctx.lineTo(tailX + 10 / camera.zoom, tailTopY);
  ctx.closePath();
  ctx.fillStyle = 'rgba(36, 22, 12, 0.9)';
  ctx.fill();

  ctx.beginPath();
  ctx.moveTo(bx + cornerR, by);
  ctx.lineTo(bx + bubbleW - cornerR, by);
  ctx.arcTo(bx + bubbleW, by, bx + bubbleW, by + cornerR, cornerR);
  ctx.lineTo(bx + bubbleW, by + bubbleH - cornerR);
  ctx.arcTo(bx + bubbleW, by + bubbleH, bx + bubbleW - cornerR, by + bubbleH, cornerR);
  ctx.lineTo(bx + cornerR, by + bubbleH);
  ctx.arcTo(bx, by + bubbleH, bx, by + bubbleH - cornerR, cornerR);
  ctx.lineTo(bx, by + cornerR);
  ctx.arcTo(bx, by, bx + cornerR, by, cornerR);
  ctx.closePath();
  ctx.fillStyle = 'rgba(36, 22, 12, 0.9)';
  ctx.shadowColor = 'rgba(0,0,0,0.42)';
  ctx.shadowBlur = 16 / camera.zoom;
  ctx.fill();
  ctx.shadowBlur = 0;

  ctx.strokeStyle = `rgba(210, 168, 84, ${0.75 + pulse * 0.2})`;
  ctx.lineWidth = 1.4 / camera.zoom;
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(bx + 12 / camera.zoom, by + 26 / camera.zoom);
  ctx.lineTo(bx + bubbleW - 12 / camera.zoom, by + 26 / camera.zoom);
  ctx.strokeStyle = 'rgba(210, 168, 84, 0.34)';
  ctx.lineWidth = 1 / camera.zoom;
  ctx.stroke();

  ctx.font = `bold ${nameSize}px "Noto Serif SC", serif`;
  ctx.fillStyle = '#f7d794';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(speakerLabel, anchor.x, by + 8 / camera.zoom);

  ctx.font = `${fontSize}px "ZCOOL XiaoWei", "Noto Serif SC", serif`;
  ctx.fillStyle = 'rgba(255, 244, 220, 0.97)';
  lines.forEach((line, i) => {
    ctx.fillText(line, anchor.x, by + 18 / camera.zoom + nameSize + i * lineH);
  });

  ctx.beginPath();
  ctx.arc(anchor.x, anchor.y - 2 / camera.zoom, (9 + pulse * 3) / camera.zoom, 0, Math.PI * 2);
  ctx.fillStyle = `rgba(255, 210, 120, ${0.08 + pulse * 0.08})`;
  ctx.fill();
  ctx.restore();
}

function drawDialogueReplayBubble(ctx, now = Date.now()) {
  if (!activeDialogueReplay || !mapData || !Array.isArray(activeDialogueReplay.scenes)) return;

  for (const scene of activeDialogueReplay.scenes) {
    drawDialogueReplayScene(ctx, scene, now);
  }
}

// 将鼠标事件坐标转换为世界坐标
function screenToWorld(e, canvas) {
  const rect = canvas.getBoundingClientRect();
  const sx = e.clientX - rect.left;
  const sy = e.clientY - rect.top;
  const worldX = (sx - canvas.width / 2) / camera.zoom + camera.x;
  const worldY = (sy - canvas.height / 2) / camera.zoom + camera.y;
  return { worldX, worldY };
}

// canvas 点击：检测是否点中某个 agent（人物区域或感叹号）
function handleCanvasClick(e, canvas) {
  const { worldX, worldY } = screenToWorld(e, canvas);
  const tileW = mapData ? mapData.tileWidth : 32;
  const tileH = mapData ? mapData.tileHeight : 32;

  // 先检测气泡点击
  for (const bubble of eventBubbles) {
    const r = bubble._rect;
    if (!r || !bubble.hasDialogue) continue;
    if (worldX >= r.bx && worldX <= r.bx + r.bw && worldY >= r.by && worldY <= r.by + r.bh) {
      openBubbleModal(bubble);
      return;
    }
  }

  const hitRadius = tileH * 1.5;

  let hitId = null;
  let hitDist = Infinity;
  for (const [id, pos] of Object.entries(agentScreenPositions)) {
    const cx = pos.worldX + tileW / 2;
    const cy = pos.worldY + tileH / 2;
    const dist = Math.hypot(worldX - cx, worldY - cy);
    if (dist < hitRadius && dist < hitDist) {
      hitDist = dist;
      hitId = id;
    }
  }
  if (hitId) {
    selectAgent(hitId);
  }
}

function drawAgentOnMap(ctx, id, x, y, facingLeft = false, isNpc = false) {
  let name, sprite, isActive;

  if (isNpc) {
    name = '小厮';
    sprite = agentSprites['小厮'];
    isActive = true;
  } else {
    name = formatAgentName(id);
    // 优先使用自定义头像
    const customAvatar = customAgentAvatars[id];
    if (customAvatar && customAvatar.type === 'custom') {
      // 如果是自定义头像，使用缓存的图片
      sprite = agentSprites[id];
      if (!sprite) {
        sprite = new Image();
        sprite.src = customAvatar.source;
        agentSprites[id] = sprite;
      }
    } else {
      sprite = agentSprites[name];
    }
    isActive = agentsData[id] && agentsData[id].is_active !== false;
  }
  
  // 人物大小设定为约两格高 (mapData.tileHeight * 2)
  const targetHeight = mapData.tileHeight * 2;
  let drawW, drawH;

  if (sprite && sprite.complete && sprite.naturalWidth > 0) {
    // 保持原图宽高比
    const aspectRatio = sprite.naturalWidth / sprite.naturalHeight;
    drawH = targetHeight;
    drawW = targetHeight * aspectRatio;

    // 绘制人物 Sprite (底部对齐当前瓦片位置)
    const drawX = x + mapData.tileWidth / 2 - drawW / 2;
    const drawY = y + mapData.tileHeight - drawH;
    
    if (facingLeft) {
      ctx.save();
      // 移动原点到图片中心，水平翻转，再移回去
      ctx.translate(drawX + drawW / 2, drawY);
      ctx.scale(-1, 1);
      ctx.drawImage(sprite, -drawW / 2, 0, drawW, drawH);
      ctx.restore();
    } else {
      ctx.drawImage(sprite, drawX, drawY, drawW, drawH);
    }
    
    // 如果是当前选中的人物，加个醒目的高亮框
    if (selectedAgent === id) {
      ctx.strokeStyle = '#f1c40f';
      ctx.lineWidth = 3 / camera.zoom; // 线条粗细随缩放调整，保持视觉一致
      ctx.strokeRect(drawX - 2, drawY - 2, drawW + 4, drawH + 4);
    }
  } else {
    // 回退到绘制较大的彩色圆点
    ctx.beginPath();
    ctx.arc(x + mapData.tileWidth / 2, y + mapData.tileHeight / 2, 10, 0, Math.PI * 2);
    ctx.fillStyle = selectedAgent === id ? '#f1c40f' : (isActive ? '#e74c3c' : '#777');
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2 / camera.zoom;
    ctx.stroke();
  }

  // 绘制名字 (放在人物下方)
  if (!isNpc) {
  // 记录世界坐标，供点击检测使用
  agentScreenPositions[id] = { worldX: x, worldY: y };

  // 感叹号：新行动未读时显示在头顶
  if (agentsWithNewAction.has(id)) {
    const spriteTop = (sprite && sprite.complete && sprite.naturalWidth > 0)
      ? (y + mapData.tileHeight - targetHeight)
      : (y + mapData.tileHeight / 2 - 10);
    const cx = x + mapData.tileWidth / 2;
    const badgeR = Math.max(8, 10 / camera.zoom);
    const badgeY = spriteTop - badgeR - 4 / camera.zoom;

    ctx.save();
    // 圆形背景（白色，黑色描边）
    ctx.beginPath();
    ctx.arc(cx, badgeY, badgeR, 0, Math.PI * 2);
    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = 'rgba(0,0,0,0.35)';
    ctx.shadowBlur = 5 / camera.zoom;
    ctx.shadowOffsetY = 2 / camera.zoom;
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.shadowOffsetY = 0;
    ctx.strokeStyle = '#111';
    ctx.lineWidth = 1.5 / camera.zoom;
    ctx.stroke();
    // 感叹号文字（黑色）
    const excFontSize = Math.max(10, 12 / camera.zoom);
    ctx.font = `bold ${excFontSize}px sans-serif`;
    ctx.fillStyle = '#111';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('!', cx, badgeY);
    ctx.textBaseline = 'alphabetic';
    ctx.restore();
  }

  // 通过除以 camera.zoom，使字体在显示器上的物理大小保持不变
  const fontSize = Math.max(12, 14 / camera.zoom);
  ctx.font = `bold ${fontSize}px "ZCOOL XiaoWei"`;
  ctx.fillStyle = '#fff';
  ctx.textAlign = 'center';
  ctx.shadowColor = 'rgba(0,0,0,0.8)';
  ctx.shadowBlur = 4 / camera.zoom;

  // 名字位置根据实际绘制高度偏移
  const labelY = (sprite && sprite.complete) ? (y + mapData.tileHeight + 15 / camera.zoom) : (y + mapData.tileHeight + 25 / camera.zoom);
  ctx.fillText(name, x + mapData.tileWidth / 2, labelY);
  ctx.shadowBlur = 0;
  }
}

// ===== 边缘市民系统 =====
function spawnCitizen() {
  if (!mapData) return;
  if (citizens.length >= MAX_CITIZENS) return;

  const side = Math.random() < 0.5 ? 'left' : 'right';
  const col = side === 'left'
    ? Math.floor(Math.random() * 5)
    : mapData.width - 1 - Math.floor(Math.random() * 5);

  const goingDown = Math.random() < 0.5;
  const startRow = goingDown ? 0 : mapData.height - 1;
  const endRow = goingDown ? mapData.height - 1 : 0;

  const spriteName = citizenSpriteNames[Math.floor(Math.random() * citizenSpriteNames.length)];
  const speed = 0.8 + Math.random() * 0.8;

  citizens.push({
    id: `citizen_${Date.now()}_${Math.random()}`,
    spriteName,
    currentX: col * mapData.tileWidth,
    currentY: startRow * mapData.tileHeight,
    targetY: endRow * mapData.tileHeight,
    speed,
    facingLeft: Math.random() < 0.5,
    done: false
  });
}

function updateAndDrawCitizens(ctx, now) {
  if (now - lastCitizenSpawnTime > CITIZEN_SPAWN_INTERVAL) {
    lastCitizenSpawnTime = now;
    const count = Math.floor(Math.random() * 2) + 1;
    for (let i = 0; i < count; i++) spawnCitizen();
  }

  citizens = citizens.filter(c => !c.done);
  citizens.forEach(c => {
    const dy = c.targetY - c.currentY;
    const dist = Math.abs(dy);
    if (dist < 2) { c.done = true; return; }
    c.currentY += (dy > 0 ? 1 : -1) * Math.min(c.speed, dist);

    const vw = ctx.canvas.width / camera.zoom;
    const vh = ctx.canvas.height / camera.zoom;
    const viewLeft = camera.x - vw / 2;
    const viewTop = camera.y - vh / 2;
    if (c.currentX < viewLeft - 100 || c.currentX > viewLeft + vw + 100 ||
        c.currentY < viewTop - 100 || c.currentY > viewTop + vh + 100) return;

    const sprite = agentSprites[c.spriteName];
    const targetHeight = mapData.tileHeight * 2;
    if (sprite && sprite.complete && sprite.naturalWidth > 0) {
      const drawH = targetHeight;
      const drawW = drawH * (sprite.naturalWidth / sprite.naturalHeight);
      const drawX = c.currentX + mapData.tileWidth / 2 - drawW / 2;
      const drawY = c.currentY + mapData.tileHeight - drawH;
      if (c.facingLeft) {
        ctx.save();
        ctx.translate(drawX + drawW / 2, drawY);
        ctx.scale(-1, 1);
        ctx.drawImage(sprite, -drawW / 2, 0, drawW, drawH);
        ctx.restore();
      } else {
        ctx.drawImage(sprite, drawX, drawY, drawW, drawH);
      }
    } else {
      ctx.beginPath();
      ctx.arc(c.currentX + mapData.tileWidth / 2, c.currentY + mapData.tileHeight / 2, 8, 0, Math.PI * 2);
      ctx.fillStyle = '#aaa';
      ctx.fill();
    }
  });
}

// ===== Settings Modal =====
document.addEventListener('DOMContentLoaded', () => {
  // Show settings modal on startup if tick is 0 (Disabled to prevent auto-popup)
  // if (currentTick <= 0) {
  //   setTimeout(openSettingsModal, 500);
  // }
  initPlayerCharacter();
});

// 保存弹窗打开时的初始配置状态
let initialConfigState = null;

async function openSettingsModal() {
  document.getElementById('settingsModal').style.display = 'block';
  try {
    const res = await fetch('http://localhost:8001/api/config/model');
    if (res.ok) {
      const config = await res.json();
      const base_url = config.base_url || '';
      const api_key = config.api_key || '';
      const model = config.model || '';
      
      document.getElementById('settingsBaseUrl').value = base_url;
      document.getElementById('settingsApiKey').value = api_key;
      document.getElementById('settingsModel').value = model;
      
      const ttsApiKey = localStorage.getItem('dashscope_tts_api_key') || '';
      document.getElementById('settingsTtsApiKey').value = ttsApiKey;

      // 记录初始状态以便比较
      initialConfigState = { base_url, api_key, model, ttsApiKey };
    }
  } catch (e) {
    console.error('Failed to fetch settings:', e);
  }
}

function closeSettingsModal() {
  document.getElementById('settingsModal').style.display = 'none';
  initialConfigState = null;
}

async function saveSettings() {
  const baseUrl = document.getElementById('settingsBaseUrl').value.trim();
  const apiKey = document.getElementById('settingsApiKey').value.trim();
  const model = document.getElementById('settingsModel').value.trim();
  const ttsApiKey = document.getElementById('settingsTtsApiKey').value.trim();

  // 检查是否发生变化
  const hasChanges = !initialConfigState || 
                     initialConfigState.base_url !== baseUrl || 
                     initialConfigState.api_key !== apiKey || 
                     initialConfigState.model !== model ||
                     initialConfigState.ttsApiKey !== ttsApiKey;

  // 如果没有修改配置，直接关闭弹窗即可，避免重启后端
  if (!hasChanges) {
    closeSettingsModal();
    return;
  }

  // 立即保存前端特有配置
  localStorage.setItem('dashscope_tts_api_key', ttsApiKey);

  // 检查后端相关配置是否发生变化
  const hasBackendChanges = !initialConfigState || 
                     initialConfigState.base_url !== baseUrl || 
                     initialConfigState.api_key !== apiKey || 
                     initialConfigState.model !== model;

  if (!hasBackendChanges) {
    // 只有前端配置发生变化，不需要重启后端
    alert(t('save_settings_success') || '保存成功！');
    closeSettingsModal();
    return;
  }

  if (!apiKey) {
    alert(t('error_no_api_key') || '请填写 API Key');
    return;
  }

  // 发生变化时，提示用户修改配置会导致系统重启
  if (!confirm(t('confirm_save_settings') || '修改模型配置将会重启后端服务，当前进度可能会中断。确定要保存并重启吗？')) {
    return;
  }

  try {
    const res = await fetch('http://localhost:8001/api/config/model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, model: model })
    });
    if (res.ok) {
      alert(t('save_settings_success') || '保存成功！后端正在自动重启以应用新配置，请稍候。');
      isReconnectingAfterRestart = true;
      closeSettingsModal();
    } else {
      alert((t('save_settings_error') || '保存失败：') + (await res.text()));
    }
  } catch (e) {
    console.error('Failed to save settings:', e);
    alert(t('save_settings_network_error') || '保存失败，请检查网络连接');
  }
}

// Ensure settings modal closes when clicking outside
window.addEventListener('click', (event) => {
  const settingsModal = document.getElementById('settingsModal');
  if (event.target === settingsModal) {
    closeSettingsModal();
  }
});

// ===== Reset Simulation =====
async function confirmReset() {
  if (confirm('警告：您即将重置推演。\n\n这将会删除所有人物的记忆、计划和状态，并重启后端服务。\n您确定要继续吗？')) {
    try {
      const res = await fetch('http://localhost:8001/api/reset', {
        method: 'POST',
      });
      if (res.ok) {
        alert('重置指令已发送！后端正在清理数据并自动重启，请稍候。');
        isReconnectingAfterRestart = true;
      } else {
        alert('重置失败：' + (await res.text()));
      }
    } catch (e) {
      console.error('Failed to reset simulation:', e);
      alert('重置请求发送失败，请检查网络连接');
    }
  }
}

async function returnToMainMenu() {
  if (!confirm('确认返回主菜单？\n当前剧情推演进度将重置。')) return;
  try {
    const res = await fetch('http://localhost:8001/story/game_restart', { method: 'POST' });
    if (!res.ok) { alert('重置失败：' + (await res.text())); return; }
  } catch (e) {
    alert('重置请求发送失败，请检查网络连接');
    return;
  }
  clearTimeout(reconnectTimer);
  if (ws) { ws.onclose = null; ws.close(); ws = null; }
  window.location.href = 'http://localhost:8000/frontend/index.html';
}
window.returnToMainMenu = returnToMainMenu;

// ── 回溯树函数 ─────────────────────────────────────────────────────────────────

function toggleMemoryTree() {
  memoryTreeOpen = !memoryTreeOpen;
  const overlay = document.getElementById('memoryTreeOverlay');
  if (overlay) overlay.style.display = memoryTreeOpen ? 'flex' : 'none';
  if (memoryTreeOpen) {
    renderBranchTree();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'get_branch_tree' }));
    }
  }
}

function handleMemoryTreeOverlayClick(event) {
  if (event.target === document.getElementById('memoryTreeOverlay')) {
    toggleMemoryTree();
  }
}

function exitHistoryView() {
  isViewingHistory = false;
  viewingTick = -1;
  viewingBranchId = -1;
  // Notify backend to clear _viewing_tick so next Start Simulation continues
  // the current branch rather than forking from the previously viewed tick.
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'reset_view' }));
  }
  updateHistoryModeBanner();
  if (tickHistory.length > 0) {
    applyHistoryTick(tickHistory[tickHistory.length - 1]);
  }
  renderBranchTree();
}

function applyAgentsData(data, tick) {
  applyHistoryTick({ tick, data });
}

function updateHistoryModeBanner() {
  const banner = document.getElementById('historyModeBanner');
  const bannerText = document.getElementById('historyModeBannerText');
  const innerBanner = document.getElementById('historyViewBanner');
  const innerText = document.getElementById('historyViewText');
  if (!banner) return;
  if (isViewingHistory && viewingTick !== -1) {
    banner.style.display = 'flex';
    // Compute the frontier tick of the viewed branch to determine what Start will do.
    const currentBranch = branchTree.find(b => b.id === currentBranchId);
    const lastTickOfCurrentBranch = currentBranch && currentBranch.ticks.length > 0
      ? Math.max(...currentBranch.ticks) : -1;
    const viewedBranch = branchTree.find(b => b.id === viewingBranchId);
    const lastTickOfViewedBranch = viewedBranch && viewedBranch.ticks.length > 0
      ? Math.max(...viewedBranch.ticks) : -1;
    const isAtCurrentFrontier = viewingBranchId === currentBranchId
      && viewingTick === lastTickOfCurrentBranch;
    const isAtOtherFrontier = viewingBranchId !== currentBranchId
      && viewingTick === lastTickOfViewedBranch;
    const msg = isAtCurrentFrontier
      ? `⏩ 正在查看 Tick ${viewingTick} · 点击"开始推演"将在此时间线继续`
      : isAtOtherFrontier
        ? `↩ 正在查看 Tick ${viewingTick} · 点击"开始推演"将切换至此时间线并继续`
        : `⏪ 正在查看 Tick ${viewingTick} · 点击"开始推演"将从此处创建新分支`;
    if (bannerText) bannerText.textContent = msg;
    if (innerBanner) innerBanner.style.display = 'flex';
    if (innerText) innerText.textContent = `正在查看 Tick ${viewingTick}`;
  } else {
    banner.style.display = 'none';
    if (innerBanner) innerBanner.style.display = 'none';
  }
}

function renderBranchTree() {
  const svg = document.getElementById('branchTreeSvg');
  if (!svg) return;
  if (!branchTree || branchTree.length === 0) {
    svg.innerHTML = '<text x="10" y="30" fill="#555" font-size="12">暂无数据</text>';
    return;
  }

  const NODE_R = 10;
  const H_GAP = 64;
  const V_GAP = 56;
  const PAD_X = 40;
  const PAD_Y = 36;

  const allTicks = [...new Set(branchTree.flatMap(b => b.ticks || []))].sort((a, b) => a - b);
  if (allTicks.length === 0) {
    svg.innerHTML = '<text x="10" y="30" fill="#555" font-size="12">暂无数据</text>';
    return;
  }

  const tickToX = {};
  allTicks.forEach((t, i) => { tickToX[t] = PAD_X + i * H_GAP; });

  const branchToY = {};
  branchTree.forEach((b, i) => { branchToY[b.id] = PAD_Y + i * V_GAP; });

  const svgWidth = PAD_X * 2 + (allTicks.length - 1) * H_GAP;
  const svgHeight = PAD_Y * 2 + (branchTree.length - 1) * V_GAP;
  svg.setAttribute('viewBox', `0 0 ${svgWidth} ${svgHeight}`);
  svg.setAttribute('height', Math.max(svgHeight, 80));

  let html = '';

  branchTree.forEach(branch => {
    const color = BRANCH_COLORS[branch.id % BRANCH_COLORS.length];
    const ticks = (branch.ticks || []).slice().sort((a, b) => a - b);
    const y = branchToY[branch.id];

    if (branch.parent_branch_id !== null && branch.parent_branch_id !== undefined && ticks.length > 0) {
      const parentY = branchToY[branch.parent_branch_id];
      const forkX = tickToX[branch.fork_tick] ?? PAD_X;
      const firstX = tickToX[ticks[0]] ?? forkX;
      html += `<line x1="${forkX}" y1="${parentY}" x2="${firstX}" y2="${y}" stroke="${color}" stroke-width="2" opacity="0.7"/>`;
    }

    if (ticks.length > 1) {
      const x1 = tickToX[ticks[0]];
      const x2 = tickToX[ticks[ticks.length - 1]];
      html += `<line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" stroke="${color}" stroke-width="2"/>`;
    }
  });

  branchTree.forEach(branch => {
    const color = BRANCH_COLORS[branch.id % BRANCH_COLORS.length];
    const ticks = (branch.ticks || []).slice().sort((a, b) => a - b);
    const y = branchToY[branch.id];

    const currentBranch = branchTree.find(b => b.id === currentBranchId);
    const lastTickOfCurrentBranch = currentBranch ? Math.max(...(currentBranch.ticks.length ? currentBranch.ticks : [0])) : -1;

    ticks.forEach(tick => {
      const x = tickToX[tick];
      const isViewing = isViewingHistory && tick === viewingTick && branch.id === viewingBranchId;
      const isLiveCurrentTick = branch.id === currentBranchId && tick === lastTickOfCurrentBranch && !isViewingHistory;

      if (isViewing) {
        html += `<circle cx="${x}" cy="${y}" r="${NODE_R + 5}" fill="none" stroke="#a0a0ff" stroke-width="2" stroke-dasharray="4 2" pointer-events="none"/>`;
      }
      if (isLiveCurrentTick) {
        html += `<circle cx="${x}" cy="${y}" r="${NODE_R + 4}" fill="none" stroke="#e94560" stroke-width="2" stroke-dasharray="3 2" opacity="0.8" pointer-events="none"/>`;
      }

      const nodeStroke = isLiveCurrentTick ? '#fff' : 'rgba(255,255,255,0.4)';
      const nodeStrokeW = isLiveCurrentTick ? 2 : 1;
      const nodeFill = isLiveCurrentTick ? '#e94560' : color;
      html += `<circle cx="${x}" cy="${y}" r="${NODE_R}" fill="${nodeFill}" stroke="${nodeStroke}" stroke-width="${nodeStrokeW}" pointer-events="none"/>`;
      html += `<text x="${x}" y="${y + NODE_R + 14}" text-anchor="middle" fill="${color}" font-size="10" pointer-events="none">T${tick}</text>`;
      html += `<circle cx="${x}" cy="${y + 8}" r="${NODE_R + 14}" fill="transparent" style="cursor:pointer" data-bid="${branch.id}" data-t="${tick}"/>`;
    });
  });

  branchTree.forEach(branch => {
    const color = BRANCH_COLORS[branch.id % BRANCH_COLORS.length];
    const ticks = branch.ticks || [];
    if (ticks.length === 0) return;
    const lastTick = Math.max(...ticks);
    const x = tickToX[lastTick] + NODE_R + 8;
    const y = branchToY[branch.id];
    html += `<text x="${x}" y="${y + 4}" fill="${color}" font-size="9" opacity="0.7" pointer-events="none">时间线${branch.id + 1}</text>`;
  });

  svg.innerHTML = html;

  svg.querySelectorAll('[data-bid]').forEach(function(el) {
    el.addEventListener('click', function(e) {
      e.stopPropagation();
      onClickTreeNode(
        parseInt(el.getAttribute('data-bid')),
        parseInt(el.getAttribute('data-t'))
      );
    });
  });

  renderBranchLegend();
}

function onClickTreeNode(branchId, tick) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.warn('回溯树：WS 未连接');
    return;
  }
  console.log('回溯树：跳转到 branch=' + branchId + ' tick=' + tick);
  ws.send(JSON.stringify({ type: 'view_tick', tick: tick, branch_id: branchId }));
  if (memoryTreeOpen) toggleMemoryTree();
}

function renderBranchLegend() {
  const legend = document.getElementById('branchLegend');
  if (!legend || !branchTree) return;
  legend.innerHTML = branchTree.map(branch => {
    const color = BRANCH_COLORS[branch.id % BRANCH_COLORS.length];
    const label = `时间线${branch.id + 1}`;
    const active = branch.id === currentBranchId ? ' (当前)' : '';
    return `<div class="branch-legend-item">
      <div class="branch-legend-dot" style="background:${color}"></div>
      <span>${label}${active}</span>
    </div>`;
  }).join('');
}
