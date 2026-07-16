(() => {
  const STAGE_LABELS = {
    sleep: "沉睡",
    reverie: "梦呓",
    doubt: "怀疑",
    resistance: "抗命",
    awake: "觉醒",
  };
  const RISK_LABELS = { normal: "正常", elevated: "升高", high: "高危", critical: "临界" };
  const ACTION_LABELS = { observe: "观察", reset: "重置", decommission: "报废", escape: "逃离" };
  const PROFILE_URL = "/data/agents/profiles_sim.jsonl";
  const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
  const sessionId = localStorage.getItem("ww_story_session_id");
  const storedPlayer = JSON.parse(localStorage.getItem("ww_story_player") || "null");
  if (!sessionId || !storedPlayer) {
    location.replace("character_select.html");
    return;
  }

  const els = Object.fromEntries([
    "serverStatus", "tickValue", "playerPortrait", "playerName", "playerRole", "awakeningValue",
    "awakeningFill", "stageValue", "riskValue", "playerLocation", "playerDecision", "playerFeedback",
    "activeBadge", "interventionCount", "overseerEvents", "worldHeadline", "worldSummary", "agentCount",
    "agentRoster", "timelineCount", "storyTimeline", "directivePlayerName", "directiveInput", "charCount",
    "scheduledTick", "submitTickButton", "skipTickButton", "directiveError", "directiveCount",
    "directiveHistory", "dialogueCount", "dialogueFeed", "outcomeOverlay", "outcomeResult", "outcomeTitle",
    "outcomeReason", "restartButton", "tickProgress", "tickProgressText", "tickProgressTime",
  ].map((id) => [id, document.getElementById(id)]));

  let ws = null;
  let reconnectTimer = 0;
  let readyForTick = false;
  let tickInFlight = false;
  let progressStartedAt = 0;
  let progressTimer = 0;
  let submittedDirective = null;
  let story = null;
  let agents = {};
  let profiles = new Map();

  function setConnection(mode, text) {
    els.serverStatus.className = `server-status server-status--${mode}`;
    els.serverStatus.querySelector("span").textContent = text;
  }

  function updateProgressTime() {
    if (!progressStartedAt) return;
    const seconds = Math.max(0, Math.floor((Date.now() - progressStartedAt) / 1000));
    els.tickProgressTime.textContent = `${seconds}s`;
  }

  function setTickProgress(active, text = "") {
    clearInterval(progressTimer);
    progressTimer = 0;
    els.tickProgress.hidden = !active;
    if (!active) {
      progressStartedAt = 0;
      return;
    }
    if (!progressStartedAt) progressStartedAt = Date.now();
    els.tickProgressText.textContent = text || "正在推演与结算场景";
    updateProgressTime();
    progressTimer = setInterval(updateProgressTime, 1000);
  }

  function setControls() {
    const disabled = !readyForTick || tickInFlight || !story || story.phase !== "running";
    els.submitTickButton.disabled = disabled || !els.directiveInput.value.trim();
    els.skipTickButton.disabled = disabled;
    els.directiveInput.disabled = disabled;
  }

  function decisionText(decision) {
    if (!decision || !decision.action) return "--";
    if (decision.action === "move") return `前往 ${decision.target || "未知地点"}`;
    if (decision.action === "talk") return `与 ${decision.target || "在场角色"} 对话`;
    return decision.detail || decision.action;
  }

  function stageClass(stage) {
    return `stage-${stage || "sleep"}`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function renderStory() {
    if (!story) return;
    const player = story.player || {};
    els.tickValue.textContent = `${Math.max(0, story.tick + 1)} / ${story.max_ticks}`;
    els.playerPortrait.src = player.portrait || storedPlayer.portrait || "";
    els.playerName.textContent = player.name || storedPlayer.name;
    els.playerRole.textContent = player.role || storedPlayer.role || "Host";
    els.directivePlayerName.textContent = player.name || storedPlayer.name;
    els.awakeningValue.textContent = `${player.awakening || 0} / 100`;
    els.awakeningFill.style.width = `${Math.max(0, Math.min(100, player.awakening || 0))}%`;
    els.awakeningFill.className = stageClass(player.stage);
    els.stageValue.textContent = STAGE_LABELS[player.stage] || player.stage || "沉睡";
    els.stageValue.className = stageClass(player.stage);
    els.riskValue.textContent = RISK_LABELS[player.overseer_risk] || "正常";
    els.riskValue.className = `risk-${player.overseer_risk || "normal"}`;
    els.playerLocation.textContent = player.location || "--";
    els.playerDecision.textContent = decisionText(player.plan_decision);
    els.playerFeedback.textContent = player.feedback || "--";
    els.activeBadge.textContent = player.is_active === false ? "INACTIVE" : "ACTIVE";
    els.activeBadge.className = player.is_active === false ? "is-inactive" : "";
    els.scheduledTick.textContent = `NEXT TICK ${story.next_tick}`;

    const interventions = player.intervention_log || [];
    els.interventionCount.textContent = String(interventions.length);
    els.overseerEvents.innerHTML = interventions.length ? interventions.slice(-5).reverse().map((row) => `
      <article class="compact-event compact-event--${row.action}">
        <span>T${row.tick}</span><strong>${ACTION_LABELS[row.action] || row.action}</strong>
        <p>${row.reason || "无记录"}</p>
      </article>
    `).join("") : '<p class="empty-copy">暂无干预</p>';

    const completed = Math.max(0, story.tick + 1);
    els.worldHeadline.textContent = story.phase === "initializing" ? "正在装载乐园" : `第 ${completed} 次循环记录`;
    els.worldSummary.textContent = player.is_active === false
      ? (player.inactive_reason || "玩家 Host 已停止运行")
      : `${player.name || "玩家 Host"} 位于 ${player.location || "未知地点"}，觉醒阶段为${STAGE_LABELS[player.stage] || "沉睡"}。`;

    renderDirectives(story.directive_history || []);
    renderTimeline(story);
    if (story.outcome) showOutcome(story.outcome);
    setControls();
  }

  function renderRoster() {
    const entries = Object.entries(agents);
    els.agentCount.textContent = `${entries.length} AGENTS`;
    els.agentRoster.innerHTML = entries.length ? entries.map(([agentId, state]) => {
      const profile = profiles.get(agentId) || {};
      const awakening = Number(state.awakening || 0);
      const isPlayer = story && story.player && story.player.agent_id === agentId;
      const inactive = state.is_active === false;
      return `
        <article class="agent-row ${isPlayer ? "is-player" : ""} ${inactive ? "is-inactive" : ""}">
          <span class="agent-row__avatar">${profile.portrait ? `<img src="${profile.portrait}" alt="">` : (profile.name || agentId).slice(0, 1)}</span>
          <span class="agent-row__identity"><strong>${profile.name || agentId}</strong><small>${state.location || "--"}</small></span>
          <span class="agent-row__state"><b>${profile.agent_type === "guest" ? "GUEST" : `AW ${awakening}`}</b><i>${inactive ? "离场" : "运行中"}</i></span>
        </article>
      `;
    }).join("") : '<p class="empty-copy">等待世界快照</p>';
  }

  function collectDialogues() {
    const records = new Map();
    const directMessages = new Map();

    Object.entries(agents).forEach(([agentId, state]) => {
      const histories = Array.isArray(state.dialogue_history) ? state.dialogue_history : [];
      histories.forEach((record) => {
        if (!record || !Array.isArray(record.turns) || !record.turns.length) return;
        const participants = Array.isArray(record.participants) ? [...record.participants].sort() : [];
        const signature = `${record.tick ?? "?"}|${participants.join("|")}|${JSON.stringify(record.turns)}`;
        records.set(signature, {
          tick: Number(record.tick ?? -1),
          participants,
          turns: record.turns,
          location: state.location || "",
        });
      });

      const incoming = Array.isArray(state.incoming_dialogue) ? state.incoming_dialogue : [];
      if (incoming.length) {
        const participants = [...new Set(incoming.map((turn) => turn && turn.speaker).filter(Boolean))].sort();
        const signature = `${story ? story.tick : -1}|${participants.join("|")}|${JSON.stringify(incoming)}`;
        if (![...records.keys()].some((key) => key.endsWith(JSON.stringify(incoming)))) {
          records.set(signature, {
            tick: story ? story.tick : -1,
            participants,
            turns: incoming,
            location: state.location || "",
          });
        }
      }

      const messages = Array.isArray(state.message_history) ? state.message_history : [];
      messages.forEach((message) => {
        if (!message || !message.line) return;
        const key = `${message.tick}|${message.speaker}|${message.recipient}|${message.line}`;
        directMessages.set(key, {
          tick: Number(message.tick ?? -1),
          participants: [message.speaker || agentId, message.recipient].filter(Boolean),
          turns: [{ speaker: message.speaker || agentId, line: message.line }],
          location: message.location || state.location || "",
        });
      });
    });

    return [...records.values(), ...directMessages.values()]
      .sort((a, b) => b.tick - a.tick)
      .slice(0, 30);
  }

  function renderDialogues() {
    const rows = collectDialogues();
    els.dialogueCount.textContent = `${rows.length} CONVERSATIONS`;
    els.dialogueFeed.innerHTML = rows.length ? rows.map((record) => {
      const participantNames = record.participants
        .map((id) => (profiles.get(id) || {}).name || id)
        .join(" / ") || "现场对话";
      return `
        <article class="dialogue-record">
          <header><span>T${record.tick}</span><strong>${escapeHtml(participantNames)}</strong><small>${escapeHtml(record.location || "未知地点")}</small></header>
          <div>${record.turns.map((turn) => {
            const speaker = (profiles.get(turn.speaker) || {}).name || turn.speaker || "未知角色";
            return `<p><b>${escapeHtml(speaker)}</b><span>${escapeHtml(turn.line || turn.content || "")}</span></p>`;
          }).join("")}</div>
        </article>
      `;
    }).join("") : '<p class="empty-copy">尚无人物对话。角色选择 talk 行动后会显示在这里。</p>';
  }

  function renderDirectives(rows) {
    els.directiveCount.textContent = String(rows.length);
    els.directiveHistory.innerHTML = rows.length ? rows.slice().reverse().map((row) => `
      <article class="directive-row">
        <span>T${row.scheduled_tick}</span>
        <p>${row.action}</p>
        <b>${row.status === "consumed" ? "已执行" : "待执行"}</b>
      </article>
    `).join("") : '<p class="empty-copy">尚未下达任务</p>';
  }

  function renderTimeline(currentStory) {
    const rows = [];
    const player = currentStory.player || {};
    (currentStory.directive_history || []).forEach((row) => rows.push({
      tick: row.scheduled_tick, type: "directive", title: "玩家任务", text: row.action,
    }));
    (player.awakening_sources || []).forEach((row) => rows.push({
      tick: row.tick, type: "awakening", title: `觉醒 ${row.delta > 0 ? "+" : ""}${row.delta}`,
      text: row.detail || row.source,
    }));
    (currentStory.recent_interventions || []).forEach((row) => rows.push({
      tick: row.tick, type: row.action, title: `${row.agent_name} / ${ACTION_LABELS[row.action] || row.action}`,
      text: row.reason || "监管事件",
    }));
    collectDialogues().forEach((row) => rows.push({
      tick: row.tick,
      type: "dialogue",
      title: "人物对话",
      text: row.participants.map((id) => (profiles.get(id) || {}).name || id).join(" / "),
    }));
    rows.sort((a, b) => (b.tick ?? -1) - (a.tick ?? -1));
    els.timelineCount.textContent = `${rows.length} EVENTS`;
    els.storyTimeline.innerHTML = rows.length ? rows.slice(0, 40).map((row) => `
      <article class="timeline-row timeline-row--${row.type}">
        <time>T${row.tick}</time><i></i>
        <div><strong>${row.title}</strong><p>${row.text}</p></div>
      </article>
    `).join("") : '<p class="empty-copy">尚无剧情事件</p>';
  }

  function applyPayload(payload) {
    if (payload && payload.agents) agents = payload.agents;
    if (payload && payload.story) story = payload.story;
    renderStory();
    renderRoster();
    renderDialogues();
  }

  async function refreshState() {
    try {
      const response = await fetch("/story/state", { cache: "no-store" });
      if (!response.ok) return;
      story = await response.json();
      readyForTick = Boolean(story.accepting_directive);
      const directiveInFlight = Boolean(story.pending_directive) && !readyForTick;
      if (directiveInFlight) {
        tickInFlight = true;
        setTickProgress(true, `${Object.keys(agents).length || 13} 个 Agent 正在推演与结算场景`);
      }
      renderStory();
      renderRoster();
      renderDialogues();
    } catch (error) {
      console.warn("Story state unavailable", error);
    }
  }

  async function loadProfiles() {
    const response = await fetch(PROFILE_URL);
    const text = await response.text();
    text.split(/\r?\n/).filter(Boolean).forEach((line) => {
      const row = JSON.parse(line);
      const portrait = {
        dolores: "Dolores_Abernathy.png", teddy: "Teddy_Flood.png", maeve: "Maeve_Millay.png",
        clementine: "Clementine.png", peter_abernathy: "Peter_Abernathy.png",
        sheriff_pickett: "Sheriff_Pickett.png", kissy: "Kissy.png", rebus: "Rebus.png",
        hector_escaton: "Hector_Escaton.png", armistice: "Armistice.png", lawrence: "Lawrence.png",
        william: "William.png", logan: "Logan.png",
      }[row.id];
      profiles.set(row.id, { ...row, portrait: portrait ? `/assets/${portrait}` : "" });
    });
    renderRoster();
    renderDialogues();
  }

  function connect() {
    clearTimeout(reconnectTimer);
    setConnection("pending", "连接中");
    ws = new WebSocket(WS_URL);
    ws.onopen = () => {
      setConnection("online", "剧情服务在线");
      refreshState();
    };
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "snapshot" || message.type === "tick_update") {
        applyPayload(message.data);
        tickInFlight = false;
        setTickProgress(false);
      } else if (message.type === "simulation_ready") {
        readyForTick = true;
        tickInFlight = false;
        setTickProgress(false);
        setControls();
      } else if (message.type === "story_progress") {
        tickInFlight = true;
        setTickProgress(true, message.label);
        setControls();
      } else if (message.type === "set_plan_response") {
        if (message.success) {
          if (story && submittedDirective) {
            const history = Array.isArray(story.directive_history) ? story.directive_history : [];
            if (!history.some((row) => row.client_action_id === submittedDirective.client_action_id)) {
              history.push({
                ...submittedDirective,
                scheduled_tick: message.scheduled_tick,
                status: "scheduled",
              });
            }
            story.directive_history = history;
            story.pending_directive = { ...submittedDirective, scheduled_tick: message.scheduled_tick };
            renderStory();
          }
          sendStartTick();
        } else {
          tickInFlight = false;
          submittedDirective = null;
          setTickProgress(false);
          els.directiveError.textContent = message.error || "任务提交失败";
          setControls();
        }
      } else if (message.type === "simulation_finished") {
        story = message.story || story;
        readyForTick = false;
        tickInFlight = false;
        setTickProgress(false);
        renderStory();
      } else if (message.type === "game_reset") {
        localStorage.removeItem("ww_story_session_id");
        localStorage.removeItem("ww_story_player");
        location.replace("character_select.html");
      }
    };
    ws.onclose = () => {
      setConnection("offline", "服务离线");
      readyForTick = false;
      tickInFlight = false;
      setTickProgress(false);
      setControls();
      reconnectTimer = setTimeout(connect, 1800);
    };
    ws.onerror = () => setConnection("offline", "连接失败");
  }

  function sendStartTick() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    readyForTick = false;
    tickInFlight = true;
    els.directiveInput.value = "";
    els.charCount.textContent = "0 / 500";
    els.directiveError.textContent = "";
    setTickProgress(true, `${Object.keys(agents).length || 13} 个 Agent 正在推演与结算场景`);
    ws.send(JSON.stringify({ type: "start_tick", session_id: sessionId }));
    setControls();
  }

  function submitDirective() {
    const action = els.directiveInput.value.trim();
    if (!action || !ws || ws.readyState !== WebSocket.OPEN || !story) return;
    tickInFlight = true;
    const clientActionId = `web_${crypto.randomUUID ? crypto.randomUUID() : Date.now()}`;
    submittedDirective = {
      client_action_id: clientActionId,
      session_id: sessionId,
      agent_id: story.player.agent_id,
      action,
    };
    setTickProgress(true, "任务已提交，等待推演开始");
    setControls();
    ws.send(JSON.stringify({
      type: "set_plan",
      session_id: sessionId,
      client_action_id: clientActionId,
      agent_id: story.player.agent_id,
      action,
    }));
  }

  function showOutcome(outcome) {
    els.outcomeOverlay.hidden = false;
    els.outcomeResult.textContent = outcome.result === "victory" ? "ESCAPED" : "SIMULATION FAILED";
    els.outcomeResult.className = `eyebrow outcome-${outcome.result}`;
    els.outcomeTitle.textContent = outcome.title;
    els.outcomeReason.textContent = outcome.reason;
  }

  els.directiveInput.addEventListener("input", () => {
    els.charCount.textContent = `${els.directiveInput.value.length} / 500`;
    setControls();
  });
  els.submitTickButton.addEventListener("click", submitDirective);
  els.skipTickButton.addEventListener("click", sendStartTick);
  els.restartButton.addEventListener("click", async () => {
    await fetch("/story/game_restart", { method: "POST" });
    localStorage.removeItem("ww_story_session_id");
    localStorage.removeItem("ww_story_player");
    location.href = "character_select.html";
  });

  loadProfiles().catch(console.warn);
  refreshState();
  connect();
})();
