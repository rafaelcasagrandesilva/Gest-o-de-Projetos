import axios from "axios";

/** Base da API FastAPI (`/api/v1`). Em dev use localhost; em build de produção defina `VITE_API_BASE`. */
export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1";

export const TOKEN_KEY = "sgp_access_token";

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    "Content-Type": "application/json",
  },
});

/** Alinha com FastAPI `redirect_slashes=True`: evita 307 em POST/PUT/PATCH (corpo pode se perder no redirect). */
function ensureTrailingSlashPath(url: string): string {
  if (!url || !url.startsWith("/")) return url;
  const q = url.indexOf("?");
  const path = q === -1 ? url : url.slice(0, q);
  const query = q === -1 ? "" : url.slice(q);
  if (path.endsWith("/")) return url;
  return `${path}/${query}`;
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

api.interceptors.request.use((config) => {
  const method = (config.method || "get").toLowerCase();
  if (
    ["post", "put", "patch", "delete"].includes(method) &&
    typeof config.url === "string" &&
    config.url.length > 0
  ) {
    config.url = ensureTrailingSlashPath(config.url);
  }
  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status;
    if (status === 401 && !window.location.pathname.includes("/login")) {
      setStoredToken(null);
      window.location.assign("/login");
    }
    return Promise.reject(err);
  }
);
