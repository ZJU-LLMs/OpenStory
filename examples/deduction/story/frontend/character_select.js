let characters = [];
let selectedCharacter = null;

async function loadCharacters() {
  const grid = document.getElementById('charGrid');
  try {
    const resp = await fetch('/data/characters.json');
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    }
    characters = await resp.json();
    renderGrid();
  } catch (e) {
    console.error('Failed to load characters:', e);
    grid.innerHTML = `<div style="color:#c86e6e;padding:20px;font-size:0.85rem;line-height:1.8;">
      角色数据加载失败<br>
      <span style="color:#8a7560;font-size:0.75rem;">${e.message}</span><br><br>
      <span style="color:#8a7560;font-size:0.75rem;">请确认服务器已启动：<br>python -m examples.deduction.story.run_simulation</span>
    </div>`;
  }
}

function renderGrid() {
  const grid = document.getElementById('charGrid');
  grid.innerHTML = '';

  characters.forEach(char => {
    const card = document.createElement('div');
    card.className = 'char-card';
    card.dataset.id = char.id;
    card.innerHTML = `
      <img src="${char.sprite}" alt="${char.id}" onerror="this.src='/map/sprite/普通人.png'" />
      <span class="char-name">${char.id}</span>
    `;
    card.addEventListener('click', () => selectCharacter(char));
    grid.appendChild(card);
  });

  // 自定义角色
  const customCard = document.createElement('div');
  customCard.className = 'char-card custom-card';
  customCard.innerHTML = `
    <img src="/map/sprite/普通人.png" alt="自定义" />
    <span class="char-name">自定义</span>
  `;
  customCard.addEventListener('click', openCustomModal);
  grid.appendChild(customCard);
}

function selectCharacter(char) {
  selectedCharacter = char;
  document.querySelectorAll('.char-card').forEach(c => c.classList.remove('selected'));
  const card = document.querySelector(`.char-card[data-id="${char.id}"]`);
  if (card) card.classList.add('selected');
  renderDetail(char);
  document.getElementById('startBtn').disabled = false;
}

function renderDetail(char) {
  document.getElementById('charDetail').innerHTML = `
    <div class="detail-portrait">
      <img src="${char.sprite}" alt="${char.id}" onerror="this.src='/map/sprite/普通人.png'" />
      <div class="detail-name">${char.id}</div>
    </div>
    <div class="detail-info">
      <div class="info-row">
        <span class="info-label">家族</span>
        <span class="info-value">${char['家族'] || '—'}</span>
      </div>
      <div class="info-row">
        <span class="info-label">性格</span>
        <span class="info-value">${char['性格'] || '—'}</span>
      </div>
      <div class="info-row">
        <span class="info-label">核心驱动</span>
        <span class="info-value">${char['核心驱动'] || '—'}</span>
      </div>
      <div class="info-row">
        <span class="info-label">语言风格</span>
        <span class="info-value">${char['语言风格'] || '—'}</span>
      </div>
    </div>
    <div class="detail-bg">${char['背景经历'] || '—'}</div>
  `;
}

function openCustomModal() {
  // 简单 prompt 交互（可后续升级为弹窗）
  const name = prompt('请输入自定义人物名称：');
  if (!name || !name.trim()) return;
  const customChar = {
    code: 'CUSTOM_' + Date.now(),
    id: name.trim(),
    '家族': '自定义',
    '性格': prompt('性格（可留空）：') || '待定',
    '核心驱动': prompt('核心驱动（可留空）：') || '参与大观园复兴',
    '语言风格': '自然',
    '背景经历': prompt('背景经历（可留空）：') || '来历神秘的人物。',
    sprite: '/map/sprite/普通人.png',
    isCustom: true
  };
  characters.push(customChar);
  renderGrid();
  selectCharacter(customChar);
}

async function startGame() {
  if (!selectedCharacter) return;
  localStorage.setItem('story_player_character', JSON.stringify(selectedCharacter));
  window.location.href = 'index.html';
}

loadCharacters();
