import { Fragment, useEffect, useMemo, useState } from "react";
import { listFleetVehicles, type FleetVehicle } from "@/services/vehicles";
import { Link, useParams } from "react-router-dom";
import { getProject, type Project } from "@/services/projects";
import {
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

function fuelLabel(f: string): string {
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

export function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [competencia, setCompetencia] = useState(() => normalizeCompetencia(monthStart()));
  const [tab, setTab] = useState<Tab>("labor");
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [laborDetails, setLaborDetails] = useState<ProjectLaborDetail[]>([]);
  const [vehicles, setVehicles] = useState<ProjectVehicle[]>([]);
  const [systems, setSystems] = useState<ProjectSystemCost[]>([]);
  const [fixed, setFixed] = useState<ProjectOperationalFixed[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const competenciaApi = useMemo(() => normalizeCompetencia(competencia), [competencia]);

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

  async function reloadTab() {
    if (!projectId) return;
    setError(null);
    try {
      if (tab === "labor") setLaborDetails(await fetchLaborDetails(projectId, competenciaApi));
      if (tab === "vehicles") setVehicles(await listVehicles(projectId, competenciaApi));
      if (tab === "systems") setSystems(await listSystems(projectId, competenciaApi));
      if (tab === "fixed") setFixed(await listFixedOperational(projectId, competenciaApi));
    } catch (e) {
      if (isAxiosError(e) && e.response?.status === 403) {
        setError("Sem acesso a este projeto.");
      } else {
        setError("Erro ao carregar dados.");
      }
    }
  }

  useEffect(() => {
    reloadTab();
  }, [projectId, competenciaApi, tab]);

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
          <p className="text-sm text-slate-500">Estrutura de custo operacional por competência</p>
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
          employees={employees}
          rows={laborDetails}
          onRefresh={reloadTab}
        />
      )}
      {tab === "vehicles" && (
        <VehiclesTab projectId={projectId} competencia={competenciaApi} rows={vehicles} onRefresh={reloadTab} />
      )}
      {tab === "systems" && (
        <SystemsTab projectId={projectId} competencia={competenciaApi} rows={systems} onRefresh={reloadTab} />
      )}
      {tab === "fixed" && (
        <FixedTab projectId={projectId} competencia={competenciaApi} rows={fixed} onRefresh={reloadTab} />
      )}
    </div>
  );
}

function LaborTab({
  projectId,
  competencia,
  employees,
  rows,
  onRefresh,
}: {
  projectId: string;
  competencia: string;
  employees: Employee[];
  rows: ProjectLaborDetail[];
  onRefresh: () => void;
}) {
  const [employeeId, setEmployeeId] = useState("");
  const [allocationPct, setAllocationPct] = useState("100");
  const [openDetailId, setOpenDetailId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

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

      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-slate-900">Participação na mão de obra</h3>
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
                      <td className="px-4 py-3 font-medium text-slate-900">{r.name}</td>
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
  rows,
  onRefresh,
}: {
  projectId: string;
  competencia: string;
  rows: ProjectVehicle[];
  onRefresh: () => void;
}) {
  const [fleet, setFleet] = useState<FleetVehicle[]>([]);
  const [fleetVid, setFleetVid] = useState("");
  const [ft, setFt] = useState<"ETHANOL" | "GASOLINE" | "DIESEL">("GASOLINE");
  const [km, setKm] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editKm, setEditKm] = useState("");
  const [editFt, setEditFt] = useState<"ETHANOL" | "GASOLINE" | "DIESEL">("GASOLINE");
  const [editVid, setEditVid] = useState("");

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

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!fleetVid) return;
    await createVehicle(projectId, {
      competencia,
      vehicle_id: fleetVid,
      fuel_type: ft,
      km_per_month: Number(km),
    });
    setFleetVid("");
    setKm("");
    onRefresh();
  }

  function startEdit(r: ProjectVehicle) {
    setEditingId(r.id);
    setEditKm(String(r.km_per_month));
    setEditFt(r.fuel_type as typeof editFt);
    setEditVid(r.vehicle_id);
  }

  async function saveEdit() {
    if (!editingId) return;
    await updateProjectVehicleAllocation(projectId, editingId, {
      vehicle_id: editVid,
      fuel_type: editFt,
      km_per_month: Number(editKm),
    });
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

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="max-w-xl space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="font-medium text-slate-900">Alocar veículo da frota</h3>
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
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-xs text-slate-500">Combustível</label>
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
        <button
          type="submit"
          disabled={!fleetVid}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          Adicionar
        </button>
      </form>

      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-slate-900">Resumo dos veículos no projeto</h3>
        <p className="text-sm text-slate-500">
          Veículos vinculados nesta competência. Custos são o valor mensal já calculado por alocação (tipo, km e
          combustível).
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
              <th className="px-4 py-3 font-medium text-slate-600">KM</th>
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
              rows.map((r) =>
                editingId === r.id ? (
                  <tr key={r.id} className="border-b border-slate-50 bg-amber-50/40">
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
                    <td className="px-4 py-3 align-top">
                      <label className="text-xs text-slate-500">KM</label>
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
                  <tr key={r.id} className="border-b border-slate-50">
                    <td className="px-4 py-3 font-medium tabular-nums">{r.plate}</td>
                    <td className="px-4 py-3 text-slate-600">{r.model ?? "—"}</td>
                    <td className="px-4 py-3">{r.driver_name ?? "—"}</td>
                    <td className="px-4 py-3 tabular-nums">{r.km_per_month}</td>
                    <td className="px-4 py-3">{fuelLabel(r.fuel_type)}</td>
                    <td className="px-4 py-3 font-medium tabular-nums">{money(r.monthly_cost)}</td>
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
                )
              )
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
  rows,
  onRefresh,
}: {
  projectId: string;
  competencia: string;
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
    await createSystem(projectId, { competencia, name: name.trim(), value: Number(value) });
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
  rows,
  onRefresh,
}: {
  projectId: string;
  competencia: string;
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
    await createFixedOperational(projectId, { competencia, name: name.trim(), value: Number(value) });
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
