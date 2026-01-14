import {
  bindAuthButtons,
  bindLogout,
  bindUserMenu,
  initAuthState,
} from "./js/auth.js";
import { bindChat } from "./js/chat.js";
import { bindConfigPage } from "./js/config.js";
import { checkRouteAccess } from "./js/routes.js";

document.addEventListener("DOMContentLoaded", () => {
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
});
