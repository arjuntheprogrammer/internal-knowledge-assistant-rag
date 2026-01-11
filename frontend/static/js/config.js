import { API_BASE, authHeaders } from "./api.js";
import { showToast } from "./toast.js";

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

  const verifyBtn = document.getElementById("verify-drive-btn");
  if (verifyBtn) {
    verifyBtn.addEventListener("click", verifyDriveConnection);
  }

  const testOpenAiBtn = document.getElementById("test-openai-btn");
  if (testOpenAiBtn) {
    testOpenAiBtn.addEventListener("click", testOpenAIKey);
  }

  loadConfig();
  showConfigNotice();
  checkAuthStatus().then((authenticated) => {
    if (!authenticated && !sessionStorage.getItem("drive_auth_attempted")) {
      sessionStorage.setItem("drive_auth_attempted", "1");
      handleGoogleAuth(true);
    }
  });
}

export async function getConfigStatus() {
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
    const ready = Boolean(
      config.has_openai_key &&
        config.openai_key_valid &&
        config.drive_folder_id &&
        config.drive_authenticated &&
        config.drive_test_success
    );
    return { ready };
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

    const driveInput = document.getElementById("drive-folder-id");
    if (driveInput) {
      driveInput.value = config.drive_folder_id || "";
    }

    const driveStatus = document.getElementById("drive-test-status");
    if (driveStatus) {
      if (config.drive_test_success && config.drive_tested_at) {
        const when = formatDate(config.drive_tested_at);
        driveStatus.textContent = `Last verified: ${when}`;
        driveStatus.style.color = "#059669";
        driveStatus.classList.add("status-valid");
      } else if (config.drive_test_success) {
        driveStatus.textContent = "Drive verified.";
        driveStatus.style.color = "#059669";
        driveStatus.classList.add("status-valid");
      } else {
        driveStatus.textContent = "Not tested yet.";
        driveStatus.style.color = "var(--text-muted)";
        driveStatus.classList.remove("status-valid");
      }
    }
    showConfigNotice(config);
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
    if (openaiKey) {
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
    const res = await fetch(`${API_BASE}/config/test-openai`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ openai_api_key: apiKey }),
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
    await loadConfig();
  } catch (e) {
    ul.innerHTML = `<li style="color: red">Verification request failed: ${e}</li>`;
    await loadConfig();
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

function showConfigNotice(config = null) {
  const notice = document.getElementById("config-notice");
  if (!notice) return;

  const params = new URLSearchParams(window.location.search);
  const needsConfigParam = params.get("reason") === "needs_config";

  if (!config) {
    if (needsConfigParam) {
      notice.style.display = "block";
      notice.textContent = "Please complete configuration before chatting.";
      notice.classList.remove("success");
    } else {
      notice.style.display = "none";
    }
    return;
  }

  const ready = Boolean(
    config.has_openai_key &&
      config.openai_key_valid &&
      config.drive_folder_id &&
      config.drive_authenticated &&
      config.drive_test_success
  );

  if (ready) {
    notice.style.display = "block";
    notice.innerHTML =
      'Configuration Completed. <a href="/" style="color: inherit; text-decoration: underline; margin-left: 8px;">Go to Chat</a>';
    notice.classList.add("success");
  } else if (needsConfigParam) {
    notice.style.display = "block";
    notice.textContent = "Please complete configuration before chatting.";
    notice.classList.remove("success");
  } else {
    notice.style.display = "none";
  }
}
