import { getStoredUser, updateNav } from "./auth.js";
import { getConfigStatus } from "./config.js";

function showProtectedContent() {
  const mainContent = document.getElementById("main-content");
  const mainNav = document.getElementById("main-nav");
  if (mainContent) mainContent.style.display = "block";
  if (mainNav) mainNav.style.display = "";
}

export async function checkRouteAccess() {
  const path = window.location.pathname;
  const publicRoutes = ["/login", "/signup", "/privacy", "/terms"];
  const token = localStorage.getItem("firebase_token");
  const user = getStoredUser();

  if (publicRoutes.includes(path)) {
    const authRoutes = ["/login", "/signup"];
    if (authRoutes.includes(path) && token && user) {
      const status = await getConfigStatus();
      window.location.href = status.ready ? "/" : "/configure";
      return;
    }
    // Public routes - show content immediately
    showProtectedContent();
    return;
  }

  // Protected routes - redirect if not authenticated
  if (!token || !user) {
    window.location.href = "/login";
    return;
  }

  // User is authenticated - check if config is complete for chat page
  if (path === "/" || path === "") {
    const status = await getConfigStatus();
    // Allow access to chat if basic config is items are ready,
    // even if indexing isn't finished yet (chat.js handles the indexing banner).
    if (!status.configReady) {
      const toast = document.getElementById("chat-redirect-toast");
      if (toast) {
        toast.style.display = "block";
        setTimeout(() => {
          window.location.href = "/configure?reason=needs_config";
        }, 1200);
        return;
      }
      window.location.href = "/configure?reason=needs_config";
      return;
    }
  }

  // All checks passed - show content
  showProtectedContent();
  updateNav();
}
