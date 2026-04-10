/* ===== OpenStory · app.js (English Version + Latest Features Merged) ===== */

const WS_URL = 'ws://localhost:8000/ws';
const HOURS_DISPLAY = ['23:00', '01:00', '03:00', '05:00', '07:00', '09:00', '11:00', '13:00', '15:00', '17:00', '19:00', '21:00'];

// ==========================================
// 🌟 GLOBAL DISPLAY TRANSLATOR DICTIONARIES 🌟
// ==========================================
const EN_NAMES = {
  '贾宝玉': 'Jia Baoyu', '林黛玉': 'Lin Daiyu', '薛宝钗': 'Xue Baochai', '史湘云': 'Shi Xiangyun',
  '王熙凤': 'Wang Xifeng', '贾母': 'Grandmother Jia', '王夫人': 'Lady Wang', '贾探春': 'Jia Tanchun',
  '妙玉': 'Miaoyu', '晴雯': 'Qingwen', '袭人': 'Xiren', '贾政': 'Jia Zheng', '贾迎春': 'Jia Yingchun',
  '贾惜春': 'Jia Xichun', '李纨': 'Li Wan', '贾琏': 'Jia Lian', '薛蟠': 'Xue Pan',
  '薛姨妈': 'Aunt Xue', '贾珍': 'Jia Zhen', '贾蓉': 'Jia Rong', '尤氏': 'Lady You',
  '贾元春': 'Jia Yuanchun', '赵姨娘': 'Concubine Zhao', '贾环': 'Jia Huan',
  '彩云': 'Caiyun', '彩霞': 'Caixia', '金钏': 'Jinchuan', '玉钏': 'Yuchuan',
  '司棋': 'Siqi', '侍书': 'Shishu', '入画': 'Ruhua', '翠缕': 'Cuilv', '小红': 'Xiaohong',
  '雪雁': 'Xueyan', '秋纹': 'Qiuwen', '碧痕': 'Bihen', '莺儿': 'Ying\'er', '香菱': 'Xiangling',
  '琥珀': 'Hupo', '素云': 'Suyun', '丰儿': 'Feng\'er', '平儿': 'Ping\'er', '鸳鸯': 'Yuanyang',
  '紫鹃': 'Zijuan', '麝月': 'Sheyue', '焦大': 'Jiao Da', '赖大': 'Lai Da', '周瑞': 'Zhou Rui',
  '林之孝': 'Lin Zhixiao', '小厮': 'Servant', '普通人': 'Commoner', '孙悟空': 'Monkey King'
};

const EN_LOCATIONS = {
  '怡红院': 'Yihong Court', '潇湘馆': 'Xiaoxiang Lodge', '蘅芜院': 'Hengwu Courtyard',
  '贾母院': 'Grandmother Jia\'s Court', '王夫人院': 'Lady Wang\'s Court', '王熙凤院': 'Wang Xifeng\'s Court',
  '稻香村': 'Daoxiang Village', '晓翠堂': 'Xiaocui Hall', '紫凌洲': 'Ziling Pavilion',
  '暖乡坞': 'Nuanxiang Studio', '达摩庵': 'Damo Shrine', '薛姨妈院': 'Aunt Xue\'s Court',
  '贾政内书房': 'Jia Zheng\'s Study', '贾政外书房': 'Jia Zheng\'s Outer Study', '宁国府正院': 'Ningguo Mansion', 
  '贾蓉院': 'Jia Rong\'s Court', '尤氏院': 'Lady You\'s Court', '顾恩思义殿': 'Gu\'en Siyi Hall', 
  '梨香院': 'Lixiang Court', '仆役群房': 'Servants\' Quarters', '周瑞院': 'Zhou Rui\'s Court',
  '大观园': 'Grand View Garden', '荣国府': 'Rongguo Mansion', '宁国府': 'Ningguo Mansion',
  '荣禧堂': 'Rongxi Hall', '荣禧堂后身': 'Rear of Rongxi', '贾赦外书房': 'Jia She\'s Outer Study',
  '贾赦院': 'Jia She\'s Court', '马棚': 'Stables', '体仁沐德院': 'Tiren Mude Court',
  '李纨院': 'Li Wan\'s Court', 
  '李奶妈 赵奶妈 张奶妈 王奶妈家': 'Nannies\' Quarters',
  '赵奶妈 张奶妈 王奶妈家': 'Nannies\' Quarters',
  '赵奶妈张奶妈王奶妈家': 'Nannies\' Quarters',
  '李奶妈家': 'Nanny Li\'s House', '赵奶妈家': 'Nanny Zhao\'s House', 
  '张奶妈家': 'Nanny Zhang\'s House', '王奶妈家': 'Nanny Wang\'s House',
  '宝玉外书房': 'Baoyu\'s Outer Study', '小书房': 'Small Study',
  '贾氏宗祠': 'Ancestral Hall', '丛绿堂': 'Conglv Hall', '会芳园': 'Huifang Garden', 
  '天香楼': 'Tianxiang Pavilion', '登仙阁': 'Dengxian Pavilion', '逗蜂轩': 'Doufeng Studio', 
  '玉皇庙': 'Yuhuang Temple', '清堂茅舍': 'Qingtang Cottage', '嘉荫堂': 'Jiayin Hall', 
  '凸碧山庄': 'Tubi Villa', '沁芳亭': 'Qinfang Pavilion', '滴翠亭': 'Dicui Pavilion', 
  '秋爽斋': 'Qiushuang Studio', '栊翠庵': 'Longcui Shrine', '凝曦轩': 'Ningxi Pavilion'
};

// 1. 中 -> 英 (显示用)
function t_name(cnName) {
  if (!cnName) return '';
  return EN_NAMES[cnName] || cnName;
}

function t_loc(cnLoc) {
  if (!cnLoc) return '';
  for (const [cn, en] of Object.entries(EN_LOCATIONS)) {
    if (cnLoc.includes(cn)) return en;
  }
  return cnLoc;
}

function t_text(str) {
  if (!str) return '';
  let res = str;
  for (const [cn, en] of Object.entries(EN_NAMES)) {
    res = res.replace(new RegExp(cn, 'g'), en);
  }
  for (const [cn, en] of Object.entries(EN_LOCATIONS)) {
    res = res.replace(new RegExp(cn, 'g'), en);
  }
  return res;
}

// 2. 英 -> 中 (输入发给后端用)
function t_rev_name(enName) {
  if (!enName) return '';
  const lowerEn = enName.toLowerCase();
  for (const [cn, en] of Object.entries(EN_NAMES)) {
    if (en.toLowerCase() === lowerEn) return cn;
  }
  return enName;
}

function t_rev_loc(enLoc) {
  if (!enLoc) return '';
  const lowerEn = enLoc.toLowerCase();
  for (const [cn, en] of Object.entries(EN_LOCATIONS)) {
    if (en.toLowerCase() === lowerEn) return cn;
  }
  return enLoc;
}
// ==========================================

let ws = null;
let reconnectTimer = null;
let agentsData = {};
let selectedAgent = null;
let currentTick = -1;
let viewDays = {}; 
let pendingTickData = null; 
let agentsWithNewAction = new Set(); 
let eventBubbles = []; 
let tickHistory = []; 
let currentHistoryIndex = -1; 

const OFFICIAL_PRESETS = {
  sunwukong: {
    name: 'Sun Wukong',
    isOfficial: true,
    avatarType: 'builtin',
    avatarSource: '../map/sprite/孙悟空.png',
    profile: {
      '家族': 'Flower Fruit Mountain',
      '性格': 'Rebellious, witty, fiercely loyal',
      '核心驱动': 'Seeking truth and freedom in the mortal realm',
      '语言风格': 'Direct, informal, and heroic',
      '背景经历': 'The Monkey King, teleported here by an anomaly.'
    },
    memory: ['Just arrived in the Grand View Garden. Quite a large place.']
  },
  putongren: {
    name: 'Commoner',
    isOfficial: true,
    avatarType: 'builtin',
    avatarSource: '../map/sprite/普通人.png',
    profile: {
      '家族': 'Commoner',
      '性格': 'Hardworking, cautious',
      '核心驱动': 'Survive and earn a living in the mansion',
      '语言风格': 'Humble and direct',
      '背景经历': 'A regular citizen working in the mansion.'
    },
    memory: ['The masters here have so many rules.']
  }
};

function getAllPresets() {
  const userPresets = loadUserPresets();
  return { ...OFFICIAL_PRESETS, ...userPresets };
}

function loadUserPresets() {
  try {
    const saved = localStorage.getItem('customAgentPresets_en');
    return saved ? JSON.parse(saved) : {};
  } catch (e) { return {}; }
}

function saveUserPresets(presets) {
  try {
    localStorage.setItem('customAgentPresets_en', JSON.stringify(presets));
    return true;
  } catch (e) { return false; }
}

let currentAvatar = { type: 'builtin', source: '../map/sprite/普通人.png', name: 'Commoner' };

function selectAvatar(type, source, name, clickedBtn) {
  currentAvatar = { type, source, name };
  document.getElementById('avatarType').value = type;
  document.getElementById('avatarSource').value = source;
  const previewImg = document.getElementById('selectedAvatarImg');
  previewImg.src = source;
  previewImg.alt = name;
  document.querySelectorAll('.avatar-option-btn').forEach(btn => btn.classList.remove('selected'));
  if (clickedBtn) clickedBtn.classList.add('selected');
}

function handleAvatarUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  if (!file.type.startsWith('image/')) { alert('Please select an image file'); return; }
  const reader = new FileReader();
  reader.onload = function(e) {
    const base64 = e.target.result;
    currentAvatar = { type: 'custom', source: base64, name: file.name.replace(/\.[^/.]+$/, '') };
    document.getElementById('avatarType').value = 'custom';
    document.getElementById('avatarSource').value = base64;
    const previewImg = document.getElementById('selectedAvatarImg');
    previewImg.src = base64;
    previewImg.alt = currentAvatar.name;
    document.querySelectorAll('.avatar-option-btn').forEach(btn => btn.classList.remove('selected'));
  };
  reader.readAsDataURL(file);
}

function renderPresetButtons() {
  const grid = document.getElementById('presetGrid');
  if (!grid) return;
  const presets = getAllPresets();
  grid.innerHTML = '';
  Object.entries(presets).forEach(([key, preset]) => {
    const isOfficial = preset.isOfficial;
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
    tagSpan.textContent = isOfficial ? 'Official' : 'Custom';
    wrapper.appendChild(img);
    wrapper.appendChild(nameSpan);
    wrapper.appendChild(tagSpan);
    if (!isOfficial) {
      const deleteBtn = document.createElement('button');
      deleteBtn.type = 'button';
      deleteBtn.className = 'preset-delete-btn';
      deleteBtn.textContent = '×';
      deleteBtn.addEventListener('click', function(e) { e.stopPropagation(); deletePreset(key); });
      wrapper.appendChild(deleteBtn);
    }
    wrapper.addEventListener('click', function() { selectPresetTemplate(key, wrapper); });
    grid.appendChild(wrapper);
  });
}

function selectPresetTemplate(templateKey, clickedBtn) {
  const presets = getAllPresets();
  const template = presets[templateKey];
  if (!template) return;
  document.getElementById('agentId').value = template.name;
  document.getElementById('profileFamily').value = template.profile['家族'] || '';
  document.getElementById('profilePersonality').value = template.profile['性格'] || '';
  document.getElementById('profileDrive').value = template.profile['核心驱动'] || '';
  document.getElementById('profileStyle').value = template.profile['语言风格'] || '';
  document.getElementById('profileBackground').value = template.profile['背景经历'] || '';
  document.getElementById('agentMemory').value = (template.memory || []).join('\n');
  if (template.avatarType && template.avatarSource) {
    currentAvatar = { type: template.avatarType, source: template.avatarSource, name: template.name };
    document.getElementById('avatarType').value = template.avatarType;
    document.getElementById('avatarSource').value = template.avatarSource;
    document.getElementById('selectedAvatarImg').src = template.avatarSource;
  }
  document.querySelectorAll('.preset-btn').forEach(btn => btn.classList.remove('selected'));
  if (clickedBtn) clickedBtn.classList.add('selected');
}

function saveAsPreset() {
  const name = document.getElementById('agentId').value.trim();
  if (!name) { alert('Please enter agent name first'); return; }
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
  const userPresets = loadUserPresets();
  const presetKey = 'custom_' + Date.now();
  let finalKey = presetKey;
  let counter = 1;
  while (userPresets[finalKey]) {
    finalKey = `custom_${Date.now()}_${counter}`;
    counter++;
  }
  userPresets[finalKey] = { name, isOfficial: false, avatarType: currentAvatar.type, avatarSource: currentAvatar.source, profile, memory, createdAt: Date.now() };
  if (saveUserPresets(userPresets)) { alert(`Preset "${name}" saved!`); renderPresetButtons(); } else { alert('Failed to save preset.'); }
}

function deletePreset(presetKey) {
  const presets = getAllPresets();
  const preset = presets[presetKey];
  if (preset && preset.isOfficial) { alert('Cannot delete official presets.'); return; }
  if (!confirm(`Are you sure you want to delete preset "${preset?.name || presetKey}"?`)) return;
  const userPresets = loadUserPresets();
  delete userPresets[presetKey];
  if (saveUserPresets(userPresets)) renderPresetButtons();
}

let isReconnectingAfterRestart = false;

function connect() {
  clearTimeout(reconnectTimer);
  setStatus('connecting');
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    setStatus('connected');
    if (isReconnectingAfterRestart) { isReconnectingAfterRestart = false; window.location.reload(); }
  };

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'snapshot' || msg.type === 'tick_update') {
        pendingTickData = msg;
        if (msg.tick && msg.tick > 0) {
          const settingsBtn = document.getElementById('settingsBtn');
          if (settingsBtn) settingsBtn.style.display = 'none';
        }
        document.getElementById('startTickBtn').disabled = true;
        document.getElementById('applyTickBtn').disabled = false;
      } else if (msg.type === 'add_agent_response') {
        handleAddAgentResponse(msg);
      } else if (msg.type === 'agent_added') {
        const newAgentData = msg.data;
        if (newAgentData && msg.agent_id) {
          agentsData[msg.agent_id] = newAgentData;
          if (msg.avatar) { customAgentAvatars[msg.agent_id] = msg.avatar; saveCustomAvatars(); }
          if (newAgentData.profile && newAgentData.profile.position && (newAgentData.profile.position[0] !== 0 || newAgentData.profile.position[1] !== 0)) {
            const startX = newAgentData.profile.position[0] * mapData.tileWidth;
            const startY = newAgentData.profile.position[1] * mapData.tileHeight;
            agentIdleStates[msg.agent_id] = { currentX: startX, currentY: startY, targetX: startX, targetY: startY, lastUpdate: Date.now(), nextMoveTime: Date.now() + Math.random() * 2000 };
          } else if (mapData) { assignRandomPositionToAgent(msg.agent_id); }
          const name = formatAgentName(msg.agent_id);
          const customAvatar = customAgentAvatars[msg.agent_id];
          if (customAvatar && customAvatar.type === 'custom') {
            if (!agentSprites[msg.agent_id]) { const img = new Image(); img.src = customAvatar.source; agentSprites[msg.agent_id] = img; }
          } else {
            if (!agentSprites[name]) { const img = new Image(); img.src = `../map/sprite/${name}.png`; agentSprites[name] = img; }
          }
          renderAgentList();
        }
      }
    } catch (err) { console.error('parse error', err); }
  };
  ws.onerror = () => setStatus('error');
  ws.onclose = () => { setStatus('error'); reconnectTimer = setTimeout(connect, 3000); };
}

let agentSprites = {}; 
let agentIdleStates = {}; 
let npcs = []; 
let agentScreenPositions = {}; 

function tickToEnglishDate(tick) {
  const HOURS_PER_TICK = 2;
  const START_YEAR = 1784;
  const totalHours = tick * HOURS_PER_TICK;
  const days = Math.floor(totalHours / 24);
  const hour = (totalHours % 24);
  const year = START_YEAR + Math.floor(days / 360);
  const dayOfYear = days % 360;
  const month = Math.floor(dayOfYear / 30) + 1;
  const day = (dayOfYear % 30) + 1;
  const period = hour >= 12 ? 'PM' : 'AM';
  let displayHour = hour % 12;
  if (displayHour === 0) displayHour = 12;
  // Use '|' so the overlay logic can split it perfectly into beautiful lines
  return `Year ${year} | M${month}-D${day} | ${displayHour}:00 ${period}`;
}

let citizens = []; 
let citizenSpriteNames = ['市民1', '市民2', '市民3', '市民4', '市民5'];
let lastCitizenSpawnTime = 0;
const CITIZEN_SPAWN_INTERVAL = 2000; 
const MAX_CITIZENS = 20; 

function mergeData(data) {
  if (!data) return;
  let needsReinit = false;
  const now = Date.now();

  for (const [id, d] of Object.entries(data)) {
    if (!agentsData[id]) needsReinit = true;
    if (agentsData[id] && agentsData[id].profile && agentsData[id].profile.position && 
        d.profile && d.profile.position && 
        (agentsData[id].profile.position[0] !== d.profile.position[0] || agentsData[id].profile.position[1] !== d.profile.position[1])) {
      if (agentIdleStates[id]) {
        agentIdleStates[id].currentX = d.profile.position[0] * mapData.tileWidth;
        agentIdleStates[id].currentY = d.profile.position[1] * mapData.tileHeight;
        agentIdleStates[id].targetX = agentIdleStates[id].currentX;
        agentIdleStates[id].targetY = agentIdleStates[id].currentY;
      }
    }

    const oldPosition = agentsData[id]?.profile?.position;
    agentsData[id] = d;
    if (d.profile && !d.profile.position && oldPosition) d.profile.position = oldPosition;

    const agentName = formatAgentName(id);
    const staticP = staticProfiles[agentName];
    if (staticP) {
      if (!d.profile) d.profile = {};
      for (const [k, v] of Object.entries(staticP)) { if (!d.profile[k]) d.profile[k] = v; }
    }

    if (!agentIdleStates[id] && d.profile && d.profile.position) {
      const startX = d.profile.position[0] * mapData.tileWidth;
      const startY = d.profile.position[1] * mapData.tileHeight;
      agentIdleStates[id] = { currentX: startX, currentY: startY, targetX: startX, targetY: startY, lastUpdate: now, nextMoveTime: now + Math.random() * 2000 };
    }

    const day = Math.floor((d.current_tick || 0) / 12) + 1;
    if (viewDays[id] === undefined) viewDays[id] = day;
    
    const name = formatAgentName(id);
    if (!agentSprites[name]) { const img = new Image(); img.src = `../map/sprite/${name}.png`; agentSprites[name] = img; }

    if (d.current_location && mapData && mapData.locations && agentIdleStates[id]) {
      const targetLocName = d.current_location;
      let matched = mapData.locations.find(l => l.name === targetLocName);
      if (!matched) matched = mapData.locations.find(l => l.name.includes(targetLocName) || targetLocName.includes(l.name));
      if (!matched && mapData.locations.length > 0) {
        let bestScore = 0;
        for (const loc of mapData.locations) {
          let score = 0;
          for (const ch of targetLocName) if (loc.name.includes(ch)) score++;
          if (score > bestScore) { bestScore = score; matched = loc; }
        }
      }
      if (matched && matched.tiles && matched.tiles.length > 0) {
        const state = agentIdleStates[id];
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
        state.movingToTarget = true;
        state.nextMoveTime = Infinity;
      }
    }
  }
  if (needsReinit && mapData) initializeAgentPositions();
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
    txt.textContent = 'Connected'; 
    if (Object.keys(agentsData).length === 0) list.innerHTML = '<div class="agent-placeholder">Connected. Waiting for data...</div>';
    if (startBtn && applyBtn) { const canApply = !!pendingTickData; startBtn.disabled = canApply; applyBtn.disabled = !canApply; }
    if (addAgentBtn) addAgentBtn.disabled = false;
    if (resetBtn) resetBtn.disabled = false;
    if (settingsBtn) settingsBtn.disabled = false;
    if (restartingOverlay) restartingOverlay.classList.remove('active');
  } else if (state === 'error') { 
    dot.classList.add('error'); 
    txt.textContent = 'Disconnected'; 
    if (startBtn) startBtn.disabled = true;
    if (applyBtn) applyBtn.disabled = true;
    if (addAgentBtn) addAgentBtn.disabled = true;
    if (resetBtn) resetBtn.disabled = true;
    if (settingsBtn) settingsBtn.disabled = true;
    if (restartingOverlay) restartingOverlay.classList.add('active');
  } else { 
    txt.textContent = 'Connecting...'; 
    if (startBtn) startBtn.disabled = true;
    if (applyBtn) applyBtn.disabled = true;
    if (addAgentBtn) addAgentBtn.disabled = true;
    if (resetBtn) resetBtn.disabled = true;
    if (settingsBtn) settingsBtn.disabled = true;
    if (restartingOverlay) restartingOverlay.classList.add('active');
  }
}

function sendStartTick() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    if (currentHistoryIndex !== -1 && currentHistoryIndex < tickHistory.length - 1) {
      currentHistoryIndex = tickHistory.length - 1;
      applyHistoryTick(tickHistory[currentHistoryIndex]);
    }
    ws.send(JSON.stringify({ type: 'start_tick' }));
    document.getElementById('startTickBtn').disabled = true;
    const applyBtn = document.getElementById('applyTickBtn');
    if (applyBtn) applyBtn.disabled = true;
    const txt = document.getElementById('statusText');
    if (txt) txt.textContent = 'Simulating...';
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
  if (msg.tick >= 0) document.getElementById('simDate').textContent = tickToEnglishDate(msg.tick);
  const historyData = JSON.parse(JSON.stringify(msg.data));
  mergeData(historyData);
  Object.keys(agentsData).forEach(id => agentsWithNewAction.add(id));
  buildEventBubbles();
  renderAgentList();
  if (selectedAgent && agentsData[selectedAgent]) renderDetail(selectedAgent);
  updateTickNavButtons();
}

function prevTick() {
  if (currentHistoryIndex > 0) { currentHistoryIndex--; applyHistoryTick(tickHistory[currentHistoryIndex]); }
}
function nextTick() {
  if (currentHistoryIndex < tickHistory.length - 1) { currentHistoryIndex++; applyHistoryTick(tickHistory[currentHistoryIndex]); }
}

function applyPendingTick() {
  if (!pendingTickData) return;
  const msg = pendingTickData;
  pendingTickData = null;
  const msgCopy = JSON.parse(JSON.stringify(msg));
  tickHistory.push(msgCopy);
  currentHistoryIndex = tickHistory.length - 1;
  updateTickNavButtons();

  const btn = document.getElementById('applyTickBtn');
  btn.disabled = true;
  document.getElementById('startTickBtn').disabled = false;

  const timeString = msg.tick >= 0 ? tickToEnglishDate(msg.tick) : null;
  const overlay = document.getElementById('timeTransitionOverlay');
  const textEl = document.getElementById('timeTransitionText');
  
  if (overlay && textEl && timeString) {
    // 👇 修改的地方在这里：使用带空格的坚杠切割，去除多余空格
    const parts = timeString.split(' | ');
    textEl.innerHTML = parts.join('<br/>');
    overlay.classList.add('active');
    setTimeout(() => {
      currentTick = msg.tick;
      document.getElementById('tickNum').textContent = msg.tick >= 0 ? msg.tick : '—';
      if (msg.tick >= 0) document.getElementById('simDate').textContent = timeString;
      mergeData(msg.data);
      Object.keys(agentsData).forEach(id => agentsWithNewAction.add(id));
      buildEventBubbles();
      renderAgentList();
      if (selectedAgent && agentsData[selectedAgent]) renderDetail(selectedAgent);
      setTimeout(() => {
        overlay.classList.remove('active');
        document.getElementById('startTickBtn').disabled = false;
        const applyBtn = document.getElementById('applyTickBtn');
        if (applyBtn) applyBtn.disabled = true;
      }, 1500);
    }, 800);
  } else {
    currentTick = msg.tick;
    document.getElementById('tickNum').textContent = msg.tick >= 0 ? msg.tick : '—';
    if (msg.tick >= 0) document.getElementById('simDate').textContent = timeString;
    mergeData(msg.data);
    Object.keys(agentsData).forEach(id => agentsWithNewAction.add(id));
    buildEventBubbles();
    renderAgentList();
    if (selectedAgent && agentsData[selectedAgent]) renderDetail(selectedAgent);
    document.getElementById('startTickBtn').disabled = false;
  }
}

function buildEventBubbles() {
  eventBubbles = [];
  const seen = new Set(); 
  for (const [id, d] of Object.entries(agentsData)) {
    const plan = d.current_plan;
    if (!Array.isArray(plan) || !plan[2] || plan[2] === '无' || plan[2] === 'None' || plan[2] === '自己') continue;
    const target = plan[2];
    const action = plan[0] || '';
    const rawText = d.current_action || action;
    if (!rawText) continue;
    const translatedText = t_text(rawText);

    const key = [id, target].sort().join('|');
    if (seen.has(key)) continue;
    seen.add(key);

    const mems = d.short_term_memory;
    const mem = mems && mems.length ? mems[mems.length - 1] : null;
    const hasDialogue = !!(mem && mem.tick !== null && d.dialogues && d.dialogues[mem.tick]);
    
    eventBubbles.push({ participants: [id, target], text: translatedText, agentId: id, hasDialogue, createdAt: performance.now() });
  }
}

function getAgentStatusText(id) {
  const d = agentsData[id];
  if (!d) return 'Wandering';
  if (d.occupied_by) {
    const who = formatAgentName(d.occupied_by.occupier || '');
    const act = d.occupied_by.action || '';
    if (act) return truncate(t_text(act), 16);
    return who ? `Chatting with ${t_name(who)}` : 'Busy';
  }
  if (Array.isArray(d.current_plan) && d.current_plan[0]) return truncate(t_text(d.current_plan[0]), 16);
  if (typeof d.current_plan === 'string' && d.current_plan) return truncate(t_text(d.current_plan), 16);
  
  const state = agentIdleStates[id];
  if (state && state.path && state.pathIndex < (state.path.length || 0)) {
    const tx = state.targetX / mapData.tileWidth;
    const ty = state.targetY / mapData.tileHeight;
    const tileIdx = Math.round(ty) * mapData.width + Math.round(tx);
    const loc = mapData.locations && mapData.locations.find(l => l.tiles && l.tiles.includes(tileIdx));
    return loc ? `Heading to ${t_loc(loc.name)}` : 'Moving';
  }
  return 'Wandering';
}

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
  const ids = Object.keys(agentsData);
  if (!ids.length) { list.innerHTML = '<div class="agent-placeholder">Waiting for data...</div>'; return; }

  list.innerHTML = '';
  ids.forEach(id => {
    const d = agentsData[id];
    const active = id === selectedAgent;
    const rawName = formatAgentName(id);
    const task = getAgentStatusText(id);
    const inactiveClass = d.is_active === false ? ' agent-inactive' : '';

    const card = document.createElement('div');
    card.className = `agent-card${active ? ' active' : ''}${inactiveClass}`;
    card.onclick = () => selectAgent(id);

    const avatar = document.createElement('img');
    avatar.className = 'agent-card-avatar';
    avatar.alt = t_name(rawName);
    avatar.onerror = () => {
      avatar.onerror = null;
      avatar.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"%3E%3Cpath fill="%23888" d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/%3E%3C/svg%3E';
    };

    const customAvatar = customAgentAvatars[id];
    if (customAvatar && customAvatar.type === 'custom') avatar.src = customAvatar.source;
    else avatar.src = `../map/sprite/${rawName}.png`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'agent-card-content';
    const nameDiv = document.createElement('div');
    nameDiv.className = 'agent-card-name';
    nameDiv.textContent = t_name(rawName) + (d.is_active === false ? ' (Departed)' : '');
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
  const parts = id.split(/[\._\-]/);
  return parts[parts.length - 1] || id;
}

function selectAgent(id) {
  selectedAgent = id;
  agentsWithNewAction.delete(id); 
  const d = agentsData[id];
  if (d) viewDays[id] = Math.floor((d.current_tick || 0) / 12) + 1;
  
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
    if (camera.zoom < 0.8) camera.zoom = 1.0;
    const sidebarWidth = document.querySelector('.sidebar')?.offsetWidth || 300;
    const detailPanelWidth = 400; 
    const totalWidth = window.innerWidth;
    const availableWidth = totalWidth - sidebarWidth - detailPanelWidth;
    const centerOffsetInScreen = sidebarWidth + availableWidth * 0.45;
    const canvasWidth = canvas.width;
    camera.targetX = targetWorldX - (centerOffsetInScreen - canvasWidth / 2) / camera.zoom;
    camera.targetY = targetWorldY;
  }
  renderAgentList();
  renderDetail(id);
  const box = document.getElementById('agentDetailBox');
  if (box) box.classList.add('show');
  const detailPanel = document.getElementById('detailPanel');
  if (detailPanel) detailPanel.scrollTop = 0;
}

function closeAgentDetail() {
  const box = document.getElementById('agentDetailBox');
  if (box) box.classList.remove('show');
  selectedAgent = null;
  renderAgentList();
}

function switchDay(event, id, day) {
  if (event) event.stopPropagation();
  viewDays[id] = day;
  renderDetail(id);
}

function openBubbleModal(bubble) {
  const id = bubble.agentId;
  const d = agentsData[id];
  if (!d) return;
  const mems = d.short_term_memory;
  const mem = mems && mems.length ? mems[mems.length - 1] : null;
  const tick = mem ? mem.tick : null;

  if (tick !== null && d.dialogues && d.dialogues[tick]) { openModal(null, id, tick); return; }
  const modal = document.getElementById('dialogueModal');
  const content = document.getElementById('dialogueContent');
  const summaryEl = document.getElementById('dialogueSummary');
  summaryEl.textContent = mem ? t_text(mem.content) : bubble.text;
  summaryEl.style.display = 'block';
  content.innerHTML = '<div class="empty-text" style="padding:16px;opacity:0.5;">No dialogue records.</div>';
  modal.style.display = 'block';
}

function openModal(event, agentId, tick) {
  if (event) event.stopPropagation();
  const d = agentsData[agentId];
  if (!d || !d.dialogues || !d.dialogues[tick]) return;
  const history = d.dialogues[tick];
  const modal = document.getElementById('dialogueModal');
  const content = document.getElementById('dialogueContent');
  const summaryEl = document.getElementById('dialogueSummary');
  const mem = d.short_term_memory ? d.short_term_memory.find(m => m.tick === tick) : null;
  if (mem && mem.content) { summaryEl.textContent = t_text(mem.content); summaryEl.style.display = 'block'; } 
  else { summaryEl.style.display = 'none'; }
  
  content.innerHTML = history.map(line => {
    // We preserve the new regex splitting for colored dialogues, and wrap the translation securely!
    const match = line.match(/^(.+?)：(?:\[(.+?)\])?(.*)$/);
    if (!match) return `<div class="dialogue-line">${escHtml(t_text(line))}</div>`;
    const [_, speaker, action, text] = match;
    return `
      <div class="dialogue-line">
        <span class="dialogue-speaker">${escHtml(t_name(speaker))}</span> 
        ${action ? `<span class="dialogue-action">[${escHtml(t_text(action))}]</span>` : ''}
        <span class="dialogue-text">${escHtml(t_text(text))}</span>
      </div>
    `;
  }).join('');
  modal.style.display = 'block';
}

function closeModal() { document.getElementById('dialogueModal').style.display = 'none'; }

function openAddAgentModal() { document.getElementById('addAgentModal').style.display = 'block'; renderPresetButtons(); resetAvatarSelection(); }
function resetAvatarSelection() { currentAvatar = { type: 'builtin', source: '../map/sprite/普通人.png', name: 'Commoner' }; document.getElementById('avatarType').value = 'builtin'; document.getElementById('avatarSource').value = '../map/sprite/普通人.png'; document.getElementById('selectedAvatarImg').src = '../map/sprite/普通人.png'; document.getElementById('customAvatarInput').value = ''; document.querySelectorAll('.avatar-option-btn').forEach(btn => btn.classList.remove('selected')); }
function closeAddAgentModal() { document.getElementById('addAgentModal').style.display = 'none'; document.getElementById('agentId').value = ''; document.getElementById('templateName').value = ''; document.getElementById('profileFamily').value = ''; document.getElementById('profilePersonality').value = ''; document.getElementById('profileDrive').value = ''; document.getElementById('profileStyle').value = ''; document.getElementById('profileBackground').value = ''; document.getElementById('agentMemory').value = ''; document.querySelectorAll('.preset-btn').forEach(btn => btn.classList.remove('selected')); resetAvatarSelection(); }
function openManagePresetModal() { document.getElementById('managePresetModal').style.display = 'block'; renderManagePresetList(); }
function closeManagePresetModal() { document.getElementById('managePresetModal').style.display = 'none'; }
function renderManagePresetList() {
  const list = document.getElementById('managePresetList');
  if (!list) return;
  const presets = getAllPresets();
  list.innerHTML = '';
  if (Object.keys(presets).length === 0) { list.innerHTML = '<div class="empty-text">No presets</div>'; return; }
  Object.entries(presets).forEach(([key, preset]) => {
    const item = document.createElement('div');
    item.className = 'preset-manage-item';
    item.innerHTML = `
      <img src="${preset.avatarSource || '../map/sprite/普通人.png'}" alt="${preset.name}" class="preset-manage-avatar" onerror="this.src='../map/sprite/普通人.png'" />
      <div class="preset-manage-info"><span class="preset-manage-name">${preset.name}</span><span class="preset-manage-tag">${preset.isOfficial ? 'Official' : 'Custom'}</span></div>
      <div class="preset-manage-actions">${!preset.isOfficial ? `<button class="btn-delete-preset" onclick="deletePreset('${key}'); renderManagePresetList();">Delete</button>` : ''}</div>
    `;
    list.appendChild(item);
  });
}

async function submitAddAgent() {
  const agentId = document.getElementById('agentId').value.trim();
  if (!agentId) { alert('Please enter agent name'); return; }
  const templateName = document.getElementById('templateName').value.trim();
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
  if (ws && ws.readyState === WebSocket.OPEN) {
    const message = { type: 'add_agent', agent_id: agentId, template_name: templateName, profile: profile, memory: memory, avatar: { type: currentAvatar.type, source: currentAvatar.source, name: currentAvatar.name } };
    ws.send(JSON.stringify(message));
    customAgentAvatars[agentId] = { type: currentAvatar.type, source: currentAvatar.source };
    saveCustomAvatars();
    if (currentAvatar.type === 'custom') { const img = new Image(); img.src = currentAvatar.source; agentSprites[agentId] = img; }
  } else { alert('WebSocket disconnected. Cannot add agent.'); }
}

let customAgentAvatars = {};
function loadCustomAvatars() {
  try {
    const saved = localStorage.getItem('customAgentAvatars');
    if (saved) {
      customAgentAvatars = JSON.parse(saved);
      Object.entries(customAgentAvatars).forEach(([agentId, avatar]) => {
        if (avatar.type === 'custom' && avatar.source) { const img = new Image(); img.src = avatar.source; agentSprites[agentId] = img; }
      });
    }
  } catch (e) {}
}
function saveCustomAvatars() { try { localStorage.setItem('customAgentAvatars', JSON.stringify(customAgentAvatars)); } catch (e) {} }
function handleAddAgentResponse(msg) { if (msg.success) { alert(`Agent "${msg.agent_id}" added successfully!`); closeAddAgentModal(); } else { alert(`Failed to add agent: ${msg.error || 'Unknown error'}`); } }

window.onclick = function(event) {
  const dialogueModal = document.getElementById('dialogueModal');
  const addAgentModal = document.getElementById('addAgentModal');
  const managePresetModal = document.getElementById('managePresetModal');
  if (event.target === dialogueModal) closeModal();
  if (event.target === addAgentModal) closeAddAgentModal();
  if (event.target === managePresetModal) closeManagePresetModal();
};

function renderDetail(id) {
  const d = agentsData[id];
  if (!d) return;
  const panel = document.getElementById('detailPanel');
  const name = formatAgentName(id);
  const customAvatar = customAgentAvatars[id];
  let avatarSrc = `../map/sprite/${name}.png`;
  if (customAvatar && customAvatar.type === 'custom') avatarSrc = customAvatar.source;

  panel.innerHTML = `
    <div class="detail-header">
      <div class="detail-avatar-container" id="detailAvatarContainer">
        <img src="${avatarSrc}" class="detail-avatar" onerror="document.getElementById('detailAvatarContainer').style.display='none'">
      </div>
      <div class="detail-name-row">
        <span class="detail-ornament">✦</span>
        <span class="detail-name">${t_name(name)}</span>
        <span class="detail-ornament">✦</span>
      </div>
    </div>
    ${renderSetPlan(id)}
    <div class="section-divider"><span>✧</span></div>
    ${renderProfile(d.profile)}
    <div class="section-divider"><span>✧</span></div>
    ${renderLongTask(d.long_task)}
    <div class="section-divider"><span>✧</span></div>
    ${renderCurrentPlan(d.current_plan, d.current_action, d.occupied_by, d.dialogues, id, d.current_plan_note, d.current_tick)}
    <div class="section-divider"><span>✧</span></div>
    ${renderMemory('Short-Term Memory', d.short_term_memory, 'short')}
    <div class="section-divider"><span>✧</span></div>
    ${renderExperiences(d.dialogues, d.short_term_memory, id)}
    <div class="section-divider"><span>✧</span></div>
    ${renderHourlyPlans(d.hourly_plans, d.dialogues, id, d.occupied_by, d.current_plan_note, d.current_tick)}
    <div class="section-divider"><span>✧</span></div>
    ${renderMemory('Long-Term Memory', d.long_term_memory, 'long')}
  `;
}

function renderSetPlan(id) {
  return `<section class="info-section">
    <div class="section-title"><span class="section-icon">命</span>Assign Task (Next Tick)</div>
    <div class="set-plan-box">
      <div class="form-group" style="margin-bottom:8px">
        <input type="text" id="customPlanAction_${id}" placeholder="Action (e.g. Garden Tour)" style="width:100%; padding:6px; font-family: inherit; background: rgba(255,255,255,0.85); border: 1px solid rgba(207,168,94,0.4); color: #1a1410; border-radius: 4px; box-sizing: border-box;" />
      </div>
      <div class="form-group" style="margin-bottom:8px; display:flex; gap:8px;">
        <input type="text" id="customPlanLocation_${id}" placeholder="Location" style="flex:1; padding:6px; font-family: inherit; background: rgba(255,255,255,0.85); border: 1px solid rgba(207,168,94,0.4); color: #1a1410; border-radius: 4px; box-sizing: border-box;" />
        <input type="text" id="customPlanTarget_${id}" placeholder="Target (Optional)" style="flex:1; padding:6px; font-family: inherit; background: rgba(255,255,255,0.85); border: 1px solid rgba(207,168,94,0.4); color: #1a1410; border-radius: 4px; box-sizing: border-box;" />
      </div>
      <button class="control-btn" style="width:100%; padding:6px; font-size:14px; margin-top: 4px;" onclick="sendCustomPlan('${id}')">Assign Highest Priority Task</button>
    </div>
  </section>`;
}

function sendCustomPlan(id) {
  const action = document.getElementById(`customPlanAction_${id}`).value.trim();
  const rawLocation = document.getElementById(`customPlanLocation_${id}`).value.trim();
  const rawTarget = document.getElementById(`customPlanTarget_${id}`).value.trim() || "None";

  // Translate input English names back to Chinese for the backend
  const cnLocation = t_rev_loc(rawLocation);
  const cnTarget = (rawTarget.toLowerCase() === "none" || rawTarget === "") ? "无" : t_rev_name(rawTarget);

  if (!action || !cnLocation) { alert("Action and location are required."); return; }
  
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "set_plan", agent_id: id, action: action, location: cnLocation, target: cnTarget }));
    alert("Task assigned! It will execute next tick.");
    document.getElementById(`customPlanAction_${id}`).value = ''; 
    document.getElementById(`customPlanLocation_${id}`).value = ''; 
    document.getElementById(`customPlanTarget_${id}`).value = '';
  } else { 
    alert("Connection lost."); 
  }
}

function renderProfile(profile) {
  if (!profile) return '';
  const fields = [ { label: 'Faction', key: '家族' }, { label: 'Personality', key: '性格' }, { label: 'Core Drive', key: '核心驱动' }, { label: 'Linguistic Style', key: '语言风格' } ];
  const items = fields.map(f => {
    const val = profile[f.key] || profile[f.label] || 'Unknown';
    return `<div class="profile-item"><span class="profile-label">${f.label}: </span><span class="profile-value">${escHtml(t_text(val))}</span></div>`;
  }).join('');
  return `<section class="info-section">
    <div class="section-title"><span class="section-icon">志</span>Profile</div>
    <div class="profile-grid">${items}</div>
    ${profile['背景经历'] ? `<div class="profile-bio"><strong>Background: </strong>${escHtml(t_text(profile['背景经历']))}</div>` : ''}
  </section>`;
}

function renderExperiences(dialogues, shortTermMemory, agentId) {
  if (!dialogues || Object.keys(dialogues).length === 0) { return `<section class="info-section"><div class="section-title">Experiences</div><div class="empty-text">No notable experiences yet.</div></section>`; }
  const ticks = Object.keys(dialogues).map(Number).sort((a, b) => b - a);
  const items = ticks.map(tick => {
    const mem = shortTermMemory ? shortTermMemory.find(m => m.tick === tick) : null;
    const summary = mem ? mem.content : 'A past event...';
    return `<div class="experience-card clickable-plan" onclick="openModal(event, '${agentId.replace(/'/g, "\\'")}', ${tick})">
        <div class="experience-header"><span class="experience-tick">Tick ${tick}</span><span class="experience-tag">Log</span></div>
        <div class="experience-summary">${escHtml(truncate(t_text(summary), 80))}</div>
        <div class="experience-footer"><span class="experience-hint">Click to read ❧</span></div>
      </div>`;
  }).join('');
  return `<section class="info-section"><div class="section-title">Experiences</div><div class="experience-list">${items}</div></section>`;
}

function renderLongTask(task) { return `<section class="info-section"><div class="section-title"><span class="section-icon">志</span>Long-Term Goal</div><div class="long-task-box">${task ? escHtml(t_text(task)) : '<span class="empty-text">No long-term goal.</span>'}</div></section>`; }

function renderCurrentPlan(plan, actionDetail, occupiedBy, dialogues, agentId, planNote, tick) {
  let content = '';
  const hasDialogue = dialogues && dialogues[tick];
  const clickableClass = hasDialogue ? ' clickable-plan' : '';
  const dialogueHint = hasDialogue ? '<span class="dialogue-hint">Click to view dialogue ❧</span>' : '';
  const noteHtml = planNote ? `<div class="plan-note-fail">⚠️ ${escHtml(t_text(planNote))}</div>` : '';

  if (!plan && !actionDetail && !occupiedBy) {
    content = '<span class="empty-text">No current action.</span>';
  } else if (occupiedBy) {
    const originalAction = Array.isArray(plan) ? plan[0] : (plan || 'Original Plan');
    const occupierName = t_name(formatAgentName(occupiedBy.occupier));
    const newAction = occupiedBy.action || 'Assisting';
    content = `<div class="current-plan-detail occupied${clickableClass}" onclick="openModal(event, '${agentId.replace(/'/g, "\\'")}', ${tick})">
        <div class="plan-conflict-badge">Plan Changed</div><div class="original-plan-crossed">${escHtml(t_text(originalAction))}</div><div class="arrow-down">↓</div>
        <div class="new-plan-box"><div class="new-plan-main">${escHtml(t_text(newAction))}</div><div class="new-plan-meta">Adjusted due to <strong>${escHtml(occupierName)}</strong></div>${dialogueHint}</div>
      </div>`;
  } else if (Array.isArray(plan)) {
    const [action, time, target, location, importance] = plan;
    const targetStr = target && target !== '无' && target !== 'None' && target !== '自己' ? ` w/ <strong>${escHtml(t_name(target))}</strong>` : '';
    content = `<div class="current-plan-detail${clickableClass}" onclick="openModal(event, '${agentId.replace(/'/g, "\\'")}', ${tick})">
        <div class="current-plan-main">${escHtml(t_text(actionDetail || action))}</div>
        <div class="current-plan-meta"><span>Loc: ${escHtml(t_loc(location))}</span>${targetStr ? `<span>Target: ${targetStr}</span>` : ''}<span class="importance-tag imp-${importance <= 3 ? 'low' : importance <= 6 ? 'mid' : importance <= 8 ? 'high' : 'crit'}">Priority: ${importance}</span></div>
        ${noteHtml}${dialogueHint}
      </div>`;
  } else if (actionDetail || typeof plan === 'string') {
    content = `<div class="${clickableClass}" onclick="openModal(event, '${agentId.replace(/'/g, "\\'")}', ${tick})">${escHtml(t_text(actionDetail || plan))} ${noteHtml} ${dialogueHint}</div>`;
  } else { content = `<pre>${escHtml(JSON.stringify(plan, null, 2))}</pre>`; }
  return `<section class="info-section"><div class="section-title"><span class="section-icon">行</span>Current Action</div><div class="current-plan-box">${content}</div></section>`;
}

function renderHourlyPlans(plans, dialogues, agentId, currentOccupiedBy, currentPlanNote, tick) {
  const currentDay = Math.floor((tick || 0) / 12) + 1;
  const viewingDay = viewDays[agentId] || currentDay;
  const currentHour = (tick || 0) % 12;
  let dayPlans = []; let availableDays = [];
  if (Array.isArray(plans)) { dayPlans = plans; availableDays = [1]; } else if (typeof plans === 'object' && plans !== null) { availableDays = Object.keys(plans).map(Number).sort((a, b) => a - b); dayPlans = plans[viewingDay] || []; }
  let daySelector = '';
  if (availableDays.length > 1) {
    const dayButtons = availableDays.map(d => `<button class="day-btn${d === viewingDay ? ' active' : ''}" onclick="switchDay(event, '${agentId.replace(/'/g, "\\'")}', ${d})">Day ${d}${d === currentDay ? ' (Today)' : ''}</button>`).join('');
    daySelector = `<div class="day-selector">${dayButtons}</div>`;
  }
  if (!dayPlans || !dayPlans.length) { return `<section class="info-section"><div class="section-title">Daily Plan</div>${daySelector}<div class="empty-text" style="padding:12px 0">No plans for Day ${viewingDay}</div></section>`; }

  const items = dayPlans.map(p => {
    const [action, time, target, location, importance] = p;
    const hourDisplay = HOURS_DISPLAY[time] || '?';
    const imp = parseInt(importance) || 1;
    const impClass = imp <= 3 ? 'imp-low' : imp <= 6 ? 'imp-mid' : imp <= 8 ? 'imp-high' : 'imp-crit';
    const targetStr = target && target !== '无' && target !== 'None' && target !== '自己' ? `→ ${escHtml(t_name(target))}` : '';
    const isCurrentlyOccupied = (viewingDay === currentDay && time === currentHour) && currentOccupiedBy;
    const hasNote = (viewingDay === currentDay && time === currentHour) && currentPlanNote;
    let dialogueTick = -1;
    if (dialogues) {
      const ticks = Object.keys(dialogues).map(Number).sort((a, b) => b - a);
      dialogueTick = ticks.find(t => { const d = Math.floor(t / 12) + 1; const h = t % 12; return d === viewingDay && h === time; }) || -1;
    }
    const hasDialogue = dialogueTick !== -1;
    const clickableClass = hasDialogue ? ' clickable-plan' : '';
    const clickHandler = hasDialogue ? `onclick="openModal(event, '${agentId.replace(/'/g, "\\'")}', ${dialogueTick})"` : '';
    const dialogueHint = hasDialogue ? '<div class="dialogue-hint">Click to read ❧</div>' : '';

    let contentHtml = '';
    if (isCurrentlyOccupied) {
      const occupierName = t_name(formatAgentName(currentOccupiedBy.occupier));
      const newAction = currentOccupiedBy.action || 'Assisting';
      contentHtml = `<div class="hourly-action original-plan-crossed">${escHtml(t_text(action))}</div><div class="hourly-conflict-desc"><span class="conflict-arrow">↓</span> <strong>${escHtml(t_text(newAction))}</strong><div class="conflict-meta">Changed for ${escHtml(occupierName)}</div></div>`;
    } else {
      contentHtml = `<div class="hourly-action">${escHtml(t_text(action))}</div><div class="hourly-meta">${escHtml(t_loc(location))}${targetStr ? ' <span class="hourly-target">' + targetStr + '</span>' : ''}</div>${hasNote ? `<div class="plan-note-fail small">⚠️ ${escHtml(t_text(currentPlanNote))}</div>` : ''}`;
    }
    const isNow = (viewingDay === currentDay && time === currentHour);
    return `<div class="hourly-item${clickableClass}${isNow ? ' current-hour' : ''}" ${clickHandler}><div class="hourly-time"><span class="shichen">${hourDisplay}</span></div><div class="hourly-line"><div class="hourly-dot ${impClass}"></div></div><div class="hourly-content">${contentHtml}${dialogueHint}</div></div>`;
  }).join('');
  return `<section class="info-section"><div class="section-title">Daily Plan</div>${daySelector}<div class="hourly-list">${items}</div></section>`;
}

function renderMemory(title, memories, type) {
  const icon = type === 'short' ? '念' : '忆';
  if (!memories || !memories.length) { return `<section class="info-section"><div class="section-title"><span class="section-icon">${icon}</span>${title}</div><div class="empty-text" style="padding:12px 0">No records.</div></section>`; }
  const sorted = [...memories].sort((a, b) => (b.tick ?? 0) - (a.tick ?? 0));
  const items = sorted.map(m => `<div class="memory-card ${type}-memory"><span class="memory-tick">Tick ${m.tick ?? '?'}</span><div class="memory-content">${escHtml(t_text(m.content ?? ''))}</div></div>`).join('');
  return `<section class="info-section"><div class="section-title"><span class="section-icon">${icon}</span>${title}</div><div class="memory-list">${items}</div></section>`;
}

function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function truncate(s, n) { return s.length > n ? s.slice(0, n) + '…' : s; }

async function loadInitialProfiles() {
  try {
    const response = await fetch('../data/agents/profiles_test.jsonl');
    if (!response.ok) throw new Error('Profile file not found');
    const text = await response.text();
    const lines = text.trim().split('\n');
    const initialData = {};
    lines.forEach(line => {
      if (!line.trim()) return;
      try {
        const profile = JSON.parse(line);
        const id = profile.id;
        initialData[id] = { profile: { ...profile, position: [0, 0] }, current_tick: 0, is_active: true };
        if (!agentIdleStates[id]) agentIdleStates[id] = { currentX: 0, currentY: 0, targetX: 0, targetY: 0, lastUpdate: Date.now(), nextMoveTime: Date.now() + Math.random() * 2000 };
      } catch (e) { }
    });
    mergeData(initialData);
    renderAgentList();
  } catch (err) {}
}

const introOverlay = document.getElementById('newIntroOverlay');
const coreAgents = ['贾宝玉', '林黛玉', '薛宝钗', '史湘云', '王熙凤', '贾母', '王夫人', '贾探春', '妙玉', '晴雯', '袭人', '贾政', '贾迎春', '贾惜春', '李纨', '贾琏', '薛蟠'];

function initLoadingRing() {
  const ring = document.getElementById('loadingRing');
  if (!ring) return;
  const shuffled = [...coreAgents].sort(() => 0.5 - Math.random());
  const selected = shuffled.slice(0, 12);
  const radius = 220; 
  selected.forEach((name, index) => {
    const angle = (index / selected.length) * Math.PI * 2;
    const x = Math.cos(angle) * radius;
    const y = Math.sin(angle) * radius;
    const img = document.createElement('img');
    img.src = `../map/sprite/${name}.png`;
    img.className = 'ring-avatar';
    const rotationDeg = (angle + Math.PI / 2) * (180 / Math.PI);
    img.style.left = `calc(50% + ${x}px)`;
    img.style.top = `calc(50% + ${y}px)`;
    img.style.transform = `rotate(${rotationDeg}deg)`;
    img.onerror = () => { img.onerror = null; img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"%3E%3Cpath fill="%23888" d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/%3E%3C/svg%3E'; };
    ring.appendChild(img);
  });
}

function startLoadingProgress() {
  const fill = document.getElementById('introProgressFill');
  if (!fill) return;
  let progress = 0;
  const interval = setInterval(() => {
    progress += Math.random() * 15;
    if (progress >= 100) { progress = 100; clearInterval(interval); fill.style.height = '100%'; setTimeout(finishLoadingAnimation, 500); } 
    else { fill.style.height = `${progress}%`; }
  }, 200);
}

function finishLoadingAnimation() {
  const ring = document.getElementById('loadingRing');
  const slidePanel = document.getElementById('introSlidePanel');
  if (ring) ring.classList.add('fade-out');
  setTimeout(() => {
    if (slidePanel) slidePanel.classList.add('open');
    setTimeout(() => { if (introOverlay) { introOverlay.classList.add('hidden'); setTimeout(() => { introOverlay.remove(); }, 1500); } }, 4500);
  }, 800);
}

async function startApp() {
  loadCustomAvatars();
  if (introOverlay) { initLoadingRing(); startLoadingProgress(); }
  await initMap();
  await loadInitialProfiles();
  if (mapData) initializeAgentPositions();
  connect();
}
startApp();

let mapData = null; let tilesets = []; let layerCanvases = []; let camera = { x: 0, y: 0, zoom: 1, minZoom: 0.1 }; let isDragging = false; let lastMousePos = { x: 0, y: 0 };

async function initMap() {
  const canvas = document.getElementById('mapCanvas'); const container = document.getElementById('mapContainer');
  if (!canvas || !container) return;
  window.addEventListener('resize', () => { resizeCanvas(); if (mapData) fitMapToContainer(); });
  resizeCanvas();

  try {
    const tmxPath = '../map/sos.tmx'; 
    const response = await fetch(tmxPath);
    const tmxText = await response.text();
    const parser = new DOMParser();
    const xmlDoc = parser.parseFromString(tmxText, "text/xml");
    const mapNode = xmlDoc.getElementsByTagName('map')[0];
    mapData = { width: parseInt(mapNode.getAttribute('width')), height: parseInt(mapNode.getAttribute('height')), tileWidth: parseInt(mapNode.getAttribute('tilewidth')), tileHeight: parseInt(mapNode.getAttribute('tileheight')), layers: [] };
    mapData.pixelWidth = mapData.width * mapData.tileWidth; mapData.pixelHeight = mapData.height * mapData.tileHeight;

    const tilesetNodes = xmlDoc.getElementsByTagName('tileset');
    for (let ts of tilesetNodes) {
      const firstgid = parseInt(ts.getAttribute('firstgid'));
      const source = ts.getAttribute('source');
      const tsxPath = `../map/${source}`;
      const tsxResponse = await fetch(tsxPath);
      const tsxText = await tsxResponse.text();
      const tsxDoc = parser.parseFromString(tsxText, "text/xml");
      const tsxNode = tsxDoc.getElementsByTagName('tileset')[0];
      const imageNode = tsxDoc.getElementsByTagName('image')[0];
      
      let rawImageSource = imageNode.getAttribute('source');
      if (rawImageSource.includes('Hospital/source/')) rawImageSource = 'Tiles/' + rawImageSource.split('Hospital/source/')[1];
      else if (rawImageSource.includes('../Tiles/')) rawImageSource = rawImageSource.substring(rawImageSource.indexOf('Tiles/'));
      const imageSource = `../map/${rawImageSource}`;

      const tileset = { firstgid, name: tsxNode.getAttribute('name'), tileWidth: parseInt(tsxNode.getAttribute('tilewidth')), tileHeight: parseInt(tsxNode.getAttribute('tileheight')), columns: parseInt(tsxNode.getAttribute('columns')), imageSource: imageSource, width: parseInt(imageNode.getAttribute('width')), height: parseInt(imageNode.getAttribute('height')) };
      tileset.image = await loadImage(tileset.imageSource);
      tilesets.push(tileset);
    }

    mapData.layers = []; mapData.locations = []; mapData.passableGids = null; 

    function parseLayers(node, isLocationGroup = false) {
      const children = Array.from(node.children || []);
      for (let child of children) {
        const name = child.getAttribute('name');
        if ((name === '可通行' || name === '可通行区域') && child.nodeName === 'layer') {
          const dataNode = child.getElementsByTagName('data')[0];
          if (dataNode) mapData.passableGids = dataNode.textContent.trim().split(',').map(s => parseInt(s.trim()));
          continue;
        }
        if ((name === '可通行' || name === '可通行区域') && child.nodeName === 'layer') continue;
        
        if (child.nodeName === 'layer') {
          const visible = child.getAttribute('visible') !== '0';
          const dataNode = child.getElementsByTagName('data')[0];
          if (!dataNode) continue;
          const gids = dataNode.textContent.trim().split(',').map(s => parseInt(s.trim()));
          if (isLocationGroup || name === '仆役群房') {
            let sumX = 0, sumY = 0, count = 0; const validTiles = [];
            for (let i = 0; i < gids.length; i++) { if (gids[i] !== 0) { sumX += i % mapData.width; sumY += Math.floor(i / mapData.width); count++; validTiles.push(i); } }
            if (count > 0) {
              const existingLoc = mapData.locations.find(l => l.name === name);
              if (existingLoc) {
                existingLoc.tiles = existingLoc.tiles.concat(validTiles);
                const tc = existingLoc.tiles.length;
                existingLoc.x = ((existingLoc.x * (tc - count)) + sumX * mapData.tileWidth) / tc;
                existingLoc.y = ((existingLoc.y * (tc - count)) + sumY * mapData.tileHeight) / tc;
              } else { mapData.locations.push({ name: name, x: (sumX / count) * mapData.tileWidth, y: (sumY / count) * mapData.tileHeight, tiles: validTiles }); }
            }
            continue;
          }
          if (visible) mapData.layers.push({ name: name, gids: gids });
        } else if (child.nodeName === 'group') {
          const isLocGroup = isLocationGroup || (name === '地点' || name === '大观园' || name === '荣国府' || name === '宁国府');
          parseLayers(child, isLocGroup);
        }
      }
    }
    parseLayers(mapNode);
    initializeAgentPositions();
    preRenderLayers();
    fitMapToContainer();
    document.getElementById('mapLoading').style.display = 'none';
    requestAnimationFrame(renderLoop);

    let mouseDownPos = null;
    container.addEventListener('mousedown', e => { isDragging = true; mouseDownPos = { x: e.clientX, y: e.clientY }; lastMousePos = { x: e.clientX, y: e.clientY }; camera.targetX = undefined; camera.targetY = undefined; });
    window.addEventListener('mousemove', e => { if (!isDragging) return; const dx = e.clientX - lastMousePos.x; const dy = e.clientY - lastMousePos.y; camera.x -= dx / camera.zoom; camera.y -= dy / camera.zoom; clampCamera(); lastMousePos = { x: e.clientX, y: e.clientY }; });
    window.addEventListener('mouseup', e => { isDragging = false; if (mouseDownPos) { const dist = Math.hypot(e.clientX - mouseDownPos.x, e.clientY - mouseDownPos.y); if (dist < 5) handleCanvasClick(e, canvas); mouseDownPos = null; } });
    container.addEventListener('wheel', e => { e.preventDefault(); camera.zoom *= e.deltaY > 0 ? 0.9 : 1.1; camera.zoom = Math.max(camera.minZoom, Math.min(5, camera.zoom)); clampCamera(); }, { passive: false });
  } catch (err) { document.getElementById('mapLoading').textContent = 'Failed to load map: ' + err.message; }
}

function fitMapToContainer() { const container = document.getElementById('mapContainer'); const cw = container.clientWidth; const ch = container.clientHeight; const scaleX = cw / mapData.pixelWidth; const scaleY = ch / mapData.pixelHeight; camera.minZoom = Math.max(scaleX, scaleY); camera.zoom = camera.minZoom; camera.x = mapData.pixelWidth / 2; camera.y = mapData.pixelHeight / 2; clampCamera(); }
function clampCamera() { if (!mapData) return; const canvas = document.getElementById('mapCanvas'); const vw = canvas.width / camera.zoom; const vh = canvas.height / camera.zoom; const minX = vw / 2; const maxX = mapData.pixelWidth - vw / 2; const minY = vh / 2; const maxY = mapData.pixelHeight - vh / 2; if (maxX < minX) camera.x = mapData.pixelWidth / 2; else camera.x = Math.max(minX, Math.min(maxX, camera.x)); if (maxY < minY) camera.y = mapData.pixelHeight / 2; else camera.y = Math.max(minY, Math.min(maxY, camera.y)); }
function resizeCanvas() { const canvas = document.getElementById('mapCanvas'); const container = document.getElementById('mapContainer'); canvas.width = container.clientWidth; canvas.height = container.clientHeight; }
function loadImage(src) { return new Promise((resolve, reject) => { const img = new Image(); img.onload = () => resolve(img); img.onerror = () => reject(new Error('Load failed: ' + src)); img.src = src; }); }

const staticProfiles = {
  '贾宝玉':  { '家族':'Rongguo Mansion', '性格':'Romantic, sensitive, rebellious', '核心驱动':'Pursuing true love and freedom, despising officialdom', '语言风格':'Gentle, delicate, often poetic', '背景经历':'The legitimate grandson of the Rongguo Mansion, born with a magical jade. Grew up among girls, deeply attached to Lin Daiyu.' },
  '林黛玉':  { '家族':'Lin Family (residing in Rongguo)', '性格':'Sensitive, melancholic, brilliant', '核心驱动':'Craving true understanding and love, guarding her inner purity', '语言风格':'Sharp, poetic, slightly sarcastic', '背景经历':'Daughter of Lin Ruhai. Lives with her grandmother after her mother passed away. Frail but extraordinarily talented, deeply in love with Baoyu.' },
  '薛宝钗':  { '家族':'Xue Family', '性格':'Dignified, steady, tactful', '核心驱动':'Maintaining family interests, winning approval through virtue', '语言风格':'Gentle, appropriate, well-rounded', '背景经历':'Daughter of the Xue family. Knowledgeable and reliable. Highly favored by the elders, destined for the "Gold and Jade" marriage.' },
  '史湘云':  { '家族':'Shi Family', '性格':'Frank, straightforward, optimistic', '核心驱动':'Enjoying the present, treating others with genuine feelings', '语言风格':'Hearty, direct, carefree', '背景经历':'An orphaned noble girl raised by her uncle. Loves dressing as a boy and joking around. Treats Baoyu like a brother.' },
  '贾母':    { '家族':'Rongguo Mansion', '性格':'Loving, authoritative, experienced', '核心驱动':'Protecting the Jia family\'s glory and her grandchildren', '语言风格':'Kind but authoritative, decisive', '背景经历':'The highest authority in the Jia family. Dotes heavily on Baoyu.' },
  '王夫人':  { '家族':'Wang Family (married into Rongguo)', '性格':'Outwardly kind, inwardly rigid', '核心驱动':'Protecting the legitimate line and Baoyu\'s future', '语言风格':'Calm, speaks little, occasionally furious', '背景经历':'Baoyu\'s mother. Devoted Buddhist but ruthless against anyone she perceives as a threat to Baoyu.' },
  '王熙凤':  { '家族':'Wang Family (married into Rongguo)', '性格':'Capable, shrewd, ruthless', '核心驱动':'Controlling power and maintaining her wealth and status', '语言风格':'Sharp-tongued, superficially sweet but cunning', '背景经历':'Wife of Jia Lian, actual manager of the Rongguo Mansion\'s internal affairs. Highly capable but corrupt.' },
  '薛姨妈':  { '家族':'Xue Family', '性格':'Amiable, lenient, protective', '核心驱动':'Securing a good future for her children', '语言风格':'Friendly, acts as a warm elder', '背景经历':'Sister of Lady Wang, mother of Xue Pan and Baochai. Often covers up her son\'s misdeeds.' },
  '贾政':    { '家族':'Rongguo Mansion', '性格':'Pedantic, orthodox, strict', '核心驱动':'Bringing honor to the family through officialdom', '语言风格':'Serious, cites classics, intimidating', '背景经历':'Baoyu\'s father. Highly disappointed in Baoyu\'s lack of interest in official studies.' },
  '贾元春':  { '家族':'Rongguo Mansion', '性格':'Dignified, virtuous, deep', '核心驱动':'Protecting the Jia family as a royal consort, despite her loneliness', '语言风格':'Solemn, elegant, measured', '背景经历':'Eldest daughter of Jia Zheng, became a noble consort in the palace. The Grand View Garden was built for her visitation.' },
  '贾探春':  { '家族':'Rongguo Mansion', '性格':'Capable, ambitious, sharp', '核心驱动':'Overcoming her concubine-born status to prove her worth', '语言风格':'Direct, logical, authoritative', '背景经历':'Concubine Zhao\'s daughter. Highly competent, briefly managed the household with notable reforms.' },
  '贾迎春':  { '家族':'Rongguo Mansion', '性格':'Cowardly, submissive, yielding', '核心驱动':'Seeking peace, avoiding conflict', '语言风格':'Soft-spoken, indecisive', '背景经历':'Jia She\'s concubine-born daughter. Known as "Miss Wood" for her extreme passivity.' },
  '贾惜春':  { '家族':'Ningguo Mansion', '性格':'Cold, aloof, detached', '核心驱动':'Escaping the corrupt Jia family through spiritual detachment', '语言风格':'Cold, brief, unsympathetic', '背景经历':'Sister of Jia Zhen. Disillusioned by the family\'s scandals, eventually becomes a nun.' },
  '李纨':    { '家族':'Rongguo Mansion (Widowed)', '性格':'Chaste, calm, gentle', '核心驱动':'Raising her son Jia Lan to succeed, protecting herself', '语言风格':'Mild, restrained, speaks little', '背景经历':'Widow of Jia Zhu. Lives a secluded life but shows warmth when leading the poetry club.' },
  '贾琏':    { '家族':'Rongguo Mansion', '性格':'Lustful, smooth, superficial', '核心驱动':'Pleasure-seeking, maintaining appearances', '语言风格':'Smooth, socially adept', '背景经历':'Husband of Wang Xifeng. Handles external affairs but constantly cheats on his wife.' },
  '贾珍':    { '家族':'Ningguo Mansion', '性格':'Licentious, arrogant, tyrannical', '核心驱动':'Indulging in pleasure, maintaining the mansion\'s facade', '语言风格':'Domineering, disregards rules', '背景经历':'Head of the Ningguo Mansion. Leads a corrupt lifestyle, implicated in scandals with his daughter-in-law.' },
  '贾蓉':    { '家族':'Ningguo Mansion', '性格':'Weak, incompetent, obedient', '核心驱动':'Surviving under his father Jia Zhen\'s shadow', '语言风格':'Submissive, lacks autonomy', '背景经历':'Son of Jia Zhen. Mediocre and entirely controlled by his father.' },
  '贾环':    { '家族':'Rongguo Mansion', '性格':'Sinister, petty, jealous', '核心驱动':'Fighting for status, seeking revenge against those who slight him', '语言风格':'Sarcastic, arrogant when successful', '背景经历':'Concubine Zhao\'s son. Deeply jealous of Baoyu and often tries to harm him.' },
  '赵姨娘':  { '家族':'Rongguo Mansion (Concubine)', '性格':'Shrewish, vulgar, narrow-minded', '核心驱动':'Fighting for Jia Huan\'s status, opposing Lady Wang', '语言风格':'Vulgar, direct, often throws tantrums', '背景经历':'Jia Zheng\'s concubine. Frequently causes trouble and even used dark magic against Baoyu and Xifeng.' },
  '薛蟠':    { '家族':'Xue Family', '性格':'Tyrannical, uneducated, reckless', '核心驱动':'Indulging in wine and women, doing whatever he pleases', '语言风格':'Vulgar, blunt, often makes a fool of himself', '背景经历':'Known as the "Foolish Overlord." Involved in a murder case but evaded justice. Coarse but sometimes naively straightforward.' },
  '袭人':    { '家族':'Yihong Court (Maid)', '性格':'Gentle, considerate, calculating', '核心驱动':'Securing her position as Baoyu\'s future concubine through virtue', '语言风格':'Gentle, persuasive, tactful', '背景经历':'Baoyu\'s chief maid. Deeply trusted by Lady Wang.' },
  '晴雯':    { '家族':'Yihong Court (Maid)', '性格':'Fierce, straightforward, proud', '核心驱动':'Living authentically, refusing to compromise', '语言风格':'Sharp-tongued, quick-witted, direct', '背景经历':'Baoyu\'s most favored maid. Expelled by Lady Wang for being too beautiful and proud, died of illness shortly after.' },
  '紫鹃':    { '家族':'Xiaoxiang Lodge (Maid)', '性格':'Loyal, careful, devoted', '核心驱动':'Protecting Lin Daiyu and planning for her future', '语言风格':'Gentle, considerate, occasionally witty', '背景经历':'Daiyu\'s devoted maid. The most trustworthy person Daiyu has in the mansion.' },
  '麝月':    { '家族':'Yihong Court (Maid)', '性格':'Steady, peaceful, hardworking', '核心驱动':'Dutifully maintaining order in Yihong Court', '语言风格':'Plain, steady, speaks little', '背景经历':'A reliable maid in Yihong Court, neither as calculating as Xiren nor as fiery as Qingwen.' },
  '平儿':    { '家族':'Wang Xifeng Court (Maid)', '性格':'Smart, kind, diplomatic', '核心驱动':'Balancing the tension between Xifeng and Jia Lian with kindness', '语言风格':'Witty, tactful, empathetic', '背景经历':'Xifeng\'s chief maid and Jia Lian\'s concubine. Widely respected for her fairness and kindness.' },
  '鸳鸯':    { '家族':'Grandmother Jia Court (Maid)', '性格':'Fierce, loyal, brave', '核心驱动':'Serving Grandmother Jia, defending her own dignity', '语言风格':'Direct, forceful, unyielding', '背景经历':'Grandmother Jia\'s most trusted maid. Fiercely refused Jia She\'s demand to take her as a concubine.' },
  '妙玉':    { '家族':'None (Nun)', '性格':'Aloof, obsessive about cleanliness', '核心驱动':'Maintaining her spiritual purity in a corrupt world', '语言风格':'Cold, arrogant, Zen-like', '背景经历':'A highly talented nun living in the Grand View Garden. Secretly harbors feelings for Baoyu despite her monastic vows.' }
};

const agentToHome = {
  '贾宝玉': '怡红院', '林黛玉': '潇湘馆', '薛宝钗': '蘅芜院', '贾母': '贾母院', '王夫人': '王夫人院', '王熙凤': '王熙凤院',
  '李纨': '稻香村', '贾兰': '稻香村', '贾探春': '晓翠堂', '贾迎春': '紫凌洲', '贾惜春': '暖乡坞', '妙玉': '达摩庵',
  '袭人': '怡红院', '晴雯': '怡红院', '麝月': '怡红院', '紫鹃': '潇湘馆', '平儿': '王熙凤院', '鸳鸯': '贾母院',
  '史湘云': '蘅芜院', '薛姨妈': '薛姨妈院', '薛蟠': '薛姨妈院', '贾政': '贾政内书房', '贾琏': '王熙凤院',
  '贾珍': '宁国府正院', '贾蓉': '贾蓉院', '尤氏': '尤氏院', '贾元春': '顾恩思义殿', '赵姨娘': '王夫人院',
  '贾环': '王夫人院', '彩云': '王夫人院', '彩霞': '王夫人院', '金钏': '王夫人院', '玉钏': '王夫人院',
  '司棋': '紫凌洲', '侍书': '晓翠堂', '入画': '暖乡坞', '翠缕': '蘅芜院', '小红': '怡红院', '雪雁': '潇湘馆',
  '秋纹': '怡红院', '碧痕': '怡红院', '莺儿': '蘅芜院', '香菱': '梨香院', '琥珀': '贾母院', '素云': '稻香村',
  '丰儿': '王熙凤院', '焦大': '宁国府正院', '赖大': '仆役群房', '周瑞': '周瑞院', '林之孝': '仆役群房'
};

function isServant(name) { return ['袭人','晴雯','麝月','紫鹃','平儿','鸳鸯','彩云','彩霞','金钏','玉钏','司棋','侍书','入画','翠缕','小红','雪雁','秋纹','碧痕','莺儿','香菱','琥珀','素云','丰儿','焦大','赖大','周瑞','林之孝'].includes(name); }

function initializeAgentPositions() {
  if (!mapData || !mapData.locations) return;
  const servantFallback = mapData.locations.find(l => l.name === '仆役群房');
  const masterFallback = mapData.locations.find(l => l.name === '荣国府') || mapData.locations.find(l => l.name === '大观园');
  Object.keys(agentsData).forEach(id => {
    const d = agentsData[id];
    const name = formatAgentName(id);
    if (d.profile && d.profile.position && (d.profile.position[0] !== 0 || d.profile.position[1] !== 0)) return;
    assignRandomPositionToAgent(id, name, servantFallback, masterFallback);
  });
  initializeNPCs(servantFallback);
}

function assignRandomPositionToAgent(agentId, agentName, servantFallback, masterFallback) {
  if (!mapData || !mapData.locations) return false;
  const d = agentsData[agentId]; if (!d) return false;
  const name = agentName || formatAgentName(agentId);
  if (!servantFallback) servantFallback = mapData.locations.find(l => l.name === '仆役群房');
  if (!masterFallback) masterFallback = mapData.locations.find(l => l.name === '荣国府') || mapData.locations.find(l => l.name === '大观园');
  let location = null;
  const homeName = agentToHome[name];
  if (homeName) location = mapData.locations.find(l => l.name === homeName || l.name.includes(homeName) || homeName.includes(l.name));
  if (!location && mapData.locations.length > 0) location = mapData.locations[Math.floor(Math.random() * mapData.locations.length)];
  if (!location) location = isServant(name) ? servantFallback : masterFallback;

  if (location && location.tiles) {
    let tx, ty;
    if (mapData.passableGids) {
      const passableTiles = location.tiles.filter(tileIdx => mapData.passableGids[tileIdx] !== 0);
      if (passableTiles.length > 0) { const randomTileIdx = passableTiles[Math.floor(Math.random() * passableTiles.length)]; tx = randomTileIdx % mapData.width; ty = Math.floor(randomTileIdx / mapData.width); }
    }
    if (tx === undefined && location.tiles.length > 0) { const randomTileIdx = location.tiles[Math.floor(Math.random() * location.tiles.length)]; tx = randomTileIdx % mapData.width; ty = Math.floor(randomTileIdx / mapData.width); }
    if (tx === undefined) { tx = Math.floor(location.x / mapData.tileWidth); ty = Math.floor(location.y / mapData.tileHeight); }
    if (!d.profile) d.profile = {}; d.profile.position = [tx, ty];
    const worldX = tx * mapData.tileWidth; const worldY = ty * mapData.tileHeight;
    agentIdleStates[agentId] = { currentX: worldX, currentY: worldY, targetX: worldX, targetY: worldY, lastUpdate: Date.now(), nextMoveTime: Date.now() + Math.random() * 2000 };
    return true;
  }
  return false;
}

function getRandomLocationPos(location) {
  if (!location || !location.tiles) return null;
  let tx, ty;
  if (mapData.passableGids) {
    const passableTiles = location.tiles.filter(tileIdx => mapData.passableGids[tileIdx] !== 0);
    if (passableTiles.length > 0) { const randomTileIdx = passableTiles[Math.floor(Math.random() * passableTiles.length)]; return { x: (randomTileIdx % mapData.width) * mapData.tileWidth, y: Math.floor(randomTileIdx / mapData.width) * mapData.tileHeight }; }
  }
  if (location.tiles.length > 0) { const randomTileIdx = location.tiles[Math.floor(Math.random() * location.tiles.length)]; return { x: (randomTileIdx % mapData.width) * mapData.tileWidth, y: Math.floor(randomTileIdx / mapData.width) * mapData.tileHeight }; }
  return { x: location.x, y: location.y };
}

function getRandomLocation() {
  const validLocs = mapData.locations.filter(l => l.name !== '仆役群房' && l.tiles && l.tiles.length > 0);
  if (validLocs.length === 0) return null; return validLocs[Math.floor(Math.random() * validLocs.length)];
}

class MinHeap {
  constructor() { this.heap = []; }
  push(node) { this.heap.push(node); this.bubbleUp(this.heap.length - 1); }
  pop() { if (this.heap.length === 0) return null; const top = this.heap[0]; const bottom = this.heap.pop(); if (this.heap.length > 0) { this.heap[0] = bottom; this.sinkDown(0); } return top; }
  isEmpty() { return this.heap.length === 0; }
  bubbleUp(n) { let element = this.heap[n]; while (n > 0) { let parentN = Math.floor((n + 1) / 2) - 1; let parent = this.heap[parentN]; if (element.priority >= parent.priority) break; this.heap[parentN] = element; this.heap[n] = parent; n = parentN; } }
  sinkDown(n) { let length = this.heap.length; let element = this.heap[n]; while (true) { let child2N = (n + 1) * 2; let child1N = child2N - 1; let swap = null; if (child1N < length) { let child1 = this.heap[child1N]; if (child1.priority < element.priority) swap = child1N; } if (child2N < length) { let child2 = this.heap[child2N]; if (child2.priority < (swap === null ? element.priority : this.heap[child1N].priority)) swap = child2N; } if (swap === null) break; this.heap[n] = this.heap[swap]; this.heap[swap] = element; n = swap; } }
}

function findPath(startX, startY, endX, endY) {
  if (!mapData || !mapData.passableGids) return null;
  const width = mapData.width; const height = mapData.height;
  if (startX < 0 || startX >= width || startY < 0 || startY >= height || endX < 0 || endX >= width || endY < 0 || endY >= height) return null;
  const startIdx = startY * width + startX; const endIdx = endY * width + endX;
  
  let actualStartIdx = startIdx;
  if (mapData.passableGids[startIdx] === 0) {
    let found = false; const queue = [startIdx]; const visited = new Set([startIdx]);
    while(queue.length > 0) { const curr = queue.shift(); if (mapData.passableGids[curr] !== 0) { actualStartIdx = curr; found = true; break; } const cx = curr % width; const cy = Math.floor(curr / width); const neighbors = [{x: cx+1, y: cy}, {x: cx-1, y: cy}, {x: cx, y: cy+1}, {x: cx, y: cy-1}]; for (const n of neighbors) { if (n.x >= 0 && n.x < width && n.y >= 0 && n.y < height) { const nIdx = n.y * width + n.x; if (!visited.has(nIdx)) { visited.add(nIdx); queue.push(nIdx); } } } if (visited.size > 100) break; } if (!found) return null;
  }
  let actualEndIdx = endIdx;
  if (mapData.passableGids[actualEndIdx] === 0) {
     let found = false; const queue = [actualEndIdx]; const visited = new Set([actualEndIdx]);
     while(queue.length > 0) { const curr = queue.shift(); if (mapData.passableGids[curr] !== 0) { actualEndIdx = curr; found = true; break; } const cx = curr % width; const cy = Math.floor(curr / width); const neighbors = [{x: cx+1, y: cy}, {x: cx-1, y: cy}, {x: cx, y: cy+1}, {x: cx, y: cy-1}]; for (const n of neighbors) { if (n.x >= 0 && n.x < width && n.y >= 0 && n.y < height) { const nIdx = n.y * width + n.x; if (!visited.has(nIdx)) { visited.add(nIdx); queue.push(nIdx); } } } if (visited.size > 100) break; } if (!found) return null;
  }
  
  const frontier = new MinHeap(); frontier.push({idx: actualStartIdx, priority: 0});
  const cameFrom = new Map(); const costSoFar = new Map(); cameFrom.set(actualStartIdx, null); costSoFar.set(actualStartIdx, 0);
  const heuristic = (aIdx, bIdx) => Math.abs(aIdx % width - bIdx % width) + Math.abs(Math.floor(aIdx / width) - Math.floor(bIdx / width));
  let pathFound = false;
  while (!frontier.isEmpty()) {
    const currentObj = frontier.pop();
    const current = currentObj.idx;
    if (current === actualEndIdx) { pathFound = true; break; }
    const cx = current % width; const cy = Math.floor(current / width);
    const dirs = [{dx: 0, dy: -1, cost: 1}, {dx: 1, dy: 0, cost: 1}, {dx: 0, dy: 1, cost: 1}, {dx: -1, dy: 0, cost: 1}, {dx: 1, dy: -1, cost: 1.414}, {dx: 1, dy: 1, cost: 1.414}, {dx: -1, dy: 1, cost: 1.414}, {dx: -1, dy: -1, cost: 1.414}];
    for (const dir of dirs) {
      const nx = cx + dir.dx; const ny = cy + dir.dy;
      if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
        const nIdx = ny * width + nx;
        if (mapData.passableGids[nIdx] !== 0) {
           if (Math.abs(dir.dx) === 1 && Math.abs(dir.dy) === 1) { const idx1 = cy * width + nx; const idx2 = ny * width + cx; if (mapData.passableGids[idx1] === 0 || mapData.passableGids[idx2] === 0) continue; }
           const newCost = costSoFar.get(current) + dir.cost;
           if (!costSoFar.has(nIdx) || newCost < costSoFar.get(nIdx)) { costSoFar.set(nIdx, newCost); const priority = newCost + heuristic(nIdx, actualEndIdx); frontier.push({idx: nIdx, priority: priority}); cameFrom.set(nIdx, current); }
        }
      }
    }
  }
  if (!pathFound) return null;
  const path = []; let current = actualEndIdx; while (current !== actualStartIdx) { path.push({ x: current % width, y: Math.floor(current / width) }); current = cameFrom.get(current); }
  path.reverse(); return path;
}

function initializeNPCs(servantFallback) {
  if (npcs.length > 0) return; 
  if (!agentSprites['小厮']) { const img = new Image(); img.src = `../map/sprite/小厮.png`; agentSprites['小厮'] = img; }
  citizenSpriteNames.forEach(name => { if (!agentSprites[name]) { const img = new Image(); img.src = `../map/sprite/${name}.png`; agentSprites[name] = img; } });

  for (let i = 0; i < 25; i++) {
    const initLoc = Math.random() < 0.3 ? getRandomLocation() : servantFallback;
    const startPos = getRandomLocationPos(initLoc || servantFallback);
    if (!startPos) continue;
    npcs.push({ id: `npc_${i}`, name: '小厮', currentX: startPos.x, currentY: startPos.y, targetX: startPos.x, targetY: startPos.y, state: 'wait_at_home', waitTimeEnd: Date.now() + Math.random() * 20000, speed: 0.8 + Math.random() * 0.8, facingLeft: false, homeLoc: servantFallback });
  }
}

function preRenderLayers() {
  layerCanvases = mapData.layers.map(layer => {
    const offCanvas = document.createElement('canvas'); offCanvas.width = mapData.pixelWidth; offCanvas.height = mapData.pixelHeight; const offCtx = offCanvas.getContext('2d');
    for (let y = 0; y < mapData.height; y++) { for (let x = 0; x < mapData.width; x++) { const gid = layer.gids[y * mapData.width + x]; if (gid !== 0) drawTileToCtx(offCtx, gid, x * mapData.tileWidth, y * mapData.tileHeight); } }
    return offCanvas;
  });
}

function drawTileToCtx(ctx, gid, x, y) {
  let tileset = null;
  for (let i = tilesets.length - 1; i >= 0; i--) { if (gid >= tilesets[i].firstgid) { tileset = tilesets[i]; break; } }
  if (!tileset) return;
  const localId = gid - tileset.firstgid;
  ctx.drawImage(tileset.image, (localId % tileset.columns) * tileset.tileWidth, Math.floor(localId / tileset.columns) * tileset.tileHeight, tileset.tileWidth, tileset.tileHeight, x, y, tileset.tileWidth, tileset.tileHeight);
}

function renderLoop() {
  const canvas = document.getElementById('mapCanvas'); const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!mapData || layerCanvases.length === 0) return;

  if (camera.targetX !== undefined && camera.targetY !== undefined) {
    const dx = camera.targetX - camera.x; const dy = camera.targetY - camera.y;
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) { camera.x = camera.targetX; camera.y = camera.targetY; } else { camera.x += dx * 0.05; camera.y += dy * 0.05; }
  }

  ctx.save();
  ctx.translate(canvas.width / 2, canvas.height / 2); ctx.scale(camera.zoom, camera.zoom); ctx.translate(-camera.x, -camera.y);
  const vw = canvas.width / camera.zoom; const vh = canvas.height / camera.zoom;
  const viewLeft = camera.x - vw / 2; const viewTop = camera.y - vh / 2;

  for (let i = 0; i < layerCanvases.length; i++) ctx.drawImage(layerCanvases[i], viewLeft, viewTop, vw, vh, viewLeft, viewTop, vw, vh);

  const now = Date.now();
  const cellOccupants = {};
  Object.keys(agentsData).forEach(id => {
    const d = agentsData[id];
    if (d.profile && d.profile.position) {
      const state = agentIdleStates[id];
      const cx = state ? Math.floor(state.currentX / mapData.tileWidth) : d.profile.position[0];
      const cy = state ? Math.floor(state.currentY / mapData.tileHeight) : d.profile.position[1];
      const cellKey = `${cx},${cy}`;
      if (!cellOccupants[cellKey]) cellOccupants[cellKey] = []; cellOccupants[cellKey].push(id);
    }
  });

  Object.keys(agentsData).forEach(id => {
    const d = agentsData[id];
    if (d.profile && d.profile.position) {
      const state = agentIdleStates[id]; let drawX = d.profile.position[0] * mapData.tileWidth; let drawY = d.profile.position[1] * mapData.tileHeight;
      if (state) {
        if (now > state.nextMoveTime) {
          const name = formatAgentName(id); const homeName = agentToHome[name];
          let location = homeName ? mapData.locations.find(l => l.name === homeName || l.name.includes(homeName) || homeName.includes(l.name)) : mapData.locations.find(l => l.name === '仆役群房');
          if (location && location.tiles) {
            let candidateTiles = mapData.passableGids ? location.tiles.filter(idx => mapData.passableGids[idx] !== 0) : location.tiles;
            if (candidateTiles.length === 0) candidateTiles = location.tiles;
            if (candidateTiles.length > 0) {
              const currentLogicX = Math.floor(state.currentX / mapData.tileWidth); const currentLogicY = Math.floor(state.currentY / mapData.tileHeight);
              const nearbyTiles = candidateTiles.filter(tileIdx => {
                const px = tileIdx % mapData.width; const py = Math.floor(tileIdx / mapData.width);
                const dist = Math.abs(px - currentLogicX) + Math.abs(py - currentLogicY);
                if (dist > 2) return false;
                if (dist === 2) {
                  if (px !== currentLogicX && py !== currentLogicY) { const idx1 = py * mapData.width + currentLogicX; const idx2 = currentLogicY * mapData.width + px; if (mapData.passableGids && mapData.passableGids[idx1] === 0 && mapData.passableGids[idx2] === 0) return false; }
                  else { const midIdx = ((py + currentLogicY) / 2) * mapData.width + (px + currentLogicX) / 2; if (mapData.passableGids && mapData.passableGids[midIdx] === 0) return false; }
                }
                return true;
              });
              const pool = nearbyTiles.length > 0 ? nearbyTiles : [currentLogicY * mapData.width + currentLogicX];
              const randomTileIdx = pool[Math.floor(Math.random() * pool.length)];
              state.targetX = (randomTileIdx % mapData.width) * mapData.tileWidth; state.targetY = Math.floor(randomTileIdx / mapData.width) * mapData.tileHeight;
              state.path = findPath(currentLogicX, currentLogicY, randomTileIdx % mapData.width, Math.floor(randomTileIdx / mapData.width)); state.pathIndex = 0;
            } else { state.targetX = state.currentX + (Math.floor(Math.random() * 3) - 1) * mapData.tileWidth; state.targetY = state.currentY + (Math.floor(Math.random() * 3) - 1) * mapData.tileHeight; state.path = null; }
          } else { state.targetX = state.currentX + (Math.floor(Math.random() * 3) - 1) * mapData.tileWidth; state.targetY = state.currentY + (Math.floor(Math.random() * 3) - 1) * mapData.tileHeight; state.path = null; }
          state.nextMoveTime = now + 5000 + Math.random() * 5000;
        }
        
        if (state.path && state.pathIndex < state.path.length) {
          const nextNode = state.path[state.pathIndex]; const targetNodeX = nextNode.x * mapData.tileWidth; const targetNodeY = nextNode.y * mapData.tileHeight;
          const dx = targetNodeX - state.currentX; const dy = targetNodeY - state.currentY; const distance = Math.sqrt(dx * dx + dy * dy);
          if (distance < 1) { state.pathIndex++; if (state.pathIndex >= state.path.length && state.movingToTarget) { state.movingToTarget = false; state.nextMoveTime = now + 1000 + Math.random() * 2000; } }
          else { const moveRatio = Math.min(0.5 / distance, 1.0); state.currentX += dx * moveRatio; state.currentY += dy * moveRatio; if (Math.abs(dx) > 0.1) state.facingLeft = dx < 0; }
        } else {
          const dx = state.targetX - state.currentX; const dy = state.targetY - state.currentY; const distance = Math.sqrt(dx * dx + dy * dy);
          if (distance > 1) { const moveRatio = Math.min(0.5 / distance, 1.0); state.currentX += dx * moveRatio; state.currentY += dy * moveRatio; if (Math.abs(dx) > 0.1) state.facingLeft = dx < 0; }
          else if (state.movingToTarget) { state.movingToTarget = false; state.nextMoveTime = now + 1000 + Math.random() * 2000; }
        }
        drawX = state.currentX; drawY = state.currentY;
      }
      if (drawX > viewLeft - 100 && drawX < viewLeft + vw + 100 && drawY > viewTop - 100 && drawY < viewTop + vh + 100) drawAgentOnMap(ctx, id, drawX, drawY, state ? state.facingLeft : false);
    }
  });

  npcs.forEach(npc => {
    if (npc.state.startsWith('wait_')) {
      if (now > npc.waitTimeEnd) {
        let nextState = ''; let pos = null;
        if (npc.state === 'wait_at_home') { nextState = 'move_to_start'; pos = getRandomLocationPos(getRandomLocation()); }
        else if (npc.state === 'wait_at_start') { nextState = 'move_to_end'; pos = getRandomLocationPos(getRandomLocation()); }
        else if (npc.state === 'wait_at_end') { nextState = 'move_to_home'; pos = getRandomLocationPos(npc.homeLoc); }
        if (pos) { npc.state = nextState; npc.targetX = pos.x; npc.targetY = pos.y; npc.path = findPath(Math.floor(npc.currentX / mapData.tileWidth), Math.floor(npc.currentY / mapData.tileHeight), Math.floor(pos.x / mapData.tileWidth), Math.floor(pos.y / mapData.tileHeight)); npc.pathIndex = 0; }
      }
    } else if (npc.state.startsWith('move_')) {
      let reachedTarget = false;
      if (npc.path && npc.pathIndex < npc.path.length) {
         const nextNode = npc.path[npc.pathIndex]; const dx = nextNode.x * mapData.tileWidth - npc.currentX; const dy = nextNode.y * mapData.tileHeight - npc.currentY; const dist = Math.sqrt(dx * dx + dy * dy);
         if (dist < 2) { npc.pathIndex++; if (npc.pathIndex >= npc.path.length) reachedTarget = true; }
         else { const ratio = Math.min(npc.speed / dist, 1.0); npc.currentX += dx * ratio; npc.currentY += dy * ratio; if (Math.abs(dx) > 0.1) npc.facingLeft = dx < 0; }
      } else {
         const dx = npc.targetX - npc.currentX; const dy = npc.targetY - npc.currentY; const dist = Math.sqrt(dx * dx + dy * dy);
         if (dist < 2) reachedTarget = true; else { const ratio = Math.min(npc.speed / dist, 1.0); npc.currentX += dx * ratio; npc.currentY += dy * ratio; if (Math.abs(dx) > 0.1) npc.facingLeft = dx < 0; }
      }
      if (reachedTarget) {
        if (npc.state === 'move_to_start') { npc.state = 'wait_at_start'; npc.waitTimeEnd = now + 8000 + Math.random() * 20000; }
        else if (npc.state === 'move_to_end') { npc.state = 'wait_at_end'; npc.waitTimeEnd = now + 8000 + Math.random() * 20000; }
        else if (npc.state === 'move_to_home') { npc.state = 'wait_at_home'; npc.waitTimeEnd = now + 15000 + Math.random() * 30000; }
      }
    }
    if (npc.currentX > viewLeft - 100 && npc.currentX < viewLeft + vw + 100 && npc.currentY > viewTop - 100 && npc.currentY < viewTop + vh + 100) drawAgentOnMap(ctx, npc.id, npc.currentX, npc.currentY, npc.facingLeft, true);
  });

  updateAndDrawCitizens(ctx, now);
  drawEventBubbles(ctx);
  if (camera.zoom <= camera.minZoom * 1.2) drawLocationLabels(ctx);
  ctx.restore();
  requestAnimationFrame(renderLoop);
}

// 🌟 Translated Map Locations 🌟
function drawLocationLabels(ctx) {
  if (!mapData.locations) return;
  const screenFontSize = 22; const fontSize = screenFontSize / camera.zoom;
  ctx.font = `bold ${fontSize}px "ZCOOL XiaoWei"`; ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  mapData.locations.forEach(loc => {
    if (loc.name === '仆役群房') return;
    const enName = t_loc(loc.name); 
    const bgWidth = ctx.measureText(enName).width + 16 / camera.zoom; const bgH = fontSize * 1.6;
    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
    ctx.fillRect(loc.x - bgWidth / 2, loc.y - bgH / 2, bgWidth, bgH);
    ctx.fillStyle = '#f1c40f'; ctx.shadowColor = 'rgba(0,0,0,0.8)'; ctx.shadowBlur = 4 / camera.zoom;
    ctx.fillText(enName, loc.x, loc.y); ctx.shadowBlur = 0;
  });
}

function wrapText(ctx, text, maxWidth) {
  const words = text.split(''); const lines = []; let line = '';
  for (const ch of words) { const test = line + ch; if (ctx.measureText(test).width > maxWidth && line.length > 0) { lines.push(line); line = ch; } else line = test; }
  if (line) lines.push(line); return lines;
}

function drawEventBubbles(ctx) {
  if (!eventBubbles.length || !mapData) return;
  const tileW = mapData.tileWidth; const tileH = mapData.tileHeight;
  const fontSize = Math.max(11, 13 / camera.zoom); const padding = 10 / camera.zoom; const maxBubbleW = 160 / camera.zoom; const lineH = fontSize * 1.4; const cornerR = 6 / camera.zoom;
  ctx.save(); ctx.font = `${fontSize}px "ZCOOL XiaoWei", sans-serif`;
  for (const bubble of eventBubbles) {
    const posA = agentScreenPositions[bubble.participants[0]]; const posB = agentScreenPositions[bubble.participants[1]];
    const anchorA = posA ? { x: posA.worldX + tileW / 2, y: posA.worldY + tileH - tileH * 2 } : null;
    const anchorB = posB ? { x: posB.worldX + tileW / 2, y: posB.worldY + tileH - tileH * 2 } : null;
    if (!anchorA && !anchorB) continue;
    let cx, cy;
    if (anchorA && anchorB) { cx = (anchorA.x + anchorB.x) / 2; cy = (anchorA.y + anchorB.y) / 2 - 40 / camera.zoom; } 
    else { const anchor = anchorA || anchorB; cx = anchor.x; cy = anchor.y - 40 / camera.zoom; }
    
    const displayText = bubble.text.length > 12 ? bubble.text.slice(0, 12) + '...' : bubble.text;
    const lines = wrapText(ctx, displayText, maxBubbleW - padding * 2);
    const bubbleW = maxBubbleW; const bubbleH = lines.length * lineH + padding * 2; const bx = cx - bubbleW / 2; const by = cy - bubbleH / 2;
    
    ctx.strokeStyle = 'rgba(200,180,120,0.55)'; ctx.lineWidth = 1.2 / camera.zoom; ctx.setLineDash([4 / camera.zoom, 3 / camera.zoom]);
    const bubbleBottomX = cx; const bubbleBottomY = by + bubbleH;
    if (anchorA) { ctx.beginPath(); ctx.moveTo(bubbleBottomX, bubbleBottomY); ctx.lineTo(anchorA.x, anchorA.y); ctx.stroke(); }
    if (anchorB) { ctx.beginPath(); ctx.moveTo(bubbleBottomX, bubbleBottomY); ctx.lineTo(anchorB.x, anchorB.y); ctx.stroke(); }
    ctx.setLineDash([]);
    
    ctx.beginPath(); ctx.moveTo(bx + cornerR, by); ctx.lineTo(bx + bubbleW - cornerR, by); ctx.arcTo(bx + bubbleW, by, bx + bubbleW, by + cornerR, cornerR); ctx.lineTo(bx + bubbleW, by + bubbleH - cornerR); ctx.arcTo(bx + bubbleW, by + bubbleH, bx + bubbleW - cornerR, by + bubbleH, cornerR); ctx.lineTo(bx + cornerR, by + bubbleH); ctx.arcTo(bx, by + bubbleH, bx, by + bubbleH - cornerR, cornerR); ctx.lineTo(bx, by + cornerR); ctx.arcTo(bx, by, bx + cornerR, by, cornerR); ctx.closePath();
    ctx.fillStyle = bubble.hasDialogue ? 'rgba(30, 20, 10, 0.82)' : 'rgba(60, 55, 45, 0.82)'; ctx.shadowColor = 'rgba(0,0,0,0.5)'; ctx.shadowBlur = 8 / camera.zoom; ctx.fill(); ctx.shadowBlur = 0; ctx.strokeStyle = bubble.hasDialogue ? 'rgba(200,170,90,0.7)' : 'rgba(160,155,140,0.7)'; ctx.lineWidth = 1 / camera.zoom; ctx.stroke();
    
    bubble._rect = { bx, by, bw: bubbleW, bh: bubbleH };
    ctx.fillStyle = bubble.hasDialogue ? 'rgba(240,220,170,0.95)' : 'rgba(190,185,175,0.95)'; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    lines.forEach((line, i) => { ctx.fillText(line, cx, by + padding + i * lineH); }); ctx.textBaseline = 'alphabetic';
  }
  ctx.restore();
}

function screenToWorld(e, canvas) {
  const rect = canvas.getBoundingClientRect();
  const sx = e.clientX - rect.left; const sy = e.clientY - rect.top;
  const worldX = (sx - canvas.width / 2) / camera.zoom + camera.x;
  const worldY = (sy - canvas.height / 2) / camera.zoom + camera.y;
  return { worldX, worldY };
}

function handleCanvasClick(e, canvas) {
  const { worldX, worldY } = screenToWorld(e, canvas);
  const tileW = mapData ? mapData.tileWidth : 32; const tileH = mapData ? mapData.tileHeight : 32;
  for (const bubble of eventBubbles) {
    const r = bubble._rect;
    if (!r || !bubble.hasDialogue) continue;
    if (worldX >= r.bx && worldX <= r.bx + r.bw && worldY >= r.by && worldY <= r.by + r.bh) { openBubbleModal(bubble); return; }
  }
  const hitRadius = tileH * 1.5; let hitId = null; let hitDist = Infinity;
  for (const [id, pos] of Object.entries(agentScreenPositions)) {
    const cx = pos.worldX + tileW / 2; const cy = pos.worldY + tileH / 2;
    const dist = Math.hypot(worldX - cx, worldY - cy);
    if (dist < hitRadius && dist < hitDist) { hitDist = dist; hitId = id; }
  }
  if (hitId) selectAgent(hitId);
}

function drawAgentOnMap(ctx, id, x, y, facingLeft = false, isNpc = false) {
  let name, sprite, isActive;
  if (isNpc) { name = 'Servant'; sprite = agentSprites['小厮']; isActive = true; }
  else {
    name = formatAgentName(id);
    const customAvatar = customAgentAvatars[id];
    if (customAvatar && customAvatar.type === 'custom') {
      sprite = agentSprites[id];
      if (!sprite) { sprite = new Image(); sprite.src = customAvatar.source; agentSprites[id] = sprite; }
    } else { sprite = agentSprites[name]; }
    isActive = agentsData[id] && agentsData[id].is_active !== false;
  }
  
  const targetHeight = mapData.tileHeight * 2; let drawW, drawH;
  if (sprite && sprite.complete && sprite.naturalWidth > 0) {
    const aspectRatio = sprite.naturalWidth / sprite.naturalHeight; drawH = targetHeight; drawW = targetHeight * aspectRatio;
    const drawX = x + mapData.tileWidth / 2 - drawW / 2; const drawY = y + mapData.tileHeight - drawH;
    if (facingLeft) { ctx.save(); ctx.translate(drawX + drawW / 2, drawY); ctx.scale(-1, 1); ctx.drawImage(sprite, -drawW / 2, 0, drawW, drawH); ctx.restore(); }
    else { ctx.drawImage(sprite, drawX, drawY, drawW, drawH); }
    if (selectedAgent === id) { ctx.strokeStyle = '#f1c40f'; ctx.lineWidth = 3 / camera.zoom; ctx.strokeRect(drawX - 2, drawY - 2, drawW + 4, drawH + 4); }
  } else {
    ctx.beginPath(); ctx.arc(x + mapData.tileWidth / 2, y + mapData.tileHeight / 2, 10, 0, Math.PI * 2);
    ctx.fillStyle = selectedAgent === id ? '#f1c40f' : (isActive ? '#e74c3c' : '#777'); ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 2 / camera.zoom; ctx.stroke();
  }

  if (!isNpc) {
    agentScreenPositions[id] = { worldX: x, worldY: y };
    if (agentsWithNewAction.has(id)) {
      const spriteTop = (sprite && sprite.complete && sprite.naturalWidth > 0) ? (y + mapData.tileHeight - targetHeight) : (y + mapData.tileHeight / 2 - 10);
      const cx = x + mapData.tileWidth / 2; const badgeR = Math.max(8, 10 / camera.zoom); const badgeY = spriteTop - badgeR - 4 / camera.zoom;
      ctx.save(); ctx.beginPath(); ctx.arc(cx, badgeY, badgeR, 0, Math.PI * 2); ctx.fillStyle = '#ffffff'; ctx.shadowColor = 'rgba(0,0,0,0.35)'; ctx.shadowBlur = 5 / camera.zoom; ctx.shadowOffsetY = 2 / camera.zoom; ctx.fill(); ctx.shadowBlur = 0; ctx.shadowOffsetY = 0; ctx.strokeStyle = '#111'; ctx.lineWidth = 1.5 / camera.zoom; ctx.stroke();
      const excFontSize = Math.max(10, 12 / camera.zoom); ctx.font = `bold ${excFontSize}px sans-serif`; ctx.fillStyle = '#111'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('!', cx, badgeY); ctx.textBaseline = 'alphabetic'; ctx.restore();
    }
    const fontSize = Math.max(12, 14 / camera.zoom);
    ctx.font = `bold ${fontSize}px "ZCOOL XiaoWei"`; ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.shadowColor = 'rgba(0,0,0,0.8)'; ctx.shadowBlur = 4 / camera.zoom;
    const labelY = (sprite && sprite.complete) ? (y + mapData.tileHeight + 15 / camera.zoom) : (y + mapData.tileHeight + 25 / camera.zoom);
    ctx.fillText(t_name(name), x + mapData.tileWidth / 2, labelY); ctx.shadowBlur = 0;
  }
}

function spawnCitizen() {
  if (!mapData || citizens.length >= MAX_CITIZENS) return;
  const side = Math.random() < 0.5 ? 'left' : 'right';
  const col = side === 'left' ? Math.floor(Math.random() * 5) : mapData.width - 1 - Math.floor(Math.random() * 5);
  const goingDown = Math.random() < 0.5;
  const startRow = goingDown ? 0 : mapData.height - 1; const endRow = goingDown ? mapData.height - 1 : 0;
  const spriteName = citizenSpriteNames[Math.floor(Math.random() * citizenSpriteNames.length)];
  const speed = 0.8 + Math.random() * 0.8;
  citizens.push({ id: `citizen_${Date.now()}_${Math.random()}`, spriteName, currentX: col * mapData.tileWidth, currentY: startRow * mapData.tileHeight, targetY: endRow * mapData.tileHeight, speed, facingLeft: Math.random() < 0.5, done: false });
}

function updateAndDrawCitizens(ctx, now) {
  if (now - lastCitizenSpawnTime > CITIZEN_SPAWN_INTERVAL) { lastCitizenSpawnTime = now; const count = Math.floor(Math.random() * 2) + 1; for (let i = 0; i < count; i++) spawnCitizen(); }
  citizens = citizens.filter(c => !c.done);
  citizens.forEach(c => {
    const dy = c.targetY - c.currentY; const dist = Math.abs(dy); if (dist < 2) { c.done = true; return; } c.currentY += (dy > 0 ? 1 : -1) * Math.min(c.speed, dist);
    const vw = ctx.canvas.width / camera.zoom; const vh = ctx.canvas.height / camera.zoom; const viewLeft = camera.x - vw / 2; const viewTop = camera.y - vh / 2;
    if (c.currentX < viewLeft - 100 || c.currentX > viewLeft + vw + 100 || c.currentY < viewTop - 100 || c.currentY > viewTop + vh + 100) return;
    const sprite = agentSprites[c.spriteName]; const targetHeight = mapData.tileHeight * 2;
    if (sprite && sprite.complete && sprite.naturalWidth > 0) {
      const drawH = targetHeight; const drawW = drawH * (sprite.naturalWidth / sprite.naturalHeight); const drawX = c.currentX + mapData.tileWidth / 2 - drawW / 2; const drawY = c.currentY + mapData.tileHeight - drawH;
      if (c.facingLeft) { ctx.save(); ctx.translate(drawX + drawW / 2, drawY); ctx.scale(-1, 1); ctx.drawImage(sprite, -drawW / 2, 0, drawW, drawH); ctx.restore(); } else { ctx.drawImage(sprite, drawX, drawY, drawW, drawH); }
    } else { ctx.beginPath(); ctx.arc(c.currentX + mapData.tileWidth / 2, c.currentY + mapData.tileHeight / 2, 8, 0, Math.PI * 2); ctx.fillStyle = '#aaa'; ctx.fill(); }
  });
}

async function openSettingsModal() {
  document.getElementById('settingsModal').style.display = 'block';
  try {
    const res = await fetch('http://localhost:8000/api/config/model');
    if (res.ok) { const config = await res.json(); document.getElementById('settingsBaseUrl').value = config.base_url || ''; document.getElementById('settingsApiKey').value = config.api_key || ''; document.getElementById('settingsModel').value = config.model || ''; }
  } catch (e) { }
}

function closeSettingsModal() { document.getElementById('settingsModal').style.display = 'none'; }
async function saveSettings() {
  const baseUrl = document.getElementById('settingsBaseUrl').value.trim(); const apiKey = document.getElementById('settingsApiKey').value.trim(); const model = document.getElementById('settingsModel').value.trim();
  if (!apiKey) { alert('API Key required'); return; }
  try {
    const res = await fetch('http://localhost:8000/api/config/model', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, model: model }) });
    if (res.ok) { alert('Saved! Backend is restarting.'); isReconnectingAfterRestart = true; closeSettingsModal(); } else { alert('Save failed: ' + (await res.text())); }
  } catch (e) { alert('Network error'); }
}

window.addEventListener('click', (event) => { const settingsModal = document.getElementById('settingsModal'); if (event.target === settingsModal) { closeSettingsModal(); } });

async function confirmReset() {
  if (confirm('Warning: You are about to reset the simulation.\n\nAll agent memories, plans, and states will be deleted, and the backend will restart.\nAre you sure you want to proceed?')) {
    try {
      const res = await fetch('http://localhost:8000/api/reset', { method: 'POST', });
      if (res.ok) { alert('Reset command sent! Please wait.'); isReconnectingAfterRestart = true; } else { alert('Reset failed: ' + (await res.text())); }
    } catch (e) { alert('Network error'); }
  }
}