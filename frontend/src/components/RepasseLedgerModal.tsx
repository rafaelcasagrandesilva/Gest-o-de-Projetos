import { useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  fetchRepasseLedger,
  DIRECTION_LABELS,
  SOURCE_LABELS,
  type LedgerStatement,
} from "@/services/advanceRepasseLedger";
import { formatApiError } from "@/utils/apiError";
import { formatCurrency, formatCurrencyOrDash } from "@/utils/currency";

function formatDateBr(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return String(iso);
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

/** Extrato de Repasse — read-only. O usuário vê Entradas/Saídas e o Saldo; nunca o Ledger interno. */
export function RepasseLedgerModal({
  institutions,
  onClose,
}: {
  institutions: { id: string; name: string }[];
  onClose: () => void;
}) {
  const [instId, setInstId] = useState<string>(institutions[0]?.id ?? "");
  const [statement, setStatement] = useState<LedgerStatement | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function run() {
      setLoading(true);
      setError(null);
      try {
        const st = await fetchRepasseLedger(instId || undefined);
        if (alive) setStatement(st);
      } catch (e) {
        if (alive) setError(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar o extrato.");
      } finally {
        if (alive) setLoading(false);
      }
    }
    void run();
    return () => {
      alive = false;
    };
  }, [instId]);

  const entries = useMemo(() => statement?.entries ?? [], [statement]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-2 sm:p-4" onClick={onClose}>
      <div
        className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-slate-200 p-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Extrato do Repasse</h2>
            <p className="mt-0.5 text-sm text-slate-600">Entradas (operações) e saídas (liquidações). Histórico preservado.</p>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
            ✕
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-4">
          <label className="text-xs font-medium text-slate-600">
            Instituição
            <select
              value={instId}
              onChange={(e) => setInstId(e.target.value)}
              className="mt-1 block w-56 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            >
              {institutions.length === 0 && <option value="">—</option>}
              {institutions.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}
                </option>
              ))}
            </select>
          </label>
          <div className="text-right">
            <p className="text-xs uppercase tracking-wide text-slate-500">Saldo do Repasse</p>
            <p className="text-xl font-semibold tabular-nums text-indigo-700">
              {statement ? formatCurrency(statement.balance) : "—"}
            </p>
          </div>
        </div>

        {error && <div className="m-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}

        <div className="overflow-x-auto p-2">
          <table className="w-full min-w-[640px] divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-2 py-2">Data</th>
                <th className="px-2 py-2">Tipo</th>
                <th className="px-2 py-2">Origem</th>
                <th className="px-2 py-2 text-right">Valor</th>
                <th className="px-2 py-2">Descrição</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                    Carregando…
                  </td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                    Sem lançamentos.
                  </td>
                </tr>
              ) : (
                entries.map((e) => {
                  const isIn = e.direction === "CREDIT";
                  const reversed = Boolean(e.reversed_at);
                  return (
                    <tr key={e.id} className={reversed ? "text-slate-400 line-through" : ""}>
                      <td className="whitespace-nowrap px-2 py-1.5">{formatDateBr(e.occurred_at)}</td>
                      <td className="px-2 py-1.5">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${
                            isIn ? "bg-emerald-100 text-emerald-900 ring-emerald-200" : "bg-red-100 text-red-800 ring-red-200"
                          }`}
                        >
                          {DIRECTION_LABELS[e.direction]}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 text-slate-600">{SOURCE_LABELS[e.source_type]}</td>
                      <td className={`px-2 py-1.5 text-right tabular-nums ${isIn ? "text-emerald-700" : "text-red-700"}`}>
                        {isIn ? "+" : "−"}
                        {formatCurrencyOrDash(e.amount)}
                      </td>
                      <td className="max-w-[240px] truncate px-2 py-1.5 text-slate-600" title={e.description || undefined}>
                        {e.description || "—"}
                        {reversed && <span className="ml-1 text-[10px] uppercase">(estornado)</span>}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
