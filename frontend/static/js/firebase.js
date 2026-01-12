import { initializeApp } from "https://www.gstatic.com/firebasejs/9.22.2/firebase-app.js";
import {
  GoogleAuthProvider,
  getAuth,
  onIdTokenChanged,
  signInWithPopup,
  signInWithRedirect,
  signOut,
} from "https://www.gstatic.com/firebasejs/9.22.2/firebase-auth.js";

const currentHost = window.location.hostname;
const isLocal = currentHost === "localhost" || currentHost === "127.0.0.1";

const firebaseConfig = {
  apiKey: "[REMOVED]",
  authDomain: isLocal
    ? "internal-knowledge-assistant.firebaseapp.com"
    : currentHost,
  projectId: "internal-knowledge-assistant",
  storageBucket: "internal-knowledge-assistant.firebasestorage.app",
  messagingSenderId: "472638866088",
  appId: "1:472638866088:web:9d97a43d6c4d838bbb789d",
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

const provider = new GoogleAuthProvider();
provider.addScope("https://www.googleapis.com/auth/drive.readonly");
provider.setCustomParameters({
  prompt: "consent",
  access_type: "offline",
});

export function onAuthChange(callback) {
  return onIdTokenChanged(auth, callback);
}

export async function signInWithGoogle() {
  try {
    const result = await signInWithPopup(auth, provider);
    const user = result.user;
    const idToken = await user.getIdToken();
    return { user, idToken, mode: "popup" };
  } catch (err) {
    const code = err?.code || "";
    const shouldRedirect = [
      "auth/popup-blocked",
      "auth/popup-closed-by-user",
      "auth/cancelled-popup-request",
    ].includes(code);
    if (shouldRedirect) {
      await signInWithRedirect(auth, provider);
      return { mode: "redirect" };
    }
    throw err;
  }
}

export async function signOutUser() {
  await signOut(auth);
}

export async function getIdToken() {
  const user = auth.currentUser;
  if (!user) return null;
  return user.getIdToken();
}

export function getCurrentUser() {
  return auth.currentUser;
}
