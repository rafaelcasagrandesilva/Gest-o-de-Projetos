import type { Employee } from "@/services/employees";

const LABOR_KIND: Record<
  NonNullable<Employee["labor_kind"]>,
  { label: string; className: string; title: string }
> = {
  DIRETA: {
    label: "Direta",
    className: "bg-emerald-50 text-emerald-700",
    title: "Mão de obra direta: alocado em projeto.",
  },
  INDIRETA: {
    label: "Indireta",
    className: "bg-amber-50 text-amber-700",
    title: "Mão de obra indireta: vinculado a um item dos Custos Indiretos nesta competência.",
  },
  DIRETA_E_INDIRETA: {
    label: "Direta e indireta",
    className: "bg-violet-50 text-violet-700",
    title: "Divide o tempo entre projeto e Custos Indiretos nesta competência.",
  },
};

/**
 * Classificação da mão de obra na listagem de Colaboradores. Não é um campo do cadastro:
 * o backend deriva de onde a pessoa está na competência (projeto × Custos Indiretos).
 * Vermelho só quando projeto + indireto passam de 100% — aí o custo está contado em dobro.
 */
export function LaborKindBadge({ employee }: { employee: Employee }) {
  const kind = employee.labor_kind;
  if (!kind) return null;
  const cfg = LABOR_KIND[kind];
  const over = Boolean(employee.labor_over_allocated);
  return (
    <span
      className={`whitespace-nowrap rounded px-1.5 py-0.5 text-xs ${
        over ? "bg-rose-50 font-medium text-rose-700" : cfg.className
      }`}
      title={
        over
          ? "Atenção: projeto + Custos Indiretos somam mais de 100% nesta competência. " +
            "O custo desta pessoa está sendo contado em dobro."
          : cfg.title
      }
    >
      {cfg.label}
      {over && " · acima de 100%"}
    </span>
  );
}
