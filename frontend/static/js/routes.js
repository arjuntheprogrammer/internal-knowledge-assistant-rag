import { updateNav } from "./auth.js";
import { checkAuthStatus } from "./admin.js";

export function checkRouteAccess() {
  const path = window.location.pathname;
  const publicRoutes = ["/login", "/signup"];
  const token = localStorage.getItem("token");
  const user = JSON.parse(localStorage.getItem("user"));
  const mainContent = document.getElementById("main-content");

  if (publicRoutes.includes(path)) {
    if (mainContent) mainContent.style.display = "block";
    return;
  }

  if (!token || !user) {
    window.location.href = "/login";
    return;
  }

  if (path.includes("/admin") && user.role !== "admin") {
    alert("Access Denied: Admins only.");
    window.location.href = "/";
    return;
  }

  if (mainContent) mainContent.style.display = "block";
  updateNav();

  if (path.includes("/admin")) {
    checkAuthStatus();
  }
}
