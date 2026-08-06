import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  createSettlement,
  fetchManagementSummary,
  fetchObligations,
  fetchSettlementKpis,
  fetchTimeline,
  reverseMovement,
  FUNDING_SOURCE_LABELS,
  FUNDING_SOURCE_OPTIONS,
  SITUACAO_META,
  type FundingSource,
  type ManagementSummary,
  type Obligation,
  type SettlementKpis,
  type SettlementMovementInput,
  type SituacaoLiquidacao,
  type Timeline,
} from "@/services/advanceSettlements";
import { RepasseLedgerModal } from "@/components/RepasseLedgerModal";
import { formatApiError } from "@/utils/apiError";
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
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-lg font-semibold tabular-nums text-slate-900 ${accent ?? ""}`}>{value}</p>
    </div>
  );
}

function ManagementPanel({ m }: { m: ManagementSummary }) {
  const dist = m.distribuicao_origens;
  const barColors = ["bg-indigo-500", "bg-emerald-500", "bg-amber-500", "bg-sky-500", "bg-slate-400"];
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="mb-3 text-sm font-semibold text-slate-800">Visão gerencial</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
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

export function AdvanceSettlementsTab({ canEdit }: { canEdit: boolean }) {
  const [obligations, setObligations] = useState<Obligation[]>([]);
  const [kpis, setKpis] = useState<SettlementKpis | null>(null);
  const [mgmt, setMgmt] = useState<ManagementSummary | null>(null);
  const [showMgmt, setShowMgmt] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filtros: aplicados APENAS sobre o conjunto já carregado (dados já vêm prontos do backend).
  const [fSituacao, setFSituacao] = useState<"ALL" | SituacaoLiquidacao>("ALL");
  const [fInstitution, setFInstitution] = useState<string>("ALL");
  const [fClient, setFClient] = useState("");
  const [fNf, setFNf] = useState("");
  const [fSgc, setFSgc] = useState("");

  const [settleTarget, setSettleTarget] = useState<Obligation | null>(null);
  const [ledgerOpen, setLedgerOpen] = useState(false);

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

  useEffect(() => {
    void load();
  }, [load]);

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
      return true;
    });
  }, [obligations, fSituacao, fInstitution, fClient, fNf, fSgc]);

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
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => setShowMgmt((v) => !v)}
          className={`rounded-lg border px-4 py-2 text-sm font-medium ${
            showMgmt ? "border-indigo-300 bg-indigo-50 text-indigo-700" : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50"
          }`}
        >
          Visão gerencial
        </button>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
        >
          Atualizar
        </button>
        <button
          type="button"
          onClick={() => setLedgerOpen(true)}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
        >
          Extrato do Repasse
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      {/* Cards: consomem EXCLUSIVAMENTE os KPIs do backend (sem somatório em React). */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
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
        </div>
      </section>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-[1100px] w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-2 py-2">Situação</th>
              <th className="px-2 py-2">Nº NF</th>
              <th className="px-2 py-2">Cliente</th>
              <th className="px-2 py-2 text-right">Borderô</th>
              <th className="px-2 py-2">Instituição</th>
              <th className="px-2 py-2 text-right">Valor</th>
              <th className="px-2 py-2 text-right">Liquidado</th>
              <th className="px-2 py-2 text-right">Residual</th>
              <th className="px-2 py-2">Origens</th>
              <th className="px-2 py-2">Vencimento</th>
              <th className="px-2 py-2 text-right">Atraso</th>
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
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={12} className="px-3 py-8 text-center text-slate-500">
                  Nenhuma NF antecipada com obrigação de liquidação.
                </td>
              </tr>
            ) : (
              filtered.map((o) => (
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
                  <td className="px-2 py-1.5 text-right tabular-nums">{formatCurrencyOrDash(o.valor_total)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-emerald-700">{formatCurrencyOrDash(o.valor_liquidado)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums font-medium">{formatCurrencyOrDash(o.valor_residual)}</td>
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
      {ledgerOpen && <RepasseLedgerModal institutions={institutions} onClose={() => setLedgerOpen(false)} />}
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
