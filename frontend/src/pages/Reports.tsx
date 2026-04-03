import { useAuth } from "@/context/AuthContext";
import { listProjects, type Project } from "@/services/projects";
import { generateReport, type ReportFormat, type ReportType } from "@/services/reports";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

type ReportDef = { id: ReportType; label: string; roles: string[] };

/** Papéis RBAC (backend: ROLE_ADMIN, ROLE_GESTOR, ROLE_CONSULTA). */
const R_ALL: string[] = ["ADMIN", "GESTOR", "CONSULTA"];
const R_ADMIN_ONLY: string[] = ["ADMIN"];

const DEFINITIONS: ReportDef[] = [
  {
    id: "project_summary",
    label: "Projeto — resumo financeiro e custos (mão de obra, veículos, sistemas, fixos)",
    roles: R_ALL,
  },
  {
    id: "company_summary",
    label: "Empresa — resumo financeiro por projeto (com TOTAL)",
    roles: R_ALL,
  },
  { id: "employees", label: "Colaboradores — nome, tipo e custo", roles: R_ALL },
  { id: "vehicles", label: "Frota — placa, tipo, custo e status", roles: R_ALL },
  {
    id: "invoices",
    label: "Notas fiscais — valores, vencimento, recebido e saldo",
    roles: R_ALL,
  },
  {
    id: "debt",
    label: "Endividamento — itens, referência e pagamentos mensais (JAN–DEZ)",
    roles: R_ALL,
  },
  {
    id: "fixed_costs",
    label: "Custos fixos (empresa) — itens e pagamentos mensais (JAN–DEZ)",
    roles: R_ALL,
  },
  {
    id: "dashboard",
    label: "Dashboard — série mensal de receita, custos e margem",
    roles: R_ALL,
  },
  { id: "users", label: "Usuários do sistema (e-mail, papéis)", roles: R_ADMIN_ONLY },
  {
    id: "revenues",
    label: "Receitas lançadas (faturamento por projeto)",
    roles: R_ALL,
  },
];

function monthDefault(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function Reports() {
  const { user } = useAuth();
  const roles = user?.role_names ?? [];

  const visible = useMemo(
    () => DEFINITIONS.filter((d) => d.roles.some((r) => roles.includes(r))),
    [roles],
  );

  const [type, setType] = useState<ReportType | "">("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [competencia, setCompetencia] = useState(monthDefault);
  const [summaryProjectId, setSummaryProjectId] = useState("");
  const [companyProjectId, setCompanyProjectId] = useState("");
  const [invoiceProjectId, setInvoiceProjectId] = useState("");
  const [dashProjectId, setDashProjectId] = useState("");
  const [revenuesProjectId, setRevenuesProjectId] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [invStatus, setInvStatus] = useState("");
  const [invYear, setInvYear] = useState<number | "">("");
  const [invMonth, setInvMonth] = useState<number | "">("");
  const [dashMonths, setDashMonths] = useState(6);

  const canGlobalDashboard = roles.includes("ADMIN") || roles.includes("CONSULTA");

  const loadProjects = useCallback(async () => {
    setLoadingProjects(true);
    try {
      const data = await listProjects();
      setProjects(data);
    } catch {
      setProjects([]);
    } finally {
      setLoadingProjects(false);
    }
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    if (visible.length && !type) setType(visible[0].id);
  }, [visible, type]);

  function buildFilters(): Record<string, string | number | boolean> {
    if (!type) throw new Error("Selecione o relatório.");
    switch (type) {
      case "project_summary":
        if (!summaryProjectId) throw new Error("Selecione o projeto.");
        return { project_id: summaryProjectId, competencia: `${competencia}-01` };
      case "company_summary": {
        const f: Record<string, string | number | boolean> = { competencia: `${competencia}-01` };
        if (companyProjectId) f.project_id = companyProjectId;
        return f;
      }
      case "employees":
        return { competencia: `${competencia}-01` };
      case "vehicles":
        return { active_only: activeOnly };
      case "invoices": {
        const f: Record<string, string | number | boolean> = {};
        if (invoiceProjectId) f.project_id = invoiceProjectId;
        if (invStatus) f.status = invStatus;
        if (invYear !== "" && invMonth !== "") {
          f.year = Number(invYear);
          f.month = Number(invMonth);
        }
        return f;
      }
      case "debt":
      case "fixed_costs":
        return { competencia };
      case "dashboard": {
        const f: Record<string, string | number | boolean> = { months: dashMonths };
        if (competencia) f.competencia = `${competencia}-01`;
        if (dashProjectId) f.project_id = dashProjectId;
        return f;
      }
      case "users":
        return {};
      case "revenues": {
        const f: Record<string, string | number | boolean> = {};
        if (revenuesProjectId) f.project_id = revenuesProjectId;
        return f;
      }
      default:
        return {};
    }
  }

  async function run(fmt: ReportFormat) {
    if (!type) return;
    setErr(null);
    setBusy(true);
    try {
      if (type === "dashboard" && !canGlobalDashboard && !dashProjectId) {
        throw new Error("Selecione um projeto para o dashboard.");
      }
      const filters = buildFilters();
      await generateReport(type, fmt, filters);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Falha ao gerar.");
    } finally {
      setBusy(false);
    }
  }

  const def = DEFINITIONS.find((d) => d.id === type);

  if (visible.length === 0) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <h2 className="text-xl font-semibold text-slate-900">Relatórios</h2>
        <p className="text-sm text-slate-600">Seu perfil não tem permissão para gerar relatórios.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Relatórios</h2>
        <p className="mt-1 text-sm text-slate-600">
          Gere Excel ou PDF a partir dos mesmos dados e regras do sistema (dashboard, custos e financeiro).
        </p>
      </div>

      {err && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{err}</div>
      )}

      <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Tipo de relatório</label>
          <select
            value={type}
            onChange={(e) => {
              setType(e.target.value as ReportType);
              setErr(null);
            }}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
          >
            {visible.map((d) => (
              <option key={d.id} value={d.id}>
                {d.label}
              </option>
            ))}
          </select>
          {def && <p className="mt-2 text-xs text-slate-500">{def.label}</p>}
        </div>

        {type === "project_summary" && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <Field label="Projeto" required>
              <select
                value={summaryProjectId}
                onChange={(e) => setSummaryProjectId(e.target.value)}
                disabled={loadingProjects}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                required
              >
                <option value="">Selecione…</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Competência" required>
              <input
                type="month"
                value={competencia}
                onChange={(e) => e.target.value && setCompetencia(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </Field>
          </div>
        )}

        {type === "company_summary" && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <Field label="Competência" required>
              <input
                type="month"
                value={competencia}
                onChange={(e) => e.target.value && setCompetencia(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </Field>
            <Field label="Projeto (opcional — deixe vazio para todos os permitidos)">
              <select
                value={companyProjectId}
                onChange={(e) => setCompanyProjectId(e.target.value)}
                disabled={loadingProjects}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">Todos</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}

        {type === "employees" && (
          <div className="border-t border-slate-100 pt-4">
            <Field label="Competência de referência do custo">
              <input
                type="month"
                value={competencia}
                onChange={(e) => e.target.value && setCompetencia(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </Field>
          </div>
        )}

        {type === "vehicles" && (
          <div className="border-t border-slate-100 pt-4">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={activeOnly}
                onChange={(e) => setActiveOnly(e.target.checked)}
                className="rounded border-slate-300"
              />
              Somente veículos ativos
            </label>
          </div>
        )}

        {type === "invoices" && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <Field label="Projeto (opcional)">
              <select
                value={invoiceProjectId}
                onChange={(e) => setInvoiceProjectId(e.target.value)}
                disabled={loadingProjects}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">Todos</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Status">
              <select
                value={invStatus}
                onChange={(e) => setInvStatus(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">Todos</option>
                <option value="PAGA">Paga</option>
                <option value="PENDENTE">Pendente</option>
                <option value="ATRASADA">Atrasada</option>
              </select>
            </Field>
            <p className="text-xs text-slate-500">Período por emissão (opcional): informe ano e mês juntos.</p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Ano">
                <input
                  type="number"
                  min={2000}
                  max={2100}
                  value={invYear}
                  onChange={(e) => setInvYear(e.target.value === "" ? "" : Number(e.target.value))}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="ex. 2026"
                />
              </Field>
              <Field label="Mês">
                <input
                  type="number"
                  min={1}
                  max={12}
                  value={invMonth}
                  onChange={(e) => setInvMonth(e.target.value === "" ? "" : Number(e.target.value))}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="1–12"
                />
              </Field>
            </div>
          </div>
        )}

        {(type === "debt" || type === "fixed_costs") && (
          <div className="border-t border-slate-100 pt-4">
            <Field label="Competência (mês de referência)" required>
              <input
                type="month"
                value={competencia}
                onChange={(e) => e.target.value && setCompetencia(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </Field>
          </div>
        )}

        {type === "revenues" && (
          <div className="border-t border-slate-100 pt-4">
            <Field label="Projeto (opcional — vazio = todos)">
              <select
                value={revenuesProjectId}
                onChange={(e) => setRevenuesProjectId(e.target.value)}
                disabled={loadingProjects}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">Todos</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}

        {type === "dashboard" && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <Field label={canGlobalDashboard ? "Projeto (opcional — vazio = consolidado)" : "Projeto"}>
              <select
                value={dashProjectId}
                onChange={(e) => setDashProjectId(e.target.value)}
                disabled={loadingProjects}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                {canGlobalDashboard && <option value="">Consolidado (todos)</option>}
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Competência inicial da série (opcional)">
              <input
                type="month"
                value={competencia}
                onChange={(e) => e.target.value && setCompetencia(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </Field>
            <Field label="Quantidade de meses na série">
              <input
                type="number"
                min={1}
                max={24}
                value={dashMonths}
                onChange={(e) => setDashMonths(Number(e.target.value) || 6)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </Field>
          </div>
        )}

        <div className="flex flex-wrap gap-3 border-t border-slate-100 pt-4">
          <button
            type="button"
            disabled={busy || !type || visible.length === 0}
            onClick={() => void run("xlsx")}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
          >
            {busy ? "Gerando…" : "Gerar Excel"}
          </button>
          <button
            type="button"
            disabled={busy || !type || visible.length === 0}
            onClick={() => void run("pdf")}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          >
            Gerar PDF
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-600">
        {label}
        {required ? <span className="text-red-600"> *</span> : null}
      </label>
      {children}
    </div>
  );
}
