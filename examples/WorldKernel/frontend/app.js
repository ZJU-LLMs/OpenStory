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

    const data = await resp.json();
    setStatus(false);
    showResult(data);
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

function showResult(session) {
  document.getElementById('resultSection').style.display = 'block';
  document.getElementById('sessionId').textContent = 'session: ' + session.session_id;
  document.getElementById('resultMsg').textContent =
    '已提交至后端，生成文件保存在 worlds/generated/' + session.session_id + '/';
}

document.getElementById('worldInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submitInput();
});
