import { api } from "@/services/api";

/**
 * Workspace Jurídico — Processos e Pessoas.
 *
 * Todo campo monetário é `number | null`: `null` = valor OMITIDO pelo backend por falta de
 * `legal.sensitive` (não é zero). Renderize com `formatCurrencyOrDash` / `<Money>`.
 */

export type LegalCaseStatus =
  | "EM_ANDAMENTO"
  | "COM_DECISAO"
  | "SUSPENSO"
  | "ACORDO"
  | "ACORDO_FINALIZADO"
  | "ENCERRADO"
  | "SEM_PROCESSO";

export type LegalCaseType = "TRABALHISTA" | "CIVEL" | "TRIBUTARIO" | "OUTRO";

/** Base de valor dos gráficos, dos totais por barra e da faixa de valor. */
export type LegalValueBasis = "considered" | "claimed";

export type LegalCase = {
  id: string;
  is_active: boolean;
  case_number: string;
  jusbrasil_url: string | null;
  person_id: string | null;
  person_name: string | null;
  person_cpf: string | null;
  status: LegalCaseStatus;
  case_type: LegalCaseType;
  nature: string | null;
  uf: string | null;
  court: string | null;
  city: string | null;
  company: string | null;
  project: string | null;
  client: string | null;
  claimant_name: string | null;
  defendant_name: string | null;
  amount_claimed: number | null;
  amount_considered: number | null;
  amount_agreed: number | null;
  amount_paid: number | null;
  amount_pending: number | null;
  agreement_terms: string | null;
  last_movement: string | null;
  last_movement_date: string | null;
  hearing_date: string | null;
  distribution_date: string | null;
  notes: string | null;
};

export type LegalPerson = {
  id: string;
  full_name: string;
  cpf: string | null;
  company: string | null;
  project: string | null;
  client: string | null;
  role: string | null;
  admission_date: string | null;
  termination_date: string | null;
  severance_amount: number | null;
  fgts_balance: number | null;
  notes: string | null;
  is_active: boolean;
  case_count: number;
  total_claimed: number | null;
  total_considered: number | null;
  total_agreed: number | null;
  total_paid: number | null;
  total_pending: number | null;
};

export type LegalPersonDetail = LegalPerson & { cases: LegalCase[] };

export type LegalKpis = {
  case_count: number;
  person_count: number;
  total_claimed: number | null;
  total_considered: number | null;
  total_agreed: number | null;
  total_paid: number | null;
  total_pending: number | null;
};

export type LegalBucket = { key: string; label: string; value: number | null; count: number };

export type LegalFacets = {
  statuses: LegalCaseStatus[];
  types: LegalCaseType[];
  ufs: string[];
  companies: string[];
  projects: string[];
  clients: string[];
};

export type LegalOverview = {
  kpis: LegalKpis;
  by_status: LegalBucket[];
  by_type: LegalBucket[];
  by_uf: LegalBucket[];
  by_company: LegalBucket[];
  by_project: LegalBucket[];
  facets: LegalFacets;
};

export type LegalCaseFilters = {
  /** Administração: inclui registros desativados (telas analíticas nunca enviam). */
  include_inactive?: boolean;
  status?: string[];
  type?: string[];
  uf?: string[];
  company?: string[];
  project?: string[];
  client?: string[];
  person_id?: string;
  value_min?: number | null;
  value_max?: number | null;
  q?: string;
  basis?: LegalValueBasis;
};

/**
 * Filtros → query string. Listas viram parâmetros repetidos (`?status=A&status=B`), que é o
 * formato que o FastAPI espera para `Query(list[str])`. Vazio/nulo é omitido.
 */
function caseParams(filters: LegalCaseFilters): URLSearchParams {
  const params = new URLSearchParams();
  const lists: [string, string[] | undefined][] = [
    ["status", filters.status],
    ["type", filters.type],
    ["uf", filters.uf],
    ["company", filters.company],
    ["project", filters.project],
    ["client", filters.client],
  ];
  for (const [key, values] of lists) {
    for (const value of values ?? []) params.append(key, value);
  }
  if (filters.person_id) params.set("person_id", filters.person_id);
  if (filters.value_min != null) params.set("value_min", String(filters.value_min));
  if (filters.value_max != null) params.set("value_max", String(filters.value_max));
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.basis) params.set("basis", filters.basis);
  if (filters.include_inactive) params.set("include_inactive", "true");
  return params;
}

export async function listLegalCases(filters: LegalCaseFilters = {}): Promise<LegalCase[]> {
  const { data } = await api.get<LegalCase[]>(`/legal/cases?${caseParams(filters)}`);
  return data;
}

/** Um processo pelo id — usado pelo deep link vindo da Central de Trabalho. */
export async function getLegalCase(id: string): Promise<LegalCase> {
  const { data } = await api.get<LegalCase>(`/legal/cases/${id}`);
  return data;
}

export async function fetchLegalOverview(filters: LegalCaseFilters = {}): Promise<LegalOverview> {
  const { data } = await api.get<LegalOverview>(`/legal/cases/overview?${caseParams(filters)}`);
  return data;
}

export type LegalPersonFilters = {
  company?: string[];
  project?: string[];
  client?: string[];
  has_cases?: boolean | null;
  q?: string;
  include_inactive?: boolean;
};

export async function listLegalPersons(filters: LegalPersonFilters = {}): Promise<LegalPerson[]> {
  const params = new URLSearchParams();
  for (const value of filters.company ?? []) params.append("company", value);
  for (const value of filters.project ?? []) params.append("project", value);
  for (const value of filters.client ?? []) params.append("client", value);
  if (filters.has_cases != null) params.set("has_cases", String(filters.has_cases));
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.include_inactive) params.set("include_inactive", "true");
  const { data } = await api.get<LegalPerson[]>(`/legal/persons?${params}`);
  return data;
}

export async function fetchLegalPersonFacets(): Promise<LegalFacets> {
  const { data } = await api.get<LegalFacets>("/legal/persons/facets");
  return data;
}

export async function fetchLegalPerson(personId: string): Promise<LegalPersonDetail> {
  const { data } = await api.get<LegalPersonDetail>(`/legal/persons/${personId}`);
  return data;
}

// ---------------------------------------------------------------------------
// Administração (Fase 2) — CRUD sem exclusão física
// ---------------------------------------------------------------------------

export type LegalPersonInput = {
  full_name: string;
  cpf?: string | null;
  company?: string | null;
  project?: string | null;
  client?: string | null;
  role?: string | null;
  admission_date?: string | null;
  termination_date?: string | null;
  severance_amount?: number | null;
  fgts_balance?: number | null;
  notes?: string | null;
};

export type LegalCaseInput = {
  case_number: string;
  person_id?: string | null;
  jusbrasil_url?: string | null;
  status?: LegalCaseStatus;
  case_type?: LegalCaseType;
  uf?: string | null;
  court?: string | null;
  company?: string | null;
  project?: string | null;
  client?: string | null;
  claimant_name?: string | null;
  defendant_name?: string | null;
  amount_claimed?: number | null;
  amount_considered?: number | null;
  amount_agreed?: number | null;
  amount_paid?: number | null;
  amount_pending?: number | null;
  notes?: string | null;
};

export type LegalCompany = {
  id: string;
  name: string;
  cnpj: string | null;
  notes: string | null;
  is_active: boolean;
  case_count: number;
};

export type LegalProjectItem = {
  id: string;
  name: string;
  client: string | null;
  notes: string | null;
  is_active: boolean;
  case_count: number;
};

export type LegalChangeLog = {
  id: string;
  created_at: string;
  entity_type: "PERSON" | "CASE" | "COMPANY" | "PROJECT";
  entity_id: string;
  action: "CREATE" | "UPDATE" | "DEACTIVATE" | "RESTORE";
  field: string | null;
  old_value: string | null;
  new_value: string | null;
  changed_by_email: string | null;
};

export async function createLegalPerson(data: LegalPersonInput): Promise<LegalPerson> {
  return (await api.post<LegalPerson>("/legal/persons", data)).data;
}
export async function updateLegalPerson(id: string, data: Partial<LegalPersonInput>): Promise<LegalPerson> {
  return (await api.patch<LegalPerson>(`/legal/persons/${id}`, data)).data;
}
/** Baixa LÓGICA — nunca exclusão física. */
export async function setLegalPersonActive(id: string, active: boolean): Promise<LegalPerson> {
  const action = active ? "restore" : "deactivate";
  return (await api.post<LegalPerson>(`/legal/persons/${id}/${action}`)).data;
}

export async function createLegalCase(data: LegalCaseInput): Promise<LegalCase> {
  return (await api.post<LegalCase>("/legal/cases", data)).data;
}
export async function updateLegalCase(id: string, data: Partial<LegalCaseInput>): Promise<LegalCase> {
  return (await api.patch<LegalCase>(`/legal/cases/${id}`, data)).data;
}
export async function setLegalCaseActive(id: string, active: boolean): Promise<LegalCase> {
  const action = active ? "restore" : "deactivate";
  return (await api.post<LegalCase>(`/legal/cases/${id}/${action}`)).data;
}

export async function listLegalCompanies(includeInactive = false): Promise<LegalCompany[]> {
  const q = includeInactive ? "?include_inactive=true" : "";
  return (await api.get<LegalCompany[]>(`/legal/companies${q}`)).data;
}
export async function createLegalCompany(data: { name: string; cnpj?: string | null; notes?: string | null }) {
  return (await api.post<LegalCompany>("/legal/companies", data)).data;
}
export async function updateLegalCompany(id: string, data: { name?: string; cnpj?: string | null; notes?: string | null }) {
  return (await api.patch<LegalCompany>(`/legal/companies/${id}`, data)).data;
}
export async function setLegalCompanyActive(id: string, active: boolean) {
  const action = active ? "restore" : "deactivate";
  return (await api.post<LegalCompany>(`/legal/companies/${id}/${action}`)).data;
}

export async function listLegalProjectItems(includeInactive = false): Promise<LegalProjectItem[]> {
  const q = includeInactive ? "?include_inactive=true" : "";
  return (await api.get<LegalProjectItem[]>(`/legal/projects${q}`)).data;
}
export async function createLegalProject(data: { name: string; client?: string | null; notes?: string | null }) {
  return (await api.post<LegalProjectItem>("/legal/projects", data)).data;
}
export async function updateLegalProject(id: string, data: { name?: string; client?: string | null; notes?: string | null }) {
  return (await api.patch<LegalProjectItem>(`/legal/projects/${id}`, data)).data;
}
export async function setLegalProjectActive(id: string, active: boolean) {
  const action = active ? "restore" : "deactivate";
  return (await api.post<LegalProjectItem>(`/legal/projects/${id}/${action}`)).data;
}

export async function listLegalChangeLogs(params: {
  entity_type?: string;
  entity_id?: string;
  limit?: number;
} = {}): Promise<LegalChangeLog[]> {
  const q = new URLSearchParams();
  if (params.entity_type) q.set("entity_type", params.entity_type);
  if (params.entity_id) q.set("entity_id", params.entity_id);
  if (params.limit) q.set("limit", String(params.limit));
  return (await api.get<LegalChangeLog[]>(`/legal/change-logs?${q}`)).data;
}

/* --------------------------------------------------------- Importação da planilha */

export type LegalImportIssue = {
  level: "ERROR" | "WARNING";
  message: string;
  /** Linha da planilha como aparece no Excel (cabeçalho = 1). */
  row: number | null;
  identifier: string | null;
};

export type LegalImportEntry = {
  label: string;
  detail: string | null;
  /** Rótulos dos campos que mudam (vazio quando o registro é novo). */
  changes: string[];
};

export type LegalImportSummary = {
  rows_read: number;
  people_new: number;
  people_updated: number;
  people_unchanged: number;
  cases_new: number;
  cases_updated: number;
  cases_unchanged: number;
  duplicates: number;
  errors: number;
  warnings: number;
  ignored: number;
  panel_rows: number;
  panel_matched: number;
};

/** Pré-visualização (`applied: false`) e relatório final compartilham o mesmo formato. */
export type LegalImportReport = {
  applied: boolean;
  spreadsheet: string;
  sheet: string;
  panel: string | null;
  summary: LegalImportSummary;
  new_people: LegalImportEntry[];
  updated_people: LegalImportEntry[];
  new_cases: LegalImportEntry[];
  updated_cases: LegalImportEntry[];
  duplicates: LegalImportIssue[];
  issues: LegalImportIssue[];
  ignored: LegalImportIssue[];
  truncated: boolean;
};

/** Uma importação já executada (trilha de auditoria). */
export type LegalImportRun = {
  id: string;
  created_at: string;
  spreadsheet_name: string;
  /** null = importação só com a planilha (o padrão depois da carga inicial). */
  panel_name: string | null;
  rows_read: number;
  people_new: number;
  people_updated: number;
  cases_new: number;
  cases_updated: number;
  unchanged: number;
  ignored: number;
  duplicates: number;
  errors: number;
  warnings: number;
  duration_ms: number;
  executed_by_email: string | null;
};

export async function listLegalImports(limit = 50): Promise<LegalImportRun[]> {
  return (await api.get<LegalImportRun[]>(`/legal/imports?limit=${limit}`)).data;
}

function importForm(spreadsheet: File, panel: File | null): FormData {
  const form = new FormData();
  form.append("spreadsheet", spreadsheet);
  if (panel) form.append("panel", panel);
  return form;
}

/** Simula a importação: nada é gravado. */
export async function previewLegalImport(
  spreadsheet: File,
  panel: File | null,
): Promise<LegalImportReport> {
  const { data } = await api.post<LegalImportReport>(
    "/legal/imports/preview",
    importForm(spreadsheet, panel),
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}

/** Executa a importação. Os mesmos arquivos da pré-visualização dão o mesmo resultado. */
export async function confirmLegalImport(
  spreadsheet: File,
  panel: File | null,
): Promise<LegalImportReport> {
  const { data } = await api.post<LegalImportReport>(
    "/legal/imports/confirm",
    importForm(spreadsheet, panel),
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}

/** Rótulos pt-BR — espelham `STATUS_LABELS`/`TYPE_LABELS` em app/services/legal_service.py. */
export const LEGAL_STATUS_LABELS: Record<LegalCaseStatus, string> = {
  EM_ANDAMENTO: "Em andamento",
  COM_DECISAO: "Com decisão/sentença",
  SUSPENSO: "Suspenso/Sobrestado",
  ACORDO: "Acordo",
  ACORDO_FINALIZADO: "Acordo finalizado",
  ENCERRADO: "Encerrado/Arquivado",
  SEM_PROCESSO: "Sem processo cadastrado",
};

export const LEGAL_TYPE_LABELS: Record<LegalCaseType, string> = {
  TRABALHISTA: "Trabalhista",
  CIVEL: "Cível",
  TRIBUTARIO: "Tributário",
  OUTRO: "Outro",
};

/**
 * Cor semântica por status (mesma leitura do Painel de Passivo: âmbar = ativo, vermelho = decisão,
 * azul = suspenso, verde = encerrado/acordo fechado). Classes Tailwind para pílula e barra.
 */
export const LEGAL_STATUS_STYLES: Record<
  LegalCaseStatus,
  { pill: string; bar: string; dot: string }
> = {
  EM_ANDAMENTO: { pill: "bg-amber-100 text-amber-900", bar: "bg-amber-500", dot: "bg-amber-500" },
  COM_DECISAO: { pill: "bg-rose-100 text-rose-900", bar: "bg-rose-500", dot: "bg-rose-500" },
  ACORDO: { pill: "bg-violet-100 text-violet-900", bar: "bg-violet-500", dot: "bg-violet-500" },
  ACORDO_FINALIZADO: {
    pill: "bg-teal-100 text-teal-900",
    bar: "bg-teal-500",
    dot: "bg-teal-500",
  },
  SUSPENSO: { pill: "bg-sky-100 text-sky-900", bar: "bg-sky-500", dot: "bg-sky-500" },
  ENCERRADO: {
    pill: "bg-emerald-100 text-emerald-900",
    bar: "bg-emerald-500",
    dot: "bg-emerald-500",
  },
  SEM_PROCESSO: { pill: "bg-slate-100 text-slate-700", bar: "bg-slate-400", dot: "bg-slate-400" },
};
