import { api } from "./api";

export interface UserRow {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  role_names: string[];
  project_ids: string[];
  created_at: string;
  updated_at: string;
}

export async function listUsers(): Promise<UserRow[]> {
  const { data } = await api.get<UserRow[]>("/users/");
  return data;
}

export async function createUser(payload: {
  email: string;
  full_name: string;
  password: string;
  is_active?: boolean;
  role_name: "ADMIN" | "GESTOR" | "CONSULTA";
  project_ids?: string[];
}): Promise<UserRow> {
  const { data } = await api.post<UserRow>("/users/", {
    email: payload.email,
    full_name: payload.full_name,
    password: payload.password,
    is_active: payload.is_active ?? true,
    role_name: payload.role_name,
    project_ids: payload.project_ids,
  });
  return data;
}

export async function patchUser(
  userId: string,
  body: {
    full_name?: string;
    is_active?: boolean;
    role_name?: "ADMIN" | "GESTOR" | "CONSULTA";
    project_ids?: string[];
  },
): Promise<UserRow> {
  const { data } = await api.patch<UserRow>(`/users/${userId}/`, body);
  return data;
}

export async function resetUserPassword(userId: string, newPassword: string): Promise<void> {
  await api.post(`/users/${userId}/reset-password/`, { new_password: newPassword });
}
