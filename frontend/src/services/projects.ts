import { api } from "./api";

export interface Project {
  id: string;
  name: string;
  code: string | null;
  description: string | null;
  cost_center?: string | null;
  // Dados contratuais (cadastrais).
  contract_number?: string | null;
  contract_value?: number | null;
  contract_start_date?: string | null;
  /** Prazo total em meses. */
  contract_duration?: number | null;
  /** Data final ORIGINAL derivada (início + prazo) — somente leitura. */
  contract_end_date?: string | null;
  /** Vigência atual derivada (início + prazo + Σ prazos dos aditivos) — somente leitura. */
  current_validity_date?: string | null;
  /** Σ dos prazos adicionais (meses) dos aditivos. */
  additive_months_total?: number;
  buyer_name?: string | null;
  buyer_phone?: string | null;
  buyer_email?: string | null;
  manager_name?: string | null;
  manager_phone?: string | null;
  manager_email?: string | null;
  created_at: string;
  updated_at: string;
  is_active: boolean;
  closed_at?: string | null;
  deleted_at?: string | null;
}

export interface ProjectContractAdditive {
  id: string;
  project_id: string;
  additive_date: string | null;
  additive_value: number | null;
  additive_duration: string | null;
  /** Data final derivada (data do aditivo + prazo adicional) — somente leitura. */
  additive_end_date?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends Project {
  additives: ProjectContractAdditive[];
}

/** Campos contratuais editáveis no modal Detalhes. */
export interface ProjectContractInput {
  contract_number?: string | null;
  contract_value?: number | null;
  contract_start_date?: string | null;
  contract_duration?: number | null;
  buyer_name?: string | null;
  buyer_phone?: string | null;
  buyer_email?: string | null;
  manager_name?: string | null;
  manager_phone?: string | null;
  manager_email?: string | null;
}

export interface AdditiveInput {
  additive_date?: string | null;
  additive_value?: number | null;
  additive_duration?: string | null;
}

export type ProjectDocumentCategory =
  | "CONTRATO"
  | "ADITIVO"
  | "CRONOGRAMA"
  | "ART"
  | "MEMORIAL"
  | "LICENCA"
  | "OUTRO";

export const PROJECT_DOCUMENT_CATEGORIES: { value: ProjectDocumentCategory; label: string }[] = [
  { value: "CONTRATO", label: "Contrato" },
  { value: "ADITIVO", label: "Aditivo" },
  { value: "CRONOGRAMA", label: "Cronograma" },
  { value: "ART", label: "ART" },
  { value: "MEMORIAL", label: "Memorial" },
  { value: "LICENCA", label: "Licença" },
  { value: "OUTRO", label: "Outro" },
];

export interface ProjectDocument {
  id: string;
  project_id: string;
  category: ProjectDocumentCategory;
  title: string;
  original_filename: string;
  uploaded_by: string | null;
  uploaded_by_name: string | null;
  uploaded_at: string;
  download_url: string | null;
  created_at: string;
  updated_at: string;
}

export type ProjectStatusFilter = "ACTIVE" | "CLOSED" | "ALL";

export async function listProjects(params?: {
  status?: ProjectStatusFilter;
  /** Padrão API: 50; use até 200 para listagens completas (ex.: selects). */
  limit?: number;
  offset?: number;
}): Promise<Project[]> {
  const { data } = await api.get<Project[]>("/projects/", { params });
  return data;
}

export async function createProject(payload: {
  name: string;
  description?: string | null;
}): Promise<Project> {
  const { data } = await api.post<Project>("/projects/", {
    name: payload.name,
    description: payload.description || null,
  });
  return data;
}

export async function getProject(id: string): Promise<Project> {
  const { data } = await api.get<Project>(`/projects/${id}/`);
  return data;
}

/** Detalhe do projeto com dados contratuais + aditivos (modal Detalhes). */
export async function getProjectDetail(id: string): Promise<ProjectDetail> {
  const { data } = await api.get<ProjectDetail>(`/projects/${id}`);
  return data;
}

/** Salva os dados contratuais/comprador/gestor do projeto. */
export async function updateProjectContract(
  id: string,
  payload: ProjectContractInput,
): Promise<Project> {
  const { data } = await api.patch<Project>(`/projects/${id}`, payload);
  return data;
}

/** Salva os dados básicos (aba Geral) reutilizando o mesmo endpoint de atualização. */
export async function updateProjectGeneral(
  id: string,
  payload: { name?: string; description?: string | null },
): Promise<Project> {
  const { data } = await api.patch<Project>(`/projects/${id}`, payload);
  return data;
}

export type ContractValidityTone = "normal" | "warning" | "expired";

export interface ContractValidityInfo {
  /** Data da vigência formatada dd/mm/aaaa, ou "—". */
  dateBr: string;
  /** Dias restantes (negativo = vencido) ou null se sem vigência. */
  days: number | null;
  tone: ContractValidityTone;
}

/** Regra única de vigência (baseada na Vigência Atual, considerando aditivos).
 *  > 180 dias: normal · até 180 dias: warning · vencido: expired. */
export function contractValidityInfo(validityIso: string | null | undefined): ContractValidityInfo {
  if (!validityIso) return { dateBr: "—", days: null, tone: "normal" };
  const [y, m, d] = validityIso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return { dateBr: "—", days: null, tone: "normal" };
  const dateBr = `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const end = new Date(y, m - 1, d);
  const days = Math.round((end.getTime() - start.getTime()) / 86400000);
  const tone: ContractValidityTone = days < 0 ? "expired" : days <= 180 ? "warning" : "normal";
  return { dateBr, days, tone };
}

export async function createProjectAdditive(
  projectId: string,
  payload: AdditiveInput,
): Promise<ProjectContractAdditive> {
  const { data } = await api.post<ProjectContractAdditive>(
    `/projects/${projectId}/additives`,
    payload,
  );
  return data;
}

export async function updateProjectAdditive(
  projectId: string,
  additiveId: string,
  payload: AdditiveInput,
): Promise<ProjectContractAdditive> {
  const { data } = await api.patch<ProjectContractAdditive>(
    `/projects/${projectId}/additives/${additiveId}`,
    payload,
  );
  return data;
}

export async function deleteProjectAdditive(projectId: string, additiveId: string): Promise<void> {
  await api.delete(`/projects/${projectId}/additives/${additiveId}`);
}

// --- Documentos do projeto ---

export async function listProjectDocuments(projectId: string): Promise<ProjectDocument[]> {
  const { data } = await api.get<ProjectDocument[]>(`/projects/${projectId}/documents`);
  return data;
}

export async function uploadProjectDocument(
  projectId: string,
  payload: { category: ProjectDocumentCategory; title: string; file: File },
): Promise<ProjectDocument> {
  const form = new FormData();
  form.append("file", payload.file);
  form.append("category", payload.category);
  form.append("title", payload.title);
  const { data } = await api.post<ProjectDocument>(`/projects/${projectId}/documents`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

/** Baixa o documento (blob autenticado) e dispara o download no navegador. */
export async function downloadProjectDocument(doc: ProjectDocument): Promise<void> {
  const { data } = await api.get<Blob>(`/projects/${doc.project_id}/documents/${doc.id}/download`, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = doc.original_filename || doc.title;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function deleteProjectDocument(projectId: string, documentId: string): Promise<void> {
  await api.delete(`/projects/${projectId}/documents/${documentId}`);
}

export async function deactivateProject(id: string): Promise<Project> {
  const { data } = await api.patch<Project>(`/projects/${id}/deactivate`);
  return data;
}

export async function activateProject(id: string): Promise<Project> {
  const { data } = await api.patch<Project>(`/projects/${id}/activate`);
  return data;
}

export async function softDeleteProject(id: string): Promise<void> {
  await api.delete(`/projects/${id}/`);
}
