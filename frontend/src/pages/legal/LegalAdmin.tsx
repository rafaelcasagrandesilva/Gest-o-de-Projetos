import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { hasPermission } from "@/permissions";
import { useAuth } from "@/context/AuthContext";
import { useWorkspace } from "@/context/WorkspaceContext";
import { Money } from "@/components/Money";
import {
  ActiveBadge,
  AdminTable,
  AdminToolbar,
  EmptyRow,
  Field,
  FormModal,
  RowActions,
  Th,
  inputClass,
} from "@/components/legal/LegalAdminPieces";
import { formatApiError } from "@/utils/apiError";
import {
  LEGAL_STATUS_LABELS,
  LEGAL_TYPE_LABELS,
  createLegalCase,
  createLegalCompany,
  createLegalPerson,
  createLegalProject,
  confirmLegalImport,
  fetchLegalOverview,
  listLegalImports,
  previewLegalImport,
  listLegalCases,
  listLegalChangeLogs,
  listLegalCompanies,
  listLegalPersons,
  listLegalProjectItems,
  setLegalCaseActive,
  setLegalCompanyActive,
  setLegalPersonActive,
  setLegalProjectActive,
  updateLegalCase,
  updateLegalCompany,
  updateLegalPerson,
  updateLegalProject,
  type LegalCase,
  type LegalCaseStatus,
  type LegalCaseType,
  type LegalChangeLog,
  type LegalCompany,
  type LegalFacets,
  type LegalImportEntry,
  type LegalImportIssue,
  type LegalImportReport,
  type LegalImportRun,
  type LegalPerson,
  type LegalProjectItem,
} from "@/services/legal";

/**
 * Administração do Workspace Jurídico — manutenção dos dados.
 *
 * Cinco abas numa única rota (`/legal/admin?tab=…`): Pessoas, Processos, Empresas, Projetos e
 * Importações. Regra transversal: **não existe exclusão física**. Todo "remover" é uma baixa
 * lógica (Desativar) reversível por Restaurar, e toda alteração manual gera histórico no backend.
 *
 * As abas Empresas/Projetos são o VOCABULÁRIO que alimenta os filtros das demais telas — por isso
 * cada linha mostra em quantos processos o nome é usado, para o admin ver o impacto antes de mexer.
 */

type TabKey = "persons" | "cases" | "companies" | "projects" | "imports";

const TABS: { key: TabKey; label: string }[] = [
  { key: "persons", label: "Desligados" },
  { key: "cases", label: "Processos" },
  { key: "companies", label: "Empresas" },
  { key: "projects", label: "Projetos" },
  { key: "imports", label: "Importações" },
];

/** Aba → recurso de permissão correspondente (um recurso por MENU, como no backend). */
const TAB_RESOURCE: Record<TabKey, string> = {
  persons: "legal_persons",
  cases: "legal_cases",
  companies: "legal_companies",
  projects: "legal_projects",
  imports: "legal_imports",
};

function matches(haystack: (string | null | undefined)[], needle: string): boolean {
  if (!needle.trim()) return true;
  const q = needle.trim().toLowerCase();
  return haystack.some((v) => (v ?? "").toLowerCase().includes(q));
}

/** Converte "" → null (o backend distingue "campo vazio" de "não enviado"). */
function orNull(v: string): string | null {
  const t = v.trim();
  return t ? t : null;
}

function numOrNull(v: string): number | null {
  const t = v.replace(/\./g, "").replace(",", ".").trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export function LegalAdmin() {
  const { user } = useAuth();
  const { setWorkspace } = useWorkspace();
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    setWorkspace("legal");
  }, [setWorkspace]);

  // Cada aba usa os verbos do SEU recurso: quem só pode editar Empresas não vê "Novo processo".
  const perms = user?.permission_names;
  const permsFor = (resource: string): CrudPerms => ({
    canCreate: hasPermission(perms, `${resource}.create`),
    canUpdate: hasPermission(perms, `${resource}.update`),
    canDeactivate: hasPermission(perms, `${resource}.delete`),
  });
  const casesPerms = permsFor("legal_cases");
  const personsPerms = permsFor("legal_persons");
  const companiesPerms = permsFor("legal_companies");
  const projectsPerms = permsFor("legal_projects");

  /** Aba visível quando o usuário pode ao menos LISTAR aquele recurso. */
  const visibleTabs = TABS.filter((t) => hasPermission(perms, `${TAB_RESOURCE[t.key]}.list`));
  const canImport = hasPermission(perms, "legal_imports.create");

  const tabParam = (searchParams.get("tab") ?? "") as TabKey;
  // Cai na primeira aba PERMITIDA — não numa aba que o usuário não pode abrir.
  const fallback: TabKey = visibleTabs[0]?.key ?? "imports";
  const tab: TabKey = visibleTabs.some((t) => t.key === tabParam) ? tabParam : fallback;

  function goTab(next: TabKey) {
    const p = new URLSearchParams(searchParams);
    p.set("tab", next);
    setSearchParams(p, { replace: true });
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Administração</h1>
        <p className="text-sm text-slate-500">
          Manutenção dos dados do Jurídico. Registros são desativados, nunca excluídos — e toda
          alteração fica registrada no histórico.
        </p>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {visibleTabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => goTab(t.key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition ${
              tab === t.key
                ? "border-indigo-600 text-indigo-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "persons" ? <PersonsTab {...personsPerms} /> : null}
      {tab === "cases" ? <CasesTab {...casesPerms} /> : null}
      {tab === "companies" ? <CompaniesTab {...companiesPerms} /> : null}
      {tab === "projects" ? <ProjectsTab {...projectsPerms} /> : null}
      {tab === "imports" ? <ImportsTab canRun={canImport} /> : null}
    </div>
  );
}

type CrudPerms = { canCreate: boolean; canUpdate: boolean; canDeactivate: boolean };

/** Painel de histórico reaproveitado pelas abas (últimas alterações da entidade). */
function HistoryPanel({ entityType, title }: { entityType: string; title: string }) {
  const [logs, setLogs] = useState<LegalChangeLog[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    void (async () => {
      try {
        setLogs(await listLegalChangeLogs({ entity_type: entityType, limit: 50 }));
      } catch {
        setLogs([]);
      }
    })();
  }, [open, entityType]);

  const ACTION_LABEL: Record<string, string> = {
    CREATE: "Criou",
    UPDATE: "Alterou",
    DEACTIVATE: "Desativou",
    RESTORE: "Restaurou",
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        <span>{title}</span>
        <span className="text-xs text-slate-400">{open ? "ocultar ▲" : "mostrar ▼"}</span>
      </button>
      {open ? (
        <div className="border-t border-slate-100 px-4 py-3">
          {logs.length === 0 ? (
            <p className="py-4 text-center text-sm text-slate-400">
              Nenhuma alteração manual registrada ainda.
            </p>
          ) : (
            <ul className="space-y-1.5 text-xs text-slate-600">
              {logs.map((l) => (
                <li key={l.id} className="flex flex-wrap gap-x-2">
                  <span className="tabular-nums text-slate-400">
                    {new Date(l.created_at).toLocaleString("pt-BR")}
                  </span>
                  <span className="font-medium text-slate-800">{ACTION_LABEL[l.action] ?? l.action}</span>
                  {l.field ? (
                    <span>
                      <span className="font-medium">{l.field}</span>: {l.old_value ?? "—"} →{" "}
                      {l.new_value ?? "—"}
                    </span>
                  ) : null}
                  {l.changed_by_email ? <span className="text-slate-400">· {l.changed_by_email}</span> : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ Pessoas */

function PersonsTab({ canCreate, canUpdate, canDeactivate }: CrudPerms) {
  const [rows, setRows] = useState<LegalPerson[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editing, setEditing] = useState<LegalPerson | "new" | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await listLegalPersons({ include_inactive: true }));
    } catch (e) {
      setError(formatApiError(e));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(
    () =>
      rows
        .filter((r) => (showInactive ? true : r.is_active))
        .filter((r) => matches([r.full_name, r.cpf, r.company, r.project], search)),
    [rows, showInactive, search],
  );

  async function toggleActive(row: LegalPerson) {
    setBusyId(row.id);
    setError(null);
    try {
      await setLegalPersonActive(row.id, !row.is_active);
      await load();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-3">
      <AdminToolbar
        description="Desligados e demais partes vinculadas aos processos."
        search={search}
        onSearch={setSearch}
        showInactive={showInactive}
        onShowInactive={setShowInactive}
        onCreate={() => setEditing("new")}
        createLabel="Nova pessoa"
        canCreate={canCreate}
        count={visible.length}
      />
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <AdminTable
        head={
          <>
            <Th>Nome</Th>
            <Th>CPF</Th>
            <Th>Empresa</Th>
            <Th>Projeto</Th>
            <Th align="right">Processos</Th>
            <Th>Situação</Th>
            <Th align="right">Ações</Th>
          </>
        }
      >
        {visible.length === 0 ? (
          <EmptyRow colSpan={7}>Nenhuma pessoa encontrada.</EmptyRow>
        ) : (
          visible.map((r) => (
            <tr
              key={r.id}
              className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 ${
                r.is_active ? "" : "opacity-60"
              }`}
            >
              <td className="max-w-[16rem] truncate px-3 py-2 font-medium text-slate-800" title={r.full_name}>
                {r.full_name}
              </td>
              <td className="whitespace-nowrap px-3 py-2 tabular-nums text-slate-600">{r.cpf ?? "—"}</td>
              <td className="max-w-[14rem] truncate px-3 py-2 text-slate-600" title={r.company ?? ""}>
                {r.company ?? "—"}
              </td>
              <td className="max-w-[14rem] truncate px-3 py-2 text-slate-600" title={r.project ?? ""}>
                {r.project ?? "—"}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-slate-700">{r.case_count}</td>
              <td className="px-3 py-2">
                <ActiveBadge active={r.is_active} />
              </td>
              <td className="px-3 py-2">
                <RowActions
                  active={r.is_active}
                  onEdit={() => setEditing(r)}
                  onToggle={() => void toggleActive(r)}
                  canEdit={canUpdate}
                  canToggle={r.is_active ? canDeactivate : canUpdate || canDeactivate}
                  busy={busyId === r.id}
                />
              </td>
            </tr>
          ))
        )}
      </AdminTable>

      <HistoryPanel entityType="PERSON" title="Histórico de alterações — Pessoas" />

      {editing ? (
        <PersonForm
          person={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await load();
          }}
        />
      ) : null}
    </div>
  );
}

function PersonForm({
  person,
  onClose,
  onSaved,
}: {
  person: LegalPerson | null;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const [fullName, setFullName] = useState(person?.full_name ?? "");
  const [cpf, setCpf] = useState(person?.cpf ?? "");
  const [company, setCompany] = useState(person?.company ?? "");
  const [project, setProject] = useState(person?.project ?? "");
  const [client, setClient] = useState(person?.client ?? "");
  const [role, setRole] = useState(person?.role ?? "");
  const [admission, setAdmission] = useState(person?.admission_date ?? "");
  const [termination, setTermination] = useState(person?.termination_date ?? "");
  const [notes, setNotes] = useState(person?.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [companies, setCompanies] = useState<string[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  useEffect(() => {
    void (async () => {
      try {
        const [c, p] = await Promise.all([listLegalCompanies(), listLegalProjectItems()]);
        setCompanies(c.map((x) => x.name));
        setProjects(p.map((x) => x.name));
      } catch {
        /* combos vazios não impedem o cadastro (os campos aceitam texto livre) */
      }
    })();
  }, []);

  async function submit() {
    if (!fullName.trim()) {
      setError("Informe o nome.");
      return;
    }
    setSaving(true);
    setError(null);
    const payload = {
      full_name: fullName.trim(),
      cpf: orNull(cpf),
      company: orNull(company),
      project: orNull(project),
      client: orNull(client),
      role: orNull(role),
      admission_date: orNull(admission),
      termination_date: orNull(termination),
      notes: orNull(notes),
    };
    try {
      if (person) await updateLegalPerson(person.id, payload);
      else await createLegalPerson(payload);
      await onSaved();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <FormModal
      title={person ? "Editar pessoa" : "Nova pessoa"}
      subtitle={person ? person.full_name : "Cadastro manual — gera histórico."}
      onClose={onClose}
      onSubmit={() => void submit()}
      submitting={saving}
      error={error}
    >
      <Field label="Nome completo" wide>
        <input className={inputClass} value={fullName} onChange={(e) => setFullName(e.target.value)} />
      </Field>
      <Field label="CPF">
        <input className={inputClass} value={cpf} onChange={(e) => setCpf(e.target.value)} placeholder="000.000.000-00" />
      </Field>
      <Field label="Cargo">
        <input className={inputClass} value={role} onChange={(e) => setRole(e.target.value)} />
      </Field>
      <Field label="Empresa" hint="Cadastradas na aba Empresas; aceita texto livre.">
        <input className={inputClass} list="legal-companies" value={company} onChange={(e) => setCompany(e.target.value)} />
        <datalist id="legal-companies">
          {companies.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>
      </Field>
      <Field label="Projeto / Contrato" hint="Cadastrados na aba Projetos; aceita texto livre.">
        <input className={inputClass} list="legal-projects" value={project} onChange={(e) => setProject(e.target.value)} />
        <datalist id="legal-projects">
          {projects.map((p) => (
            <option key={p} value={p} />
          ))}
        </datalist>
      </Field>
      <Field label="Cliente">
        <input className={inputClass} value={client} onChange={(e) => setClient(e.target.value)} />
      </Field>
      <Field label="Admissão">
        <input type="date" className={inputClass} value={admission} onChange={(e) => setAdmission(e.target.value)} />
      </Field>
      <Field label="Desligamento">
        <input type="date" className={inputClass} value={termination} onChange={(e) => setTermination(e.target.value)} />
      </Field>
      <Field label="Observações" wide>
        <textarea className={inputClass} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
    </FormModal>
  );
}

/* ----------------------------------------------------------------- Processos */

function CasesTab({ canCreate, canUpdate, canDeactivate }: CrudPerms) {
  const [rows, setRows] = useState<LegalCase[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editing, setEditing] = useState<LegalCase | "new" | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await listLegalCases({ include_inactive: true }));
    } catch (e) {
      setError(formatApiError(e));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(
    () =>
      rows
        .filter((r) => (showInactive ? true : r.is_active))
        .filter((r) => matches([r.case_number, r.person_name, r.claimant_name, r.company, r.project], search)),
    [rows, showInactive, search],
  );

  async function toggleActive(row: LegalCase) {
    setBusyId(row.id);
    setError(null);
    try {
      await setLegalCaseActive(row.id, !row.is_active);
      await load();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-3">
      <AdminToolbar
        description="Processos do módulo. Desativar remove o processo dos indicadores, preservando o registro."
        search={search}
        onSearch={setSearch}
        showInactive={showInactive}
        onShowInactive={setShowInactive}
        onCreate={() => setEditing("new")}
        createLabel="Novo processo"
        canCreate={canCreate}
        count={visible.length}
      />
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <AdminTable
        head={
          <>
            <Th>Processo</Th>
            <Th>Pessoa</Th>
            <Th>Empresa</Th>
            <Th>UF</Th>
            <Th>Status</Th>
            <Th align="right">Considerado</Th>
            <Th>Situação</Th>
            <Th align="right">Ações</Th>
          </>
        }
      >
        {visible.length === 0 ? (
          <EmptyRow colSpan={8}>Nenhum processo encontrado.</EmptyRow>
        ) : (
          visible.map((r) => (
            <tr
              key={r.id}
              className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 ${
                r.is_active ? "" : "opacity-60"
              }`}
            >
              <td className="whitespace-nowrap px-3 py-2 font-medium tabular-nums text-slate-800">
                {r.case_number}
              </td>
              <td className="max-w-[14rem] truncate px-3 py-2 text-slate-600">
                {r.person_name ?? r.claimant_name ?? "—"}
              </td>
              <td className="max-w-[12rem] truncate px-3 py-2 text-slate-600" title={r.company ?? ""}>
                {r.company ?? "—"}
              </td>
              <td className="px-3 py-2 text-slate-600">{r.uf ?? "—"}</td>
              <td className="px-3 py-2 text-slate-600">{LEGAL_STATUS_LABELS[r.status]}</td>
              <td className="px-3 py-2">
                <Money value={r.amount_considered} />
              </td>
              <td className="px-3 py-2">
                <ActiveBadge active={r.is_active} />
              </td>
              <td className="px-3 py-2">
                <RowActions
                  active={r.is_active}
                  onEdit={() => setEditing(r)}
                  onToggle={() => void toggleActive(r)}
                  canEdit={canUpdate}
                  canToggle={r.is_active ? canDeactivate : canUpdate || canDeactivate}
                  busy={busyId === r.id}
                />
              </td>
            </tr>
          ))
        )}
      </AdminTable>

      <HistoryPanel entityType="CASE" title="Histórico de alterações — Processos" />

      {editing ? (
        <CaseForm
          legalCase={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await load();
          }}
        />
      ) : null}
    </div>
  );
}

function CaseForm({
  legalCase,
  onClose,
  onSaved,
}: {
  legalCase: LegalCase | null;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const c = legalCase;
  const [caseNumber, setCaseNumber] = useState(c?.case_number ?? "");
  const [personId, setPersonId] = useState(c?.person_id ?? "");
  const [status, setStatus] = useState<LegalCaseStatus>(c?.status ?? "EM_ANDAMENTO");
  const [caseType, setCaseType] = useState<LegalCaseType>(c?.case_type ?? "TRABALHISTA");
  const [uf, setUf] = useState(c?.uf ?? "");
  const [court, setCourt] = useState(c?.court ?? "");
  const [company, setCompany] = useState(c?.company ?? "");
  const [project, setProject] = useState(c?.project ?? "");
  const [claimant, setClaimant] = useState(c?.claimant_name ?? "");
  const [defendant, setDefendant] = useState(c?.defendant_name ?? "");
  const [url, setUrl] = useState(c?.jusbrasil_url ?? "");
  const [claimed, setClaimed] = useState(c?.amount_claimed?.toString() ?? "");
  const [considered, setConsidered] = useState(c?.amount_considered?.toString() ?? "");
  const [agreed, setAgreed] = useState(c?.amount_agreed?.toString() ?? "");
  const [paid, setPaid] = useState(c?.amount_paid?.toString() ?? "");
  const [notes, setNotes] = useState(c?.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [people, setPeople] = useState<LegalPerson[]>([]);
  const [facets, setFacets] = useState<LegalFacets | null>(null);
  useEffect(() => {
    void (async () => {
      try {
        const [p, ov] = await Promise.all([listLegalPersons({}), fetchLegalOverview({})]);
        setPeople(p);
        setFacets(ov.facets);
      } catch {
        /* seletores vazios não impedem o cadastro */
      }
    })();
  }, []);

  async function submit() {
    if (!caseNumber.trim()) {
      setError("Informe o número do processo.");
      return;
    }
    setSaving(true);
    setError(null);
    const payload = {
      case_number: caseNumber.trim(),
      person_id: personId || null,
      status,
      case_type: caseType,
      uf: orNull(uf.toUpperCase()),
      court: orNull(court),
      company: orNull(company),
      project: orNull(project),
      claimant_name: orNull(claimant),
      defendant_name: orNull(defendant),
      jusbrasil_url: orNull(url),
      amount_claimed: numOrNull(claimed),
      amount_considered: numOrNull(considered),
      amount_agreed: numOrNull(agreed),
      amount_paid: numOrNull(paid),
      notes: orNull(notes),
    };
    try {
      if (c) await updateLegalCase(c.id, payload);
      else await createLegalCase(payload);
      await onSaved();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <FormModal
      title={c ? "Editar processo" : "Novo processo"}
      subtitle={c ? c.case_number : "Cadastro manual — gera histórico."}
      onClose={onClose}
      onSubmit={() => void submit()}
      submitting={saving}
      error={error}
    >
      <Field label="Número do processo" wide>
        <input className={inputClass} value={caseNumber} onChange={(e) => setCaseNumber(e.target.value)} />
      </Field>
      <Field label="Pessoa vinculada" hint="Opcional — processos da empresa podem não ter pessoa.">
        <select className={inputClass} value={personId} onChange={(e) => setPersonId(e.target.value)}>
          <option value="">Sem pessoa vinculada</option>
          {people.map((p) => (
            <option key={p.id} value={p.id}>
              {p.full_name}
              {p.cpf ? ` — ${p.cpf}` : ""}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Status">
        <select
          className={inputClass}
          value={status}
          onChange={(e) => setStatus(e.target.value as LegalCaseStatus)}
        >
          {(Object.keys(LEGAL_STATUS_LABELS) as LegalCaseStatus[]).map((s) => (
            <option key={s} value={s}>
              {LEGAL_STATUS_LABELS[s]}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Tipo">
        <select
          className={inputClass}
          value={caseType}
          onChange={(e) => setCaseType(e.target.value as LegalCaseType)}
        >
          {(Object.keys(LEGAL_TYPE_LABELS) as LegalCaseType[]).map((t) => (
            <option key={t} value={t}>
              {LEGAL_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Estado (UF)">
        <input className={inputClass} maxLength={2} value={uf} onChange={(e) => setUf(e.target.value)} />
      </Field>
      <Field label="Foro">
        <input className={inputClass} value={court} onChange={(e) => setCourt(e.target.value)} />
      </Field>
      <Field label="Empresa">
        <input className={inputClass} list="case-companies" value={company} onChange={(e) => setCompany(e.target.value)} />
        <datalist id="case-companies">
          {(facets?.companies ?? []).map((x) => (
            <option key={x} value={x} />
          ))}
        </datalist>
      </Field>
      <Field label="Projeto / Contrato">
        <input className={inputClass} list="case-projects" value={project} onChange={(e) => setProject(e.target.value)} />
        <datalist id="case-projects">
          {(facets?.projects ?? []).map((x) => (
            <option key={x} value={x} />
          ))}
        </datalist>
      </Field>
      <Field label="Reclamante">
        <input className={inputClass} value={claimant} onChange={(e) => setClaimant(e.target.value)} />
      </Field>
      <Field label="Reclamado">
        <input className={inputClass} value={defendant} onChange={(e) => setDefendant(e.target.value)} />
      </Field>
      <Field label="Link do JusBrasil" wide>
        <input className={inputClass} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
      </Field>
      <Field label="Valor da causa">
        <input className={inputClass} value={claimed} onChange={(e) => setClaimed(e.target.value)} placeholder="0,00" />
      </Field>
      <Field label="Valor considerado" hint="0 quando o processo espelha outro já contabilizado.">
        <input className={inputClass} value={considered} onChange={(e) => setConsidered(e.target.value)} placeholder="0,00" />
      </Field>
      <Field label="Valor acordado">
        <input className={inputClass} value={agreed} onChange={(e) => setAgreed(e.target.value)} placeholder="0,00" />
      </Field>
      <Field label="Valor pago">
        <input className={inputClass} value={paid} onChange={(e) => setPaid(e.target.value)} placeholder="0,00" />
      </Field>
      <Field label="Observações" wide>
        <textarea className={inputClass} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
    </FormModal>
  );
}

/* ------------------------------------------------------- Empresas / Projetos */

function CompaniesTab({ canCreate, canUpdate, canDeactivate }: CrudPerms) {
  const [rows, setRows] = useState<LegalCompany[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editing, setEditing] = useState<LegalCompany | "new" | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await listLegalCompanies(true));
    } catch (e) {
      setError(formatApiError(e));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(
    () =>
      rows
        .filter((r) => (showInactive ? true : r.is_active))
        .filter((r) => matches([r.name, r.cnpj], search)),
    [rows, showInactive, search],
  );

  async function toggleActive(row: LegalCompany) {
    setBusyId(row.id);
    setError(null);
    try {
      await setLegalCompanyActive(row.id, !row.is_active);
      await load();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-3">
      <AdminToolbar
        description="Empresas do grupo e demais partes reclamadas. Alimentam os filtros das telas do módulo."
        search={search}
        onSearch={setSearch}
        showInactive={showInactive}
        onShowInactive={setShowInactive}
        onCreate={() => setEditing("new")}
        createLabel="Nova empresa"
        canCreate={canCreate}
        count={visible.length}
      />
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <AdminTable
        head={
          <>
            <Th>Empresa</Th>
            <Th>CNPJ</Th>
            <Th align="right">Processos</Th>
            <Th>Situação</Th>
            <Th align="right">Ações</Th>
          </>
        }
      >
        {visible.length === 0 ? (
          <EmptyRow colSpan={5}>Nenhuma empresa cadastrada.</EmptyRow>
        ) : (
          visible.map((r) => (
            <tr
              key={r.id}
              className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 ${
                r.is_active ? "" : "opacity-60"
              }`}
            >
              <td className="px-3 py-2 font-medium text-slate-800">{r.name}</td>
              <td className="whitespace-nowrap px-3 py-2 tabular-nums text-slate-600">{r.cnpj ?? "—"}</td>
              <td className="px-3 py-2 text-right tabular-nums text-slate-700">{r.case_count}</td>
              <td className="px-3 py-2">
                <ActiveBadge active={r.is_active} />
              </td>
              <td className="px-3 py-2">
                <RowActions
                  active={r.is_active}
                  onEdit={() => setEditing(r)}
                  onToggle={() => void toggleActive(r)}
                  canEdit={canUpdate}
                  canToggle={r.is_active ? canDeactivate : canUpdate || canDeactivate}
                  busy={busyId === r.id}
                />
              </td>
            </tr>
          ))
        )}
      </AdminTable>

      <HistoryPanel entityType="COMPANY" title="Histórico de alterações — Empresas" />

      {editing ? (
        <CatalogForm
          kind="company"
          row={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await load();
          }}
        />
      ) : null}
    </div>
  );
}

function ProjectsTab({ canCreate, canUpdate, canDeactivate }: CrudPerms) {
  const [rows, setRows] = useState<LegalProjectItem[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editing, setEditing] = useState<LegalProjectItem | "new" | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await listLegalProjectItems(true));
    } catch (e) {
      setError(formatApiError(e));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(
    () =>
      rows
        .filter((r) => (showInactive ? true : r.is_active))
        .filter((r) => matches([r.name, r.client], search)),
    [rows, showInactive, search],
  );

  async function toggleActive(row: LegalProjectItem) {
    setBusyId(row.id);
    setError(null);
    try {
      await setLegalProjectActive(row.id, !row.is_active);
      await load();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-3">
      <AdminToolbar
        description="Projetos/contratos e seus clientes. Alimentam os filtros das telas do módulo."
        search={search}
        onSearch={setSearch}
        showInactive={showInactive}
        onShowInactive={setShowInactive}
        onCreate={() => setEditing("new")}
        createLabel="Novo projeto"
        canCreate={canCreate}
        count={visible.length}
      />
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <AdminTable
        head={
          <>
            <Th>Projeto / Contrato</Th>
            <Th>Cliente</Th>
            <Th align="right">Processos</Th>
            <Th>Situação</Th>
            <Th align="right">Ações</Th>
          </>
        }
      >
        {visible.length === 0 ? (
          <EmptyRow colSpan={5}>Nenhum projeto cadastrado.</EmptyRow>
        ) : (
          visible.map((r) => (
            <tr
              key={r.id}
              className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 ${
                r.is_active ? "" : "opacity-60"
              }`}
            >
              <td className="px-3 py-2 font-medium text-slate-800">{r.name}</td>
              <td className="px-3 py-2 text-slate-600">{r.client ?? "—"}</td>
              <td className="px-3 py-2 text-right tabular-nums text-slate-700">{r.case_count}</td>
              <td className="px-3 py-2">
                <ActiveBadge active={r.is_active} />
              </td>
              <td className="px-3 py-2">
                <RowActions
                  active={r.is_active}
                  onEdit={() => setEditing(r)}
                  onToggle={() => void toggleActive(r)}
                  canEdit={canUpdate}
                  canToggle={r.is_active ? canDeactivate : canUpdate || canDeactivate}
                  busy={busyId === r.id}
                />
              </td>
            </tr>
          ))
        )}
      </AdminTable>

      <HistoryPanel entityType="PROJECT" title="Histórico de alterações — Projetos" />

      {editing ? (
        <CatalogForm
          kind="project"
          row={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await load();
          }}
        />
      ) : null}
    </div>
  );
}

/** Formulário único de Empresa/Projeto — os dois cadastros só diferem no 2º campo. */
function CatalogForm({
  kind,
  row,
  onClose,
  onSaved,
}: {
  kind: "company" | "project";
  row: LegalCompany | LegalProjectItem | null;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const isCompany = kind === "company";
  const [name, setName] = useState(row?.name ?? "");
  const [second, setSecond] = useState(
    row ? (isCompany ? ((row as LegalCompany).cnpj ?? "") : ((row as LegalProjectItem).client ?? "")) : "",
  );
  const [notes, setNotes] = useState(row?.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!name.trim()) {
      setError("Informe o nome.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (isCompany) {
        const payload = { name: name.trim(), cnpj: orNull(second), notes: orNull(notes) };
        if (row) await updateLegalCompany(row.id, payload);
        else await createLegalCompany(payload);
      } else {
        const payload = { name: name.trim(), client: orNull(second), notes: orNull(notes) };
        if (row) await updateLegalProject(row.id, payload);
        else await createLegalProject(payload);
      }
      await onSaved();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setSaving(false);
    }
  }

  const label = isCompany ? "empresa" : "projeto";
  return (
    <FormModal
      title={`${row ? "Editar" : "Nova"} ${label}`}
      subtitle={
        row && row.case_count > 0
          ? `Usada em ${row.case_count} processo(s) — renomear NÃO altera os processos existentes.`
          : "Alimenta os filtros das telas do módulo."
      }
      onClose={onClose}
      onSubmit={() => void submit()}
      submitting={saving}
      error={error}
    >
      <Field label={isCompany ? "Nome da empresa" : "Nome do projeto"} wide>
        <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label={isCompany ? "CNPJ" : "Cliente"} wide>
        <input className={inputClass} value={second} onChange={(e) => setSecond(e.target.value)} />
      </Field>
      <Field label="Observações" wide>
        <textarea className={inputClass} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
    </FormModal>
  );
}

/* --------------------------------------------------------------- Importações */

/**
 * Importação da planilha oficial — a forma de alimentar o módulo.
 *
 * Fluxo em dois passos deliberados: **Analisar** roda a importação inteira em modo simulação e
 * mostra o que aconteceria; **Confirmar** repete a operação gravando. O mesmo serviço calcula os
 * dois, então o que está na tela é literalmente o que será executado.
 *
 * A planilha nunca exclui: registros que sumirem do arquivo permanecem no sistema, e coluna vazia
 * não apaga valor já gravado.
 */
function ImportsTab({ canRun }: { canRun: boolean }) {
  const [spreadsheet, setSpreadsheet] = useState<File | null>(null);
  const [panel, setPanel] = useState<File | null>(null);
  const [report, setReport] = useState<LegalImportReport | null>(null);
  const [busy, setBusy] = useState<"preview" | "confirm" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<LegalImportRun[]>([]);

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await listLegalImports());
    } catch {
      setHistory([]);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  function pick(setter: (f: File | null) => void) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setter(e.target.files?.[0] ?? null);
      setReport(null);
      setError(null);
    };
  }

  async function run(step: "preview" | "confirm") {
    if (!spreadsheet) return;
    setBusy(step);
    setError(null);
    try {
      const fn = step === "preview" ? previewLegalImport : confirmLegalImport;
      setReport(await fn(spreadsheet, panel));
      if (step === "confirm") await loadHistory();
    } catch (e) {
      setReport(null);
      setError(formatApiError(e));
    } finally {
      setBusy(null);
    }
  }

  const s = report?.summary;

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="text-base font-semibold text-slate-900">Importar a planilha do Jurídico</h2>
        <p className="mt-1 text-sm text-slate-500">
          A planilha consolidada é o formato oficial do módulo — envie o arquivo exatamente como a
          consultoria entrega. A importação <strong>cria os novos e atualiza os existentes</strong>;
          registros que saírem da planilha continuam no sistema (a exclusão é sempre manual).
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <FilePicker
            label="Planilha consolidada (.xlsx)"
            hint="Obrigatória — aba “Processos e Demitidos M&E”."
            accept=".xlsx"
            file={spreadsheet}
            onChange={pick(setSpreadsheet)}
            disabled={!canRun || busy !== null}
          />
          <FilePicker
            label="Painel de Passivo (.html)"
            hint="Opcional — traz valor da causa, valor considerado e o link do JusBrasil."
            accept=".html,.htm"
            file={panel}
            onChange={pick(setPanel)}
            disabled={!canRun || busy !== null}
          />
        </div>

        {spreadsheet && !panel ? (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Sem o Painel de Passivo os valores da causa, o valor considerado e os links do JusBrasil
            não vêm no arquivo. Nada é apagado: o que já estiver gravado é preservado.
          </p>
        ) : null}

        {!canRun ? (
          <p className="mt-3 text-xs text-slate-500">
            Seu perfil não tem permissão para importar (Jurídico · Importações).
          </p>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!canRun || !spreadsheet || busy !== null}
            onClick={() => void run("preview")}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busy === "preview" ? "Analisando…" : "Analisar arquivos"}
          </button>
          {report && !report.applied ? (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void run("confirm")}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {busy === "confirm" ? "Importando…" : "Confirmar importação"}
            </button>
          ) : null}
          {report?.applied ? (
            <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800">
              Importação concluída
            </span>
          ) : null}
        </div>

        {error ? (
          <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</p>
        ) : null}
      </div>

      {report && s ? (
        <div className="space-y-3">
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-sm font-semibold text-slate-900">
                {report.applied ? "Resultado da importação" : "Pré-visualização"}
              </h3>
              <span className="text-xs text-slate-400">
                {report.spreadsheet}
                {report.panel ? ` + ${report.panel}` : " (sem o Painel de Passivo)"} ·{" "}
                {s.rows_read} linhas lidas
              </span>
            </div>

            <div className="mt-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
              <ImportStat label="Novos desligados" value={s.people_new} tone="emerald" />
              <ImportStat label="Desligados atualizados" value={s.people_updated} tone="indigo" />
              <ImportStat label="Novos processos" value={s.cases_new} tone="emerald" />
              <ImportStat label="Processos atualizados" value={s.cases_updated} tone="indigo" />
              <ImportStat label="Duplicados" value={s.duplicates} tone="slate" />
              <ImportStat label="Erros" value={s.errors} tone={s.errors ? "rose" : "slate"} />
            </div>

            <p className="mt-3 text-xs text-slate-500">
              Sem alteração: {s.people_unchanged} desligados e {s.cases_unchanged} processos ·
              Linhas ignoradas: {s.ignored} · Avisos: {s.warnings}
              {report.panel
                ? ` · Painel: ${s.panel_matched} de ${s.panel_rows} entradas vinculadas`
                : ""}
            </p>
            {report.truncated ? (
              <p className="mt-1 text-xs text-slate-400">
                As listas abaixo mostram os primeiros 500 itens de cada categoria; os totais acima
                estão completos.
              </p>
            ) : null}
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <ImportList title="Novos desligados" entries={report.new_people} />
            <ImportList title="Desligados atualizados" entries={report.updated_people} />
            <ImportList title="Novos processos" entries={report.new_cases} />
            <ImportList title="Processos atualizados" entries={report.updated_cases} />
          </div>

          <ImportIssues title="Duplicados encontrados" issues={report.duplicates} />
          <ImportIssues title="Erros e avisos" issues={report.issues} />
          <ImportIssues title="Linhas ignoradas" issues={report.ignored} />
        </div>
      ) : null}

      <ImportHistory runs={history} />
    </div>
  );
}

/** Trilha de auditoria: uma linha por importação CONFIRMADA (pré-visualização não entra). */
function ImportHistory({ runs }: { runs: LegalImportRun[] }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white">
      <div className="flex items-baseline justify-between px-4 py-2.5">
        <h3 className="text-sm font-semibold text-slate-900">Histórico de importações</h3>
        <span className="text-xs text-slate-400">{runs.length} registro(s)</span>
      </div>
      {runs.length === 0 ? (
        <p className="border-t border-slate-100 py-6 text-center text-sm text-slate-400">
          Nenhuma importação executada ainda.
        </p>
      ) : (
        <div className="overflow-x-auto border-t border-slate-100">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                <Th>Data</Th>
                <Th>Usuário</Th>
                <Th>Arquivos</Th>
                <Th align="right">Linhas</Th>
                <Th align="right">Desligados</Th>
                <Th align="right">Processos</Th>
                <Th align="right">Ignorados</Th>
                <Th align="right">Erros</Th>
                <Th align="right">Tempo</Th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-b border-slate-50 last:border-0">
                  <td className="px-3 py-2 whitespace-nowrap text-slate-700">
                    {new Date(r.created_at).toLocaleString("pt-BR")}
                  </td>
                  <td className="px-3 py-2 text-slate-600">{r.executed_by_email ?? "—"}</td>
                  <td className="px-3 py-2 text-xs text-slate-500">
                    {r.spreadsheet_name}
                    {r.panel_name ? (
                      <span className="block text-slate-400">+ {r.panel_name}</span>
                    ) : (
                      <span className="block text-slate-400">somente planilha</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-600">{r.rows_read}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-600">
                    +{r.people_new} / ~{r.people_updated}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-600">
                    +{r.cases_new} / ~{r.cases_updated}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-600">{r.ignored}</td>
                  <td
                    className={`px-3 py-2 text-right tabular-nums ${
                      r.errors ? "font-semibold text-rose-700" : "text-slate-600"
                    }`}
                  >
                    {r.errors}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-500">
                    {(r.duration_ms / 1000).toFixed(1)}s
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-3 py-2 text-[11px] text-slate-400">
            “+N / ~M” = criados / atualizados. Pré-visualizações não geram registro.
          </p>
        </div>
      )}
    </div>
  );
}

function FilePicker({
  label,
  hint,
  accept,
  file,
  onChange,
  disabled,
}: {
  label: string;
  hint: string;
  accept: string;
  file: File | null;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  disabled: boolean;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-slate-700">{label}</span>
      <input
        type="file"
        accept={accept}
        onChange={onChange}
        disabled={disabled}
        className="mt-1 block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-200 disabled:opacity-50"
      />
      <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>
      {file ? (
        <span className="mt-1 block text-[11px] text-slate-500">
          {file.name} · {Math.max(1, Math.round(file.size / 1024))} KB
        </span>
      ) : null}
    </label>
  );
}

function ImportStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "emerald" | "indigo" | "rose" | "slate";
}) {
  const TONES = {
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-900",
    indigo: "border-indigo-200 bg-indigo-50 text-indigo-900",
    rose: "border-rose-200 bg-rose-50 text-rose-900",
    slate: "border-slate-200 bg-slate-50 text-slate-700",
  } as const;
  return (
    <div className={`rounded-lg border px-3 py-2 ${TONES[tone]}`}>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
      <div className="text-[11px] leading-tight">{label}</div>
    </div>
  );
}

/** Lista recolhível: o resumo já responde "quanto", isto responde "quais". */
function ImportList({ title, entries }: { title: string; entries: LegalImportEntry[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={entries.length === 0}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-default disabled:text-slate-400"
      >
        <span>
          {title} <span className="tabular-nums">({entries.length})</span>
        </span>
        {entries.length ? (
          <span className="text-xs text-slate-400">{open ? "ocultar ▲" : "mostrar ▼"}</span>
        ) : null}
      </button>
      {open && entries.length ? (
        <ul className="max-h-72 overflow-y-auto border-t border-slate-100 px-4 py-2 text-sm">
          {entries.map((e, i) => (
            <li key={`${e.label}-${i}`} className="border-b border-slate-50 py-1.5 last:border-0">
              <span className="font-medium text-slate-800">{e.label}</span>
              {e.detail ? <span className="text-slate-400"> · {e.detail}</span> : null}
              {e.changes.length ? (
                <span className="block text-xs text-slate-500">{e.changes.join(", ")}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ImportIssues({ title, issues }: { title: string; issues: LegalImportIssue[] }) {
  const [open, setOpen] = useState(false);
  if (!issues.length) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        <span>
          {title} <span className="tabular-nums">({issues.length})</span>
        </span>
        <span className="text-xs text-slate-400">{open ? "ocultar ▲" : "mostrar ▼"}</span>
      </button>
      {open ? (
        <ul className="max-h-72 overflow-y-auto border-t border-slate-100 px-4 py-2 text-sm">
          {issues.map((issue, i) => (
            <li key={i} className="border-b border-slate-50 py-1.5 last:border-0">
              <span
                className={`mr-2 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                  issue.level === "ERROR"
                    ? "bg-rose-100 text-rose-800"
                    : "bg-amber-100 text-amber-900"
                }`}
              >
                {issue.level === "ERROR" ? "ERRO" : "AVISO"}
              </span>
              {issue.row ? <span className="text-slate-400">Linha {issue.row} · </span> : null}
              {issue.identifier ? (
                <span className="font-medium text-slate-800">{issue.identifier} · </span>
              ) : null}
              <span className="text-slate-600">{issue.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
