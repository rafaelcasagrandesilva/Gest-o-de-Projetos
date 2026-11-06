import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { EChartsOption } from "echarts";
import { isAxiosError } from "axios";
import { useWorkspace } from "@/context/WorkspaceContext";
import { useScenario, type ScenarioKind } from "@/context/ScenarioContext";
import { usePermission } from "@/hooks/usePermission";
import {
  fetchCompanyResult,
  type CompanyResult,
  type CompanyResultBasis,
  type CompanyResultMonth,
} from "@/services/companyResult";
import { currentMonth, monthMinus, monthToCompetencia } from "@/utils/roiFormat";
import {
  formatCurrencyOrDash,
  formatCurrencyShort,
  formatCurrencyShortOrDash,
  SENSITIVE_PLACEHOLDER,
} from "@/utils/currency";
import { CHART_COLORS } from "@/utils/chartTheme";
import {
  taxRegimeName,
} from "@/utils/projectCostBasis";
import { DashboardHeader } from "@/components/dashboard/executive/DashboardHeader";
import { DashboardFilterBar, FilterField } from "@/components/dashboard/executive/DashboardFilterBar";
import { ChartCard } from "@/components/dashboard/executive/ChartCard";
import { EChart } from "@/components/dashboard/executive/EChart";
import { Money } from "@/components/Money";
import { ProjectFilterDropdown } from "@/components/indicators/ProjectFilterDropdown";
import {
  COMPANY_SERIES,
  COMPANY_SERIES_IDS,
  DEFAULT_SERIES_VISIBILITY,
  FinancialEvolutionMainChart,
  companySeriesPoints,
} from "@/components/indicators/FinancialEvolutionMainChart";
import { useFinancialChartViz } from "@/hooks/useFinancialChartViz";
import { fetchIndicatorFilters, type FilterProject } from "@/services/indicators";

/**
 * Resultado da Empresa — quanto entra pelos projetos e quanto a empresa realmente precisa pagar.
 *
 * Toda a conta vem pronta do backend (`/indicators/company-result`); esta tela só apresenta.
 * Valores `null` são redigidos (sem permissão de dados sensíveis) e viram "—".
 */

type PeriodMode = "single" | "range" | "last";

/** Paleta da tela — alinhada ao `CHART_COLORS` e aos demais Dashboards Executivos. */
const COLORS = {
  revenue: CHART_COLORS.faturamento,
  revenueMuted: "#bfdbfe",
  // Deduções dos projetos (custos diretos, impostos, antecipação, retenção): ardósia — o rosa
  // anterior se confundia com o vermelho do resultado negativo.
  projectCost: "#64748b",
  available: "#0d9488",
  indirect: "#f97316",
  debt: "#7c3aed",
  companyCosts: "#ea580c",
  pos: CHART_COLORS.caixaPos,
  neg: CHART_COLORS.caixaNeg,
  breakEven: CHART_COLORS.custos,
} as const;

const HELP_SCENARIO =
  "Realizado: o que já aconteceu — receita lançada, impostos devidos, antecipações já realizadas e todos os custos (folha, sistemas, frota, itens do projeto, custos indiretos e dívidas) somente pelo valor efetivamente PAGO no Contas a Pagar; o lançado e ainda não pago aparece como \"a pagar\" e fica fora do resultado.\nPrevisto: simulação do mês se todas as contas lançadas forem pagas — custos pelo valor lançado, ou estimativa/projeção do cadastro quando as contas do mês ainda não foram geradas.";
const HELP_ANTICIPATION =
  "Antecipação: custo das operações do mês seguinte (Lepta + Daycoval, sem repasse) — no Realizado, só as operações já feitas; no Previsto, o custo real ou a taxa média.";
const HELP_RETENTION =
  "Retenção: 10% retidos pelo cliente, devolvidos no fim do contrato — descontada depois do lucro líquido (não está disponível para pagar contas).";
const HELP_DEBTS =
  "Dívidas pagas: parcelas do Endividamento no Contas a Pagar + retiradas do Repasse que abatem dívida (ex.: Lepta), que não geram título no Contas a Pagar.";
const HELP_PROJECTION =
  "O faturamento de um mês paga as contas do mês seguinte: os custos do mês trabalhado vêm do Contas a Pagar do mês seguinte.";
const COSTS_PARTIAL_TITLE =
  "Parcial: o mês de pagamento (seguinte ao trabalhado) ainda está em curso — mais pagamentos podem ser registrados e o valor pode subir.";
const HELP_TAXES =
  "Impostos: pelo regime tributário de cada mês (Configurações → Regime tributário). No Lucro Real, IRPJ/CSLL incidem sobre o lucro da empresa.";
const HELP_FLEET =
  "Frota: rateada entre projetos e indiretos pelo centro de custo dos veículos.";
const HELP_PROJECT_CAP =
  "Itens dos Custos Indiretos com o projeto como centro de custo somam no custo do projeto conforme o cadastro do item (ex.: combustível em Veículos, plano de saúde em Mão de obra).";
const HELP_TEXT = [HELP_SCENARIO, HELP_PROJECTION, HELP_ANTICIPATION, HELP_DEBTS, HELP_RETENTION, HELP_TAXES, HELP_FLEET, HELP_PROJECT_CAP].join("\n");

const SCENARIO_TITLE: Record<ScenarioKind, string> = {
  REALIZADO:
    "O que já aconteceu: receita lançada, impostos devidos, antecipações realizadas e contas efetivamente pagas.",
  PREVISTO:
    "Simulação do mês se todas as contas lançadas forem pagas (estimativa quando as contas ainda não foram lançadas).",
};
const PROJECT_FILTER_CAPTION =
  "Filtrado por projetos: custos indiretos e dívidas pagas não entram (são da empresa, não de um projeto).";
const SCENARIO_CAPTION: Record<ScenarioKind, string> = {
  REALIZADO: "Realizado: igual ao Contas a Pagar — atualiza conforme os pagamentos são registrados.",
  PREVISTO: "Previsto: simulação com todas as contas lançadas pagas.",
};

/** Base dos custos: vem do backend; em backends antigos (sem `basis`) deriva do cenário. */
function basisOf(data: CompanyResult): CompanyResultBasis {
  return data.basis ?? (data.scenario === "PREVISTO" ? "LANCADO" : "PAGO");
}

/** Valor "a pagar" só conta na base PAGO e quando é positivo. */
function openAmount(basis: CompanyResultBasis, v: number | null | undefined): number | null {
  return basis === "PAGO" && v != null && v > 0.005 ? v : null;
}

const PARTIAL_TITLE =
  "Parcial: as operações de antecipação do mês seguinte ainda estão em andamento — o valor pode subir.";
const PROJECTED_TITLE =
  "Projeção: há meses cujas contas ainda não foram geradas no Contas a Pagar; custos indiretos e dívidas pagas desses meses vêm do cadastro.";

const MONTHS_PT = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"];

/** "YYYY-MM-01" (ou "YYYY-MM") → "JUN/26". */
function monthShort(competencia: string | null): string {
  if (!competencia) return "";
  const [y, m] = competencia.split("-");
  return `${MONTHS_PT[Number(m) - 1] ?? ""}/${(y ?? "").slice(2)}`;
}

/** Fração → "32,7%". null/indefinido → "—". */
function formatFraction(frac: number | null | undefined): string {
  if (frac == null || !Number.isFinite(frac)) return SENSITIVE_PLACEHOLDER;
  return `${(frac * 100).toFixed(1).replace(".", ",")}%`;
}

/** Parte de um todo (ambos podem vir redigidos) → fração ou null. */
function shareOf(part: number | null | undefined, whole: number | null | undefined): number | null {
  if (part == null || whole == null || Math.abs(whole) < 0.005) return null;
  return part / whole;
}

function sumOrNull(...values: Array<number | null | undefined>): number | null {
  if (values.every((v) => v == null)) return null;
  return values.reduce<number>((s, v) => s + (v ?? 0), 0);
}

const isProjectedMonth = (m: CompanyResultMonth) => m.indirect_projected || m.debt_projected;

const TOOLTIP_BASE = {
  borderColor: "#e2e8f0",
  textStyle: { color: "#0f172a" },
  confine: true,
} as const;

function tooltipRow(color: string, label: string, value: string, extra?: string): string {
  return `<div style="display:flex;align-items:center;gap:6px;margin-top:3px;min-width:220px">
    <span style="width:8px;height:8px;border-radius:2px;background:${color}"></span>
    <span style="color:#475569">${label}</span>
    <span style="margin-left:auto;font-weight:600;color:#0f172a">${value}</span>
    ${extra ? `<span style="color:#94a3b8;font-size:11px;min-width:44px;text-align:right">${extra}</span>` : ""}
  </div>`;
}

// ---------------------------------------------------------------------------
// Peças visuais locais
// ---------------------------------------------------------------------------

/**
 * Chip de estado dos custos da empresa. REALIZADO (PAGO): "parcial" enquanto o mês de pagamento
 * está em curso. PREVISTO (LANCADO): "projeção" quando as contas ainda não foram geradas.
 */
function CostStateChip({
  basis,
  projected,
  partial,
}: {
  basis: CompanyResultBasis;
  projected: boolean;
  partial: boolean | undefined;
}) {
  if (basis === "PAGO") {
    return partial ? <StatusChip tone="amber" title={COSTS_PARTIAL_TITLE}>parcial</StatusChip> : null;
  }
  return projected ? <StatusChip tone="sky" title={PROJECTED_TITLE}>projeção</StatusChip> : null;
}

/** Chip pequeno de estado (parcial / projeção) com explicação no `title`. */
function StatusChip({
  tone,
  title,
  children,
}: {
  tone: "amber" | "sky" | "emerald";
  title: string;
  children: ReactNode;
}) {
  const cls =
    tone === "amber"
      ? "border-amber-200 bg-amber-50 text-amber-700"
      : tone === "emerald"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
        : "border-sky-200 bg-sky-50 text-sky-700";
  return (
    <span
      title={title}
      className={`inline-flex cursor-help items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${cls}`}
    >
      {children}
    </span>
  );
}

/**
 * Mesmo desenho do `KpiCard` executivo, com linha de apoio e cor do valor
 * (o Resultado da empresa precisa ficar vermelho/verde conforme o sinal).
 */
function ResultKpi({
  label,
  value,
  color,
  hint,
  valueClassName = "text-slate-900",
  chip,
  title,
}: {
  label: string;
  value: string;
  color: string;
  hint?: ReactNode;
  valueClassName?: string;
  chip?: ReactNode;
  /** explicação nativa (hover) do cartão */
  title?: string;
}) {
  return (
    <div title={title} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="h-1 w-full" style={{ backgroundColor: color }} />
      <div className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: color }} />
          <p className="truncate text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
          {chip ? <span className="ml-auto shrink-0">{chip}</span> : null}
        </div>
        <p className={`mt-1 text-2xl font-bold tabular-nums ${valueClassName}`}>{value}</p>
        {hint ? <p className="mt-1 text-[11px] leading-snug text-slate-500">{hint}</p> : null}
      </div>
    </div>
  );
}

function InfoTip({ text }: { text: string }) {
  return (
    <span
      title={text}
      aria-label={text}
      className="inline-flex h-6 w-6 cursor-help items-center justify-center rounded-full border border-slate-300 text-xs font-semibold text-slate-500 hover:bg-slate-50"
    >
      i
    </span>
  );
}

function LegendDot({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-slate-600">
      <span
        aria-hidden
        className="h-2.5 w-2.5 rounded-sm"
        style={dashed ? { border: `1px dashed ${color}` } : { backgroundColor: color }}
      />
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Evolução mensal
// ---------------------------------------------------------------------------

function monthAxisLabels(months: CompanyResultMonth[]): string[] {
  return months.map((m) => `${monthShort(m.competencia)}${isProjectedMonth(m) ? "\n(proj.)" : ""}`);
}

/** Faixas contíguas de meses projetados → markArea do ECharts. */
function projectedAreas(months: CompanyResultMonth[], labels: string[]) {
  const areas: Array<[{ xAxis: string }, { xAxis: string }]> = [];
  let startIdx = -1;
  months.forEach((m, i) => {
    const proj = isProjectedMonth(m);
    if (proj && startIdx < 0) startIdx = i;
    const last = i === months.length - 1;
    if (startIdx >= 0 && (!proj || last)) {
      const endIdx = proj ? i : i - 1;
      areas.push([{ xAxis: labels[startIdx] }, { xAxis: labels[endIdx] }]);
      startIdx = -1;
    }
  });
  return areas;
}

function MonthlyEvolutionChart({ months, height = 320 }: { months: CompanyResultMonth[]; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const labels = monthAxisLabels(months);
    const areas = projectedAreas(months, labels);
    return {
      grid: { top: 40, right: 16, bottom: 44, left: 72 },
      legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { color: "#475569", fontSize: 11 } },
      tooltip: {
        ...TOOLTIP_BASE,
        trigger: "axis",
        formatter: (params: unknown) => {
          const arr = params as Array<{ dataIndex: number }>;
          const m = months[arr[0]?.dataIndex ?? -1];
          if (!m) return "";
          const res = m.company_result;
          let html = `<div style="font-weight:600;color:#0f172a">${monthShort(m.competencia)}${isProjectedMonth(m) ? " · projeção" : ""}</div>`;
          html += tooltipRow(COLORS.revenueMuted, "Receita dos projetos", formatCurrencyOrDash(m.revenue));
          html += tooltipRow(COLORS.available, "Lucro líquido", formatCurrencyOrDash(m.net_profit));
          html += tooltipRow(COLORS.debt, "Dívidas pagas", formatCurrencyOrDash(m.debt_cost));
          html += tooltipRow(res != null && res < 0 ? COLORS.neg : COLORS.pos, "Resultado da empresa", formatCurrencyOrDash(res));
          if (m.anticipation_partial) html += `<div style="color:#b45309;font-size:11px;margin-top:4px">Antecipação parcial</div>`;
          return html;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        axisTick: { show: false },
        axisLabel: { color: "#64748b", fontSize: 11, interval: 0, lineHeight: 13 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: CHART_COLORS.grid, type: "dashed" } },
        axisLabel: { color: "#64748b", fontSize: 11, formatter: (v: number) => formatCurrencyShort(v) },
      },
      series: [
        {
          name: "Receita dos projetos",
          type: "bar",
          barMaxWidth: 26,
          itemStyle: { color: COLORS.revenueMuted, borderRadius: [3, 3, 0, 0] },
          data: months.map((m) => m.revenue),
          markArea: areas.length
            ? {
                silent: true,
                itemStyle: { color: "rgba(148,163,184,0.12)" },
                label: { show: true, position: "insideTop", color: "#94a3b8", fontSize: 10, formatter: "projeção" },
                data: areas,
              }
            : undefined,
        },
        {
          name: "Resultado da empresa",
          type: "bar",
          barMaxWidth: 26,
          itemStyle: { color: COLORS.pos },
          data: months.map((m) => {
            const v = m.company_result;
            const neg = v != null && v < 0;
            const color = neg ? COLORS.neg : COLORS.pos;
            const proj = isProjectedMonth(m);
            return {
              value: v,
              itemStyle: {
                color,
                opacity: proj ? 0.5 : 1,
                borderColor: color,
                borderWidth: proj ? 1 : 0,
                borderType: "dashed" as const,
                borderRadius: neg ? [0, 0, 3, 3] : [3, 3, 0, 0],
              },
            };
          }),
        },
        {
          name: "Lucro líquido",
          type: "line",
          smooth: false,
          symbolSize: 7,
          itemStyle: { color: COLORS.available },
          lineStyle: { width: 2.5, color: COLORS.available },
          data: months.map((m) => ({ value: m.net_profit, symbol: isProjectedMonth(m) ? "emptyCircle" : "circle" })),
        },
        {
          name: "Dívidas pagas",
          type: "line",
          smooth: false,
          symbolSize: 7,
          itemStyle: { color: COLORS.debt },
          lineStyle: { width: 2, color: COLORS.debt, type: "dashed" },
          data: months.map((m) => ({
            value: m.debt_cost,
            symbol: isProjectedMonth(m) ? "emptyCircle" : "circle",
          })),
        },
      ],
    };
  }, [months]);

  return <EChart option={option} height={height} />;
}

// ---------------------------------------------------------------------------
// Custos indiretos
// ---------------------------------------------------------------------------

const TOP_ITEMS = 10;

function IndirectCostsCard({ data }: { data: CompanyResult }) {
  const [showAll, setShowAll] = useState(false);
  const t = data.totals;
  const labor = t.indirect_labor_cost;
  const supplier = t.indirect_supplier_cost;
  const splitTotal = sumOrNull(labor, supplier);
  const laborShare = shareOf(labor, splitTotal);
  const items = showAll ? data.indirect_items : data.indirect_items.slice(0, TOP_ITEMS);
  const hidden = data.indirect_items.length - TOP_ITEMS;
  const basis = basisOf(data);

  return (
    <ChartCard
      className="lg:col-span-2"
      title="Custos indiretos"
      subtitle="Estrutura da empresa no período (menu Custos Indiretos)"
      aside={
        <div className="flex items-center gap-2">
          <CostStateChip basis={basis} projected={t.indirect_projected} partial={t.company_costs_partial} />
          <span className="text-sm font-semibold tabular-nums text-slate-900">{formatCurrencyOrDash(t.indirect_cost)}</span>
        </div>
      }
    >
      <div>
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Mão de obra × fornecedores</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
              <p className="text-[11px] text-slate-500">Mão de obra indireta</p>
              <p className="text-base font-bold tabular-nums text-slate-900">{formatCurrencyShortOrDash(labor)}</p>
              <p className="text-[11px] font-medium tabular-nums text-slate-500">{formatFraction(laborShare)}</p>
            </div>
            <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
              <p className="text-[11px] text-slate-500">Fornecedores e outros</p>
              <p className="text-base font-bold tabular-nums text-slate-900">{formatCurrencyShortOrDash(supplier)}</p>
              <p className="text-[11px] font-medium tabular-nums text-slate-500">{formatFraction(shareOf(supplier, splitTotal))}</p>
            </div>
          </div>
          {laborShare != null ? (
            <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-slate-100" aria-hidden>
              <div style={{ width: `${Math.max(0, Math.min(1, laborShare)) * 100}%`, backgroundColor: COLORS.indirect }} />
              <div className="flex-1" style={{ backgroundColor: "#fdba74" }} />
            </div>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-3">
            <LegendDot color={COLORS.indirect} label="Mão de obra" />
            <LegendDot color="#fdba74" label="Fornecedores" />
          </div>
        </div>
      </div>

      <div className="mt-5">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {showAll ? "Todos os itens" : `Maiores itens (top ${Math.min(TOP_ITEMS, data.indirect_items.length)})`}
        </p>
        {data.indirect_items.length === 0 ? (
          <p className="py-4 text-center text-xs text-slate-400">Nenhum item no período.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="py-1.5 pr-3 font-semibold">Item</th>
                  <th className="py-1.5 pr-3 font-semibold">Categoria</th>
                  <th className="py-1.5 pr-3 text-right font-semibold">Valor</th>
                  <th className="py-1.5 text-right font-semibold">% indiretos</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, idx) => (
                  // Sem permissão de Custos Indiretos os nomes chegam anônimos ("Item restrito"): a chave não pode depender só do nome.
                  <tr key={it.item_id ?? `sem-item:${idx}:${it.name}`} className="border-b border-slate-100 last:border-0">
                    <td className="py-1.5 pr-3 text-slate-800">
                      <span className="inline-flex flex-wrap items-center gap-1.5">
                        {it.name}
                        {it.is_labor ? (
                          <span className="rounded bg-orange-100 px-1.5 py-0.5 text-[10px] font-semibold text-orange-700">
                            Mão de obra
                          </span>
                        ) : null}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3 text-slate-500">{it.category}</td>
                    <td className="py-1.5 pr-3 text-slate-900">
                      <Money value={it.amount} />
                    </td>
                    <td className="py-1.5 text-right tabular-nums text-slate-500">
                      {formatFraction(shareOf(it.amount, t.indirect_cost))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {hidden > 0 ? (
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className="mt-2 text-xs font-medium text-indigo-600 hover:text-indigo-800"
          >
            {showAll ? "Mostrar só os 10 maiores" : `Ver todos (${data.indirect_items.length})`}
          </button>
        ) : null}
      </div>
    </ChartCard>
  );
}

function DebtCard({ data }: { data: CompanyResult }) {
  const t = data.totals;
  const basis = basisOf(data);
  const open = openAmount(basis, t.debt_open_cost);
  return (
    <ChartCard
      title="Dívidas pagas"
      subtitle={
        basis === "PAGO"
          ? `Parcelas pagas${open != null ? ` · ${formatCurrencyOrDash(open)} a pagar` : ""}`
          : "Todas as parcelas lançadas"
      }
      aside={
        <div className="flex items-center gap-2">
          <CostStateChip basis={basis} projected={t.debt_projected} partial={t.company_costs_partial} />
          <span className="text-sm font-semibold tabular-nums text-slate-900">{formatCurrencyOrDash(t.debt_cost)}</span>
        </div>
      }
    >
      {data.debt_items.length === 0 ? (
        <p className="py-6 text-center text-xs text-slate-400">Nenhuma parcela de dívida no período.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[300px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-[11px] uppercase tracking-wide text-slate-500">
                <th className="py-1.5 pr-3 font-semibold">Dívida</th>
                <th className="py-1.5 pr-3 text-right font-semibold">Valor</th>
                <th className="py-1.5 text-right font-semibold">%</th>
              </tr>
            </thead>
            <tbody>
              {data.debt_items.map((d, idx) => (
                <tr key={d.item_id ?? `sem-item:${idx}`} className="border-b border-slate-100 last:border-0">
                  <td className="py-1.5 pr-3 text-slate-800">{d.name}</td>
                  <td className="py-1.5 pr-3 text-slate-900">
                    <Money value={d.amount} />
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-slate-500">{formatFraction(shareOf(d.amount, t.debt_cost))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

const inputCls =
  "rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-800 focus:border-indigo-500 focus:outline-none";

function segmentCls(active: boolean): string {
  return `px-3 py-1.5 text-sm font-medium ${active ? "bg-indigo-600 text-white" : "text-slate-700 hover:bg-slate-50"}`;
}

export function ResultadoEmpresa() {
  const { setWorkspace } = useWorkspace();
  const { globalScenario, setGlobalScenario } = useScenario();
  const canRead = usePermission("company_result.read");

  // Padrão: últimos 6 meses terminando no mês ANTERIOR (o mês corrente ainda está aberto).
  const lastClosed = useMemo(() => monthMinus(currentMonth(), 1), []);
  // Abre no mês atual (Mês único); os presets de últimos N meses seguem terminando no último mês fechado.
  const [mode, setMode] = useState<PeriodMode>("single");
  const [lastN, setLastN] = useState<number>(6);
  const [singleMonth, setSingleMonth] = useState<string>(() => currentMonth());
  const [rangeStart, setRangeStart] = useState<string>(() => monthMinus(lastClosed, 5));
  const [rangeEnd, setRangeEnd] = useState<string>(lastClosed);

  const [data, setData] = useState<CompanyResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const reqId = useRef(0);

  // Filtro de projetos: por padrão só os ATIVOS marcados (= empresa inteira). Desmarcar algum ativo
  // filtra pelos projetos marcados — aí custos indiretos e dívidas zeram (são da empresa).
  const [projects, setProjects] = useState<FilterProject[] | null>(null);
  const [selProjects, setSelProjects] = useState<Set<string>>(new Set());
  useEffect(() => {
    void (async () => {
      try {
        const f = await fetchIndicatorFilters();
        setProjects(f.projects);
        setSelProjects(new Set(f.projects.filter((p) => p.is_active ?? true).map((p) => p.project_id)));
      } catch {
        setProjects([]); // sem acesso às opções: fica a empresa inteira, sem filtro
      }
    })();
  }, []);
  const projectOptions = useMemo(
    () =>
      [...(projects ?? [])]
        .sort(
          (a, b) =>
            Number(!(a.is_active ?? true)) - Number(!(b.is_active ?? true)) ||
            a.project_name.localeCompare(b.project_name, "pt-BR"),
        )
        .map((p) => ({ id: p.project_id, name: (p.is_active ?? true) ? p.project_name : `${p.project_name} (inativo)` })),
    [projects],
  );
  // null = empresa inteira (todos os ativos marcados); lista = só esses projetos.
  const projectFilter = useMemo<string[] | null>(() => {
    if (!projects || projects.length === 0) return null;
    const allActive = projects.filter((p) => p.is_active ?? true).every((p) => selProjects.has(p.project_id));
    return allActive ? null : [...selProjects].sort();
  }, [projects, selProjects]);
  const projectKey = projectFilter ? projectFilter.join(",") : "";
  const noProjectSelected = !!projectFilter && projectFilter.length === 0;
  const toggleProject = useCallback(
    (id: string) =>
      setSelProjects((prev) => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      }),
    [],
  );

  // Linhas do gráfico (mesmas da Evolução Financeira): padrão Faturamento, Custos Diretos e Lucro Líquido.
  const { selectedSeries, applySelection } = useFinancialChartViz(COMPANY_SERIES_IDS, DEFAULT_SERIES_VISIBILITY);

  useEffect(() => {
    setWorkspace("indicators");
  }, [setWorkspace]);

  const [startMonth, endMonth] = useMemo<[string, string]>(() => {
    if (mode === "single") return [singleMonth, singleMonth];
    if (mode === "range") return rangeStart <= rangeEnd ? [rangeStart, rangeEnd] : [rangeEnd, rangeStart];
    return [monthMinus(lastClosed, lastN - 1), lastClosed];
  }, [mode, singleMonth, rangeStart, rangeEnd, lastN, lastClosed]);

  const di = monthToCompetencia(startMonth);
  const df = monthToCompetencia(endMonth);

  const load = useCallback(async () => {
    if (!canRead || projects === null) {
      setLoading(!canRead ? false : true);
      return;
    }
    if (noProjectSelected) {
      reqId.current++;
      setData(null);
      setLoading(false);
      return;
    }
    const myId = ++reqId.current;
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchCompanyResult({
        data_inicial: di,
        data_final: df,
        scenario: globalScenario,
        project_ids: projectKey ? projectKey.split(",") : undefined,
      });
      if (myId !== reqId.current) return;
      setData(payload);
    } catch (e) {
      if (myId !== reqId.current) return;
      const detail = isAxiosError(e) ? e.response?.data?.detail ?? e.message : null;
      setError(
        typeof detail === "string" && detail
          ? `Não foi possível carregar o Resultado da Empresa: ${detail}`
          : "Não foi possível carregar o Resultado da Empresa.",
      );
      setData(null);
    } finally {
      if (myId === reqId.current) setLoading(false);
    }
  }, [canRead, di, df, globalScenario, projects, projectKey, noProjectSelected]);

  useEffect(() => {
    void load();
  }, [load]);

  const periodLabel =
    startMonth === endMonth ? monthShort(startMonth) : `${monthShort(startMonth)} – ${monthShort(endMonth)}`;

  const t = data?.totals ?? null;
  const redacted = !!data && t?.revenue == null;
  const hasData =
    !!data &&
    data.months.length > 0 &&
    [t?.revenue, t?.indirect_cost, t?.debt_cost, t?.direct_cost].some((v) => v != null && Math.abs(v) > 0.005);

  const projectedCount = data ? data.months.filter(isProjectedMonth).length : 0;
  const basis: CompanyResultBasis = data ? basisOf(data) : globalScenario === "PREVISTO" ? "LANCADO" : "PAGO";

  if (!canRead) {
    return <p className="text-slate-600">Sem permissão para acessar o Resultado da Empresa.</p>;
  }

  const result = t?.company_result ?? null;
  const resultClass = result == null ? "text-slate-900" : result < 0 ? "text-rose-600" : "text-emerald-600";
  const projectedChip =
    t && (t.indirect_projected || t.debt_projected) ? (
      <StatusChip tone="sky" title={PROJECTED_TITLE}>projeção</StatusChip>
    ) : null;

  return (
    <div className="space-y-4">
      <DashboardHeader
        title="Resultado da Empresa"
        subtitle={`Período ${periodLabel}`}
        description="Quanto entra pelos projetos e quanto a empresa realmente precisa pagar"
        badge="Relatório Executivo · Confidencial"
        actions={<InfoTip text={HELP_TEXT} />}
      />

      <DashboardFilterBar>
        <FilterField label="Período">
          <div className="inline-flex overflow-hidden rounded-lg border border-slate-300">
            {(
              [
                ["single", "Mês único"],
                ["range", "Intervalo"],
                ["last", "Últimos N meses"],
              ] as [PeriodMode, string][]
            ).map(([m, label]) => (
              <button key={m} type="button" onClick={() => setMode(m)} className={segmentCls(mode === m)}>
                {label}
              </button>
            ))}
          </div>
        </FilterField>

        {mode === "single" ? (
          <FilterField label="Mês">
            <input
              type="month"
              value={singleMonth}
              onChange={(e) => setSingleMonth(e.target.value || singleMonth)}
              className={inputCls}
            />
          </FilterField>
        ) : null}

        {mode === "range" ? (
          <>
            <FilterField label="Data inicial">
              <input
                type="month"
                value={rangeStart}
                onChange={(e) => setRangeStart(e.target.value || rangeStart)}
                className={inputCls}
              />
            </FilterField>
            <FilterField label="Data final">
              <input
                type="month"
                value={rangeEnd}
                onChange={(e) => setRangeEnd(e.target.value || rangeEnd)}
                className={inputCls}
              />
            </FilterField>
          </>
        ) : null}

        {mode === "last" ? (
          <FilterField label={`Até ${monthShort(lastClosed)}`}>
            <div className="inline-flex flex-wrap gap-1">
              {[3, 6, 12].map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setLastN(n)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${
                    lastN === n ? "border-indigo-600 bg-indigo-600 text-white" : "border-slate-300 text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  {n} meses
                </button>
              ))}
            </div>
          </FilterField>
        ) : null}

        {projectOptions.length > 0 ? (
          <FilterField label="Projeto">
            <ProjectFilterDropdown
              options={projectOptions}
              selected={selProjects}
              onToggle={toggleProject}
              emptyText="Nenhum projeto"
              noOptionsText="Nenhum projeto cadastrado."
            />
          </FilterField>
        ) : null}

        <FilterField label="Cenário">
          <div className="inline-flex overflow-hidden rounded-lg border border-slate-300">
            {(["REALIZADO", "PREVISTO"] as ScenarioKind[]).map((s) => (
              <button
                key={s}
                type="button"
                title={SCENARIO_TITLE[s]}
                onClick={() => setGlobalScenario(s)}
                className={segmentCls(globalScenario === s)}
              >
                {s === "REALIZADO" ? "Realizado" : "Previsto"}
              </button>
            ))}
          </div>
        </FilterField>
      </DashboardFilterBar>
      <p className="-mt-2 px-1 text-xs text-slate-500">
        {SCENARIO_CAPTION[globalScenario]}
        {projectFilter ? " " + PROJECT_FILTER_CAPTION : ""}
      </p>

      {error ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
      ) : loading && !data ? (
        <p className="text-sm text-slate-500">Carregando…</p>
      ) : redacted ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-10 text-center text-sm text-amber-800">
          Valores ocultos: sem permissão para dados sensíveis
        </div>
      ) : noProjectSelected ? (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">
          Selecione ao menos um projeto.
        </div>
      ) : !hasData || !data || !t ? (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">
          Não há dados financeiros para o período selecionado.
        </div>
      ) : (
        <div className={`space-y-4 transition-opacity ${loading ? "opacity-60" : ""}`}>
          {/* KPIs — linha 1: a receita e o que sai dela até o lucro líquido (ordem da cascata) */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <ResultKpi
              label="Receita dos projetos"
              value={formatCurrencyOrDash(t.revenue)}
              color={COLORS.revenue}
              hint={`${data.month_count} ${data.month_count === 1 ? "mês" : "meses"} · ${periodLabel}`}
            />
            <ResultKpi
              label="Antecipação"
              value={formatCurrencyOrDash(t.anticipation_amount)}
              color={COLORS.projectCost}
              title={HELP_ANTICIPATION}
              chip={t.anticipation_partial ? <StatusChip tone="amber" title={PARTIAL_TITLE}>parcial</StatusChip> : null}
              hint={`${formatFraction(t.anticipation_rate ?? shareOf(t.anticipation_amount, t.revenue))} da receita`}
            />
            <ResultKpi
              label="Custos diretos"
              value={formatCurrencyOrDash(t.direct_cost)}
              color={COLORS.projectCost}
              chip={<CostStateChip basis={basis} projected={t.indirect_projected} partial={t.company_costs_partial} />}
              hint={`${formatFraction(shareOf(t.direct_cost, t.revenue))} da receita`}
            />
            <ResultKpi
              label="Custos indiretos"
              value={formatCurrencyOrDash(t.indirect_cost)}
              color={COLORS.indirect}
              chip={<CostStateChip basis={basis} projected={t.indirect_projected} partial={t.company_costs_partial} />}
              hint={`${formatFraction(shareOf(t.indirect_cost, t.revenue))} da receita`}
            />
            <ResultKpi
              label="Impostos"
              value={formatCurrencyOrDash(sumOrNull(t.tax_amount, t.profit_tax_amount))}
              color={COLORS.projectCost}
              title={HELP_TAXES}
              hint={`${formatFraction(shareOf(sumOrNull(t.tax_amount, t.profit_tax_amount), t.revenue))} da receita · ${taxRegimeName(t.tax_regime)}`}
            />
          </div>

          {/* KPIs — linha 2: lucro líquido, retenção, dívidas e a resposta (ordem da cascata) */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <ResultKpi
              label="Lucro líquido"
              value={formatCurrencyOrDash(t.net_profit ?? null)}
              color={t.net_profit != null && t.net_profit < 0 ? COLORS.neg : COLORS.available}
              hint={`${formatFraction(shareOf(t.net_profit, t.revenue))} da receita · Receita − antecipação − custos diretos − custos indiretos − impostos`}
            />
            <ResultKpi
              label="Retenção"
              value={formatCurrencyOrDash(t.retention)}
              color={COLORS.projectCost}
              title={HELP_RETENTION}
              hint={`${formatFraction(shareOf(t.retention, t.revenue))} da receita`}
            />
            <ResultKpi
              label="Dívidas pagas"
              value={formatCurrencyOrDash(t.debt_cost)}
              color={COLORS.debt}
              title={HELP_DEBTS}
              chip={<CostStateChip basis={basis} projected={t.debt_projected} partial={t.company_costs_partial} />}
              hint={`${formatFraction(shareOf(t.debt_cost, t.revenue))} da receita`}
            />
            <ResultKpi
              label="Resultado da empresa"
              value={formatCurrencyOrDash(result)}
              color={result != null && result < 0 ? COLORS.neg : COLORS.pos}
              valueClassName={resultClass}
              chip={projectedChip}
              hint={`${formatFraction(shareOf(result, t.revenue))} da receita · Lucro líquido − retenção − dívidas pagas`}
            />
          </div>

          {/* Evolução do resultado — uma linha por card (largura total) */}
          <div className="grid grid-cols-1 gap-4">
            <ChartCard
              title="Evolução do resultado"
              subtitle={
                basis === "PAGO"
                  ? `Uma linha por card · ${periodLabel}`
                  : `Uma linha por card — todas as contas lançadas · ${periodLabel}`
              }
              aside={
                <div className="flex flex-wrap items-center gap-1.5">
                  {basis === "PAGO" && t.company_costs_partial ? (
                    <StatusChip tone="amber" title={COSTS_PARTIAL_TITLE}>Pagamentos em curso</StatusChip>
                  ) : null}
                  {t.anticipation_partial ? (
                    <StatusChip tone="amber" title={PARTIAL_TITLE}>Antecipação parcial</StatusChip>
                  ) : null}
                  {t.indirect_projected || t.debt_projected ? (
                    <StatusChip tone="sky" title={PROJECTED_TITLE}>
                      {t.indirect_projected && t.debt_projected
                        ? "Indiretos e dívidas em projeção"
                        : t.indirect_projected
                          ? "Indiretos em projeção"
                          : "Dívidas em projeção"}
                    </StatusChip>
                  ) : null}
                </div>
              }
            >
              <FinancialEvolutionMainChart
                points={companySeriesPoints(data.months)}
                seriesCatalog={COMPANY_SERIES}
                showAllValues={false}
                selectedSeries={selectedSeries}
                onSelectedSeriesChange={applySelection}
                height={520}
              />
            </ChartCard>
          </div>

          {/* Custos indiretos (2/3) + Dívidas pagas (1/3) */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <IndirectCostsCard data={data} />
            <DebtCard data={data} />
          </div>

          {/* Evolução mensal (largura total, por último) */}
          <div className="grid grid-cols-1 gap-4">
            <ChartCard
              title="Evolução mensal"
              subtitle="Receita, lucro disponível, custos da empresa e resultado"
              aside={projectedCount > 0 ? <StatusChip tone="sky" title={PROJECTED_TITLE}>(proj.) = projeção</StatusChip> : null}
            >
              <MonthlyEvolutionChart months={data.months} />
            </ChartCard>
          </div>
        </div>
      )}
    </div>
  );
}
