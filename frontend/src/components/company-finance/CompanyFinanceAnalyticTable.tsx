import { useMemo, useState } from "react";
import type { CompanyFinancialItem, TipoFinanceiro } from "@/services/companyFinance";
import { formatCurrency } from "@/utils/currency";
import { StatusBadge, type StatusTone } from "@/components/finance/StatusBadge";

type SortDir = "asc" | "desc";

/** Saldo pendente (endividamento), reaproveitando `restante` já carregado. */
function saldoOf(item: CompanyFinancialItem): number {
  if (item.restante != null) return item.restante;
  return Math.max(0, item.valor_referencia - item.total_pago);
}

/** % Quitado = (total_pago / valor_referencia) * 100. */
function pctQuitadoOf(item: CompanyFinancialItem): number {
  if (!(item.valor_referencia > 0)) return 0;
  return (item.total_pago / item.valor_referencia) * 100;
}

/** Valor anual estimado para custo fixo: valor mensal × 12. */
function valorAnualOf(item: CompanyFinancialItem): number {
  return item.valor_referencia * 12;
}

function formatPct(n: number): string {
  return `${n.toFixed(1).replace(".", ",")}%`;
}

/** Status de exibição derivado dos mesmos dados (sem nova regra). */
function statusOf(item: CompanyFinancialItem, tipo: TipoFinanceiro): { label: string; tone: StatusTone } {
  if (tipo === "endividamento") {
    if (item.status === "quitado" || pctQuitadoOf(item) >= 100) return { label: "Quitado", tone: "green" };
    if (item.has_renegotiation) return { label: "Renegociado", tone: "blue" };
    if (item.total_pago > 0) return { label: "Parcial", tone: "amber" };
    return { label: "Em aberto", tone: "red" };
  }
  // custo_fixo: cobertura do mês (pago_mes vs valor mensal esperado).
  const ref = item.valor_referencia;
  if (ref > 0 && item.pago_mes >= ref) return { label: "Pago", tone: "green" };
  if (item.pago_mes > 0) return { label: "Parcial", tone: "amber" };
  return { label: "Pendente", tone: "red" };
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

function buildColumns(tipo: TipoFinanceiro): Column[] {
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
  const status: Column = {
    key: "status",
    label: "Status",
    align: "left",
    sortable: false,
    cell: (i) => {
      const s = statusOf(i, tipo);
      return <StatusBadge label={s.label} tone={s.tone} />;
    },
  };

  if (tipo === "endividamento") {
    return [
      {
        key: "nome",
        label: "Credor",
        align: "left",
        sortable: true,
        sortValue: (i) => i.nome,
        cell: (i) => <span className="font-medium text-slate-900">{i.nome}</span>,
      },
      categoria,
      centroCusto,
      {
        key: "valor_referencia",
        label: "Referência",
        align: "right",
        sortable: true,
        sortValue: (i) => i.valor_referencia,
        cell: (i) => <span className="tabular-nums text-slate-700">{formatCurrency(i.valor_referencia)}</span>,
      },
      {
        key: "total_pago",
        label: "Pago",
        align: "right",
        sortable: true,
        sortValue: (i) => i.total_pago,
        cell: (i) => <span className="tabular-nums text-emerald-700">{formatCurrency(i.total_pago)}</span>,
      },
      {
        key: "saldo",
        label: "Saldo",
        align: "right",
        sortable: true,
        sortValue: (i) => saldoOf(i),
        cell: (i) => {
          const s = saldoOf(i);
          return <span className={`tabular-nums ${s > 0.009 ? "text-rose-600" : "text-slate-500"}`}>{formatCurrency(s)}</span>;
        },
      },
      {
        key: "pct",
        label: "% Quitado",
        align: "right",
        sortable: true,
        sortValue: (i) => pctQuitadoOf(i),
        cell: (i) => <span className="tabular-nums text-slate-700">{formatPct(pctQuitadoOf(i))}</span>,
      },
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
      cell: (i) => <span className="font-medium text-slate-900">{i.nome}</span>,
    },
    categoria,
    centroCusto,
    {
      key: "valor_mensal",
      label: "Valor Mensal",
      align: "right",
      sortable: true,
      sortValue: (i) => i.valor_referencia,
      cell: (i) => <span className="tabular-nums text-slate-700">{formatCurrency(i.valor_referencia)}</span>,
    },
    {
      key: "valor_anual",
      label: "Valor Anual",
      align: "right",
      sortable: true,
      sortValue: (i) => valorAnualOf(i),
      cell: (i) => <span className="tabular-nums text-slate-700">{formatCurrency(valorAnualOf(i))}</span>,
    },
    {
      key: "pago_mes",
      label: "Pago no mês",
      align: "right",
      sortable: true,
      sortValue: (i) => i.pago_mes,
      cell: (i) => (
        <span className={`tabular-nums ${i.pago_mes > 0.009 ? "text-emerald-700" : "text-slate-500"}`}>
          {formatCurrency(i.pago_mes)}
        </span>
      ),
    },
    status,
  ];
}

type RequiredFilter = "ALL" | "REQUIRED" | "PENDING";

export function CompanyFinanceAnalyticTable({
  items,
  tipo,
  search,
  onSearch,
  readOnly = false,
  readOnlyTitle,
  pendingItemIds,
  onToggleRequired,
}: {
  items: CompanyFinancialItem[];
  tipo: TipoFinanceiro;
  search: string;
  onSearch: (v: string) => void;
  readOnly?: boolean;
  readOnlyTitle?: string;
  pendingItemIds?: Set<string>;
  onToggleRequired?: (itemId: string, value: boolean) => void | Promise<void>;
}) {
  const columns = useMemo(() => buildColumns(tipo), [tipo]);
  const showRequiredColumn = tipo === "custo_fixo";
  const [sortKey, setSortKey] = useState<string>("nome");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [requiredFilter, setRequiredFilter] = useState<RequiredFilter>("ALL");

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

  const visibleRows = useMemo(() => {
    if (!showRequiredColumn || requiredFilter === "ALL") return sorted;
    if (requiredFilter === "REQUIRED") return sorted.filter((i) => i.is_monthly_required);
    return sorted.filter((i) => pendingItemIds?.has(i.id));
  }, [sorted, showRequiredColumn, requiredFilter, pendingItemIds]);

  const minWidth = tipo === "endividamento" ? "min-w-[860px]" : "min-w-[920px]";

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-medium text-slate-900">Extrato analítico</h2>
          <p className="text-xs text-slate-500">Consulta tabular de todos os registros no mesmo período.</p>
        </div>
        <label className="flex min-w-[min(100%,280px)] flex-1 flex-col gap-1 text-sm sm:max-w-md">
          <span className="font-medium text-slate-700">Buscar</span>
          <input
            type="search"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Buscar item, fornecedor ou descrição..."
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 shadow-sm"
          />
        </label>
      </div>

      {showRequiredColumn && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Filtrar:</span>
          {([
            { key: "ALL", label: "Todos" },
            { key: "REQUIRED", label: "Obrigatórios" },
            { key: "PENDING", label: "Pendentes" },
          ] as { key: RequiredFilter; label: string }[]).map((opt) => {
            const active = requiredFilter === opt.key;
            return (
              <button
                key={opt.key}
                type="button"
                onClick={() => setRequiredFilter(opt.key)}
                aria-pressed={active}
                className={`rounded-full px-3 py-1 text-xs font-medium ring-1 transition ${
                  active
                    ? "bg-indigo-600 text-white ring-indigo-600"
                    : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      )}

      {visibleRows.length === 0 ? (
        <p className="text-sm text-slate-500">
          {search.trim()
            ? "Nenhum item corresponde à busca."
            : requiredFilter !== "ALL"
              ? "Nenhum item corresponde ao filtro selecionado."
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
