import { useEffect, useMemo, useState } from "react";
import {
  createFleetVehicle,
  deleteFleetVehicle,
  listFleetVehicles,
  updateFleetVehicle,
  type FleetVehicle,
  type FleetVehicleType,
} from "@/services/vehicles";
import { listEmployees, type Employee } from "@/services/employees";
import { fetchSettings, type SystemSettings } from "@/services/settings";
import { isAxiosError } from "axios";
import { useConsultaReadOnly } from "@/hooks/useConsultaReadOnly";
import { useGestorGlobalReadOnly } from "@/hooks/useGestorGlobalReadOnly";

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

function formatCurrency(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

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

type FormState = {
  plate: string;
  model: string;
  vehicle_type: FleetVehicleType;
  monthly_cost: number;
  driver_employee_id: string;
};

const emptyForm: FormState = {
  plate: "",
  model: "",
  vehicle_type: "LIGHT",
  monthly_cost: 0,
  driver_employee_id: "",
};

function vehicleToForm(v: FleetVehicle): FormState {
  return {
    plate: v.plate,
    model: v.model ?? "",
    vehicle_type: (v.type as FleetVehicleType) || "LIGHT",
    monthly_cost: typeof v.monthly_cost === "number" ? v.monthly_cost : 0,
    driver_employee_id: v.driver_employee_id ?? "",
  };
}

export function Vehicles() {
  const readOnly = useConsultaReadOnly() || useGestorGlobalReadOnly();
  const [items, setItems] = useState<FleetVehicle[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [referenceCompetencia] = useState(monthStartIso);

  async function reload() {
    const [data, st] = await Promise.all([
      listFleetVehicles({ active_only: false, limit: 200 }),
      fetchSettings().catch(() => null),
    ]);
    setItems(data);
    setSettings(st);
  }

  const fleetSummary = useMemo(() => {
    const active = items.filter((v) => v.active);
    const byKey = {
      LIGHT: { count: 0, cost: 0 },
      PICKUP: { count: 0, cost: 0 },
      SEDAN: { count: 0, cost: 0 },
    };
    let totalCost = 0;
    for (const v of active) {
      const t = (v.type || "LIGHT") as string;
      const unit = typeof v.monthly_cost === "number" ? v.monthly_cost : 0;
      totalCost += unit;
      if (t === "LIGHT" || t === "PICKUP" || t === "SEDAN") {
        const k = t as keyof typeof byKey;
        byKey[k].count += 1;
        byKey[k].cost += unit;
      }
    }
    return { totalVehicles: active.length, totalCost, byKey };
  }, [items]);

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
        const [fleet, em, st] = await Promise.all([
          listFleetVehicles({ active_only: false, limit: 200 }),
          listEmployees({ competencia: referenceCompetencia }).catch(() => [] as Employee[]),
          fetchSettings().catch(() => null),
        ]);
        if (!cancelled) {
          setItems(fleet);
          setEmployees(em);
          setSettings(st);
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
  }, [referenceCompetencia]);

  const employeeName = (id: string | null) => {
    if (!id) return "—";
    return employees.find((e) => e.id === id)?.full_name ?? id.slice(0, 8) + "…";
  };

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
      await createFleetVehicle({
        plate: form.plate.trim().toUpperCase(),
        model: form.model.trim() || null,
        vehicle_type: form.vehicle_type,
        monthly_cost: mc,
        driver_employee_id: form.driver_employee_id || null,
        is_active: true,
      });
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
      await updateFleetVehicle(v.id, { is_active: !v.active });
      await reload();
    } catch {
      setError("Erro ao atualizar status.");
    }
  }

  async function handleSoftDelete(v: FleetVehicle) {
    if (!confirm("Inativar este veículo? Ele deixará de aparecer nos projetos.")) return;
    try {
      await deleteFleetVehicle(v.id);
      await reload();
    } catch {
      setError("Erro ao inativar.");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Veículos</h2>
        <p className="text-sm text-slate-500">
          Custo fixo mensal por veículo (editável); configurações definem apenas o padrão ao escolher o tipo. Consumo e
          combustível nas configurações entram no custo do projeto (km). Condutor opcional.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      {!readOnly && (
      <form
        onSubmit={handleCreate}
        className="max-w-2xl space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h3 className="font-medium text-slate-900">Novo veículo</h3>
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
          <div className="sm:col-span-2">
            <label className="mb-1 block text-sm text-slate-600">Condutor</label>
            <select
              value={form.driver_employee_id}
              onChange={(e) => setForm((f) => ({ ...f, driver_employee_id: e.target.value }))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="">—</option>
              {employees
                .filter((e) => e.is_active)
                .map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.full_name}
                  </option>
                ))}
            </select>
          </div>
        </div>
        <button
          type="submit"
          disabled={creating}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          {creating ? "Salvando…" : "Cadastrar"}
        </button>
      </form>
      )}

      {loading ? (
        <div className="text-slate-500">Carregando…</div>
      ) : (
        <div className="space-y-6">
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
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Custo total da frota</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
                  {formatCurrency(fleetSummary.totalCost)}
                </p>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              {FLEET_SUMMARY_TYPES.map(({ key, title }) => {
                const row = fleetSummary.byKey[key];
                return (
                  <div key={key} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                    <p className="text-sm font-medium text-slate-500">{title}</p>
                    <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{row.count}</p>
                    <p className="mt-1 text-sm tabular-nums text-slate-600">{formatCurrency(row.cost)}</p>
                    <p className="mt-0.5 text-xs text-slate-500">veículos · custo mensal do tipo</p>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="overflow-x-auto overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50/80">
              <tr>
                <th className="px-4 py-3 font-medium text-slate-600">Placa</th>
                <th className="px-4 py-3 font-medium text-slate-600">Modelo</th>
                <th className="px-4 py-3 font-medium text-slate-600">Tipo</th>
                <th className="px-4 py-3 font-medium text-slate-600">Custo mensal</th>
                <th className="px-4 py-3 font-medium text-slate-600">Condutor</th>
                <th className="px-4 py-3 font-medium text-slate-600">Ativo</th>
                {!readOnly && <th className="px-4 py-3" />}
              </tr>
            </thead>
            <tbody>
              {items.map((v) => (
                <tr key={v.id} className="border-b border-slate-50">
                  <td className="px-4 py-3 font-medium tabular-nums">{v.plate}</td>
                  <td className="px-4 py-3 text-slate-600">{v.model ?? "—"}</td>
                  <td className="px-4 py-3">{typeLabel(v.type)}</td>
                  <td className="px-4 py-3 font-medium tabular-nums">{formatCurrency(v.monthly_cost ?? 0)}</td>
                  <td className="px-4 py-3">{v.driver_name ?? employeeName(v.driver_employee_id)}</td>
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
                  {!readOnly && (
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setEditingId(editingId === v.id ? null : v.id)}
                        className="text-sm text-slate-600 hover:text-slate-900"
                      >
                        {editingId === v.id ? "Fechar" : "Editar"}
                      </button>
                      {v.active && (
                        <button
                          type="button"
                          onClick={() => handleSoftDelete(v)}
                          className="ml-3 text-sm text-red-600 hover:underline"
                        >
                          Inativar
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
  onCancel,
  onSaved,
}: {
  vehicle: FleetVehicle;
  employees: Employee[];
  settings: SystemSettings | null;
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
          <div className="sm:col-span-2">
            <label className="mb-1 block text-sm text-slate-600">Condutor</label>
            <select
              value={form.driver_employee_id}
              onChange={(e) => setForm((f) => ({ ...f, driver_employee_id: e.target.value }))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="">—</option>
              {employees
                .filter((e) => e.is_active)
                .map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.full_name}
                  </option>
                ))}
            </select>
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
