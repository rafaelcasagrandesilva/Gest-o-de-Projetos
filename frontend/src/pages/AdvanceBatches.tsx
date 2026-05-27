import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import { AdvanceBatchModal } from "@/components/AdvanceBatchModal";
import {
  cancelAdvanceBatch,
  deleteAdvanceBatchHard,
  fetchAdvanceBatches,
  type AdvanceBatch,
} from "@/services/receivableAdvanceBatches";
import { formatApiError } from "@/utils/apiError";
import { usePermission } from "@/hooks/usePermission";

function formatBRL(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatDateBr(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

export function AdvanceBatches() {
  const canEditInvoices = usePermission("invoices.edit");
  const [rows, setRows] = useState<AdvanceBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [viewBatchId, setViewBatchId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchAdvanceBatches();
      setRows(list);
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar borderôs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const sorted = useMemo(() => {
    return [...rows].sort((a, b) => (b.receive_date || "").localeCompare(a.receive_date || ""));
  }, [rows]);

  const operationLabel = (b: AdvanceBatch) => {
    const code = b.operation_code ?? null;
    if (code && String(code).trim()) return String(code).trim();
    if (b.batch_number) return b.batch_number;
    return `ANTECIPACAO-${String(b.id).slice(0, 8)}`;
  };

  async function handleCancel(b: AdvanceBatch) {
    if (!canEditInvoices) return;
    if (b.status !== "OPEN") return;
    const ok = window.confirm(
      `Cancelar a operação ${operationLabel(b)}?\n\n` +
        `Isso remove o vínculo das NFs e exclui as despesas automáticas (se não houver pagamento nelas).`,
    );
    if (!ok) return;
    setBusyId(b.id);
    setError(null);
    try {
      await cancelAdvanceBatch(b.id);
      await load();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível cancelar o borderô.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDeleteHard(b: AdvanceBatch) {
    if (!canEditInvoices) return;
    if (b.status !== "CANCELLED") {
      setError("Para excluir definitivamente, primeiro cancele o borderô.");
      return;
    }
    const ok = window.confirm(
      `EXCLUIR definitivamente a operação ${operationLabel(b)}?\n\n` +
        `Esta ação é irreversível e é indicada apenas para correção de erro.\n` +
        `O sistema bloqueará se houver pagamentos nas despesas do borderô.`,
    );
    if (!ok) return;
    setBusyId(b.id);
    setError(null);
    try {
      await deleteAdvanceBatchHard(b.id);
      await load();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível excluir o borderô.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Operações de antecipação</h1>
          <p className="mt-1 text-sm text-slate-600">Operações financeiras (evento real de recebimento).</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
          >
            Atualizar
          </button>
          <button
            type="button"
            disabled={!canEditInvoices}
            onClick={() => {
              setViewBatchId(null);
              setModalOpen(true);
            }}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Nova antecipação
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-[1200px] w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-2 py-2">Operação</th>
              <th className="px-2 py-2">Instituição</th>
              <th className="px-2 py-2 text-right">Qtd NFs</th>
              <th className="px-2 py-2 text-right">Bruto</th>
              <th className="px-2 py-2 text-right">Líquido</th>
              <th className="px-2 py-2 text-right">Deságio</th>
              <th className="px-2 py-2 text-right">Tarifas</th>
              <th className="px-2 py-2">Recebimento</th>
              <th className="px-2 py-2">Devolução</th>
              <th className="px-2 py-2">Status</th>
              <th className="px-2 py-2 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr>
                <td colSpan={11} className="px-3 py-10 text-center text-slate-500">
                  Carregando…
                </td>
              </tr>
            ) : sorted.length === 0 ? (
              <tr>
                <td colSpan={11} className="px-3 py-8 text-center text-slate-500">
                  Nenhum borderô criado ainda.
                </td>
              </tr>
            ) : (
              sorted.map((b) => (
                <tr key={b.id} className="hover:bg-slate-50/80">
                  <td className="whitespace-nowrap px-2 py-1.5 font-medium text-slate-900">{operationLabel(b)}</td>
                  <td className="max-w-[220px] truncate px-2 py-1.5 text-slate-700" title={b.institution}>
                    {b.institution}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{b.invoice_count}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{formatBRL(b.gross_amount)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{formatBRL(b.received_amount)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{formatBRL(b.discount_amount)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{formatBRL(b.fee_amount)}</td>
                  <td className="whitespace-nowrap px-2 py-1.5">{formatDateBr(b.receive_date)}</td>
                  <td className="whitespace-nowrap px-2 py-1.5">{formatDateBr(b.repayment_date)}</td>
                  <td className="px-2 py-1.5 text-xs">{b.status}</td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        setViewBatchId(b.id);
                        setModalOpen(true);
                      }}
                      className="rounded px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
                    >
                      Ver detalhes
                    </button>
                    <button
                      type="button"
                      disabled={!canEditInvoices || b.status !== "OPEN" || busyId === b.id}
                      onClick={() => void handleCancel(b)}
                      className="ml-1 rounded px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {busyId === b.id ? "Cancelando…" : "Cancelar"}
                    </button>
                    <button
                      type="button"
                      disabled={!canEditInvoices || b.status !== "CANCELLED" || busyId === b.id}
                      onClick={() => void handleDeleteHard(b)}
                      className="ml-1 rounded px-2 py-1 text-xs font-medium text-red-800 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {busyId === b.id ? "Excluindo…" : "Excluir"}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <AdvanceBatchModal
        open={modalOpen}
        viewBatchId={viewBatchId}
        onClose={() => {
          setModalOpen(false);
          setViewBatchId(null);
        }}
        onCreated={() => void load()}
      />
    </div>
  );
}

