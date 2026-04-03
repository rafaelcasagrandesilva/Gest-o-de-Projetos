import { useEffect, useMemo, useState } from "react";
import { FinancialDashboardCharts } from "@/components/FinancialDashboardCharts";
import { useAuth } from "@/context/AuthContext";
import { fetchFinancialSummary, type FinancialDashboardSummary } from "@/services/dashboard";
import { listProjects, type Project } from "@/services/projects";
import { isAxiosError } from "axios";

function monthStart(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

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
  /** Alinhado ao backend: visão consolidada sem project_id para ADMIN e CONSULTA. */
  const canViewGlobal = useMemo(
    () => Boolean(user?.role_names?.some((r) => r === "ADMIN" || r === "CONSULTA")),
    [user]
  );

  const [competencia, setCompetencia] = useState(() => monthStart(new Date()));
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [projectsError, setProjectsError] = useState<string | null>(null);

  const [data, setData] = useState<FinancialDashboardSummary | null>(null);
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
          setData(null);
          setLoading(false);
          return;
        }
        if (!selectedProjectId) return;
      }

      setLoading(true);
      setError(null);
      try {
        const res = await fetchFinancialSummary({
          competencia,
          months: 6,
          ...(selectedProjectId ? { project_id: selectedProjectId } : {}),
        });
        if (!cancelled) setData(res);
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
          setData(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competencia, selectedProjectId, canViewGlobal, projectsLoaded, projects.length]);

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

  if (error || !data) {
    return (
      <div className="space-y-4">
        <h2 className="text-xl font-semibold text-slate-900">Dashboard financeiro</h2>
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{error}</div>
      </div>
    );
  }

  const s = data.summary;
  const isGlobalView = canViewGlobal && !selectedProjectId;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Dashboard financeiro</h2>
          <p className="text-sm text-slate-500">
            {isGlobalView ? "KPIs consolidados (todos os projetos) e tendência mensal" : "KPIs do projeto e tendência mensal"}
          </p>
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
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Competência (mês)</label>
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
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <KpiCard label="Receita" value={formatMoney(s.total_revenue ?? s.revenue_total)} />
        <KpiCard label="Custo total (regras)" value={formatMoney(s.total_cost ?? s.cost_total)} />
        <KpiCard label="Retenção (R$)" value={formatMoney(s.total_retention ?? 0)} />
        <KpiCard
          label="Lucro operacional"
          value={formatMoney(s.operational_profit ?? s.profit)}
          accent="text-gray-900"
          subtitle={`Margem: ${formatPercentage(s.margin_operational ?? s.margin)}`}
        />
        <KpiCard
          label="Lucro líquido"
          value={formatMoney(s.net_profit ?? s.profit)}
          accent={getProfitColor(s.net_profit ?? s.profit)}
          subtitle={`Margem: ${formatPercentage(s.margin_net ?? s.margin)}`}
        />
        <KpiCard
          label="EBITDA"
          value={formatMoney(s.ebitda ?? 0)}
          accent={getProfitColor(s.ebitda ?? 0)}
          subtitle={`Margem EBITDA: ${formatPercentage(s.ebitda_margin ?? 0)}`}
        />
      </div>

      <FinancialDashboardCharts summary={s} monthlySeries={data.monthly_series} />

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-sm font-medium text-slate-700">Custos operacionais por projeto</h3>
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
