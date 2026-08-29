import type { Employee } from "@/services/employees";

/**
 * Encurta um nome de Centro de Custo preservando o que identifica.
 *
 * Só é usado quando o colaborador atua em MAIS DE UM centro — aí os nomes inteiros não caberiam
 * na coluna. Palavras curtas e siglas (AT, TI) ficam intactas; as longas viram prefixo + ponto.
 * "Fiscalização AT" → "Fisca. AT"; "Administrativo" → "Admin.".
 */
export function abbreviateCostCenter(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => {
      if (w.length <= 6) return w; // "AT", "TI", "Obras"
      if (w === w.toUpperCase()) return w; // siglas longas continuam legíveis
      return `${w.slice(0, 5)}.`;
    })
    .join(" ");
}

/**
 * Centros de Custo do colaborador na listagem: o do cadastro em destaque e os das alocações
 * ativas ao lado. Sem isso, quem tem contrato em dois centros aparecia com apenas um deles —
 * e ficava parecendo que o filtro havia trazido a pessoa errada.
 */
export function CostCenterBadges({ employee }: { employee: Employee }) {
  const principal = (employee.cost_center || "").trim();
  const todos = employee.cost_centers?.length
    ? employee.cost_centers
    : principal
      ? [principal]
      : [];

  if (todos.length === 0) return <span className="text-slate-400">—</span>;

  const varios = todos.length > 1;
  return (
    <span className="flex flex-wrap gap-1" title={todos.join(" · ")}>
      {todos.map((cc) => {
        const ehPrincipal = cc.toLowerCase() === principal.toLowerCase();
        return (
          <span
            key={cc}
            className={`whitespace-nowrap rounded px-1.5 py-0.5 text-xs ${
              ehPrincipal ? "bg-indigo-50 font-medium text-indigo-700" : "bg-slate-100 text-slate-600"
            }`}
          >
            {varios ? abbreviateCostCenter(cc) : cc}
          </span>
        );
      })}
    </span>
  );
}
