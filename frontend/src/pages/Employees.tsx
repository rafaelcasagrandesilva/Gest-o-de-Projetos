import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import {
  createEmployee,
  deleteEmployee,
  listEmployees,
  parseCompetenciaYm,
  previewCltCost,
  updateEmployee,
  type CLTCostPreviewResponse,
  type Employee,
  type EmployeeCreate,
} from "@/services/employees";
import { isAxiosError } from "axios";
import { useConsultaReadOnly } from "@/hooks/useConsultaReadOnly";
import { useGestorGlobalReadOnly } from "@/hooks/useGestorGlobalReadOnly";

function monthStartIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

type FormState = {
  full_name: string;
  email: string | null;
  role_title: string | null;
  employment_type: "CLT" | "PJ";
  salary_base: number | null;
  additional_costs: number | null;
  has_periculosidade: boolean;
  has_adicional_dirigida: boolean;
  extra_hours_50: number;
  extra_hours_70: number;
  extra_hours_100: number;
  pj_hours_per_month: number | null;
  pj_additional_cost: number;
  is_active: boolean;
};

const emptyForm: FormState = {
  full_name: "",
  email: null,
  role_title: null,
  employment_type: "CLT",
  salary_base: null,
  additional_costs: null,
  has_periculosidade: false,
  has_adicional_dirigida: false,
  extra_hours_50: 0,
  extra_hours_70: 0,
  extra_hours_100: 0,
  pj_hours_per_month: null,
  pj_additional_cost: 0,
  is_active: true,
};

function employeeToForm(emp: Employee): FormState {
  return {
    full_name: emp.full_name,
    email: emp.email,
    role_title: emp.role_title,
    employment_type: emp.employment_type === "PJ" ? "PJ" : "CLT",
    salary_base: emp.salary_base,
    additional_costs: emp.additional_costs,
    has_periculosidade: emp.has_periculosidade ?? false,
    has_adicional_dirigida: emp.has_adicional_dirigida ?? false,
    extra_hours_50: emp.extra_hours_50 ?? 0,
    extra_hours_70: emp.extra_hours_70 ?? 0,
    extra_hours_100: emp.extra_hours_100 ?? 0,
    pj_hours_per_month: emp.pj_hours_per_month,
    pj_additional_cost: emp.pj_additional_cost ?? 0,
    is_active: emp.is_active,
  };
}

function formToPayload(form: FormState, referenceCompetencia: string): EmployeeCreate {
  return {
    full_name: form.full_name.trim(),
    email: form.email?.trim() || null,
    role_title: form.role_title?.trim() || null,
    employment_type: form.employment_type,
    salary_base: form.salary_base,
    additional_costs: form.additional_costs,
    is_active: form.is_active,
    has_periculosidade: form.has_periculosidade,
    has_adicional_dirigida: form.has_adicional_dirigida,
    extra_hours_50: form.extra_hours_50,
    extra_hours_70: form.extra_hours_70,
    extra_hours_100: form.extra_hours_100,
    pj_hours_per_month: form.pj_hours_per_month,
    pj_additional_cost: form.pj_additional_cost,
    cost_reference_competencia: referenceCompetencia,
  };
}

function formatMoney(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatCurrency(n: number): string {
  return formatMoney(n);
}

function pjEstimatedTotal(form: FormState): number | null {
  if (form.employment_type !== "PJ") return null;
  const sb = form.salary_base;
  if (sb == null) return null;
  const h = form.pj_hours_per_month;
  const base = h != null && h > 0 ? sb * h : sb;
  return base + (form.pj_additional_cost || 0);
}

function useCltLivePreview(form: FormState, referenceCompetencia: string) {
  const [preview, setPreview] = useState<CLTCostPreviewResponse | null>(null);
  const { year, month } = parseCompetenciaYm(referenceCompetencia);
  useEffect(() => {
    if (form.employment_type !== "CLT") {
      setPreview(null);
      return;
    }
    const sb = form.salary_base;
    if (sb == null || sb <= 0) {
      setPreview(null);
      return;
    }
    const t = setTimeout(() => {
      previewCltCost({
        salary_base: sb,
        has_periculosidade: form.has_periculosidade,
        has_adicional_dirigida: form.has_adicional_dirigida,
        extra_hours_50: form.extra_hours_50,
        extra_hours_70: form.extra_hours_70,
        extra_hours_100: form.extra_hours_100,
        additional_costs: form.additional_costs,
        year,
        month,
      })
        .then(setPreview)
        .catch(() => setPreview(null));
    }, 400);
    return () => clearTimeout(t);
  }, [
    form.employment_type,
    form.salary_base,
    form.additional_costs,
    form.has_periculosidade,
    form.has_adicional_dirigida,
    form.extra_hours_50,
    form.extra_hours_70,
    form.extra_hours_100,
    year,
    month,
    referenceCompetencia,
  ]);
  return preview;
}

function EmployeeFields({
  form,
  setForm,
  idPrefix,
  referenceCompetencia,
}: {
  form: FormState;
  setForm: Dispatch<SetStateAction<FormState>>;
  idPrefix: string;
  referenceCompetencia: string;
}) {
  const cltPreview = useCltLivePreview(form, referenceCompetencia);
  const pjTotal = pjEstimatedTotal(form);

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <label htmlFor={`${idPrefix}-name`} className="mb-1 block text-sm text-slate-600">
          Nome
        </label>
        <input
          id={`${idPrefix}-name`}
          required
          value={form.full_name}
          onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-role`} className="mb-1 block text-sm text-slate-600">
          Cargo
        </label>
        <input
          id={`${idPrefix}-role`}
          value={form.role_title ?? ""}
          onChange={(e) => setForm((f) => ({ ...f, role_title: e.target.value || null }))}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-type`} className="mb-1 block text-sm text-slate-600">
          Tipo
        </label>
        <select
          id={`${idPrefix}-type`}
          value={form.employment_type}
          onChange={(e) => setForm((f) => ({ ...f, employment_type: e.target.value as "CLT" | "PJ" }))}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        >
          <option value="CLT">CLT</option>
          <option value="PJ">PJ</option>
        </select>
      </div>

      {form.employment_type === "CLT" ? (
        <>
          <div>
            <label htmlFor={`${idPrefix}-salary`} className="mb-1 block text-sm text-slate-600">
              Salário base (R$)
            </label>
            <input
              id={`${idPrefix}-salary`}
              type="number"
              min={0}
              step="0.01"
              required
              value={form.salary_base ?? ""}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  salary_base: e.target.value === "" ? null : Number(e.target.value),
                }))
              }
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-add`} className="mb-1 block text-sm text-slate-600">
              Outros custos adicionais (R$, opcional)
            </label>
            <input
              id={`${idPrefix}-add`}
              type="number"
              min={0}
              step="0.01"
              value={form.additional_costs ?? ""}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  additional_costs: e.target.value === "" ? null : Number(e.target.value),
                }))
              }
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div className="sm:col-span-2 flex flex-wrap gap-6">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={form.has_periculosidade}
                onChange={(e) => setForm((f) => ({ ...f, has_periculosidade: e.target.checked }))}
              />
              Periculosidade (+30% sobre salário base)
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={form.has_adicional_dirigida}
                onChange={(e) => setForm((f) => ({ ...f, has_adicional_dirigida: e.target.checked }))}
              />
              Adicional dirigida (R$ 209,24)
            </label>
          </div>
          <div>
            <label htmlFor={`${idPrefix}-h50`} className="mb-1 block text-sm text-slate-600">
              Horas extras 50%
            </label>
            <input
              id={`${idPrefix}-h50`}
              type="number"
              min={0}
              step="0.01"
              value={form.extra_hours_50 || ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, extra_hours_50: e.target.value === "" ? 0 : Number(e.target.value) }))
              }
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-h70`} className="mb-1 block text-sm text-slate-600">
              Horas extras 70%
            </label>
            <input
              id={`${idPrefix}-h70`}
              type="number"
              min={0}
              step="0.01"
              value={form.extra_hours_70 || ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, extra_hours_70: e.target.value === "" ? 0 : Number(e.target.value) }))
              }
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-h100`} className="mb-1 block text-sm text-slate-600">
              Horas extras 100%
            </label>
            <input
              id={`${idPrefix}-h100`}
              type="number"
              min={0}
              step="0.01"
              value={form.extra_hours_100 || ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, extra_hours_100: e.target.value === "" ? 0 : Number(e.target.value) }))
              }
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div className="sm:col-span-2 rounded-lg border border-emerald-200 bg-emerald-50/60 px-4 py-3">
            <p className="text-xs font-medium text-emerald-900">Mês de referência do cálculo</p>
            <p className="text-sm font-semibold text-emerald-950">{referenceCompetencia.slice(0, 7)}</p>
            <p className="mt-2 text-xs font-medium text-emerald-900">Custo total mensal estimado (CLT)</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-emerald-950">
              {cltPreview ? formatMoney(cltPreview.total_cost) : "—"}
            </p>
            {cltPreview ? (
              <p className="mt-1 text-xs text-emerald-800">
                Inclui encargos (taxa nas configurações), VR × {cltPreview.business_days} dia(s) úteis no mês e horas
                extras.
              </p>
            ) : (
              <p className="mt-1 text-xs text-emerald-800">Informe o salário base para calcular.</p>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="sm:col-span-2">
            <label htmlFor={`${idPrefix}-pj-h`} className="mb-1 block text-sm text-slate-600">
              Horas por mês (opcional)
            </label>
            <input
              id={`${idPrefix}-pj-h`}
              type="number"
              min={0}
              step="0.01"
              placeholder="Vazio = valor mensal fixo abaixo"
              value={form.pj_hours_per_month ?? ""}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  pj_hours_per_month: e.target.value === "" ? null : Number(e.target.value),
                }))
              }
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <p className="mt-1 text-xs text-slate-500">
              Se preencher: custo = valor hora × horas. Se vazio: o valor abaixo é o mensal fixo.
            </p>
          </div>
          <div className="sm:col-span-2">
            <label htmlFor={`${idPrefix}-pj-val`} className="mb-1 block text-sm text-slate-600">
              {form.pj_hours_per_month != null && form.pj_hours_per_month > 0
                ? "Valor hora (R$)"
                : "Valor mensal fixo (R$)"}
            </label>
            <input
              id={`${idPrefix}-pj-val`}
              type="number"
              min={0}
              step="0.01"
              value={form.salary_base ?? ""}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  salary_base: e.target.value === "" ? null : Number(e.target.value),
                }))
              }
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div className="sm:col-span-2">
            <label htmlFor={`${idPrefix}-pj-add`} className="mb-1 block text-sm text-slate-600">
              Ajuda de custo (R$, opcional)
            </label>
            <input
              id={`${idPrefix}-pj-add`}
              type="number"
              min={0}
              step="0.01"
              value={form.pj_additional_cost || ""}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  pj_additional_cost: e.target.value === "" ? 0 : Number(e.target.value),
                }))
              }
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <p className="mt-1 text-xs text-slate-500">Valores recorrentes além do contrato (ex.: benefícios, reembolsos fixos).</p>
          </div>
          <div className="sm:col-span-2 rounded-lg border border-sky-200 bg-sky-50/60 px-4 py-3">
            <p className="text-xs font-medium text-sky-900">Custo total mensal (PJ)</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-sky-950">
              {pjTotal != null ? formatMoney(pjTotal) : "—"}
            </p>
          </div>
        </>
      )}

      <div className="sm:col-span-2">
        <label htmlFor={`${idPrefix}-email`} className="mb-1 block text-sm text-slate-600">
          E-mail
        </label>
        <input
          id={`${idPrefix}-email`}
          type="email"
          value={form.email ?? ""}
          onChange={(e) => setForm((f) => ({ ...f, email: e.target.value || null }))}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
      </div>
    </div>
  );
}

export function Employees() {
  const readOnly = useConsultaReadOnly() || useGestorGlobalReadOnly();
  const [items, setItems] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [referenceCompetencia, setReferenceCompetencia] = useState(monthStartIso);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await listEmployees({ competencia: referenceCompetencia });
        if (!cancelled) setItems(data);
      } catch (e) {
        if (!cancelled) {
          setError(isAxiosError(e) && e.response?.status === 403 ? "Sem permissão." : "Erro ao listar colaboradores.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [referenceCompetencia]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await createEmployee(formToPayload(form, referenceCompetencia));
      setForm(emptyForm);
      const data = await listEmployees({ competencia: referenceCompetencia });
      setItems(data);
    } catch (err) {
      if (isAxiosError(err) && err.response?.data?.detail) {
        const d = err.response.data.detail;
        setError(typeof d === "string" ? d : "Não foi possível salvar.");
      } else {
        setError("Não foi possível salvar.");
      }
    } finally {
      setCreating(false);
    }
  }

  async function toggleActive(emp: Employee) {
    try {
      await updateEmployee(emp.id, { is_active: !emp.is_active });
      const data = await listEmployees({ competencia: referenceCompetencia });
      setItems(data);
    } catch {
      setError("Erro ao atualizar status.");
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Excluir colaborador?")) return;
    try {
      await deleteEmployee(id);
      const data = await listEmployees({ competencia: referenceCompetencia });
      setItems(data);
    } catch {
      setError("Erro ao excluir.");
    }
  }

  const teamSummary = useMemo(() => {
    const active = items.filter((e) => e.is_active);
    const cltList = active.filter((e) => e.employment_type === "CLT");
    const pjList = active.filter((e) => e.employment_type === "PJ");
    const folhaClt = cltList.reduce((s, e) => s + e.total_cost, 0);
    const folhaPj = pjList.reduce((s, e) => s + e.total_cost, 0);
    return {
      totalColaboradores: active.length,
      totalFolha: active.reduce((s, e) => s + e.total_cost, 0),
      totalClt: cltList.length,
      totalPj: pjList.length,
      folhaClt,
      folhaPj,
    };
  }, [items]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Colaboradores</h2>
        <p className="text-sm text-slate-500">
          CLT: salário, adicionais, horas extras, encargos (% nas configurações) e VR conforme dias úteis do mês de
          competência. PJ: mensal fixo ou valor hora × horas.
        </p>
      </div>

      <div className="max-w-md rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <label className="mb-1 block text-xs font-medium text-slate-600">Mês de referência (competência)</label>
        <input
          type="month"
          value={referenceCompetencia.slice(0, 7)}
          onChange={(e) => {
            const v = e.target.value;
            if (v) setReferenceCompetencia(`${v}-01`);
          }}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
        <p className="mt-1 text-xs text-slate-500">
          Lista, preview e gravação do custo CLT usam este mês (dias úteis e VR).
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
          <h3 className="font-medium text-slate-900">Novo colaborador</h3>
          <EmployeeFields
            form={form}
            setForm={setForm}
            idPrefix="new"
            referenceCompetencia={referenceCompetencia}
          />
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
            <h3 className="text-lg font-semibold text-slate-900">Resumo da equipe</h3>
            <p className="text-sm text-slate-500">Apenas colaboradores ativos na competência selecionada.</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Total de colaboradores</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
                  {teamSummary.totalColaboradores}
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Folha total</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
                  {formatCurrency(teamSummary.totalFolha)}
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">CLT</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{teamSummary.totalClt}</p>
                <p className="mt-1 text-sm tabular-nums text-slate-600">{formatCurrency(teamSummary.folhaClt)}</p>
                <p className="mt-0.5 text-xs text-slate-500">Total na folha (CLT)</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">PJ</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{teamSummary.totalPj}</p>
                <p className="mt-1 text-sm tabular-nums text-slate-600">{formatCurrency(teamSummary.folhaPj)}</p>
                <p className="mt-0.5 text-xs text-slate-500">Total na folha (PJ)</p>
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50/80">
              <tr>
                <th className="px-4 py-3 font-medium text-slate-600">Nome</th>
                <th className="px-4 py-3 font-medium text-slate-600">Cargo</th>
                <th className="px-4 py-3 font-medium text-slate-600">Tipo</th>
                <th className="px-4 py-3 font-medium text-slate-600">Custo (competência)</th>
                <th className="px-4 py-3 font-medium text-slate-600">Ativo</th>
                {!readOnly && <th className="px-4 py-3" />}
              </tr>
            </thead>
            <tbody>
              {items.map((emp) => (
                <tr key={emp.id} className="border-b border-slate-50">
                  <td className="px-4 py-3">{emp.full_name}</td>
                  <td className="px-4 py-3 text-slate-600">{emp.role_title ?? "—"}</td>
                  <td className="px-4 py-3">{emp.employment_type}</td>
                  <td className="px-4 py-3 font-medium tabular-nums">
                    {formatMoney(emp.total_cost)}
                  </td>
                  <td className="px-4 py-3">
                    {readOnly ? (
                      <span>{emp.is_active ? "Sim" : "Não"}</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => toggleActive(emp)}
                        className="text-indigo-600 hover:underline"
                      >
                        {emp.is_active ? "Sim" : "Não"}
                      </button>
                    )}
                  </td>
                  {!readOnly && (
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setEditingId(editingId === emp.id ? null : emp.id)}
                        className="text-sm text-slate-600 hover:text-slate-900"
                      >
                        {editingId === emp.id ? "Fechar" : "Editar"}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(emp.id)}
                        className="ml-3 text-sm text-red-600 hover:underline"
                      >
                        Excluir
                      </button>
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
        <EditEmployeePanel
          emp={items.find((e) => e.id === editingId)!}
          referenceCompetencia={referenceCompetencia}
          onCancel={() => setEditingId(null)}
          onSaved={async () => {
            setEditingId(null);
            const data = await listEmployees({ competencia: referenceCompetencia });
            setItems(data);
          }}
        />
      )}
    </div>
  );
}

function EditEmployeePanel({
  emp,
  referenceCompetencia,
  onCancel,
  onSaved,
}: {
  emp: Employee;
  referenceCompetencia: string;
  onCancel: () => void;
  onSaved: () => Promise<void>;
}) {
  const [form, setForm] = useState<FormState>(() => employeeToForm(emp));
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setLocalError(null);
    try {
      await updateEmployee(emp.id, formToPayload(form, referenceCompetencia));
      await onSaved();
    } catch (err) {
      if (isAxiosError(err) && err.response?.data?.detail) {
        const d = err.response.data.detail;
        setLocalError(typeof d === "string" ? d : "Erro ao salvar.");
      } else {
        setLocalError("Erro ao salvar.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-2xl rounded-xl border border-slate-200 bg-slate-50/80 p-6 shadow-sm">
      <h3 className="font-medium text-slate-900">Editar colaborador</h3>
      {localError && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {localError}
        </div>
      )}
      <form onSubmit={save} className="mt-4 space-y-4">
        <EmployeeFields
          form={form}
          setForm={setForm}
          idPrefix={`edit-${emp.id}`}
          referenceCompetencia={referenceCompetencia}
        />
        <div className="flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {saving ? "Salvando…" : "Salvar"}
          </button>
          <button type="button" onClick={onCancel} className="rounded-lg border border-slate-300 px-4 py-2 text-sm">
            Cancelar
          </button>
        </div>
      </form>
    </div>
  );
}
