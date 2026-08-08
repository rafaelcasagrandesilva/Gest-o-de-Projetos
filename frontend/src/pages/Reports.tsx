import { useAuth } from "@/context/AuthContext";
import { useScenario } from "@/context/ScenarioContext";
import { hasPermission } from "@/permissions";
import { fetchAdvanceInstitutions, type AdvanceInstitution } from "@/services/advanceInstitutions";
import { listProjects, type Project } from "@/services/projects";
import {
  generateReport,
  type ReportFormat,
  type ReportScenario,
  type ReportType,
} from "@/services/reports";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

// Fase 1: visibilidade por PERMISSÃO (espelha app/modules/reports/router._REPORT_TYPE_VIEW_PERMISSION),
// nunca por perfil. `perm` ausente = sem exigência de módulo (basta reports.view do próprio menu).
type ReportDef = { id: ReportType; label: string; perm?: string };

const REPORT_GROUPS: { label: string; reports: ReportDef[] }[] = [
  {
    label: "Financeiro",
    reports: [
      { id: "payables_detailed", label: "Contas a pagar — detalhado", perm: "payables.view" },
      { id: "receivables_detailed", label: "Contas a receber — detalhado", perm: "receivables.view" },
      { id: "invoices_detailed", label: "Notas fiscais — detalhado", perm: "invoices.view" },
      { id: "invoices", label: "Notas fiscais — resumo (legado)", perm: "invoices.view" },
      { id: "antecipacoes", label: "Antecipações — Operações e Liquidações", perm: "invoices.view" },
      { id: "debt", label: "Endividamento — matriz mensal", perm: "debts.view" },
      { id: "fixed_costs", label: "Custos fixos (empresa) — matriz mensal", perm: "company_finance.view" },
      { id: "revenues", label: "Receitas lançadas (faturamento)", perm: "billing.view" },
    ],
  },
  {
    label: "Projetos",
    reports: [
      { id: "project_summary", label: "Projeto — resumo financeiro e custos" },
      { id: "company_summary", label: "Empresa — resumo financeiro por projeto" },
      { id: "dashboard", label: "Dashboard — série mensal receita/custos/margem", perm: "dashboard.view" },
    ],
  },
  {
    label: "Patrimônio",
    reports: [
      { id: "assets_inventory", label: "Inventário patrimonial", perm: "assets.view" },
      { id: "assets_in_use", label: "Ativos em uso", perm: "assets.view" },
      { id: "assets_inspections", label: "Inspeções e vencimentos", perm: "assets.view" },
      { id: "assets_movements", label: "Movimentações patrimoniais", perm: "assets.view" },
    ],
  },
  {
    label: "Administrativo",
    reports: [
      { id: "employees", label: "Colaboradores — nome, tipo e custo", perm: "employees.export" },
      { id: "payroll", label: "Folha de Pagamento — fechamento mensal", perm: "employees.export" },
      { id: "vehicles", label: "Frota — placa, tipo, custo e status", perm: "vehicles.export" },
      { id: "users", label: "Usuários do sistema", perm: "users.manage" },
    ],
  },
];

function monthDefault(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** Mês de PAGAMENTO da folha: a competência trabalhada é paga no Contas a Pagar do mês seguinte. */
function nextCompetenciaLabel(competencia: string): string {
  const [y, m] = competencia.split("-").map(Number);
  if (!y || !m) return "—";
  const year = m === 12 ? y + 1 : y;
  const month = m === 12 ? 1 : m + 1;
  return `${year}-${String(month).padStart(2, "0")}`;
}

export function Reports() {
  const { user } = useAuth();
  const { globalScenario } = useScenario();
  const permissionNames = user?.permission_names;

  const visibleGroups = useMemo(() => {
    return REPORT_GROUPS.map((g) => ({
      ...g,
      // Fase 1: só permissão. `perm` ausente = visível a quem acessa Relatórios (reports.view do menu).
      reports: g.reports.filter((d) => !d.perm || hasPermission(permissionNames, d.perm)),
    })).filter((g) => g.reports.length > 0);
  }, [permissionNames]);

  const visible = useMemo(() => visibleGroups.flatMap((g) => g.reports), [visibleGroups]);

  const [type, setType] = useState<ReportType | "">("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [competencia, setCompetencia] = useState(monthDefault);
  const [monthTo, setMonthTo] = useState(monthDefault);
  const [summaryProjectId, setSummaryProjectId] = useState("");
  const [companyProjectId, setCompanyProjectId] = useState("");
  const [invoiceProjectId, setInvoiceProjectId] = useState("");
  const [dashProjectId, setDashProjectId] = useState("");
  const [revenuesProjectId, setRevenuesProjectId] = useState("");
  const [payablesProjectId, setPayablesProjectId] = useState("");
  const [payablesStatus, setPayablesStatus] = useState("");
  const [payablesCategory, setPayablesCategory] = useState("");
  const [receivablesProjectId, setReceivablesProjectId] = useState("");
  const [receivablesStatus, setReceivablesStatus] = useState("");
  const [receivablesClient, setReceivablesClient] = useState("");
  const [assetCategory, setAssetCategory] = useState("");
  const [assetStatus, setAssetStatus] = useState("");
  const [assetCostCenter, setAssetCostCenter] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [invStatus, setInvStatus] = useState("");
  const [invYear, setInvYear] = useState<number | "">("");
  const [invMonth, setInvMonth] = useState<number | "">("");
  const [dashMonths, setDashMonths] = useState(6);
  const [reportScenario, setReportScenario] = useState<ReportScenario>(globalScenario);

  // Antecipações — filtros espelhando as duas telas (Operações e Liquidação).
  const [antecInstitutions, setAntecInstitutions] = useState<AdvanceInstitution[]>([]);
  const [antOpMonth, setAntOpMonth] = useState("");
  const [antOpInstitution, setAntOpInstitution] = useState("");
  const [antOpStatus, setAntOpStatus] = useState("");
  const [antLiqMonth, setAntLiqMonth] = useState("");
  const [antLiqSituacao, setAntLiqSituacao] = useState("");
  const [antLiqInstitution, setAntLiqInstitution] = useState("");
  const [antLiqClient, setAntLiqClient] = useState("");
  const [antLiqNf, setAntLiqNf] = useState("");
  const [antLiqSgc, setAntLiqSgc] = useState("");

  // Fase 1: dashboard consolidado (sem projeto) depende da permissão dashboard.director, não do perfil.
  const canGlobalDashboard = hasPermission(permissionNames, "dashboard.director");

  const loadProjects = useCallback(async () => {
    setLoadingProjects(true);
    try {
      const data = await listProjects({ status: "ALL" });
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

  // Instituições p/ os filtros de Antecipações (carrega só quando o relatório é selecionado).
  useEffect(() => {
    if (type !== "antecipacoes" || antecInstitutions.length > 0) return;
    let alive = true;
    fetchAdvanceInstitutions()
      .then((rows) => alive && setAntecInstitutions(rows))
      .catch(() => alive && setAntecInstitutions([]));
    return () => {
      alive = false;
    };
  }, [type, antecInstitutions.length]);

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
      case "payroll":
        return { competencia: `${competencia}-01` };
      case "vehicles":
        return { active_only: activeOnly };
      case "invoices":
      case "invoices_detailed": {
        const f: Record<string, string | number | boolean> = {};
        if (invoiceProjectId) f.project_id = invoiceProjectId;
        if (invStatus) f.status = invStatus;
        if (invYear !== "" && invMonth !== "") {
          f.year = Number(invYear);
          f.month = Number(invMonth);
        }
        return f;
      }
      case "payables_detailed": {
        const f: Record<string, string | number | boolean> = { month: competencia };
        if (monthTo && monthTo !== competencia) f.month_to = monthTo;
        if (payablesProjectId) f.project_id = payablesProjectId;
        if (payablesStatus) f.status = payablesStatus;
        if (payablesCategory.trim()) f.category = payablesCategory.trim();
        return f;
      }
      case "receivables_detailed": {
        const f: Record<string, string | number | boolean> = {};
        if (receivablesProjectId) f.project_id = receivablesProjectId;
        if (receivablesStatus) f.status = receivablesStatus;
        if (receivablesClient.trim()) f.client = receivablesClient.trim();
        if (invYear !== "" && invMonth !== "") {
          f.year = Number(invYear);
          f.month = Number(invMonth);
        }
        return f;
      }
      case "assets_inventory": {
        const f: Record<string, string | number | boolean> = {};
        if (assetCategory.trim()) f.category = assetCategory.trim();
        if (assetStatus) f.status = assetStatus;
        if (assetCostCenter.trim()) f.cost_center_ref = assetCostCenter.trim();
        return f;
      }
      case "assets_in_use":
        return {};
      case "assets_inspections":
        return {};
      case "assets_movements": {
        const f: Record<string, string | number | boolean> = { month: competencia };
        if (monthTo && monthTo !== competencia) f.month_to = monthTo;
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
      case "antecipacoes": {
        const f: Record<string, string | number | boolean> = {};
        if (antOpMonth) f.op_month = antOpMonth;
        if (antOpInstitution) f.op_institution_id = antOpInstitution;
        if (antOpStatus) f.op_status = antOpStatus;
        if (antLiqMonth) f.liq_month = antLiqMonth;
        if (antLiqSituacao) f.liq_situacao = antLiqSituacao;
        if (antLiqInstitution) f.liq_institution_id = antLiqInstitution;
        if (antLiqClient.trim()) f.liq_client = antLiqClient.trim();
        if (antLiqNf.trim()) f.liq_nf = antLiqNf.trim();
        if (antLiqSgc.trim()) f.liq_sgc = antLiqSgc.trim();
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
      await generateReport(type, fmt, filters, reportScenario);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Falha ao gerar.");
    } finally {
      setBusy(false);
    }
  }

  const def = visible.find((d) => d.id === type);
  const usesScenario = ![
    "payables_detailed",
    "receivables_detailed",
    "invoices_detailed",
    "invoices",
    "debt",
    "fixed_costs",
    "vehicles",
    "users",
    "assets_inventory",
    "assets_in_use",
    "assets_inspections",
    "assets_movements",
    "antecipacoes",
  ].includes(type);

  if (visible.length === 0) {
    return (
      <div className="space-y-4">
        <h2 className="text-xl font-semibold text-slate-900">Relatórios</h2>
        <p className="text-sm text-slate-600">Seu perfil não tem permissão para gerar relatórios.</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Relatórios</h2>
        <p className="mt-1 text-sm text-slate-600">
          Exportações operacionais (Excel/PDF) com os mesmos dados e regras das telas do sistema.
        </p>
      </div>

      {usesScenario ? (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="mb-2 text-sm font-medium text-slate-800">Cenário do relatório</p>
          <p className="mb-3 text-xs text-slate-500">
            Receitas, custos de projeto e folha seguem o cenário escolhido.
          </p>
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            {(["PREVISTO", "REALIZADO"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setReportScenario(s)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  reportScenario === s ? "bg-indigo-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {s === "PREVISTO" ? "Previsto" : "Realizado"}
              </button>
            ))}
          </div>
        </div>
      ) : null}

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
            {visibleGroups.map((g) => (
              <optgroup key={g.label} label={g.label}>
                {g.reports.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          {def && <p className="mt-2 text-xs text-slate-500">{def.label}</p>}
        </div>

        {type === "project_summary" && (
          <ProjectMonthFilters
            competencia={competencia}
            setCompetencia={setCompetencia}
            projectId={summaryProjectId}
            setProjectId={setSummaryProjectId}
            projects={projects}
            loadingProjects={loadingProjects}
            required
          />
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
            <Field label="Projeto (opcional)">
              <ProjectSelect
                value={companyProjectId}
                onChange={setCompanyProjectId}
                projects={projects}
                loading={loadingProjects}
                allowEmpty
              />
            </Field>
          </div>
        )}

        {(type === "employees" || type === "payroll") && (
          <div className="border-t border-slate-100 pt-4">
            <Field label={type === "payroll" ? "Competência da folha (mês trabalhado)" : "Competência de referência do custo"}>
              <input
                type="month"
                value={competencia}
                onChange={(e) => e.target.value && setCompetencia(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </Field>
            {type === "payroll" && (
              <p className="mt-2 text-xs text-slate-500">
                A folha da competência <strong>{competencia}</strong> é paga no Contas a Pagar de{" "}
                <strong>{nextCompetenciaLabel(competencia)}</strong>. Para conferir contra a tela de
                Contas a Pagar, compare com o mês de pagamento — não com o mesmo mês.
              </p>
            )}
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

        {(type === "invoices" || type === "invoices_detailed") && (
          <InvoicePeriodFilters
            invoiceProjectId={invoiceProjectId}
            setInvoiceProjectId={setInvoiceProjectId}
            invStatus={invStatus}
            setInvStatus={setInvStatus}
            invYear={invYear}
            setInvYear={setInvYear}
            invMonth={invMonth}
            setInvMonth={setInvMonth}
            projects={projects}
            loadingProjects={loadingProjects}
          />
        )}

        {type === "payables_detailed" && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <p className="text-xs text-slate-500">Mesmos critérios da tela Contas a pagar (snapshot do mês).</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Mês (início)" required>
                <input
                  type="month"
                  value={competencia}
                  onChange={(e) => e.target.value && setCompetencia(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </Field>
              <Field label="Mês (fim — opcional)">
                <input
                  type="month"
                  value={monthTo}
                  onChange={(e) => e.target.value && setMonthTo(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </Field>
            </div>
            <Field label="Projeto (opcional)">
              <ProjectSelect
                value={payablesProjectId}
                onChange={setPayablesProjectId}
                projects={projects}
                loading={loadingProjects}
                allowEmpty
              />
            </Field>
            <Field label="Status">
              <select
                value={payablesStatus}
                onChange={(e) => setPayablesStatus(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">Todos</option>
                <option value="ABERTO">Aberto</option>
                <option value="PARCIAL">Parcial</option>
                <option value="PAGO">Pago</option>
              </select>
            </Field>
            <Field label="Categoria (contém)">
              <input
                type="text"
                value={payablesCategory}
                onChange={(e) => setPayablesCategory(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="Ex.: Mão de obra"
              />
            </Field>
          </div>
        )}

        {type === "receivables_detailed" && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <p className="text-xs text-slate-500">Alinhado à tela Contas a receber.</p>
            <Field label="Projeto (opcional)">
              <ProjectSelect
                value={receivablesProjectId}
                onChange={setReceivablesProjectId}
                projects={projects}
                loading={loadingProjects}
                allowEmpty
              />
            </Field>
            <Field label="Cliente (busca)">
              <input
                type="text"
                value={receivablesClient}
                onChange={(e) => setReceivablesClient(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </Field>
            <Field label="Status (NF)">
              <select
                value={receivablesStatus}
                onChange={(e) => setReceivablesStatus(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">Todos</option>
                <option value="EMITIDA">Emitida</option>
                <option value="ANTECIPADA">Antecipada</option>
                <option value="RECEBIDA">Recebida</option>
              </select>
            </Field>
            <InvoicePeriodFilters
              invoiceProjectId=""
              setInvoiceProjectId={() => {}}
              invStatus=""
              setInvStatus={() => {}}
              invYear={invYear}
              setInvYear={setInvYear}
              invMonth={invMonth}
              setInvMonth={setInvMonth}
              projects={projects}
              loadingProjects={loadingProjects}
              hideProject
              hideStatus
            />
          </div>
        )}

        {type === "assets_inventory" && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <Field label="Categoria">
              <input
                type="text"
                value={assetCategory}
                onChange={(e) => setAssetCategory(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="Ex.: EPI"
              />
            </Field>
            <Field label="Status">
              <select
                value={assetStatus}
                onChange={(e) => setAssetStatus(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">Todos</option>
                <option value="AVAILABLE">Disponível</option>
                <option value="IN_USE">Em uso</option>
                <option value="MAINTENANCE">Manutenção</option>
                <option value="EXPIRED">Vencido</option>
              </select>
            </Field>
            <Field label="Centro de custo (ref.)">
              <input
                type="text"
                value={assetCostCenter}
                onChange={(e) => setAssetCostCenter(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="ADMINISTRATIVO ou UUID do projeto"
              />
            </Field>
          </div>
        )}

        {type === "assets_movements" && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Entrega a partir de">
                <input
                  type="month"
                  value={competencia}
                  onChange={(e) => e.target.value && setCompetencia(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </Field>
              <Field label="Entrega até (opcional)">
                <input
                  type="month"
                  value={monthTo}
                  onChange={(e) => e.target.value && setMonthTo(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
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
            <Field label="Projeto (opcional)">
              <ProjectSelect
                value={revenuesProjectId}
                onChange={setRevenuesProjectId}
                projects={projects}
                loading={loadingProjects}
                allowEmpty
              />
            </Field>
          </div>
        )}

        {type === "antecipacoes" && (
          <div className="space-y-4 border-t border-slate-100 pt-4">
            <p className="text-xs text-slate-500">
              Excel com 6 abas espelhando as telas de Antecipações. Os filtros refletem exatamente o
              que a tela mostraria; em branco = tudo.
            </p>

            <fieldset className="space-y-3 rounded-lg border border-slate-200 p-3">
              <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Operações
              </legend>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Período (Recebimento)">
                  <input
                    type="month"
                    value={antOpMonth}
                    onChange={(e) => setAntOpMonth(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                </Field>
                <Field label="Instituição">
                  <select
                    value={antOpInstitution}
                    onChange={(e) => setAntOpInstitution(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  >
                    <option value="">Todas</option>
                    {antecInstitutions.map((i) => (
                      <option key={i.id} value={i.id}>
                        {i.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Status">
                  <select
                    value={antOpStatus}
                    onChange={(e) => setAntOpStatus(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  >
                    <option value="">Todos</option>
                    <option value="DRAFT">Rascunho</option>
                    <option value="OPEN">Em aberto</option>
                    <option value="SETTLED">Liquidada</option>
                    <option value="CANCELLED">Cancelada</option>
                  </select>
                </Field>
              </div>
            </fieldset>

            <fieldset className="space-y-3 rounded-lg border border-slate-200 p-3">
              <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Liquidação
              </legend>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Período (Vencimento)">
                  <input
                    type="month"
                    value={antLiqMonth}
                    onChange={(e) => setAntLiqMonth(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                </Field>
                <Field label="Situação">
                  <select
                    value={antLiqSituacao}
                    onChange={(e) => setAntLiqSituacao(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  >
                    <option value="">Todas</option>
                    <option value="EM_ABERTO">Em aberto</option>
                    <option value="PARCIALMENTE_LIQUIDADA">Parcialmente liquidada</option>
                    <option value="VENCIDA">Vencida</option>
                    <option value="LIQUIDADA">Liquidada</option>
                  </select>
                </Field>
                <Field label="Instituição">
                  <select
                    value={antLiqInstitution}
                    onChange={(e) => setAntLiqInstitution(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  >
                    <option value="">Todas</option>
                    {antecInstitutions.map((i) => (
                      <option key={i.id} value={i.id}>
                        {i.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Cliente (busca)">
                  <input
                    type="text"
                    value={antLiqClient}
                    onChange={(e) => setAntLiqClient(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                </Field>
                <Field label="Nº NF">
                  <input
                    type="text"
                    value={antLiqNf}
                    onChange={(e) => setAntLiqNf(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                </Field>
                <Field label="Borderô (SGC)">
                  <input
                    type="text"
                    value={antLiqSgc}
                    onChange={(e) => setAntLiqSgc(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    placeholder="Nº SGC"
                  />
                </Field>
              </div>
            </fieldset>
          </div>
        )}

        {type === "dashboard" && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <Field label={canGlobalDashboard ? "Projeto (opcional)" : "Projeto"}>
              <ProjectSelect
                value={dashProjectId}
                onChange={setDashProjectId}
                projects={projects}
                loading={loadingProjects}
                allowEmpty={canGlobalDashboard}
                emptyLabel="Consolidado (todos)"
              />
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
            disabled={busy || !type}
            onClick={() => void run("xlsx")}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
          >
            {busy ? "Gerando…" : "Gerar Excel"}
          </button>
          {type !== "antecipacoes" && (
            <button
              type="button"
              disabled={busy || !type}
              onClick={() => void run("pdf")}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            >
              Gerar PDF
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ProjectSelect({
  value,
  onChange,
  projects,
  loading,
  allowEmpty,
  emptyLabel = "Todos",
}: {
  value: string;
  onChange: (v: string) => void;
  projects: Project[];
  loading: boolean;
  allowEmpty?: boolean;
  emptyLabel?: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={loading}
      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
    >
      {allowEmpty ? <option value="">{emptyLabel}</option> : <option value="">Selecione…</option>}
      {projects.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </select>
  );
}

function ProjectMonthFilters({
  competencia,
  setCompetencia,
  projectId,
  setProjectId,
  projects,
  loadingProjects,
  required,
}: {
  competencia: string;
  setCompetencia: (v: string) => void;
  projectId: string;
  setProjectId: (v: string) => void;
  projects: Project[];
  loadingProjects: boolean;
  required?: boolean;
}) {
  return (
    <div className="space-y-3 border-t border-slate-100 pt-4">
      <Field label="Projeto" required={required}>
        <ProjectSelect
          value={projectId}
          onChange={setProjectId}
          projects={projects}
          loading={loadingProjects}
        />
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
  );
}

function InvoicePeriodFilters({
  invoiceProjectId,
  setInvoiceProjectId,
  invStatus,
  setInvStatus,
  invYear,
  setInvYear,
  invMonth,
  setInvMonth,
  projects,
  loadingProjects,
  hideProject,
  hideStatus,
}: {
  invoiceProjectId: string;
  setInvoiceProjectId: (v: string) => void;
  invStatus: string;
  setInvStatus: (v: string) => void;
  invYear: number | "";
  setInvYear: (v: number | "") => void;
  invMonth: number | "";
  setInvMonth: (v: number | "") => void;
  projects: Project[];
  loadingProjects: boolean;
  hideProject?: boolean;
  hideStatus?: boolean;
}) {
  return (
    <div className="space-y-3 border-t border-slate-100 pt-4">
      {!hideProject ? (
        <Field label="Projeto (opcional)">
          <ProjectSelect
            value={invoiceProjectId}
            onChange={setInvoiceProjectId}
            projects={projects}
            loading={loadingProjects}
            allowEmpty
          />
        </Field>
      ) : null}
      {!hideStatus ? (
        <Field label="Status">
          <select
            value={invStatus}
            onChange={(e) => setInvStatus(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">Todos</option>
            <option value="EMITIDA">Emitida</option>
            <option value="ANTECIPADA">Antecipada</option>
            <option value="FINALIZADA">Finalizada</option>
            <option value="CANCELADA">Cancelada</option>
          </select>
        </Field>
      ) : null}
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
          />
        </Field>
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
