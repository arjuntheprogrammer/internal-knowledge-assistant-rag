import { API_BASE, authHeaders } from "./api.js";
import { showToast } from "./toast.js";

export function handleEnter(e) {
  if (e.key === "Enter") sendMessage();
}

export function bindChat() {
  const input = document.getElementById("user-input");
  if (input) {
    input.addEventListener("keypress", handleEnter);
  }

  const sendBtn = document.getElementById("send-btn");
  if (sendBtn) {
    sendBtn.addEventListener("click", sendMessage);
  }
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
