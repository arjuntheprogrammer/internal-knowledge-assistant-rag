const API_BASE = ""; // Relative path to support running on any port

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

function updateNav() {
  const user = JSON.parse(localStorage.getItem("user"));
  if (user) {
    document.getElementById("login-link").style.display = "none";
    document.getElementById("logout-link").style.display = "block";
    if (user.role === "admin") {
      document.getElementById("admin-link").style.display = "block";
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
    }
  } catch (err) {
    console.error("Failed to load config");
  }
}

async function saveConfig() {
  const token = localStorage.getItem("token");
  const provider = document.getElementById("llm-provider").value;
  const config = {
    llm_provider: provider,
    openai_model: document.getElementById("openai-model").value,
    ollama_url: document.getElementById("ollama-url").value,
    ollama_model: document.getElementById("ollama-model").value,
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
    if (res.ok) alert("Configuration saved!");
  } catch (err) {
    alert("Failed to save config");
  }
}
