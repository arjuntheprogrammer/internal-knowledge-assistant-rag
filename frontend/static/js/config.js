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

export function bindConfigPage() {
  const token = localStorage.getItem("firebase_token");
  if (!token) return;
  if (!document.getElementById("openai-key")) return;

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

  const verifyBtn = document.getElementById("verify-drive-btn");
  if (verifyBtn) {
    verifyBtn.addEventListener("click", verifyDriveConnection);
  }

  const testOpenAiBtn = document.getElementById("test-openai-btn");
  if (testOpenAiBtn) {
    testOpenAiBtn.addEventListener("click", testOpenAIKey);
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
  loadIndexingStatusInline();
  showConfigNotice();
  checkAuthStatus().then((authenticated) => {
    if (!authenticated && !sessionStorage.getItem("drive_auth_attempted")) {
      sessionStorage.setItem("drive_auth_attempted", "1");
      handleGoogleAuth(true);
    }
  });
}

export function unbindConfigPage() {
  if (indexingPollInterval) {
    clearInterval(indexingPollInterval);
    indexingPollInterval = null;
  }
}

export async function getConfigStatus() {
  const token = localStorage.getItem("firebase_token");
  if (!token) {
    return { ready: false };
  }

  try {
    const res = await fetch(`${API_BASE}/config`, {
      headers: authHeaders(),
    });
    if (!res.ok) {
      return { ready: false };
    }
    const config = await safeJson(res);
    if (!config) {
      return { ready: false };
    }

    // Also check indexing status
    const indexingRes = await fetch(`${API_BASE}/config/indexing-ready`, {
      headers: authHeaders(),
    });
    const indexingData = indexingRes.ok ? await safeJson(indexingRes) : null;
    const indexingReady = indexingData?.ready || false;

    const configReady = Boolean(
      config.has_openai_key &&
        config.openai_key_valid &&
        config.drive_folder_id &&
        config.drive_authenticated &&
        config.drive_test_success
    );

    // Both config and indexing must be ready
    return {
      ready: configReady && indexingReady,
      configReady,
      indexingReady,
      indexingStatus: indexingData?.status || "PENDING",
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
        `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,status=yes`
      );

      if (!popup) {
        window.location.href = data.auth_url;
        return;
      }

      const authListener = (event) => {
        if (event.origin !== window.location.origin) return;
        if (event.data?.type === "google-auth-success") {
          checkAuthStatus();
        }
      };

      window.addEventListener("message", authListener);

      const timer = setInterval(() => {
        if (popup.closed) {
          clearInterval(timer);
          window.removeEventListener("message", authListener);
          checkAuthStatus();
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

export async function loadConfig() {
  try {
    const res = await fetch(`${API_BASE}/config`, {
      headers: authHeaders(),
    });
    if (!res.ok) return;
    const config = await safeJson(res);
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

    // Update folder picker display if a folder is already configured
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
      // No folder configured - show the picker button, hide the display
      if (displayDiv) {
        displayDiv.style.display = "none";
      }
      if (selectBtn) {
        selectBtn.style.display = "flex";
      }
    }

    const driveStatus = document.getElementById("drive-test-status");
    if (driveStatus) {
      if (config.drive_test_success && config.drive_tested_at) {
        const when = formatDate(config.drive_tested_at);
        driveStatus.textContent = `Connected: ${when}`;
        driveStatus.style.color = "#059669";
        driveStatus.classList.add("status-valid");
      } else if (config.drive_test_success) {
        driveStatus.textContent = "Connected";
        driveStatus.style.color = "#059669";
        driveStatus.classList.add("status-valid");
      } else {
        driveStatus.textContent = "Not connected yet.";
        driveStatus.style.color = "var(--text-muted)";
        driveStatus.classList.remove("status-valid");
      }
    }
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
      await loadConfig();
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

export async function verifyDriveConnection() {
  const listContainer = document.getElementById("drive-test-results");
  const ul = document.getElementById("drive-files-list");

  if (!listContainer || !ul) return;
  listContainer.style.display = "block";
  ul.innerHTML = "<li>Scanning...</li>";

  const saved = await saveConfig({ showAlert: false });
  if (!saved) {
    ul.innerHTML = '<li style="color: red">Failed to save Drive settings.</li>';
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/config/test-drive`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        drive_folder_id: normalizeDriveFolderId(
          document.getElementById("drive-folder-id")?.value
        ),
      }),
    });
    const data = await safeJson(res);
    if (!data) {
      throw new Error("Invalid response from server.");
    }

    ul.innerHTML = "";

    if (!res.ok) {
      ul.innerHTML = `<li style="color: red">Error: ${
        data.message || "Verification failed."
      }</li>`;
      return;
    }

    if (!data.success) {
      ul.innerHTML = `<li style="color: red">Error: ${data.message}</li>`;
      return;
    }

    if (data.files && data.files.length > 0) {
      const summary =
        findDriveSummary(data.files) ||
        data.message ||
        "Drive verification complete.";
      ul.innerHTML = `<li>${summary}</li>`;
    } else {
      ul.innerHTML = `<li>${data.message || "No files found."}</li>`;
    }

    // Check if indexing was auto-started
    if (data.indexing_started) {
      showToast("Drive connected! Indexing your documents...", "success");
      showIndexingStatusInline("Indexing documents...");
      startIndexingPoll();
    }

    await loadConfig();
  } catch (e) {
    ul.innerHTML = `<li style="color: red">Verification request failed: ${e}</li>`;
    await loadConfig();
  }
}

function formatDate(value) {
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return date.toLocaleString();
  } catch (err) {
    return value;
  }
}

function findDriveSummary(items) {
  if (!Array.isArray(items)) return "";
  const foundLine = items.find((line) => /found \\d+/i.test(line));
  if (foundLine) return foundLine;
  const apiLine = items.find((line) => /Drive API:/i.test(line));
  if (apiLine) return apiLine;
  return items[0] || "";
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

  const configReady = Boolean(
    currentConfig.has_openai_key &&
      currentConfig.openai_key_valid &&
      currentConfig.drive_folder_id &&
      currentConfig.drive_authenticated &&
      currentConfig.drive_test_success
  );

  // Also check if indexing is complete
  let indexingReady = false;
  if (configReady) {
    try {
      const indexingStatus = await getIndexingStatus();
      indexingReady = indexingStatus?.status === "READY";
    } catch (err) {
      // If we can't check, assume not ready
      indexingReady = false;
    }
  }

  // Only show "completed" if both config AND indexing are ready
  if (configReady && indexingReady) {
    notice.style.display = "block";
    notice.innerHTML =
      'Configuration Completed. <a href="/" style="color: inherit; font-weight: 700; text-decoration: underline; margin-left: 8px;">Go to Chat →</a>';
    notice.classList.add("success");
  } else if (configReady && !indexingReady) {
    // Config is done but indexing is not - show the actual status message and progress
    notice.style.display = "block";
    let msg = "Document indexing in progress... Chat will be enabled shortly.";
    try {
      // Fetch fresh status if not provided or to get latest message
      const indexingStatus = await getIndexingStatus();
      if (indexingStatus && indexingStatus.message) {
        msg = indexingStatus.message;
        if (indexingStatus.progress) {
          msg += ` (${indexingStatus.progress}%)`;
        }
      }
    } catch (e) {}

    notice.textContent = msg;
    notice.classList.remove("success");
  } else if (needsConfigParam) {
    notice.style.display = "block";
    notice.textContent = "Please complete configuration before chatting.";
    notice.classList.remove("success");
  } else {
    notice.style.display = "none";
  }
}

// ============ Indexing Functions (Simplified - Auto-triggered by Drive test) ============

let indexingPollInterval = null;

export async function getIndexingStatus() {
  try {
    const res = await fetch(`${API_BASE}/config/indexing-status`, {
      headers: authHeaders(),
    });
    if (!res.ok) return null;
    return await safeJson(res);
  } catch (err) {
    console.error("Failed to get indexing status:", err);
    return null;
  }
}

// Load and display inline indexing status (shown in Drive section)
async function loadIndexingStatusInline() {
  const status = await getIndexingStatus();
  if (!status) return;

  if (status.status === "INDEXING") {
    showIndexingStatusInline(
      `Indexing documents... (${status.progress || 0}%)`
    );
    startIndexingPoll();
  } else if (status.status === "READY" && status.document_count > 0) {
    showIndexingStatusInline(
      `✓ ${status.document_count} documents indexed and ready`,
      true
    );
  } else if (status.status === "FAILED") {
    showIndexingStatusInline(
      `✗ Indexing failed: ${status.message || "Unknown error"}`,
      false,
      true
    );
  }
}

function showIndexingStatusInline(message, isSuccess = false, isError = false) {
  const container = document.getElementById("indexing-status-inline");
  const textEl = document.getElementById("indexing-inline-text");

  if (!container || !textEl) return;

  container.style.display = "block";
  textEl.textContent = message;

  if (isSuccess) {
    textEl.style.color = "#059669";
  } else if (isError) {
    textEl.style.color = "#dc2626";
  } else {
    textEl.style.color = "#f59e0b";
  }
}

function hideIndexingStatusInline() {
  const container = document.getElementById("indexing-status-inline");
  if (container) {
    container.style.display = "none";
  }
}

function startIndexingPoll() {
  if (indexingPollInterval) return;

  indexingPollInterval = setInterval(async () => {
    const status = await getIndexingStatus();
    if (status) {
      if (status.status === "INDEXING") {
        showIndexingStatusInline(
          `Indexing documents... (${status.progress || 0}%)`
        );
        // Also update the top banner
        showConfigNotice();
      } else if (status.status !== "INDEXING") {
        // Stop polling when done
        clearInterval(indexingPollInterval);
        indexingPollInterval = null;

        if (status.status === "READY") {
          showIndexingStatusInline(
            `✓ ${status.document_count || 0} documents indexed and ready`,
            true
          );
          showToast(
            'Indexing complete! <a href="/" style="color: white; font-weight: 700; text-decoration: underline; margin-left: 8px;">Go to Chat →</a>',
            "success"
          );
          // Update the config notice
          showConfigNotice();
        } else if (status.status === "FAILED") {
          showIndexingStatusInline(
            `✗ Indexing failed: ${status.message || "Unknown error"}`,
            false,
            true
          );
          showToast("Indexing failed. Please try again.");
        }
      }
    }
  }, 2000); // Poll every 2 seconds
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
      showToast(`Selected folder: ${folder.name}`, "success");
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

    // Clear drive test results
    const listContainer = document.getElementById("drive-test-results");
    const ul = document.getElementById("drive-files-list");
    if (listContainer) listContainer.style.display = "none";
    if (ul) ul.innerHTML = "";

    // Reset drive status text
    const driveStatus = document.getElementById("drive-test-status");
    if (driveStatus) {
      driveStatus.textContent = "Not connected yet.";
      driveStatus.style.color = "var(--text-muted)";
      driveStatus.classList.remove("status-valid");
    }

    // Hide indexing status
    hideIndexingStatusInline();

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

// Export for use in chat.js
export { getIndexingStatus as checkIndexingReady };
