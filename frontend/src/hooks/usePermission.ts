import { useAuth } from "@/context/AuthContext";
import { hasPermission } from "@/permissions";

/** Permissão efetiva vem do backend em `user.permission_names` (preset da role + customizações). */
export function usePermission(code: string): boolean {
  const { user } = useAuth();
  return hasPermission(user?.permission_names, code);
}

/** Mesma regra que `user_sees_all_projects` no backend (ADMIN role ou system.*). */
export function useSeesAllProjects(): boolean {
  const { user } = useAuth();
  if (user?.role_names?.includes("ADMIN")) return true;
  return (
    hasPermission(user?.permission_names, "system.admin") ||
    hasPermission(user?.permission_names, "system.all_projects")
  );
}
