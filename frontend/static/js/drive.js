export function extractDriveFolderId(value) {
  const trimmed = value.trim();
  if (!trimmed) return "";

  const folderMatch = trimmed.match(
    /drive\.google\.com\/drive\/(?:u\/\d+\/)?folders\/([a-zA-Z0-9_-]+)/i
  );
  if (folderMatch) return folderMatch[1];

  const openMatch = trimmed.match(/[?&]id=([a-zA-Z0-9_-]+)/i);
  if (openMatch) return openMatch[1];

  return trimmed;
}

export function addDriveFolder(value = "", isSaved = false, onSave) {
  const list = document.getElementById("drive-folders-list");
  if (!list) return;

  const div = document.createElement("div");
  div.className = "folder-row";
  div.style.display = "flex";
  div.style.gap = "12px";
  div.style.marginBottom = "10px";
  div.style.alignItems = "center";
  div.style.padding = "10px 14px";
  div.style.background = "#fff";
  div.style.borderRadius = "12px";
  div.style.border = "1px solid #e2e8f0";

  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Paste Google Drive Folder URL or ID...";
  input.value = value;
  input.className = "drive-folder-input";
  input.style.flex = "1";
  input.style.border = "none";
  input.style.outline = "none";
  input.style.background = "transparent";
  input.style.fontSize = "0.9rem";
  if (isSaved) input.disabled = true;

  const saveBtn = document.createElement("button");
  saveBtn.textContent = "Save";
  saveBtn.style.padding = "0.5rem 1rem";
  saveBtn.style.fontSize = "0.8rem";
  saveBtn.style.borderRadius = "8px";
  saveBtn.style.display = "none";
  saveBtn.onclick = async () => {
    if (!input.value.trim()) return;
    if (typeof onSave === "function") {
      await onSave();
    }
  };

  const removeBtn = document.createElement("button");
  removeBtn.textContent = "Remove";
  removeBtn.className = "btn-secondary";
  removeBtn.style.padding = "0.5rem 1rem";
  removeBtn.style.fontSize = "0.8rem";
  removeBtn.style.borderRadius = "8px";
  removeBtn.style.borderColor = "#fee2e2";
  removeBtn.style.color = "#ef4444";
  removeBtn.style.background = "#fff";
  removeBtn.style.display = isSaved ? "inline-flex" : "none";
  removeBtn.onclick = async () => {
    div.classList.add("removing");
    div.remove();
    if (typeof onSave === "function") {
      await onSave();
    }
  };

  const refreshSaveVisibility = () => {
    if (!isSaved) {
      saveBtn.style.display =
        input.value.trim().length > 5 ? "inline-flex" : "none";
    }
  };

  input.oninput = refreshSaveVisibility;
  input.onblur = () => {
    const normalized = extractDriveFolderId(input.value);
    if (normalized && normalized !== input.value.trim()) {
      input.value = normalized;
    }
    refreshSaveVisibility();
  };

  div.appendChild(input);
  div.appendChild(saveBtn);
  div.appendChild(removeBtn);
  list.appendChild(div);
}
