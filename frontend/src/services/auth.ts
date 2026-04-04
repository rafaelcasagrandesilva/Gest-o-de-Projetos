import { api, setStoredToken } from "./api";

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface UserMe {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  role_names: string[];
  project_ids?: string[];
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>("/auth/login/", { email, password });
  setStoredToken(data.access_token);
  return data;
}

export async function fetchMe(): Promise<UserMe> {
  const { data } = await api.get<UserMe>("/users/me/");
  return data;
}

export function logout(): void {
  setStoredToken(null);
}
