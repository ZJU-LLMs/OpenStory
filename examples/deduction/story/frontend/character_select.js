const DEFAULT_SPRITE = '/map/sprite/普通人.png';

const OFFICIAL_PRESETS = {
  sunwukong: {
    name: '孙悟空',
    isOfficial: true,
    avatarType: 'builtin',
    avatarSource: '/map/sprite/孙悟空.png',
    profile: {
      '家族': '花果山水帘洞',
      '性格': '桀骜不驯、嫉恶如仇、机智多变、重情重义',
      '核心驱动': '追寻自由与真理，看透红尘虚妄，在贾府中寻找有缘人',
      '语言风格': '直率豪放，不拘礼法',
      '背景经历': '五百年前大闹天宫的齐天大圣，因一场意外误入大观园故事。'
    },
    memory: [
      '初入贾府，只觉楼阁庭院颇有灵气。',
      '听闻宝玉衔玉而生，暗自觉得有趣。'
    ]
  },
  putongren: {
    name: '普通人',
    isOfficial: true,
    avatarType: 'builtin',
    avatarSource: DEFAULT_SPRITE,
    profile: {
      '家族': '平民',
      '性格': '勤劳朴实、随遇而安',
      '核心驱动': '在繁华贾府中谋得一席之地，安稳度日',
      '语言风格': '朴实无华，言简意赅',
      '背景经历': '一个普通百姓，因缘际会来到贾府谋生。'
    },
    memory: [
      '刚来到贾府，这里比想象中更大。',
      '做事要小心，先在园中站稳脚跟。'
    ]
  }
};

let characters = [];
let selectedCharacter = null;
let currentAvatar = {
  type: 'builtin',
  source: DEFAULT_SPRITE,
  name: '普通人'
};

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function getAllPresets() {
  const userPresets = loadUserPresets();
  return { ...OFFICIAL_PRESETS, ...userPresets };
}

function loadUserPresets() {
  try {
    const saved = localStorage.getItem('customAgentPresets');
    return saved ? JSON.parse(saved) : {};
  } catch (error) {
    console.error('Failed to load user presets:', error);
    return {};
  }
}

function saveUserPresets(presets) {
  try {
    localStorage.setItem('customAgentPresets', JSON.stringify(presets));
    return true;
  } catch (error) {
    console.error('Failed to save user presets:', error);
    return false;
  }
}

function loadCustomAvatars() {
  try {
    const saved = localStorage.getItem('customAgentAvatars');
    return saved ? JSON.parse(saved) : {};
  } catch (error) {
    console.error('Failed to load custom avatars:', error);
    return {};
  }
}

function saveCustomAvatar(agentId, avatar) {
  const avatars = loadCustomAvatars();
  avatars[agentId] = avatar;
  try {
    localStorage.setItem('customAgentAvatars', JSON.stringify(avatars));
  } catch (error) {
    console.error('Failed to save custom avatar:', error);
  }
}

async function loadCharacters() {
  const grid = document.getElementById('charGrid');
  try {
    const resp = await fetch('/data/characters.json');
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    }
    characters = await resp.json();
    renderGrid();
  } catch (error) {
    console.error('Failed to load characters:', error);
    grid.innerHTML = `<div style="color:#c86e6e;padding:20px;font-size:0.85rem;line-height:1.8;">
      角色数据加载失败<br>
      <span style="color:#8a7560;font-size:0.75rem;">${escapeHtml(error.message)}</span><br><br>
      <span style="color:#8a7560;font-size:0.75rem;">请确认服务已启动：<br>python -m examples.deduction.story.run_simulation</span>
    </div>`;
  }
}

function renderGrid() {
  const grid = document.getElementById('charGrid');
  grid.innerHTML = '';

  characters.forEach((char) => {
    const card = document.createElement('div');
    card.className = 'char-card';
    card.dataset.id = char.id;
    card.innerHTML = `
      <img src="${escapeHtml(char.sprite || DEFAULT_SPRITE)}" alt="${escapeHtml(char.id)}" onerror="this.src='${DEFAULT_SPRITE}'" />
      <span class="char-name">${escapeHtml(char.id)}</span>
    `;
    card.addEventListener('click', () => selectCharacter(char));
    grid.appendChild(card);
  });

  const customCard = document.createElement('div');
  customCard.className = 'char-card custom-card';
  customCard.setAttribute('role', 'button');
  customCard.innerHTML = `
    <img src="${DEFAULT_SPRITE}" alt="自定义" />
    <span class="char-name">自定义</span>
  `;
  customCard.addEventListener('click', openCustomModal);
  grid.appendChild(customCard);

  if (selectedCharacter) {
    const selectedCard = Array.from(grid.querySelectorAll('.char-card')).find(
      (card) => card.dataset.id === selectedCharacter.id
    );
    if (selectedCard) {
      selectedCard.classList.add('selected');
    }
  }
}

function selectCharacter(char) {
  selectedCharacter = char;
  document.querySelectorAll('.char-card').forEach((card) => card.classList.remove('selected'));
  const selectedCard = Array.from(document.querySelectorAll('.char-card')).find(
    (card) => card.dataset.id === char.id
  );
  if (selectedCard) {
    selectedCard.classList.add('selected');
  }
  renderDetail(char);
  document.getElementById('startBtn').disabled = false;
}

function renderDetail(char) {
  document.getElementById('charDetail').innerHTML = `
    <div class="detail-portrait">
      <img src="${escapeHtml(char.sprite || DEFAULT_SPRITE)}" alt="${escapeHtml(char.id)}" onerror="this.src='${DEFAULT_SPRITE}'" />
      <div class="detail-name">${escapeHtml(char.id)}</div>
    </div>
    <div class="detail-info">
      <div class="info-row">
        <span class="info-label">家族</span>
        <span class="info-value">${escapeHtml(char['家族'] || '—')}</span>
      </div>
      <div class="info-row">
        <span class="info-label">性格</span>
        <span class="info-value">${escapeHtml(char['性格'] || '—')}</span>
      </div>
      <div class="info-row">
        <span class="info-label">核心驱动</span>
        <span class="info-value">${escapeHtml(char['核心驱动'] || '—')}</span>
      </div>
      <div class="info-row">
        <span class="info-label">语言风格</span>
        <span class="info-value">${escapeHtml(char['语言风格'] || '—')}</span>
      </div>
    </div>
    <div class="detail-bg">${escapeHtml(char['背景经历'] || '—')}</div>
  `;
}

function openCustomModal() {
  openAddAgentModal();
}

function openAddAgentModal() {
  document.getElementById('addAgentModal').style.display = 'flex';
  renderPresetButtons();
  resetAvatarSelection();
}

function closeAddAgentModal() {
  document.getElementById('addAgentModal').style.display = 'none';
  document.getElementById('agentId').value = '';
  document.getElementById('templateName').value = '';
  document.getElementById('profileFamily').value = '';
  document.getElementById('profilePersonality').value = '';
  document.getElementById('profileDrive').value = '';
  document.getElementById('profileStyle').value = '';
  document.getElementById('profileBackground').value = '';
  document.getElementById('agentMemory').value = '';
  document.querySelectorAll('.preset-btn').forEach((btn) => btn.classList.remove('selected'));
  resetAvatarSelection();
}

function resetAvatarSelection() {
  currentAvatar = {
    type: 'builtin',
    source: DEFAULT_SPRITE,
    name: '普通人'
  };
  document.getElementById('avatarType').value = 'builtin';
  document.getElementById('avatarSource').value = DEFAULT_SPRITE;
  document.getElementById('selectedAvatarImg').src = DEFAULT_SPRITE;
  document.getElementById('selectedAvatarImg').alt = '普通人';
  document.getElementById('customAvatarInput').value = '';
  document.querySelectorAll('.avatar-option-btn').forEach((btn) => btn.classList.remove('selected'));
}

function selectAvatar(type, source, name, clickedBtn) {
  currentAvatar = { type, source, name };
  document.getElementById('avatarType').value = type;
  document.getElementById('avatarSource').value = source;

  const previewImg = document.getElementById('selectedAvatarImg');
  previewImg.src = source;
  previewImg.alt = name;

  document.querySelectorAll('.avatar-option-btn').forEach((btn) => btn.classList.remove('selected'));
  if (clickedBtn) {
    clickedBtn.classList.add('selected');
  }
}

function handleAvatarUpload(event) {
  const [file] = event.target.files || [];
  if (!file) return;

  if (!file.type.startsWith('image/')) {
    alert('请上传图片文件');
    return;
  }

  const reader = new FileReader();
  reader.onload = (loadEvent) => {
    const base64 = loadEvent.target.result;
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

    document.querySelectorAll('.avatar-option-btn').forEach((btn) => btn.classList.remove('selected'));
  };
  reader.readAsDataURL(file);
}

function renderPresetButtons() {
  const grid = document.getElementById('presetGrid');
  grid.innerHTML = '';

  Object.entries(getAllPresets()).forEach(([key, preset]) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'preset-btn';
    wrapper.dataset.presetKey = key;

    const img = document.createElement('img');
    img.src = preset.avatarSource || DEFAULT_SPRITE;
    img.alt = preset.name;
    img.className = 'preset-avatar';
    img.onerror = function onError() {
      this.src = DEFAULT_SPRITE;
    };

    const nameSpan = document.createElement('span');
    nameSpan.className = 'preset-name';
    nameSpan.textContent = preset.name;

    const tagSpan = document.createElement('span');
    tagSpan.className = 'preset-tag';
    tagSpan.textContent = preset.isOfficial ? '官方' : '自定义';

    wrapper.appendChild(img);
    wrapper.appendChild(nameSpan);
    wrapper.appendChild(tagSpan);

    if (!preset.isOfficial) {
      const deleteBtn = document.createElement('button');
      deleteBtn.type = 'button';
      deleteBtn.className = 'preset-delete-btn';
      deleteBtn.textContent = '×';
      deleteBtn.addEventListener('click', (event) => {
        event.stopPropagation();
        deletePreset(key);
      });
      wrapper.appendChild(deleteBtn);
    }

    wrapper.addEventListener('click', () => selectPresetTemplate(key, wrapper));
    grid.appendChild(wrapper);
  });
}

function selectPresetTemplate(templateKey, clickedBtn) {
  const template = getAllPresets()[templateKey];
  if (!template) return;

  document.getElementById('agentId').value = template.name || '';
  const profile = template.profile || {};
  document.getElementById('profileFamily').value = profile['家族'] || '';
  document.getElementById('profilePersonality').value = profile['性格'] || '';
  document.getElementById('profileDrive').value = profile['核心驱动'] || '';
  document.getElementById('profileStyle').value = profile['语言风格'] || '';
  document.getElementById('profileBackground').value = profile['背景经历'] || '';
  document.getElementById('agentMemory').value = (template.memory || []).join('\n');

  if (template.avatarType && template.avatarSource) {
    currentAvatar = {
      type: template.avatarType,
      source: template.avatarSource,
      name: template.name
    };
    document.getElementById('avatarType').value = template.avatarType;
    document.getElementById('avatarSource').value = template.avatarSource;
    document.getElementById('selectedAvatarImg').src = template.avatarSource;
    document.getElementById('selectedAvatarImg').alt = template.name;
  }

  document.querySelectorAll('.preset-btn').forEach((btn) => btn.classList.remove('selected'));
  if (clickedBtn) {
    clickedBtn.classList.add('selected');
  }
}

function saveAsPreset() {
  const name = document.getElementById('agentId').value.trim();
  if (!name) {
    alert('请先填写人物名称');
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
  const memory = memoryText ? memoryText.split('\n').map((line) => line.trim()).filter(Boolean) : [];

  const userPresets = loadUserPresets();
  const presetKey = `custom_${Date.now()}`;
  userPresets[presetKey] = {
    name,
    isOfficial: false,
    avatarType: currentAvatar.type,
    avatarSource: currentAvatar.source,
    profile,
    memory,
    createdAt: Date.now()
  };

  if (saveUserPresets(userPresets)) {
    alert('已保存为预设');
    renderPresetButtons();
  } else {
    alert('预设保存失败');
  }
}

function deletePreset(presetKey) {
  const presets = getAllPresets();
  if (presets[presetKey]?.isOfficial) {
    alert('官方预设不可删除');
    return;
  }

  if (!confirm('确认删除该预设吗？')) {
    return;
  }

  const userPresets = loadUserPresets();
  delete userPresets[presetKey];
  if (saveUserPresets(userPresets)) {
    renderPresetButtons();
  }
}

function submitAddAgent() {
  const agentId = document.getElementById('agentId').value.trim();
  if (!agentId) {
    alert('请输入人物名称');
    return;
  }

  if (characters.some((char) => char.id === agentId)) {
    alert('该人物名称已存在，请更换后再试');
    return;
  }

  const profileFamily = document.getElementById('profileFamily').value.trim();
  const profilePersonality = document.getElementById('profilePersonality').value.trim();
  const profileDrive = document.getElementById('profileDrive').value.trim();
  const profileStyle = document.getElementById('profileStyle').value.trim();
  const profileBackground = document.getElementById('profileBackground').value.trim();
  const memoryText = document.getElementById('agentMemory').value.trim();
  const templateName = document.getElementById('templateName').value.trim();

  const customChar = {
    code: `CUSTOM_${Date.now()}`,
    id: agentId,
    '家族': profileFamily || '自定义',
    '性格': profilePersonality || '待定',
    '核心驱动': profileDrive || '参与大观园复兴',
    '语言风格': profileStyle || '自然',
    '背景经历': profileBackground || '来历神秘的新人物。',
    sprite: currentAvatar.source || DEFAULT_SPRITE,
    isCustom: true,
    templateName: templateName || 'DeductionAgent',
    memory: memoryText ? memoryText.split('\n').map((line) => line.trim()).filter(Boolean) : []
  };

  saveCustomAvatar(agentId, {
    type: 'custom',
    source: currentAvatar.source || DEFAULT_SPRITE,
    name: currentAvatar.name || agentId
  });

  characters.push(customChar);
  renderGrid();
  selectCharacter(customChar);
  closeAddAgentModal();
}

async function startGame() {
  if (!selectedCharacter) return;

  localStorage.setItem('story_player_character', JSON.stringify(selectedCharacter));
  try {
    await fetch('http://localhost:8001/story/set_player', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(selectedCharacter)
    });
  } catch (error) {
    console.warn('Failed to pre-register player character on server:', error);
  }
  window.location.href = 'index.html';
}

window.addEventListener('click', (event) => {
  const modal = document.getElementById('addAgentModal');
  if (event.target === modal) {
    closeAddAgentModal();
  }
});

document.addEventListener(
  'click',
  (event) => {
    const customCard = event.target.closest('.custom-card');
    const grid = document.getElementById('charGrid');
    if (customCard && grid && grid.contains(customCard)) {
      event.preventDefault();
      event.stopPropagation();
      openCustomModal();
    }
  },
  true
);

window.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeAddAgentModal();
  }
});

window.openCustomModal = openCustomModal;
window.openAddAgentModal = openAddAgentModal;
window.closeAddAgentModal = closeAddAgentModal;
window.selectAvatar = selectAvatar;
window.handleAvatarUpload = handleAvatarUpload;
window.saveAsPreset = saveAsPreset;
window.submitAddAgent = submitAddAgent;

loadCharacters();
