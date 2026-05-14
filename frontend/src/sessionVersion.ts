export const APP_VERSION = "2.0.0";

const VERSION_KEY = "sgp_app_version";
const TOKEN_KEY = "sgp_access_token";

function removeLegacyLocalStorage(): void {
  const keysToRemove = new Set<string>([
    TOKEN_KEY,
    "sgp_workspace",
    "sgp_permissions",
    "sgp_user",
    "sgp_user_context",
    "sgp_linked_projects",
  ]);

  for (let i = localStorage.length - 1; i >= 0; i -= 1) {
    const key = localStorage.key(i);
    if (!key || key === VERSION_KEY) continue;
    const normalized = key.toLowerCase();
    if (
      keysToRemove.has(key) ||
      normalized.includes("permission") ||
      normalized.includes("workspace") ||
      normalized.includes("token")
    ) {
      localStorage.removeItem(key);
    }
  }
}

export function enforceClientSessionVersion(): void {
  if (typeof window === "undefined") return;

  try {
    const savedVersion = localStorage.getItem(VERSION_KEY);
    if (savedVersion === APP_VERSION) return;

    removeLegacyLocalStorage();
    sessionStorage.clear();
    localStorage.setItem(VERSION_KEY, APP_VERSION);
  } catch {
    // Storage pode estar indisponivel em contextos restritos; nesse caso seguimos sem persistencia.
  }
}
