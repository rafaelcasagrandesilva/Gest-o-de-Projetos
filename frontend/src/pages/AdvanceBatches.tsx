import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { isAxiosError } from "axios";
import { AdvanceBatchModal } from "@/components/AdvanceBatchModal";
import { AdvanceRateCards } from "@/components/AdvanceRateCards";
import { AdvanceSettlementsTab } from "@/components/AdvanceSettlementsTab";
import { Money } from "@/components/Money";
import { PeriodFilter, type PeriodMode } from "@/components/PeriodFilter";
import { SortableTh } from "@/components/table";
import { useTableSort } from "@/hooks/useTableSort";
import { ADVANCE_BATCH_SORT_COLUMNS, defaultAdvanceBatchSort } from "@/tableSort/advanceBatches";
import {
  cancelAdvanceBatch,
  deleteAdvanceBatchHard,
  fetchAdvanceBatches,
  type AdvanceBatch,
  type AdvanceBatchStatus,
} from "@/services/receivableAdvanceBatches";
import { formatApiError } from "@/utils/apiError";
import { usePermission } from "@/hooks/usePermission";

function formatDateBr(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

const STATUS_META: Record<AdvanceBatchStatus, { label: string; cls: string }> = {
  DRAFT: { label: "Rascunho", cls: "bg-amber-100 text-amber-900 ring-amber-200" },
  OPEN: { label: "Em aberto", cls: "bg-emerald-100 text-emerald-900 ring-emerald-200" },
  SETTLED: { label: "Liquidada", cls: "bg-indigo-100 text-indigo-900 ring-indigo-200" },
  CANCELLED: { label: "Cancelada", cls: "bg-slate-200 text-slate-700 ring-slate-300" },
};

export function AdvanceBatches() {
  const canEditInvoices = usePermission("invoices.update");
  const navigate = useNavigate();
  const [rows, setRows] = useState<AdvanceBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [viewBatchId, setViewBatchId] = useState<string | null>(null);
  const [tab, setTab] = useState<"operacoes" | "liquidacao">("operacoes");
  // Ações da aba Liquidação, elevadas ao pai para ficarem na mesma linha das abas.
  const [mgmtOpen, setMgmtOpen] = useState(false);
  const [ledgerOpen, setLedgerOpen] = useState(false);
  const [massOpen, setMassOpen] = useState(false);
  const [eventsOpen, setEventsOpen] = useState(false);
  const [settlementsRefresh, setSettlementsRefresh] = useState(0);
  // Período por Data da Operação (receive_date). Default "ALL" preserva a lista completa.
  const [periodMode, setPeriodMode] = useState<PeriodMode>("ALL");
  const [period, setPeriod] = useState("");
  // Instituição (""= todas). Filtro client-side, como o de período.
  const [institution, setInstitution] = useState("");

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

  // Opções do filtro de instituição: derivadas dos próprios dados (nenhuma lista fixa —
  // instituições novas aparecem sozinhas). Vem de `rows`, não do recorte, para a lista
  // não mudar de tamanho a cada troca de mês.
  const institutionOptions = useMemo(
    () =>
      [...new Set(rows.map((b) => b.institution?.trim()).filter((n): n is string => !!n))].sort((a, b) =>
        a.localeCompare(b, "pt-BR"),
      ),
    [rows],
  );

  // Filtros por período (mês, sobre a Data da Operação) e por instituição. "Todos" mantém tudo.
  const filteredRows = useMemo(() => {
    let out = rows;
    if (periodMode === "MONTH" && period) {
      out = out.filter((b) => (b.receive_date || "").slice(0, 7) === period);
    }
    if (institution) {
      out = out.filter((b) => (b.institution?.trim() || "") === institution);
    }
    return out;
  }, [rows, periodMode, period, institution]);

  const { sortedRows: sorted, headerSort } = useTableSort(filteredRows, ADVANCE_BATCH_SORT_COLUMNS, {
    defaultCompare: defaultAdvanceBatchSort,
  });

  const operationLabel = (b: AdvanceBatch) => {
    // Identificador operacional oficial = número interno do SGC.
    if (b.sgc_number != null) return String(b.sgc_number);
    if (b.batch_number) return b.batch_number;
    return `ANTECIPACAO-${String(b.id).slice(0, 8)}`;
  };

  async function handleCancel(b: AdvanceBatch) {
    if (!canEditInvoices) return;
    if (b.status !== "OPEN" && b.status !== "DRAFT") return;
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
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Antecipações</h1>
        <p className="mt-1 text-sm text-slate-600">Operações de antecipação e liquidação das NFs perante a instituição.</p>
      </div>

      {/* Abas + ações na MESMA linha (aproveita o espaço do topo). */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
          {(["operacoes", "liquidacao"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                tab === t ? "bg-indigo-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {t === "operacoes" ? "Operações" : "Liquidação de NFs"}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {tab === "liquidacao" ? (
            <>
              <button
                type="button"
                onClick={() => setMgmtOpen((v) => !v)}
                className={`rounded-lg border px-3 py-1.5 text-sm font-medium ${
                  mgmtOpen ? "border-indigo-300 bg-indigo-50 text-indigo-700" : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50"
                }`}
              >
                Visão gerencial
              </button>
              <button
                type="button"
                onClick={() => setSettlementsRefresh((n) => n + 1)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
              >
                Atualizar
              </button>
              <button
                type="button"
                disabled={!canEditInvoices}
                onClick={() => setMassOpen(true)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Liquidação em massa
              </button>
              <button
                type="button"
                onClick={() => setEventsOpen(true)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
              >
                Extrato de Liquidações
              </button>
              <button
                type="button"
                onClick={() => setLedgerOpen(true)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
              >
                Extrato do Repasse
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => void load()}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
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
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Nova antecipação
              </button>
            </>
          )}
        </div>
      </div>

      {tab === "liquidacao" ? (
        <AdvanceSettlementsTab
          canEdit={canEditInvoices}
          showMgmt={mgmtOpen}
          ledgerOpen={ledgerOpen}
          onCloseLedger={() => setLedgerOpen(false)}
          massOpen={massOpen}
          onCloseMass={() => setMassOpen(false)}
          eventsOpen={eventsOpen}
          onCloseEvents={() => setEventsOpen(false)}
          refreshSignal={settlementsRefresh}
        />
      ) : (
        <>
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap gap-3">
          <PeriodFilter
            label="Período (Operação)"
            mode={periodMode}
            value={period}
            onModeChange={setPeriodMode}
            onChange={setPeriod}
          />

          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Instituição</span>
            <select
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Todas</option>
              {institutionOptions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>

          {/* Indicadores na MESMA barra dos filtros, ocupando o espaço livre à direita:
              mostrar a taxa efetiva não pode custar altura da tabela de operações. */}
          <AdvanceRateCards batches={filteredRows} />
        </div>
      </section>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-[1200px] w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <SortableTh label="Operação SGC" column="sgc" {...headerSort} />
              <SortableTh label="Nº instituição" column="operation_code" {...headerSort} />
              <SortableTh label="Instituição" column="institution" {...headerSort} />
              <SortableTh label="Qtd NFs" column="invoice_count" align="right" {...headerSort} />
              <SortableTh label="Repasse Retido" column="repasse" align="right" {...headerSort} />
              <SortableTh label="Líquido" column="received" align="right" {...headerSort} />
              <SortableTh label="Deságio" column="discount" align="right" {...headerSort} />
              <SortableTh label="Tarifas" column="fee" align="right" {...headerSort} />
              <SortableTh label="Recebimento" column="receive_date" {...headerSort} />
              <SortableTh label="Status" column="status" {...headerSort} />
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
                  <td className="whitespace-nowrap px-2 py-1.5 font-semibold text-slate-900">{operationLabel(b)}</td>
                  <td className="max-w-[160px] truncate px-2 py-1.5 text-slate-600" title={b.operation_code ?? undefined}>
                    {b.operation_code?.trim() ? b.operation_code : "—"}
                  </td>
                  <td className="max-w-[220px] truncate px-2 py-1.5 text-slate-700" title={b.institution}>
                    {b.institution}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{b.invoice_count}</td>
                  <td className="px-2 py-1.5 text-indigo-700" title="Repasse retido (7% do antecipado)">
                    <Money value={b.repasse_enabled ? b.repasse_amount : null} />
                  </td>
                  <td className="px-2 py-1.5"><Money value={b.received_amount} /></td>
                  <td className="px-2 py-1.5"><Money value={b.discount_amount} /></td>
                  <td className="px-2 py-1.5"><Money value={b.fee_amount} /></td>
                  <td className="whitespace-nowrap px-2 py-1.5">{formatDateBr(b.receive_date)}</td>
                  <td className="px-2 py-1.5">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${STATUS_META[b.status].cls}`}
                    >
                      {STATUS_META[b.status].label}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        setViewBatchId(b.id);
                        setModalOpen(true);
                      }}
                      className="ml-1 rounded px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
                    >
                      Ver detalhes
                    </button>
                    <button
                      type="button"
                      disabled={!canEditInvoices || (b.status !== "OPEN" && b.status !== "DRAFT") || busyId === b.id}
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
        onOpenInvoice={() => {
          setModalOpen(false);
          setViewBatchId(null);
          navigate("/finance/invoices");
        }}
        onOpenOperation={(batchId) => setViewBatchId(batchId)}
      />
        </>
      )}
    </div>
  );
}

