import { useMemo } from "react";
import type { AdvanceBatchItem } from "@/services/receivableAdvanceBatches";
import { Money } from "@/components/Money";

function formatDateBr(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

const MESES = [
  "JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ",
];

function formatCompetence(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m] = iso.slice(0, 7).split("-").map(Number);
  if (!y || !m) return "—";
  return `${MESES[m - 1]}/${y}`;
}

const BASIS_LABELS: Record<string, string> = {
  BRUTO: "Bruto",
  LIQUIDO: "Líquido",
  LIQUIDO_MENOS_10: "Líquido −10%",
  MANUAL: "Manual",
};

const STATUS_LABELS: Record<string, string> = {
  EMITIDA: "Emitida",
  ANTECIPADA: "Antecipada",
  RECEBIDA: "Recebida",
  CANCELADA: "Cancelada",
};

function statusBadgeClass(s: string | null | undefined): string {
  if (s === "RECEBIDA") return "bg-emerald-100 text-emerald-900 ring-emerald-200";
  if (s === "CANCELADA") return "bg-slate-200 text-slate-700 ring-slate-300";
  if (s === "ANTECIPADA") return "bg-amber-100 text-amber-900 ring-amber-200";
  return "bg-slate-100 text-slate-800 ring-slate-200";
}

function competenceKey(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 7) : "";
}

/**
 * Tabela rica das NFs de uma operação de antecipação. Reutilizável no detalhe da
 * operação e na composição do repasse (filtrando por competência de vencimento).
 * Os dados são derivados da própria operação — sem duplicação.
 */
export function OperationInvoicesTable({
  items,
  dueCompetenceFilter,
  onOpenInvoice,
  currentBatchId,
  onOpenOperation,
}: {
  items: AdvanceBatchItem[];
  /** Mostra apenas NFs cujo mês de vencimento é YYYY-MM (composição do repasse). */
  dueCompetenceFilter?: string;
  /** Callback para navegar até a NF (operação → NF). */
  onOpenInvoice?: (item: AdvanceBatchItem) => void;
  /** Operação atualmente aberta (para excluir das "outras operações"). */
  currentBatchId?: string;
  /** Callback para navegar até outra operação da mesma NF (regra 6). */
  onOpenOperation?: (batchId: string) => void;
}) {
  const rows = useMemo(() => {
    if (!dueCompetenceFilter) return items;
    return items.filter((it) => competenceKey(it.due_date) === dueCompetenceFilter);
  }, [items, dueCompetenceFilter]);

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-[840px] w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-600">
          <tr>
            <th className="px-2 py-2">Nº NF</th>
            <th className="px-2 py-2">Projeto</th>
            <th className="px-2 py-2">Cliente</th>
            <th className="px-2 py-2">Competência</th>
            <th className="px-2 py-2 text-right">Bruto</th>
            <th className="px-2 py-2 text-right">Líquido</th>
            <th className="px-2 py-2">Base</th>
            <th className="px-2 py-2 text-right">Antecipado</th>
            <th className="px-2 py-2">Vencimento</th>
            <th className="px-2 py-2">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={10} className="px-3 py-6 text-center text-slate-500">
                Nenhuma NF.
              </td>
            </tr>
          ) : (
            rows.map((it) => (
              <tr key={it.id} className="hover:bg-slate-50/80">
                <td className="px-2 py-1.5 font-medium">
                  {onOpenInvoice ? (
                    <button
                      type="button"
                      onClick={() => onOpenInvoice(it)}
                      className="text-indigo-700 hover:underline"
                    >
                      {it.invoice_number ?? "—"}
                    </button>
                  ) : (
                    (it.invoice_number ?? "—")
                  )}
                  {(() => {
                    // Regra 6: outras operações válidas em que esta mesma NF participa.
                    const others = (it.other_operations ?? []).filter((op) => op.id !== currentBatchId);
                    if (others.length === 0) return null;
                    return (
                      <span className="mt-0.5 block text-[10px] font-normal text-slate-500">
                        Participa também de:{" "}
                        {others.map((op, idx) => (
                          <span key={op.id}>
                            {idx > 0 ? ", " : ""}
                            {onOpenOperation ? (
                              <button
                                type="button"
                                onClick={() => onOpenOperation(op.id)}
                                className="text-indigo-600 hover:underline"
                                title={`${op.institution} — abrir operação`}
                              >
                                SGC {op.sgc_number ?? op.batch_number}
                              </button>
                            ) : (
                              <span>SGC {op.sgc_number ?? op.batch_number}</span>
                            )}
                          </span>
                        ))}
                      </span>
                    );
                  })()}
                </td>
                <td className="max-w-[140px] truncate px-2 py-1.5">{it.project_name ?? "—"}</td>
                <td className="max-w-[140px] truncate px-2 py-1.5">{it.client_name ?? "—"}</td>
                <td className="px-2 py-1.5 tabular-nums">{formatCompetence(it.competence_month)}</td>
                <td className="px-2 py-1.5">
                  <Money value={it.gross_amount} />
                </td>
                <td className="px-2 py-1.5">
                  <Money value={it.net_amount} />
                </td>
                <td className="px-2 py-1.5">{it.advance_basis ? (BASIS_LABELS[it.advance_basis] ?? it.advance_basis) : "—"}</td>
                <td className="px-2 py-1.5">
                  <Money value={it.advanced_amount} />
                </td>
                <td className="whitespace-nowrap px-2 py-1.5">{formatDateBr(it.due_date)}</td>
                <td className="px-2 py-1.5">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${statusBadgeClass(it.invoice_status)}`}
                  >
                    {it.invoice_status ? (STATUS_LABELS[it.invoice_status] ?? it.invoice_status) : "—"}
                  </span>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
