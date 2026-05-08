import { api } from "./api";

export interface Project {
  id: string;
  name: string;
  code: string | null;
  description: string | null;
  cost_center?: string | null;
  created_at: string;
  updated_at: string;
  is_active: boolean;
  closed_at?: string | null;
  deleted_at?: string | null;
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
