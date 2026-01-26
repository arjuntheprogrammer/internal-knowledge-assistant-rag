import {
  bindAuthButtons,
  bindLogout,
  bindUserMenu,
  initAuthState,
} from "./js/auth.js";
import { bindChat } from "./js/chat.js";
import { bindConfigPage } from "./js/config.js";
import { checkRouteAccess, initSPANavigation } from "./js/routes.js";

document.addEventListener("DOMContentLoaded", () => {
  initSPANavigation();
  bindLogout();
  bindUserMenu();
  bindAuthButtons();

  initAuthState().then(() => {
    // Only bind page-specific logic if on the correct page and (usually) authenticated
    // Note: checkRouteAccess will handle redirects if not authenticated
    bindChat();
    bindConfigPage();
    checkRouteAccess();
  });

  // Register Service Worker
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker
        .register("/sw.js")
        .then((registration) => {
          console.log("SW registered:", registration.scope);
        })
        .catch((error) => {
          console.error("SW registration failed:", error);
        });
    });
  }
});
