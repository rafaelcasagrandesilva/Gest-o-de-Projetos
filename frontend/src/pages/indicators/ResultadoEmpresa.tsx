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
  anticipationInstitutions,
  taxBreakdownLines,
  taxRegimeName,
} from "@/utils/projectCostBasis";
import { DashboardHeader } from "@/components/dashboard/executive/DashboardHeader";
import { DashboardFilterBar, FilterField } from "@/components/dashboard/executive/DashboardFilterBar";
import { ChartCard } from "@/components/dashboard/executive/ChartCard";
import { EChart } from "@/components/dashboard/executive/EChart";
import { Money } from "@/components/Money";

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
  "Retenção: 10% retidos pelo cliente, devolvidos no fim do contrato — não disponível para pagar contas.";
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
const HELP_TEXT = [HELP_SCENARIO, HELP_PROJECTION, HELP_ANTICIPATION, HELP_RETENTION, HELP_TAXES, HELP_FLEET, HELP_PROJECT_CAP].join("\n");

const SCENARIO_TITLE: Record<ScenarioKind, string> = {
  REALIZADO:
    "O que já aconteceu: receita lançada, impostos devidos, antecipações realizadas e contas efetivamente pagas.",
  PREVISTO:
    "Simulação do mês se todas as contas lançadas forem pagas (estimativa quando as contas ainda não foram lançadas).",
};
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

const PROFIT_TAX_TITLE =
  "IRPJ/CSLL do Lucro Real sobre o lucro da empresa (lucro operacional − custos indiretos); zero quando há prejuízo.";

/** A cascata ganha o degrau "IRPJ/CSLL (Lucro Real)" quando há valor ou o período tem Lucro Real. */
function showsProfitTax(t: CompanyResultMonth): boolean {
  return (t.profit_tax_amount ?? 0) > 0.005 || t.tax_regime === "LUCRO_REAL" || t.tax_regime === "MISTO";
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

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);
}

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
// Cascata do resultado (waterfall)
// ---------------------------------------------------------------------------

type WfKind = "start" | "delta" | "subtotal";

interface WfStep {
  /** rótulo do eixo (pode ter quebra de linha) */
  axis: string;
  /** rótulo do tooltip */
  label: string;
  kind: WfKind;
  start: number;
  end: number;
  /** valor original do contrato (dedução positiva = sai dinheiro); null = redigido */
  raw: number | null;
  color: string;
  note?: "partial" | "projected";
  /** linhas extras do tooltip */
  detail?: string[];
}

function buildWaterfall(t: CompanyResultMonth, basis: CompanyResultBasis): WfStep[] {
  const steps: WfStep[] = [];
  let running = 0;

  const start = (axis: string, label: string, v: number | null, color: string) => {
    running = v ?? 0;
    steps.push({ axis, label, kind: "start", start: 0, end: running, raw: v, color });
  };
  const deduct = (axis: string, label: string, v: number | null, color: string, extra?: Partial<WfStep>) => {
    const s = running;
    running = s - (v ?? 0);
    steps.push({ axis, label, kind: "delta", start: s, end: running, raw: v, color, ...extra });
  };
  // Subtotal usa o valor do backend (fonte da verdade); cai no acumulado só se vier redigido.
  const subtotal = (axis: string, label: string, v: number | null, posColor: string) => {
    running = v ?? running;
    steps.push({ axis, label, kind: "subtotal", start: 0, end: running, raw: v, color: running < 0 ? COLORS.neg : posColor });
  };

  const openLine = (v: number | null | undefined) => {
    const open = openAmount(basis, v);
    return open == null ? [] : [`${formatCurrencyOrDash(open)} a pagar (lançado, ainda não pago — fora do resultado)`];
  };

  start("Receita", "Receita dos projetos", t.revenue, COLORS.revenue);
  deduct("Custos\ndiretos", "Custos diretos", t.direct_cost, COLORS.projectCost, {
    detail: [
      `Mão de obra: ${formatCurrencyOrDash(t.labor_cost)}`,
      `Veículos: ${formatCurrencyOrDash(t.vehicle_cost)}`,
      `Sistemas: ${formatCurrencyOrDash(t.system_cost)}`,
      `Custos fixos operacionais: ${formatCurrencyOrDash(t.fixed_operational_cost)}`,
      ...openLine(t.direct_open_cost),
    ],
  });
  deduct("Impostos", `Impostos — ${taxRegimeName(t.tax_regime)}`, t.tax_amount, COLORS.projectCost, {
    detail: [`Taxa efetiva sobre a receita: ${formatFraction(t.tax_rate)}`, ...taxBreakdownLines(t)],
  });
  deduct("Antecipação", "Antecipação", t.anticipation_amount, COLORS.projectCost, {
    note: t.anticipation_partial ? "partial" : undefined,
    detail: [
      `Taxa sobre a receita: ${formatFraction(t.anticipation_rate)}`,
      ...anticipationInstitutions(t.anticipation_by_institution).map(
        ([name, v]) =>
          `${name}: ${formatCurrencyOrDash(v)} (${formatFraction(shareOf(v, t.anticipation_amount))} da antecipação)`,
      ),
    ],
  });
  subtotal("Lucro\noperacional", "Lucro operacional", t.operational_profit, COLORS.pos);
  deduct("Retenção\n10%", "Retenção 10%", t.retention, COLORS.projectCost);
  subtotal("Lucro\ndisponível", "Lucro disponível", t.available_profit, COLORS.available);
  deduct("Custos\nindiretos", "Custos indiretos", t.indirect_cost, COLORS.indirect, {
    note: t.indirect_projected ? "projected" : undefined,
    detail: openLine(t.indirect_open_cost),
  });
  if (showsProfitTax(t)) {
    deduct("IRPJ/CSLL\n(Lucro Real)", "IRPJ/CSLL (Lucro Real)", t.profit_tax_amount ?? null, COLORS.indirect, {
      detail: [PROFIT_TAX_TITLE],
    });
  }
  deduct("Dívidas\npagas", "Dívidas pagas", t.debt_cost, COLORS.debt, {
    note: t.debt_projected ? "projected" : undefined,
    detail: openLine(t.debt_open_cost),
  });
  subtotal("Resultado\nda empresa", "Resultado da empresa", t.company_result, COLORS.pos);
  return steps;
}

/**
 * Limites do eixo Y com folga para o rótulo de valor. Sem ela, uma barra que termina rente ao limite
 * do eixo (ex.: resultado negativo de −196 mil com eixo em −200 mil) desenha o rótulo fora da área do
 * gráfico — por cima do nome da barra, e pior quanto menor a tela. A folga é proporcional à amplitude
 * (não arredondada para passos grandes, que achatariam as barras); as linhas continuam em valores
 * redondos escolhidos pelo ECharts e os rótulos quebrados das bordas ficam ocultos.
 */
function waterfallAxisBounds(steps: WfStep[]): { min: number; max: number } {
  const values = steps.flatMap((s) => [s.start, s.end]);
  const lo = Math.min(0, ...values);
  const hi = Math.max(0, ...values);
  const range = hi - lo || 1;
  return {
    min: lo < 0 ? lo - range * 0.09 : 0,
    max: hi + range * 0.07,
  };
}

function WaterfallChart({
  totals,
  basis,
  height = 380,
}: {
  totals: CompanyResultMonth;
  basis: CompanyResultBasis;
  height?: number;
}) {
  const option = useMemo<EChartsOption>(() => {
    const steps = buildWaterfall(totals, basis);
    const revenue = totals.revenue;

    const deltaText = (s: WfStep, short: boolean) => {
      if (s.raw == null) return SENSITIVE_PLACEHOLDER;
      const fmt = short ? formatCurrencyShort : (n: number) => formatCurrencyOrDash(n);
      if (s.kind !== "delta") return fmt(s.raw);
      return s.raw >= 0 ? `−${fmt(s.raw)}` : `+${fmt(-s.raw)}`;
    };

    const bounds = waterfallAxisBounds(steps);

    return {
      // containLabel: a margem esquerda acompanha a largura real dos valores do eixo em qualquer tela.
      grid: { top: 28, right: 16, bottom: 12, left: 8, containLabel: true },
      tooltip: {
        ...TOOLTIP_BASE,
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params: unknown) => {
          const arr = params as Array<{ dataIndex: number }>;
          const s = steps[arr[0]?.dataIndex ?? -1];
          if (!s) return "";
          const share = s.raw == null ? null : shareOf(s.kind === "delta" ? s.raw : s.end, revenue);
          let html = `<div style="font-weight:600;color:#0f172a">${escapeHtml(s.label)}</div>`;
          html += tooltipRow(s.color, s.kind === "delta" ? "Valor" : "Total", deltaText(s, false));
          html += tooltipRow("transparent", "% da receita", formatFraction(share));
          for (const d of s.detail ?? []) {
            html += `<div style="color:#64748b;font-size:11px;margin-top:2px">${escapeHtml(d)}</div>`;
          }
          if (s.note === "partial") html += `<div style="color:#b45309;font-size:11px;margin-top:4px;max-width:260px;white-space:normal">${escapeHtml(PARTIAL_TITLE)}</div>`;
          if (s.note === "projected") html += `<div style="color:#0369a1;font-size:11px;margin-top:4px;max-width:260px;white-space:normal">${escapeHtml(PROJECTED_TITLE)}</div>`;
          return html;
        },
      },
      xAxis: {
        type: "category",
        data: steps.map((s) => s.axis),
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        axisTick: { show: false },
        axisLabel: {
          color: "#475569",
          fontSize: 11,
          interval: 0,
          lineHeight: 14,
          formatter: (value: string, idx: number) => {
            const note = steps[idx]?.note;
            if (note === "partial") return `${value}\n{partial|parcial}`;
            if (note === "projected") return `${value}\n{projected|projeção}`;
            return value;
          },
          rich: {
            partial: { backgroundColor: "#fef3c7", color: "#b45309", borderRadius: 3, padding: [1, 4], fontSize: 9, fontWeight: "bold" },
            projected: { backgroundColor: "#e0f2fe", color: "#0369a1", borderRadius: 3, padding: [1, 4], fontSize: 9, fontWeight: "bold" },
          },
        },
      },
      yAxis: {
        type: "value",
        min: bounds.min,
        max: bounds.max,
        splitLine: { lineStyle: { color: CHART_COLORS.grid, type: "dashed" } },
        axisLabel: {
          color: "#64748b",
          fontSize: 11,
          // As bordas do eixo são a folga (valor quebrado): só as linhas redondas levam rótulo.
          showMinLabel: false,
          showMaxLabel: false,
          formatter: (v: number) => formatCurrencyShort(v),
        },
      },
      series: [
        // Série auxiliar transparente: empurra a barra visível até o início da dedução.
        // `stackStrategy: "all"` empilha somando valores de qualquer sinal — é o que permite
        // uma dedução cruzar o zero (base negativa + altura positiva).
        {
          name: "base",
          type: "bar",
          stack: "wf",
          stackStrategy: "all",
          silent: true,
          itemStyle: { color: "transparent" },
          emphasis: { disabled: true },
          data: steps.map((s) => (s.kind === "delta" ? Math.min(s.start, s.end) : 0)),
        },
        {
          name: "valor",
          type: "bar",
          stack: "wf",
          stackStrategy: "all",
          barMaxWidth: 58,
          data: steps.map((s) => {
            const value = s.kind === "delta" ? Math.abs(s.end - s.start) : s.end;
            const negTotal = s.kind !== "delta" && s.end < 0;
            return {
              value,
              itemStyle: { color: s.color, borderRadius: negTotal ? [0, 0, 3, 3] : [3, 3, 0, 0] },
              label: { position: negTotal ? ("bottom" as const) : ("top" as const) },
            };
          }),
          label: {
            show: true,
            distance: 5,
            fontSize: 10,
            fontWeight: "bold",
            color: "#475569",
            formatter: (p: { dataIndex?: number }) => {
              const s = steps[p.dataIndex ?? -1];
              return s ? deltaText(s, true) : "";
            },
          },
          labelLayout: { hideOverlap: true },
          markLine: {
            silent: true,
            symbol: "none",
            label: { show: false },
            lineStyle: { color: CHART_COLORS.zeroLine, width: 1, type: "solid", opacity: 0.35 },
            data: [{ yAxis: 0 }],
          },
        },
      ],
    };
  }, [totals, basis]);

  return <EChart option={option} height={height} />;
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
          html += tooltipRow(COLORS.available, "Lucro disponível", formatCurrencyOrDash(m.available_profit));
          html += tooltipRow(COLORS.companyCosts, "Indiretos + dívidas pagas", formatCurrencyOrDash(sumOrNull(m.indirect_cost, m.debt_cost)));
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
          name: "Lucro disponível",
          type: "line",
          smooth: false,
          symbolSize: 7,
          itemStyle: { color: COLORS.available },
          lineStyle: { width: 2.5, color: COLORS.available },
          data: months.map((m) => ({ value: m.available_profit, symbol: isProjectedMonth(m) ? "emptyCircle" : "circle" })),
        },
        {
          name: "Indiretos + dívidas pagas",
          type: "line",
          smooth: false,
          symbolSize: 7,
          itemStyle: { color: COLORS.companyCosts },
          lineStyle: { width: 2, color: COLORS.companyCosts, type: "dashed" },
          data: months.map((m) => ({
            value: sumOrNull(m.indirect_cost, m.debt_cost),
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
              <p className="text-[11px] font-medium text-slate-500">{formatFraction(laborShare)}</p>
            </div>
            <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
              <p className="text-[11px] text-slate-500">Fornecedores e outros</p>
              <p className="text-base font-bold tabular-nums text-slate-900">{formatCurrencyShortOrDash(supplier)}</p>
              <p className="text-[11px] font-medium text-slate-500">{formatFraction(shareOf(supplier, splitTotal))}</p>
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
    if (!canRead) {
      setLoading(false);
      return;
    }
    const myId = ++reqId.current;
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchCompanyResult({ data_inicial: di, data_final: df, scenario: globalScenario });
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
  }, [canRead, di, df, globalScenario]);

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
      <p className="-mt-2 px-1 text-xs text-slate-500">{SCENARIO_CAPTION[globalScenario]}</p>

      {error ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
      ) : loading && !data ? (
        <p className="text-sm text-slate-500">Carregando…</p>
      ) : redacted ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-10 text-center text-sm text-amber-800">
          Valores ocultos: sem permissão para dados sensíveis
        </div>
      ) : !hasData || !data || !t ? (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">
          Não há dados financeiros para o período selecionado.
        </div>
      ) : (
        <div className={`space-y-4 transition-opacity ${loading ? "opacity-60" : ""}`}>
          {/* KPIs — linha 1: o que entra e o que a empresa paga */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <ResultKpi
              label="Receita dos projetos"
              value={formatCurrencyOrDash(t.revenue)}
              color={COLORS.revenue}
              hint={`${data.month_count} ${data.month_count === 1 ? "mês" : "meses"} · ${periodLabel}`}
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
              label="Retenção"
              value={formatCurrencyOrDash(t.retention)}
              color={COLORS.projectCost}
              title={HELP_RETENTION}
              hint={`${formatFraction(shareOf(t.retention, t.revenue))} da receita`}
            />
          </div>

          {/* KPIs — linha 2: impostos, antecipação, dívidas e a resposta */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <ResultKpi
              label="Impostos"
              value={formatCurrencyOrDash(t.tax_amount)}
              color={COLORS.projectCost}
              title={HELP_TAXES}
              hint={`${formatFraction(t.tax_rate ?? shareOf(t.tax_amount, t.revenue))} da receita · ${taxRegimeName(t.tax_regime)}`}
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
              label="Dívidas pagas"
              value={formatCurrencyOrDash(t.debt_cost)}
              color={COLORS.debt}
              chip={<CostStateChip basis={basis} projected={t.debt_projected} partial={t.company_costs_partial} />}
              hint={`${formatFraction(shareOf(t.debt_cost, t.revenue))} da receita`}
            />
            <ResultKpi
              label="Resultado da empresa"
              value={formatCurrencyOrDash(result)}
              color={result != null && result < 0 ? COLORS.neg : COLORS.pos}
              valueClassName={resultClass}
              chip={projectedChip}
              hint={`${formatFraction(shareOf(result, t.revenue))} da receita · ${
                showsProfitTax(t)
                  ? "Lucro disponível − custos indiretos − IRPJ/CSLL (Lucro Real) − dívidas pagas"
                  : "Lucro disponível − custos indiretos − dívidas pagas"
              }`}
            />
          </div>

          {/* Cascata do resultado (largura total) */}
          <div className="grid grid-cols-1 gap-4">
            <ChartCard
              title="Cascata do resultado"
              subtitle={
                basis === "PAGO"
                  ? `Da receita ao resultado · ${periodLabel}`
                  : `Da receita ao resultado — todas as contas lançadas · ${periodLabel}`
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
              <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1">
                <LegendDot color={COLORS.revenue} label="Receita" />
                <LegendDot color={COLORS.projectCost} label="Deduções dos projetos" />
                <LegendDot color={COLORS.pos} label="Subtotal" />
                <LegendDot color={COLORS.indirect} label="Custos indiretos" />
                <LegendDot color={COLORS.debt} label="Dívidas pagas" />
              </div>
              <div className="overflow-x-auto">
                {/* Mínimo só para telas muito estreitas (celular); em notebook e monitor o gráfico acompanha a largura. */}
                <div className={showsProfitTax(t) ? "min-w-[600px]" : "min-w-[540px]"}>
                  <WaterfallChart totals={t} basis={basis} />
                </div>
              </div>
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
