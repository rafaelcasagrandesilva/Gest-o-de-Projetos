import { useMemo, useState } from "react";
import type { CompanyFinancialItem, TipoFinanceiro } from "@/services/companyFinance";
import { formatCurrencyOrDash } from "@/utils/currency";
import { StatusBadge, type StatusTone } from "@/components/finance/StatusBadge";

type SortDir = "asc" | "desc";

/** Valores redigidos por "Dados sensíveis": backend envia `valor_referencia = null`. */
function isRedacted(item: CompanyFinancialItem): boolean {
  return item.valor_referencia == null;
}

/** Base financeira ÚNICA da dívida (espelha a fonte da verdade do backend): renegociado
 *  válido (> 0) senão valor_referencia. Null quando redigido. */
function baseOf(item: CompanyFinancialItem): number | null {
  if (isRedacted(item)) return null;
  const base = item.debt_base;
  if (base != null && base > 0) return base;
  return item.valor_referencia;
}

/** % Quitado da dívida inteira = (Pago Total / base) * 100. Null quando redigido. */
function pctQuitadoOf(item: CompanyFinancialItem): number | null {
  const base = baseOf(item);
  if (base == null || item.total_pago == null) return null;
  if (!(base > 0)) return 0;
  return (item.total_pago / base) * 100;
}

/** Saldo Restante da dívida inteira = base − Pago Total (nunca negativo). Null quando redigido. */
function saldoOf(item: CompanyFinancialItem): number | null {
  const base = baseOf(item);
  if (base == null || item.total_pago == null) return null;
  return Math.max(0, base - item.total_pago);
}

function formatPctOrDash(n: number | null): string {
  if (n == null) return "—";
  return `${n.toFixed(1).replace(".", ",")}%`;
}

/** Valor lançado na grade mensal para a competência (YYYY-MM); null quando não informado. */
function gridValueForMonth(item: CompanyFinancialItem, mes: string): number | null {
  const p = item.pagamentos.find((x) => x.mes === mes);
  return p && p.valor != null && p.valor > 0 ? p.valor : null;
}

/** Valor Mensal — regra do CAP: grade (se lançada) senão valor de referência. Null se redigido. */
function valorMensalOf(item: CompanyFinancialItem, competencia: string): number | null {
  const g = gridValueForMonth(item, competencia);
  if (g != null) return g;
  return item.valor_referencia; // number | null
}

/** Valor Anual híbrido: grade (se lançada) senão referência, por mês. Null se redigido. */
function valorAnualOf(item: CompanyFinancialItem, competencia: string): number | null {
  if (isRedacted(item)) return null;
  const year = competencia.slice(0, 4);
  let total = 0;
  for (let m = 1; m <= 12; m++) {
    const mes = `${year}-${String(m).padStart(2, "0")}`;
    const g = gridValueForMonth(item, mes);
    total += g != null ? g : (item.valor_referencia ?? 0);
  }
  return total;
}

/** Pago no mês — espelho do CAP (amount_paid); null quando redigido, 0 quando sem lançamento. */
function capPaidOf(item: CompanyFinancialItem): number | null {
  if (isRedacted(item)) return null;
  return item.cap_amount_paid ?? 0;
}

/** Saldo (Custos Fixos) = Valor Mensal − Pago no mês. Null quando redigido. */
function saldoMensalOf(item: CompanyFinancialItem, competencia: string): number | null {
  const mensal = valorMensalOf(item, competencia);
  const pago = capPaidOf(item);
  if (mensal == null || pago == null) return null;
  return mensal - pago;
}

/** Status financeiro espelhado do Contas a Pagar; null quando ainda não há lançamento. */
function capStatusDisplay(item: CompanyFinancialItem): { label: string; tone: StatusTone } | null {
  if (!item.cap_has_line) return null;
  if (item.cap_is_obsolete) return { label: "Cancelado", tone: "red" };
  switch (item.cap_status) {
    case "PAGO":
      return { label: "Pago", tone: "green" };
    case "PARCIAL":
      return { label: "Parcial", tone: "blue" };
    case "ABERTO":
      return { label: "Em aberto", tone: "amber" };
    default:
      return null;
  }
}

/** Nome com ícones discretos de Processo Judicial (⚖️) e Renegociação (🔄) — só no Extrato. */
function nameCell(item: CompanyFinancialItem): React.ReactNode {
  return (
    <span className="font-medium text-slate-900">
      {item.has_legal_process ? (
        <span className="mr-1" title="Processo judicial" aria-label="Processo judicial">
          ⚖️
        </span>
      ) : null}
      {item.has_renegotiation ? (
        <span className="mr-1" title="Renegociado" aria-label="Renegociado">
          🔄
        </span>
      ) : null}
      {item.nome}
    </span>
  );
}

/** Célula de Status — espelha o CAP; "—" quando não há lançamento na competência. */
function statusCell(item: CompanyFinancialItem): React.ReactNode {
  const s = capStatusDisplay(item);
  if (!s) return <span className="text-slate-400">—</span>;
  return <StatusBadge label={s.label} tone={s.tone} />;
}

type Column = {
  key: string;
  label: string;
  align: "left" | "right";
  sortable: boolean;
  /** valor para ordenação (number ou string) */
  sortValue?: (i: CompanyFinancialItem) => number | string;
  /** célula renderizada */
  cell: (i: CompanyFinancialItem) => React.ReactNode;
};

function buildColumns(tipo: TipoFinanceiro, competencia: string): Column[] {
  const categoria: Column = {
    key: "category",
    label: "Categoria",
    align: "left",
    sortable: true,
    sortValue: (i) => i.category ?? "",
    cell: (i) => <span className="text-slate-600">{i.category ?? "—"}</span>,
  };
  const centroCusto: Column = {
    key: "cost_center",
    label: "Centro de Custo",
    align: "left",
    sortable: true,
    sortValue: (i) => i.cost_center ?? "",
    cell: (i) => <span className="text-slate-600">{i.cost_center || "—"}</span>,
  };
  // Status: espelha SOMENTE o status financeiro do Contas a Pagar (não calcula nada).
  const status: Column = {
    key: "status",
    label: "Status",
    align: "left",
    sortable: false,
    cell: (i) => statusCell(i),
  };
  // Pago no mês: consulta o Contas a Pagar (amount_paid) — 0,00 quando não há lançamento.
  const pagoNoMes: Column = {
    key: "pago_mes",
    label: "Pago no mês",
    align: "right",
    sortable: true,
    sortValue: (i) => capPaidOf(i) ?? -1,
    cell: (i) => {
      const v = capPaidOf(i);
      return (
        <span className={`tabular-nums ${(v ?? 0) > 0.009 ? "text-emerald-700" : "text-slate-500"}`}>
          {formatCurrencyOrDash(v)}
        </span>
      );
    },
  };

  if (tipo === "endividamento") {
    // Módulo exclusivo de Endividamento → coluna "Categoria" omitida (todos têm a mesma).
    return [
      {
        key: "nome",
        label: "Credor",
        align: "left",
        sortable: true,
        sortValue: (i) => i.nome,
        cell: (i) => nameCell(i),
      },
      centroCusto,
      {
        key: "valor_referencia",
        label: "Valor da Dívida",
        align: "right",
        sortable: true,
        sortValue: (i) => baseOf(i) ?? -1,
        cell: (i) => <span className="tabular-nums text-slate-700">{formatCurrencyOrDash(baseOf(i))}</span>,
      },
      {
        key: "total_pago",
        label: "Pago Total",
        align: "right",
        sortable: true,
        sortValue: (i) => i.total_pago ?? -1,
        cell: (i) => <span className="tabular-nums text-emerald-700">{formatCurrencyOrDash(i.total_pago)}</span>,
      },
      {
        key: "saldo",
        label: "Saldo Restante",
        align: "right",
        sortable: true,
        sortValue: (i) => saldoOf(i) ?? -1,
        cell: (i) => {
          const s = saldoOf(i);
          return (
            <span className={`tabular-nums ${(s ?? 0) > 0.009 ? "text-rose-600" : "text-slate-500"}`}>
              {formatCurrencyOrDash(s)}
            </span>
          );
        },
      },
      {
        key: "pct",
        label: "% Quitado",
        align: "right",
        sortable: true,
        sortValue: (i) => pctQuitadoOf(i) ?? -1,
        cell: (i) => <span className="tabular-nums text-slate-700">{formatPctOrDash(pctQuitadoOf(i))}</span>,
      },
      pagoNoMes,
      status,
    ];
  }

  // custo_fixo
  return [
    {
      key: "nome",
      label: "Despesa",
      align: "left",
      sortable: true,
      sortValue: (i) => i.nome,
      cell: (i) => nameCell(i),
    },
    categoria,
    centroCusto,
    {
      key: "valor_mensal",
      label: "Valor Mensal",
      align: "right",
      sortable: true,
      sortValue: (i) => valorMensalOf(i, competencia) ?? -1,
      cell: (i) => (
        <span className="tabular-nums text-slate-700">{formatCurrencyOrDash(valorMensalOf(i, competencia))}</span>
      ),
    },
    {
      key: "valor_anual",
      label: "Valor Anual",
      align: "right",
      sortable: true,
      sortValue: (i) => valorAnualOf(i, competencia) ?? -1,
      cell: (i) => (
        <span className="tabular-nums text-slate-700">{formatCurrencyOrDash(valorAnualOf(i, competencia))}</span>
      ),
    },
    pagoNoMes,
    {
      key: "saldo",
      label: "Saldo",
      align: "right",
      sortable: true,
      sortValue: (i) => saldoMensalOf(i, competencia) ?? -1,
      cell: (i) => {
        const s = saldoMensalOf(i, competencia);
        return (
          <span className={`tabular-nums ${Math.abs(s ?? 0) > 0.009 ? "text-rose-600" : "text-slate-500"}`}>
            {formatCurrencyOrDash(s)}
          </span>
        );
      },
    },
    status,
  ];
}

export type RequiredFilter = "ALL" | "REQUIRED" | "PENDING";

export type StatusFilter = "ALL" | "ABERTO" | "PARCIAL" | "RENEGOCIADO" | "JUDICIAL" | "QUITADO";

export const REQUIRED_FILTER_OPTIONS: { key: RequiredFilter; label: string }[] = [
  { key: "ALL", label: "Todos" },
  { key: "REQUIRED", label: "Obrigatórios" },
  { key: "PENDING", label: "Pendentes" },
];

export const STATUS_FILTER_OPTIONS: { key: StatusFilter; label: string }[] = [
  { key: "ALL", label: "Todos" },
  { key: "ABERTO", label: "Em aberto" },
  { key: "PARCIAL", label: "Parcial" },
  { key: "RENEGOCIADO", label: "Renegociado" },
  { key: "JUDICIAL", label: "Judicial" },
  { key: "QUITADO", label: "Quitado" },
];

/** Predicado do filtro de status (endividamento). Critérios multi (Judicial/Renegociado podem coexistir). */
export function matchesStatusFilter(item: CompanyFinancialItem, key: StatusFilter): boolean {
  if (key === "ALL") return true;
  const quitado = item.status === "quitado" || (pctQuitadoOf(item) ?? 0) >= 100;
  switch (key) {
    case "QUITADO":
      return quitado;
    case "JUDICIAL":
      return !quitado && Boolean(item.has_legal_process);
    case "RENEGOCIADO":
      return !quitado && Boolean(item.has_renegotiation);
    case "PARCIAL":
      return !quitado && (item.total_pago ?? 0) > 0;
    case "ABERTO":
      return !quitado && (item.total_pago ?? 0) <= 0;
    default:
      return true;
  }
}

export function CompanyFinanceAnalyticTable({
  items,
  tipo,
  competencia,
  search,
  readOnly = false,
  readOnlyTitle,
  onToggleRequired,
}: {
  items: CompanyFinancialItem[];
  tipo: TipoFinanceiro;
  competencia: string;
  search: string;
  readOnly?: boolean;
  readOnlyTitle?: string;
  onToggleRequired?: (itemId: string, value: boolean) => void | Promise<void>;
}) {
  const columns = useMemo(() => buildColumns(tipo, competencia), [tipo, competencia]);
  const showRequiredColumn = true;
  const [sortKey, setSortKey] = useState<string>("nome");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  function onSort(col: Column) {
    if (!col.sortable) return;
    if (col.key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(col.key);
      setSortDir(col.key === "nome" || col.key === "category" || col.key === "cost_center" ? "asc" : "desc");
    }
  }

  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sortKey);
    const rows = [...items];
    if (!col || !col.sortValue) return rows;
    const acc = col.sortValue;
    const factor = sortDir === "asc" ? 1 : -1;
    rows.sort((a, b) => {
      const va = acc(a);
      const vb = acc(b);
      let cmp: number;
      if (typeof va === "number" && typeof vb === "number") cmp = va - vb;
      else cmp = String(va).localeCompare(String(vb), "pt-BR");
      if (cmp === 0) cmp = a.nome.localeCompare(b.nome, "pt-BR");
      return cmp * factor;
    });
    return rows;
  }, [items, columns, sortKey, sortDir]);

  // Filtros de Tipo/Status são globais (aplicados no componente pai antes de `items`);
  // aqui só ordenamos. Mantém exatamente os mesmos registros que a Visão Executiva.
  const visibleRows = sorted;

  const minWidth = tipo === "endividamento" ? "min-w-[1040px]" : "min-w-[980px]";

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-medium text-slate-900">Extrato analítico</h2>
        <p className="text-xs text-slate-500">Consulta tabular de todos os registros no mesmo período.</p>
      </div>

      {visibleRows.length === 0 ? (
        <p className="text-sm text-slate-500">
          {search.trim()
            ? "Nenhum item corresponde à busca."
            : "Nenhum item encontrado para este filtro."}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className={`w-full ${minWidth} text-left text-sm`}>
            <thead className="border-b border-slate-100 bg-slate-50/80">
              <tr>
                {columns.map((col) => {
                  const active = col.sortable && col.key === sortKey;
                  const indicator = !active ? "↕" : sortDir === "asc" ? "↑" : "↓";
                  return (
                    <th
                      key={col.key}
                      className={`px-3 py-2 text-xs font-semibold uppercase tracking-wide ${col.align === "right" ? "text-right" : "text-left"} ${col.sortable ? "" : "text-slate-600"}`}
                      aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                    >
                      {col.sortable ? (
                        <button
                          type="button"
                          onClick={() => onSort(col)}
                          className={`group inline-flex max-w-full items-center gap-1 ${col.align === "right" ? "ml-auto flex-row-reverse" : ""} ${
                            active ? "text-indigo-700" : "text-slate-600 hover:text-slate-900"
                          }`}
                        >
                          <span className="truncate">{col.label}</span>
                          <span
                            className={`shrink-0 text-[10px] leading-none tabular-nums ${active ? "text-indigo-600" : "text-slate-400 opacity-60 group-hover:opacity-100"}`}
                            aria-hidden
                          >
                            {indicator}
                          </span>
                        </button>
                      ) : (
                        col.label
                      )}
                    </th>
                  );
                })}
                {showRequiredColumn && (
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                    Obrigatório
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {visibleRows.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50/60">
                  {columns.map((col) => (
                    <td key={col.key} className={`px-3 py-2 ${col.align === "right" ? "text-right" : "text-left"}`}>
                      {col.cell(item)}
                    </td>
                  ))}
                  {showRequiredColumn && (
                    <td className="px-3 py-2 text-left">
                      <label
                        className={`inline-flex items-center gap-2 ${readOnly ? "cursor-not-allowed" : "cursor-pointer"}`}
                        title={readOnly ? readOnlyTitle : "Marcar/desmarcar custo fixo obrigatório mensal"}
                      >
                        <input
                          type="checkbox"
                          checked={Boolean(item.is_monthly_required)}
                          disabled={readOnly}
                          onChange={(e) => void onToggleRequired?.(item.id, e.target.checked)}
                          className="h-4 w-4 rounded border-slate-300 text-amber-600 focus:ring-amber-500"
                        />
                        {item.is_monthly_required ? (
                          <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
                            ☑ Obrigatório
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
                            ☐ Não obrigatório
                          </span>
                        )}
                      </label>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
