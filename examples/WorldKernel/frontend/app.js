let currentSpec = null;
let activeTab = 'intent';

async function submitInput() {
  const input = document.getElementById('worldInput').value.trim();
  if (!input) return;

  setStatus(true, '解析中…');
  hideResult();
  hideError();

  try {
    const resp = await fetch('/api/stage1/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || '请求失败');
    }

    currentSpec = await resp.json();
    setStatus(false);
    showResult(currentSpec);
  } catch (e) {
    setStatus(false);
    showError(e.message);
  }
}

function setStatus(loading, text = '') {
  const section = document.getElementById('statusSection');
  const btn = document.getElementById('submitBtn');
  section.style.display = loading ? 'flex' : 'none';
  document.getElementById('statusText').textContent = text;
  btn.disabled = loading;
}

function hideResult() { document.getElementById('resultSection').style.display = 'none'; }
function hideError()  { document.getElementById('errorSection').style.display = 'none'; }

function showError(msg) {
  const s = document.getElementById('errorSection');
  s.style.display = 'block';
  document.getElementById('errorText').textContent = '错误：' + msg;
}

function showResult(spec) {
  document.getElementById('resultSection').style.display = 'block';
  document.getElementById('sessionId').textContent = 'session: ' + spec.meta?.session_id;
  showTab(activeTab);
}

function showTab(name) {
  activeTab = name;
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.textContent.toLowerCase().includes(name) || t.onclick?.toString().includes(`'${name}'`));
  });
  // reset active based on onclick attr
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => {
    if (t.getAttribute('onclick') === `showTab('${name}')`) t.classList.add('active');
  });

  const content = document.getElementById('tabContent');
  if (!currentSpec) return;

  switch (name) {
    case 'intent':       content.innerHTML = renderIntent(currentSpec.intent); break;
    case 'world_type':   content.innerHTML = renderWorldType(currentSpec.world_type); break;
    case 'generation_plan': content.innerHTML = renderPlan(currentSpec.generation_plan); break;
    case 'ontology':     content.innerHTML = renderOntology(currentSpec.ontology); break;
    case 'raw':          content.innerHTML = `<pre>${escHtml(JSON.stringify(currentSpec, null, 2))}</pre>`; break;
  }
}

function renderIntent(intent) {
  if (!intent) return '<p style="color:#64748b">暂无数据</p>';
  const rows = [
    ['原始输入', escHtml(intent.raw_text)],
    ['世界名称', escHtml(intent.world_name_hint)],
    ['来源提示', escHtml(intent.source_hint)],
    ['用户目标', escHtml(intent.user_goal)],
    ['风格', `<span class="tag">${escHtml(intent.style)}</span>`],
    ['约束条件', (intent.constraints || []).map(c => `<span class="tag">${escHtml(c)}</span>`).join('') || '无'],
    ['不确定信息', (intent.uncertain_slots || []).map(s => `<div style="color:#f59e0b;font-size:.85rem;margin:.15rem 0">⚠ ${escHtml(s)}</div>`).join('') || '无'],
  ];
  return `<table class="kv-table">${rows.map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table>`;
}

function renderWorldType(wt) {
  if (!wt) return '<p style="color:#64748b">暂无数据</p>';
  const pct = Math.round((wt.confidence || 0) * 100);
  return `
    <table class="kv-table">
      <tr><td>主类型</td><td><span class="tag">${escHtml(wt.primary)}</span></td></tr>
      <tr><td>次类型</td><td>${wt.secondary ? `<span class="tag">${escHtml(wt.secondary)}</span>` : '—'}</td></tr>
      <tr><td>置信度</td><td>
        ${pct}%
        <div class="confidence-bar"><div class="confidence-fill" style="width:${pct}%"></div></div>
      </td></tr>
      <tr><td>标签</td><td>${(wt.tags || []).map(t => `<span class="tag">${escHtml(t)}</span>`).join('')}</td></tr>
    </table>`;
}

function renderPlan(plan) {
  if (!plan?.steps?.length) return '<p style="color:#64748b">暂无数据</p>';
  const items = plan.steps.map((s, i) => `
    <li class="step-item">
      <span class="step-num">${i + 1}</span>
      <div>
        <div class="step-name">${escHtml(s.name)}</div>
        <div class="step-target">${escHtml(s.target)}</div>
      </div>
    </li>`).join('');
  return `<ul class="step-list">${items}</ul>`;
}

function renderOntology(ontology) {
  if (!ontology) return '<p style="color:#64748b">暂无数据</p>';
  const types = (ontology.entity_types || []).map(t => `<span class="tag">${escHtml(t)}</span>`).join('');
  const schemas = Object.entries(ontology.schemas || {}).map(([type, fields]) => {
    const fieldRows = Object.entries(fields).map(([f, t]) =>
      `<tr><td style="padding:.2rem .5rem;color:#94a3b8;font-family:monospace;font-size:.8rem">${escHtml(f)}</td><td style="padding:.2rem .5rem;color:#64748b;font-size:.8rem">${escHtml(String(t))}</td></tr>`
    ).join('');
    return `<div style="margin-top:1rem">
      <div style="color:#a78bfa;font-size:.9rem;margin-bottom:.4rem">${escHtml(type)}</div>
      <table style="width:100%;border-collapse:collapse">${fieldRows}</table>
    </div>`;
  }).join('');
  return `<div><div style="margin-bottom:.75rem">${types}</div>${schemas}</div>`;
}

function escHtml(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

document.getElementById('worldInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submitInput();
});
