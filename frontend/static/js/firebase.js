import { initializeApp } from "https://www.gstatic.com/firebasejs/9.22.2/firebase-app.js";
import { getAnalytics } from "https://www.gstatic.com/firebasejs/9.22.2/firebase-analytics.js";
import {
  GoogleAuthProvider,
  getAuth,
  onIdTokenChanged,
  signInWithPopup,
  signInWithRedirect,
  signOut,
} from "https://www.gstatic.com/firebasejs/9.22.2/firebase-auth.js";

const configElement = document.getElementById("firebase-config");
const firebaseConfig = JSON.parse(configElement?.textContent || "{}");

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const analytics = firebaseConfig.measurementId ? getAnalytics(app) : null;

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
