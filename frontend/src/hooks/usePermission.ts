import { useAuth } from "@/context/AuthContext";
import { hasPermission } from "@/permissions";

/** Permissão efetiva vem do backend em `user.permission_names` (preset da role + customizações). */
export function usePermission(code: string): boolean {
  const { user } = useAuth();
  return hasPermission(user?.permission_names, code);
}

/**
 * Pode usar visão consolidada "Todos" no dashboard (UI).
 * - ADMIN / system.admin / system.all_projects (como no backend).
 * - Ou vínculo com todos os projetos do sistema (`has_all_projects_linked` em /users/me).
 * Consultas à API continuam filtradas pelo backend conforme escopo real.
 */
export function useSeesAllProjects(): boolean {
  const { user } = useAuth();
  if (user?.role_names?.includes("ADMIN")) return true;
  if (
    hasPermission(user?.permission_names, "system.admin") ||
    hasPermission(user?.permission_names, "system.all_projects")
  ) {
    return true;
  }
  if (user?.has_all_projects_linked) return true;
  return false;
}
