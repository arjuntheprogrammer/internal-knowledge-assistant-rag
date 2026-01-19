import { getStoredUser, updateNav } from "./auth.js";
import { getConfigStatus } from "./config.js";
import { bindChat, unbindChat } from "./chat.js";
import { bindConfigPage, unbindConfigPage } from "./config.js";

function showProtectedContent() {
  const mainContent = document.getElementById("main-content");
  const mainNav = document.getElementById("main-nav");
  if (mainContent) mainContent.style.display = "block";
  if (mainNav) mainNav.style.display = "";
}

/**
 * Perform SPA navigation
 */
export async function navigateTo(path, pushState = true) {
  if (pushState) {
    window.history.pushState({}, "", path);
  }

  // Unbind old page logic
  unbindChat();
  unbindConfigPage();

  // Update Nav active states immediately
  updateNav();

  // Scroll to top
  window.scrollTo(0, 0);

  // Check if we already have the content or need to fetch it
  // For simplicity, we always fetch the full page and extract #main-content
  try {
    const response = await fetch(path);
    if (!response.ok) throw new Error("Failed to load page");

    const html = await response.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    const newContent = doc.getElementById("main-content");

    if (newContent) {
      const currentContent = document.getElementById("main-content");
      if (currentContent) {
        currentContent.innerHTML = newContent.innerHTML;
        // Also copy attributes/classes if needed
        currentContent.className = newContent.className;
      }
    }

    // Re-run checks and bindings
    await checkRouteAccess(false); // Don't redirect again if we're already navigating
    bindChat();
    bindConfigPage();
  } catch (err) {
    console.error("Navigation error:", err);
    // Fallback to full reload if SPA fails
    window.location.href = path;
  }
}

/**
 * Intercept all internal link clicks for SPA navigation
 */
export function initSPANavigation() {
  document.addEventListener("click", (e) => {
    const link = e.target.closest("a");
    if (!link) return;

    const href = link.getAttribute("href");
    if (!href) return;

    // Check if it's an internal link
    if (
      href.startsWith("/") &&
      !href.startsWith("//") &&
      !link.hasAttribute("target") &&
      !link.hasAttribute("download") &&
      !e.ctrlKey &&
      !e.metaKey &&
      !e.shiftKey &&
      !e.altKey
    ) {
      e.preventDefault();
      // Skip if already on the same path
      if (normalizePath(window.location.pathname) === normalizePath(href))
        return;
      navigateTo(href);
    }
  });

  window.addEventListener("popstate", () => {
    navigateTo(window.location.pathname, false);
  });
}

function normalizePath(pathname) {
  if (!pathname) return "/";
  if (pathname !== "/" && pathname.endsWith("/")) {
    return pathname.slice(0, -1);
  }
  return pathname;
}

export async function checkRouteAccess(redirectOnSuccess = true) {
  const path = window.location.pathname;
  const publicRoutes = ["/login", "/signup", "/privacy", "/terms"];
  const token = localStorage.getItem("firebase_token");
  const user = getStoredUser();

  if (publicRoutes.includes(path)) {
    const authRoutes = ["/login", "/signup"];
    if (authRoutes.includes(path) && token && user) {
      if (redirectOnSuccess) {
        const status = await getConfigStatus();
        navigateTo(status.ready ? "/" : "/configure");
      }
      return;
    }
    // Public routes - show content immediately
    showProtectedContent();
    return;
  }

  // Protected routes - redirect if not authenticated
  if (!token || !user) {
    // We don't use navigateTo for login to ensure a clean state
    window.location.href = "/login";
    return;
  }

  // User is authenticated - check if config is complete for chat page
  if (path === "/" || path === "") {
    const status = await getConfigStatus();
    if (!status.ready) {
      const toast = document.getElementById("chat-redirect-toast");
      if (toast) {
        toast.style.display = "block";
        setTimeout(() => {
          navigateTo("/configure?reason=needs_config");
        }, 1200);
        return;
      }
      navigateTo("/configure?reason=needs_config");
      return;
    }
  }

  // All checks passed - show content
  showProtectedContent();
  updateNav();
}
