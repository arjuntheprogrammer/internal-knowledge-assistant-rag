import { API_BASE, authHeaders } from "./api.js";
import { showToast, showConfirmToast } from "./toast.js";

async function safeJson(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return null;
  }
  try {
    return await response.json();
  } catch (err) {
    return null;
  }
}

function showFullscreenLoader(text) {
  const loader = document.getElementById("fullscreen-loader");
  if (!loader) return;
  const textEl = loader.querySelector(".loader-text");
  if (textEl) textEl.textContent = text;
  loader.style.display = "flex";
  window.addEventListener("beforeunload", preventExitListener);
}

function hideFullscreenLoader() {
  const loader = document.getElementById("fullscreen-loader");
  if (loader) loader.style.display = "none";
  window.removeEventListener("beforeunload", preventExitListener);
}

const preventExitListener = (e) => {
  e.preventDefault();
  e.returnValue = "Operation in progress. Are you sure you want to leave?";
  return e.returnValue;
};

let buildPollInterval = null;
let isBuilding = false;
let isSavingDrive = false;
let navigationLocked = false;
let lastStepStatuses = {
  1: null,
  2: null,
  3: null,
};
const stepDefaultSubtitles = {
  1: "Validate your OpenAI key.",
  2: "Authorize and pick a folder.",
  3: "Index your Drive data.",
};

function bindStepToggles() {
  const headers = document.querySelectorAll("[data-step-toggle]");
  headers.forEach((header) => {
    header.addEventListener("click", () => {
      const step = Number(header.getAttribute("data-step-toggle"));
      if (isStepLocked(step)) {
        showToast("Complete the previous step to continue.");
        return;
      }
      const expanded = header.getAttribute("aria-expanded") === "true";
      setStepExpanded(step, !expanded);
    });
  });
}

function setStepExpanded(step, expanded) {
  const header = document.querySelector(
    `[data-step-toggle="${step}"]`
  );
  const body = document.getElementById(`step-${step}-body`);
  if (!header || !body) return;
  header.setAttribute("aria-expanded", String(expanded));
  body.style.display = expanded ? "block" : "none";
}

function setStepLocked(step, locked) {
  const container = document.getElementById(`step-${step}`);
  if (!container) return;
  container.classList.toggle("locked", locked);
}

function isStepLocked(step) {
  const container = document.getElementById(`step-${step}`);
  return container ? container.classList.contains("locked") : false;
}

function setStepStatus(step, status, message = "") {
  const statusEl = document.getElementById(`step-${step}-status`);
  const subtitleEl = document.getElementById(`step-${step}-subtitle`);
  if (!statusEl) return;
  const normalized = (status || "PENDING").toUpperCase();
  statusEl.textContent =
    normalized === "COMPLETED"
      ? "✓ Completed"
      : normalized === "PROCESSING"
        ? "Processing"
        : normalized === "FAILED"
          ? "Failed"
          : normalized === "LOCKED"
            ? "Locked"
            : "Pending";
  statusEl.classList.remove(
    "step-status--completed",
    "step-status--failed",
    "step-status--processing",
    "step-status--locked"
  );
  if (normalized === "COMPLETED") {
    statusEl.classList.add("step-status--completed");
  } else if (normalized === "FAILED") {
    statusEl.classList.add("step-status--failed");
  } else if (normalized === "PROCESSING") {
    statusEl.classList.add("step-status--processing");
  } else if (normalized === "LOCKED") {
    statusEl.classList.add("step-status--locked");
  }
  if (message) {
    statusEl.title = message;
  }
  if (subtitleEl) {
    subtitleEl.classList.remove("step-subtitle--completed");
    if (normalized === "COMPLETED" && message) {
      subtitleEl.textContent = `✓ ${message}`;
      subtitleEl.classList.add("step-subtitle--completed");
    } else {
      subtitleEl.textContent = stepDefaultSubtitles[step] || "";
    }
  }
}

function lockNavigation(locked) {
  navigationLocked = locked;
  document.body.classList.toggle("nav-locked", locked);
}

document.addEventListener(
  "click",
  (event) => {
    if (!navigationLocked) return;
    const link = event.target.closest("a");
    if (link && link.getAttribute("href")) {
      event.preventDefault();
      showToast("Please wait until the build is complete.");
    }
  },
  true
);

export function bindConfigPage() {
  const token = localStorage.getItem("firebase_token");
  if (!token) return;
  if (!document.getElementById("openai-key")) return;

  bindStepToggles();

  const authBtn = document.getElementById("auth-btn");
  if (authBtn) {
    authBtn.addEventListener("click", handleGoogleAuth);
  }

  const openAiInput = document.getElementById("openai-key");
  if (openAiInput) {
    openAiInput.addEventListener("focus", () => {
      if (openAiInput.value.includes("*")) {
        openAiInput.value = "";
      }
    });
  }

  const testOpenAiBtn = document.getElementById("test-openai-btn");
  if (testOpenAiBtn) {
    testOpenAiBtn.addEventListener("click", testOpenAIKey);
  }

  const buildBtn = document.getElementById("build-database-btn");
  if (buildBtn) {
    buildBtn.addEventListener("click", buildDatabase);
  }

  // Folder picker bindings
  const selectFolderBtn = document.getElementById("select-folder-btn");
  if (selectFolderBtn) {
    selectFolderBtn.addEventListener("click", openFolderPicker);
  }

  const changeFolderBtn = document.getElementById("change-folder-btn");
  if (changeFolderBtn) {
    changeFolderBtn.addEventListener("click", openFolderPicker);
  }

  const removeFolderBtn = document.getElementById("remove-folder-btn");
  if (removeFolderBtn) {
    removeFolderBtn.addEventListener("click", removeDriveFolder);
  }

  loadConfig();
  checkAuthStatus();
}

export function unbindConfigPage() {
  if (buildPollInterval) {
    clearInterval(buildPollInterval);
    buildPollInterval = null;
  }
  lockNavigation(false);
}

export async function getConfigStatus() {
  const token = localStorage.getItem("firebase_token");
  if (!token) {
    return { ready: false };
  }

  try {
    const config = await fetchConfig();
    if (!config) {
      return { ready: false };
    }
    return {
      ready: Boolean(config.config_ready),
      steps: config.steps || {},
      indexing: config.indexing || {},
    };
  } catch (err) {
    return { ready: false };
  }
}

export async function checkAuthStatus() {
  const statusDiv = document.getElementById("drive-auth-status");
  const btn = document.getElementById("auth-btn");
  if (!statusDiv || !btn) return false;

  try {
    const response = await fetch(`${API_BASE}/config/drive-auth-status`, {
      headers: authHeaders(),
    });
    const data = await safeJson(response);
    if (!response.ok || !data) {
      throw new Error("Invalid auth status response.");
    }
    const authenticated = Boolean(data.authenticated);

    if (authenticated) {
      statusDiv.textContent = "Connected";
      statusDiv.style.color = "#059669";
      statusDiv.classList.add("status-valid");
      btn.textContent = "Re-authorize";
      document.getElementById("auth-hint").textContent =
        "Your Google Drive access is active.";
    } else {
      statusDiv.textContent = "Not Connected";
      statusDiv.style.color = "#dc2626";
      statusDiv.classList.remove("status-valid");
      btn.textContent = "Authorize Google Drive";
      document.getElementById("auth-hint").textContent =
        "Authorize to access your Drive.";
      if (saveBtn) saveBtn.disabled = true;
    }
    return authenticated;
  } catch (e) {
    statusDiv.textContent = "Unknown";
    statusDiv.style.color = "#d97706";
    statusDiv.classList.remove("status-valid");
    btn.textContent = "Retry";
    document.getElementById("auth-hint").textContent =
      "Unable to reach auth status.";
    console.error("Auth check failed", e);
    if (saveBtn) saveBtn.disabled = true;
    return false;
  }
}

export async function handleGoogleAuth(autoRedirect = false) {
  try {
    const response = await fetch(`${API_BASE}/config/drive-auth-url`, {
      headers: authHeaders(),
    });
    const data = await safeJson(response);

    if (data && data.auth_url) {
      if (autoRedirect) {
        window.location.href = data.auth_url;
        return;
      }
      const width = 600;
      const height = 700;
      const left = (window.innerWidth - width) / 2;
      const top = (window.innerHeight - height) / 2;

      const popup = window.open(
        data.auth_url,
        "GoogleAuth",
        `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,status=yes`
      );

      if (!popup) {
        window.location.href = data.auth_url;
        return;
      }

      const authListener = (event) => {
        if (event.origin !== window.location.origin) return;
        if (event.data?.type === "google-auth-success") {
          checkAuthStatus().then(() => loadConfig());
        }
      };

      window.addEventListener("message", authListener);

      const timer = setInterval(() => {
        if (popup.closed) {
          clearInterval(timer);
          window.removeEventListener("message", authListener);
          checkAuthStatus().then(() => loadConfig());
        }
      }, 1000);
    } else {
      const message = data?.message || "Could not get auth URL";
      showToast("Error: " + message);
    }
  } catch (e) {
    showToast("Failed to initiate auth: " + e);
  }
}

async function fetchConfig() {
  const res = await fetch(`${API_BASE}/config`, {
    headers: authHeaders(),
  });
  if (!res.ok) return null;
  return safeJson(res);
}

export async function loadConfig() {
  try {
    const config = await fetchConfig();
    if (!config) return;

    const openAiStatus = document.getElementById("openai-key-status");
    const openAiResult = document.getElementById("openai-test-result");
    if (openAiStatus) {
      if (config.has_openai_key && config.openai_key_valid) {
        const first4 = config.openai_key_first4 || "****";
        const last4 = config.openai_key_last4 || "****";
        openAiStatus.textContent = `Configured (${first4}...${last4})`;
        openAiStatus.style.color = "#059669";
      } else if (config.has_openai_key) {
        openAiStatus.textContent = "Invalid or not tested";
        openAiStatus.style.color = "#dc2626";
      } else {
        openAiStatus.textContent = "Not configured";
        openAiStatus.style.color = "var(--text-muted)";
      }
    }
    if (openAiResult) {
      if (config.openai_key_valid) {
        openAiResult.textContent = "Validated";
        openAiResult.style.color = "#059669";
        openAiResult.classList.add("status-valid");
      } else {
        openAiResult.textContent = "";
        openAiResult.classList.remove("status-valid");
      }
    }

    const openAiInput = document.getElementById("openai-key");
    if (openAiInput && config.has_openai_key) {
      const first4 = config.openai_key_first4 || "";
      const last4 = config.openai_key_last4 || "";
      if (first4 && last4) {
        openAiInput.value = `${first4}${"*".repeat(20)}${last4}`;
      } else {
        openAiInput.value = "************************";
      }
    }

    const driveInput = document.getElementById("drive-folder-id");
    if (driveInput) {
      driveInput.value = config.drive_folder_id || "";
    }

    const selectBtn = document.getElementById("folder-picker-actions");
    const displayDiv = document.getElementById("selected-folder-display");
    const nameSpan = document.getElementById("selected-folder-name");

    if (config.drive_folder_id) {
      const storedName = localStorage.getItem("selected_folder_name");
      const displayName = storedName || config.drive_folder_id;

      if (displayDiv && nameSpan) {
        nameSpan.textContent = displayName;
        displayDiv.style.display = "flex";
      }
      if (selectBtn) {
        selectBtn.style.display = "none";
      }
    } else {
      if (displayDiv) {
        displayDiv.style.display = "none";
      }
      if (selectBtn) {
        selectBtn.style.display = "flex";
      }
    }

    const driveSaveStatus = document.getElementById("drive-save-status");
    if (driveSaveStatus) {
      if (config.drive_authenticated && config.drive_folder_id) {
        driveSaveStatus.textContent = "Folder saved";
        driveSaveStatus.style.color = "#059669";
      } else {
        driveSaveStatus.textContent = "No folder selected.";
        driveSaveStatus.style.color = "var(--text-muted)";
      }
    }

    updateStepUI(config);
    updateBuildStatus(config.indexing);
    updateCompletionState(config);
    await showConfigNotice(config);
  } catch (err) {
    console.error("Failed to load config");
  }
}

export async function saveConfig(options = {}) {
  const {
    showAlert = true,
    includeOpenAIKey = true,
    includeDriveFolder = true,
  } = options;
  const openAiKeyInput = document.getElementById("openai-key");
  const driveInput = document.getElementById("drive-folder-id");

  const payload = {};
  if (includeOpenAIKey) {
    const openaiKey = openAiKeyInput?.value?.trim();
    if (openaiKey && !openaiKey.includes("*")) {
      payload.openai_api_key = openaiKey;
    }
  }
  if (includeDriveFolder) {
    const driveFolder = normalizeDriveFolderId(driveInput?.value);
    if (driveFolder) {
      payload.drive_folder_id = driveFolder;
    }
  }

  try {
    if (!Object.keys(payload).length) {
      return true;
    }
    const res = await fetch(`${API_BASE}/config`, {
      method: "PUT",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });
    const result = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(result.message || "Failed to save config");
      return false;
    }

    if (showAlert) {
      showToast("Configuration saved!", "success");
    }
    await loadConfig();
    return true;
  } catch (err) {
    showToast("Failed to save config");
    return false;
  }
}

export async function testOpenAIKey() {
  const keyInput = document.getElementById("openai-key");
  const resultEl = document.getElementById("openai-test-result");
  const apiKey = keyInput?.value?.trim();
  if (!apiKey) {
    showToast("Enter an OpenAI API key to test.");
    return;
  }

  const saved = await saveConfig({ showAlert: false });
  if (!saved) return;

  if (resultEl) {
    resultEl.textContent = "Testing...";
    resultEl.style.color = "var(--text-muted)";
    resultEl.classList.remove("status-valid");
  }

  try {
    const body = {};
    if (apiKey && !apiKey.includes("*")) {
      body.openai_api_key = apiKey;
    }

    const res = await fetch(`${API_BASE}/config/test-openai`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    const data = await safeJson(res);
    if (!data) {
      throw new Error("Invalid response from server.");
    }

    if (res.ok && data.success) {
      if (resultEl) {
        resultEl.textContent = "Valid";
        resultEl.style.color = "#059669";
        resultEl.classList.add("status-valid");
      }
      showToast("OpenAI key validated successfully!", "success");
      await loadConfig();
      setStepExpanded(1, false);
      setStepExpanded(2, true);
    } else {
      if (resultEl) {
        resultEl.textContent = "Invalid";
        resultEl.style.color = "#dc2626";
        resultEl.classList.remove("status-valid");
      }
      showToast(data.message || "OpenAI key validation failed.");
      await loadConfig();
    }
  } catch (err) {
    if (resultEl) {
      resultEl.textContent = "Error";
      resultEl.style.color = "#dc2626";
      resultEl.classList.remove("status-valid");
    }
    showToast("OpenAI key validation failed.");
    await loadConfig();
  }
}

async function showConfigNotice(config = null) {
  const notice = document.getElementById("config-notice");
  if (!notice) return;

  const params = new URLSearchParams(window.location.search);
  const needsConfigParam = params.get("reason") === "needs_config";

  let currentConfig = config;
  if (!currentConfig) {
    try {
      const res = await fetch(`${API_BASE}/config`, { headers: authHeaders() });
      if (res.ok) currentConfig = await safeJson(res);
    } catch (e) {}
  }

  if (!currentConfig) {
    if (needsConfigParam) {
      notice.style.display = "block";
      notice.textContent = "Please complete configuration before chatting.";
      notice.classList.remove("success");
    } else {
      notice.style.display = "none";
    }
    return;
  }

  const steps = currentConfig.steps || {};
  const step1Done = steps.api_key?.status === "COMPLETED";
  const step2Done = steps.drive?.status === "COMPLETED";
  const step3Status = steps.build?.status;
  const configReady = Boolean(currentConfig.config_ready);

  if (configReady) {
    notice.style.display = "block";
    notice.innerHTML =
      'Configuration Completed. <a href="/" style="color: inherit; font-weight: 700; text-decoration: underline; margin-left: 8px;">Go to Chat →</a>';
    notice.classList.add("success");
  } else if (step3Status === "PROCESSING") {
    const progress = currentConfig.indexing?.progress || 0;
    const message =
      currentConfig.indexing?.message || "Building your database...";
    notice.style.display = "block";
    notice.textContent = `${message} (${progress}%)`;
    notice.classList.remove("success");
  } else if (!step1Done) {
    notice.style.display = "block";
    notice.textContent =
      "Step 1 required: add and validate your OpenAI API key.";
    notice.classList.remove("success");
  } else if (!step2Done) {
    notice.style.display = "block";
    notice.textContent =
      "Step 2 required: authorize Google Drive and select a folder.";
    notice.classList.remove("success");
  } else {
    notice.style.display = "block";
    notice.textContent =
      "Step 3 required: build your document database.";
    notice.classList.remove("success");
  }
}

// ============ Build Database Functions ============

function updateStepUI(config) {
  const steps = config.steps || {};
  const step1 = steps.api_key?.status || "PENDING";
  const step2 = steps.drive?.status || "PENDING";
  const step3 = steps.build?.status || "PENDING";

  const step1Done = step1 === "COMPLETED";
  const step2Done = step2 === "COMPLETED";

  setStepLocked(2, !step1Done);
  setStepLocked(3, !step2Done);

  setStepStatus(1, step1, steps.api_key?.message);
  setStepStatus(2, step1Done ? step2 : "LOCKED", steps.drive?.message);
  setStepStatus(3, step2Done ? step3 : "LOCKED", steps.build?.message);

  const buildBtn = document.getElementById("build-database-btn");
  if (buildBtn) {
    buildBtn.disabled = !step2Done;
  }

  if (lastStepStatuses[1] !== step1 && step1 === "COMPLETED") {
    setStepExpanded(1, false);
    setStepExpanded(2, true);
  }

  if (lastStepStatuses[2] !== step2 && step2 === "COMPLETED") {
    setStepExpanded(2, false);
    setStepExpanded(3, true);
  }

  lastStepStatuses = { 1: step1, 2: step2, 3: step3 };
}

function updateBuildStatus(indexing) {
  const container = document.getElementById("indexing-status-inline");
  const textEl = document.getElementById("indexing-inline-text");
  const progressFill = document.getElementById("indexing-progress-fill");
  if (!container || !textEl || !progressFill) return;

  const status = indexing?.status || "PENDING";
  const progress = indexing?.progress || 0;
  const message =
    indexing?.message ||
    (status === "COMPLETED"
      ? "Database built."
      : status === "FAILED"
        ? "Build failed."
        : "Ready to build.");

  if (status === "PENDING" && progress === 0 && !isBuilding) {
    container.style.display = "none";
    return;
  }

  container.style.display = "block";
  textEl.textContent = `${message} (${progress}%)`;
  progressFill.style.width = `${Math.min(progress, 100)}%`;

  if (status === "COMPLETED") {
    textEl.style.color = "#059669";
  } else if (status === "FAILED") {
    textEl.style.color = "#dc2626";
  } else {
    textEl.style.color = "#f59e0b";
  }

  if (status === "PROCESSING") {
    showFullscreenLoader(`${message} (${progress}%)`);
  }

  const buildBtn = document.getElementById("build-database-btn");
  if (buildBtn) {
    buildBtn.disabled = status === "PROCESSING";
  }
}

function updateCompletionState(config) {
  const complete = Boolean(config.config_ready);
  const completeBlock = document.getElementById("config-complete");
  if (!completeBlock) return;

  if (complete) {
    completeBlock.style.display = "flex";
    setStepExpanded(1, false);
    setStepExpanded(2, false);
    setStepExpanded(3, false);
  } else {
    completeBlock.style.display = "none";
  }
}

function startBuildPoll() {
  if (buildPollInterval) return;

  buildPollInterval = setInterval(async () => {
    const config = await fetchConfig();
    if (!config) return;
    updateStepUI(config);
    updateBuildStatus(config.indexing);
    updateCompletionState(config);
    showConfigNotice(config);

    const status = config.indexing?.status;
    if (status === "COMPLETED" || status === "FAILED") {
      stopBuildPoll();
      if (status === "COMPLETED") {
        showToast("Database built successfully!", "success");
      } else {
        showToast("Build failed. Please try again.");
      }
    }
  }, 5000);
}

function stopBuildPoll() {
  if (buildPollInterval) {
    clearInterval(buildPollInterval);
    buildPollInterval = null;
  }
  isBuilding = false;
  lockNavigation(false);
  hideFullscreenLoader();
}

async function buildDatabase() {
  if (isBuilding) return;
  const config = await fetchConfig();
  if (!config) {
    showToast("Failed to load configuration.");
    return;
  }

  if (config.steps?.drive?.status !== "COMPLETED") {
    showToast("Complete Step 2 before building the database.");
    return;
  }

  if (config.indexing?.status === "PROCESSING") {
    showToast("Build already in progress.");
    return;
  }

  if (isSavingDrive) {
    showToast("Saving folder selection. Please wait.");
    return;
  }

  const selectedFolder = document
    .getElementById("drive-folder-id")
    ?.value?.trim();
  if (selectedFolder && selectedFolder !== config.drive_folder_id) {
    showToast("Saving folder selection. Please wait.");
    return;
  }

  isBuilding = true;
  lockNavigation(true);
  showFullscreenLoader("Building your database...");
  updateBuildStatus({
    status: "PROCESSING",
    message: "Starting build...",
    progress: 0,
  });
  startBuildPoll();

  try {
    const res = await fetch(`${API_BASE}/config/build-database`, {
      method: "POST",
      headers: authHeaders(),
    });
    const data = await safeJson(res);
    if (!res.ok || !data?.success) {
      stopBuildPoll();
      showToast(data?.message || "Build failed.");
      return;
    }
    await loadConfig();
  } catch (err) {
    stopBuildPoll();
    showToast("Build failed. Please try again.");
  }
}

async function saveDriveSelection() {
  if (isSavingDrive) return;
  const authorized = await checkAuthStatus();
  if (!authorized) {
    showToast("Authorize Google Drive before saving a folder.");
    return;
  }

  const folderIdInput = document.getElementById("drive-folder-id");
  const folderId = folderIdInput?.value?.trim();
  if (!folderId) {
    showToast("Select a folder to continue.");
    return;
  }

  const driveSaveStatus = document.getElementById("drive-save-status");
  if (driveSaveStatus) {
    driveSaveStatus.textContent = "Saving folder...";
    driveSaveStatus.style.color = "#f59e0b";
  }

  isSavingDrive = true;
  try {
    const saved = await saveConfig({
      showAlert: false,
      includeOpenAIKey: false,
      includeDriveFolder: true,
    });
    if (!saved) return;

    showToast("Drive folder saved!", "success");
    await loadConfig();
    setStepExpanded(2, false);
    setStepExpanded(3, true);
  } finally {
    isSavingDrive = false;
  }
}

// ============ Google Folder Picker Functions ============

let pickerApiLoaded = false;
let pickerConfig = null;

async function getPickerConfig() {
  if (pickerConfig) return pickerConfig;

  try {
    const res = await fetch(`${API_BASE}/config/picker-config`, {
      headers: authHeaders(),
    });
    if (!res.ok) {
      const data = await safeJson(res);
      throw new Error(data?.error || "Failed to get picker config");
    }
    pickerConfig = await safeJson(res);
    return pickerConfig;
  } catch (err) {
    console.error("Failed to get picker config:", err);
    throw err;
  }
}

async function openFolderPicker() {
  try {
    if (isStepLocked(2)) {
      showToast("Complete Step 1 before selecting a folder.");
      return;
    }

    // First check if Drive is authorized
    const authStatus = await checkAuthStatus();
    if (!authStatus) {
      showToast("Please authorize Google Drive first.");
      return;
    }

    // Get picker configuration
    const config = await getPickerConfig();
    if (!config || !config.apiKey || !config.accessToken) {
      showToast("Unable to load folder picker. Please try again.");
      return;
    }

    // Load the Picker API if not already loaded
    if (!pickerApiLoaded) {
      await loadPickerApi();
    }

    // Create and show the picker
    createPicker(config);
  } catch (err) {
    console.error("Folder picker error:", err);
    showToast("Failed to open folder picker: " + err.message);
  }
}

function loadPickerApi() {
  return new Promise((resolve, reject) => {
    if (pickerApiLoaded) {
      resolve();
      return;
    }

    // Check if gapi is available
    if (typeof gapi === "undefined") {
      reject(new Error("Google API not loaded. Please refresh the page."));
      return;
    }

    gapi.load("picker", {
      callback: () => {
        pickerApiLoaded = true;
        resolve();
      },
      onerror: () => {
        reject(new Error("Failed to load Google Picker API"));
      },
    });
  });
}

function createPicker(config) {
  const picker = new google.picker.PickerBuilder()
    .setTitle("Select a folder to index")
    .setOrigin(window.location.origin)
    .setAppId(config.appId)
    .addView(
      new google.picker.DocsView()
        .setIncludeFolders(true)
        .setSelectFolderEnabled(true)
        .setMimeTypes("application/vnd.google-apps.folder")
    )
    .addView(
      new google.picker.DocsView()
        .setIncludeFolders(true)
        .setSelectFolderEnabled(true)
        .setMimeTypes("application/vnd.google-apps.folder")
        .setEnableTeamDrives(true)
        .setLabel("Shared Drives")
    )
    .setOAuthToken(config.accessToken)
    .setDeveloperKey(config.apiKey)
    .setCallback(pickerCallback)
    .enableFeature(google.picker.Feature.SUPPORT_DRIVES)
    .build();

  picker.setVisible(true);
}

function pickerCallback(data) {
  if (data.action === google.picker.Action.PICKED) {
    const folder = data.docs[0];
    if (folder) {
      setSelectedFolder(folder.id, folder.name);
      void saveDriveSelection();
    }
  } else if (data.action === google.picker.Action.CANCEL) {
    // User cancelled, do nothing
  }
}

function setSelectedFolder(folderId, folderName) {
  // Update the hidden input
  const folderIdInput = document.getElementById("drive-folder-id");
  if (folderIdInput) {
    folderIdInput.value = folderId;
  }

  // Show the selected folder display
  const selectBtn = document.getElementById("folder-picker-actions");
  const displayDiv = document.getElementById("selected-folder-display");
  const nameSpan = document.getElementById("selected-folder-name");

  if (displayDiv && nameSpan) {
    nameSpan.textContent = folderName || folderId;
    displayDiv.style.display = "flex";
  }
  if (selectBtn) {
    selectBtn.style.display = "none";
  }

  // Store folder name for display
  localStorage.setItem("selected_folder_name", folderName || "");

  const driveSaveStatus = document.getElementById("drive-save-status");
  if (driveSaveStatus) {
    driveSaveStatus.textContent = "Saving folder...";
    driveSaveStatus.style.color = "#f59e0b";
  }
}

async function removeDriveFolder() {
  const confirmed = await showConfirmToast(
    "Are you sure you want to remove this folder? This will delete the search index and all associated data."
  );
  if (!confirmed) {
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/config/remove-drive`, {
      method: "POST",
      headers: authHeaders(),
    });

    if (!res.ok) {
      const data = await safeJson(res);
      showToast(data?.message || "Failed to remove folder");
      return;
    }

    // Reset UI
    const folderIdInput = document.getElementById("drive-folder-id");
    if (folderIdInput) folderIdInput.value = "";
    localStorage.removeItem("selected_folder_name");

    const selectBtn = document.getElementById("folder-picker-actions");
    const displayDiv = document.getElementById("selected-folder-display");
    if (displayDiv) displayDiv.style.display = "none";
    if (selectBtn) selectBtn.style.display = "flex";

    const driveSaveStatus = document.getElementById("drive-save-status");
    if (driveSaveStatus) {
      driveSaveStatus.textContent = "No folder selected.";
      driveSaveStatus.style.color = "var(--text-muted)";
    }

    const indexingStatus = document.getElementById("indexing-status-inline");
    if (indexingStatus) indexingStatus.style.display = "none";

    showToast("Remove successful", "success");
    await loadConfig();
  } catch (err) {
    console.error("Remove folder error:", err);
    showToast("Failed to remove folder");
  }
}

function normalizeDriveFolderId(value) {
  const trimmed = (value || "").trim();
  if (!trimmed) return "";
  const folderMatch = trimmed.match(
    /drive\.google\.com\/drive\/(?:u\/\d+\/)?folders\/([a-zA-Z0-9_-]+)/i
  );
  if (folderMatch) return folderMatch[1];
  return trimmed;
}
