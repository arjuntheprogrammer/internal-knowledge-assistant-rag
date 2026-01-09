import { bindAuthForms, bindLogout } from "./js/auth.js";
import { bindChat } from "./js/chat.js";
import { bindAdminPage } from "./js/admin.js";
import { checkRouteAccess } from "./js/routes.js";

document.addEventListener("DOMContentLoaded", () => {
  bindLogout();
  bindAuthForms();
  bindChat();
  bindAdminPage();
  checkRouteAccess();
});
