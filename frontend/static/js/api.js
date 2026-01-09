export const API_BASE = "/api"; // Relative path to support running on any port

export function getAuthToken() {
  return localStorage.getItem("token");
}

export function authHeaders(extraHeaders = {}) {
  const token = getAuthToken();
  if (!token) return extraHeaders;
  return {
    ...extraHeaders,
    Authorization: `Bearer ${token}`,
  };
}
