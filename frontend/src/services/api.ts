import axios from "axios";

export const API_BASE = "https://gest-o-de-projetos-production.up.railway.app/api/v1";

export const TOKEN_KEY = "sgp_access_token";

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    "Content-Type": "application/json",
  },
});

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
