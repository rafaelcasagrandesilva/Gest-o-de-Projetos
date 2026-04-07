import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { useAuth } from "@/context/AuthContext";
import {
  createEmployee,
  createStaffCost,
  deleteEmployee,
  deleteStaffCost,
  fetchPayroll,
  listEmployees,
  listStaffCosts,
  parseCompetenciaYm,
  previewCltCost,
  updateEmployee,
  type CompanyStaffCost,
  type Employee,
  type EmployeeCreate,
  type PayrollLine,
  type PayrollResponse,
} from "@/services/employees";
import { listProjects, type Project } from "@/services/projects";
import { isAxiosError } from "axios";
import { useConsultaReadOnly } from "@/hooks/useConsultaReadOnly";
import { usePermission } from "@/hooks/usePermission";
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
  is_active: boolean;
  salary_base: string;
  has_periculosidade: boolean;
  has_adicional_dirigida: boolean;
  additional_costs: string;
  extra_hours_50: string;
  extra_hours_70: string;
  extra_hours_100: string;
  pj_hours_per_month: string;
  pj_additional_cost: string;
};

const emptyForm: FormState = {
  full_name: "",
  email: null,
  role_title: null,
  employment_type: "CLT",
  is_active: true,
  salary_base: "",
  has_periculosidade: false,
  has_adicional_dirigida: false,
  additional_costs: "",
  extra_hours_50: "0",
  extra_hours_70: "0",
  extra_hours_100: "0",
  pj_hours_per_month: "",
  pj_additional_cost: "0",
};

function parseOptionalMoney(s: string): number | null {
  const t = s.trim().replace(",", ".");
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

function parseNonNegativeMoney(s: string, fallback: number): number {
  const n = parseOptionalMoney(s);
  if (n === null || n < 0) return fallback;
  return n;
}

function employeeToForm(emp: Employee): FormState {
  return {
    full_name: emp.full_name,
    email: emp.email,
    role_title: emp.role_title,
    employment_type: emp.employment_type === "PJ" ? "PJ" : "CLT",
    is_active: emp.is_active,
    salary_base: emp.salary_base != null ? String(emp.salary_base) : "",
    has_periculosidade: emp.has_periculosidade,
    has_adicional_dirigida: emp.has_adicional_dirigida,
    additional_costs: emp.additional_costs != null ? String(emp.additional_costs) : "",
    extra_hours_50: String(emp.extra_hours_50 ?? 0),
    extra_hours_70: String(emp.extra_hours_70 ?? 0),
    extra_hours_100: String(emp.extra_hours_100 ?? 0),
    pj_hours_per_month: emp.pj_hours_per_month != null ? String(emp.pj_hours_per_month) : "",
    pj_additional_cost: String(emp.pj_additional_cost ?? 0),
  };
}

function formToCreatePayload(form: FormState, referenceCompetencia: string): EmployeeCreate {
  const add = parseOptionalMoney(form.additional_costs);
  const pjH = parseOptionalMoney(form.pj_hours_per_month);
  const salary = parseOptionalMoney(form.salary_base);
  return {
    full_name: form.full_name.trim(),
    email: form.email?.trim() || null,
    role_title: form.role_title?.trim() || null,
    employment_type: form.employment_type,
    is_active: form.is_active,
    salary_base: salary,
    additional_costs: add,
    has_periculosidade: form.has_periculosidade,
    has_adicional_dirigida: form.has_adicional_dirigida,
    extra_hours_50: parseNonNegativeMoney(form.extra_hours_50, 0),
    extra_hours_70: parseNonNegativeMoney(form.extra_hours_70, 0),
    extra_hours_100: parseNonNegativeMoney(form.extra_hours_100, 0),
    pj_hours_per_month: pjH,
    pj_additional_cost: parseNonNegativeMoney(form.pj_additional_cost, 0),
    cost_reference_competencia: referenceCompetencia,
  };
}

function formToUpdatePayload(form: FormState): Partial<EmployeeCreate> {
  const add = parseOptionalMoney(form.additional_costs);
  const pjH = parseOptionalMoney(form.pj_hours_per_month);
  const salary = parseOptionalMoney(form.salary_base);
  return {
    full_name: form.full_name.trim(),
    email: form.email?.trim() || null,
    role_title: form.role_title?.trim() || null,
    employment_type: form.employment_type,
    is_active: form.is_active,
    salary_base: salary,
    additional_costs: add,
    has_periculosidade: form.has_periculosidade,
    has_adicional_dirigida: form.has_adicional_dirigida,
    extra_hours_50: parseNonNegativeMoney(form.extra_hours_50, 0),
    extra_hours_70: parseNonNegativeMoney(form.extra_hours_70, 0),
    extra_hours_100: parseNonNegativeMoney(form.extra_hours_100, 0),
    pj_hours_per_month: pjH,
    pj_additional_cost: parseNonNegativeMoney(form.pj_additional_cost, 0),
  };
}

function formatMoney(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatCurrency(n: number): string {
  return formatMoney(n);
}

/** Variação percentual realizado vs previsto no total do colaborador. */
function formatDeltaPrevReal(prevT: number, realT: number): string {
  if (prevT === 0 && realT === 0) return "—";
  if (prevT === 0) return "—";
  const p = ((realT - prevT) / prevT) * 100;
  return `${p >= 0 ? "+" : ""}${p.toFixed(1)}%`;
}

type ScenarioKind = "PREVISTO" | "REALIZADO";

function CltCostLivePreview({
  form,
  referenceCompetencia,
}: {
  form: FormState;
  referenceCompetencia: string;
}) {
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (form.employment_type !== "CLT") {
      setTotal(null);
      return;
    }
    const salary = parseOptionalMoney(form.salary_base);
    if (salary === null || salary <= 0) {
      setTotal(null);
      return;
    }
    const { year, month } = parseCompetenciaYm(referenceCompetencia);
    let cancelled = false;
    const t = window.setTimeout(() => {
      setLoading(true);
      void previewCltCost({
        salary_base: salary,
        has_periculosidade: form.has_periculosidade,
        has_adicional_dirigida: form.has_adicional_dirigida,
        extra_hours_50: parseNonNegativeMoney(form.extra_hours_50, 0),
        extra_hours_70: parseNonNegativeMoney(form.extra_hours_70, 0),
        extra_hours_100: parseNonNegativeMoney(form.extra_hours_100, 0),
        additional_costs: parseOptionalMoney(form.additional_costs),
        year,
        month,
      })
        .then((r) => {
          if (!cancelled) {
            setTotal(r.total_cost);
            setLoading(false);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setTotal(null);
            setLoading(false);
          }
        });
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [
    form.employment_type,
    form.salary_base,
    form.has_periculosidade,
    form.has_adicional_dirigida,
    form.extra_hours_50,
    form.extra_hours_70,
    form.extra_hours_100,
    form.additional_costs,
    referenceCompetencia,
  ]);

  if (form.employment_type !== "CLT") return null;
  return (
    <div className="sm:col-span-2 rounded-lg border border-indigo-100 bg-indigo-50/50 px-4 py-3 text-sm">
      <p className="text-xs font-medium text-indigo-900">Custo mensal estimado (CLT)</p>
      <p className="mt-1 text-xs text-slate-600">
        Salário + 30% se periculosidade + R$ 209,24 se função dirigida + horas extras + encargos (Configurações) + VR
        (dias úteis) + custos adicionais opcionais. O valor é gravado no cadastro ao salvar.
      </p>
      <p className="mt-2 text-lg font-semibold tabular-nums text-slate-900">
        {loading ? "Calculando…" : total != null ? formatMoney(total) : "Informe o salário base"}
      </p>
    </div>
  );
}

function CadastroColaboradorFields({
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

      {form.employment_type === "CLT" ? (
        <>
          <div>
            <label htmlFor={`${idPrefix}-salary`} className="mb-1 block text-sm text-slate-600">
              Salário base (R$) <span className="text-red-600">*</span>
            </label>
            <input
              id={`${idPrefix}-salary`}
              required
              inputMode="decimal"
              value={form.salary_base}
              onChange={(e) => setForm((f) => ({ ...f, salary_base: e.target.value }))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
              placeholder="0,00"
            />
          </div>
          <div className="flex flex-col justify-end gap-3 sm:flex-row sm:items-center">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={form.has_periculosidade}
                onChange={(e) => setForm((f) => ({ ...f, has_periculosidade: e.target.checked }))}
                className="rounded border-slate-300"
              />
              Periculosidade (+30% sobre salário)
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={form.has_adicional_dirigida}
                onChange={(e) => setForm((f) => ({ ...f, has_adicional_dirigida: e.target.checked }))}
                className="rounded border-slate-300"
              />
              Função dirigida (+R$ 209,24)
            </label>
          </div>
          <div className="sm:col-span-2">
            <p className="mb-2 text-xs font-medium text-slate-500">Opcional — horas extras no mês (referência 220h)</p>
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="block text-xs text-slate-600">
                Horas 50%
                <input
                  type="text"
                  inputMode="decimal"
                  value={form.extra_hours_50}
                  onChange={(e) => setForm((f) => ({ ...f, extra_hours_50: e.target.value }))}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
                />
              </label>
              <label className="block text-xs text-slate-600">
                Horas 70%
                <input
                  type="text"
                  inputMode="decimal"
                  value={form.extra_hours_70}
                  onChange={(e) => setForm((f) => ({ ...f, extra_hours_70: e.target.value }))}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
                />
              </label>
              <label className="block text-xs text-slate-600">
                Horas 100%
                <input
                  type="text"
                  inputMode="decimal"
                  value={form.extra_hours_100}
                  onChange={(e) => setForm((f) => ({ ...f, extra_hours_100: e.target.value }))}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
                />
              </label>
            </div>
          </div>
          <div className="sm:col-span-2">
            <label htmlFor={`${idPrefix}-addcost`} className="mb-1 block text-sm text-slate-600">
              Custos adicionais mensais (R$, opcional)
            </label>
            <input
              id={`${idPrefix}-addcost`}
              inputMode="decimal"
              value={form.additional_costs}
              onChange={(e) => setForm((f) => ({ ...f, additional_costs: e.target.value }))}
              className="w-full max-w-xs rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
              placeholder="0"
            />
          </div>
          <CltCostLivePreview form={form} referenceCompetencia={referenceCompetencia} />
        </>
      ) : (
        <>
          <div>
            <label htmlFor={`${idPrefix}-pj-base`} className="mb-1 block text-sm text-slate-600">
              Valor base (R$) — mensal fixo ou valor/hora conforme horas abaixo
            </label>
            <input
              id={`${idPrefix}-pj-base`}
              inputMode="decimal"
              value={form.salary_base}
              onChange={(e) => setForm((f) => ({ ...f, salary_base: e.target.value }))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-pj-h`} className="mb-1 block text-sm text-slate-600">
              Horas/mês (opcional — se preenchido, base × horas)
            </label>
            <input
              id={`${idPrefix}-pj-h`}
              inputMode="decimal"
              value={form.pj_hours_per_month}
              onChange={(e) => setForm((f) => ({ ...f, pj_hours_per_month: e.target.value }))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
            />
          </div>
          <div className="sm:col-span-2">
            <label htmlFor={`${idPrefix}-pj-add`} className="mb-1 block text-sm text-slate-600">
              Ajuda de custo / adicional PJ (R$)
            </label>
            <input
              id={`${idPrefix}-pj-add`}
              inputMode="decimal"
              value={form.pj_additional_cost}
              onChange={(e) => setForm((f) => ({ ...f, pj_additional_cost: e.target.value }))}
              className="w-full max-w-xs rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
            />
          </div>
        </>
      )}
    </div>
  );
}

export function Employees() {
  const { user } = useAuth();
  const isAdmin = Boolean(user?.role_names?.includes("ADMIN"));
  const canEditEmployees = usePermission("employees.edit");
  const readOnly = useConsultaReadOnly() || useGestorGlobalReadOnly() || !canEditEmployees;
  const [items, setItems] = useState<Employee[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [payrollLoading, setPayrollLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [referenceCompetencia, setReferenceCompetencia] = useState(monthStartIso);
  const [scenario, setScenario] = useState<ScenarioKind>("REALIZADO");
  const [filterProjectId, setFilterProjectId] = useState("");
  const [payPrev, setPayPrev] = useState<PayrollResponse | null>(null);
  const [payReal, setPayReal] = useState<PayrollResponse | null>(null);
  const [expandedPayroll, setExpandedPayroll] = useState<Set<string>>(() => new Set());
  const [staffCosts, setStaffCosts] = useState<CompanyStaffCost[]>([]);
  const [staffEmpId, setStaffEmpId] = useState("");
  const [staffValor, setStaffValor] = useState("");
  const [staffSaving, setStaffSaving] = useState(false);

  const refreshPayroll = useCallback(async () => {
    setPayrollLoading(true);
    try {
      const base = {
        competencia: referenceCompetencia,
        ...(filterProjectId ? { project_id: filterProjectId } : {}),
      };
      const [p, r] = await Promise.all([
        fetchPayroll({ ...base, scenario: "PREVISTO" }),
        fetchPayroll({ ...base, scenario: "REALIZADO" }),
      ]);
      setPayPrev(p);
      setPayReal(r);
      setError(null);
    } catch (e) {
      setPayPrev(null);
      setPayReal(null);
      setError(
        isAxiosError(e) && e.response?.status === 403
          ? "Sem permissão."
          : "Erro ao carregar folha consolidada."
      );
    } finally {
      setPayrollLoading(false);
    }
  }, [referenceCompetencia, filterProjectId]);

  const payroll = scenario === "PREVISTO" ? payPrev : payReal;

  const prevTotalsByEmp = useMemo(() => {
    const m = new Map<string, number>();
    for (const l of payPrev?.lines ?? []) m.set(l.employee_id, l.grand_total);
    return m;
  }, [payPrev]);

  const realTotalsByEmp = useMemo(() => {
    const m = new Map<string, number>();
    for (const l of payReal?.lines ?? []) m.set(l.employee_id, l.grand_total);
    return m;
  }, [payReal]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [emps, projs] = await Promise.all([
          listEmployees({ competencia: referenceCompetencia, limit: 200 }),
          listProjects(),
        ]);
        if (!cancelled) {
          setItems(emps);
          setProjects(projs);
        }
      } catch {
        if (!cancelled) setError("Erro ao listar colaboradores.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [referenceCompetencia]);

  useEffect(() => {
    void refreshPayroll();
  }, [refreshPayroll]);

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    (async () => {
      try {
        const rows = await listStaffCosts({ competencia: referenceCompetencia, scenario });
        if (!cancelled) setStaffCosts(rows);
      } catch {
        if (!cancelled) setStaffCosts([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAdmin, referenceCompetencia, scenario]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (form.employment_type === "CLT") {
      const sb = parseOptionalMoney(form.salary_base);
      if (sb === null || sb <= 0) {
        setError("CLT: informe salário base maior que zero.");
        return;
      }
    }
    setCreating(true);
    setError(null);
    try {
      await createEmployee(formToCreatePayload(form, referenceCompetencia));
      setForm(emptyForm);
      const data = await listEmployees({ competencia: referenceCompetencia, limit: 200 });
      setItems(data);
      await refreshPayroll();
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
      const data = await listEmployees({ competencia: referenceCompetencia, limit: 200 });
      setItems(data);
      await refreshPayroll();
    } catch {
      setError("Erro ao atualizar status.");
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Excluir colaborador?")) return;
    try {
      await deleteEmployee(id);
      const data = await listEmployees({ competencia: referenceCompetencia, limit: 200 });
      setItems(data);
      await refreshPayroll();
    } catch {
      setError("Erro ao excluir.");
    }
  }

  async function submitStaffCost(e: React.FormEvent) {
    e.preventDefault();
    if (!staffEmpId || !staffValor) return;
    const v = Number(staffValor.replace(",", "."));
    if (Number.isNaN(v) || v < 0) return;
    setStaffSaving(true);
    try {
      await createStaffCost({
        employee_id: staffEmpId,
        competencia: referenceCompetencia,
        valor: v,
        scenario,
      });
      setStaffValor("");
      setStaffEmpId("");
      setStaffCosts(await listStaffCosts({ competencia: referenceCompetencia, scenario }));
      await refreshPayroll();
    } catch (err) {
      if (isAxiosError(err) && err.response?.data?.detail) {
        const d = err.response.data.detail;
        setError(typeof d === "string" ? d : "Não foi possível salvar custo administrativo.");
      } else {
        setError("Não foi possível salvar custo administrativo.");
      }
    } finally {
      setStaffSaving(false);
    }
  }

  async function removeStaffCost(id: string) {
    if (!confirm("Remover este custo administrativo?")) return;
    try {
      await deleteStaffCost(id);
      setStaffCosts(await listStaffCosts({ competencia: referenceCompetencia, scenario }));
      await refreshPayroll();
    } catch {
      setError("Erro ao excluir custo administrativo.");
    }
  }

  const teamSummary = useMemo(() => {
    if (!payroll) {
      return {
        totalColaboradores: 0,
        totalFolha: 0,
        totalClt: 0,
        totalPj: 0,
        folhaClt: 0,
        folhaPj: 0,
      };
    }
    const activeLines = payroll.lines.filter((l) => l.is_active);
    const cltList = activeLines.filter((l) => l.employment_type === "CLT");
    const pjList = activeLines.filter((l) => l.employment_type === "PJ");
    return {
      totalColaboradores: activeLines.length,
      totalFolha: payroll.totals.grand_total,
      totalClt: cltList.length,
      totalPj: pjList.length,
      folhaClt: cltList.reduce((s, l) => s + l.grand_total, 0),
      folhaPj: pjList.reduce((s, l) => s + l.grand_total, 0),
    };
  }, [payroll]);

  function toggleExpandPayroll(id: string) {
    setExpandedPayroll((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Colaboradores — folha mensal</h2>
        <p className="text-sm text-slate-500">
          O <strong>custo mensal CLT</strong> é calculado no cadastro (salário, periculosidade, função dirigida,
          encargos das Configurações, VR e opcionais) e gravado no colaborador. A folha soma as alocações em{" "}
          <strong>projetos</strong> (usa esse custo automaticamente; overrides ficam na aba Mão de obra) e os{" "}
          <strong>custos administrativos</strong> abaixo.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-4 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Competência</label>
          <input
            type="month"
            value={referenceCompetencia.slice(0, 7)}
            onChange={(e) => {
              const v = e.target.value;
              if (v) setReferenceCompetencia(`${v}-01`);
            }}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <span className="mb-1 block text-xs font-medium text-slate-600">Cenário</span>
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            {(["PREVISTO", "REALIZADO"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setScenario(s)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  scenario === s ? "bg-indigo-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {s === "PREVISTO" ? "Previsto" : "Realizado"}
              </button>
            ))}
          </div>
        </div>
        <div className="min-w-[12rem]">
          <label className="mb-1 block text-xs font-medium text-slate-600">Projeto (filtro)</label>
          <select
            value={filterProjectId}
            onChange={(e) => setFilterProjectId(e.target.value)}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            <option value="">Todos os projetos</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
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
          <CadastroColaboradorFields
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

      {loading || payrollLoading ? (
        <div className="text-slate-500">Carregando…</div>
      ) : (
        <div className="space-y-6">
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-slate-900">Resumo da folha</h3>
            <p className="text-sm text-slate-500">
              Totais no cenário <strong>{scenario === "PREVISTO" ? "previsto" : "realizado"}</strong>
              {filterProjectId ? " — apenas alocações do projeto selecionado (custos administrativos mantidos)." : "."}
            </p>
            {payroll ? (
              <div className="rounded-xl border-2 border-indigo-100 bg-gradient-to-br from-white to-indigo-50/30 p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-600">Folha total</p>
                <p className="mt-1 text-3xl font-semibold tabular-nums text-slate-900">
                  {formatCurrency(payroll.totals.grand_total)}
                </p>
                <div className="mt-3 flex flex-wrap gap-x-8 gap-y-2 text-sm">
                  <span className="tabular-nums text-slate-700">
                    <span className="font-medium text-slate-500">Projetos:</span>{" "}
                    {formatMoney(payroll.totals.sum_projects)}
                  </span>
                  <span className="tabular-nums text-slate-700">
                    <span className="font-medium text-slate-500">Administrativo:</span>{" "}
                    {formatMoney(payroll.totals.sum_administrative)}
                  </span>
                </div>
              </div>
            ) : null}
            {payPrev && payReal ? (
              <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4">
                <p className="text-sm font-semibold text-slate-800">Previsto × Realizado (mesma competência)</p>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
                  <div>
                    <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Previsto</dt>
                    <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                      {formatMoney(payPrev.totals.grand_total)}
                    </dd>
                    <dd className="mt-1 text-xs text-slate-600">
                      Proj. {formatMoney(payPrev.totals.sum_projects)} · Adm.{" "}
                      {formatMoney(payPrev.totals.sum_administrative)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Realizado</dt>
                    <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
                      {formatMoney(payReal.totals.grand_total)}
                    </dd>
                    <dd className="mt-1 text-xs text-slate-600">
                      Proj. {formatMoney(payReal.totals.sum_projects)} · Adm.{" "}
                      {formatMoney(payReal.totals.sum_administrative)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Δ (real vs prev.)</dt>
                    <dd className="mt-1 text-lg font-semibold tabular-nums text-indigo-700">
                      {formatDeltaPrevReal(payPrev.totals.grand_total, payReal.totals.grand_total)}
                    </dd>
                  </div>
                </dl>
              </div>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Colaboradores ativos (folha)</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
                  {teamSummary.totalColaboradores}
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">CLT (ativos)</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{teamSummary.totalClt}</p>
                <p className="mt-1 text-sm tabular-nums text-slate-600">{formatCurrency(teamSummary.folhaClt)}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">PJ (ativos)</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{teamSummary.totalPj}</p>
                <p className="mt-1 text-sm tabular-nums text-slate-600">{formatCurrency(teamSummary.folhaPj)}</p>
              </div>
            </div>
          </div>

          {payroll && (
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-100 bg-slate-50/80">
                  <tr>
                    <th className="px-4 py-3 font-medium text-slate-600" />
                    <th className="px-4 py-3 font-medium text-slate-600">Nome</th>
                    <th className="px-4 py-3 font-medium text-slate-600">Cargo</th>
                    <th className="px-4 py-3 font-medium text-slate-600">Tipo</th>
                    <th className="px-4 py-3 text-right font-medium text-slate-600">Projetos</th>
                    <th className="px-4 py-3 text-right font-medium text-slate-600">Adm.</th>
                    <th className="px-4 py-3 text-right font-medium text-slate-600">
                      Total ({scenario === "PREVISTO" ? "prev." : "real."})
                    </th>
                    <th className="px-4 py-3 text-right font-medium text-slate-600">Previsto</th>
                    <th className="px-4 py-3 text-right font-medium text-slate-600">Realizado</th>
                    <th className="px-4 py-3 text-right font-medium text-slate-600">Δ (%)</th>
                    <th className="px-4 py-3 font-medium text-slate-600">Ativo</th>
                  </tr>
                </thead>
                <tbody>
                  {payroll.lines.map((line: PayrollLine) => {
                    const open = expandedPayroll.has(line.employee_id);
                    const prevEmp = prevTotalsByEmp.get(line.employee_id) ?? 0;
                    const realEmp = realTotalsByEmp.get(line.employee_id) ?? 0;
                    return (
                      <Fragment key={line.employee_id}>
                        <tr className={`border-b border-slate-50 ${!line.is_active ? "opacity-70" : ""}`}>
                          <td className="px-4 py-3">
                            {line.by_project.length > 0 ? (
                              <button
                                type="button"
                                onClick={() => toggleExpandPayroll(line.employee_id)}
                                className="text-indigo-600 hover:underline"
                              >
                                {open ? "−" : "+"}
                              </button>
                            ) : (
                              <span className="text-slate-300">·</span>
                            )}
                          </td>
                          <td className="px-4 py-3 font-medium text-slate-900">{line.full_name}</td>
                          <td className="px-4 py-3 text-slate-600">{line.role_title ?? "—"}</td>
                          <td className="px-4 py-3">{line.employment_type}</td>
                          <td className="px-4 py-3 text-right tabular-nums">{formatMoney(line.projects_total)}</td>
                          <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                            {formatMoney(line.administrative_cost)}
                          </td>
                          <td className="px-4 py-3 text-right font-medium tabular-nums">
                            {formatMoney(line.grand_total)}
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                            {formatMoney(prevEmp)}
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                            {formatMoney(realEmp)}
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums text-indigo-700">
                            {formatDeltaPrevReal(prevEmp, realEmp)}
                          </td>
                          <td className="px-4 py-3">{line.is_active ? "Sim" : "Não"}</td>
                        </tr>
                        {open && line.by_project.length > 0 ? (
                          <tr className="border-b border-slate-50 bg-slate-50/50">
                            <td colSpan={11} className="px-4 py-3">
                              <p className="mb-2 text-xs font-medium text-slate-600">Por projeto</p>
                              <ul className="space-y-1 text-xs text-slate-700">
                                {line.by_project.map((s) => (
                                  <li
                                    key={s.labor_id}
                                    className="flex flex-wrap justify-between gap-2 border-b border-slate-100/80 py-1"
                                  >
                                    <span>{s.project_name}</span>
                                    <span className="tabular-nums text-slate-600">
                                      {s.allocation_percentage}% → {formatMoney(s.allocated_cost)}
                                      <span className="ml-2 text-slate-400">
                                        (integral {formatMoney(s.full_monthly_cost)})
                                      </span>
                                    </span>
                                  </li>
                                ))}
                              </ul>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {isAdmin && !readOnly && (
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="font-medium text-slate-900">Custos administrativos (fora de projeto)</h3>
              <p className="mt-1 text-sm text-slate-500">
                Valor extra por colaborador no mês e cenário (soma na coluna Adm. da folha).
              </p>
              <form onSubmit={submitStaffCost} className="mt-4 flex flex-wrap items-end gap-3">
                <div>
                  <label className="mb-1 block text-xs text-slate-600">Colaborador</label>
                  <select
                    value={staffEmpId}
                    onChange={(e) => setStaffEmpId(e.target.value)}
                    className="min-w-[12rem] rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    required
                  >
                    <option value="">—</option>
                    {items.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.full_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-600">Valor (R$)</label>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={staffValor}
                    onChange={(e) => setStaffValor(e.target.value)}
                    className="w-32 rounded-lg border border-slate-200 px-3 py-2 text-sm tabular-nums"
                    placeholder="0"
                  />
                </div>
                <button
                  type="submit"
                  disabled={staffSaving}
                  className="rounded-lg bg-slate-800 px-4 py-2 text-sm text-white disabled:opacity-50"
                >
                  {staffSaving ? "Salvando…" : "Adicionar"}
                </button>
              </form>
              {staffCosts.length > 0 ? (
                <ul className="mt-4 space-y-2 border-t border-slate-100 pt-4 text-sm">
                  {staffCosts.map((c) => (
                    <li
                      key={c.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2"
                    >
                      <span>
                        {c.employee_full_name ?? c.employee_id} — {formatMoney(c.valor)}
                      </span>
                      <button
                        type="button"
                        onClick={() => removeStaffCost(c.id)}
                        className="text-xs text-red-600 hover:underline"
                      >
                        Remover
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          )}

          <div>
            <h3 className="mb-2 text-lg font-semibold text-slate-900">Cadastro (identificação)</h3>
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-100 bg-slate-50/80">
                  <tr>
                    <th className="px-4 py-3 font-medium text-slate-600">Nome</th>
                    <th className="px-4 py-3 font-medium text-slate-600">Cargo</th>
                    <th className="px-4 py-3 font-medium text-slate-600">Tipo</th>
                    <th className="px-4 py-3 text-right font-medium text-slate-600">Salário base</th>
                    <th className="px-4 py-3 text-right font-medium text-slate-600">Custo mês</th>
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
                      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                        {emp.salary_base != null ? formatMoney(emp.salary_base) : "—"}
                      </td>
                      <td className="px-4 py-3 text-right font-medium tabular-nums text-slate-900">
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
        </div>
      )}
      {editingId && !readOnly && (
        <EditEmployeePanel
          emp={items.find((e) => e.id === editingId)!}
          referenceCompetencia={referenceCompetencia}
          onCancel={() => setEditingId(null)}
          onSaved={async () => {
            setEditingId(null);
            const data = await listEmployees({ competencia: referenceCompetencia, limit: 200 });
            setItems(data);
            await refreshPayroll();
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

  useEffect(() => {
    setForm(employeeToForm(emp));
  }, [emp]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (form.employment_type === "CLT") {
      const sb = parseOptionalMoney(form.salary_base);
      if (sb === null || sb <= 0) {
        setLocalError("CLT: informe salário base maior que zero.");
        return;
      }
    }
    setSaving(true);
    setLocalError(null);
    try {
      await updateEmployee(emp.id, {
        ...formToUpdatePayload(form),
        cost_reference_competencia: referenceCompetencia,
      });
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
        <CadastroColaboradorFields
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
