import { useAuth } from "@/context/AuthContext";
import { hasPermission } from "@/permissions";

/**
 * UI somente leitura quando não há permissões de mutação.
 * Backend continua sendo a fonte da verdade — isto evita confusão e alinha com RBAC.
 */
export function useConsultaReadOnly(): boolean {
  const { user } = useAuth();
  const p = user?.permission_names ?? [];
  if (hasPermission(p, "system.admin")) return false;
  const canMutate = p.some(
    (c) =>
      c.endsWith(".edit") ||
      c.endsWith(".create") ||
      c.endsWith(".delete") ||
      c === "users.manage",
  );
  return !canMutate;
}
