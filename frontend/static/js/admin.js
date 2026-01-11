import { API_BASE, authHeaders } from "./api.js";
import { addDriveFolder, extractDriveFolderId } from "./drive.js";

export function bindAdminPage() {
  const token = localStorage.getItem("token");
  if (!token) return;

  const saveApiBtn = document.getElementById("save-api-btn");
  if (saveApiBtn) {
    saveApiBtn.addEventListener("click", () => saveConfig());
  }

  const authBtn = document.getElementById("auth-btn");
  if (authBtn) {
    authBtn.addEventListener("click", handleGoogleAuth);
  }

  const verifyBtn = document.getElementById("verify-drive-btn");
  if (verifyBtn) {
    verifyBtn.addEventListener("click", verifyDriveConnection);
  }

  const addFolderBtn = document.getElementById("add-drive-folder-btn");
  if (addFolderBtn) {
    addFolderBtn.addEventListener("click", () =>
      addDriveFolder("", false, saveConfig)
    );
  }

  const saveConfigBtn = document.getElementById("save-config-btn");
  if (saveConfigBtn) {
    saveConfigBtn.addEventListener("click", () => saveConfig());
  }

  const copyRedirectBtn = document.getElementById("copy-redirect-btn");
  if (copyRedirectBtn) {
    copyRedirectBtn.addEventListener("click", copyRedirectUri);
  }

  loadConfig();
}

export async function checkAuthStatus() {
  const statusDiv = document.getElementById("drive-auth-status");
  const btn = document.getElementById("auth-btn");
  const foldersContainer = document.getElementById("drive-folders-container");
  if (!statusDiv) return false;

  try {
    const response = await fetch(`${API_BASE}/admin/chk_google_auth`, {
      headers: authHeaders(),
    });
    const data = await response.json();
    const authenticated = Boolean(data.authenticated);

    if (authenticated) {
      statusDiv.textContent = "Status: Connected ✅";
      statusDiv.style.color = "#059669";
      btn.textContent = "Switch Account";
      document.getElementById("auth-hint").textContent =
        "Your Google account is linked.";
      if (foldersContainer) foldersContainer.style.display = "block";
    } else {
      statusDiv.textContent = "Status: Not Connected ❌";
      statusDiv.style.color = "#dc2626";
      btn.textContent = "Authorize Now";
      document.getElementById("auth-hint").textContent =
        "Link your account to see folders.";
      if (foldersContainer) foldersContainer.style.display = "none";
    }
    return authenticated;
  } catch (e) {
    statusDiv.textContent = "Status: Unknown ⚠️";
    statusDiv.style.color = "#d97706";
    btn.textContent = "Retry";
    document.getElementById("auth-hint").textContent =
      "Unable to reach auth status.";
    if (foldersContainer) foldersContainer.style.display = "none";
    console.error("Auth check failed", e);
    return false;
  }
}

export async function handleGoogleAuth() {
  try {
    const clientId = document.getElementById("google-client-id")?.value.trim();
    const clientSecret = document
      .getElementById("google-client-secret")
      ?.value.trim();

    if (clientId && clientSecret) {
      await saveConfig({ verifyDrive: false, showAlert: false });
    }

    const response = await fetch(`${API_BASE}/admin/google-login`, {
      headers: authHeaders(),
    });
    const data = await response.json();

    if (data.auth_url) {
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
      alert("Error: " + (data.message || "Could not get auth URL"));
    }
  } catch (e) {
    alert("Failed to initiate auth: " + e);
  }
}

export async function loadConfig() {
  try {
    const res = await fetch(`${API_BASE}/admin/config`, {
      headers: authHeaders(),
    });
    if (res.ok) {
      const config = await res.json();
      document.getElementById("openai-model").value =
        config.openai_model || "gpt-4o-mini";

      document.getElementById("google-client-id").value =
        config.google_client_id || "";
      document.getElementById("google-client-secret").value =
        config.google_client_secret || "";

      const redirectDisplay = document.getElementById("redirect-uri-display");
      if (redirectDisplay) {
        redirectDisplay.textContent = `${window.location.origin}/api/admin/oauth2callback`;
      }

      const list = document.getElementById("drive-folders-list");
      list.innerHTML = "";
      if (config.drive_folders && config.drive_folders.length > 0) {
        config.drive_folders.forEach((f) =>
          addDriveFolder(f.id, true, saveConfig)
        );
      }
    }
  } catch (err) {
    console.error("Failed to load config");
  }
}

export async function saveConfig(options = {}) {
  const { verifyDrive = true, showAlert = true } = options;

  const folderInputs = document.querySelectorAll(".drive-folder-input");
  const driveFolderIds = [];
  folderInputs.forEach((input) => {
    const normalized = extractDriveFolderId(input.value);
    if (normalized) {
      input.value = normalized;
      driveFolderIds.push(normalized);
    }
  });

  const uniqueIds = [...new Set(driveFolderIds)];
  const driveFolders = uniqueIds.map((id) => ({ id }));

  const config = {
    openai_model: document.getElementById("openai-model").value,
    drive_folders: driveFolders,
    google_client_id: document.getElementById("google-client-id").value.trim(),
    google_client_secret: document
      .getElementById("google-client-secret")
      .value.trim(),
  };

  try {
    const res = await fetch(`${API_BASE}/admin/config`, {
      method: "PUT",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(config),
    });
    const result = await res.json().catch(() => ({}));
    if (!res.ok) {
      alert(result.message || "Failed to save config");
      return;
    }

    if (showAlert) {
      alert("Configuration saved!");
    }
    let shouldVerify = verifyDrive;
    if (verifyDrive) {
      shouldVerify = await checkAuthStatus();
    }
    if (shouldVerify) {
      await verifyDriveConnection();
    }
    await loadConfig();
  } catch (err) {
    alert("Failed to save config");
  }
}

export async function verifyDriveConnection() {
  const listContainer = document.getElementById("verification-results");
  const ul = document.getElementById("files-list");

  listContainer.style.display = "block";
  ul.innerHTML = "<li>Scanning...</li>";

  try {
    const res = await fetch(`${API_BASE}/admin/preview_docs`, {
      method: "POST",
      headers: authHeaders(),
    });
    const data = await res.json();

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
      const infoLi = document.createElement("li");
      infoLi.innerHTML = `<strong>${data.message}</strong>`;
      ul.appendChild(infoLi);

      data.files.forEach((f) => {
        const li = document.createElement("li");
        li.textContent = f;
        ul.appendChild(li);
      });
    } else {
      ul.innerHTML = `<li>${data.message || "No files found."}</li>`;
    }
  } catch (e) {
    ul.innerHTML = `<li style="color: red">Verification request failed: ${e}</li>`;
  }
}

export function copyRedirectUri() {
  const uri = document.getElementById("redirect-uri-display").textContent;
  navigator.clipboard.writeText(uri).then(() => {
    alert("Redirect URI copied to clipboard!");
  });
}
