import { bindAuthButtons, bindLogout, bindUserMenu, initAuthState } from "./js/auth.js";
import { bindChat } from "./js/chat.js";
import { bindConfigPage } from "./js/config.js";
import { checkRouteAccess } from "./js/routes.js";

document.addEventListener("DOMContentLoaded", () => {
  bindLogout();
  bindUserMenu();
  bindAuthButtons();
  bindChat();
  bindConfigPage();
  initAuthState().then(() => checkRouteAccess());
});
