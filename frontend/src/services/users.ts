import { api } from "./api";

export interface UserRow {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  deleted_at?: string | null;
  role_names: string[];
  project_ids: string[];
  permission_names: string[];
  created_at: string;
  updated_at: string;
}

export interface RoleRow {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  is_active: boolean;
  user_count: number;
  permission_names: string[];
  created_at: string;
  updated_at: string;
}

export async function listRoles(): Promise<RoleRow[]> {
  const { data } = await api.get<RoleRow[]>("/users/roles");
  return data;
}

export async function createRole(payload: {
  name: string;
  description?: string | null;
  is_active?: boolean;
  permission_names?: string[] | null;
  base_role_id?: string | null;
}): Promise<RoleRow> {
  const { data } = await api.post<RoleRow>("/users/roles", payload);
  return data;
}

export async function updateRole(
  roleId: string,
  body: { name?: string; description?: string | null; is_active?: boolean; permission_names?: string[] },
): Promise<RoleRow> {
  const { data } = await api.patch<RoleRow>(`/users/roles/${roleId}`, body);
  return data;
}

export async function deleteRole(roleId: string): Promise<void> {
  await api.delete(`/users/roles/${roleId}`);
}

export async function listUsers(params?: { include_deleted?: boolean }): Promise<UserRow[]> {
  const { data } = await api.get<UserRow[]>("/users/", { params });
  return data;
}

export async function createUser(payload: {
  email: string;
  full_name: string;
  password: string;
  is_active?: boolean;
  role_name: string;
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
    role_name?: string;
    project_ids?: string[];
    permission_names?: string[];
  },
): Promise<UserRow> {
  const { data } = await api.patch<UserRow>(`/users/${userId}/`, body);
  return data;
}

export async function resetUserPassword(userId: string, newPassword: string): Promise<void> {
  await api.post(`/users/${userId}/reset-password/`, { new_password: newPassword });
}

export async function activateUser(userId: string): Promise<UserRow> {
  const { data } = await api.patch<UserRow>(`/users/${userId}/activate/`, {});
  return data;
}

export async function deactivateUser(userId: string): Promise<UserRow> {
  const { data } = await api.patch<UserRow>(`/users/${userId}/deactivate/`, {});
  return data;
}

export async function softDeleteUser(userId: string): Promise<void> {
  await api.delete(`/users/${userId}/`);
}
