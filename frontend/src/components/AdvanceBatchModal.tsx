import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  createAdvanceBatch,
  fetchAdvanceBatch,
  fetchEligibleInvoicesForBatch,
  cancelAdvanceBatch,
  deleteAdvanceBatchHard,
  updateAdvanceBatchDashboardInclusion,
  type AdvanceBatch,
  type AdvanceBatchEligibleInvoice,
} from "@/services/receivableAdvanceBatches";
import { formatApiError } from "@/utils/apiError";

function formatBRL(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatDateBr(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

function parseMoney(raw: string): number {
  const t = raw.replace(/\s/g, "").replace(/R\$\s?/i, "");
  return Number.parseFloat(t.replace(/\./g, "").replace(",", ".")) || 0;
}

function todayIso(): string {
  const t = new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
}

type Props = {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  /** Visualizar borderô existente */
  viewBatchId?: string | null;
};

export function AdvanceBatchModal({ open, onClose, onCreated, viewBatchId }: Props) {
  const isView = Boolean(viewBatchId);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invoices, setInvoices] = useState<AdvanceBatchEligibleInvoice[]>([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<AdvanceBatch | null>(null);
  const [includeInDashboard, setIncludeInDashboard] = useState(true);
  const [dashboardSaving, setDashboardSaving] = useState(false);

  const [institution, setInstitution] = useState("");
  const [operationCode, setOperationCode] = useState("");
  const [operationType, setOperationType] = useState<"BORDERO" | "FACTORING" | "FIDC" | "OUTROS">("BORDERO");
  const [receiveDate, setReceiveDate] = useState(todayIso());
  const [repaymentDate, setRepaymentDate] = useState("");
  const [receivedAmount, setReceivedAmount] = useState("");
  const [discountAmount, setDiscountAmount] = useState("");
  const [feeAmount, setFeeAmount] = useState("");
  const [observation, setObservation] = useState("");

  const loadEligible = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchEligibleInvoicesForBatch({
        search: search.trim() || undefined,
      });
      setInvoices(rows);
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível carregar NFs elegíveis.");
    } finally {
      setLoading(false);
    }
  }, [search]);

  const loadDetail = useCallback(async () => {
    if (!viewBatchId) return;
    setLoading(true);
    setError(null);
    try {
      const b = await fetchAdvanceBatch(viewBatchId);
      setDetail(b);
      setIncludeInDashboard(b.include_in_dashboard !== false);
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível carregar o borderô.");
    } finally {
      setLoading(false);
    }
  }, [viewBatchId]);

  useEffect(() => {
    if (!open) return;
    if (isView) {
      void loadDetail();
    } else {
      void loadEligible();
    }
  }, [open, isView, loadDetail, loadEligible]);

  const grossTotal = useMemo(() => {
    let sum = 0;
    for (const id of selected) {
      const inv = invoices.find((r) => r.id === id);
      if (inv) sum += inv.gross_amount;
    }
    return Math.round(sum * 100) / 100;
  }, [selected, invoices]);

  const receivedNum = parseMoney(receivedAmount);
  const discountNum = parseMoney(discountAmount);
  const discountPct = grossTotal > 0.005 ? ((discountNum / grossTotal) * 100).toFixed(2) : "—";

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (selected.size < 2) {
      setError("Selecione no mínimo 2 notas fiscais.");
      return;
    }
    if (!institution.trim()) {
      setError("Informe a instituição.");
      return;
    }
    if (!receiveDate || !repaymentDate) {
      setError("Informe as datas de recebimento e devolução.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createAdvanceBatch({
        operation_type: operationType,
        operation_code: operationCode.trim() || null,
        institution: institution.trim(),
        received_amount: receivedNum,
        discount_amount: discountNum,
        fee_amount: parseMoney(feeAmount),
        receive_date: receiveDate,
        repayment_date: repaymentDate,
        observation: observation.trim() || null,
        invoice_ids: [...selected],
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(isAxiosError(err) ? formatApiError(err) : "Não foi possível criar o borderô.");
    } finally {
      setSaving(false);
    }
  }

  function operationLabel(): string {
    if (!detail) return "";
    const code = (detail.operation_code ?? "").trim();
    if (code) return code;
    if ((detail.batch_number ?? "").trim()) return detail.batch_number;
    return `ANTECIPACAO-${detail.id.slice(0, 8)}`;
  }

  async function handleSaveDashboardInclusion() {
    if (!detail) return;
    setDashboardSaving(true);
    setError(null);
    try {
      const updated = await updateAdvanceBatchDashboardInclusion(detail.id, includeInDashboard);
      setDetail(updated);
      onCreated();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar.");
    } finally {
      setDashboardSaving(false);
    }
  }

  async function handleCancelBatch() {
    if (!detail) return;
    if (detail.status !== "OPEN") return;
    const ok = window.confirm(
      `Cancelar a operação ${operationLabel()}?\n\n` +
        `Isso remove o vínculo das NFs e exclui as despesas automáticas (se não houver pagamento nelas).`,
    );
    if (!ok) return;
    setSaving(true);
    setError(null);
    try {
      await cancelAdvanceBatch(detail.id);
      onCreated();
      onClose();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível cancelar o borderô.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteHard() {
    if (!detail) return;
    if (detail.status !== "CANCELLED") {
      setError("Para excluir definitivamente, primeiro cancele o borderô.");
      return;
    }
    const ok = window.confirm(
      `EXCLUIR definitivamente a operação ${operationLabel()}?\n\n` +
        `Esta ação é irreversível e indicada apenas para correção de erro.\n` +
        `O sistema bloqueará se houver pagamentos nas despesas do borderô.`,
    );
    if (!ok) return;
    setSaving(true);
    setError(null);
    try {
      await deleteAdvanceBatchHard(detail.id);
      onCreated();
      onClose();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível excluir o borderô.");
    } finally {
      setSaving(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        className="my-4 w-full max-w-5xl rounded-xl border border-slate-200 bg-white shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 className="text-lg font-semibold text-slate-900">
            {isView ? `Operação ${detail?.operation_code ?? detail?.batch_number ?? ""}` : "Nova antecipação"}
          </h2>
          <button type="button" onClick={onClose} className="text-sm text-slate-600 hover:text-slate-900">
            Fechar
          </button>
        </div>

        {error ? (
          <div className="mx-5 mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        {isView && detail ? (
          <div className="space-y-4 p-5 text-sm">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                disabled={saving || detail.status !== "OPEN"}
                onClick={() => void handleCancelBatch()}
                className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving ? "Cancelando…" : "Cancelar borderô"}
              </button>
              <button
                type="button"
                disabled={saving || detail.status !== "CANCELLED"}
                onClick={() => void handleDeleteHard()}
                className="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-sm font-medium text-red-900 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving ? "Excluindo…" : "Excluir definitivamente"}
              </button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <p>
                <span className="text-slate-500">Operação:</span>{" "}
                {detail.operation_code ?? detail.batch_number ?? `ANTECIPACAO-${detail.id.slice(0, 8)}`}
              </p>
              <p>
                <span className="text-slate-500">Instituição:</span> {detail.institution}
              </p>
              <p>
                <span className="text-slate-500">Recebimento:</span> {formatDateBr(detail.receive_date)}
              </p>
              <p>
                <span className="text-slate-500">Devolução:</span> {formatDateBr(detail.repayment_date)}
              </p>
              <p>
                <span className="text-slate-500">Bruto:</span> {formatBRL(detail.gross_amount)}
              </p>
              <p>
                <span className="text-slate-500">Líquido:</span> {formatBRL(detail.received_amount)}
              </p>
              <p>
                <span className="text-slate-500">Deságio:</span> {formatBRL(detail.discount_amount)}
                {detail.discount_percent != null ? ` (${detail.discount_percent}%)` : null}
              </p>
              <p>
                <span className="text-slate-500">Tarifas:</span> {formatBRL(detail.fee_amount)}
              </p>
              <p>
                <span className="text-slate-500">Status:</span> {detail.status}
              </p>
            </div>
            {detail.observation ? (
              <p className="text-slate-600">
                <span className="font-medium">Obs.:</span> {detail.observation}
              </p>
            ) : null}
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={includeInDashboard}
                  onChange={(e) => setIncludeInDashboard(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300"
                />
                <span className="text-slate-700">Considerar no Dashboard Financeiro</span>
              </label>
              {includeInDashboard !== (detail.include_in_dashboard !== false) ? (
                <button
                  type="button"
                  disabled={dashboardSaving}
                  onClick={() => void handleSaveDashboardInclusion()}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {dashboardSaving ? "Salvando…" : "Salvar participação no dashboard"}
                </button>
              ) : null}
            </div>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-600">
                  <tr>
                    <th className="px-2 py-2">NF</th>
                    <th className="px-2 py-2">Projeto</th>
                    <th className="px-2 py-2">Cliente</th>
                    <th className="px-2 py-2 text-right">Valor</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {detail.items.map((it) => (
                    <tr key={it.id}>
                      <td className="px-2 py-1.5">{it.invoice_number}</td>
                      <td className="px-2 py-1.5">{it.project_name ?? "—"}</td>
                      <td className="px-2 py-1.5">{it.client_name ?? "—"}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{formatBRL(it.invoice_amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : loading ? (
          <p className="p-8 text-center text-sm text-slate-500">Carregando…</p>
        ) : (
          <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 p-5">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Tipo</span>
                <select
                  value={operationType}
                  onChange={(e) => setOperationType(e.target.value as typeof operationType)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                >
                  <option value="BORDERO">Borderô</option>
                  <option value="FACTORING">Factoring</option>
                  <option value="FIDC">FIDC</option>
                  <option value="OUTROS">Outros</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Identificação da operação</span>
                <input
                  value={operationCode}
                  onChange={(e) => setOperationCode(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="Ex.: LEPTA-2026-019"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Instituição *</span>
                <input
                  required
                  value={institution}
                  onChange={(e) => setInstitution(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Data recebimento *</span>
                <input
                  type="date"
                  required
                  value={receiveDate}
                  onChange={(e) => setReceiveDate(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Data devolução *</span>
                <input
                  type="date"
                  required
                  value={repaymentDate}
                  onChange={(e) => setRepaymentDate(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Valor líquido recebido *</span>
                <input
                  value={receivedAmount}
                  onChange={(e) => setReceivedAmount(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="0,00"
                  inputMode="decimal"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Deságio</span>
                <input
                  value={discountAmount}
                  onChange={(e) => setDiscountAmount(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="0,00"
                  inputMode="decimal"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Tarifas bancárias</span>
                <input
                  value={feeAmount}
                  onChange={(e) => setFeeAmount(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="0,00"
                  inputMode="decimal"
                />
              </label>
              <label className="sm:col-span-2 lg:col-span-3 flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Observações</span>
                <textarea
                  value={observation}
                  onChange={(e) => setObservation(e.target.value)}
                  rows={2}
                  className="resize-y rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
            </div>

            <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 px-4 py-3 text-sm text-indigo-950">
              <p>
                <span className="font-medium">{selected.size}</span> NF(s) · Bruto{" "}
                <span className="font-semibold tabular-nums">{formatBRL(grossTotal)}</span>
                {" · "}
                Líquido <span className="font-semibold tabular-nums">{formatBRL(receivedNum)}</span>
                {" · "}
                Deságio {discountPct !== "—" ? `${discountPct}%` : "—"}
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar NF, cliente ou projeto…"
                className="min-w-[240px] flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
              <button
                type="button"
                onClick={() => void loadEligible()}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
              >
                Buscar
              </button>
            </div>

            <div className="max-h-[320px] overflow-x-auto overflow-y-auto rounded-lg border border-slate-200">
              <table className="min-w-[720px] w-full divide-y divide-slate-200 text-sm">
                <thead className="sticky top-0 bg-slate-50 text-left text-xs font-semibold uppercase text-slate-600">
                  <tr>
                    <th className="w-10 px-2 py-2" />
                    <th className="px-2 py-2">Projeto</th>
                    <th className="px-2 py-2">Cliente</th>
                    <th className="px-2 py-2">Nº NF</th>
                    <th className="px-2 py-2">Emissão</th>
                    <th className="px-2 py-2">Vencimento</th>
                    <th className="px-2 py-2 text-right">Bruto</th>
                    <th className="px-2 py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {invoices.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-3 py-8 text-center text-slate-500">
                        Nenhuma NF elegível encontrada.
                      </td>
                    </tr>
                  ) : (
                    invoices.map((inv) => (
                      <tr key={inv.id} className="hover:bg-slate-50/80">
                        <td className="px-2 py-1.5">
                          <input
                            type="checkbox"
                            checked={selected.has(inv.id)}
                            onChange={() => toggle(inv.id)}
                          />
                        </td>
                        <td className="px-2 py-1.5">{inv.project_name ?? "—"}</td>
                        <td className="px-2 py-1.5">{inv.client_name ?? "—"}</td>
                        <td className="px-2 py-1.5 font-medium">{inv.number}</td>
                        <td className="px-2 py-1.5 whitespace-nowrap">{formatDateBr(inv.issue_date)}</td>
                        <td className="px-2 py-1.5 whitespace-nowrap">{formatDateBr(inv.due_date)}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{formatBRL(inv.gross_amount)}</td>
                        <td className="px-2 py-1.5 text-xs">{inv.status}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex justify-end gap-2 border-t border-slate-200 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={saving || selected.size < 2}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {saving ? "Salvando…" : "Criar borderô"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
