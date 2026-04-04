import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { useScenario, type ScenarioKind } from "@/context/ScenarioContext";
import { listFleetVehicles, type FleetVehicle } from "@/services/vehicles";
import { Link, useParams } from "react-router-dom";
import { getProject, type Project } from "@/services/projects";
import {
  copyLaborsFromPrevious,
  createFixedOperational,
  createLabor,
  createSystem,
  createVehicle,
  updateVehicle as updateProjectVehicleAllocation,
  deleteFixedOperational,
  deleteLabor,
  deleteSystem,
  deleteVehicle,
  fetchLaborDetails,
  listFixedOperational,
  listSystems,
  listVehicles,
  updateLaborCosts,
  type LaborCostPatch,
  type ProjectLaborDetail,
  type ProjectOperationalFixed,
  type ProjectSystemCost,
  type ProjectVehicle,
} from "@/services/projectStructure";
import { listEmployees, type Employee } from "@/services/employees";
import { isAxiosError } from "axios";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function monthStart(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

/** Competência sempre no primeiro dia do mês (YYYY-MM-01), alinhado ao backend. */
function normalizeCompetencia(iso: string): string {
  const slice = iso.trim().slice(0, 10);
  const m = /^(\d{4})-(\d{2})/.exec(slice);
  if (!m) return monthStart();
  return `${m[1]}-${m[2]}-01`;
}

function money(n: number) {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Mesmo formato BRL que `money` (resumos e textos padronizados). */
const formatCurrency = money;

const LABOR_BAR_BASE = "#3b82f6";
const LABOR_BAR_MAX = "#1d4ed8";

type LaborChartRow = {
  key: string;
  name: string;
  cost: number;
  pctOfTotal: number;
  isMax: boolean;
};

function LaborShareTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: LaborChartRow }>;
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-md">
      <p className="font-medium text-slate-900">{p.name}</p>
      <p className="tabular-nums text-slate-700">{money(p.cost)}</p>
      <p className="text-slate-600">{(p.pctOfTotal * 100).toFixed(1)}% do total</p>
    </div>
  );
}

function fleetTypeLabel(t: string): string {
  switch (t) {
    case "LIGHT":
      return "Leve";
    case "PICKUP":
      return "Pickup";
    case "SEDAN":
      return "Sedan";
    default:
      return t;
  }
}

function fuelLabel(f: string | null | undefined): string {
  if (f == null || f === "") return "—";
  switch (f) {
    case "ETHANOL":
      return "Etanol";
    case "GASOLINE":
      return "Gasolina";
    case "DIESEL":
      return "Diesel";
    default:
      return f;
  }
}

const PROJECT_FLEET_SUMMARY_TYPES: { key: "LIGHT" | "PICKUP" | "SEDAN"; title: string }[] = [
  { key: "LIGHT", title: "Leve" },
  { key: "PICKUP", title: "Caminhonete" },
  { key: "SEDAN", title: "Pesado" },
];

type Tab = "labor" | "vehicles" | "systems" | "fixed";

function strOrEmpty(v: number | null | undefined): string {
  return v == null ? "" : String(v);
}

function laborBaseLabel(src: string | undefined): string {
  if (src === "OVERRIDE_TOTAL") return "Custo total: override";
  if (src === "OVERRIDE_SALARY") return "Base: override";
  return "Base: cadastro";
}

function LaborCostEditor({
  projectId,
  detail,
  onSaved,
}: {
  projectId: string;
  detail: ProjectLaborDetail;
  onSaved: () => void | Promise<void>;
}) {
  const isClt = (detail.tipo || "").toUpperCase() === "CLT";
  const [salary, setSalary] = useState(() => strOrEmpty(detail.cost_salary_base));
  const [add, setAdd] = useState(() => strOrEmpty(detail.cost_additional_costs));
  const [h50, setH50] = useState(() => strOrEmpty(detail.cost_extra_hours_50));
  const [h70, setH70] = useState(() => strOrEmpty(detail.cost_extra_hours_70));
  const [h100, setH100] = useState(() => strOrEmpty(detail.cost_extra_hours_100));
  const [pjH, setPjH] = useState(() => strOrEmpty(detail.cost_pj_hours_per_month));
  const [pjAdd, setPjAdd] = useState(() => strOrEmpty(detail.cost_pj_additional_cost));
  const [totalOv, setTotalOv] = useState(() => strOrEmpty(detail.cost_total_override));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setSalary(strOrEmpty(detail.cost_salary_base));
    setAdd(strOrEmpty(detail.cost_additional_costs));
    setH50(strOrEmpty(detail.cost_extra_hours_50));
    setH70(strOrEmpty(detail.cost_extra_hours_70));
    setH100(strOrEmpty(detail.cost_extra_hours_100));
    setPjH(strOrEmpty(detail.cost_pj_hours_per_month));
    setPjAdd(strOrEmpty(detail.cost_pj_additional_cost));
    setTotalOv(strOrEmpty(detail.cost_total_override));
    setErr(null);
  }, [detail]);

  function parseNum(s: string): number | null {
    if (s.trim() === "") return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  }

  async function submit(patch: LaborCostPatch) {
    setSaving(true);
    setErr(null);
    try {
      await updateLaborCosts(projectId, detail.labor_id, patch);
      await Promise.resolve(onSaved());
    } catch {
      setErr("Não foi possível salvar os custos.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-indigo-100 bg-indigo-50/40 p-4">
      <p className="text-xs font-medium text-indigo-900">Custos deste mês neste projeto (não altera o cadastro RH)</p>
      {detail.uses_cost_total_override ? (
        <p className="mt-1 text-xs text-amber-800">
          Custo total fixo ativo — demais campos de composição são ignorados no cálculo.
        </p>
      ) : null}
      {err ? <p className="mt-2 text-xs text-red-700">{err}</p> : null}
      <p className="mt-2 text-xs font-medium text-slate-700">
        Fonte do cálculo:{" "}
        <span className="rounded-md bg-white px-2 py-0.5 ring-1 ring-slate-200">
          {laborBaseLabel(detail.cost_base_source)}
        </span>
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="block text-xs text-slate-600">
          Custo total (override)
          <input
            type="number"
            step="0.01"
            min={0}
            value={totalOv}
            onChange={(e) => setTotalOv(e.target.value)}
            className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
            placeholder="Vazio = calcular"
          />
        </label>
        <label className="block text-xs text-slate-600">
          Salário base (override)
          <input
            type="number"
            step="0.01"
            min={0}
            value={salary}
            onChange={(e) => setSalary(e.target.value)}
            className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
            placeholder="Vazio = cadastro"
          />
        </label>
        {isClt ? (
          <>
            <label className="block text-xs text-slate-600">
              Horas extras 50%
              <input
                type="number"
                step="0.01"
                min={0}
                value={h50}
                onChange={(e) => setH50(e.target.value)}
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
              />
            </label>
            <label className="block text-xs text-slate-600">
              Horas extras 70%
              <input
                type="number"
                step="0.01"
                min={0}
                value={h70}
                onChange={(e) => setH70(e.target.value)}
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
              />
            </label>
            <label className="block text-xs text-slate-600">
              Horas extras 100%
              <input
                type="number"
                step="0.01"
                min={0}
                value={h100}
                onChange={(e) => setH100(e.target.value)}
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
              />
            </label>
            <label className="block text-xs text-slate-600 sm:col-span-2">
              Custos adicionais (R$)
              <input
                type="number"
                step="0.01"
                min={0}
                value={add}
                onChange={(e) => setAdd(e.target.value)}
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
              />
            </label>
          </>
        ) : (
          <>
            <label className="block text-xs text-slate-600">
              Horas/mês PJ (override)
              <input
                type="number"
                step="0.01"
                min={0}
                value={pjH}
                onChange={(e) => setPjH(e.target.value)}
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
              />
            </label>
            <label className="block text-xs text-slate-600">
              Ajuda de custo PJ (override)
              <input
                type="number"
                step="0.01"
                min={0}
                value={pjAdd}
                onChange={(e) => setPjAdd(e.target.value)}
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
              />
            </label>
          </>
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={saving}
          onClick={() =>
            submit({
              cost_total_override: parseNum(totalOv),
              cost_salary_base: parseNum(salary),
              cost_additional_costs: parseNum(add),
              cost_extra_hours_50: parseNum(h50),
              cost_extra_hours_70: parseNum(h70),
              cost_extra_hours_100: parseNum(h100),
              cost_pj_hours_per_month: parseNum(pjH),
              cost_pj_additional_cost: parseNum(pjAdd),
            })
          }
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
        >
          {saving ? "Salvando…" : "Salvar custos do mês"}
        </button>
        <button
          type="button"
          disabled={saving}
          onClick={() =>
            submit({
              cost_salary_base: null,
              cost_additional_costs: null,
              cost_extra_hours_50: null,
              cost_extra_hours_70: null,
              cost_extra_hours_100: null,
              cost_pj_hours_per_month: null,
              cost_pj_additional_cost: null,
              cost_total_override: null,
            })
          }
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-700 disabled:opacity-50"
        >
          Limpar overrides (usar cadastro)
        </button>
      </div>
    </div>
  );
}

export function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>();
  const { globalScenario } = useScenario();
  const [editScenario, setEditScenario] = useState<ScenarioKind>(globalScenario);
  const [project, setProject] = useState<Project | null>(null);
  const [competencia, setCompetencia] = useState(() => normalizeCompetencia(monthStart()));
  const [tab, setTab] = useState<Tab>("labor");
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [laborDetails, setLaborDetails] = useState<ProjectLaborDetail[]>([]);
  const [vehicleRowsByScenario, setVehicleRowsByScenario] = useState<{
    PREVISTO: ProjectVehicle[];
    REALIZADO: ProjectVehicle[];
  }>({ PREVISTO: [], REALIZADO: [] });
  const [systems, setSystems] = useState<ProjectSystemCost[]>([]);
  const [fixed, setFixed] = useState<ProjectOperationalFixed[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const competenciaApi = useMemo(() => normalizeCompetencia(competencia), [competencia]);

  useEffect(() => {
    setEditScenario(globalScenario);
  }, [globalScenario, projectId]);

  useEffect(() => {
    if (!projectId) return;
    let c = false;
    (async () => {
      setLoading(true);
      try {
        const p = await getProject(projectId);
        if (!c) setProject(p);
      } catch {
        if (!c) setError("Projeto não encontrado ou sem permissão.");
      } finally {
        if (!c) setLoading(false);
      }
    })();
    return () => {
      c = true;
    };
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;
    let c = false;
    (async () => {
      try {
        const em = await listEmployees({ competencia: competenciaApi }).catch(() => []);
        if (!c) setEmployees(em);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      c = true;
    };
  }, [projectId, competenciaApi]);

  const reloadTab = useCallback(async () => {
    if (!projectId) return;
    setError(null);
    try {
      if (tab === "labor")
        setLaborDetails(await fetchLaborDetails(projectId, competenciaApi, editScenario));
      if (tab === "vehicles") {
        const [vp, vr] = await Promise.all([
          listVehicles(projectId, competenciaApi, "PREVISTO"),
          listVehicles(projectId, competenciaApi, "REALIZADO"),
        ]);
        setVehicleRowsByScenario({ PREVISTO: vp, REALIZADO: vr });
      }
      if (tab === "systems") setSystems(await listSystems(projectId, competenciaApi, editScenario));
      if (tab === "fixed")
        setFixed(await listFixedOperational(projectId, competenciaApi, editScenario));
    } catch (e) {
      if (isAxiosError(e) && e.response?.status === 403) {
        setError("Sem acesso a este projeto.");
      } else {
        setError("Erro ao carregar dados.");
      }
    }
  }, [projectId, competenciaApi, tab, editScenario]);

  useEffect(() => {
    void reloadTab();
  }, [reloadTab]);

  if (!projectId) {
    return <p className="text-slate-500">ID inválido.</p>;
  }
  if (loading) {
    return <div className="text-slate-500">Carregando…</div>;
  }
  if (!project) {
    return (
      <div className="space-y-4">
        <p className="text-red-700">{error}</p>
        <Link to="/projects" className="text-indigo-600 hover:underline">
          Voltar
        </Link>
      </div>
    );
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "labor", label: "Mão de obra" },
    { id: "vehicles", label: "Veículos" },
    { id: "systems", label: "Sistemas" },
    { id: "fixed", label: "Custos fixos" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link to="/projects" className="text-sm text-indigo-600 hover:underline">
            ← Projetos
          </Link>
          <h2 className="mt-2 text-xl font-semibold text-slate-900">{project.name}</h2>
          <p className="text-sm text-slate-500">
            Estrutura por competência e cenário. Mão de obra: custos mensais editáveis aqui; cadastro global do
            colaborador não é alterado. Na aba Mão de obra, use o botão para copiar colaboradores do mês anterior
            (mesmo cenário) quando quiser preencher a competência.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <span className="mb-1 block text-xs text-slate-500">Editando</span>
            <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
              {(["PREVISTO", "REALIZADO"] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setEditScenario(s)}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                    editScenario === s ? "bg-indigo-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {s === "PREVISTO" ? "Previsto" : "Realizado"}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">Competência</label>
            <input
              type="month"
              value={competencia.slice(0, 7)}
              onChange={(e) =>
                e.target.value && setCompetencia(normalizeCompetencia(`${e.target.value}-01`))
              }
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{error}</div>
      )}

      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              tab === t.id ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "labor" && (
        <LaborTab
          projectId={projectId}
          competencia={competenciaApi}
          editScenario={editScenario}
          employees={employees}
          rows={laborDetails}
          onRefresh={reloadTab}
        />
      )}
      {tab === "vehicles" && (
        <VehiclesTab
          projectId={projectId}
          competencia={competenciaApi}
          editScenario={editScenario}
          rows={vehicleRowsByScenario[editScenario]}
          rowsPrevisto={vehicleRowsByScenario.PREVISTO}
          rowsRealizado={vehicleRowsByScenario.REALIZADO}
          onRefresh={reloadTab}
        />
      )}
      {tab === "systems" && (
        <SystemsTab
          projectId={projectId}
          competencia={competenciaApi}
          editScenario={editScenario}
          rows={systems}
          onRefresh={reloadTab}
        />
      )}
      {tab === "fixed" && (
        <FixedTab
          projectId={projectId}
          competencia={competenciaApi}
          editScenario={editScenario}
          rows={fixed}
          onRefresh={reloadTab}
        />
      )}
    </div>
  );
}

function LaborTab({
  projectId,
  competencia,
  editScenario,
  employees,
  rows,
  onRefresh,
}: {
  projectId: string;
  competencia: string;
  editScenario: ScenarioKind;
  employees: Employee[];
  rows: ProjectLaborDetail[];
  onRefresh: () => void;
}) {
  const [employeeId, setEmployeeId] = useState("");
  const [allocationPct, setAllocationPct] = useState("100");
  const [openDetailId, setOpenDetailId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [copyBusy, setCopyBusy] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  const linkedIds = new Set(rows.map((r) => r.employee_id));
  const availableEmployees = employees.filter((e) => !linkedIds.has(e.id));

  const laborShare = useMemo(() => {
    const sorted = [...rows].sort((a, b) => b.allocated_cost - a.allocated_cost);
    const totalMaoDeObra = sorted.reduce((s, r) => s + r.allocated_cost, 0);
    const maxCost = sorted.length ? sorted[0].allocated_cost : 0;
    const chartData: LaborChartRow[] = sorted.map((r) => ({
      key: r.labor_id,
      name: r.name.length > 42 ? `${r.name.slice(0, 39)}…` : r.name,
      cost: r.allocated_cost,
      pctOfTotal: totalMaoDeObra > 0 ? r.allocated_cost / totalMaoDeObra : 0,
      isMax: maxCost > 0 && r.allocated_cost === maxCost,
    }));
    return { totalMaoDeObra, count: rows.length, chartData };
  }, [rows]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!employeeId) {
      setFormError("Selecione um colaborador.");
      return;
    }
    const pct = Number(allocationPct);
    if (Number.isNaN(pct) || pct < 1 || pct > 100) {
      setFormError("Percentual deve ser entre 1 e 100.");
      return;
    }
    try {
      await createLabor(projectId, {
        competencia,
        employee_id: employeeId,
        allocation_percentage: pct,
        scenario: editScenario,
      });
      setEmployeeId("");
      setAllocationPct("100");
      onRefresh();
    } catch (err) {
      if (isAxiosError(err) && err.response?.status === 409) {
        setFormError("Este colaborador já está vinculado nesta competência.");
      } else if (isAxiosError(err) && err.response?.data?.detail) {
        const d = err.response.data.detail;
        setFormError(typeof d === "string" ? d : Array.isArray(d) ? d.map((x: { msg?: string }) => x.msg ?? "").join(" ") : "Não foi possível adicionar.");
      } else {
        setFormError("Não foi possível adicionar.");
      }
    }
  }

  async function copyFromPrevious() {
    if (
      !window.confirm(
        "Isso irá copiar os colaboradores do mês anterior para este mês. Deseja continuar?"
      )
    ) {
      return;
    }
    setCopyBusy(true);
    setCopyFeedback(null);
    try {
      const res = await copyLaborsFromPrevious(projectId, {
        competencia,
        scenario: editScenario,
      });
      if (res.copied > 0) {
        setCopyFeedback(
          `${res.copied} colaborador(es) copiado(s).` +
            (res.skipped_allocation_cap > 0
              ? ` ${res.skipped_allocation_cap} omitido(s) por limite de alocação (>100%).`
              : "")
        );
      } else {
        setCopyFeedback(
          "Nenhum colaborador novo foi copiado (já vinculados neste mês, mês anterior vazio ou limite de alocação)."
        );
      }
      onRefresh();
    } catch (err) {
      if (isAxiosError(err) && err.response?.data?.detail) {
        const d = err.response.data.detail;
        setCopyFeedback(
          typeof d === "string" ? d : "Não foi possível copiar. Tente novamente."
        );
      } else {
        setCopyFeedback("Não foi possível copiar. Tente novamente.");
      }
    } finally {
      setCopyBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="max-w-xl space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="font-medium text-slate-900">Vincular colaborador ao projeto</h3>
        <p className="text-xs text-slate-500">
          O custo vem do cadastro (CLT ou PJ), multiplicado pelo percentual de alocação neste projeto. A soma dos
          percentuais do mesmo colaborador em todos os projetos no mês não pode passar de 100%.
        </p>
        <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <div>
            <label className="text-xs text-slate-500">Colaborador</label>
            <select
              required
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="">—</option>
              {availableEmployees.map((em) => (
                <option key={em.id} value={em.id}>
                  {em.full_name} ({em.employment_type})
                </option>
              ))}
            </select>
          </div>
          <div className="w-full sm:w-28">
            <label className="text-xs text-slate-500">Percentual (%)</label>
            <input
              type="number"
              min={1}
              max={100}
              step={0.5}
              value={allocationPct}
              onChange={(e) => setAllocationPct(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
            />
          </div>
        </div>
        {formError && <p className="text-sm text-red-600">{formError}</p>}
        <button type="submit" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white">
          Adicionar
        </button>
      </form>

      {rows.length === 0 ? (
        <div className="rounded-xl border-2 border-dashed border-indigo-200 bg-indigo-50/60 p-6 text-center shadow-sm">
          <p className="text-sm text-slate-700">
            Esta competência ainda não tem colaboradores vinculados. Você pode trazer os do mês anterior de uma vez.
          </p>
          <button
            type="button"
            disabled={copyBusy}
            onClick={copyFromPrevious}
            className="mt-4 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60"
          >
            {copyBusy ? "Copiando…" : "Inicializar mês com base no mês anterior"}
          </button>
        </div>
      ) : null}

      {copyFeedback && (
        <p
          className={`text-sm ${copyFeedback.startsWith("Não foi") || copyFeedback.includes("conflito") ? "text-red-600" : "text-slate-600"}`}
        >
          {copyFeedback}
        </p>
      )}

      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-slate-900">Participação na mão de obra</h3>
          {rows.length > 0 ? (
            <button
              type="button"
              disabled={copyBusy}
              onClick={copyFromPrevious}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-60"
            >
              {copyBusy ? "Copiando…" : "Copiar colaboradores do mês anterior"}
            </button>
          ) : null}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Total de colaboradores</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{laborShare.count}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Custo total mão de obra (R$)</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{money(laborShare.totalMaoDeObra)}</p>
          </div>
        </div>

        {laborShare.chartData.length > 0 ? (
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
            <p className="mb-4 text-xs text-slate-500">
              Custo proporcional por colaborador (ordenado do maior para o menor). Percentuais sobre o total da mão de
              obra do projeto.
            </p>
            <div
              className="w-full"
              style={{
                height: Math.min(520, Math.max(220, laborShare.chartData.length * 44)),
              }}
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  layout="vertical"
                  data={laborShare.chartData}
                  margin={{ top: 4, right: 52, left: 8, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal vertical={false} className="stroke-slate-200" />
                  <XAxis
                    type="number"
                    tickFormatter={(v) =>
                      typeof v === "number"
                        ? v.toLocaleString("pt-BR", { maximumFractionDigits: 0, notation: "compact" })
                        : String(v)
                    }
                    className="text-xs"
                  />
                  <YAxis type="category" dataKey="name" width={132} tick={{ fontSize: 11 }} interval={0} />
                  <Tooltip content={<LaborShareTooltip />} cursor={{ fill: "rgba(148, 163, 184, 0.12)" }} />
                  <Bar dataKey="cost" radius={[0, 4, 4, 0]} maxBarSize={32}>
                    {laborShare.chartData.map((entry) => (
                      <Cell key={entry.key} fill={entry.isMax ? LABOR_BAR_MAX : LABOR_BAR_BASE} />
                    ))}
                    <LabelList
                      dataKey="pctOfTotal"
                      position="right"
                      formatter={(v: number) => `${(v * 100).toFixed(1)}%`}
                      style={{ fill: "#475569", fontSize: 11 }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : null}
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full min-w-[32rem] text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Nome</th>
              <th className="px-4 py-3">Tipo</th>
              <th className="px-4 py-3 text-right">%</th>
              <th className="px-4 py-3 text-right">Custo proporcional</th>
              <th className="px-4 py-3 w-28" />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  Nenhum colaborador vinculado nesta competência.
                </td>
              </tr>
            ) : (
              rows.map((r) => {
                const open = openDetailId === r.labor_id;
                const b = r.breakdown;
                return (
                  <Fragment key={r.labor_id}>
                    <tr className="border-b border-slate-100">
                      <td className="px-4 py-3 font-medium text-slate-900">
                        <span className="align-middle">{r.name}</span>
                        <span
                          className={`ml-2 inline-block align-middle rounded px-1.5 py-0.5 text-[10px] font-medium ${
                            r.cost_base_source === "OVERRIDE_TOTAL"
                              ? "bg-amber-100 text-amber-900"
                              : r.cost_base_source === "OVERRIDE_SALARY"
                                ? "bg-indigo-100 text-indigo-900"
                                : "bg-slate-100 text-slate-600"
                          }`}
                          title={laborBaseLabel(r.cost_base_source)}
                        >
                          {r.cost_base_source === "OVERRIDE_TOTAL"
                            ? "Total ov."
                            : r.cost_base_source === "OVERRIDE_SALARY"
                              ? "Base ov."
                              : "Cadastro"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{r.tipo}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.allocation_percentage}%</td>
                      <td className="px-4 py-3 text-right tabular-nums">{money(r.allocated_cost)}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => setOpenDetailId(open ? null : r.labor_id)}
                          className="text-indigo-600 hover:underline"
                        >
                          {open ? "Ocultar" : "Detalhes"}
                        </button>
                      </td>
                    </tr>
                    {open && (
                      <tr className="border-b border-slate-100 bg-slate-50/80">
                        <td colSpan={5} className="px-4 py-3 text-xs text-slate-700">
                          <dl className="mb-3 grid gap-2 border-b border-slate-200 pb-3 sm:grid-cols-3">
                            <div>
                              <dt className="text-slate-500">Alocação</dt>
                              <dd className="font-medium">{r.allocation_percentage}%</dd>
                            </div>
                            <div>
                              <dt className="text-slate-500">Custo integral (colaborador)</dt>
                              <dd className="font-medium tabular-nums">{money(r.full_cost)}</dd>
                            </div>
                            <div>
                              <dt className="text-slate-500">Custo alocado ao projeto</dt>
                              <dd className="font-medium tabular-nums">{money(r.allocated_cost)}</dd>
                            </div>
                          </dl>
                          <p className="mb-2 text-slate-500">Detalhamento proporcional ao percentual:</p>
                          <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                            <div>
                              <dt className="text-slate-500">Salário base (ou base PJ)</dt>
                              <dd className="font-medium tabular-nums">{money(b.salary_base)}</dd>
                            </div>
                            <div>
                              <dt className="text-slate-500">Periculosidade</dt>
                              <dd className="font-medium tabular-nums">{money(b.periculosidade)}</dd>
                            </div>
                            <div>
                              <dt className="text-slate-500">Adicional dirigida</dt>
                              <dd className="font-medium tabular-nums">{money(b.adicional_dirigida)}</dd>
                            </div>
                            <div>
                              <dt className="text-slate-500">VR</dt>
                              <dd className="font-medium tabular-nums">{money(b.vr)}</dd>
                            </div>
                            <div>
                              <dt className="text-slate-500">Horas extras</dt>
                              <dd className="font-medium tabular-nums">{money(b.horas_extras)}</dd>
                            </div>
                            <div>
                              <dt className="text-slate-500">Encargos</dt>
                              <dd className="font-medium tabular-nums">{money(b.encargos)}</dd>
                            </div>
                            <div>
                              <dt className="text-slate-500">Custos adicionais</dt>
                              <dd className="font-medium tabular-nums">{money(b.additional_costs)}</dd>
                            </div>
                            <div>
                              <dt className="text-slate-500">Ajuda de custo (PJ)</dt>
                              <dd className="font-medium tabular-nums">{money(b.ajuda_custo)}</dd>
                            </div>
                          </dl>
                          <LaborCostEditor projectId={projectId} detail={r} onSaved={onRefresh} />
                          <div className="mt-3 flex justify-end border-t border-slate-200 pt-3">
                            <button
                              type="button"
                              onClick={async () => {
                                await deleteLabor(projectId, r.labor_id);
                                setOpenDetailId(null);
                                onRefresh();
                              }}
                              className="text-red-600 hover:underline"
                            >
                              Excluir vínculo
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function VehiclesTab({
  projectId,
  competencia,
  editScenario,
  rows,
  rowsPrevisto,
  rowsRealizado,
  onRefresh,
}: {
  projectId: string;
  competencia: string;
  editScenario: ScenarioKind;
  rows: ProjectVehicle[];
  rowsPrevisto: ProjectVehicle[];
  rowsRealizado: ProjectVehicle[];
  onRefresh: () => void;
}) {
  const isPrevisto = editScenario === "PREVISTO";
  const [fleet, setFleet] = useState<FleetVehicle[]>([]);
  const [fleetVid, setFleetVid] = useState("");
  const [ft, setFt] = useState<"ETHANOL" | "GASOLINE" | "DIESEL">("GASOLINE");
  const [km, setKm] = useState("");
  const [fuelRealized, setFuelRealized] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editKm, setEditKm] = useState("");
  const [editFt, setEditFt] = useState<"ETHANOL" | "GASOLINE" | "DIESEL">("GASOLINE");
  const [editFuelRealized, setEditFuelRealized] = useState("");
  const [editVid, setEditVid] = useState("");

  useEffect(() => {
    setKm("");
    setFuelRealized("");
    setEditKm("");
    setEditFuelRealized("");
    setEditingId(null);
  }, [editScenario]);

  useEffect(() => {
    let c = false;
    listFleetVehicles({ active_only: true, limit: 200 })
      .then((list) => {
        if (!c) setFleet(list);
      })
      .catch(() => {
        if (!c) setFleet([]);
      });
    return () => {
      c = true;
    };
  }, [projectId, competencia]);

  const selectedFleet = fleet.find((v) => v.id === fleetVid);

  function rowByVehicleId(list: ProjectVehicle[], vehicleId: string) {
    return list.find((x) => x.vehicle_id === vehicleId);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!fleetVid) return;
    if (isPrevisto) {
      if (km.trim() === "" || Number(km) < 0) return;
      await createVehicle(projectId, {
        competencia,
        vehicle_id: fleetVid,
        fuel_type: ft,
        km_per_month: Number(km),
        scenario: editScenario,
      });
    } else {
      const v = Number(fuelRealized);
      if (Number.isNaN(v) || v < 0) return;
      await createVehicle(projectId, {
        competencia,
        vehicle_id: fleetVid,
        fuel_cost_realized: v,
        scenario: editScenario,
      });
    }
    setFleetVid("");
    setKm("");
    setFuelRealized("");
    onRefresh();
  }

  function startEdit(r: ProjectVehicle) {
    setEditingId(r.id);
    setEditKm(r.km_per_month != null ? String(r.km_per_month) : "");
    setEditFt((r.fuel_type as typeof editFt) || "GASOLINE");
    setEditVid(r.vehicle_id);
    setEditFuelRealized(r.fuel_cost_realized != null ? String(r.fuel_cost_realized) : "");
  }

  async function saveEdit() {
    if (!editingId) return;
    if (isPrevisto) {
      if (editKm.trim() === "" || Number(editKm) < 0) return;
      await updateProjectVehicleAllocation(projectId, editingId, {
        vehicle_id: editVid,
        fuel_type: editFt,
        km_per_month: Number(editKm),
      });
    } else {
      const v = Number(editFuelRealized);
      if (Number.isNaN(v) || v < 0) return;
      await updateProjectVehicleAllocation(projectId, editingId, {
        vehicle_id: editVid,
        fuel_cost_realized: v,
        km_per_month: editKm.trim() === "" ? null : Number(editKm),
      });
    }
    setEditingId(null);
    onRefresh();
  }

  const projectVehiclesSummary = useMemo(() => {
    const byKey = {
      LIGHT: { count: 0, cost: 0 },
      PICKUP: { count: 0, cost: 0 },
      SEDAN: { count: 0, cost: 0 },
    };
    let totalCost = 0;
    for (const r of rows) {
      totalCost += r.monthly_cost;
      const t = r.vehicle_type || "LIGHT";
      if (t === "LIGHT" || t === "PICKUP" || t === "SEDAN") {
        const k = t as keyof typeof byKey;
        byKey[k].count += 1;
        byKey[k].cost += r.monthly_cost;
      }
    }
    return { totalVehicles: rows.length, totalCost, byKey };
  }, [rows]);

  const scenarioHint = isPrevisto
    ? "O custo será estimado com base no km e no tipo de combustível (inclui custo fixo mensal do veículo na frota)."
    : "Informe o valor real gasto com combustível no mês. O custo da linha é custo fixo da frota (locação) + esse valor; km e tipo de combustível não entram no cálculo (km pode ser só referência).";

  const addDisabled =
    !fleetVid ||
    (isPrevisto ? km.trim() === "" || Number(km) < 0 : fuelRealized.trim() === "" || Number(fuelRealized) < 0);

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="max-w-xl space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="font-medium text-slate-900">Alocar veículo da frota</h3>
        <p className="rounded-md border border-indigo-100 bg-indigo-50/60 px-3 py-2 text-xs text-indigo-950">
          {scenarioHint}
        </p>
        <div>
          <label className="text-xs text-slate-500">Veículo (placa — modelo)</label>
          <select
            required
            value={fleetVid}
            onChange={(e) => setFleetVid(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            <option value="">Selecione…</option>
            {fleet.map((v) => (
              <option key={v.id} value={v.id}>
                {v.plate}
                {v.model ? ` — ${v.model}` : ""}
              </option>
            ))}
          </select>
        </div>
        {selectedFleet && (
          <p className="text-sm text-slate-600">
            Tipo: <span className="font-medium text-slate-900">{fleetTypeLabel(selectedFleet.type)}</span>
          </p>
        )}
        {isPrevisto ? (
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-slate-500">Tipo de combustível</label>
              <select
                value={ft}
                onChange={(e) => setFt(e.target.value as typeof ft)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <option value="ETHANOL">Etanol</option>
                <option value="GASOLINE">Gasolina</option>
                <option value="DIESEL">Diesel</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500">Km / mês</label>
              <input
                type="number"
                required
                min={0}
                value={km}
                onChange={(e) => setKm(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
          </div>
        ) : (
          <div>
            <label className="text-xs text-slate-500">Valor combustível (R$) — realizado</label>
            <input
              type="number"
              required
              min={0}
              step="0.01"
              value={fuelRealized}
              onChange={(e) => setFuelRealized(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
              placeholder="0,00"
            />
          </div>
        )}
        <button
          type="submit"
          disabled={addDisabled}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          Adicionar
        </button>
      </form>

      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-slate-900">Resumo dos veículos no projeto</h3>
        <p className="text-sm text-slate-500">
          Cenário atual: <strong>{isPrevisto ? "PREVISTO (simulação)" : "REALIZADO (valor informado)"}</strong>.
          Totais abaixo refletem apenas as alocações deste cenário nesta competência.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Total de veículos vinculados</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
              {projectVehiclesSummary.totalVehicles}
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Custo total de veículos</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
              {money(projectVehiclesSummary.totalCost)}
            </p>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          {PROJECT_FLEET_SUMMARY_TYPES.map(({ key, title }) => {
            const row = projectVehiclesSummary.byKey[key];
            return (
              <div key={key} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">{title}</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{row.count}</p>
                <p className="mt-1 text-sm tabular-nums text-slate-600">{money(row.cost)}</p>
                <p className="mt-0.5 text-xs text-slate-500">veículos · custo do tipo</p>
              </div>
            );
          })}
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b border-slate-100 bg-slate-50/80">
            <tr>
              <th className="px-4 py-3 font-medium text-slate-600">Placa</th>
              <th className="px-4 py-3 font-medium text-slate-600">Modelo</th>
              <th className="px-4 py-3 font-medium text-slate-600">Condutor</th>
              <th className="px-4 py-3 font-medium text-slate-600">KM (ref.)</th>
              <th className="px-4 py-3 font-medium text-slate-600">Combustível</th>
              <th className="px-4 py-3 font-medium text-slate-600">Custo</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-slate-500">
                  Nenhum veículo nesta competência.
                </td>
              </tr>
            ) : (
              rows.map((r) => {
                const prevRow = rowByVehicleId(rowsPrevisto, r.vehicle_id);
                const realRow = rowByVehicleId(rowsRealizado, r.vehicle_id);
                const pv = prevRow?.display_fuel_cost;
                const rv = realRow?.display_fuel_cost;
                const showFuelCompare = pv != null && rv != null;
                return (
                  <Fragment key={r.id}>
                    {editingId === r.id ? (
                      <tr className="border-b border-slate-50 bg-amber-50/40">
                        <td className="px-4 py-3 align-top" colSpan={3}>
                          <label className="text-xs text-slate-500">Veículo</label>
                          <select
                            value={editVid}
                            onChange={(e) => setEditVid(e.target.value)}
                            className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                          >
                            {fleet.map((v) => (
                              <option key={v.id} value={v.id}>
                                {v.plate}
                                {v.model ? ` — ${v.model}` : ""}
                              </option>
                            ))}
                          </select>
                        </td>
                        {isPrevisto ? (
                          <>
                            <td className="px-4 py-3 align-top">
                              <label className="text-xs text-slate-500">Km / mês</label>
                              <input
                                type="number"
                                min={0}
                                value={editKm}
                                onChange={(e) => setEditKm(e.target.value)}
                                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm tabular-nums"
                              />
                            </td>
                            <td className="px-4 py-3 align-top">
                              <label className="text-xs text-slate-500">Comb.</label>
                              <select
                                value={editFt}
                                onChange={(e) => setEditFt(e.target.value as typeof editFt)}
                                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                              >
                                <option value="ETHANOL">Etanol</option>
                                <option value="GASOLINE">Gasolina</option>
                                <option value="DIESEL">Diesel</option>
                              </select>
                            </td>
                          </>
                        ) : (
                          <>
                            <td className="px-4 py-3 align-top">
                              <label className="text-xs text-slate-500">Km (opcional)</label>
                              <input
                                type="number"
                                min={0}
                                value={editKm}
                                onChange={(e) => setEditKm(e.target.value)}
                                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm tabular-nums"
                                placeholder="—"
                              />
                            </td>
                            <td className="px-4 py-3 align-top">
                              <label className="text-xs text-slate-500">Valor comb. (R$)</label>
                              <input
                                type="number"
                                min={0}
                                step="0.01"
                                value={editFuelRealized}
                                onChange={(e) => setEditFuelRealized(e.target.value)}
                                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm tabular-nums"
                              />
                            </td>
                          </>
                        )}
                        <td className="px-4 py-3 text-slate-400">—</td>
                        <td className="px-4 py-3 align-top text-right">
                          <div className="flex flex-col gap-1">
                            <button
                              type="button"
                              onClick={() => void saveEdit()}
                              className="text-sm text-indigo-600 hover:underline"
                            >
                              Salvar
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingId(null)}
                              className="text-sm text-slate-600 hover:underline"
                            >
                              Cancelar
                            </button>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      <tr className="border-b border-slate-50">
                        <td className="px-4 py-3 font-medium tabular-nums">{r.plate}</td>
                        <td className="px-4 py-3 text-slate-600">{r.model ?? "—"}</td>
                        <td className="px-4 py-3">{r.driver_name ?? "—"}</td>
                        <td className="px-4 py-3 tabular-nums text-slate-700">
                          {r.km_per_month != null ? r.km_per_month : "—"}
                        </td>
                        <td className="px-4 py-3 text-slate-700">
                          {isPrevisto ? fuelLabel(r.fuel_type) : "—"}
                          {!isPrevisto && r.fuel_cost_realized != null ? (
                            <span className="mt-0.5 block text-xs text-slate-500 tabular-nums">
                              R$ {Number(r.fuel_cost_realized).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                            </span>
                          ) : null}
                        </td>
                        <td className="px-4 py-3 font-medium tabular-nums">
                          {money(r.monthly_cost)}
                          {!isPrevisto && r.fuel_cost_per_km_realized != null ? (
                            <span className="mt-0.5 block text-xs font-normal text-slate-500 tabular-nums">
                              ≈ {money(r.fuel_cost_per_km_realized)}/km
                            </span>
                          ) : null}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            onClick={() => startEdit(r)}
                            className="text-sm text-slate-600 hover:underline"
                          >
                            Editar
                          </button>
                          <button
                            type="button"
                            onClick={async () => {
                              await deleteVehicle(projectId, r.id);
                              onRefresh();
                            }}
                            className="ml-3 text-sm text-red-600 hover:underline"
                          >
                            Excluir
                          </button>
                        </td>
                      </tr>
                    )}
                    {showFuelCompare && editingId !== r.id ? (
                      <tr className="border-b border-slate-50 bg-slate-50/70">
                        <td colSpan={7} className="px-4 py-2 text-xs text-slate-600">
                          <span className="font-medium text-slate-800">Combustível (previsto × realizado):</span>{" "}
                          Previsto {money(pv!)} · Realizado {money(rv!)} · Δ {money(rv! - pv!)}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SystemsTab({
  projectId,
  competencia,
  editScenario,
  rows,
  onRefresh,
}: {
  projectId: string;
  competencia: string;
  editScenario: ScenarioKind;
  rows: ProjectSystemCost[];
  onRefresh: () => void;
}) {
  const [name, setName] = useState("");
  const [value, setValue] = useState("");

  const systemsSummary = useMemo(() => {
    const totalCost = rows.reduce((s, r) => s + r.value, 0);
    return { count: rows.length, totalCost };
  }, [rows]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await createSystem(projectId, {
      competencia,
      name: name.trim(),
      value: Number(value),
      scenario: editScenario,
    });
    setName("");
    setValue("");
    onRefresh();
  }

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-3 max-w-xl">
        <h3 className="font-medium text-slate-900">Sistema / licença</h3>
        <input
          placeholder="Nome"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
        <input
          type="number"
          placeholder="Valor mensal"
          required
          min={0}
          step="0.01"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
        <button type="submit" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white">
          Adicionar
        </button>
      </form>

      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-slate-900">Resumo de sistemas</h3>
        <p className="text-sm text-slate-500">Sistemas e licenças nesta competência (valores mensais).</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Total de sistemas cadastrados</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{systemsSummary.count}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Custo total dos sistemas</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
              {formatCurrency(systemsSummary.totalCost)}
            </p>
          </div>
        </div>
      </div>

      <ul className="space-y-2">
        {rows.map((r) => (
          <li
            key={r.id}
            className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3 text-sm"
          >
            <span>
              {r.name} — {formatCurrency(r.value)}
            </span>
            <button
              type="button"
              onClick={async () => {
                await deleteSystem(projectId, r.id);
                onRefresh();
              }}
              className="text-red-600 hover:underline"
            >
              Excluir
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FixedTab({
  projectId,
  competencia,
  editScenario,
  rows,
  onRefresh,
}: {
  projectId: string;
  competencia: string;
  editScenario: ScenarioKind;
  rows: ProjectOperationalFixed[];
  onRefresh: () => void;
}) {
  const [name, setName] = useState("");
  const [value, setValue] = useState("");

  const fixedSummary = useMemo(() => {
    const totalCost = rows.reduce((s, r) => s + r.value, 0);
    return { count: rows.length, totalCost };
  }, [rows]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await createFixedOperational(projectId, {
      competencia,
      name: name.trim(),
      value: Number(value),
      scenario: editScenario,
    });
    setName("");
    setValue("");
    onRefresh();
  }

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-3 max-w-xl">
        <h3 className="font-medium text-slate-900">Custo fixo operacional</h3>
        <input
          placeholder="Nome"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
        <input
          type="number"
          placeholder="Valor mensal"
          required
          min={0}
          step="0.01"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
        <button type="submit" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white">
          Adicionar
        </button>
      </form>

      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-slate-900">Resumo de custos fixos</h3>
        <p className="text-sm text-slate-500">Custos fixos operacionais nesta competência (valores mensais).</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Total de custos fixos</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{fixedSummary.count}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Valor total</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
              {formatCurrency(fixedSummary.totalCost)}
            </p>
          </div>
        </div>
      </div>

      <ul className="space-y-2">
        {rows.map((r) => (
          <li
            key={r.id}
            className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3 text-sm"
          >
            <span>
              {r.name} — {formatCurrency(r.value)}
            </span>
            <button
              type="button"
              onClick={async () => {
                await deleteFixedOperational(projectId, r.id);
                onRefresh();
              }}
              className="text-red-600 hover:underline"
            >
              Excluir
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
