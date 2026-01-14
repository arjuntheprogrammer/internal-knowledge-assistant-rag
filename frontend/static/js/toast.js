const ERROR_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
const SUCCESS_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`;

export function showToast(message, type = "error") {
  const toast = document.getElementById("app-toast");
  const toastBody = document.querySelector(".app-toast-body");
  const toastIcon = document.getElementById("app-toast-icon");
  const toastMessage = document.getElementById("app-toast-message");
  const toastOk = document.getElementById("app-toast-ok");

  if (!toast || !toastMessage || !toastOk || !toastBody || !toastIcon) {
    console.error("Toast elements not found");
    alert(message); // Fallback
    return;
  }

  toastMessage.innerHTML = message;

  if (type === "success") {
    toastBody.classList.add("success");
    toastIcon.innerHTML = SUCCESS_ICON;
  } else {
    toastBody.classList.remove("success");
    toastIcon.innerHTML = ERROR_ICON;
  }

  // Display the toast
  toast.style.display = "flex";

  const closeToast = () => {
    toast.style.display = "none";
    toastOk.onclick = null;
    toast.onclick = null;
  };

  // Button dismiss
  toastOk.onclick = (e) => {
    e.stopPropagation();
    closeToast();
  };

  // Click backdrop to dismiss
  toast.onclick = (e) => {
    if (e.target === toast) {
      closeToast();
    }
  };
}

export function showConfirmToast(message) {
  return new Promise((resolve) => {
    const toast = document.getElementById("app-confirm-toast");
    const toastMessage = document.getElementById("app-confirm-message");
    const yesBtn = document.getElementById("app-confirm-yes");
    const dismissBtn = document.getElementById("app-confirm-dismiss");

    if (!toast || !toastMessage || !yesBtn || !dismissBtn) {
      // Fallback to native confirm
      resolve(confirm(message));
      return;
    }

    toastMessage.textContent = message;
    toast.style.display = "flex";

    const cleanup = () => {
      toast.style.display = "none";
      yesBtn.onclick = null;
      dismissBtn.onclick = null;
      toast.onclick = null;
    };

    yesBtn.onclick = (e) => {
      e.stopPropagation();
      cleanup();
      resolve(true);
    };

    dismissBtn.onclick = (e) => {
      e.stopPropagation();
      cleanup();
      resolve(false);
    };

    toast.onclick = (e) => {
      if (e.target === toast) {
        cleanup();
        resolve(false);
      }
    };
  });
}
