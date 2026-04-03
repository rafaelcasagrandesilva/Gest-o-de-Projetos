import { api } from "./api";

export interface EmployeeAllocation {
  id: string;
  created_at: string;
  updated_at: string;
  employee_id: string;
  project_id: string;
  start_date: string;
  end_date: string | null;
  allocation_percent: number;
  monthly_cost: number | null;
  hours_allocated: number | null;
}

export interface EmployeeAllocationCreate {
  employee_id: string;
  project_id: string;
  start_date: string;
  end_date?: string | null;
  allocation_percent?: number;
  monthly_cost?: number | null;
  hours_allocated?: number | null;
}

export async function listProjectAllocations(projectId: string): Promise<EmployeeAllocation[]> {
  const { data } = await api.get<EmployeeAllocation[]>(`/projects/${projectId}/allocations`);
  return data;
}

export async function createProjectAllocation(
  projectId: string,
  payload: Omit<EmployeeAllocationCreate, "project_id">
): Promise<EmployeeAllocation> {
  const { data } = await api.post<EmployeeAllocation>(`/projects/${projectId}/allocations`, {
    ...payload,
    project_id: projectId,
  });
  return data;
}
