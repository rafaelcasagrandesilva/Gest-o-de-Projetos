import { useAuth } from "@/context/AuthContext";

/** Shown on disabled actions when the user is GESTOR (global data is admin-only). */
export const GESTOR_GLOBAL_EDIT_TOOLTIP = "Somente administradores podem editar";

/** True when the user is GESTOR and not ADMIN (global master data is read-only in UI). */
export function useGestorGlobalReadOnly(): boolean {
  const { user } = useAuth();
  const names = user?.role_names ?? [];
  return names.includes("GESTOR") && !names.includes("ADMIN");
}
