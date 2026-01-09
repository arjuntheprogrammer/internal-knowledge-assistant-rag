const API_BASE = "/api"; // Relative path to support running on any port

// Auth Functions
async function handleLogin(e) {
  e.preventDefault();
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();

    if (res.ok) {
      localStorage.setItem("token", data.token);
      localStorage.setItem("user", JSON.stringify(data.user));
      window.location.href = "/";
    } else {
      alert(data.message);
    }
  } catch (err) {
    alert("Login failed");
  }
}

async function handleSignup(e) {
  e.preventDefault();
  const name = document.getElementById("name").value;
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;

  try {
    const res = await fetch(`${API_BASE}/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email, password }),
    });
    const data = await res.json();

    if (res.ok) {
      alert("Signup successful! Please login.");
      window.location.href = "/login";
    } else {
      alert(data.message);
    }
  } catch (err) {
    alert("Signup failed");
  }
}

function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  window.location.href = "/login";
}

// Google Auth
async function checkAuthStatus() {
  const statusDiv = document.getElementById("drive-auth-status");
  const btn = document.getElementById("auth-btn");
  const foldersContainer = document.getElementById("drive-folders-container");
  if (!statusDiv) return false;

  try {
    const response = await fetch(`${API_BASE}/admin/chk_google_auth`, {
      headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
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

async function handleGoogleAuth() {
  try {
    const clientId = document.getElementById("google-client-id")?.value.trim();
    const clientSecret = document
      .getElementById("google-client-secret")
      ?.value.trim();

    if (clientId && clientSecret) {
      await saveConfig({ verifyDrive: false, showAlert: false });
    }

    const response = await fetch(`${API_BASE}/admin/google-login`, {
      headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
    });
    const data = await response.json();

    if (data.auth_url) {
      // Open Google Auth in a popup
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

      // Refresh status when popup closes (rough check)
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

// Auth & Route Protection
function checkRouteAccess() {
  const path = window.location.pathname;
  const publicRoutes = ["/login", "/signup"];
  const token = localStorage.getItem("token");
  const user = JSON.parse(localStorage.getItem("user"));

  // 1. If public route, just show content
  if (publicRoutes.includes(path)) {
    document.getElementById("main-content").style.display = "block";
    return;
  }

  // 2. If no token, redirect to login
  if (!token || !user) {
    window.location.href = "/login";
    return;
  }

  // 3. Role-based checks
  if (path.includes("/admin") && user.role !== "admin") {
    alert("Access Denied: Admins only.");
    window.location.href = "/";
    return;
  }

  // 4. Access Granted
  document.getElementById("main-content").style.display = "block";
  updateNav();

  // Additional initializers
  if (path.includes("/admin")) {
    checkAuthStatus();
  }
}

// Run check immediately
document.addEventListener("DOMContentLoaded", checkRouteAccess);

// ... existing code ...

function updateNav() {
  const user = JSON.parse(localStorage.getItem("user"));
  const path = window.location.pathname;

  // Highlight active link
  const links = document.querySelectorAll(".nav-links a");
  links.forEach((link) => {
    if (link.getAttribute("href") === path) {
      link.classList.add("active");
    } else {
      link.classList.remove("active");
    }
  });

  if (user) {
    document.getElementById("login-link").style.display = "none";
    document.getElementById("logout-link").style.display = "flex";
    if (user.role === "admin") {
      document.getElementById("admin-link").style.display = "flex";
    }
  }
}

// Chat Functions
function handleEnter(e) {
  if (e.key === "Enter") sendMessage();
}

async function sendMessage() {
  const input = document.getElementById("user-input");
  const text = input.value.trim();
  if (!text) return;

  appendMessage("user", text);
  input.value = "";

  const token = localStorage.getItem("token");

  try {
    const res = await fetch(`${API_BASE}/chat/message`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ message: text }),
    });

    const data = await res.json();
    if (res.ok) {
      appendMessage("bot", data.response, data.message_id);
    } else {
      appendMessage(
        "bot",
        "Error: " + (data.message || "Failed to get response")
      );
    }
  } catch (err) {
    appendMessage("bot", "Network error. Please try again.");
  }
}

function appendMessage(sender, text, messageId = null) {
  const history = document.getElementById("chat-history");
  const msg = document.createElement("div");
  msg.className = `message ${sender}-message`;

  const content = document.createElement("div");
  content.textContent = text;
  msg.appendChild(content);

  if (sender === "bot" && messageId) {
    const feedbackDiv = document.createElement("div");
    feedbackDiv.style.marginTop = "5px";
    feedbackDiv.style.fontSize = "0.8em";

    const upBtn = document.createElement("span");
    upBtn.innerHTML = "👍";
    upBtn.style.cursor = "pointer";
    upBtn.style.marginRight = "10px";
    upBtn.onclick = () => sendFeedback(messageId, "positive");

    const downBtn = document.createElement("span");
    downBtn.innerHTML = "👎";
    downBtn.style.cursor = "pointer";
    downBtn.onclick = () => sendFeedback(messageId, "negative");

    feedbackDiv.appendChild(upBtn);
    feedbackDiv.appendChild(downBtn);
    msg.appendChild(feedbackDiv);
  }

  history.appendChild(msg);
  history.scrollTop = history.scrollHeight;
}

async function sendFeedback(messageId, rating) {
  const token = localStorage.getItem("token");
  try {
    await fetch(`${API_BASE}/chat/feedback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ message_id: messageId, rating }),
    });
    alert("Thanks for your feedback!");
  } catch (err) {
    console.error("Feedback failed");
  }
}

// Drive Folder Management
function extractDriveFolderId(value) {
  const trimmed = value.trim();
  if (!trimmed) return "";

  const folderMatch = trimmed.match(
    /drive\.google\.com\/drive\/(?:u\/\d+\/)?folders\/([a-zA-Z0-9_-]+)/i
  );
  if (folderMatch) return folderMatch[1];

  const openMatch = trimmed.match(/[?&]id=([a-zA-Z0-9_-]+)/i);
  if (openMatch) return openMatch[1];

  return trimmed;
}

function addDriveFolder(value = "", isSaved = false) {
  const list = document.getElementById("drive-folders-list");
  if (!list) return;

  const div = document.createElement("div");
  div.className = "folder-row";
  div.style.display = "flex";
  div.style.gap = "12px";
  div.style.marginBottom = "10px";
  div.style.alignItems = "center";
  div.style.padding = "10px 14px";
  div.style.background = "#fff";
  div.style.borderRadius = "12px";
  div.style.border = "1px solid #e2e8f0";

  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Paste Google Drive Folder URL or ID...";
  input.value = value;
  input.className = "drive-folder-input";
  input.style.flex = "1";
  input.style.border = "none";
  input.style.outline = "none";
  input.style.background = "transparent";
  input.style.fontSize = "0.9rem";
  if (isSaved) input.disabled = true;

  const saveBtn = document.createElement("button");
  saveBtn.textContent = "Save";
  saveBtn.style.padding = "0.5rem 1rem";
  saveBtn.style.fontSize = "0.8rem";
  saveBtn.style.borderRadius = "8px";
  saveBtn.style.display = "none"; // Initially hidden
  saveBtn.onclick = async () => {
    if (!input.value.trim()) return;
    await saveConfig();
  };

  const removeBtn = document.createElement("button");
  removeBtn.textContent = "Remove";
  removeBtn.className = "btn-secondary";
  removeBtn.style.padding = "0.5rem 1rem";
  removeBtn.style.fontSize = "0.8rem";
  removeBtn.style.borderRadius = "8px";
  removeBtn.style.borderColor = "#fee2e2";
  removeBtn.style.color = "#ef4444";
  removeBtn.style.background = "#fff";
  removeBtn.style.display = isSaved ? "inline-flex" : "none";
  removeBtn.onclick = async () => {
    div.classList.add("removing");
    div.remove();
    await saveConfig();
  };

  const refreshSaveVisibility = () => {
    if (!isSaved) {
      saveBtn.style.display =
        input.value.trim().length > 5 ? "inline-flex" : "none";
    }
  };

  input.oninput = refreshSaveVisibility;
  input.onblur = () => {
    const normalized = extractDriveFolderId(input.value);
    if (normalized && normalized !== input.value.trim()) {
      input.value = normalized;
    }
    refreshSaveVisibility();
  };

  div.appendChild(input);
  div.appendChild(saveBtn);
  div.appendChild(removeBtn);
  list.appendChild(div);
}

// Admin Functions
async function loadConfig() {
  const token = localStorage.getItem("token");
  try {
    const res = await fetch(`${API_BASE}/admin/config`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const config = await res.json();
      document.getElementById("llm-provider").value =
        config.llm_provider || "openai";
      document.getElementById("openai-model").value =
        config.openai_model || "gpt-3.5-turbo";
      if (config.ollama_url)
        document.getElementById("ollama-url").value = config.ollama_url;
      toggleLLMConfig(config.llm_provider);

      // Load Google Config
      document.getElementById("google-client-id").value =
        config.google_client_id || "";
      document.getElementById("google-client-secret").value =
        config.google_client_secret || "";

      // Show Redirect URI for help
      const redirectDisplay = document.getElementById("redirect-uri-display");
      if (redirectDisplay) {
        redirectDisplay.textContent = `${window.location.origin}/api/admin/oauth2callback`;
      }

      // Load folders
      const list = document.getElementById("drive-folders-list");
      list.innerHTML = "";
      if (config.drive_folders && config.drive_folders.length > 0) {
        config.drive_folders.forEach((f) => addDriveFolder(f.id, true));
      }
    }
  } catch (err) {
    console.error("Failed to load config");
  }
}

async function saveConfig(options = {}) {
  const { verifyDrive = true, showAlert = true } = options;
  const token = localStorage.getItem("token");
  const provider = document.getElementById("llm-provider").value;

  // Collect drive folders
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
    llm_provider: provider,
    openai_model: document.getElementById("openai-model").value,
    ollama_url: document.getElementById("ollama-url").value,
    ollama_model: document.getElementById("ollama-model").value,
    drive_folders: driveFolders,
    google_client_id: document.getElementById("google-client-id").value.trim(),
    google_client_secret: document
      .getElementById("google-client-secret")
      .value.trim(),
  };

  try {
    const res = await fetch(`${API_BASE}/admin/config`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
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
    await loadConfig(); // Refresh UI to show saved states (Remove buttons, etc.)
  } catch (err) {
    alert("Failed to save config");
  }
}

async function verifyDriveConnection() {
  const listContainer = document.getElementById("verification-results");
  const ul = document.getElementById("files-list");
  const token = localStorage.getItem("token");

  listContainer.style.display = "block";
  ul.innerHTML = "<li>Scanning...</li>";

  try {
    const res = await fetch(`${API_BASE}/admin/preview_docs`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
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

function copyRedirectUri() {
  const uri = document.getElementById("redirect-uri-display").textContent;
  navigator.clipboard.writeText(uri).then(() => {
    alert("Redirect URI copied to clipboard!");
  });
}
