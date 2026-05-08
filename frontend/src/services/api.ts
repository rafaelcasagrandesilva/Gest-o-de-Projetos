import axios from "axios";
import { getStoredWorkspaceForApi } from "@/context/WorkspaceContext";

function normalizeApiBase(url: string): string {
  return url.replace(/\/+$/, "");
}

/**
 * Base da API (`/api/v1`).
 * 1) `window.__SGP_API_BASE__` — injetado em produção por GET `/sgp-runtime-config.js` (server.js + env Railway).
 * 2) `import.meta.env.VITE_API_BASE` — build local / CI.
 * 3) fallback desenvolvimento.
 */
function resolveApiBase(): string {
  if (typeof window !== "undefined") {
    const raw = window.__SGP_API_BASE__;
    if (typeof raw === "string") {
      const t = raw.trim();
      if (t.length > 0) return normalizeApiBase(t);
    }
  }
  const vite = import.meta.env.VITE_API_BASE;
  if (typeof vite === "string" && vite.trim().length > 0) {
    return normalizeApiBase(vite.trim());
  }
  return "http://localhost:8000/api/v1";
}

export const API_BASE = resolveApiBase();

export const TOKEN_KEY = "sgp_access_token";

export const api = axios.create({
  baseURL: API_BASE,
  // Evita "loading infinito" quando o backend não responde (ex.: API fora do ar).
  timeout: 15_000,
});

/**
 * Alinha com rotas FastAPI SEM barra final (padrão do projeto).
 * Evita 307 em POST/PUT/PATCH/DELETE, que pode causar problemas com body.
 */
function ensureNoTrailingSlashPath(url: string): string {
  if (!url || !url.startsWith("/")) return url;
  const q = url.indexOf("?");
  const path = q === -1 ? url : url.slice(0, q);
  const query = q === -1 ? "" : url.slice(q);
  if (path.length > 1 && path.endsWith("/")) {
    return `${path.slice(0, -1)}${query}`;
  }
  return url;
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
  if (typeof config.url === "string" && config.url.length > 0) {
    config.url = ensureNoTrailingSlashPath(config.url);
  }
  // Importante: quando enviamos `FormData`, NÃO podemos forçar `application/json`,
  // senão o FastAPI não reconhece `multipart/form-data` e retorna 422 (file ausente).
  if (typeof FormData !== "undefined" && config.data instanceof FormData) {
    // Deixa o axios/browser setar o multipart boundary corretamente.
    delete config.headers["Content-Type"];
  }
  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Header opcional (não quebra backend). Usado para contextualizar workspace.
  config.headers["X-Workspace"] = getStoredWorkspaceForApi();
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
