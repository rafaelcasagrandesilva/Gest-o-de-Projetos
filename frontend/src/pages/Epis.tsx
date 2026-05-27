import { Assets } from "@/pages/Assets";

/** Listagem operacional de EPIs (mesma base de dados dos ativos, escopo EPI). */
export function Epis() {
  return <Assets variant="epi" />;
}
