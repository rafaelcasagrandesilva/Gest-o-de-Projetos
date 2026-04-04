import { useEffect, useMemo, useState } from "react";
import { FinancialDashboardCharts } from "@/components/FinancialDashboardCharts";
import { useAuth } from "@/context/AuthContext";
import { useScenario, type ScenarioKind } from "@/context/ScenarioContext";
import { fetchFinancialSummary, type FinancialDashboardSummary } from "@/services/dashboard";
import { listProjects, type Project } from "@/services/projects";
import { isAxiosError } from "axios";

function monthStart(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function formatPeriodPt(iso: string): string {
  if (!iso || iso.length < 7) return iso;
  const [y, m] = iso.slice(0, 10).split("-");
  return `${m}/${y}`;
}

type PeriodMode = "single" | "range" | "lastN";

function formatMoney(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

/** Margem em fração da receita (ex.: 0,15 → 15,0%). */
function formatPercentage(n: number): string {
  return formatPct(n);
}

function getProfitColor(value: number): string {
  if (value > 0) return "text-green-600";
  if (value < 0) return "text-red-600";
  return "text-gray-900";
}

/** Percentual já em escala 0–100 (backend). */
function formatMoneyVsRevenue(money: number, pctOfRevenue: number): string {
  return `${formatMoney(money)} (${pctOfRevenue.toFixed(1)}%)`;
}

export function Dashboard() {
  const { user } = useAuth();
  const { globalScenario } = useScenario();
  const [dashboardScenario, setDashboardScenario] = useState<ScenarioKind>(globalScenario);

  /** Alinhado ao backend: visão consolidada sem project_id para ADMIN e CONSULTA. */
  const canViewGlobal = useMemo(
    () => Boolean(user?.role_names?.some((r) => r === "ADMIN" || r === "CONSULTA")),
    [user]
  );

  const [periodMode, setPeriodMode] = useState<PeriodMode>("single");
  const [competencia, setCompetencia] = useState(() => monthStart(new Date()));
  const [rangeStart, setRangeStart] = useState(() => monthStart(new Date()));
  const [rangeEnd, setRangeEnd] = useState(() => monthStart(new Date()));
  const [lastNMonths, setLastNMonths] = useState<3 | 6 | 12>(6);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [projectsError, setProjectsError] = useState<string | null>(null);

  const [dataPrevisto, setDataPrevisto] = useState<FinancialDashboardSummary | null>(null);
  const [dataRealizado, setDataRealizado] = useState<FinancialDashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setProjectsError(null);
      try {
        const list = await listProjects();
        if (cancelled) return;
        setProjects(list);
        if (!canViewGlobal && list.length > 0) {
          setSelectedProjectId((prev) => (prev === "" ? list[0].id : prev));
        }
      } catch {
        if (!cancelled) setProjectsError("Não foi possível carregar a lista de projetos.");
      } finally {
        if (!cancelled) setProjectsLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [canViewGlobal]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!canViewGlobal) {
        if (!projectsLoaded) return;
        if (projects.length === 0) {
          setError("Nenhum projeto vinculado ao seu usuário.");
          setDataPrevisto(null);
          setDataRealizado(null);
          setLoading(false);
          return;
        }
        if (!selectedProjectId) return;
      }

      setLoading(true);
      setError(null);
      try {
        const base: Parameters<typeof fetchFinancialSummary>[0] = selectedProjectId
          ? { project_id: selectedProjectId }
          : {};
        if (periodMode === "single") {
          base.competencia = competencia;
        } else if (periodMode === "range") {
          base.start_date = rangeStart;
          base.end_date = rangeEnd;
        } else {
          base.competencia = competencia;
          base.months = lastNMonths;
        }
        const [prev, real] = await Promise.all([
          fetchFinancialSummary({ ...base, scenario: "PREVISTO" }),
          fetchFinancialSummary({ ...base, scenario: "REALIZADO" }),
        ]);
        if (!cancelled) {
          setDataPrevisto(prev);
          setDataRealizado(real);
        }
      } catch (e) {
        if (!cancelled) {
          if (isAxiosError(e)) {
            const st = e.response?.status;
            const detail = (e.response?.data as { detail?: string } | undefined)?.detail;
            if (st === 403) setError("Sem permissão para acessar este dashboard.");
            else if (st === 400) setError(typeof detail === "string" ? detail : "Requisição inválida.");
            else setError("Não foi possível carregar o dashboard financeiro.");
          } else {
            setError("Não foi possível carregar o dashboard financeiro.");
          }
          setDataPrevisto(null);
          setDataRealizado(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    periodMode,
    competencia,
    rangeStart,
    rangeEnd,
    lastNMonths,
    selectedProjectId,
    canViewGlobal,
    projectsLoaded,
    projects.length,
  ]);

  if (!projectsLoaded) {
    return (
      <div className="flex items-center gap-3 text-slate-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
        Carregando projetos…
      </div>
    );
  }

  if (projectsError) {
    return (
      <div className="space-y-4">
        <h2 className="text-xl font-semibold text-slate-900">Dashboard financeiro</h2>
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {projectsError}
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center gap-3 text-slate-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
        Carregando dashboard…
      </div>
    );
  }

  if (error || !dataPrevisto || !dataRealizado) {
    return (
      <div className="space-y-4">
        <h2 className="text-xl font-semibold text-slate-900">Dashboard financeiro</h2>
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{error}</div>
      </div>
    );
  }

  const activeData = dashboardScenario === "PREVISTO" ? dataPrevisto : dataRealizado;
  const s = activeData.summary;
  const sp = dataPrevisto.summary;
  const sr = dataRealizado.summary;
  const isGlobalView = canViewGlobal && !selectedProjectId;
  const monthCount = activeData.month_count ?? 1;
  const multiMonth = monthCount > 1;
  const periodStart = activeData.period_start;
  const periodEnd = activeData.period_end;
  const scenarioHint =
    dashboardScenario === "PREVISTO"
      ? "Exibindo dados previstos (planejamento)."
      : "Exibindo dados realizados (execução).";
  const scenarioLabelShort = dashboardScenario === "PREVISTO" ? "previsto" : "realizado";
  const periodSubtitle =
    periodStart && periodEnd
      ? periodStart.slice(0, 7) === periodEnd.slice(0, 7)
        ? `Competência ${formatPeriodPt(periodStart)}`
        : `${formatPeriodPt(periodStart)} a ${formatPeriodPt(periodEnd)} · ${monthCount} meses`
      : null;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Dashboard financeiro</h2>
          <p className="mt-2 rounded-md border border-indigo-100 bg-indigo-50/70 px-3 py-2 text-sm text-indigo-950">
            {scenarioHint}
          </p>
          <p className="mt-2 text-sm text-slate-500">
            {isGlobalView
              ? "Visão consolidada. Cards principais e gráficos de barras / composição usam só o cenário selecionado. A primeira linha de cards e as curvas ao final comparam previsto × realizado."
              : "Cards principais e gráficos de barras / composição usam só o cenário selecionado. A primeira linha de cards e as curvas ao final comparam previsto × realizado."}
          </p>
          {periodSubtitle ? (
            <p className="mt-1 text-xs font-medium text-indigo-700">{periodSubtitle}</p>
          ) : null}
        </div>
        <div className="flex max-w-2xl flex-col gap-3">
          <div>
            <span className="mb-1 block text-xs font-medium text-slate-500">Cenário</span>
            <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
              {(["PREVISTO", "REALIZADO"] as const).map((sc) => (
                <button
                  key={sc}
                  type="button"
                  onClick={() => setDashboardScenario(sc)}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                    dashboardScenario === sc
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {sc === "PREVISTO" ? "Previsto" : "Realizado"}
                </button>
              ))}
            </div>
          </div>
          <div>
            <span className="mb-1 block text-xs font-medium text-slate-500">Período</span>
            <div className="flex flex-wrap gap-2">
              {(
                [
                  ["single", "Mês único"],
                  ["range", "Intervalo"],
                  ["lastN", "Últimos N meses"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setPeriodMode(id)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                    periodMode === id
                      ? "border-indigo-600 bg-indigo-50 text-indigo-800"
                      : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <label htmlFor="dash-project" className="mb-1 block text-xs font-medium text-slate-500">
                Projeto
              </label>
              <select
                id="dash-project"
                value={selectedProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
                className="min-w-[12rem] rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                {canViewGlobal ? <option value="">Todos</option> : null}
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            {periodMode === "single" ? (
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Mês</label>
                <input
                  type="month"
                  value={competencia.slice(0, 7)}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v) setCompetencia(`${v}-01`);
                  }}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
              </div>
            ) : null}
            {periodMode === "range" ? (
              <>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">Início</label>
                  <input
                    type="month"
                    value={rangeStart.slice(0, 7)}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v) setRangeStart(`${v}-01`);
                    }}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">Fim</label>
                  <input
                    type="month"
                    value={rangeEnd.slice(0, 7)}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v) setRangeEnd(`${v}-01`);
                    }}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  />
                </div>
              </>
            ) : null}
            {periodMode === "lastN" ? (
              <>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">Até o mês (âncora)</label>
                  <input
                    type="month"
                    value={competencia.slice(0, 7)}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v) setCompetencia(`${v}-01`);
                    }}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <span className="mb-1 block text-xs font-medium text-slate-500">Janela</span>
                  <div className="flex gap-1">
                    {([3, 6, 12] as const).map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setLastNMonths(n)}
                        className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium ${
                          lastNMonths === n
                            ? "border-indigo-600 bg-indigo-600 text-white"
                            : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        {n} meses
                      </button>
                    ))}
                  </div>
                </div>
              </>
            ) : null}
          </div>
        </div>
      </div>

      {multiMonth ? (
        <p className="text-xs text-slate-600">
          Comparativo previsto × realizado com soma de cada mês do período; o Δ é a diferença total (realizado −
          previsto).
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <ScenarioCompareCard
          label={multiMonth ? "Receita (soma no período)" : "Receita"}
          previsto={sp.total_revenue ?? sp.revenue_total}
          realizado={sr.total_revenue ?? sr.revenue_total}
        />
        <ScenarioCompareCard
          label={multiMonth ? "Custo total (soma no período)" : "Custo total (regras)"}
          previsto={sp.total_cost ?? sp.cost_total}
          realizado={sr.total_cost ?? sr.cost_total}
        />
        <ScenarioCompareCard
          label={multiMonth ? "Lucro líquido (soma no período)" : "Lucro líquido"}
          previsto={dataPrevisto.lucro_liquido_previsto ?? sp.net_profit ?? sp.profit}
          realizado={dataRealizado.lucro_liquido_realizado ?? sr.net_profit ?? sr.profit}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <KpiCard
          label={multiMonth ? `Receita (${scenarioLabelShort}) — período` : `Receita (${scenarioLabelShort})`}
          value={formatMoney(s.total_revenue ?? s.revenue_total)}
          subtitle={multiMonth ? "Soma dos meses selecionados" : undefined}
        />
        <KpiCard
          label={multiMonth ? `Custo total (${scenarioLabelShort}) — período` : `Custo total (${scenarioLabelShort})`}
          value={formatMoney(s.total_cost ?? s.cost_total)}
          subtitle={multiMonth ? "Soma dos meses selecionados" : undefined}
        />
        <KpiCard
          label={multiMonth ? `Retenção (R$) (${scenarioLabelShort}) — período` : `Retenção (R$) (${scenarioLabelShort})`}
          value={formatMoney(s.total_retention ?? 0)}
          subtitle={multiMonth ? "Soma dos meses selecionados" : undefined}
        />
        <KpiCard
          label={`Lucro operacional (${scenarioLabelShort})`}
          value={formatMoney(s.operational_profit ?? s.profit)}
          accent="text-gray-900"
          subtitle={`Margem${multiMonth ? " no período" : ""}: ${formatPercentage(s.margin_operational ?? s.margin)}`}
        />
        <KpiCard
          label={`Lucro líquido (${scenarioLabelShort})`}
          value={formatMoney(s.net_profit ?? s.profit)}
          accent={getProfitColor(s.net_profit ?? s.profit)}
          subtitle={`Margem${multiMonth ? " no período" : ""}: ${formatPercentage(s.margin_net ?? s.margin)}`}
        />
        <KpiCard
          label={`EBITDA (${scenarioLabelShort})`}
          value={formatMoney(s.ebitda ?? 0)}
          accent={getProfitColor(s.ebitda ?? 0)}
          subtitle={`Margem EBITDA${multiMonth ? " no período" : ""}: ${formatPercentage(s.ebitda_margin ?? 0)}`}
        />
      </div>

      <FinancialDashboardCharts
        summary={s}
        monthlySeries={activeData.monthly_series}
        monthlySeriesPrevisto={activeData.monthly_series_previsto}
        monthlySeriesRealizado={activeData.monthly_series_realizado}
        multiMonth={multiMonth}
        selectedScenario={dashboardScenario}
      />

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-sm font-medium text-slate-700">
          Custos operacionais por projeto ({scenarioLabelShort})
        </h3>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-slate-500">Operacional total</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.operational_cost ?? 0, s.operational_cost_pct ?? 0)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Mão de obra</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.labor_cost ?? 0, s.labor_cost_pct ?? 0)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Veículos</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.vehicle_cost ?? 0, s.vehicle_cost_pct ?? 0)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Sistemas</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.system_cost ?? 0, s.system_cost_pct ?? 0)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Fixos operacionais</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.fixed_operational_cost ?? 0, s.fixed_operational_cost_pct ?? 0)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Impostos (sobre receita)</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.tax_amount ?? 0, s.tax_amount_pct ?? 0)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Rateio / overhead</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.overhead_amount ?? 0, s.overhead_amount_pct ?? 0)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Antecipação</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.anticipation_amount ?? 0, s.anticipation_amount_pct ?? 0)}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

function ScenarioCompareCard({
  label,
  previsto,
  realizado,
}: {
  label: string;
  previsto: number;
  realizado: number;
}) {
  const delta = realizado - previsto;
  const pct = previsto !== 0 ? (delta / previsto) * 100 : null;
  const deltaCls =
    delta > 0 ? "text-emerald-700" : delta < 0 ? "text-red-700" : "text-slate-700";
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm font-medium text-slate-700">{label}</p>
      <div className="mt-3 space-y-1.5 text-sm">
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">Previsto</span>
          <span className="tabular-nums text-slate-900">{formatMoney(previsto)}</span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">Realizado</span>
          <span className="tabular-nums text-slate-900">{formatMoney(realizado)}</span>
        </div>
        <div className="flex justify-between gap-2 border-t border-slate-100 pt-2 font-medium">
          <span className="text-slate-600">Δ (real − prev)</span>
          <span className={`tabular-nums ${deltaCls}`}>
            {formatMoney(delta)}
            {pct != null && !Number.isNaN(pct)
              ? ` (${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%)`
              : ""}
          </span>
        </div>
      </div>
    </div>
  );
}

function KpiCard({
  label,
  value,
  accent,
  subtitle,
}: {
  label: string;
  value: string;
  accent?: string;
  subtitle?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${accent ?? "text-slate-900"}`}>{value}</p>
      {subtitle != null ? <p className="mt-1 text-sm text-gray-500">{subtitle}</p> : null}
    </div>
  );
}
