import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { EChartsType } from "echarts";
import { isAxiosError } from "axios";
import { useWorkspace } from "@/context/WorkspaceContext";
import { useScenario, type ScenarioKind } from "@/context/ScenarioContext";
import {
  fetchFinancialEvolution,
  fetchIndicatorFilters,
  fetchRoiOperacionalRanking,
  type FinancialEvolution,
  type IndicatorFilters,
  type ProjectRoi,
} from "@/services/indicators";
import { currentMonth, monthMinus, monthToCompetencia } from "@/utils/roiFormat";
import { formatCurrency, formatCurrencyShort } from "@/utils/currency";
import { CHART_COLORS } from "@/utils/chartTheme";
import { DashboardHeader } from "@/components/dashboard/executive/DashboardHeader";
import { DashboardFilterBar, FilterField } from "@/components/dashboard/executive/DashboardFilterBar";
import { ChartCard } from "@/components/dashboard/executive/ChartCard";
import { DashboardModal } from "@/components/dashboard/executive/DashboardModal";
import { KpiCard } from "@/components/dashboard/executive/KpiCard";
import { InsightsPanel, type InsightItem } from "@/components/dashboard/executive/InsightsPanel";
import { ProjectFilterDropdown } from "@/components/indicators/ProjectFilterDropdown";
import { FinancialEvolutionMainChart, MAIN_SERIES_IDS } from "@/components/indicators/FinancialEvolutionMainChart";
import { NetProfitChart } from "@/components/indicators/NetProfitChart";
import { useFinancialChartViz } from "@/hooks/useFinancialChartViz";

type RangePreset = "custom" | "last3" | "last6" | "last12" | "ytd";

/** Cor de acento por indicador (alinhada aos gráficos). */
const NET_PROFIT_COLOR = "#0d9488";

const MONTHS_PT = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"];

/** "YYYY-MM-01" → "JUN". */
function monthAbbr(competencia: string): string {
  const m = Number(competencia.split("-")[1]);
  return MONTHS_PT[m - 1] ?? "";
}

const TENDENCIA_LABEL: Record<string, string> = { alta: "Em alta", baixa: "Em queda", estavel: "Estável" };

/** Toggle "Exibir valores em todos os pontos" (reutilizado no card e no modal). */
function ValueToggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer select-none items-center gap-1.5 text-xs font-medium text-slate-600">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="accent-indigo-600" />
      Exibir valores em todos os pontos
    </label>
  );
}

/** Botão discreto de barra de ferramentas do gráfico. */
function ChartToolButton({ onClick, label, children }: { onClick: () => void; label: string; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
    >
      {children}
    </button>
  );
}

const ExpandIcon = (
  <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5" aria-hidden>
    <path d="M4 4h5v2H6v3H4V4zm12 0v5h-2V6h-3V4h5zM4 16v-5h2v3h3v2H4zm12 0h-5v-2h3v-3h2v5z" />
  </svg>
);

export function EvolucaoFinanceira() {
  const { setWorkspace } = useWorkspace();
  const { globalScenario, setGlobalScenario } = useScenario();

  const [dataInicial, setDataInicial] = useState<string>(() => monthMinus(currentMonth(), 5));
  const [dataFinal, setDataFinal] = useState<string>(() => currentMonth());
  const [preset, setPreset] = useState<RangePreset>("last6");

  const [filters, setFilters] = useState<IndicatorFilters | null>(null);
  // Ranking dos projetos COM MOVIMENTAÇÃO (receita/custo) no período — fonte das
  // opções de projeto e da seleção automática (mesmo critério do ROI Operacional).
  const [rankingItems, setRankingItems] = useState<ProjectRoi[]>([]);
  const [selProjects, setSelProjects] = useState<Set<string>>(new Set());
  const [selCostCenters, setSelCostCenters] = useState<Set<string>>(new Set());
  // Período (di|df) para o qual a seleção automática já foi aplicada. A
  // autosseleção ocorre só na abertura e quando o PERÍODO muda — nunca em troca de
  // cenário, zoom ou controles de gráfico.
  const lastAutoPeriodRef = useRef<string | null>(null);
  const rankingReqId = useRef(0);
  const [rankingLoading, setRankingLoading] = useState(true);

  const [data, setData] = useState<FinancialEvolution | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Controles de UX do gráfico principal (não alteram dados nem filtros).
  // Estado de visualização controlado pelo React (preservado entre reconstruções).
  const { selectedSeries, showAllValues, setShowAllValues, applySelection } = useFinancialChartViz(MAIN_SERIES_IDS);
  const [expanded, setExpanded] = useState(false);
  const modalChartRef = useRef<EChartsType | null>(null);

  useEffect(() => {
    setWorkspace("indicators");
  }, [setWorkspace]);

  useEffect(() => {
    void (async () => {
      try {
        setFilters(await fetchIndicatorFilters());
      } catch {
        setFilters({ projects: [], cost_centers: [] });
      }
    })();
  }, []);

  const di = monthToCompetencia(dataInicial);
  const df = monthToCompetencia(dataFinal);
  const projKey = useMemo(() => [...selProjects].sort().join(","), [selProjects]);
  const ccKey = useMemo(() => [...selCostCenters].sort().join(","), [selCostCenters]);

  // Ranking dos projetos com movimentação no período (mesmo endpoint/critério do
  // ROI). Reexecuta em período/cenário, mas a seleção automática só é aplicada
  // quando o PERÍODO muda (guardado por lastAutoPeriodRef).
  const loadRanking = useCallback(async () => {
    setRankingLoading(true);
    const periodKey = `${di}|${df}`;
    const myId = ++rankingReqId.current;
    try {
      const ranking = await fetchRoiOperacionalRanking({ dataInicial: di, dataFinal: df, scenario: globalScenario });
      if (myId !== rankingReqId.current) return;
      setRankingItems(ranking.items);
      if (lastAutoPeriodRef.current !== periodKey) {
        setSelProjects(new Set(ranking.items.map((i) => i.project_id)));
        lastAutoPeriodRef.current = periodKey;
      }
    } catch {
      if (myId !== rankingReqId.current) return;
      setRankingItems([]);
      if (lastAutoPeriodRef.current !== periodKey) {
        setSelProjects(new Set());
        lastAutoPeriodRef.current = periodKey;
      }
    } finally {
      if (myId === rankingReqId.current) setRankingLoading(false);
    }
  }, [di, df, globalScenario]);

  useEffect(() => {
    void loadRanking();
  }, [loadRanking]);

  const load = useCallback(async () => {
    const ids = projKey ? projKey.split(",") : [];
    // Nenhum projeto selecionado (ou nenhum com movimentação): não busca "todos".
    if (ids.length === 0) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchFinancialEvolution({
        dataInicial: di,
        dataFinal: df,
        scenario: globalScenario,
        projectIds: ids,
        costCenters: ccKey ? ccKey.split(",") : undefined,
      });
      setData(payload);
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Não foi possível carregar a Evolução Financeira.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [di, df, globalScenario, projKey, ccKey]);

  useEffect(() => {
    void load();
  }, [load]);

  function applyPreset(p: RangePreset) {
    setPreset(p);
    const anchor = currentMonth();
    if (p === "last3") setDataInicial(monthMinus(anchor, 2));
    else if (p === "last6") setDataInicial(monthMinus(anchor, 5));
    else if (p === "last12") setDataInicial(monthMinus(anchor, 11));
    else if (p === "ytd") setDataInicial(`${anchor.split("-")[0]}-01`);
    if (p !== "custom") setDataFinal(anchor);
  }

  const toggle = (set: React.Dispatch<React.SetStateAction<Set<string>>>) => (id: string) =>
    set((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const projectOptions = useMemo(
    () => rankingItems.map((i) => ({ id: i.project_id, name: i.project_name })),
    [rankingItems],
  );
  const costCenterOptions = useMemo(
    () => (filters?.cost_centers ?? []).map((c) => ({ id: c, name: c })),
    [filters],
  );

  const periodLabel = `${monthAbbr(di)}/${di.split("-")[0]} – ${monthAbbr(df)}/${df.split("-")[0]}`;

  const insights: InsightItem[] = useMemo(() => {
    const ins = data?.insights;
    if (!ins) return [];
    const items: InsightItem[] = [];
    if (ins.maior_faturamento)
      items.push({ label: "Maior faturamento", value: formatCurrencyShort(ins.maior_faturamento.value), meta: monthAbbr(ins.maior_faturamento.competencia), color: CHART_COLORS.faturamento });
    if (ins.menor_faturamento)
      items.push({ label: "Menor faturamento", value: formatCurrencyShort(ins.menor_faturamento.value), meta: monthAbbr(ins.menor_faturamento.competencia), color: CHART_COLORS.faturamento });
    if (ins.maior_lucro_operacional)
      items.push({ label: "Maior lucro operacional", value: formatCurrencyShort(ins.maior_lucro_operacional.value), meta: monthAbbr(ins.maior_lucro_operacional.competencia), color: CHART_COLORS.caixaPos });
    if (ins.maior_lucro_liquido)
      items.push({ label: "Maior lucro líquido", value: formatCurrencyShort(ins.maior_lucro_liquido.value), meta: monthAbbr(ins.maior_lucro_liquido.competencia), color: NET_PROFIT_COLOR });
    if (ins.projeto_maior_faturamento)
      items.push({ label: "Projeto · maior faturamento", value: ins.projeto_maior_faturamento.project_name, meta: formatCurrencyShort(ins.projeto_maior_faturamento.value), color: CHART_COLORS.faturamento });
    if (ins.projeto_maior_lucro)
      items.push({ label: "Projeto · maior lucro", value: ins.projeto_maior_lucro.project_name, meta: formatCurrencyShort(ins.projeto_maior_lucro.value), color: CHART_COLORS.caixaPos });
    items.push({ label: "Tendência financeira", value: TENDENCIA_LABEL[ins.tendencia] ?? "—", color: "#6366f1" });
    return items;
  }, [data]);

  // Há dados quando existe série E algum indicador acumulado é economicamente
  // relevante (evita mostrar um dashboard todo zerado para filtros sem movimento).
  const hasPoints =
    (data?.points.length ?? 0) > 0 &&
    !!data &&
    [data.kpis.faturamento.total, data.kpis.custo_mo.total, data.kpis.lucro_operacional.total].some(
      (v) => Math.abs(v) > 0.005,
    );

  return (
    <div className="space-y-4">
      <DashboardHeader
        title="Evolução Financeira"
        subtitle={`Período ${periodLabel}`}
        description="Desempenho financeiro mensal e evolução em relação ao mês anterior."
        badge="Relatório Executivo · Confidencial"
      />

      <DashboardFilterBar>
        <FilterField label="Data inicial">
          <input
            type="month"
            value={dataInicial}
            onChange={(e) => {
              setPreset("custom");
              setDataInicial(e.target.value || dataInicial);
            }}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-800 focus:border-indigo-500 focus:outline-none"
          />
        </FilterField>
        <FilterField label="Data final">
          <input
            type="month"
            value={dataFinal}
            onChange={(e) => {
              setPreset("custom");
              setDataFinal(e.target.value || dataFinal);
            }}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-800 focus:border-indigo-500 focus:outline-none"
          />
        </FilterField>
        <FilterField label="Projeto">
          <ProjectFilterDropdown
            options={projectOptions}
            selected={selProjects}
            onToggle={toggle(setSelProjects)}
            emptyText="Nenhum projeto"
            noOptionsText="Nenhum projeto com movimentação no período."
          />
        </FilterField>
        <FilterField label="Centro de custo">
          <ProjectFilterDropdown
            options={costCenterOptions}
            selected={selCostCenters}
            onToggle={toggle(setSelCostCenters)}
            emptyText="Todos os centros"
            noOptionsText="Nenhum centro de custo cadastrado."
          />
        </FilterField>
        <FilterField label="Atalhos">
          <div className="inline-flex flex-wrap gap-1">
            {(
              [
                ["last3", "3 meses"],
                ["last6", "6 meses"],
                ["last12", "12 meses"],
                ["ytd", "Ano atual"],
              ] as [RangePreset, string][]
            ).map(([p, label]) => (
              <button
                key={p}
                type="button"
                onClick={() => applyPreset(p)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${
                  preset === p ? "border-indigo-600 bg-indigo-600 text-white" : "border-slate-300 text-slate-700 hover:bg-slate-50"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </FilterField>
        <FilterField label="Cenário">
          <div className="inline-flex overflow-hidden rounded-lg border border-slate-300">
            {(["REALIZADO", "PREVISTO"] as ScenarioKind[]).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setGlobalScenario(s)}
                className={`px-3 py-1.5 text-sm font-medium ${
                  globalScenario === s ? "bg-indigo-600 text-white" : "text-slate-700 hover:bg-slate-50"
                }`}
              >
                {s === "REALIZADO" ? "Realizado" : "Previsto"}
              </button>
            ))}
          </div>
        </FilterField>
      </DashboardFilterBar>

      {error ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
      ) : (loading || rankingLoading) && !data ? (
        <p className="text-sm text-slate-500">Carregando…</p>
      ) : selProjects.size === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">
          {rankingItems.length === 0
            ? "Não há dados financeiros para o período e filtros selecionados."
            : "Selecione ao menos um projeto para visualizar as métricas."}
        </div>
      ) : !hasPoints ? (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">
          Não há dados financeiros para o período e filtros selecionados.
        </div>
      ) : (
        <>
          {/* Gráfico principal (2/3) + coluna Lucro Líquido & Insights (1/3) */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <ChartCard
              className="lg:col-span-2"
              title="Evolução mensal"
              subtitle="Receita, custos e resultado operacional"
              aside={
                <div className="flex flex-wrap items-center gap-3">
                  <ValueToggle checked={showAllValues} onChange={setShowAllValues} />
                  <ChartToolButton onClick={() => setExpanded(true)} label="Expandir gráfico">
                    {ExpandIcon}
                    Expandir
                  </ChartToolButton>
                </div>
              }
            >
              <FinancialEvolutionMainChart
                points={data!.points}
                showAllValues={showAllValues}
                selectedSeries={selectedSeries}
                onSelectedSeriesChange={applySelection}
              />
            </ChartCard>

            <div className="flex flex-col gap-4">
              <ChartCard title="Lucro Líquido" subtitle="Resultado final por mês">
                <NetProfitChart points={data!.points} />
              </ChartCard>
              <InsightsPanel
                headline={
                  data!.insights.crescimento_acumulado_pct !== null
                    ? {
                        label: "Crescimento da receita",
                        value: `${data!.insights.crescimento_acumulado_pct >= 0 ? "+" : ""}${Math.round(
                          data!.insights.crescimento_acumulado_pct,
                        )}%`,
                        meta: periodLabel,
                      }
                    : undefined
                }
                items={insights}
              />
            </div>
          </div>

          {/* Cards KPI */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard label="Faturamento" value={formatCurrency(data!.kpis.faturamento.total)} deltaPct={data!.kpis.faturamento.growth_pct} color={CHART_COLORS.faturamento} />
            <KpiCard label="Custos de M.O." value={formatCurrency(data!.kpis.custo_mo.total)} deltaPct={data!.kpis.custo_mo.growth_pct} color={CHART_COLORS.custos} />
            <KpiCard label="Lucro Operacional" value={formatCurrency(data!.kpis.lucro_operacional.total)} deltaPct={data!.kpis.lucro_operacional.growth_pct} color={CHART_COLORS.caixaPos} />
            <KpiCard label="Lucro Líquido" value={formatCurrency(data!.kpis.lucro_liquido.total)} deltaPct={data!.kpis.lucro_liquido.growth_pct} color={NET_PROFIT_COLOR} />
          </div>
        </>
      )}

      {/* Modo expandido: mesmo gráfico, filtros e séries, com zoom (dataZoom). */}
      <DashboardModal
        open={expanded && hasPoints}
        title="Evolução mensal"
        onClose={() => setExpanded(false)}
        actions={
          <>
            <ValueToggle checked={showAllValues} onChange={setShowAllValues} />
            <ChartToolButton
              onClick={() => modalChartRef.current?.dispatchAction({ type: "dataZoom", start: 0, end: 100 })}
              label="Resetar zoom"
            >
              Resetar zoom
            </ChartToolButton>
          </>
        }
      >
        {data ? (
          <FinancialEvolutionMainChart
            points={data.points}
            showAllValues={showAllValues}
            selectedSeries={selectedSeries}
            onSelectedSeriesChange={applySelection}
            expanded
            onReady={(inst) => {
              modalChartRef.current = inst;
            }}
            height="78vh"
          />
        ) : null}
      </DashboardModal>
    </div>
  );
}
