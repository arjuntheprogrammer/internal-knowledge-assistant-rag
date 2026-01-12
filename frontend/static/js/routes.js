import { getStoredUser, updateNav } from "./auth.js";
import { getConfigStatus } from "./config.js";

export async function checkRouteAccess() {
  const path = window.location.pathname;
  const publicRoutes = ["/login", "/signup", "/privacy", "/terms"];
  const token = localStorage.getItem("firebase_token");
  const user = getStoredUser();
  const mainContent = document.getElementById("main-content");

  if (publicRoutes.includes(path)) {
    const authRoutes = ["/login", "/signup"];
    if (authRoutes.includes(path) && token && user) {
      const status = await getConfigStatus();
      window.location.href = status.ready ? "/" : "/configure";
      return;
    }
    if (mainContent) mainContent.style.display = "block";
    return;
  }

  if (!token || !user) {
    window.location.href = "/login";
    return;
  }

  if (path === "/" || path === "") {
    const status = await getConfigStatus();
    if (!status.ready) {
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

  if (mainContent) mainContent.style.display = "block";
  updateNav();
}
