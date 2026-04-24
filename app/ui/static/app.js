const chatLog = document.getElementById("chatLog");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");

const dirInput = document.getElementById("dirInput");
const browseBtn = document.getElementById("browseBtn");
const browseFileBtn = document.getElementById("browseFileBtn");
const setDirBtn = document.getElementById("setDirBtn");
const dirStatus = document.getElementById("dirStatus");

const indexingWrap = document.getElementById("indexingWrap");
const indexingLabel = document.getElementById("indexingLabel");
const indexingPercent = document.getElementById("indexingPercent");
const indexingBar = document.getElementById("indexingBar");
const indexingDetails = document.getElementById("indexingDetails");

const resultsList = document.getElementById("resultsList");
const resultCount = document.getElementById("resultCount");
const clearResultsBtn = document.getElementById("clearResultsBtn");

const selectedList = document.getElementById("selectedList");
const selectedCount = document.getElementById("selectedCount");
const clearDeckBtn = document.getElementById("clearDeckBtn");
const exportDeckBtn = document.getElementById("exportDeckBtn");
const exportStatus = document.getElementById("exportStatus");
const newDeckModal = document.getElementById("newDeckModal");
const newDeckModalSub = document.getElementById("newDeckModalSub");
const newDeckModalMsg = document.getElementById("newDeckModalMsg");
const newDeckYesBtn = document.getElementById("newDeckYesBtn");
const newDeckNoBtn = document.getElementById("newDeckNoBtn");

const openSettingsBtn = document.getElementById("openSettingsBtn");
const closeSettingsBtn = document.getElementById("closeSettingsBtn");
const settingsModal = document.getElementById("settingsModal");

const msAuthArea = document.getElementById("msAuthArea");
const msAuthLabel = document.getElementById("msAuthLabel");
const signOutBtn = document.getElementById("signOutBtn");
const signInModal = document.getElementById("signInModal");
const closeSignInBtn = document.getElementById("closeSignInBtn");
const signInBody = document.getElementById("signInBody");
const fixedDirSection = document.getElementById("fixedDirSection");
const exportDirectoryInput = document.getElementById("exportDirectoryInput");
const browseExportDirBtn = document.getElementById("browseExportDirBtn");
const saveSettingsBtn = document.getElementById("saveSettingsBtn");
const settingsError = document.getElementById("settingsError");
const exportModeInputs = Array.from(document.querySelectorAll('input[name="exportMode"]'));
const teamsIndexingModeInputs = Array.from(document.querySelectorAll('input[name="teamsIndexingMode"]'));
const newDeckModeInputs = Array.from(document.querySelectorAll('input[name="newDeckMode"]'));
const resetDatabaseBtn = document.getElementById("resetDatabaseBtn");

function safeOn(el, eventName, handler) {
  if (el) el.addEventListener(eventName, handler);
}

function updateSetBtnState() {
  if (!setDirBtn) return;
  const current = (dirInput ? dirInput.value : "").trim();
  const applied = (state.lastAppliedInput || "").trim();
  setDirBtn.disabled = !current || current === applied;
}

const state = {
  results: [],
  selected: [],
  indexingPoller: null,
  authPoller: null,
  signInResolve: null,
  signInReject: null,
  pendingTeamsUrl: "",
  pendingNewDeckPath: "",
  preferences: {
    export_mode: "ask",
    export_directory: "",
    teams_indexing_mode: "download",
    new_deck_mode: "ask",
  },
  lastAppliedDirectory: "",
  lastAppliedInput: "",
};

function itemKey(item) {
  return [item.path || "", item.slide_number ?? "", item.reason || ""].join("::");
}

function matchPct(score) {
  // Linear rescale: [SCORE_MIN, SCORE_MAX] → [1%, 99%]
  // SCORE_MIN = search_min_score from settings (retrieval filter — no result below this appears)
  // SCORE_MAX = SCORE_DISPLAY_MAX injected from server via window.SCORE_DISPLAY_MAX
  //             (set SCORE_DISPLAY_MAX in .env to tune; lower = higher displayed percentages)
  const SCORE_MIN = 0.25;
  const SCORE_MAX = (typeof window.SCORE_DISPLAY_MAX === "number") ? window.SCORE_DISPLAY_MAX : 0.50;
  const n = Number(score);
  if (!Number.isFinite(n)) return "—";
  const raw = (n - SCORE_MIN) / (SCORE_MAX - SCORE_MIN) * 100;
  return Math.max(1, Math.min(99, Math.round(raw))) + "%";
}

function basename(path) {
  if (!path) return "";
  const norm = String(path).replaceAll("\\", "/");
  const parts = norm.split("/");
  return parts[parts.length - 1] || norm;
}

function addMsg(role, content) {
  const row = document.createElement("div");
  row.className = `msg ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const text = document.createElement("div");
  text.className = "bubble-text";
  text.textContent = String(content ?? "");

  bubble.appendChild(text);
  row.appendChild(bubble);
  chatLog.appendChild(row);
  chatLog.scrollTop = chatLog.scrollHeight;
}

async function postJSON(url, data) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  const text = await r.text();
  let j;
  try {
    j = JSON.parse(text);
  } catch (e) {
    throw new Error(`Non-JSON response (${r.status}): ${text.slice(0, 160)}`);
  }

  if (!r.ok) throw new Error(j.error || j.detail || `HTTP ${r.status}`);
  return j;
}

async function getJSON(url) {
  const r = await fetch(url);
  const text = await r.text();
  let j;
  try {
    j = JSON.parse(text);
  } catch (e) {
    throw new Error(`Non-JSON response (${r.status}): ${text.slice(0, 160)}`);
  }
  if (!r.ok) throw new Error(j.error || j.detail || `HTTP ${r.status}`);
  return j;
}

function setEmptyState(container, text) {
  container.innerHTML = "";
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.textContent = text;
  container.appendChild(empty);
}

function isSelected(item) {
  const key = itemKey(item);
  return state.selected.some((x) => itemKey(x) === key);
}

function addSelected(item) {
  if (isSelected(item)) return;
  state.selected.push(item);
  renderSelected();
  renderResults();
}

function removeSelectedByKey(key) {
  state.selected = state.selected.filter((x) => itemKey(x) !== key);
  renderSelected();
  renderResults();
}

function moveSelected(index, delta) {
  const next = index + delta;
  if (next < 0 || next >= state.selected.length) return;
  const copy = [...state.selected];
  const tmp = copy[index];
  copy[index] = copy[next];
  copy[next] = tmp;
  state.selected = copy;
  renderSelected();
}

function renderResults() {
  resultCount.textContent = `${state.results.length} result${state.results.length === 1 ? "" : "s"}`;
  resultsList.innerHTML = "";

  if (!state.results.length) {
    setEmptyState(resultsList, "Describe what you're looking for in the chat — matching slides will appear here.");
    return;
  }

  for (const item of state.results) {
    const card = document.createElement("div");
    card.className = `result-card ${isSelected(item) ? "selected" : ""}`;

    const top = document.createElement("div");
    top.className = "result-top";

    const titleWrap = document.createElement("div");
    titleWrap.className = "result-title-wrap";

    const title = document.createElement("div");
    title.className = "result-title";
    title.textContent = item.deck_title || basename(item.path) || "Untitled deck";

    const meta = document.createElement("div");
    meta.className = "result-meta";
    const slideLabel = item.slide_number ? `Slide ${item.slide_number}` : "Slide ?";
    const totalLabel = item.num_slides ? ` / ${item.num_slides}` : "";
    meta.textContent = `${basename(item.path)} • ${slideLabel}${totalLabel}`;

    titleWrap.appendChild(title);
    titleWrap.appendChild(meta);

    const score = document.createElement("div");
    score.className = "score-pill";
    score.textContent = `${matchPct(item.score)} match`;

    top.appendChild(titleWrap);
    top.appendChild(score);

    const snippet = document.createElement("div");
    snippet.className = "result-snippet";
    snippet.textContent = item.snippet || item.reason || "";

    const footer = document.createElement("div");
    footer.className = "result-footer";

    const path = document.createElement("div");
    path.className = "result-path";
    path.textContent = item.path || "";

    const addBtn = document.createElement("button");
    addBtn.className = isSelected(item) ? "btn btn-secondary" : "btn btn-primary";
    addBtn.textContent = isSelected(item) ? "Added" : "Add";
    addBtn.addEventListener("click", () => addSelected(item));

    footer.appendChild(path);
    footer.appendChild(addBtn);

    card.appendChild(top);
    card.appendChild(snippet);
    card.appendChild(footer);

    resultsList.appendChild(card);
  }
}

function renderSelected() {
  selectedCount.textContent = `${state.selected.length} selected`;
  exportDeckBtn.disabled = state.selected.length === 0;
  selectedList.innerHTML = "";

  if (!state.selected.length) {
    setEmptyState(selectedList, "Click Add on any suggested slide to include it in your presentation.");
    return;
  }

  state.selected.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "selected-card";

    const left = document.createElement("div");
    left.className = "selected-main";

    const title = document.createElement("div");
    title.className = "selected-title";
    title.textContent = `${index + 1}. ${item.deck_title || basename(item.path)}${item.slide_number ? ` — Slide ${item.slide_number}` : ""}`;

    const sub = document.createElement("div");
    sub.className = "selected-sub";
    sub.textContent = item.path || "";

    const note = document.createElement("div");
    note.className = "selected-note";
    note.textContent = item.snippet || item.reason || "";

    left.appendChild(title);
    left.appendChild(sub);
    left.appendChild(note);

    const actions = document.createElement("div");
    actions.className = "selected-actions";

    const upBtn = document.createElement("button");
    upBtn.className = "btn btn-ghost";
    upBtn.textContent = "↑";
    upBtn.title = "Move up";
    upBtn.disabled = index === 0;
    upBtn.addEventListener("click", () => moveSelected(index, -1));

    const downBtn = document.createElement("button");
    downBtn.className = "btn btn-ghost";
    downBtn.textContent = "↓";
    downBtn.title = "Move down";
    downBtn.disabled = index === state.selected.length - 1;
    downBtn.addEventListener("click", () => moveSelected(index, +1));

    const removeBtn = document.createElement("button");
    removeBtn.className = "btn btn-secondary";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => removeSelectedByKey(itemKey(item)));

    actions.appendChild(upBtn);
    actions.appendChild(downBtn);
    actions.appendChild(removeBtn);

    row.appendChild(left);
    row.appendChild(actions);

    selectedList.appendChild(row);
  });
}

function stopIndexPolling() {
  if (state.indexingPoller) {
    clearInterval(state.indexingPoller);
    state.indexingPoller = null;
  }
}

function updateIndexingUI(indexing) {
  const data = indexing || {};
  const status = data.status || "idle";
  const percent = Number(data.percent || 0);
  indexingBar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  indexingPercent.textContent = `${percent}%`;

  if (status === "idle") {
    indexingWrap.classList.add("hidden");
    sendBtn.disabled = false;
    return;
  }

  indexingWrap.classList.remove("hidden");

  if (status === "indexing" || status === "running") {
    indexingLabel.textContent = "Reading your presentations…";
    const total = Number(data.total || 0);
    const current = Number(data.current || 0);
    const fileInfo = data.current_file ? basename(data.current_file) : "";
    if (total > 0 && fileInfo) {
      indexingDetails.textContent = `Reading file ${current} of ${total}: ${fileInfo}`;
    } else if (total > 0) {
      indexingDetails.textContent = `Reading file ${current} of ${total}…`;
    } else {
      indexingDetails.textContent = data.message || "Getting ready…";
    }
    sendBtn.disabled = true;
    return;
  }

  sendBtn.disabled = false;

  if (status === "completed") {
    indexingLabel.textContent = "Your slides are ready!";
    const stats = data.stats || {};
    const files = stats.indexed_files || 0;
    const slides = stats.indexed_slides || 0;
    const skipped = stats.skipped_files || 0;
    const removed = stats.deleted_files || 0;
    let detail = `Found ${files} presentation${files !== 1 ? "s" : ""} with ${slides} slide${slides !== 1 ? "s" : ""}.`;
    if (skipped > 0) detail += ` (${skipped} unchanged, skipped)`;
    if (removed > 0) detail += ` Removed ${removed} old file${removed !== 1 ? "s" : ""}.`;
    indexingDetails.textContent = detail;
    return;
  }

  if (status === "error") {
    indexingLabel.textContent = "Something went wrong";
    indexingDetails.textContent = data.error || data.message || "Please try again.";
  }
}

async function pollIndexStatus() {
  try {
    const j = await getJSON("/api/index_status");
    const indexing = j.indexing || {};
    updateIndexingUI(indexing);
    if (!["indexing", "running"].includes(indexing.status)) {
      stopIndexPolling();
    }
  } catch (e) {
    stopIndexPolling();
    updateIndexingUI({ status: "error", percent: 0, error: e.message });
  }
}

function startIndexPolling(initialState) {
  updateIndexingUI(initialState);
  stopIndexPolling();
  if (["indexing", "running"].includes(initialState?.status)) {
    state.indexingPoller = setInterval(pollIndexStatus, 1000);
  }
}

function setExportStatus(text, loading = false) {
  exportStatus.innerHTML = "";
  if (loading) {
    const spinner = document.createElement("span");
    spinner.className = "export-spinner";
    exportStatus.appendChild(spinner);
  }
  const label = document.createElement("span");
  label.textContent = text;
  exportStatus.appendChild(label);
}

function resetSearchState() {
  state.results = [];
  state.selected = [];
  setExportStatus("");
  renderResults();
  renderSelected();
}

// ------------------------------------------------------------------
// Microsoft / Teams authentication
// ------------------------------------------------------------------

function setMsAuthConnected(connected) {
  if (!msAuthArea) return;
  if (connected) {
    msAuthArea.classList.remove("hidden");
    if (msAuthLabel) msAuthLabel.textContent = "Microsoft: Connected";
  } else {
    msAuthArea.classList.add("hidden");
  }
}

function openSignInModal() {
  if (!signInModal) return;
  signInModal.classList.remove("hidden");
  signInModal.setAttribute("aria-hidden", "false");
}

function closeSignInModal() {
  if (!signInModal) return;
  signInModal.classList.add("hidden");
  signInModal.setAttribute("aria-hidden", "true");
  stopAuthPolling();
}

function stopAuthPolling() {
  if (state.authPoller) {
    clearInterval(state.authPoller);
    state.authPoller = null;
  }
}

function renderSignInChallenge(userCode, verificationUri) {
  if (!signInBody) return;
  signInBody.innerHTML = `
    <div class="signin-steps">
      <div class="signin-step">
        <div class="signin-step-num">1</div>
        <div class="signin-step-body">
          <div class="signin-step-title">Open the Microsoft sign-in page</div>
          <a class="signin-link" href="${verificationUri}" target="_blank" rel="noopener">${verificationUri}</a>
        </div>
      </div>
      <div class="signin-step">
        <div class="signin-step-num">2</div>
        <div class="signin-step-body">
          <div class="signin-step-title">Enter this code</div>
          <div class="signin-code-row">
            <span class="signin-code" id="signInCodeDisplay">${userCode}</span>
            <button class="btn-copy" id="copyCodeBtn" type="button">Copy</button>
          </div>
        </div>
      </div>
      <div class="signin-step">
        <div class="signin-step-num">3</div>
        <div class="signin-step-body">
          <div class="signin-step-title">Sign in with your work account</div>
          <div class="muted small">Use the account that has access to your Teams folders.</div>
        </div>
      </div>
    </div>
    <div class="signin-status-row">
      <div class="signin-spinner"></div>
      <div class="signin-status-text" id="signInStatusText">Waiting for sign-in…</div>
    </div>
    <div class="signin-error hidden" id="signInError"></div>
  `;

  const copyBtn = document.getElementById("copyCodeBtn");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(userCode).catch(() => {});
      copyBtn.textContent = "Copied!";
      setTimeout(() => { copyBtn.textContent = "Copy"; }, 2000);
    });
  }
}

function setSignInStatus(text) {
  const el = document.getElementById("signInStatusText");
  if (el) el.textContent = text;
}

function setSignInError(text) {
  const el = document.getElementById("signInError");
  if (el) {
    el.textContent = text;
    el.classList.toggle("hidden", !text);
  }
  const spinner = signInBody ? signInBody.querySelector(".signin-spinner") : null;
  if (spinner) spinner.style.display = text ? "none" : "";
}

async function startSignIn(retryUrl) {
  state.pendingTeamsUrl = retryUrl || "";
  if (signInBody) signInBody.innerHTML = '<div class="signin-loading muted small">Starting sign-in…</div>';
  openSignInModal();

  let challenge;
  try {
    challenge = await postJSON("/api/auth/teams/start", {});
  } catch (e) {
    if (signInBody) signInBody.innerHTML = `<div class="signin-error">${e.message}</div>`;
    return;
  }

  renderSignInChallenge(challenge.user_code, challenge.verification_uri);

  stopAuthPolling();
  state.authPoller = setInterval(async () => {
    try {
      const j = await getJSON("/api/auth/teams/status");
      const auth = j.auth || {};
      if (auth.status === "complete") {
        stopAuthPolling();
        setSignInStatus("Signed in successfully!");
        setMsAuthConnected(true);
        setTimeout(() => {
          closeSignInModal();
          if (state.pendingTeamsUrl) {
            applyDirectory(state.pendingTeamsUrl);
            state.pendingTeamsUrl = "";
          }
        }, 800);
      } else if (auth.status === "error") {
        stopAuthPolling();
        setSignInError(auth.error || "Sign-in failed. Please try again.");
      }
    } catch (e) {
      stopAuthPolling();
      setSignInError("Connection error while waiting for sign-in.");
    }
  }, 3000);
}

async function checkAuthState() {
  try {
    const j = await getJSON("/api/auth/teams/state");
    setMsAuthConnected(j.signed_in === true);
  } catch (e) {
    // non-critical
  }
}

safeOn(closeSignInBtn, "click", () => {
  closeSignInModal();
  dirStatus.textContent = "Sign-in was cancelled.";
});

safeOn(signOutBtn, "click", async () => {
  try {
    await postJSON("/api/auth/teams/logout", {});
    setMsAuthConnected(false);
    dirStatus.textContent = "Signed out from Microsoft.";
  } catch (e) {
    dirStatus.textContent = `Sign-out failed: ${e.message}`;
  }
});

if (signInModal) {
  signInModal.addEventListener("click", (e) => {
    if (e.target === signInModal) {
      closeSignInModal();
      dirStatus.textContent = "Sign-in cancelled.";
    }
  });
}

// ------------------------------------------------------------------
// Directory application
// ------------------------------------------------------------------

async function applyDirectory(directory) {
  const target = String(directory || dirInput.value || "").trim();
  let j;
  try {
    const r = await fetch("/api/set_dir", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ directory: target }),
    });
    j = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));

    if (j.need_auth) {
      dirStatus.textContent = "Sign in to Microsoft to access Teams folders.";
      await startSignIn(target);
      return;
    }

    if (!r.ok) {
      dirStatus.textContent = `Error: ${j.error || j.detail || "Unknown error."}`;
      return;
    }
  } catch (e) {
    dirStatus.textContent = `Error: ${e.message}`;
    return;
  }

  const isFile = j.directory && j.directory.toLowerCase().endsWith(".pptx");
  const displayDir = j.display_name
    ? `Teams folder: ${j.display_name}`
    : j.directory
      ? (isFile ? `Searching in file: ${j.directory}` : `Searching in folder: ${j.directory}`)
      : "No folder or file selected yet.";
  dirInput.value = j.display_name ? target : (j.directory || "");
  state.lastAppliedDirectory = j.directory || "";
  state.lastAppliedInput = dirInput.value;
  updateSetBtnState();
  dirStatus.textContent = displayDir;
  resetSearchState();
  startIndexPolling(j.indexing || { status: "idle" });
}

async function chooseDirectory(initialDir = "") {
  const url = `/api/choose_directory?initial_dir=${encodeURIComponent(initialDir || "")}`;
  const j = await getJSON(url);
  if (!j.ok) throw new Error(j.error || "No directory selected.");
  return j.directory;
}

safeOn(browseBtn, "click", async () => {
  try {
    const j = await getJSON("/api/browse_dir");
    if (!j.ok) throw new Error(j.error || "Browse failed");
    dirInput.value = j.directory || "";
    state.lastAppliedDirectory = j.directory || "";
    state.lastAppliedInput = dirInput.value;
    updateSetBtnState();
    dirStatus.textContent = j.directory ? `Searching in folder: ${j.directory}` : "No folder or file selected yet.";
    resetSearchState();
    startIndexPolling(j.indexing || { status: "idle" });
  } catch (e) {
    dirStatus.textContent = `Error: ${e.message}`;
  }
});

safeOn(browseFileBtn, "click", async () => {
  try {
    const j = await getJSON("/api/browse_file");
    if (!j.ok) throw new Error(j.error || "File browse failed");
    dirInput.value = j.directory || "";
    state.lastAppliedDirectory = j.directory || "";
    state.lastAppliedInput = dirInput.value;
    updateSetBtnState();
    dirStatus.textContent = j.directory ? `Searching in file: ${j.directory}` : "No folder or file selected yet.";
    resetSearchState();
    startIndexPolling(j.indexing || { status: "idle" });
  } catch (e) {
    dirStatus.textContent = `Error: ${e.message}`;
  }
});

safeOn(setDirBtn, "click", () => {
  applyDirectory(dirInput.value);
});

if (dirInput) {
  dirInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      applyDirectory(dirInput.value);
    }
  });
  dirInput.addEventListener("input", updateSetBtnState);
}


safeOn(clearResultsBtn, "click", () => {
  state.results = [];
  renderResults();
});

safeOn(clearDeckBtn, "click", () => {
  state.selected = [];
  state.pendingNewDeckPath = "";
  exportStatus.textContent = "";
  closeNewDeckModal();
  renderSelected();
  renderResults();
});

function syncSettingsUI() {
  const mode = state.preferences.export_mode || "ask";
  exportModeInputs.forEach((input) => {
    input.checked = input.value === mode;
  });
  if (exportDirectoryInput) exportDirectoryInput.value = state.preferences.export_directory || "";
  if (fixedDirSection) fixedDirSection.classList.toggle("hidden", mode !== "fixed");

  const teamsMode = state.preferences.teams_indexing_mode || "download";
  teamsIndexingModeInputs.forEach((input) => {
    input.checked = input.value === teamsMode;
  });

  const newDeckMode = state.preferences.new_deck_mode || "ask";
  newDeckModeInputs.forEach((input) => {
    input.checked = input.value === newDeckMode;
  });

  if (settingsError) settingsError.textContent = "";
}

function openSettingsModal() {
  syncSettingsUI();
  settingsModal.classList.remove("hidden");
  settingsModal.setAttribute("aria-hidden", "false");
}

function closeSettingsModal() {
  settingsModal.classList.add("hidden");
  settingsModal.setAttribute("aria-hidden", "true");
}

async function loadPreferences() {
  try {
    const j = await getJSON("/api/preferences");
    state.preferences = j.preferences || state.preferences;
    if (openSettingsBtn) syncSettingsUI();
  } catch (e) {
    console.error(e);
  }
}

safeOn(openSettingsBtn, "click", openSettingsModal);
safeOn(closeSettingsBtn, "click", closeSettingsModal);
if (settingsModal) settingsModal.addEventListener("click", (e) => {
  if (e.target === settingsModal) closeSettingsModal();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (settingsModal && !settingsModal.classList.contains("hidden")) closeSettingsModal();
    if (newDeckModal && !newDeckModal.classList.contains("hidden")) closeNewDeckModal();
  }
});

exportModeInputs.forEach((input) => {
  input.addEventListener("change", () => {
    state.preferences.export_mode = input.value;
    syncSettingsUI();
  });
});

teamsIndexingModeInputs.forEach((input) => {
  input.addEventListener("change", () => {
    state.preferences.teams_indexing_mode = input.value;
  });
});

newDeckModeInputs.forEach((input) => {
  input.addEventListener("change", () => {
    state.preferences.new_deck_mode = input.value;
  });
});

safeOn(resetDatabaseBtn, "click", async () => {
  const confirmed = window.confirm(
    "Reset the database?\n\n" +
    "This will permanently delete all indexed data for every folder — both local and Teams. " +
    "You will need to re-index any folder before you can search it again.\n\n" +
    "This cannot be undone."
  );
  if (!confirmed) return;

  resetDatabaseBtn.disabled = true;
  try {
    const j = await postJSON("/api/reset_database", {});
    if (j.ok) {
      dirInput.value = "";
      state.lastAppliedDirectory = "";
      state.lastAppliedInput = "";
      updateSetBtnState();
      dirStatus.textContent = "All data cleared. Select a folder or file to get started.";
      resetSearchState();
      updateIndexingUI({ status: "idle" });
      closeSettingsModal();
    } else {
      alert(`Reset failed: ${j.error}`);
    }
  } catch (e) {
    alert(`Reset failed: ${e.message}`);
  } finally {
    resetDatabaseBtn.disabled = false;
  }
});

safeOn(browseExportDirBtn, "click", async () => {
  try {
    const selected = await chooseDirectory(exportDirectoryInput.value || state.preferences.export_directory || "");
    exportDirectoryInput.value = selected;
    if (settingsError) settingsError.textContent = "";
  } catch (e) {
    if (settingsError) settingsError.textContent = e.message;
  }
});

safeOn(saveSettingsBtn, "click", async () => {
  const selectedMode = exportModeInputs.find((input) => input.checked)?.value || "ask";
  const selectedTeamsMode = teamsIndexingModeInputs.find((input) => input.checked)?.value || "download";
  const selectedNewDeckMode = newDeckModeInputs.find((input) => input.checked)?.value || "ask";
  const payload = {
    export_mode: selectedMode,
    export_directory: exportDirectoryInput.value || "",
    teams_indexing_mode: selectedTeamsMode,
    new_deck_mode: selectedNewDeckMode,
  };

  try {
    const j = await postJSON("/api/preferences", payload);
    state.preferences = j.preferences || payload;
    syncSettingsUI();
    if (settingsError) settingsError.textContent = "Saved.";
    setTimeout(() => {
      if (settingsError) settingsError.textContent = "";
      closeSettingsModal();
    }, 500);
  } catch (e) {
    if (settingsError) settingsError.textContent = e.message;
  }
});

function openNewDeckModal(savedPath, filename) {
  state.pendingNewDeckPath = savedPath;
  if (newDeckModalSub) newDeckModalSub.textContent = filename;
  if (newDeckModalMsg) newDeckModalMsg.textContent = `"${filename}" has been saved to your computer.`;
  if (newDeckModal) {
    newDeckModal.classList.remove("hidden");
    newDeckModal.setAttribute("aria-hidden", "false");
  }
}

function closeNewDeckModal() {
  if (newDeckModal) {
    newDeckModal.classList.add("hidden");
    newDeckModal.setAttribute("aria-hidden", "true");
  }
  state.pendingNewDeckPath = "";
}

safeOn(exportDeckBtn, "click", async () => {
  if (!state.selected.length) return;

  exportDeckBtn.disabled = true;
  setExportStatus("Creating your presentation…", true);

  try {
    let targetDirectory = "";
    if ((state.preferences.export_mode || "ask") === "fixed") {
      targetDirectory = String(state.preferences.export_directory || "").trim();
      if (!targetDirectory) {
        throw new Error("Please choose a valid export directory in Settings.");
      }
    }

    const j = await postJSON("/api/export_deck", {
      slides: state.selected,
      target_directory: targetDirectory,
    });

    if (j.saved_path) {
      setExportStatus(`Saved to: ${j.saved_path}`);
      const mode = state.preferences.new_deck_mode || "ask";
      if (mode === "auto") {
        setExportStatus("Saved! Switching search to new presentation…", true);
        await applyDirectory(j.saved_path);
        setExportStatus(`Now searching: ${j.filename}`);
      } else if (mode === "ask") {
        openNewDeckModal(j.saved_path, j.filename);
      }
      // "never" — do nothing extra
    } else if (j.download_url) {
      setExportStatus(`Ready to download: ${j.filename}`);
      window.location.href = j.download_url;
    } else {
      setExportStatus("Your presentation is ready!");
    }
  } catch (e) {
    setExportStatus(`Export failed: ${e.message}`);
  } finally {
    exportDeckBtn.disabled = false;
  }
});

safeOn(newDeckYesBtn, "click", async () => {
  const path = state.pendingNewDeckPath;
  closeNewDeckModal();
  if (path) {
    setExportStatus("Switching to new presentation…", true);
    await applyDirectory(path);
    setExportStatus("");
  }
});

safeOn(newDeckNoBtn, "click", () => {
  closeNewDeckModal();
});

if (newDeckModal) {
  newDeckModal.addEventListener("click", (e) => {
    if (e.target === newDeckModal) closeNewDeckModal();
  });
}

function addThinkingMsg() {
  const row = document.createElement("div");
  row.className = "msg assistant";
  row.id = "thinkingBubble";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const dots = document.createElement("div");
  dots.className = "thinking-dots";
  dots.innerHTML = "<span></span><span></span><span></span>";
  bubble.appendChild(dots);
  row.appendChild(bubble);
  chatLog.appendChild(row);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function removeThinkingMsg() {
  const el = document.getElementById("thinkingBubble");
  if (el) el.remove();
}

async function send() {
  const msg = (chatInput.value || "").trim();
  if (!msg) return;

  chatInput.value = "";
  sendBtn.disabled = true;
  chatInput.disabled = true;
  addMsg("user", msg);
  addThinkingMsg();

  try {
    const j = await postJSON("/api/chat", { message: msg });
    removeThinkingMsg();

    if (j.mode === "search") {
      addMsg("assistant", j.text || "Search complete.");
      state.results = Array.isArray(j.results) ? j.results : [];
      renderResults();
    } else {
      addMsg("assistant", j.text || "OK.");
    }
  } catch (e) {
    removeThinkingMsg();
    addMsg("assistant", `Error: ${e.message}`);
  } finally {
    sendBtn.disabled = false;
    chatInput.disabled = false;
    chatInput.focus();
  }
}

safeOn(sendBtn, "click", send);
if (chatInput) chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    send();
  }
});

renderResults();
renderSelected();
pollIndexStatus();
loadPreferences();
checkAuthState();
