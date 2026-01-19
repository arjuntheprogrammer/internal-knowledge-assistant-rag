import { API_BASE } from "./api.js";
import { signInWithGoogle, signOutUser, onAuthChange } from "./firebase.js";
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

export function bindAuthButtons() {
  const loginBtn = document.getElementById("google-login-btn");
  if (loginBtn) {
    loginBtn.addEventListener("click", async () => {
      try {
        const result = await signInWithGoogle();
        if (result && result.idToken && result.user) {
          localStorage.setItem("firebase_token", result.idToken);
          localStorage.setItem(
            "user",
            JSON.stringify({
              name: result.user.displayName,
              email: result.user.email,
              photoURL: result.user.photoURL,
            })
          );
          const ready = await fetchConfigReady(result.idToken);
          window.location.href = ready ? "/" : "/configure";
          return;
        }
        loginBtn.disabled = true;
        loginBtn.textContent = "Redirecting to Google...";
      } catch (err) {
        const code = err?.code ? ` (${err.code})` : "";
        showToast(`Google sign-in failed${code}.`);
      }
    });
  }
}

export function bindLogout() {
  const logoutLink = document.getElementById("logout-link");
  if (!logoutLink) return;
  logoutLink.addEventListener("click", async (event) => {
    event.preventDefault();
    sessionStorage.removeItem("drive_auth_attempted");
    await signOutUser();
  });
}

export function bindUserMenu() {
  const menuBtn = document.getElementById("user-menu-btn");
  const dropdown = document.getElementById("user-menu-dropdown");
  if (!menuBtn || !dropdown) return;
  menuBtn.addEventListener("click", () => {
    const expanded = menuBtn.getAttribute("aria-expanded") === "true";
    menuBtn.setAttribute("aria-expanded", String(!expanded));
    dropdown.classList.toggle("show", !expanded);
  });
  document.addEventListener("click", (event) => {
    if (!dropdown.classList.contains("show")) return;
    if (event.target.closest("#user-menu")) return;
    dropdown.classList.remove("show");
    menuBtn.setAttribute("aria-expanded", "false");
  });
}

export function initAuthState() {
  return new Promise((resolve) => {
    let resolved = false;
    const fallbackTimer = setTimeout(() => {
      if (resolved) return;
      updateNav();
      resolved = true;
      resolve();
    }, 1500);

    onAuthChange(async (user) => {
      if (user) {
        const token = await user.getIdToken();
        localStorage.setItem("firebase_token", token);
        localStorage.setItem(
          "user",
          JSON.stringify({
            name: user.displayName,
            email: user.email,
            photoURL: user.photoURL,
          })
        );
      } else {
        localStorage.removeItem("firebase_token");
        localStorage.removeItem("user");
        const isPublic = ["/login", "/signup", "/privacy", "/terms"].includes(
          window.location.pathname
        );
        if (!isPublic) {
          window.location.href = "/login";
        }
      }
      updateNav();
      if (!resolved) {
        resolved = true;
        clearTimeout(fallbackTimer);
        resolve();
      }
    });
  });
}

export function getStoredUser() {
  const raw = localStorage.getItem("user");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (err) {
    return null;
  }
}

export function updateNav() {
  const user = getStoredUser();
  const path = normalizePath(window.location.pathname);

  const links = document.querySelectorAll(".nav-links a");
  links.forEach((link) => {
    const href = normalizePath(link.getAttribute("href"));
    const isLoginLink = href === "/login";
    const isActive = isLoginLink ? path.startsWith("/login") : href === path;
    link.classList.toggle("active", isActive);
  });

  const loginLink = document.getElementById("login-link");
  const chatLink = document.getElementById("chat-link");
  const configLink = document.getElementById("config-link");
  const userMenu = document.getElementById("user-menu");

  if (user) {
    if (loginLink) loginLink.style.display = "none";
    if (chatLink) chatLink.style.display = "flex";
    if (configLink) configLink.style.display = "flex";
    if (userMenu) userMenu.style.display = "flex";

    const nameEl = document.getElementById("user-name");
    const emailEl = document.getElementById("user-email");
    const avatarEl = document.getElementById("user-avatar");
    if (nameEl) nameEl.textContent = user.name || "User";
    if (emailEl) emailEl.textContent = user.email || "";
    if (avatarEl) {
      if (user.photoURL) {
        avatarEl.innerHTML = `<img src="${user.photoURL}" alt="${user.name}" referrerpolicy="no-referrer" style="width: 100%; height: 100%; border-radius: 50%; object-fit: cover;">`;
        avatarEl.style.background = "none";
      } else {
        const initial = (user.name || user.email || "U")
          .charAt(0)
          .toUpperCase();
        avatarEl.textContent = initial;
        avatarEl.style.background = "rgba(59, 130, 246, 0.12)";
      }
    }
  } else {
    if (loginLink) loginLink.style.display = "flex";
    if (chatLink) chatLink.style.display = "none";
    if (configLink) configLink.style.display = "none";
    if (userMenu) userMenu.style.display = "none";
  }
}

function normalizePath(pathname) {
  if (!pathname) return "/";
  if (pathname !== "/" && pathname.endsWith("/")) {
    return pathname.slice(0, -1);
  }
  return pathname;
}

async function fetchConfigReady(idToken) {
  try {
    const res = await fetch(`${API_BASE}/config`, {
      headers: { Authorization: `Bearer ${idToken}` },
    });
    if (!res.ok) return false;
    const config = await safeJson(res);
    if (!config) return false;
    return Boolean(config.config_ready);
  } catch (err) {
    return false;
  }
}
