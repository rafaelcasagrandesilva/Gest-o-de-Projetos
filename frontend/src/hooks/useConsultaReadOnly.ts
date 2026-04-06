import { useAuth } from "@/context/AuthContext";

/** UI: usuário sem nenhuma permissão de edição explícita (backend continua sendo a fonte da verdade). */
export function useConsultaReadOnly(): boolean {
  const { user } = useAuth();
  const p = user?.permission_names ?? [];
  if (p.includes("system.admin")) return false;
  return !p.some((c) => c.endsWith(".edit") || c === "users.manage");
}
