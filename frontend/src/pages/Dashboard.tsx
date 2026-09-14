import { useEffect, useState } from "react";
import { FinancialDashboardCharts } from "@/components/FinancialDashboardCharts";
import { FinancialEvolutionProjectChart } from "@/components/FinancialEvolutionProjectChart";
import { DashboardToolbar } from "@/components/dashboard/DashboardToolbar";
import { HoverDetails, type HoverDetailsRow } from "@/components/dashboard/HoverDetails";
import { useSeesAllProjects } from "@/hooks/usePermission";
import { useScenario, type ScenarioKind } from "@/context/ScenarioContext";
import { formatCurrencyOrDash } from "@/utils/currency";
import {
  ANTICIPATION_SOURCE_NOTE,
  LABOR_REAL_TITLE,
  LUCRO_REAL_PROFIT_TAX_NOTE,
  VEHICLE_REAL_TITLE,
  anticipationInstitutions,
  taxLabel,
} from "@/utils/projectCostBasis";
import {
  fetchFinancialSummary,
  fetchProjectsBreakdown,
  type DirectorSummary,
  type FinancialDashboardSummary,
  type ProjectBreakdownRow,
} from "@/services/dashboard";
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

// Valores podem vir `null` do backend quando o usuário não tem "Dados sensíveis"
// (redact_for). Toda renderização monetária/percentual trata null → "—" (mesmo padrão
// de formatCurrencyOrDash), evitando exceção (tela branca) ao chamar métodos em null.
const SENSITIVE_DASH = "—";

/** Fonte única (utils/currency): valor redigido → "—". */
const formatMoney = formatCurrencyOrDash;

function formatPct(n: number | null | undefined): string {
  if (n == null) return SENSITIVE_DASH;
  return `${(n * 100).toFixed(1)}%`;
}

/** Margem em fração da receita (ex.: 0,15 → 15,0%). */
function formatPercentage(n: number | null | undefined): string {
  return formatPct(n);
}

function getProfitColor(value: number | null | undefined): string {
  if (value == null) return "text-gray-900";
  if (value > 0) return "text-green-600";
  if (value < 0) return "text-red-600";
  return "text-gray-900";
}

/** Percentual já em escala 0–100 (backend). */
function formatMoneyVsRevenue(money: number | null | undefined, pctOfRevenue: number | null | undefined): string {
  if (money == null) return SENSITIVE_DASH;
  const pct = pctOfRevenue == null ? "" : ` (${pctOfRevenue.toFixed(1)}%)`;
  return `${formatMoney(money)}${pct}`;
}

/** Parte ÷ todo em "12,34%" (2 casas, vírgula). Sem valor ou todo zero/ausente → "—". */
function formatShare(part: number | null | undefined, whole: number | null | undefined): string {
  if (part == null || whole == null || !Number.isFinite(whole) || Math.abs(whole) < 0.005) return SENSITIVE_DASH;
  return `${((part / whole) * 100).toFixed(2).replace(".", ",")}%`;
}

/** Detalhamento dos impostos por tributo (valor e % da receita). */
function TaxDetails({ s }: { s: DirectorSummary }) {
  const revenue = s.total_revenue ?? s.revenue_total;
  const regime = s.tax_regime ?? null;
  const components: Array<[string, number | null | undefined]> = regime
    ? [
        ["PIS", s.tax_pis],
        ["COFINS", s.tax_cofins],
        ["ISS", s.tax_iss],
        ["IRPJ", s.tax_irpj],
        ["CSLL", s.tax_csll],
      ]
    : [];
  const rows: HoverDetailsRow[] = components
    // No Lucro Real IRPJ/CSLL incidem sobre o lucro da empresa: aqui vêm 0 → ocultos.
    .filter(([name, v]) => !(regime === "LUCRO_REAL" && (name === "IRPJ" || name === "CSLL") && v === 0))
    .map(([name, v]) => ({ key: name, label: name, values: [formatMoney(v), formatShare(v, revenue)] }));
  rows.push({
    key: "total",
    label: "Total",
    values: [formatMoney(s.tax_amount), formatShare(s.tax_amount, revenue)],
    emphasis: true,
  });
  const footer =
    regime === "LUCRO_REAL" || regime === "MISTO"
      ? LUCRO_REAL_PROFIT_TAX_NOTE
      : !regime
        ? "Sem regime tributário cadastrado: percentual de reserva sobre a receita."
        : undefined;
  return (
    <HoverDetails
      title={taxLabel(regime)}
      subtitle={`Carga efetiva ${formatShare(s.tax_amount, revenue)} da receita`}
      columns={["Valor", "% receita"]}
      rows={rows}
      footer={footer}
    >
      {taxLabel(regime)}
    </HoverDetails>
  );
}

/** Detalhamento da antecipação por instituição (valor e % do total da antecipação). */
function AnticipationDetails({ s }: { s: DirectorSummary }) {
  const total = s.anticipation_amount;
  const institutions = anticipationInstitutions(s.anticipation_by_institution);
  const rows: HoverDetailsRow[] = institutions.map(([name, v]) => ({
    key: name,
    label: name,
    values: [formatMoney(v), formatShare(v, total)],
  }));
  rows.push({
    key: "total",
    label: "Total",
    values: institutions.length ? [formatMoney(total), formatShare(total, total)] : [formatMoney(total)],
    emphasis: true,
  });
  const source = s.anticipation_source ?? (s.anticipation_partial ? "PARCIAL" : null);
  return (
    <HoverDetails
      title="Antecipação — custo por instituição"
      columns={institutions.length ? ["Valor", "% antecip."] : undefined}
      rows={rows}
      footer={source ? ANTICIPATION_SOURCE_NOTE[source] : undefined}
    >
      Antecipação
    </HoverDetails>
  );
}

export function Dashboard() {
  const { globalScenario } = useScenario();
  const [dashboardScenario, setDashboardScenario] = useState<ScenarioKind>(globalScenario);

  /** Visão "Todos": admin/global OU todos os projetos vinculados (has_all_projects_linked no /users/me). */
  const canViewGlobal = useSeesAllProjects();

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

  const [breakdown, setBreakdown] = useState<ProjectBreakdownRow[]>([]);
  const [breakdownLoading, setBreakdownLoading] = useState(false);

  /** Filtros de período no formato do endpoint (sem project_id/scenario). */
  function buildPeriodParams(): {
    competencia?: string;
    start_date?: string;
    end_date?: string;
    months?: number;
  } {
    if (periodMode === "single") return { competencia };
    if (periodMode === "range") return { start_date: rangeStart, end_date: rangeEnd };
    return { competencia, months: lastNMonths };
  }

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
          setError(
            "Usuário sem projetos vinculados. Solicite a um administrador o acesso aos projetos necessários."
          );
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
        const base: Parameters<typeof fetchFinancialSummary>[0] = {
          ...buildPeriodParams(),
          ...(selectedProjectId ? { project_id: selectedProjectId } : {}),
        };
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

  // Quebra por projeto (gráficos “por projeto”), usando o cenário/período ativos.
  // Projeto único: derivado dos dados já carregados. Visão “Todos”: 1 request por projeto.
  useEffect(() => {
    if (!dataPrevisto || !dataRealizado) return;
    let cancelled = false;

    if (selectedProjectId) {
      const proj = projects.find((p) => p.id === selectedProjectId);
      const src = dashboardScenario === "PREVISTO" ? dataPrevisto.summary : dataRealizado.summary;
      setBreakdown([
        {
          projectId: selectedProjectId,
          name: proj?.name ?? "Projeto",
          revenue: src.total_revenue ?? src.revenue_total,
          operationalCost: src.operational_cost ?? 0,
        },
      ]);
      setBreakdownLoading(false);
      return;
    }

    if (projects.length === 0) {
      setBreakdown([]);
      return;
    }

    setBreakdownLoading(true);
    (async () => {
      try {
        const rows = await fetchProjectsBreakdown(projects, buildPeriodParams(), dashboardScenario);
        if (!cancelled) setBreakdown(rows);
      } catch {
        if (!cancelled) setBreakdown([]);
      } finally {
        if (!cancelled) setBreakdownLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    dataPrevisto,
    dataRealizado,
    dashboardScenario,
    selectedProjectId,
    projects,
    periodMode,
    competencia,
    rangeStart,
    rangeEnd,
    lastNMonths,
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
        <h2 className="text-xl font-semibold text-slate-900">Dashboard operacional</h2>
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
        <h2 className="text-xl font-semibold text-slate-900">Dashboard operacional</h2>
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
    <div className="space-y-4">
      <DashboardToolbar
        title="Dashboard operacional"
        meta={periodSubtitle}
        hint={
          <>
            <p>{scenarioHint}</p>
            <p className="mt-1">
              {isGlobalView
                ? "Visão consolidada. Cards principais e gráficos de composição usam o cenário selecionado; a primeira linha de cards compara previsto × realizado."
                : "Cards principais e gráficos de composição usam o cenário selecionado; a primeira linha de cards compara previsto × realizado."}
            </p>
          </>
        }
      >
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
      </DashboardToolbar>

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
          higherIsWorse
        />
        <ScenarioCompareCard
          label={multiMonth ? "Lucro disponível (soma no período)" : "Lucro disponível"}
          previsto={dataPrevisto.lucro_liquido_previsto ?? sp.net_profit ?? sp.profit}
          realizado={dataRealizado.lucro_liquido_realizado ?? sr.net_profit ?? sr.profit}
        />
      </div>

      {/* `auto-rows-fr`: quando a faixa quebra em duas linhas (telas médias), as linhas ficam com
          a mesma altura em vez de cada uma se ajustar ao seu conteúdo. */}
      <div className="grid auto-rows-fr grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
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
          value={formatMoney(s.total_retention)}
          subtitle={multiMonth ? "Soma dos meses selecionados" : undefined}
        />
        <KpiCard
          label={`Lucro operacional (${scenarioLabelShort})`}
          value={formatMoney(s.operational_profit ?? s.profit)}
          accent="text-gray-900"
          subtitle={`Margem${multiMonth ? " no período" : ""}: ${formatPercentage(s.margin_operational ?? s.margin)}`}
        />
        <KpiCard
          label={`Lucro disponível (${scenarioLabelShort})`}
          value={formatMoney(s.net_profit ?? s.profit)}
          accent={getProfitColor(s.net_profit ?? s.profit)}
          subtitle={`Margem${multiMonth ? " no período" : ""}: ${formatPercentage(s.margin_net ?? s.margin)}`}
        />
        <KpiCard
          label={`EBITDA (${scenarioLabelShort})`}
          value={formatMoney(s.ebitda)}
          accent={getProfitColor(s.ebitda)}
          subtitle={`Margem EBITDA${multiMonth ? " no período" : ""}: ${formatPercentage(s.ebitda_margin)}`}
        />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-sm font-medium text-slate-700">
          Custos operacionais por projeto ({scenarioLabelShort})
        </h3>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-slate-500">Operacional total</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.operational_cost, s.operational_cost_pct)}
            </dd>
          </div>
          <div>
            <dt className="flex items-center gap-1.5 text-slate-500">
              Mão de obra
              {s.labor_real && <BasisChip title={LABOR_REAL_TITLE}>folha real</BasisChip>}
            </dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.labor_cost, s.labor_cost_pct)}
            </dd>
          </div>
          <div>
            <dt className="flex items-center gap-1.5 text-slate-500">
              Veículos
              {s.vehicle_real && <BasisChip title={VEHICLE_REAL_TITLE}>frota real</BasisChip>}
            </dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.vehicle_cost, s.vehicle_cost_pct)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Sistemas</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.system_cost, s.system_cost_pct)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Fixos operacionais</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.fixed_operational_cost, s.fixed_operational_cost_pct)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">
              <TaxDetails s={s} />
            </dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.tax_amount, s.tax_amount_pct)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Rateio / overhead</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.overhead_amount, s.overhead_amount_pct)}
            </dd>
          </div>
          <div>
            <dt className="flex items-center gap-1.5 text-slate-500">
              <AnticipationDetails s={s} />
              {s.anticipation_partial && (
                <span
                  className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-700"
                  title="Custo das antecipações do mês seguinte, que ainda está em andamento: o valor pode subir a cada nova operação até o fim do mês."
                >
                  parcial
                </span>
              )}
            </dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {formatMoneyVsRevenue(s.anticipation_amount, s.anticipation_amount_pct)}
            </dd>
          </div>
        </dl>
      </div>

      <FinancialEvolutionProjectChart
        monthlySeries={activeData.monthly_series}
        scenario={dashboardScenario}
        multiMonth={multiMonth}
      />

      <FinancialDashboardCharts
        breakdown={breakdown}
        loading={breakdownLoading}
        multiMonth={multiMonth}
        selectedScenario={dashboardScenario}
      />
    </div>
  );
}

/** Chip "folha real" / "frota real" — mesmo desenho do chip "parcial" da Antecipação, em verde. */
function BasisChip({ title, children }: { title: string; children: string }) {
  return (
    <span className="cursor-help rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700" title={title}>
      {children}
    </span>
  );
}

function ScenarioCompareCard({
  label,
  previsto,
  realizado,
  higherIsWorse = false,
}: {
  label: string;
  // Podem vir null quando redigidos por "Dados sensíveis" (redact_for) → exibe "—".
  previsto: number | null;
  realizado: number | null;
  /**
   * Para métricas em que “realizado maior que previsto” é desfavorável (ex.: Custo total),
   * inverte a cor do Δ: estouro (realizado &gt; previsto) fica vermelho; economia, verde.
   * Receita e Lucro mantêm o padrão (maior = melhor = verde).
   */
  higherIsWorse?: boolean;
}) {
  // Sem ambos os valores (ex.: redigidos), não há delta calculável → "—".
  const hasBoth = previsto != null && realizado != null;
  const delta = hasBoth ? realizado - previsto : null;
  const pct = hasBoth && previsto !== 0 ? ((delta as number) / previsto) * 100 : null;
  let deltaCls = "text-slate-700";
  if (delta != null && delta !== 0) {
    const favorable = higherIsWorse ? delta < 0 : delta > 0;
    deltaCls = favorable ? "text-emerald-700" : "text-red-700";
  }
  return (
    <div className="flex h-full flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {/* Mesma faixa fixa do KpiCard: "Custo total (soma no período)" ocupa duas linhas e não pode
          empurrar as linhas de valor para fora do alinhamento com os cards vizinhos. */}
      <p className="line-clamp-2 min-h-[2.5rem] text-sm font-medium leading-5 text-slate-700" title={label}>
        {label}
      </p>
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
  // Três FAIXAS de altura fixa (rótulo · valor · subtítulo). Sem isso, um rótulo de duas linhas
  // empurra o valor para baixo e os cards da mesma faixa deixam de se alinhar entre si — e o
  // subtítulo é reservado mesmo quando ausente, para que todos os valores fiquem na mesma altura.
  return (
    <div className="flex h-full flex-col rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
      <p className="line-clamp-2 min-h-[2.5rem] text-sm font-medium leading-5 text-slate-500" title={label}>
        {label}
      </p>
      <p
        className={`mt-1 min-h-[2rem] text-2xl font-semibold leading-8 tabular-nums ${accent ?? "text-slate-900"}`}
      >
        {value}
      </p>
      {/* Sempre renderizado: a faixa reservada mantém a base dos cards alinhada mesmo sem texto. */}
      <p className="mt-0.5 min-h-[1.25rem] text-sm leading-5 text-gray-500">{subtitle}</p>
    </div>
  );
}
