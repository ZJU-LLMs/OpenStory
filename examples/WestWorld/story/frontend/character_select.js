(() => {
  const grid = document.getElementById("hostGrid");
  const count = document.getElementById("hostCount");
  const status = document.getElementById("serverStatus");
  const startButton = document.getElementById("startButton");
  const errorBox = document.getElementById("selectionError");
  let characters = [];
  let selected = null;

  function setStatus(mode, text) {
    status.className = `server-status server-status--${mode}`;
    status.querySelector("span").textContent = text;
  }

  function initials(name) {
    return String(name || "?").trim().slice(0, 1).toUpperCase();
  }

  function selectCharacter(character) {
    selected = character;
    document.querySelectorAll(".host-card").forEach((card) => {
      card.classList.toggle("is-selected", card.dataset.agentId === character.agent_id);
    });
    const image = document.getElementById("detailPortrait");
    image.src = character.portrait;
    image.alt = character.name;
    image.hidden = !character.portrait;
    document.getElementById("detailInitial").hidden = Boolean(character.portrait);
    document.getElementById("detailInitial").textContent = initials(character.name);
    document.getElementById("detailName").textContent = character.name;
    document.getElementById("detailRole").textContent = character.role;
    document.getElementById("detailAwakening").textContent = `${character.initial_awakening}/100`;
    document.getElementById("detailPersona").textContent = character.persona || "--";
    document.getElementById("detailBackground").textContent = character.background || "--";
    startButton.disabled = false;
    errorBox.textContent = "";
  }

  function renderCharacters() {
    count.textContent = `${characters.length} HOSTS`;
    grid.innerHTML = "";
    characters.forEach((character) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "host-card";
      card.dataset.agentId = character.agent_id;
      card.innerHTML = `
        <span class="host-card__portrait">
          ${character.portrait ? `<img src="${character.portrait}" alt="">` : `<b>${initials(character.name)}</b>`}
        </span>
        <span class="host-card__copy">
          <strong>${character.name}</strong>
          <small>${character.role}</small>
        </span>
        <span class="host-card__awakening">AW ${character.initial_awakening}</span>
      `;
      card.addEventListener("click", () => selectCharacter(character));
      grid.appendChild(card);
    });
  }

  async function loadCharacters() {
    try {
      const response = await fetch("/story/characters", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      characters = payload.characters || [];
      renderCharacters();
      setStatus("online", "剧情服务在线");
    } catch (error) {
      console.error(error);
      grid.innerHTML = '<p class="loading-copy loading-copy--error">剧情服务未启动</p>';
      setStatus("offline", "服务离线");
    }
  }

  startButton.addEventListener("click", async () => {
    if (!selected) return;
    startButton.disabled = true;
    startButton.querySelector("span").textContent = "正在初始化";
    try {
      const response = await fetch("/story/set_player", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_id: "awakening_escape", agent_id: selected.agent_id }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "选角失败");
      localStorage.setItem("ww_story_session_id", payload.session_id);
      localStorage.setItem("ww_story_player", JSON.stringify(selected));
      window.location.href = "index.html";
    } catch (error) {
      errorBox.textContent = error.message;
      startButton.disabled = false;
      startButton.querySelector("span").textContent = "进入乐园";
    }
  });

  loadCharacters();
})();
