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
  2: "Authorize and select files.",
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
  const header = document.querySelector(`[data-step-toggle="${step}"]`);
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
    "step-status--locked",
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
  true,
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

  const resetOpenAiBtn = document.getElementById("reset-openai-btn");
  if (resetOpenAiBtn) {
    resetOpenAiBtn.addEventListener("click", resetOpenAIKey);
  }

  const buildBtn = document.getElementById("build-database-btn");
  if (buildBtn) {
    buildBtn.addEventListener("click", buildDatabase);
  }

  // Folder picker bindings
  const selectFilesBtn = document.getElementById("select-files-btn");
  if (selectFilesBtn) {
    selectFilesBtn.addEventListener("click", openFilePicker);
  }

  const changeFilesBtn = document.getElementById("change-files-btn");
  if (changeFilesBtn) {
    changeFilesBtn.addEventListener("click", openFilePicker);
  }

  const removeFilesBtn = document.getElementById("remove-files-btn");
  if (removeFilesBtn) {
    removeFilesBtn.addEventListener("click", removeDriveFiles);
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
        `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,status=yes`,
      );

      if (!popup) {
        window.location.href = data.auth_url;
        return;
      }

      const authListener = (event) => {
        if (event.origin !== window.location.origin) return;
        if (event.data?.type === "google-auth-success") {
          // Clear cached picker config so new token is used
          pickerConfig = null;
          checkAuthStatus().then(() => loadConfig());
        }
      };

      window.addEventListener("message", authListener);

      const timer = setInterval(() => {
        if (popup.closed) {
          clearInterval(timer);
          window.removeEventListener("message", authListener);
          // Clear cached picker config so new token is used
          pickerConfig = null;
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

    // Store file IDs for later use
    window._selectedDriveFileIds = config.drive_file_ids || [];
    window._selectedDriveFileNames = config.drive_file_names || [];

    const selectBtn = document.getElementById("file-picker-actions");
    const displayDiv = document.getElementById("selected-files-display");
    const nameSpan = document.getElementById("selected-files-summary");
    const filesList = document.getElementById("selected-files-list");

    const hasFiles = config.drive_file_ids && config.drive_file_ids.length > 0;

    if (hasFiles) {
      const fileCount = config.drive_file_ids.length;
      const fileNames = config.drive_file_names || [];
      const displayName = `${fileCount} file${fileCount > 1 ? "s" : ""} selected`;

      // Populate the files list
      if (filesList && fileNames.length > 0) {
        filesList.innerHTML = fileNames
          .map((name) => `<li>${name}</li>`)
          .join("");
        filesList.style.display = "flex";
      }

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
      // Clear and hide files list
      if (filesList) {
        filesList.innerHTML = "";
        filesList.style.display = "none";
      }
    }

    const driveSaveStatus = document.getElementById("drive-save-status");
    if (driveSaveStatus) {
      if (config.drive_authenticated && hasFiles) {
        const statusText = `${config.drive_file_ids.length} file${config.drive_file_ids.length > 1 ? "s" : ""} saved`;
        driveSaveStatus.textContent = statusText;
        driveSaveStatus.style.color = "#059669";
      } else {
        driveSaveStatus.textContent = "No files selected.";
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
    includeDriveFiles = false,
    driveFileIds = null,
    driveFileNames = null,
    skipLoadConfig = false,
  } = options;
  const openAiKeyInput = document.getElementById("openai-key");

  const payload = {};
  if (includeOpenAIKey) {
    const openaiKey = openAiKeyInput?.value?.trim();
    if (openaiKey && !openaiKey.includes("*")) {
      payload.openai_api_key = openaiKey;
    }
  }

  if (includeDriveFiles && driveFileIds !== null) {
    payload.drive_file_ids = driveFileIds;
    payload.drive_file_names = driveFileNames || [];
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
    if (!skipLoadConfig) {
      await loadConfig();
    }
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

  // Set local state to "Testing..." immediately to avoid flicker
  if (resultEl) {
    resultEl.textContent = "Testing...";
    resultEl.style.color = "var(--text-muted)";
    resultEl.classList.remove("status-valid");
  }

  const saved = await saveConfig({ showAlert: false, skipLoadConfig: true });
  if (!saved) {
    await loadConfig();
    return;
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

export async function resetOpenAIKey() {
  const confirmed = await showConfirmToast(
    "Are you sure you want to reset your OpenAI API key? This will disable chat and indexing until a new key is provided.",
  );
  if (!confirmed) return;

  try {
    const res = await fetch(`${API_BASE}/config`, {
      method: "PUT",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        openai_api_key: "",
        openai_key_valid: false,
      }),
    });

    if (res.ok) {
      showToast("OpenAI API key reset.", "success");
      const keyInput = document.getElementById("openai-key");
      if (keyInput) keyInput.value = "";
      await loadConfig();
    } else {
      showToast("Failed to reset OpenAI key.");
    }
  } catch (err) {
    showToast("An error occurred while resetting.");
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
      "Step 2 required: authorize Google Drive and select files.";
    notice.classList.remove("success");
  } else {
    notice.style.display = "block";
    notice.textContent = "Step 3 required: build your document database.";
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
    showToast("Saving file selection. Please wait.");
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

// ============ Google File Picker Functions ============

let pickerApiLoaded = false;
let pickerConfig = null;

async function getPickerConfig() {
  if (pickerConfig) return pickerConfig;

  try {
    const res = await fetch(`${API_BASE}/config/picker-config`, {
      headers: authHeaders(),
    });
    const data = await safeJson(res);

    if (!res.ok) {
      // Check for needs_reauth flag
      if (data?.needs_reauth) {
        const error = new Error(
          data?.error || "Please re-authorize Google Drive.",
        );
        error.needs_reauth = true;
        throw error;
      }
      throw new Error(data?.error || "Failed to get picker config");
    }

    pickerConfig = data;
    return pickerConfig;
  } catch (err) {
    console.error("Failed to get picker config:", err);
    throw err;
  }
}

async function openFilePicker() {
  try {
    if (isStepLocked(2)) {
      showToast("Complete Step 1 before selecting files.");
      return;
    }

    // First check if Drive is authorized
    const authStatus = await checkAuthStatus();
    if (!authStatus) {
      showToast("Please authorize Google Drive first.");
      return;
    }

    // Get picker configuration
    let config;
    try {
      config = await getPickerConfig();
    } catch (err) {
      // Check if we need to re-authorize due to scope change
      if (err.message && err.message.includes("re-authorize")) {
        showToast("Permissions updated. Please re-authorize Google Drive.");
        // Trigger re-authorization
        await handleGoogleAuth();
        return;
      }
      throw err;
    }

    if (!config) {
      showToast("Unable to load file picker. Please try again.");
      return;
    }

    // Check if we need to re-authorize
    if (config.needs_reauth) {
      showToast("Permissions updated. Please re-authorize Google Drive.");
      await handleGoogleAuth();
      return;
    }

    if (!config.apiKey || !config.accessToken) {
      showToast("Unable to load file picker. Please try again.");
      return;
    }

    // Load the Picker API if not already loaded
    if (!pickerApiLoaded) {
      await loadPickerApi();
    }

    // Create and show the picker
    createPicker(config);
  } catch (err) {
    console.error("File picker error:", err);
    showToast("Failed to open file picker: " + err.message);
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
  // Use the origin from server config or fall back to window.location.origin
  const pickerOrigin = config.origin || window.location.origin;

  const picker = new google.picker.PickerBuilder()
    .setTitle("Select files to index")
    .setOrigin(pickerOrigin)
    .setAppId(config.appId)
    // All files view (default)
    .addView(
      new google.picker.DocsView()
        .setIncludeFolders(true)
        .setSelectFolderEnabled(false)
        .setMode(google.picker.DocsViewMode.LIST),
    )
    // Documents view
    .addView(
      new google.picker.DocsView(google.picker.ViewId.DOCUMENTS).setMode(
        google.picker.DocsViewMode.LIST,
      ),
    )
    // Spreadsheets view
    .addView(
      new google.picker.DocsView(google.picker.ViewId.SPREADSHEETS).setMode(
        google.picker.DocsViewMode.LIST,
      ),
    )
    // PDFs view
    .addView(
      new google.picker.DocsView(google.picker.ViewId.PDFS).setMode(
        google.picker.DocsViewMode.LIST,
      ),
    )
    // Shared drives view
    .addView(
      new google.picker.DocsView()
        .setIncludeFolders(true)
        .setSelectFolderEnabled(false)
        .setEnableTeamDrives(true)
        .setMode(google.picker.DocsViewMode.LIST)
        .setLabel("Shared Drives"),
    )
    .setOAuthToken(config.accessToken)
    .setDeveloperKey(config.apiKey)
    .setCallback(pickerCallback)
    .enableFeature(google.picker.Feature.MULTISELECT_ENABLED)
    .enableFeature(google.picker.Feature.SUPPORT_DRIVES)
    .build();

  picker.setVisible(true);
}

function pickerCallback(data) {
  if (data.action === google.picker.Action.PICKED) {
    const docs = data.docs || [];
    if (docs.length > 0) {
      // Filter out folders - we only want files
      const files = docs.filter(
        (doc) => doc.mimeType !== "application/vnd.google-apps.folder",
      );

      if (files.length === 0) {
        showToast(
          "Please select files, not folders. With the new permissions model, you need to select individual files.",
        );
        return;
      }

      const fileIds = files.map((doc) => doc.id);
      const fileNames = files.map((doc) => doc.name);
      setSelectedFiles(fileIds, fileNames);
      void saveDriveFilesSelection(fileIds, fileNames);
    }
  } else if (data.action === google.picker.Action.CANCEL) {
    // User cancelled, do nothing
  }
}

function setSelectedFiles(fileIds, fileNames) {
  // Store in window for later use
  window._selectedDriveFileIds = fileIds;
  window._selectedDriveFileNames = fileNames;

  // Show the selected files display
  const selectBtn = document.getElementById("file-picker-actions");
  const displayDiv = document.getElementById("selected-files-display");
  const nameSpan = document.getElementById("selected-files-summary");
  const filesList = document.getElementById("selected-files-list");

  const displayName = `${fileNames.length} file${fileNames.length > 1 ? "s" : ""} selected`;

  if (displayDiv && nameSpan) {
    nameSpan.textContent = displayName;
    displayDiv.style.display = "flex";
  }
  if (selectBtn) {
    selectBtn.style.display = "none";
  }

  // Populate the files list
  if (filesList && fileNames.length > 0) {
    filesList.innerHTML = fileNames.map((name) => `<li>${name}</li>`).join("");
    filesList.style.display = "flex";
  }

  // Clear folder name from localStorage since we're using files now
  localStorage.removeItem("selected_folder_name");

  const driveSaveStatus = document.getElementById("drive-save-status");
  if (driveSaveStatus) {
    driveSaveStatus.textContent = "Saving files...";
    driveSaveStatus.style.color = "#f59e0b";
  }
}

async function saveDriveFilesSelection(fileIds, fileNames) {
  if (isSavingDrive) return;
  const authorized = await checkAuthStatus();
  if (!authorized) {
    showToast("Authorize Google Drive before saving files.");
    return;
  }

  if (!fileIds || fileIds.length === 0) {
    showToast("Select files to continue.");
    return;
  }

  const driveSaveStatus = document.getElementById("drive-save-status");
  if (driveSaveStatus) {
    driveSaveStatus.textContent = "Saving files...";
    driveSaveStatus.style.color = "#f59e0b";
  }

  isSavingDrive = true;
  try {
    const saved = await saveConfig({
      showAlert: false,
      includeOpenAIKey: false,
      includeDriveFiles: true,
      driveFileIds: fileIds,
      driveFileNames: fileNames,
    });
    if (!saved) return;

    showToast(
      `${fileIds.length} file${fileIds.length > 1 ? "s" : ""} saved!`,
      "success",
    );
    await loadConfig();
    setStepExpanded(2, false);
    setStepExpanded(3, true);
  } finally {
    isSavingDrive = false;
  }
}
async function removeDriveFiles() {
  const confirmed = await showConfirmToast(
    "Are you sure you want to remove the selected files? This will delete the search index and all associated data.",
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
      showToast(data?.message || "Failed to remove files");
      return;
    }

    // Reset UI
    localStorage.removeItem("selected_folder_name");

    // Clear file IDs
    window._selectedDriveFileIds = [];
    window._selectedDriveFileNames = [];

    const selectBtn = document.getElementById("file-picker-actions");
    const displayDiv = document.getElementById("selected-files-display");
    const filesList = document.getElementById("selected-files-list");
    if (displayDiv) displayDiv.style.display = "none";
    if (selectBtn) selectBtn.style.display = "flex";
    if (filesList) {
      filesList.innerHTML = "";
      filesList.style.display = "none";
    }

    const driveSaveStatus = document.getElementById("drive-save-status");
    if (driveSaveStatus) {
      driveSaveStatus.textContent = "No files selected.";
      driveSaveStatus.style.color = "var(--text-muted)";
    }

    const indexingStatus = document.getElementById("indexing-status-inline");
    if (indexingStatus) indexingStatus.style.display = "none";

    showToast("Files removed successfully", "success");
    await loadConfig();
  } catch (err) {
    console.error("Remove files error:", err);
    showToast("Failed to remove files");
  }
}
