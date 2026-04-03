import { useAuth } from "@/context/AuthContext";

/** True when the logged-in user has role CONSULTA (UI-only; backend enforces writes). */
export function useConsultaReadOnly(): boolean {
  const { user } = useAuth();
  return user?.role_names?.includes("CONSULTA") ?? false;
}
