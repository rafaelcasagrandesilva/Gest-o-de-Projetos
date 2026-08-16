import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { EChartsOption } from "echarts";
import { DashboardHeader } from "@/components/dashboard/executive/DashboardHeader";
import { DashboardFilterBar, FilterField } from "@/components/dashboard/executive/DashboardFilterBar";
import { ChartCard } from "@/components/dashboard/executive/ChartCard";
import { EChart } from "@/components/dashboard/executive/EChart";
import { KpiCard } from "@/components/dashboard/executive/KpiCard";
import { useWorkspace } from "@/context/WorkspaceContext";
import { formatApiError } from "@/utils/apiError";
import { formatCurrencyOrDash, formatCurrencyShort } from "@/utils/currency";
import {
  LEGAL_STATUS_LABELS,
  fetchLegalOverview,
  type LegalBucket,
  type LegalCaseFilters,
  type LegalCaseStatus,
  type LegalOverview,
} from "@/services/legal";

/**
 * Dashboard Jurídico — visão EXECUTIVA (não operacional).
 *
 * Reusa o framework de Dashboards Executivos do SGC (DashboardHeader / FilterBar / ChartCard /
 * KpiCard / ECharts), então a identidade visual é a mesma do Financeiro e dos Indicadores.
 *
 * Um único indicador financeiro: **Passivo (valor considerado)**. O "valor da causa" soma o mesmo
 * passivo duas vezes quando dois processos espelham a mesma origem (10 processos, R$ 278.038,65 na
 * base atual) — por isso ele fica só nas telas analíticas, onde há contexto processo a processo.
 * Ver o cabeçalho da tela de Processos para a comparação completa.
 *
 * Cards e gráficos consomem o MESMO endpoint com os MESMOS filtros da tela de Processos
 * (`/legal/cases/overview`), então não há como divergirem. Clicar numa barra aplica o filtro.
 */

/** Cores do módulo (alinhadas ao semáforo de status usado na tela de Processos). */
const COLOR = {
  andamento: "#d97706",
  acordo: "#7c3aed",
  encerrado: "#059669",
  passivo: "#3a4ca8",
  bar: "#4f46e5",
} as const;

/** Cor por status — compartilhada pelo gráfico e pela legenda clicável. */
const STATUS_COLOR: Record<string, string> = {
  EM_ANDAMENTO: "#d97706",
  COM_DECISAO: "#e11d48",
  ACORDO: "#7c3aed",
  ACORDO_FINALIZADO: "#0d9488",
  SUSPENSO: "#0284c7",
  ENCERRADO: "#059669",
  SEM_PROCESSO: "#94a3b8",
};

/** Status considerados "acordo ativo" (acordado, ainda em execução) e "encerrado". */
const ACORDO_STATUSES: LegalCaseStatus[] = ["ACORDO", "ACORDO_FINALIZADO"];
const ENCERRADO_STATUSES: LegalCaseStatus[] = ["ENCERRADO"];

const TYPING_DEBOUNCE_MS = 350;

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

function countOf(buckets: LegalBucket[], keys: string[]): number {
  return buckets.filter((b) => keys.includes(b.key)).reduce((sum, b) => sum + b.count, 0);
}

/**
 * Gráfico de barras horizontais clicável. Rótulos longos (projeto/empresa) são truncados no eixo
 * e completos no tooltip. Sem `legal.sensitive` os valores vêm nulos: a barra passa a representar
 * a QUANTIDADE, e o eixo muda de rótulo — o gráfico continua legível em vez de ficar vazio.
 */
function BarChart({
  buckets,
  onPick,
  selected,
  color = COLOR.bar,
  height = 260,
}: {
  buckets: LegalBucket[];
  onPick: (key: string) => void;
  selected: string[];
  color?: string;
  height?: number;
}) {
  const redacted = buckets.length > 0 && buckets.every((b) => b.value == null);
  // ECharts desenha de baixo para cima: inverte para o maior ficar no topo.
  const rows = [...buckets].reverse();
  const labels = rows.map((b) => b.label);
  const values = rows.map((b) => (redacted ? b.count : (b.value ?? 0)));

  const option: EChartsOption = {
    // Sem animação de entrada: as barras pintam no primeiro frame. Além de ser a leitura certa
    // para um painel executivo (o número importa, não o efeito), evita depender de
    // requestAnimationFrame — que não roda em aba oculta/projetor adormecido e deixaria o
    // gráfico vazio bem na hora da apresentação.
    animation: false,
    grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const list = params as { dataIndex: number }[];
        const row = rows[list?.[0]?.dataIndex ?? 0];
        if (!row) return "";
        const money = redacted ? "—" : formatCurrencyOrDash(row.value);
        return `<strong>${row.label}</strong><br/>Passivo: ${money}<br/>Processos: ${row.count}`;
      },
    },
    xAxis: {
      type: "value",
      axisLabel: {
        color: "#94a3b8",
        formatter: (v: number) => (redacted ? String(v) : formatCurrencyShort(v)),
      },
      splitLine: { lineStyle: { color: "#eef2f7" } },
    },
    yAxis: {
      type: "category",
      data: labels,
      axisLabel: {
        color: "#475569",
        width: 130,
        overflow: "truncate",
        formatter: (v: string) => v,
      },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#e2e8f0" } },
    },
    series: [
      {
        type: "bar",
        data: values.map((v, i) => ({
          value: v,
          itemStyle: {
            color,
            // Barra do filtro ativo fica sólida; as demais esmaecem.
            opacity: selected.length === 0 || selected.includes(rows[i].key) ? 1 : 0.35,
            borderRadius: [0, 4, 4, 0],
          },
        })),
        barMaxWidth: 22,
        label: {
          show: true,
          position: "right",
          color: "#334155",
          fontSize: 11,
          formatter: (p: { dataIndex: number }) => {
            const row = rows[p.dataIndex];
            return redacted ? `${row.count}` : formatCurrencyShort(row.value ?? 0);
          },
        },
      },
    ],
  };

  return (
    <EChart
      option={option}
      height={height}
      onEvents={{
        click: (params: unknown) => {
          const p = params as { dataIndex?: number };
          const row = typeof p?.dataIndex === "number" ? rows[p.dataIndex] : undefined;
          if (row) onPick(row.key);
        },
      }}
    />
  );
}

export function LegalDashboard() {
  const { setWorkspace } = useWorkspace();
  const navigate = useNavigate();

  useEffect(() => {
    setWorkspace("legal");
  }, [setWorkspace]);

  const [statuses, setStatuses] = useState<string[]>([]);
  const [ufs, setUfs] = useState<string[]>([]);
  const [companies, setCompanies] = useState<string[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  const [overview, setOverview] = useState<LegalOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const id = setTimeout(() => setSearch(searchInput), TYPING_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [searchInput]);

  const filters = useMemo<LegalCaseFilters>(
    () => ({
      status: statuses,
      uf: ufs,
      company: companies,
      project: projects,
      q: search,
      basis: "considered",
    }),
    [statuses, ufs, companies, projects, search],
  );

  const seq = useRef(0);
  const load = useCallback(async () => {
    const mine = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLegalOverview(filters);
      if (mine !== seq.current) return;
      setOverview(data);
    } catch (e) {
      if (mine !== seq.current) return;
      setError(formatApiError(e));
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  const kpis = overview?.kpis;
  const facets = overview?.facets;
  const byStatus = overview?.by_status ?? [];

  const emAndamento = countOf(byStatus, ["EM_ANDAMENTO", "COM_DECISAO", "SUSPENSO"]);
  const acordos = countOf(byStatus, ACORDO_STATUSES);
  const encerrados = countOf(byStatus, ENCERRADO_STATUSES);

  const hasFilters =
    statuses.length > 0 || ufs.length > 0 || companies.length > 0 || projects.length > 0 || !!search;

  function clearAll() {
    setStatuses([]);
    setUfs([]);
    setCompanies([]);
    setProjects([]);
    setSearchInput("");
    setSearch("");
  }

  /** Leva o recorte atual para a tela operacional, preservando os filtros. */
  function openInCases(extra?: { status?: string; uf?: string; project?: string }) {
    const params = new URLSearchParams();
    for (const s of extra?.status ? [extra.status] : statuses) params.append("status", s);
    for (const u of extra?.uf ? [extra.uf] : ufs) params.append("uf", u);
    for (const c of companies) params.append("company", c);
    for (const p of extra?.project ? [extra.project] : projects) params.append("project", p);
    if (search) params.set("q", search);
    navigate(`/legal/cases?${params}`);
  }

  const selectClass =
    "min-w-[13rem] rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-800 focus:border-indigo-500 focus:outline-none";

  return (
    <div className="space-y-4">
      <DashboardHeader
        title="Passivo Jurídico"
        subtitle={
          kpis ? `${kpis.case_count} processo(s) · ${kpis.person_count} pessoa(s)` : "Carregando…"
        }
        description="Situação consolidada do contencioso. Clique em qualquer barra para filtrar."
        badge="Relatório Executivo · Confidencial"
      />

      <DashboardFilterBar
        actions={
          hasFilters ? (
            <button
              type="button"
              onClick={clearAll}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              Limpar filtros
            </button>
          ) : null
        }
      >
        <FilterField label="Status">
          <select
            value=""
            onChange={(e) => e.target.value && setStatuses((p) => toggle(p, e.target.value))}
            className={selectClass}
          >
            <option value="">Todos os status</option>
            {(facets?.statuses ?? [])
              .filter((s) => !statuses.includes(s))
              .map((s) => (
                <option key={s} value={s}>
                  {LEGAL_STATUS_LABELS[s]}
                </option>
              ))}
          </select>
        </FilterField>
        <FilterField label="Estado">
          <select
            value=""
            onChange={(e) => e.target.value && setUfs((p) => toggle(p, e.target.value))}
            className={selectClass}
          >
            <option value="">Todos os estados</option>
            {(facets?.ufs ?? [])
              .filter((u) => !ufs.includes(u))
              .map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
          </select>
        </FilterField>
        <FilterField label="Empresa">
          <select
            value=""
            onChange={(e) => e.target.value && setCompanies((p) => toggle(p, e.target.value))}
            className={selectClass}
          >
            <option value="">Todas as empresas</option>
            {(facets?.companies ?? [])
              .filter((c) => !companies.includes(c))
              .map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
          </select>
        </FilterField>
        <FilterField label="Projeto">
          <select
            value=""
            onChange={(e) => e.target.value && setProjects((p) => toggle(p, e.target.value))}
            className={selectClass}
          >
            <option value="">Todos os projetos</option>
            {(facets?.projects ?? [])
              .filter((p) => !projects.includes(p))
              .map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
          </select>
        </FilterField>
        <FilterField label="Pesquisa">
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Nome, CPF, processo…"
            className={`${selectClass} min-w-[15rem]`}
          />
        </FilterField>
      </DashboardFilterBar>

      {(statuses.length > 0 || ufs.length > 0 || companies.length > 0 || projects.length > 0) && (
        <div className="flex flex-wrap items-center gap-2">
          {statuses.map((s) => (
            <FilterTag key={`s-${s}`} label={LEGAL_STATUS_LABELS[s as LegalCaseStatus] ?? s} onClear={() => setStatuses((p) => toggle(p, s))} />
          ))}
          {ufs.map((u) => (
            <FilterTag key={`u-${u}`} label={u} onClear={() => setUfs((p) => toggle(p, u))} />
          ))}
          {companies.map((c) => (
            <FilterTag key={`c-${c}`} label={c} onClear={() => setCompanies((p) => toggle(p, c))} />
          ))}
          {projects.map((p) => (
            <FilterTag key={`p-${p}`} label={p} onClear={() => setProjects((x) => toggle(x, p))} />
          ))}
        </div>
      )}

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {/* Quatro indicadores — três contagens e UM valor financeiro. */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Processos em andamento"
          value={loading && !overview ? "—" : String(emAndamento)}
          color={COLOR.andamento}
          onClick={() => openInCases({ status: "EM_ANDAMENTO" })}
        />
        <KpiCard
          label="Acordos ativos"
          value={loading && !overview ? "—" : String(acordos)}
          color={COLOR.acordo}
          onClick={() => openInCases({ status: "ACORDO" })}
        />
        <KpiCard
          label="Processos encerrados"
          value={loading && !overview ? "—" : String(encerrados)}
          color={COLOR.encerrado}
          onClick={() => openInCases({ status: "ENCERRADO" })}
        />
        <KpiCard
          label="Passivo considerado"
          value={formatCurrencyOrDash(kpis?.total_considered)}
          color={COLOR.passivo}
          onClick={() => openInCases()}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Processos por status"
          subtitle="Quantidade e passivo por situação processual"
          aside={<span>clique para filtrar</span>}
        >
          <StatusChart
            buckets={byStatus}
            selected={statuses}
            onPick={(key) => setStatuses((p) => toggle(p, key))}
          />
          <ChartLegendChips
            buckets={byStatus}
            selected={statuses}
            onPick={(key) => setStatuses((p) => toggle(p, key))}
            colorOf={(k) => STATUS_COLOR[k] ?? COLOR.bar}
          />
        </ChartCard>

        <ChartCard title="Passivo por estado" subtitle="Valor considerado por UF" aside={<span>clique para filtrar</span>}>
          <BarChart
            buckets={overview?.by_uf ?? []}
            selected={ufs}
            onPick={(key) => setUfs((p) => toggle(p, key))}
          />
          <ChartLegendChips
            buckets={overview?.by_uf ?? []}
            selected={ufs}
            onPick={(key) => setUfs((p) => toggle(p, key))}
          />
        </ChartCard>
      </div>

      <ChartCard
        title="Passivo por projeto"
        subtitle="Valor considerado por contrato/projeto"
        aside={<span>clique para filtrar</span>}
      >
        <BarChart
          buckets={overview?.by_project ?? []}
          selected={projects}
          onPick={(key) => setProjects((p) => toggle(p, key))}
          height={Math.max(220, (overview?.by_project?.length ?? 0) * 30)}
        />
        <ChartLegendChips
          buckets={overview?.by_project ?? []}
          selected={projects}
          onPick={(key) => setProjects((p) => toggle(p, key))}
        />
      </ChartCard>

      <p className="text-center text-xs text-slate-400">
        Passivo considerado desconta processos que espelham a mesma origem. O valor da causa está
        disponível na tela de Processos.
      </p>
    </div>
  );
}

/**
 * Legenda CLICÁVEL abaixo de cada gráfico — uma pastilha por barra.
 *
 * Duplica de propósito o clique na barra: o canvas do ECharts não é alcançável por teclado nem
 * por leitor de tela, então o filtro precisa existir também como elemento de interface. Na
 * prática também é o alvo mais fácil de acertar num projetor.
 */
function ChartLegendChips({
  buckets,
  selected,
  onPick,
  colorOf,
}: {
  buckets: LegalBucket[];
  selected: string[];
  onPick: (key: string) => void;
  colorOf?: (key: string) => string;
}) {
  if (buckets.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-1.5 border-t border-slate-100 pt-3">
      {buckets.map((b) => {
        const on = selected.includes(b.key);
        return (
          <button
            key={b.key || "—"}
            type="button"
            aria-pressed={on}
            onClick={() => onPick(b.key)}
            title={`Filtrar por ${b.label}`}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${
              on
                ? "border-indigo-600 bg-indigo-600 text-white"
                : "border-slate-200 bg-white text-slate-600 hover:border-indigo-400 hover:text-slate-900"
            }`}
          >
            <span
              className="h-2 w-2 shrink-0 rounded-sm"
              style={{ backgroundColor: on ? "#fff" : (colorOf?.(b.key) ?? COLOR.bar) }}
              aria-hidden
            />
            <span className="max-w-[11rem] truncate">{b.label}</span>
            <span className={on ? "text-white/75" : "text-slate-400"}>{b.count}</span>
          </button>
        );
      })}
    </div>
  );
}

function FilterTag({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <button
      type="button"
      onClick={onClear}
      className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-800 hover:bg-indigo-100"
    >
      {label} <span aria-hidden>×</span>
    </button>
  );
}

/** Status: barras verticais coloridas pelo semáforo do módulo, rotuladas pela QUANTIDADE. */
function StatusChart({
  buckets,
  selected,
  onPick,
}: {
  buckets: LegalBucket[];
  selected: string[];
  onPick: (key: string) => void;
}) {
  const option: EChartsOption = {
    animation: false, // ver nota em BarChart
    grid: { left: 8, right: 8, top: 24, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const list = params as { dataIndex: number }[];
        const row = buckets[list?.[0]?.dataIndex ?? 0];
        if (!row) return "";
        return `<strong>${row.label}</strong><br/>Processos: ${row.count}<br/>Passivo: ${formatCurrencyOrDash(row.value)}`;
      },
    },
    xAxis: {
      type: "category",
      data: buckets.map((b) => b.label),
      axisLabel: { color: "#475569", interval: 0, width: 88, overflow: "break", fontSize: 11 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#e2e8f0" } },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#94a3b8" },
      splitLine: { lineStyle: { color: "#eef2f7" } },
    },
    series: [
      {
        type: "bar",
        data: buckets.map((b) => ({
          value: b.count,
          itemStyle: {
            color: STATUS_COLOR[b.key] ?? "#64748b",
            opacity: selected.length === 0 || selected.includes(b.key) ? 1 : 0.35,
            borderRadius: [4, 4, 0, 0],
          },
        })),
        barMaxWidth: 44,
        label: { show: true, position: "top", color: "#334155", fontSize: 11 },
      },
    ],
  };

  return (
    <EChart
      option={option}
      height={260}
      onEvents={{
        click: (params: unknown) => {
          const p = params as { dataIndex?: number };
          const row = typeof p?.dataIndex === "number" ? buckets[p.dataIndex] : undefined;
          if (row) onPick(row.key);
        },
      }}
    />
  );
}
