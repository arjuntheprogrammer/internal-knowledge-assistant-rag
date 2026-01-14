import { API_BASE, authHeaders } from "./api.js";
import { showToast } from "./toast.js";

export function handleEnter(e) {
  if (e.key === "Enter") sendMessage();
}

export function bindChat() {
  const token = localStorage.getItem("firebase_token");
  if (!token) return;

  const input = document.getElementById("user-input");
  if (input) {
    input.addEventListener("keypress", handleEnter);
  }

  const sendBtn = document.getElementById("send-btn");
  if (sendBtn) {
    sendBtn.addEventListener("click", sendMessage);
  }

  // Check indexing status and show banner if needed
  checkAndShowIndexingBanner();
}

async function checkAndShowIndexingBanner() {
  try {
    const res = await fetch(`${API_BASE}/config/indexing-ready`, {
      headers: authHeaders(),
    });
    if (!res.ok) return;

    const data = await res.json();
    const chatContainer = document.getElementById("chat-container");
    const existingBanner = document.getElementById("indexing-banner");

    if (existingBanner) {
      existingBanner.remove();
    }

    if (!data.ready) {
      // Disable input if not ready
      toggleChatInput(false, getDisabledMessage(data.status));

      const banner = createIndexingBanner(data);
      if (chatContainer && banner) {
        chatContainer.insertBefore(banner, chatContainer.firstChild);
      }

      // Start polling if indexing is in progress
      if (data.status === "INDEXING") {
        startChatIndexingPoll();
      }
    } else {
      // Enable input if ready
      toggleChatInput(true);
    }
  } catch (err) {
    console.error("Failed to check indexing status:", err);
  }
}

function toggleChatInput(enabled, placeholder = "Type your message...") {
  const input = document.getElementById("user-input");
  const sendBtn = document.getElementById("send-btn");
  if (input) {
    input.disabled = !enabled;
    input.placeholder = placeholder;
  }
  if (sendBtn) {
    sendBtn.disabled = !enabled;
  }
}

function getDisabledMessage(status) {
  if (status === "INDEXING") return "Getting documents ready... Please wait.";
  if (status === "PENDING") return "Please finish setup in settings.";
  if (status === "FAILED") return "Setup incomplete. Check settings.";
  return "Chat disabled.";
}

function createIndexingBanner(data) {
  const banner = document.createElement("div");
  banner.id = "indexing-banner";
  banner.className = `chat-indexing-banner ${
    data.status === "INDEXING" ? "indexing" : "needs-indexing"
  }`;

  const icon = document.createElement("div");
  icon.className = "chat-indexing-banner-icon";
  icon.textContent = data.status === "INDEXING" ? "⏳" : "📚";

  const content = document.createElement("div");
  content.className = "chat-indexing-banner-content";

  const title = document.createElement("div");
  title.className = "chat-indexing-banner-title";

  const message = document.createElement("div");
  message.className = "chat-indexing-banner-message";

  if (data.status === "INDEXING") {
    title.textContent = "Connecting to Documents";
    message.innerHTML = `${
      data.message || "Processing your documents..."
    } <br>Please wait while we get everything ready.`;
  } else if (data.status === "PENDING") {
    title.textContent = "No Documents Connected";
    message.innerHTML = `We haven't processed your documents yet. <a href="/configure">Go to Settings</a> to finish the setup.`;
  } else if (data.status === "FAILED") {
    title.textContent = "Setup Incomplete";
    message.innerHTML = `${
      data.message || "We ran into an issue."
    } <a href="/configure">Go to Settings</a> to retry connecting your folder.`;
  }

  content.appendChild(title);
  content.appendChild(message);

  banner.appendChild(icon);
  banner.appendChild(content);

  return banner;
}

let chatIndexingPollInterval = null;

function startChatIndexingPoll() {
  if (chatIndexingPollInterval) return;

  chatIndexingPollInterval = setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/config/indexing-ready`, {
        headers: authHeaders(),
      });
      if (!res.ok) return;

      const data = await res.json();

      if (data.ready) {
        clearInterval(chatIndexingPollInterval);
        chatIndexingPollInterval = null;

        const banner = document.getElementById("indexing-banner");
        if (banner) {
          banner.remove();
        }

        // Re-enable input
        toggleChatInput(true);

        showToast(
          "Great! Your documents are now connected and ready to chat.",
          "success"
        );
      }
    } catch (err) {
      // Ignore polling errors
    }
  }, 3000);
}

export async function sendMessage() {
  const input = document.getElementById("user-input");
  const text = input.value.trim();
  if (!text) return;

  appendMessage("user", text);
  input.value = "";

  try {
    const res = await fetch(`${API_BASE}/chat/message`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ message: text }),
    });

    const data = await res.json();

    if (res.status === 202 && data.indexing) {
      appendMessage(
        "bot",
        `⏳ **Getting Ready** (${data.progress || 0}% complete)\n\n${
          data.message
        }\n\nPlease wait a moment while we finish connecting your documents.`
      );
      return;
    }

    if (res.ok) {
      appendMessage("bot", data.response, data.message_id);
    } else {
      // Handle needs_indexing and failed states
      if (data.needs_indexing) {
        appendMessage(
          "bot",
          "📚 **No Documents Connected**\n\nYour documents haven't been processed yet. Please go to [Settings](/configure) and click **Connect Google Drive** to begin."
        );
      } else if (data.failed) {
        appendMessage(
          "bot",
          "❌ **Setup Incomplete**\n\n" +
            (data.message || "Please go to Settings to reconnect your folder.")
        );
      } else {
        appendMessage(
          "bot",
          "Error: " + (data.message || "Failed to get response")
        );
      }
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
  if (sender === "bot") {
    content.innerHTML = renderMarkdown(text);
    decorateLinks(content);
  } else {
    content.textContent = text;
  }
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

function renderMarkdown(text) {
  if (window.marked) {
    const html = window.marked.parse(text || "");
    if (window.DOMPurify) {
      return window.DOMPurify.sanitize(html);
    }
    return html;
  }
  return escapeHtml(text || "").replace(/\n/g, "<br>");
}

function escapeHtml(text) {
  const map = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };
  return text.replace(/[&<>"']/g, (char) => map[char]);
}

function decorateLinks(container) {
  const links = container.querySelectorAll("a");
  if (!links.length) return;
  links.forEach((link) => {
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  });
}

async function sendFeedback(messageId, rating) {
  try {
    await fetch(`${API_BASE}/chat/feedback`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ message_id: messageId, rating }),
    });
    showToast("Thanks for your feedback!", "success");
  } catch (err) {
    console.error("Feedback failed");
  }
}
