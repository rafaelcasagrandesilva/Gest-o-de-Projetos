import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  createMassSettlement,
  createSettlement,
  fetchManagementSummary,
  fetchObligations,
  fetchSettlementEventDetail,
  fetchSettlementEvents,
  fetchSettlementKpis,
  fetchTimeline,
  reverseMovement,
  FUNDING_SOURCE_LABELS,
  FUNDING_SOURCE_OPTIONS,
  SITUACAO_META,
  type FundingSource,
  type ManagementSummary,
  type Obligation,
  type SettlementEvent,
  type SettlementEventDetail,
  type SettlementKpis,
  type SettlementMovementInput,
  type SituacaoLiquidacao,
  type Timeline,
} from "@/services/advanceSettlements";
import { Money } from "@/components/Money";
import { PeriodFilter, type PeriodMode } from "@/components/PeriodFilter";
import { RepasseLedgerModal } from "@/components/RepasseLedgerModal";
import { SortableTh } from "@/components/table";
import { useTableSort } from "@/hooks/useTableSort";
import { OBLIGATION_SORT_COLUMNS, defaultObligationSort } from "@/tableSort/advanceSettlements";
import { formatApiError } from "@/utils/apiError";
import { eventCode, nfSummary } from "@/utils/settlementPresenter";
import {
  formatCurrency,
  formatCurrencyOrDash,
  normalizeCurrencyForApi,
  sanitizeCurrencyTyping,
} from "@/utils/currency";

function formatDateBr(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return String(iso);
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function Kpi({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-0.5 text-base font-semibold tabular-nums text-slate-900 ${accent ?? ""}`}>{value}</p>
    </div>
  );
}

function ManagementPanel({ m }: { m: ManagementSummary }) {
  const dist = m.distribuicao_origens;
  const barColors = ["bg-indigo-500", "bg-emerald-500", "bg-amber-500", "bg-sky-500", "bg-slate-400"];
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <Kpi label="Ainda antecipado (a devolver)" value={formatCurrency(m.valor_ainda_antecipado)} />
        <Kpi label="A vencer (30 dias)" value={formatCurrency(m.valor_a_vencer_30d)} accent="text-amber-700" />
        <Kpi
          label="Tempo médio de liquidação"
          value={m.tempo_medio_liquidacao_dias != null ? `${m.tempo_medio_liquidacao_dias} dias` : "—"}
        />
        <Kpi label="Liquidado com Repasse" value={formatCurrency(m.liquidado_repasse)} accent="text-indigo-700" />
        <Kpi label="Liquidado outras origens" value={formatCurrency(m.liquidado_outras_origens)} accent="text-emerald-700" />
      </div>

      <div className="mt-4">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
          Distribuição das origens de liquidação
        </p>
        {dist.length === 0 ? (
          <p className="text-sm text-slate-500">Nenhuma liquidação registrada ainda.</p>
        ) : (
          <div className="space-y-2">
            <div className="flex h-3 w-full overflow-hidden rounded-full bg-slate-100">
              {dist.map((d, i) => (
                <div
                  key={d.funding_source}
                  className={barColors[i % barColors.length]}
                  style={{ width: `${d.pct}%` }}
                  title={`${d.label}: ${d.pct}%`}
                />
              ))}
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
              {dist.map((d, i) => (
                <span key={d.funding_source} className="inline-flex items-center gap-1">
                  <span className={`inline-block h-2 w-2 rounded-full ${barColors[i % barColors.length]}`} />
                  {d.label} · {formatCurrency(d.total)} ({d.pct}%)
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function SituacaoBadge({ s }: { s: SituacaoLiquidacao }) {
  const meta = SITUACAO_META[s];
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${meta.cls}`}>
      {meta.label}
    </span>
  );
}

export function AdvanceSettlementsTab({
  canEdit,
  showMgmt,
  ledgerOpen,
  onCloseLedger,
  massOpen,
  onCloseMass,
  eventsOpen,
  onCloseEvents,
  refreshSignal,
}: {
  canEdit: boolean;
  showMgmt: boolean;
  ledgerOpen: boolean;
  onCloseLedger: () => void;
  massOpen: boolean;
  onCloseMass: () => void;
  eventsOpen: boolean;
  onCloseEvents: () => void;
  refreshSignal: number;
}) {
  const [obligations, setObligations] = useState<Obligation[]>([]);
  const [kpis, setKpis] = useState<SettlementKpis | null>(null);
  const [mgmt, setMgmt] = useState<ManagementSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filtros: aplicados APENAS sobre o conjunto já carregado (dados já vêm prontos do backend).
  const [fSituacao, setFSituacao] = useState<"ALL" | SituacaoLiquidacao>("ALL");
  const [fInstitution, setFInstitution] = useState<string>("ALL");
  const [fClient, setFClient] = useState("");
  const [fNf, setFNf] = useState("");
  const [fSgc, setFSgc] = useState("");
  // Período por Vencimento da obrigação. Default "ALL" preserva a lista completa (comportamento atual).
  const [periodMode, setPeriodMode] = useState<PeriodMode>("ALL");
  const [period, setPeriod] = useState("");

  const [settleTarget, setSettleTarget] = useState<Obligation | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [obs, k, m] = await Promise.all([
        fetchObligations(),
        fetchSettlementKpis(),
        fetchManagementSummary(),
      ]);
      setObligations(obs);
      setKpis(k);
      setMgmt(m);
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar liquidações.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Carrega na montagem e sempre que o pai pedir "Atualizar" (refreshSignal muda).
  useEffect(() => {
    void load();
  }, [load, refreshSignal]);

  const institutions = useMemo(() => {
    const map = new Map<string, string>();
    for (const o of obligations) {
      if (o.institution_id && o.institution) map.set(o.institution_id, o.institution);
    }
    return Array.from(map, ([id, name]) => ({ id, name }));
  }, [obligations]);

  const filtered = useMemo(() => {
    return obligations.filter((o) => {
      if (fSituacao !== "ALL" && o.situacao !== fSituacao) return false;
      if (fInstitution !== "ALL" && o.institution_id !== fInstitution) return false;
      if (fClient.trim() && !(o.client_name || "").toLowerCase().includes(fClient.trim().toLowerCase())) return false;
      if (fNf.trim() && !(o.invoice_number || "").toLowerCase().includes(fNf.trim().toLowerCase())) return false;
      if (fSgc.trim() && !String(o.sgc_number).includes(fSgc.trim())) return false;
      // Período por Vencimento (mês). Obrigações sem vencimento saem no modo mês; entram no "Todos".
      if (periodMode === "MONTH" && period) {
        if ((o.vencimento || "").slice(0, 7) !== period) return false;
      }
      return true;
    });
  }, [obligations, fSituacao, fInstitution, fClient, fNf, fSgc, periodMode, period]);

  // Ordenação por coluna (mesmo padrão do CAP): aplicada sobre o conjunto já filtrado.
  const { sortedRows, headerSort } = useTableSort(filtered, OBLIGATION_SORT_COLUMNS, {
    defaultCompare: defaultObligationSort,
  });

  // Reflete a obrigação atualizada devolvida pelo backend (após liquidar/estornar) e atualiza KPIs.
  const applyUpdated = useCallback(async (updated: Obligation) => {
    setObligations((prev) => prev.map((o) => (o.batch_item_id === updated.batch_item_id ? updated : o)));
    setSettleTarget((prev) => (prev && prev.batch_item_id === updated.batch_item_id ? updated : prev));
    try {
      const [k, m] = await Promise.all([fetchSettlementKpis(), fetchManagementSummary()]);
      setKpis(k);
      setMgmt(m);
    } catch {
      /* KPIs não críticos para a ação; ignora */
    }
  }, []);

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      {/* Cards: consomem EXCLUSIVAMENTE os KPIs do backend (sem somatório em React). */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <Kpi label="NFs pendentes" value={kpis ? String(kpis.nfs_pendentes) : "—"} />
        <Kpi label="NFs vencidas" value={kpis ? String(kpis.nfs_vencidas) : "—"} accent="text-red-700" />
        <Kpi label="Valor total vencido" value={kpis ? formatCurrency(kpis.valor_total_vencido) : "—"} accent="text-red-700" />
        <Kpi label="Total liquidado" value={kpis ? formatCurrency(kpis.total_liquidado) : "—"} accent="text-emerald-700" />
        <Kpi label="Saldo do Repasse" value={kpis ? formatCurrency(kpis.saldo_repasse) : "—"} accent="text-indigo-700" />
      </div>

      {/* Visão gerencial: indicadores para decisão — todos computados no backend. */}
      {showMgmt && mgmt && <ManagementPanel m={mgmt} />}

      {/* Filtros: só reordenam/reduzem o conjunto já carregado. */}
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label className="text-xs font-medium text-slate-600">
            Situação
            <select
              value={fSituacao}
              onChange={(e) => setFSituacao(e.target.value as "ALL" | SituacaoLiquidacao)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            >
              <option value="ALL">Todas</option>
              <option value="EM_ABERTO">Em aberto</option>
              <option value="PARCIALMENTE_LIQUIDADA">Parcialmente liquidada</option>
              <option value="VENCIDA">Vencida</option>
              <option value="LIQUIDADA">Liquidada</option>
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Instituição
            <select
              value={fInstitution}
              onChange={(e) => setFInstitution(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            >
              <option value="ALL">Todas</option>
              {institutions.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Cliente
            <input
              value={fClient}
              onChange={(e) => setFClient(e.target.value)}
              placeholder="Nome do cliente"
              className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Nº NF
            <input
              value={fNf}
              onChange={(e) => setFNf(e.target.value)}
              placeholder="Número da NF"
              className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Borderô (SGC)
            <input
              value={fSgc}
              onChange={(e) => setFSgc(e.target.value)}
              placeholder="Nº SGC"
              className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>
          <PeriodFilter
            label="Período (Vencimento)"
            mode={periodMode}
            value={period}
            onModeChange={setPeriodMode}
            onChange={setPeriod}
          />
        </div>
      </section>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-[1100px] w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <SortableTh label="Situação" column="situacao" {...headerSort} />
              <SortableTh label="Nº NF" column="invoice_number" {...headerSort} />
              <SortableTh label="Cliente" column="client" {...headerSort} />
              <SortableTh label="Borderô" column="sgc" align="right" {...headerSort} />
              <SortableTh label="Instituição" column="institution" {...headerSort} />
              <SortableTh label="Valor" column="valor" align="right" {...headerSort} />
              <SortableTh label="Liquidado" column="liquidado" align="right" {...headerSort} />
              <SortableTh label="Residual" column="residual" align="right" {...headerSort} />
              <SortableTh label="Origens" column="origens" {...headerSort} />
              <SortableTh label="Vencimento" column="vencimento" {...headerSort} />
              <SortableTh label="Atraso" column="atraso" align="right" {...headerSort} />
              <th className="px-2 py-2 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr>
                <td colSpan={12} className="px-3 py-10 text-center text-slate-500">
                  Carregando…
                </td>
              </tr>
            ) : sortedRows.length === 0 ? (
              <tr>
                <td colSpan={12} className="px-3 py-8 text-center text-slate-500">
                  Nenhuma NF antecipada com obrigação de liquidação.
                </td>
              </tr>
            ) : (
              sortedRows.map((o) => (
                <tr key={o.batch_item_id} className="hover:bg-slate-50/80">
                  <td className="px-2 py-1.5">
                    <SituacaoBadge s={o.situacao} />
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 font-medium text-slate-900">{o.invoice_number || "—"}</td>
                  <td className="max-w-[200px] truncate px-2 py-1.5 text-slate-700" title={o.client_name || undefined}>
                    {o.client_name || "—"}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-slate-700">{o.sgc_number}</td>
                  <td className="max-w-[180px] truncate px-2 py-1.5 text-slate-700" title={o.institution || undefined}>
                    {o.institution || "—"}
                  </td>
                  <td className="px-2 py-1.5"><Money value={o.valor_total} /></td>
                  <td className="px-2 py-1.5 text-emerald-700"><Money value={o.valor_liquidado} /></td>
                  <td className="px-2 py-1.5 font-medium"><Money value={o.valor_residual} /></td>
                  <td className="max-w-[160px] truncate px-2 py-1.5 text-slate-600" title={o.origens_resumo || undefined}>
                    {o.origens_resumo || "—"}
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5">{formatDateBr(o.vencimento)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {o.dias_em_atraso > 0 ? <span className="text-red-700">{o.dias_em_atraso}d</span> : "—"}
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-right">
                    <button
                      type="button"
                      onClick={() => setSettleTarget(o)}
                      className="rounded px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
                    >
                      {o.situacao === "LIQUIDADA" || !canEdit ? "Detalhes" : "Liquidar"}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {settleTarget && (
        <SettlementModal
          obligation={settleTarget}
          canEdit={canEdit}
          onClose={() => setSettleTarget(null)}
          onChanged={applyUpdated}
        />
      )}
      {ledgerOpen && <RepasseLedgerModal institutions={institutions} canEdit={canEdit} onClose={onCloseLedger} />}
      {massOpen && (
        <MassSettlementModal
          obligations={obligations}
          institutions={institutions}
          onClose={onCloseMass}
          onDone={() => {
            onCloseMass();
            void load();
          }}
        />
      )}
      {eventsOpen && <SettlementEventsModal institutions={institutions} onClose={onCloseEvents} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modal de Liquidação — múltiplas origens; conferência VISUAL ao vivo; validação no backend.
// ---------------------------------------------------------------------------

interface MovRow {
  funding_source: FundingSource;
  amount: string; // texto controlado; convertido só no submit
  settled_at: string;
  observation: string;
}

function SettlementModal({
  obligation,
  canEdit,
  onClose,
  onChanged,
}: {
  obligation: Obligation;
  canEdit: boolean;
  onClose: () => void;
  onChanged: (o: Obligation) => Promise<void> | void;
}) {
  const isSettled = obligation.situacao === "LIQUIDADA";
  const editable = canEdit && !isSettled;
  const [rows, setRows] = useState<MovRow[]>([
    { funding_source: "SALDO_REPASSE", amount: "", settled_at: todayIso(), observation: "" },
  ]);
  const [saving, setSaving] = useState(false);
  const [busyReverseId, setBusyReverseId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);

  // Timeline (append-only): recarrega quando as movimentações da obrigação mudam.
  useEffect(() => {
    let alive = true;
    fetchTimeline(obligation.batch_item_id)
      .then((t) => alive && setTimeline(t))
      .catch(() => alive && setTimeline(null));
    return () => {
      alive = false;
    };
  }, [obligation.batch_item_id, obligation.movimentacoes.length]);

  // Conferência visual (apenas leitura de tela — NÃO é a validação oficial).
  const sumNew = rows.reduce((acc, r) => acc + normalizeCurrencyForApi(r.amount), 0);
  const repasseNew = rows
    .filter((r) => r.funding_source === "SALDO_REPASSE")
    .reduce((acc, r) => acc + normalizeCurrencyForApi(r.amount), 0);
  const novoLiquidado = obligation.valor_liquidado + sumNew;
  const residualApos = obligation.valor_total - novoLiquidado;
  const excede = residualApos < -0.005;

  function setRow(idx: number, patch: Partial<MovRow>) {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }
  function addRow() {
    setRows((prev) => [...prev, { funding_source: "CAIXA_EMPRESA", amount: "", settled_at: todayIso(), observation: "" }]);
  }
  function removeRow(idx: number) {
    setRows((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== idx) : prev));
  }
  function preencherResidual(idx: number) {
    setRow(idx, { amount: String(Math.max(0, Number(obligation.valor_residual.toFixed(2)))) });
  }

  async function submit() {
    setErr(null);
    const movements: SettlementMovementInput[] = rows
      .map((r) => ({
        funding_source: r.funding_source,
        amount: normalizeCurrencyForApi(r.amount),
        settled_at: r.settled_at || todayIso(),
        observation: r.observation.trim() || null,
      }))
      .filter((m) => m.amount > 0);
    if (movements.length === 0) {
      setErr("Informe ao menos uma movimentação com valor.");
      return;
    }
    setSaving(true);
    try {
      const updated = await createSettlement(obligation.batch_item_id, movements);
      await onChanged(updated);
      setRows([{ funding_source: "SALDO_REPASSE", amount: "", settled_at: todayIso(), observation: "" }]);
    } catch (e) {
      // A validação oficial é do backend — exibimos a mensagem retornada.
      setErr(isAxiosError(e) ? formatApiError(e) : "Não foi possível liquidar.");
    } finally {
      setSaving(false);
    }
  }

  async function estornar(movementId: string) {
    if (!window.confirm("Estornar esta movimentação? O histórico é preservado e o residual reabre.")) return;
    setBusyReverseId(movementId);
    setErr(null);
    try {
      const updated = await reverseMovement(movementId);
      await onChanged(updated);
    } catch (e) {
      setErr(isAxiosError(e) ? formatApiError(e) : "Não foi possível estornar.");
    } finally {
      setBusyReverseId(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-2 sm:p-4" onClick={onClose}>
      <div
        className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-slate-200 p-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              Liquidação — NF {obligation.invoice_number || "—"}
            </h2>
            <p className="mt-0.5 text-sm text-slate-600">
              {obligation.client_name || "—"} · Borderô SGC {obligation.sgc_number} · {obligation.institution || "—"}
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
            ✕
          </button>
        </div>

        {/* Resumo — todos os valores vêm prontos do backend. */}
        <div className="grid grid-cols-2 gap-3 border-b border-slate-200 p-4 sm:grid-cols-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">Valor da obrigação</p>
            <p className="mt-1 font-semibold tabular-nums">{formatCurrencyOrDash(obligation.valor_total)}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">Liquidado</p>
            <p className="mt-1 font-semibold tabular-nums text-emerald-700">{formatCurrencyOrDash(obligation.valor_liquidado)}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">Residual</p>
            <p className="mt-1 font-semibold tabular-nums">{formatCurrencyOrDash(obligation.valor_residual)}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">Situação</p>
            <p className="mt-1">
              <SituacaoBadge s={obligation.situacao} />
            </p>
          </div>
        </div>

        {/* Histórico (timeline append-only) — vem pronto do backend. */}
        {timeline && timeline.events.length > 0 && (
          <div className="border-b border-slate-200 p-4">
            <p className="mb-3 text-sm font-semibold text-slate-800">Histórico da NF</p>
            <ol className="space-y-3">
              {timeline.events.map((ev, i) => {
                const color =
                  ev.tipo === "ANTECIPADA"
                    ? "bg-slate-400"
                    : ev.tipo === "VENCEU"
                      ? "bg-red-500"
                      : ev.estornada
                        ? "bg-slate-300"
                        : ev.label === "Liquidada"
                          ? "bg-emerald-500"
                          : "bg-amber-500";
                return (
                  <li key={i} className="flex items-start gap-3">
                    <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${color}`} />
                    <div className="flex-1">
                      <p className={`text-sm ${ev.estornada ? "text-slate-400 line-through" : "text-slate-800"}`}>
                        {ev.label}
                        {ev.evento_number != null ? ` · Liquidação ${eventCode(ev.evento_number)}` : ""}
                        {ev.origem ? ` · ${ev.origem}` : ""}
                        {ev.amount != null ? ` · ${formatCurrencyOrDash(ev.amount)}` : ""}
                      </p>
                      <p className="text-xs text-slate-500">{formatDateBr(ev.date)}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        )}

        {/* Movimentações já registradas. */}
        <div className="border-b border-slate-200 p-4">
          <p className="mb-2 text-sm font-semibold text-slate-800">Movimentações</p>
          {obligation.movimentacoes.length === 0 ? (
            <p className="text-sm text-slate-500">Nenhuma movimentação ainda.</p>
          ) : (
            <div className="space-y-1">
              {obligation.movimentacoes.map((m) => (
                <div
                  key={m.id}
                  className={`flex items-center justify-between rounded-lg border px-3 py-1.5 text-sm ${
                    m.reversed_at ? "border-slate-200 bg-slate-50 text-slate-400 line-through" : "border-slate-200"
                  }`}
                >
                  <span className="flex-1">{FUNDING_SOURCE_LABELS[m.funding_source]}</span>
                  <span className="w-28 text-right tabular-nums">{formatCurrencyOrDash(m.amount)}</span>
                  <span className="w-24 text-right text-slate-500">{formatDateBr(m.settled_at)}</span>
                  <span className="ml-2 w-16 text-right">
                    {m.reversed_at ? (
                      <span className="text-[10px] uppercase text-slate-400">estornada</span>
                    ) : canEdit ? (
                      <button
                        type="button"
                        disabled={busyReverseId === m.id}
                        onClick={() => void estornar(m.id)}
                        className="rounded px-1.5 py-0.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                      >
                        {busyReverseId === m.id ? "…" : "Estornar"}
                      </button>
                    ) : null}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Nova liquidação (multi-origem). */}
        {editable && (
          <div className="p-4">
            <p className="mb-2 text-sm font-semibold text-slate-800">Adicionar liquidação</p>
            <div className="space-y-2">
              {rows.map((r, idx) => {
                const needsObs = r.funding_source === "OUTRA";
                return (
                  <div key={idx} className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 p-2">
                    <label className="text-xs text-slate-600">
                      Origem
                      <select
                        value={r.funding_source}
                        onChange={(e) => setRow(idx, { funding_source: e.target.value as FundingSource })}
                        className="mt-1 block w-44 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                      >
                        {FUNDING_SOURCE_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="text-xs text-slate-600">
                      Valor
                      <input
                        value={r.amount}
                        onChange={(e) => setRow(idx, { amount: sanitizeCurrencyTyping(e.target.value) })}
                        placeholder="0,00"
                        className="mt-1 block w-32 rounded-lg border border-slate-300 px-2 py-1.5 text-right text-sm tabular-nums"
                      />
                    </label>
                    <label className="text-xs text-slate-600">
                      Data
                      <input
                        type="date"
                        value={r.settled_at}
                        onChange={(e) => setRow(idx, { settled_at: e.target.value })}
                        className="mt-1 block rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                      />
                    </label>
                    <label className="min-w-[140px] flex-1 text-xs text-slate-600">
                      Observação {needsObs && <span className="text-red-600">*</span>}
                      <input
                        value={r.observation}
                        onChange={(e) => setRow(idx, { observation: e.target.value })}
                        placeholder={needsObs ? "Obrigatória para 'Outra'" : "Opcional"}
                        className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                      />
                    </label>
                    <div className="flex gap-1 pb-1">
                      <button
                        type="button"
                        onClick={() => preencherResidual(idx)}
                        title="Preencher com o residual"
                        className="rounded border border-slate-300 px-2 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                      >
                        Residual
                      </button>
                      <button
                        type="button"
                        onClick={() => removeRow(idx)}
                        disabled={rows.length === 1}
                        className="rounded border border-slate-300 px-2 py-1.5 text-xs text-slate-500 hover:bg-slate-50 disabled:opacity-40"
                      >
                        Remover
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            <button
              type="button"
              onClick={addRow}
              className="mt-2 rounded-lg border border-dashed border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              + Adicionar origem
            </button>

            {/* Conferência visual (não é a validação oficial). */}
            <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-600">Somando estas movimentações</span>
                <span className="tabular-nums">{formatCurrency(sumNew)}</span>
              </div>
              {repasseNew > 0 && (
                <div className="flex justify-between text-slate-500">
                  <span>· usando Saldo do Repasse</span>
                  <span className="tabular-nums">{formatCurrency(repasseNew)}</span>
                </div>
              )}
              <div className="mt-1 flex justify-between border-t border-slate-200 pt-1">
                <span className="text-slate-600">Residual após liquidar</span>
                <span className={`tabular-nums font-medium ${excede ? "text-red-700" : ""}`}>
                  {formatCurrency(residualApos)}
                </span>
              </div>
              {excede && (
                <p className="mt-1 text-xs text-red-700">
                  A conferência indica valor acima do residual — o backend recusará se exceder.
                </p>
              )}
            </div>

            {err && <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{err}</div>}

            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={onClose} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                Fechar
              </button>
              <button
                type="button"
                onClick={() => void submit()}
                disabled={saving}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700 disabled:opacity-50"
              >
                {saving ? "Salvando…" : "Liquidar"}
              </button>
            </div>
          </div>
        )}

        {!editable && (
          <div className="flex items-center justify-between p-4">
            <p className="text-sm text-slate-500">
              {isSettled ? "Obrigação já liquidada." : "Sem permissão para liquidar."}
            </p>
            {err && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{err}</div>}
            <button type="button" onClick={onClose} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
              Fechar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Liquidação em Massa — UX de seleção estilo Borderô; cria UM Evento (pagamento).
// ---------------------------------------------------------------------------

function MassSettlementModal({
  obligations,
  institutions,
  onClose,
  onDone,
}: {
  obligations: Obligation[];
  institutions: { id: string; name: string }[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [institutionId, setInstitutionId] = useState(institutions[0]?.id ?? "");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [fundingSource, setFundingSource] = useState<FundingSource>("SALDO_REPASSE");
  const [paymentDate, setPaymentDate] = useState(todayIso());
  const [observation, setObservation] = useState("");
  const [mode, setMode] = useState<"INTEGRAL" | "INDIVIDUAL">("INTEGRAL");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Só NFs pendentes (residual > 0) da instituição escolhida — um evento = uma instituição.
  const pending = useMemo(
    () => obligations.filter((o) => o.institution_id === institutionId && o.valor_residual > 0.005),
    [obligations, institutionId],
  );
  const { sortedRows, headerSort } = useTableSort(pending, OBLIGATION_SORT_COLUMNS, {
    defaultCompare: defaultObligationSort,
  });

  useEffect(() => {
    setSelected(new Set());
  }, [institutionId]);

  const residualStr = (o: Obligation) => String(o.valor_residual.toFixed(2));

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else {
        next.add(id);
        const o = pending.find((x) => x.batch_item_id === id);
        if (o) setAmounts((a) => (a[id] != null ? a : { ...a, [id]: residualStr(o) }));
      }
      return next;
    });
  }
  function selectMany(list: Obligation[]) {
    setSelected(new Set(list.map((o) => o.batch_item_id)));
    setAmounts((a) => {
      const next = { ...a };
      for (const o of list) if (next[o.batch_item_id] == null) next[o.batch_item_id] = residualStr(o);
      return next;
    });
  }

  const selectedList = pending.filter((o) => selected.has(o.batch_item_id));
  const rowAmount = (o: Obligation) =>
    mode === "INTEGRAL" ? o.valor_residual : normalizeCurrencyForApi(amounts[o.batch_item_id] ?? "");
  const total = selectedList.reduce((acc, o) => acc + rowAmount(o), 0);

  async function submit() {
    setErr(null);
    if (selectedList.length === 0) {
      setErr("Selecione ao menos uma NF.");
      return;
    }
    const lines = selectedList.map((o) => ({
      batch_item_id: o.batch_item_id,
      amount: mode === "INTEGRAL" ? Number(o.valor_residual.toFixed(2)) : rowAmount(o),
    }));
    if (lines.some((l) => l.amount <= 0)) {
      setErr("Cada NF selecionada precisa de um valor positivo.");
      return;
    }
    setSaving(true);
    try {
      await createMassSettlement({
        funding_source: fundingSource,
        payment_date: paymentDate || todayIso(),
        observation: observation.trim() || null,
        lines,
      });
      onDone();
    } catch (e) {
      setErr(isAxiosError(e) ? formatApiError(e) : "Não foi possível registrar a liquidação em massa.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-2 sm:p-4" onClick={onClose}>
      <div className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between border-b border-slate-200 p-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Liquidação em massa</h2>
            <p className="mt-0.5 text-sm text-slate-600">Um pagamento (evento) quita várias NFs da mesma instituição.</p>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">✕</button>
        </div>

        {/* Origem/instituição/data/modo */}
        <div className="grid grid-cols-1 gap-3 border-b border-slate-200 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-xs font-medium text-slate-600">
            Instituição
            <select
              value={institutionId}
              onChange={(e) => setInstitutionId(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            >
              {institutions.length === 0 && <option value="">—</option>}
              {institutions.map((i) => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Origem
            <select
              value={fundingSource}
              onChange={(e) => setFundingSource(e.target.value as FundingSource)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            >
              {FUNDING_SOURCE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Data do pagamento
            <input
              type="date"
              value={paymentDate}
              onChange={(e) => setPaymentDate(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Modo
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as "INTEGRAL" | "INDIVIDUAL")}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            >
              <option value="INTEGRAL">Integral (residual de todas)</option>
              <option value="INDIVIDUAL">Individual (valor por NF)</option>
            </select>
          </label>
        </div>

        {/* Atalhos de produtividade */}
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-2 text-xs">
          <span className="text-slate-500">{selectedList.length} de {pending.length} selecionadas</span>
          <button type="button" onClick={() => selectMany(pending)} className="rounded border border-slate-300 px-2 py-1 text-slate-700 hover:bg-slate-50">Selecionar todas</button>
          <button type="button" onClick={() => selectMany(pending.filter((o) => o.dias_em_atraso > 0))} className="rounded border border-slate-300 px-2 py-1 text-slate-700 hover:bg-slate-50">Selecionar vencidas</button>
          <button type="button" onClick={() => setSelected(new Set())} className="rounded border border-slate-300 px-2 py-1 text-slate-700 hover:bg-slate-50">Limpar seleção</button>
        </div>

        <div className="overflow-x-auto p-2">
          <table className="w-full min-w-[720px] divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-2 py-2 w-8"></th>
                <SortableTh label="Nº NF" column="invoice_number" {...headerSort} />
                <SortableTh label="Cliente" column="client" {...headerSort} />
                <SortableTh label="Vencimento" column="vencimento" {...headerSort} />
                <SortableTh label="Residual" column="residual" align="right" {...headerSort} />
                <th className="px-2 py-2 text-right">Valor a liquidar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {pending.length === 0 ? (
                <tr><td colSpan={6} className="px-3 py-8 text-center text-slate-500">Sem NFs pendentes nesta instituição.</td></tr>
              ) : (
                sortedRows.map((o) => {
                  const isSel = selected.has(o.batch_item_id);
                  return (
                    <tr key={o.batch_item_id} className={isSel ? "bg-indigo-50/40" : "hover:bg-slate-50/80"}>
                      <td className="px-2 py-1.5">
                        <input type="checkbox" checked={isSel} onChange={() => toggle(o.batch_item_id)} />
                      </td>
                      <td className="whitespace-nowrap px-2 py-1.5 font-medium text-slate-900">{o.invoice_number || "—"}</td>
                      <td className="max-w-[220px] truncate px-2 py-1.5 text-slate-700" title={o.client_name || undefined}>{o.client_name || "—"}</td>
                      <td className="whitespace-nowrap px-2 py-1.5">
                        {formatDateBr(o.vencimento)}
                        {o.dias_em_atraso > 0 && <span className="ml-1 text-[10px] text-red-700">{o.dias_em_atraso}d</span>}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{formatCurrencyOrDash(o.valor_residual)}</td>
                      <td className="px-2 py-1.5 text-right">
                        {mode === "INTEGRAL" ? (
                          <span className="tabular-nums text-slate-500">{formatCurrencyOrDash(o.valor_residual)}</span>
                        ) : (
                          <div className="flex items-center justify-end gap-1">
                            <input
                              value={amounts[o.batch_item_id] ?? ""}
                              onChange={(e) => setAmounts((a) => ({ ...a, [o.batch_item_id]: sanitizeCurrencyTyping(e.target.value) }))}
                              disabled={!isSel}
                              placeholder="0,00"
                              className="w-28 rounded-lg border border-slate-300 px-2 py-1 text-right text-sm tabular-nums disabled:bg-slate-50"
                            />
                            <button
                              type="button"
                              disabled={!isSel}
                              onClick={() => setAmounts((a) => ({ ...a, [o.batch_item_id]: residualStr(o) }))}
                              className="rounded border border-slate-300 px-1.5 py-1 text-[10px] text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                            >
                              Residual
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="border-t border-slate-200 p-4">
          <label className="block text-xs font-medium text-slate-600">
            Observação do evento
            <input
              value={observation}
              onChange={(e) => setObservation(e.target.value)}
              placeholder="Opcional (ex.: TED recebida da instituição)"
              className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>
          <div className="mt-3 flex items-center justify-between rounded-lg bg-slate-50 p-3 text-sm">
            <span className="text-slate-600">Total do evento ({selectedList.length} NFs)</span>
            <span className="tabular-nums font-semibold">{formatCurrency(total)}</span>
          </div>
          {err && <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{err}</div>}
          <div className="mt-4 flex justify-end gap-2">
            <button type="button" onClick={onClose} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">Cancelar</button>
            <button
              type="button"
              onClick={() => void submit()}
              disabled={saving || selectedList.length === 0}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "Liquidando…" : "Liquidar em massa"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Extrato de Liquidações — eventos de pagamento (semelhante ao Extrato do Repasse).
// ---------------------------------------------------------------------------

function SettlementEventsModal({
  institutions,
  onClose,
}: {
  institutions: { id: string; name: string }[];
  onClose: () => void;
}) {
  const [instId, setInstId] = useState<string>("");
  const [events, setEvents] = useState<SettlementEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [detail, setDetail] = useState<SettlementEventDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr(null);
    fetchSettlementEvents(instId || undefined)
      .then((rows) => alive && setEvents(rows))
      .catch((e) => alive && setErr(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar."))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [instId]);

  async function openDetail(id: string) {
    setDetailLoading(true);
    try {
      setDetail(await fetchSettlementEventDetail(id));
    } catch (e) {
      setErr(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar o evento.");
    } finally {
      setDetailLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-2 sm:p-4" onClick={onClose}>
      <div className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between border-b border-slate-200 p-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Extrato de Liquidações</h2>
            <p className="mt-0.5 text-sm text-slate-600">Eventos de pagamento (cada linha = um pagamento que quitou NFs).</p>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">✕</button>
        </div>

        <div className="border-b border-slate-200 p-4">
          <label className="text-xs font-medium text-slate-600">
            Instituição
            <select value={instId} onChange={(e) => setInstId(e.target.value)} className="mt-1 block w-56 rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
              <option value="">Todas</option>
              {institutions.map((i) => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </select>
          </label>
        </div>

        {err && <div className="m-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{err}</div>}

        <div className="overflow-x-auto p-2">
          <table className="w-full min-w-[820px] divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-2 py-2">Evento</th>
                <th className="px-2 py-2">Instituição</th>
                <th className="px-2 py-2">Data</th>
                <th className="px-2 py-2">Origem</th>
                <th className="px-2 py-2 text-right">Valor Total</th>
                <th className="px-2 py-2 text-right">Qtd NFs</th>
                <th className="px-2 py-2">Descrição</th>
                <th className="px-2 py-2">Usuário</th>
                <th className="px-2 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan={9} className="px-3 py-8 text-center text-slate-500">Carregando…</td></tr>
              ) : events.length === 0 ? (
                <tr><td colSpan={9} className="px-3 py-8 text-center text-slate-500">Nenhum evento de liquidação.</td></tr>
              ) : (
                events.map((ev) => (
                  <tr key={ev.id} className="hover:bg-slate-50/80">
                    <td className="whitespace-nowrap px-2 py-1.5 font-medium text-indigo-700">{ev.code}</td>
                    <td className="max-w-[160px] truncate px-2 py-1.5 text-slate-700" title={ev.institution || undefined}>{ev.institution || "—"}</td>
                    <td className="whitespace-nowrap px-2 py-1.5">{formatDateBr(ev.payment_date)}</td>
                    <td className="px-2 py-1.5 text-slate-600">{ev.funding_source_label || "Múltiplas origens"}</td>
                    <td className="px-2 py-1.5 text-right"><Money value={ev.total_amount} /></td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{ev.invoice_count}</td>
                    <td className="max-w-[220px] truncate px-2 py-1.5 text-slate-600" title={nfSummary(ev.nf_numbers)}>{nfSummary(ev.nf_numbers)}</td>
                    <td className="max-w-[140px] truncate px-2 py-1.5 text-slate-600" title={ev.created_by_name || undefined}>{ev.created_by_name || "—"}</td>
                    <td className="whitespace-nowrap px-2 py-1.5 text-right">
                      <button type="button" onClick={() => void openDetail(ev.id)} className="rounded px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50">Detalhes</button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {(detail || detailLoading) && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-2 sm:p-4" onClick={() => setDetail(null)}>
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between border-b border-slate-200 p-4">
              <h3 className="text-base font-semibold text-slate-900">
                Evento {detail ? detail.code : ""}
              </h3>
              <button type="button" onClick={() => setDetail(null)} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">✕</button>
            </div>
            {detailLoading || !detail ? (
              <div className="p-8 text-center text-slate-500">Carregando…</div>
            ) : (
              <>
                {/* Cabeçalho-resumo do evento */}
                <div className="grid grid-cols-2 gap-3 border-b border-slate-200 p-4 sm:grid-cols-3">
                  <div><p className="text-xs uppercase tracking-wide text-slate-500">Instituição</p><p className="mt-0.5 text-sm">{detail.institution || "—"}</p></div>
                  <div><p className="text-xs uppercase tracking-wide text-slate-500">Data do pagamento</p><p className="mt-0.5 text-sm">{formatDateBr(detail.payment_date)}</p></div>
                  <div><p className="text-xs uppercase tracking-wide text-slate-500">Origem</p><p className="mt-0.5 text-sm">{detail.funding_source_label || "Múltiplas origens"}</p></div>
                  <div><p className="text-xs uppercase tracking-wide text-slate-500">Valor Total</p><p className="mt-0.5 text-sm font-semibold tabular-nums">{formatCurrencyOrDash(detail.total_amount)}</p></div>
                  <div><p className="text-xs uppercase tracking-wide text-slate-500">Quantidade de NFs</p><p className="mt-0.5 text-sm">{detail.invoice_count}</p></div>
                  <div><p className="text-xs uppercase tracking-wide text-slate-500">Usuário</p><p className="mt-0.5 text-sm">{detail.created_by_name || "—"}</p></div>
                </div>
                {/* NFs do evento */}
                <div className="p-4">
                  <p className="mb-2 text-sm font-semibold text-slate-800">NFs do evento</p>
                  <table className="w-full divide-y divide-slate-200 text-sm">
                    <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                      <tr>
                        <th className="px-2 py-2">NF</th>
                        <th className="px-2 py-2 text-right">Valor</th>
                        <th className="px-2 py-2">Origem</th>
                        <th className="px-2 py-2">Observação</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {detail.movimentacoes.map((m) => (
                        <tr key={m.id} className={m.reversed_at ? "text-slate-400 line-through" : ""}>
                          <td className="whitespace-nowrap px-2 py-1.5">
                            {m.nf_number || "—"}
                            {m.client_name ? <span className="ml-1 text-xs text-slate-500">· {m.client_name}</span> : ""}
                          </td>
                          <td className="px-2 py-1.5 text-right tabular-nums">{formatCurrencyOrDash(m.amount)}</td>
                          <td className="px-2 py-1.5 text-slate-600">{m.funding_source_label}</td>
                          <td className="max-w-[220px] truncate px-2 py-1.5 text-slate-600" title={m.observation || undefined}>{m.observation || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
