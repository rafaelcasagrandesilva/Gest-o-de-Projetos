import { useEffect, useMemo, useState } from "react";
import {
  createFleetVehicle,
  deleteFleetVehicle,
  listFleetVehicles,
  updateFleetVehicle,
  type FleetVehicle,
  type FleetVehicleType,
} from "@/services/vehicles";
import { listEmployees, fetchCostCenters, type Employee } from "@/services/employees";
import { fetchSettings, type SystemSettings } from "@/services/settings";
import { CostCenterCombo } from "@/components/CostCenterCombo";
import { isAxiosError } from "axios";
import { usePermission } from "@/hooks/usePermission";
import { useAuxiliaryResource } from "@/hooks/useAuxiliaryResource";
import { CollaboratorSelect } from "@/components/CollaboratorSelect";
import { TruncatedCell, TruncatedText } from "@/components/TruncatedText";
import { SortableTh } from "@/components/table";
import { useTableSort } from "@/hooks/useTableSort";
import { FLEET_VEHICLE_SORT_COLUMNS, defaultFleetVehicleSort } from "@/tableSort/vehicles";
import { formatCurrencyOrDash, sumCurrencyOrNull } from "@/utils/currency";
import { Money } from "@/components/Money";

function monthStartIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function typeLabel(t: string): string {
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

/** Null-safe: delega ao util compartilhado (valor redigido → "—"). */
const formatCurrency = formatCurrencyOrDash;

/** Custo fixo mensal por tipo (mesma base das configurações / cálculo operacional). */
function monthlyFixedCostByType(vehicleType: string, s: SystemSettings | null): number {
  if (!s) return 0;
  switch (vehicleType) {
    case "LIGHT":
      return s.vehicle_light_cost;
    case "PICKUP":
      return s.vehicle_pickup_cost;
    case "SEDAN":
      return s.vehicle_sedan_cost;
    default:
      return 0;
  }
}

const FLEET_SUMMARY_TYPES: { key: "LIGHT" | "PICKUP" | "SEDAN"; title: string }[] = [
  { key: "LIGHT", title: "Leve" },
  { key: "PICKUP", title: "Caminhonete" },
  { key: "SEDAN", title: "Pesado" },
];

function currentMonthYYYYMM(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

type FormState = {
  plate: string;
  model: string;
  vehicle_type: FleetVehicleType;
  monthly_cost: number;
  driver_employee_id: string;
  cost_center: string;
  // Centro de Custo temporal: competência (YYYY-MM) a partir da qual o novo centro vale.
  cost_center_effective_month: string;
  // Valor do centro no momento da edição (detecta mudança). undefined = criação.
  _original_cost_center?: string;
  start_date: string;
  end_date: string;
};

const emptyForm: FormState = {
  plate: "",
  model: "",
  vehicle_type: "LIGHT",
  monthly_cost: 0,
  driver_employee_id: "",
  cost_center: "",
  cost_center_effective_month: currentMonthYYYYMM(),
  _original_cost_center: undefined,
  start_date: "",
  end_date: "",
};

function vehicleToForm(v: FleetVehicle): FormState {
  return {
    plate: v.plate,
    model: v.model ?? "",
    vehicle_type: (v.type as FleetVehicleType) || "LIGHT",
    monthly_cost: typeof v.monthly_cost === "number" ? v.monthly_cost : 0,
    driver_employee_id: v.driver_employee_id ?? "",
    cost_center: v.cost_center ?? "",
    cost_center_effective_month: currentMonthYYYYMM(),
    _original_cost_center: v.cost_center ?? "",
    start_date: v.start_date ?? "",
    end_date: v.end_date ?? "",
  };
}

function vehicleCostCenterChanged(form: FormState): boolean {
  return (
    form._original_cost_center !== undefined &&
    form.cost_center.trim() !== form._original_cost_center.trim()
  );
}

export function Vehicles() {
  // Fase 2: verbos específicos. Criar → create; editar → update; excluir → delete.
  const canCreateVehicles = usePermission("vehicles.create");
  const canUpdateVehicles = usePermission("vehicles.update");
  const canDeleteVehicles = usePermission("vehicles.delete");
  // Acesso ao MÓDULO = Visualizar (vehicles.read). Referenciar sozinho não abre a tela.
  const canAccessModule = usePermission("vehicles.read");
  // Dados Sensíveis: só com vehicles.sensitive aparecem custo mensal, cards e totais financeiros.
  const canSeeSensitive = usePermission("vehicles.sensitive");
  const canReferenceEmployees = usePermission("employees.reference");
  const canReferenceCostCenter = usePermission("cost_center.reference");
  const readOnly = !canUpdateVehicles;
  const [items, setItems] = useState<FleetVehicle[]>([]);
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [creating, setCreating] = useState(false);
  // Modal de cadastro (substitui o formulário fixo; mesmo padrão dos demais módulos).
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [referenceCompetencia] = useState(monthStartIso);
  // Filtro por Centro de Custo (server-side, igualdade estrita). "" = Todos.
  const [costCenterFilter, setCostCenterFilter] = useState("");
  // Opções do filtro: derivadas dos Centros de Custo presentes na frota, capturadas no load "Todos"
  // (permanecem estáveis quando um filtro está aplicado). Não exige cost_center.reference.
  const [allCostCenters, setAllCostCenters] = useState<string[]>([]);

  // Recursos AUXILIARES (padrão SGC): condutor (colaboradores) e Centros de Custo. Carregam de forma
  // independente do recurso principal (lista de veículos). Sem permissão, o controle apenas some —
  // a tela NÃO falha.
  const employeesAux = useAuxiliaryResource<Employee[]>(
    () => listEmployees({ competencia: referenceCompetencia }),
    [],
    [referenceCompetencia],
    canReferenceEmployees,
  );
  const costCentersAux = useAuxiliaryResource<string[]>(
    () => fetchCostCenters(),
    [],
    [],
    canReferenceCostCenter,
  );
  const employees = employeesAux.data;
  const costCenterOptions = costCentersAux.data;

  async function reload() {
    const [data, st] = await Promise.all([
      listFleetVehicles({ include_inactive: true, limit: 200, cost_center: costCenterFilter }),
      fetchSettings().catch(() => null),
    ]);
    setItems(data);
    setSettings(st);
  }

  const fleetSummary = useMemo(() => {
    const active = items.filter((v) => v.active);
    const groups: Record<"LIGHT" | "PICKUP" | "SEDAN", Array<number | null | undefined>> = {
      LIGHT: [],
      PICKUP: [],
      SEDAN: [],
    };
    const counts = { LIGHT: 0, PICKUP: 0, SEDAN: 0 };
    for (const v of active) {
      const t = (v.type || "LIGHT") as string;
      if (t === "LIGHT" || t === "PICKUP" || t === "SEDAN") {
        const k = t as keyof typeof groups;
        counts[k] += 1;
        groups[k].push(v.monthly_cost);
      }
    }
    // Custo redigido (null) → total/subtotal null → resumo exibe "—" (não R$ 0,00).
    const byKey = {
      LIGHT: { count: counts.LIGHT, cost: sumCurrencyOrNull(groups.LIGHT) },
      PICKUP: { count: counts.PICKUP, cost: sumCurrencyOrNull(groups.PICKUP) },
      SEDAN: { count: counts.SEDAN, cost: sumCurrencyOrNull(groups.SEDAN) },
    };
    const totalCost = sumCurrencyOrNull(active.map((v) => v.monthly_cost));
    return { totalVehicles: active.length, totalCost, byKey };
  }, [items]);

  const { sortedRows, headerSort } = useTableSort(items, FLEET_VEHICLE_SORT_COLUMNS, {
    defaultCompare: defaultFleetVehicleSort,
  });

  useEffect(() => {
    if (!settings) return;
    setForm((f) => {
      if (f.monthly_cost !== 0) return f;
      return { ...f, monthly_cost: monthlyFixedCostByType(f.vehicle_type, settings) };
    });
  }, [settings]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        // Recurso PRINCIPAL (obrigatório): a lista de veículos, JÁ FILTRADA por Centro de Custo no
        // servidor. Condutor/Centros de Custo são auxiliares e não derrubam esta carga.
        const [fleet, st] = await Promise.all([
          listFleetVehicles({ include_inactive: true, limit: 200, cost_center: costCenterFilter }),
          fetchSettings().catch(() => null),
        ]);
        if (!cancelled) {
          setItems(fleet);
          setSettings(st);
          // Opções do filtro: só recalcula no load "Todos" (sem filtro), para não colapsar a lista.
          if (!costCenterFilter) {
            const ccs = Array.from(
              new Set(fleet.map((v) => (v.cost_center ?? "").trim()).filter((c) => c !== "")),
            ).sort((a, b) => a.localeCompare(b, "pt-BR"));
            setAllCostCenters(ccs);
          }
        }
      } catch (e) {
        if (!cancelled) {
          setError(isAxiosError(e) && e.response?.status === 403 ? "Sem permissão." : "Erro ao listar veículos.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [referenceCompetencia, costCenterFilter]);

  const employeeName = (id: string | null) => {
    if (!id) return "—";
    return employees.find((e) => e.id === id)?.full_name ?? id.slice(0, 8) + "…";
  };

  function openCreate() {
    // Abre o modal com um formulário limpo, pré-preenchendo o custo padrão do tipo (mesma
    // regra do formulário fixo anterior) — nenhuma validação/comportamento de cadastro muda.
    setError(null);
    setForm({
      ...emptyForm,
      monthly_cost: settings ? monthlyFixedCostByType(emptyForm.vehicle_type, settings) : 0,
    });
    setShowCreate(true);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const mc = Number(form.monthly_cost);
      if (Number.isNaN(mc) || mc < 0) {
        setError("Informe um custo mensal válido (R$).");
        setCreating(false);
        return;
      }
      if (!form.start_date) {
        setError("Informe a data de entrada do veículo.");
        setCreating(false);
        return;
      }
      await createFleetVehicle({
        plate: form.plate.trim().toUpperCase(),
        model: form.model.trim() || null,
        vehicle_type: form.vehicle_type,
        monthly_cost: mc,
        driver_employee_id: form.driver_employee_id || null,
        cost_center: form.cost_center.trim() || null,
        is_active: true,
        start_date: form.start_date,
        end_date: form.end_date || null,
      });
      // Sucesso: fecha o modal, reseta o form e atualiza lista+cards (reload preserva o filtro).
      setShowCreate(false);
      setForm(emptyForm);
      await reload();
    } catch (err) {
      if (isAxiosError(err) && err.response?.status === 409) {
        setError("Já existe um veículo com esta placa.");
      } else if (isAxiosError(err) && err.response?.data?.detail) {
        const d = err.response.data.detail;
        setError(typeof d === "string" ? d : "Não foi possível salvar.");
      } else {
        setError("Não foi possível salvar.");
      }
    } finally {
      setCreating(false);
    }
  }

  async function toggleActive(v: FleetVehicle) {
    try {
      if (v.active) {
        // Inativar (saída) exige a data de saída (regra do ciclo de vida).
        const today = new Date().toISOString().slice(0, 10);
        const end = window.prompt(
          "Informe a data de saída do veículo (AAAA-MM-DD):",
          v.end_date ?? today,
        );
        if (!end) return;
        await updateFleetVehicle(v.id, { is_active: false, end_date: end });
      } else {
        await updateFleetVehicle(v.id, { is_active: true });
      }
      await reload();
    } catch (err) {
      if (isAxiosError(err) && typeof err.response?.data?.detail === "string") {
        setError(err.response.data.detail);
      } else {
        setError("Erro ao atualizar status.");
      }
    }
  }

  async function handleSoftDelete(v: FleetVehicle) {
    if (!confirm("Excluir este veículo? Ele deixará de aparecer nos projetos (histórico preservado).")) return;
    try {
      await deleteFleetVehicle(v.id);
      await reload();
    } catch {
      setError("Erro ao excluir.");
    }
  }

  // Acesso ao módulo exige Visualizar (vehicles.read). Sem isso, nada é renderizado.
  if (!canAccessModule) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        Você não tem permissão para acessar o módulo Veículos.
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Veículos</h2>
        <p className="text-sm text-slate-500">
          Custo fixo mensal por veículo (editável); configurações definem apenas o padrão ao escolher o tipo. Consumo e
          combustível nas configurações entram no custo do projeto (km). Condutor opcional.
        </p>
      </div>

      {/* Filtro por Centro de Custo (topo) + botão de cadastro — filtro filtra a frota no servidor. */}
      <div className="flex flex-wrap items-end gap-4">
        <div className="min-w-[14rem]">
          <label className="mb-1 block text-xs font-medium text-slate-600">Centro de Custo (filtro)</label>
          <select
            value={costCenterFilter}
            onChange={(e) => setCostCenterFilter(e.target.value)}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            <option value="">Todos os centros de custo</option>
            {allCostCenters.map((cc) => (
              <option key={cc} value={cc}>
                {cc}
              </option>
            ))}
          </select>
        </div>
        {canCreateVehicles && (
          <button
            type="button"
            onClick={openCreate}
            className="ml-auto rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700"
          >
            + Novo veículo
          </button>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      {showCreate && canCreateVehicles && (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div
          role="dialog"
          aria-modal="true"
          className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-slate-200 bg-white p-6 shadow-lg"
        >
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold text-slate-900">Novo veículo</h3>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              aria-label="Fechar"
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            >
              ✕
            </button>
          </div>
          <form onSubmit={handleCreate} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm text-slate-600">Placa</label>
            <input
              required
              minLength={4}
              maxLength={20}
              value={form.plate}
              onChange={(e) => setForm((f) => ({ ...f, plate: e.target.value }))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm uppercase"
              placeholder="ABC1D23"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Modelo</label>
            <input
              value={form.model}
              onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Centro de Custo</label>
            <CostCenterCombo
              value={form.cost_center}
              onChange={(v) => setForm((f) => ({ ...f, cost_center: v }))}
              options={costCenterOptions}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            {vehicleCostCenterChanged(form) ? (
              <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                <label className="mb-1 block text-xs font-medium text-amber-900">
                  Vigente a partir de qual competência?
                </label>
                <input
                  type="month"
                  value={form.cost_center_effective_month}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, cost_center_effective_month: e.target.value }))
                  }
                  className="w-full rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm"
                />
                <p className="mt-1 text-xs text-amber-800/80">
                  Competências anteriores mantêm o Centro de Custo anterior (histórico preservado).
                </p>
              </div>
            ) : null}
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Tipo</label>
            <select
              value={form.vehicle_type}
              onChange={(e) => {
                const vt = e.target.value as FleetVehicleType;
                setForm((f) => ({
                  ...f,
                  vehicle_type: vt,
                  monthly_cost: settings ? monthlyFixedCostByType(vt, settings) : f.monthly_cost,
                }));
              }}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="LIGHT">Leve</option>
              <option value="PICKUP">Pickup</option>
              <option value="SEDAN">Sedan</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Custo mensal (R$)</label>
            <input
              required
              type="number"
              min={0}
              step={0.01}
              value={form.monthly_cost === 0 ? "" : form.monthly_cost}
              onChange={(e) => {
                const raw = e.target.value;
                setForm((f) => ({
                  ...f,
                  monthly_cost: raw === "" ? 0 : Number(raw),
                }));
              }}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
              placeholder="0,00"
            />
            <p className="mt-1 text-xs text-slate-500">Padrão do tipo nas configurações; edite se necessário.</p>
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Entrada</label>
            <input
              type="date"
              value={form.start_date}
              onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))}
              disabled={!canCreateVehicles}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div className="sm:col-span-2">
            <CollaboratorSelect
              label="Condutor"
              value={form.driver_employee_id}
              selectedName={employees.find((e) => e.id === form.driver_employee_id)?.full_name ?? null}
              onChange={(id) => setForm((f) => ({ ...f, driver_employee_id: id }))}
              disabled={!canCreateVehicles}
              placeholder="Digite para buscar…"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={() => setShowCreate(false)}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={creating}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
          >
            {creating ? "Salvando…" : "Cadastrar"}
          </button>
        </div>
          </form>
        </div>
      </div>
      )}

      {loading ? (
        <div className="text-slate-500">Carregando…</div>
      ) : (
        <div className="space-y-5">
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-slate-900">Resumo da frota</h3>
            <p className="text-sm text-slate-500">
              Apenas veículos ativos. Soma do custo fixo mensal cadastrado em cada veículo.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Total de veículos ativos</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{fleetSummary.totalVehicles}</p>
              </div>
              {/* Cartão financeiro: só com vehicles.sensitive. */}
              {canSeeSensitive && (
                <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                  <p className="text-sm font-medium text-slate-500">Custo total da frota</p>
                  <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
                    {formatCurrency(fleetSummary.totalCost)}
                  </p>
                </div>
              )}
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              {FLEET_SUMMARY_TYPES.map(({ key, title }) => {
                const row = fleetSummary.byKey[key];
                return (
                  <div key={key} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                    <p className="text-sm font-medium text-slate-500">{title}</p>
                    <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{row.count}</p>
                    {/* Custo por categoria: só com vehicles.sensitive. A contagem (não financeira) permanece. */}
                    {canSeeSensitive ? (
                      <>
                        <p className="mt-1 text-sm tabular-nums text-slate-600">{formatCurrency(row.cost)}</p>
                        <p className="mt-0.5 text-xs text-slate-500">veículos · custo mensal do tipo</p>
                      </>
                    ) : (
                      <p className="mt-0.5 text-xs text-slate-500">veículos ativos</p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="overflow-x-auto overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50/80">
              <tr>
                <SortableTh label="Placa" column="plate" variant="standard" {...headerSort} />
                <SortableTh label="Modelo" column="model" variant="standard" {...headerSort} />
                <SortableTh label="Tipo" column="type" variant="standard" {...headerSort} />
                {/* Centro de Custo: informação NÃO financeira — sempre visível. */}
                <SortableTh label="Centro de Custo" column="cost_center" variant="standard" {...headerSort} />
                {canSeeSensitive && (
                  <SortableTh label="Custo mensal" column="monthly_cost" variant="standard" align="right" {...headerSort} />
                )}
                <SortableTh label="Condutor" column="driver" variant="standard" {...headerSort} />
                <SortableTh label="Ativo" column="active" variant="standard" {...headerSort} />
                {(canUpdateVehicles || canDeleteVehicles) && <th className="px-4 py-3" />}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((v) => (
                <tr key={v.id} className="border-b border-slate-50">
                  <td className="px-4 py-3 font-medium tabular-nums">{v.plate}</td>
                  <td className="min-w-0 max-w-[280px] px-4 py-3 align-middle text-slate-600">
                    <TruncatedCell value={v.model} maxWidthClass="max-w-[280px]" />
                  </td>
                  <td className="px-4 py-3">{typeLabel(v.type)}</td>
                  <td className="min-w-0 max-w-[220px] px-4 py-3 align-middle text-slate-600">
                    <TruncatedCell value={v.cost_center || "—"} maxWidthClass="max-w-[220px]" />
                  </td>
                  {canSeeSensitive && (
                    <td className="px-4 py-3 font-medium">
                      <Money value={v.monthly_cost} />
                    </td>
                  )}
                  <td className="min-w-0 max-w-[260px] px-4 py-3 align-middle">
                    <TruncatedText maxWidthClass="max-w-[260px]">
                      {v.driver_name ?? employeeName(v.driver_employee_id)}
                    </TruncatedText>
                  </td>
                  <td className="px-4 py-3">
                    {readOnly ? (
                      <span>{v.active ? "Sim" : "Não"}</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => toggleActive(v)}
                        className="text-indigo-600 hover:underline"
                      >
                        {v.active ? "Sim" : "Não"}
                      </button>
                    )}
                  </td>
                  {(canUpdateVehicles || canDeleteVehicles) && (
                    <td className="px-4 py-3 text-right">
                      {canUpdateVehicles && (
                        <button
                          type="button"
                          onClick={() => setEditingId(editingId === v.id ? null : v.id)}
                          className="text-sm text-slate-600 hover:text-slate-900"
                        >
                          {editingId === v.id ? "Fechar" : "Editar"}
                        </button>
                      )}
                      {/* Excluir: aparece SÓ com vehicles.delete, independente de Editar. */}
                      {v.active && canDeleteVehicles && (
                        <button
                          type="button"
                          onClick={() => handleSoftDelete(v)}
                          className={`text-sm text-red-600 hover:underline${canUpdateVehicles ? " ml-3" : ""}`}
                        >
                          Excluir
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </div>
      )}

      {editingId && !readOnly && (
        <EditVehiclePanel
          vehicle={items.find((x) => x.id === editingId)!}
          employees={employees}
          settings={settings}
          costCenterOptions={costCenterOptions}
          onCancel={() => setEditingId(null)}
          onSaved={async () => {
            setEditingId(null);
            await reload();
          }}
        />
      )}
    </div>
  );
}

function EditVehiclePanel({
  vehicle,
  employees,
  settings,
  costCenterOptions,
  onCancel,
  onSaved,
}: {
  vehicle: FleetVehicle;
  employees: Employee[];
  settings: SystemSettings | null;
  costCenterOptions: string[];
  onCancel: () => void;
  onSaved: () => Promise<void>;
}) {
  const [form, setForm] = useState<FormState>(() => vehicleToForm(vehicle));
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    setForm(vehicleToForm(vehicle));
    setLocalError(null);
  }, [vehicle]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setLocalError(null);
    try {
      const mc = Number(form.monthly_cost);
      if (Number.isNaN(mc) || mc < 0) {
        setLocalError("Informe um custo mensal válido (R$).");
        setSaving(false);
        return;
      }
      await updateFleetVehicle(vehicle.id, {
        plate: form.plate.trim().toUpperCase(),
        model: form.model.trim() || null,
        vehicle_type: form.vehicle_type,
        monthly_cost: mc,
        driver_employee_id: form.driver_employee_id || null,
        cost_center: form.cost_center.trim() || null,
        start_date: form.start_date || null,
        // Só envia a vigência quando o Centro de Custo mudou (senão o backend não abre histórico).
        ...(vehicleCostCenterChanged(form) && form.cost_center_effective_month
          ? { cost_center_effective_date: `${form.cost_center_effective_month}-01` }
          : {}),
      });
      await onSaved();
    } catch (err) {
      if (isAxiosError(err) && err.response?.data?.detail) {
        const d = err.response.data.detail;
        const msg =
          typeof d === "string"
            ? d
            : Array.isArray(d)
              ? d.map((x: { msg?: string }) => x.msg ?? "").join(" ")
              : "Erro ao salvar.";
        setLocalError(msg);
      } else if (isAxiosError(err) && err.response?.status === 409) {
        setLocalError("Já existe um veículo com esta placa.");
      } else {
        setLocalError("Erro ao salvar.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-2xl rounded-xl border border-slate-200 bg-slate-50/80 p-6 shadow-sm">
      <h3 className="font-medium text-slate-900">Editar veículo</h3>
      <p className="mt-1 text-xs text-slate-500">
        Altere placa, modelo, tipo, custo mensal ou condutor. A placa deve ser única. Ao mudar o tipo, o custo pode ser
        preenchido com o padrão das configurações.
      </p>
      {localError && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {localError}
        </div>
      )}
      <form onSubmit={save} className="mt-4 space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm text-slate-600">Placa</label>
            <input
              required
              minLength={4}
              maxLength={20}
              value={form.plate}
              onChange={(e) => setForm((f) => ({ ...f, plate: e.target.value }))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm uppercase"
              placeholder="ABC1D23"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Modelo</label>
            <input
              value={form.model}
              onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Centro de Custo</label>
            <CostCenterCombo
              value={form.cost_center}
              onChange={(v) => setForm((f) => ({ ...f, cost_center: v }))}
              options={costCenterOptions}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            {vehicleCostCenterChanged(form) ? (
              <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                <label className="mb-1 block text-xs font-medium text-amber-900">
                  Vigente a partir de qual competência?
                </label>
                <input
                  type="month"
                  value={form.cost_center_effective_month}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, cost_center_effective_month: e.target.value }))
                  }
                  className="w-full rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm"
                />
                <p className="mt-1 text-xs text-amber-800/80">
                  Competências anteriores mantêm o Centro de Custo anterior (histórico preservado).
                </p>
              </div>
            ) : null}
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Tipo</label>
            <select
              value={form.vehicle_type}
              onChange={(e) => {
                const vt = e.target.value as FleetVehicleType;
                setForm((f) => ({
                  ...f,
                  vehicle_type: vt,
                  monthly_cost: settings ? monthlyFixedCostByType(vt, settings) : f.monthly_cost,
                }));
              }}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="LIGHT">Leve</option>
              <option value="PICKUP">Pickup</option>
              <option value="SEDAN">Sedan</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Custo mensal (R$)</label>
            <input
              required
              type="number"
              min={0}
              step={0.01}
              value={form.monthly_cost === 0 ? "" : form.monthly_cost}
              onChange={(e) => {
                const raw = e.target.value;
                setForm((f) => ({
                  ...f,
                  monthly_cost: raw === "" ? 0 : Number(raw),
                }));
              }}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Entrada</label>
            <input
              type="date"
              value={form.start_date}
              onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))}
              disabled={saving}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            {form.end_date ? (
              <p className="mt-1 text-xs text-slate-500">Saída: {form.end_date}</p>
            ) : null}
          </div>
          <div className="sm:col-span-2">
            <CollaboratorSelect
              label="Condutor"
              value={form.driver_employee_id}
              selectedName={employees.find((e) => e.id === form.driver_employee_id)?.full_name ?? null}
              onChange={(id) => setForm((f) => ({ ...f, driver_employee_id: id }))}
              disabled={saving}
              placeholder="Digite para buscar…"
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {saving ? "Salvando…" : "Salvar alterações"}
          </button>
          <button type="button" onClick={onCancel} className="rounded-lg border border-slate-300 px-4 py-2 text-sm">
            Cancelar
          </button>
        </div>
      </form>
    </div>
  );
}
