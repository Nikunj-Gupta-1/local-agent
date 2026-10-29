// ── State ──
let activeConfig = {};
let currentEventSource = null;
let isExecuting = false;

// ── DOM Elements ──
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const stopBtn = document.getElementById("stopBtn");
const messagesContainer = document.getElementById("messagesContainer");
const emptyState = document.getElementById("emptyState");
const projectPill = document.getElementById("projectPill");
const activeProjectName = document.getElementById("activeProjectName");
const currentProviderBadge = document.getElementById("currentProviderBadge");
const headerModelSelect = document.getElementById("headerModelSelect");
const fileList = document.getElementById("fileList");

// Modals & Drawers
const settingsModal = document.getElementById("settingsModal");
const settingsBtn = document.getElementById("settingsBtn");
const closeSettings = document.getElementById("closeSettings");
const saveSettingsBtn = document.getElementById("saveSettingsBtn");

const memoryModal = document.getElementById("memoryModal");
const memoryBtn = document.getElementById("memoryBtn");
const closeMemory = document.getElementById("closeMemory");
const memoryList = document.getElementById("memoryList");
const clearMemoryBtn = document.getElementById("clearMemoryBtn");

const scratchpadDrawer = document.getElementById("scratchpadDrawer");
const scratchpadBtn = document.getElementById("scratchpadBtn");
const closeScratchpad = document.getElementById("closeScratchpad");

// Mode selector buttons
document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const mode = btn.dataset.mode;
    fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ safety_mode: mode }),
    });
  });
});

// ── Startup & Initialization ──
async function init() {
  await loadConfig();
  await loadWorkspaceFiles();
  await refreshModels();
}

async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    if (data.ok) {
      activeConfig = data.config;
      updateUIWithConfig(data);
    }
  } catch (e) {
    console.error("Failed to load config", e);
  }
}

function updateUIWithConfig(data) {
  const prov = (data.active_provider || "ollama").toLowerCase();
  currentProviderBadge.textContent = prov.toUpperCase();
  currentProviderBadge.className = `provider-badge ${prov}`;

  // Mode
  const mode = data.safety_mode || "safe";
  document.querySelectorAll(".mode-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.mode === mode);
  });

  // Project root
  if (data.workspace_roots && data.workspace_roots.length > 0) {
    const path = data.workspace_roots[0];
    const name = path.split("/").pop() || "project";
    activeProjectName.textContent = name;
  }

  // Populate settings form
  document.getElementById("cfgProvider").value = prov;
  document.getElementById("cfgGeminiKey").value = activeConfig.gemini_api_key || "";
  document.getElementById("cfgGeminiModel").value = activeConfig.gemini_model || "gemini-2.5-flash";
  document.getElementById("cfgNvidiaKey").value = activeConfig.nvidia_api_key || "";
  document.getElementById("cfgNvidiaModel").value = activeConfig.nvidia_model || "nvidia/nemotron-3-ultra-550b-a55b";
  document.getElementById("cfgOllamaUrl").value = activeConfig.ollama_url || "http://127.0.0.1:11434";
  document.getElementById("cfgOllamaModel").value = activeConfig.model || "gemma4-e4b-64k:latest";
  document.getElementById("cfgLmUrl").value = activeConfig.openai_base_url || "http://localhost:1234/v1";
  document.getElementById("cfgLmModel").value = activeConfig.lm_model || "local-model";
}

async function refreshModels() {
  try {
    const prov = document.getElementById("cfgProvider").value || "ollama";
    const res = await fetch(`/api/providers/models?provider=${prov}`);
    const data = await res.json();
    headerModelSelect.innerHTML = "";
    if (data.ok && data.models && data.models.length > 0) {
      data.models.forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m;
        opt.textContent = m;
        headerModelSelect.appendChild(opt);
      });
      if (activeConfig.model) {
        headerModelSelect.value = activeConfig.model;
      }
    } else {
      const opt = document.createElement("option");
      opt.value = activeConfig.model || "default";
      opt.textContent = activeConfig.model || "default";
      headerModelSelect.appendChild(opt);
    }
  } catch (e) {
    console.warn("Could not fetch models:", e);
  }
}

async function loadWorkspaceFiles() {
  try {
    const res = await fetch("/api/workspace/files");
    const data = await res.json();
    if (data.ok && data.entries) {
      fileList.innerHTML = "";
      data.entries.slice(0, 20).forEach((item) => {
        const div = document.createElement("div");
        div.className = "file-item";
        div.innerHTML = `<span>${item.type === "dir" ? "📁" : "📄"}</span><span>${item.name}</span>`;
        fileList.appendChild(div);
      });
    }
  } catch (e) {
    fileList.innerHTML = '<div class="file-item">Failed to load files</div>';
  }
}

// ── Provider Testing ──
window.testProvider = async function (provider) {
  const statusEl = document.getElementById(`${provider}TestStatus`);
  statusEl.innerHTML = '<span style="color: var(--accent-cyan);">Testing connection...</span>';

  let payload = { provider };
  if (provider === "gemini") {
    payload.gemini_api_key = document.getElementById("cfgGeminiKey").value;
    payload.model = document.getElementById("cfgGeminiModel").value;
  } else if (provider === "nvidia") {
    payload.nvidia_api_key = document.getElementById("cfgNvidiaKey").value;
    payload.model = document.getElementById("cfgNvidiaModel").value;
  } else if (provider === "ollama") {
    payload.ollama_url = document.getElementById("cfgOllamaUrl").value;
    payload.model = document.getElementById("cfgOllamaModel").value;
  } else if (provider === "lmstudio") {
    payload.openai_base_url = document.getElementById("cfgLmUrl").value;
    payload.model = document.getElementById("cfgLmModel").value;
  }

  try {
    const res = await fetch("/api/providers/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.ok) {
      statusEl.innerHTML = `<span style="color: var(--accent-green);">✓ ${data.message}</span>`;
    } else {
      statusEl.innerHTML = `<span style="color: var(--accent-red);">✗ ${data.message}</span>`;
    }
  } catch (e) {
    statusEl.innerHTML = `<span style="color: var(--accent-red);">✗ Error: ${e.message}</span>`;
  }
};

// ── Save Settings ──
saveSettingsBtn.addEventListener("click", async () => {
  const payload = {
    provider: document.getElementById("cfgProvider").value,
    gemini_api_key: document.getElementById("cfgGeminiKey").value,
    gemini_model: document.getElementById("cfgGeminiModel").value,
    nvidia_api_key: document.getElementById("cfgNvidiaKey").value,
    nvidia_model: document.getElementById("cfgNvidiaModel").value,
    ollama_url: document.getElementById("cfgOllamaUrl").value,
    openai_base_url: document.getElementById("cfgLmUrl").value,
  };

  const currentProv = payload.provider;
  if (currentProv === "gemini") payload.model = payload.gemini_model;
  else if (currentProv === "nvidia") payload.model = payload.nvidia_model;
  else if (currentProv === "ollama") payload.model = document.getElementById("cfgOllamaModel").value;
  else if (currentProv === "lmstudio") payload.model = document.getElementById("cfgLmModel").value;

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.ok) {
      await loadConfig();
      await refreshModels();
      settingsModal.classList.remove("open");
    }
  } catch (e) {
    alert("Error saving settings: " + e.message);
  }
});

// ── Send Message & SSE Streaming ──
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendBtn.addEventListener("click", sendMessage);

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || isExecuting) return;

  chatInput.value = "";
  if (emptyState) emptyState.style.display = "none";

  // 1. Render User Bubble
  const userRow = document.createElement("div");
  userRow.className = "message-row user";
  userRow.innerHTML = `<div class="user-bubble">${escapeHtml(text)}</div>`;
  messagesContainer.appendChild(userRow);

  // 2. Prepare Agent Container
  const agentRow = document.createElement("div");
  agentRow.className = "message-row";
  const agentContainer = document.createElement("div");
  agentContainer.className = "agent-container";
  agentRow.appendChild(agentContainer);
  messagesContainer.appendChild(agentRow);

  isExecuting = true;
  stopBtn.style.display = "flex";
  scrollToBottom();

  // Active stream state holders
  let planCard = null;
  let thinkingCard = null;
  let thinkingBody = null;
  let agentTextEl = null;

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: text,
        provider: document.getElementById("cfgProvider").value,
        model: headerModelSelect.value,
      }),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop(); // keep remainder

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const dataStr = line.replace("data: ", "").trim();
        if (!dataStr) continue;

        try {
          const event = JSON.parse(dataStr);
          handleAgentEvent(event, agentContainer, {
            getPlanCard: () => planCard,
            setPlanCard: (c) => (planCard = c),
            getThinkingBody: () => thinkingBody,
            setThinkingCard: (c, b) => {
              thinkingCard = c;
              thinkingBody = b;
            },
            getAgentTextEl: () => agentTextEl,
            setAgentTextEl: (el) => (agentTextEl = el),
          });
        } catch (err) {
          console.error("Error parsing SSE event", err);
        }
      }
    }
  } catch (err) {
    const errDiv = document.createElement("div");
    errDiv.style.color = "var(--accent-red)";
    errDiv.textContent = `Error: ${err.message}`;
    agentContainer.appendChild(errDiv);
  } finally {
    isExecuting = false;
    stopBtn.style.display = "none";
    scrollToBottom();
  }
}

// ── Event Handlers ──
function handleAgentEvent(event, container, refs) {
  const type = event.type;

  // 1. Long-term memory recalled
  if (type === "memory_recalled" && event.items && event.items.length > 0) {
    const pill = document.createElement("div");
    pill.className = "memory-recall-banner";
    pill.innerHTML = `<span>🧠</span><span>Recalled ${event.items.length} past memories for this project</span>`;
    pill.addEventListener("click", () => {
      openMemoryModal(event.items);
    });
    container.appendChild(pill);
    scrollToBottom();
  }

  // 2. Plan Created
  else if (type === "plan_created") {
    let pCard = refs.getPlanCard();
    if (!pCard) {
      pCard = document.createElement("div");
      pCard.className = "plan-card";
      pCard.innerHTML = `
        <div class="plan-header">
          <span>◈ Task Plan (${event.complexity})</span>
          <span style="font-size: 11.5px; color: var(--text-dim);">${event.reasoning || ""}</span>
        </div>
        <div class="subtask-list" id="subtaskList"></div>
      `;
      container.appendChild(pCard);
      refs.setPlanCard(pCard);
    }
    const list = pCard.querySelector("#subtaskList");
    list.innerHTML = "";
    (event.subtasks || []).forEach((st) => {
      const row = document.createElement("div");
      row.className = "subtask-row";
      row.id = `subtask-${st.id}`;
      row.innerHTML = `<span>○</span><span>[${st.id}] ${escapeHtml(st.title)}</span>`;
      list.appendChild(row);
    });
    updateScratchpadView(event.subtasks);
    scrollToBottom();
  }

  // 3. Subtask started
  else if (type === "subtask_start") {
    const pCard = refs.getPlanCard();
    if (pCard) {
      const activeRow = pCard.querySelector(`#subtask-${event.subtask.id}`);
      if (activeRow) {
        activeRow.className = "subtask-row active";
        activeRow.querySelector("span").textContent = "●";
      }
    }
  }

  // 4. Subtask evaluated
  else if (type === "subtask_evaluated") {
    const pCard = refs.getPlanCard();
    if (pCard) {
      const row = pCard.querySelector(`#subtask-${event.subtask_id}`);
      if (row) {
        row.className = "subtask-row done";
        row.querySelector("span").textContent = "✓";
      }
    }
  }

  // 5. Thinking tokens
  else if (type === "thinking") {
    let tBody = refs.getThinkingBody();
    if (!tBody) {
      const tCard = document.createElement("div");
      tCard.className = "thinking-card";
      tCard.innerHTML = `
        <div class="thinking-header">
          <span style="display: flex; align-items: center; gap: 6px;">
            <span>🧠</span><span>Thinking Process</span>
          </span>
          <span style="font-size: 11px;">(click to toggle)</span>
        </div>
        <div class="thinking-body"></div>
      `;
      tCard.querySelector(".thinking-header").addEventListener("click", () => {
        const body = tCard.querySelector(".thinking-body");
        body.style.display = body.style.display === "none" ? "block" : "none";
      });
      container.appendChild(tCard);
      tBody = tCard.querySelector(".thinking-body");
      refs.setThinkingCard(tCard, tBody);
    }
    tBody.textContent += event.content;
    tBody.scrollTop = tBody.scrollHeight;
    scrollToBottom();
  }

  // 6. Text Tokens
  else if (type === "token") {
    let textEl = refs.getAgentTextEl();
    if (!textEl) {
      textEl = document.createElement("div");
      textEl.className = "agent-text";
      container.appendChild(textEl);
      refs.setAgentTextEl(textEl);
    }
    textEl.textContent += event.content;
    scrollToBottom();
  }

  // 7. Tool Confirmation Required (Safe / Strict Mode)
  else if (type === "tool_approval_required") {
    const toolCard = document.createElement("div");
    toolCard.className = "tool-card";
    toolCard.innerHTML = `
      <div class="tool-card-header">
        <span class="tool-name-badge">
          <span>⚙</span><span>${escapeHtml(event.name)}</span>
        </span>
        <span style="color: var(--accent-yellow); font-size: 11.5px; font-weight: 500;">Approval Required</span>
      </div>
      <div class="tool-card-body">
        <div class="terminal-box">${escapeHtml(JSON.stringify(event.args, null, 2))}</div>
      </div>
      <div class="tool-approval-actions">
        <button class="btn-authorize" id="auth-${event.action_id}">Authorize</button>
        <button class="btn-reject" id="rej-${event.action_id}">Reject</button>
      </div>
    `;
    container.appendChild(toolCard);
    scrollToBottom();

    document.getElementById(`auth-${event.action_id}`).addEventListener("click", () => {
      respondToAction(event.action_id, true);
      toolCard.querySelector(".tool-approval-actions").innerHTML = '<span style="color: var(--accent-green); font-size: 12px; font-weight: 600;">✓ Authorized</span>';
    });

    document.getElementById(`rej-${event.action_id}`).addEventListener("click", () => {
      respondToAction(event.action_id, false);
      toolCard.querySelector(".tool-approval-actions").innerHTML = '<span style="color: var(--accent-red); font-size: 12px; font-weight: 600;">✗ Rejected</span>';
    });
  }

  // 8. Tool Executing / Result
  else if (type === "tool_result") {
    const card = document.createElement("div");
    card.className = "tool-card";
    const ok = event.result && event.result.ok !== false;
    card.innerHTML = `
      <div class="tool-card-header">
        <span class="tool-name-badge">
          <span>⚙</span><span>${escapeHtml(event.name)}</span>
        </span>
        <span style="color: ${ok ? 'var(--accent-green)' : 'var(--accent-red)'}; font-size: 11px;">
          ${ok ? '[OK]' : '[ERROR]'}
        </span>
      </div>
      <div class="tool-card-body">
        <div class="terminal-box">${escapeHtml(JSON.stringify(event.result, null, 2))}</div>
      </div>
    `;
    container.appendChild(card);
    scrollToBottom();
  }

  // 9. Ask User Question
  else if (type === "ask_user") {
    const askCard = document.createElement("div");
    askCard.className = "tool-card";
    askCard.innerHTML = `
      <div class="tool-card-header" style="background: rgba(0, 210, 255, 0.08);">
        <span style="color: var(--accent-cyan); display: flex; align-items: center; gap: 6px;">
          <span>❓</span><span>Agent Asks</span>
        </span>
      </div>
      <div class="tool-card-body">
        <div style="font-size: 13.5px; font-weight: 500; margin-bottom: 8px;">${escapeHtml(event.question)}</div>
        <div style="display: flex; gap: 8px;">
          <input type="text" class="config-input" id="ask-input-${event.action_id}" placeholder="Type your answer..." style="flex: 1;">
          <button class="btn-authorize" id="ask-btn-${event.action_id}">Submit</button>
        </div>
      </div>
    `;
    container.appendChild(askCard);
    scrollToBottom();

    const input = document.getElementById(`ask-input-${event.action_id}`);
    const btn = document.getElementById(`ask-btn-${event.action_id}`);
    btn.addEventListener("click", () => {
      const val = input.value.trim();
      respondToAction(event.action_id, true, val);
      askCard.querySelector(".tool-card-body").innerHTML = `<div style="color: var(--text-muted); font-size: 12.5px;">Answered: "${escapeHtml(val)}"</div>`;
    });
  }

  // 10. Task Completed
  else if (type === "complete") {
    if (event.scratchpad) {
      updateScratchpadFull(event.scratchpad);
    }
  }
}

async function respondToAction(actionId, approved, answer = "") {
  await fetch("/api/action/respond", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action_id: actionId, approved, answer }),
  });
}

// Interrupt Button
stopBtn.addEventListener("click", async () => {
  await fetch("/api/interrupt", { method: "POST" });
  stopBtn.style.display = "none";
});

// ── Modals & Drawers ──
settingsBtn.addEventListener("click", () => settingsModal.classList.add("open"));
closeSettings.addEventListener("click", () => settingsModal.classList.remove("open"));

scratchpadBtn.addEventListener("click", () => scratchpadDrawer.classList.toggle("open"));
closeScratchpad.addEventListener("click", () => scratchpadDrawer.classList.remove("open"));

memoryBtn.addEventListener("click", () => openMemoryModal());
closeMemory.addEventListener("click", () => memoryModal.classList.remove("open"));

async function openMemoryModal(highlightItems = null) {
  memoryModal.classList.add("open");
  memoryList.innerHTML = '<div style="color: var(--text-dim); font-size: 13px;">Loading memories...</div>';

  try {
    const res = await fetch("/api/memory");
    const data = await res.json();
    if (data.ok && data.memories) {
      memoryList.innerHTML = "";
      if (data.memories.length === 0) {
        memoryList.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">No memories indexed yet. Memories are automatically recorded as the agent completes tasks!</div>';
        return;
      }
      data.memories.forEach((m) => {
        const item = document.createElement("div");
        item.style.background = "var(--bg-card)";
        item.style.border = "1px solid var(--border-subtle)";
        item.style.borderRadius = "8px";
        item.style.padding = "10px 14px";
        item.style.display = "flex";
        item.style.justifyContent = "space-between";
        item.style.alignItems = "center";
        item.innerHTML = `
          <div>
            <span style="font-size: 11px; text-transform: uppercase; font-weight: 600; color: #c084fc;">${m.category || "info"}</span>
            <div style="font-size: 13px; margin-top: 4px; color: var(--text-main);">${escapeHtml(m.content)}</div>
            <div style="font-size: 11px; color: var(--text-dim); margin-top: 4px;">${m.timestamp ? m.timestamp.split("T")[0] : ""}</div>
          </div>
          <button class="btn-reject" style="padding: 2px 8px; font-size: 11px;" onclick="deleteMemory('${m.id}')">Delete</button>
        `;
        memoryList.appendChild(item);
      });
    }
  } catch (e) {
    memoryList.innerHTML = `<div style="color: var(--accent-red);">Error loading memories: ${e.message}</div>`;
  }
}

window.deleteMemory = async function (id) {
  await fetch(`/api/memory/${id}`, { method: "DELETE" });
  openMemoryModal();
};

clearMemoryBtn.addEventListener("click", async () => {
  if (confirm("Are you sure you want to clear all long-term memories for this project?")) {
    await fetch("/api/memory/clear", { method: "POST" });
    openMemoryModal();
  }
});

function updateScratchpadView(subtasks) {
  const planBox = document.getElementById("scratchpadPlan");
  if (planBox && subtasks) {
    planBox.innerHTML = "";
    subtasks.forEach((st) => {
      const d = document.createElement("div");
      d.textContent = `[ ] ${st.title}`;
      planBox.appendChild(d);
    });
  }
}

function updateScratchpadFull(pad) {
  document.getElementById("scratchpadGoal").textContent = pad.goal || "(none)";
  const planBox = document.getElementById("scratchpadPlan");
  planBox.innerHTML = "";
  (pad.plan || []).forEach((st) => {
    const d = document.createElement("div");
    d.textContent = `${st.done ? "[x]" : "[ ]"} ${st.title}`;
    planBox.appendChild(d);
  });
  document.getElementById("scratchpadFiles").textContent = (pad.files || []).join(", ") || "(none)";
  document.getElementById("scratchpadDiscoveries").textContent = (pad.discoveries || []).join("\n") || "(none)";
}

function scrollToBottom() {
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

window.addEventListener("DOMContentLoaded", init);
