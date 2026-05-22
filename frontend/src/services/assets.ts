import { api } from "@/services/api";

export type AssetStatus =
  | "AVAILABLE"
  | "IN_USE"
  | "MAINTENANCE"
  | "EXPIRED"
  | "LOST"
  | "DISCARDED";

export type AssetPhysicalCondition = "NEW" | "GOOD" | "FAIR" | "DAMAGED";

export type ExpirationAlertLevel = "NORMAL" | "YELLOW" | "ORANGE" | "TOMORROW" | "RED";

export type AssetAttachmentType =
  | "TERM"
  | "REPORT"
  | "CERTIFICATE"
  | "INVOICE"
  | "MANUAL"
  | "PHOTO"
  | "MAINTENANCE_ORDER"
  | "OTHER";

export type AssetListItem = {
  id: string;
  asset_code: string;
  name: string;
  category: string;
  subcategory: string | null;
  size: string | null;
  status: AssetStatus;
  physical_condition: AssetPhysicalCondition | null;
  purchase_value: number | null;
  cost_center_label: string | null;
  cost_center_ref: string | null;
  current_holder_id: string | null;
  current_holder_name: string | null;
  has_inspection_control: boolean;
  next_expiration_date: string | null;
  expiration_alert: ExpirationAlertLevel | null;
};

export type AssetRead = AssetListItem & {
  tags?: string[] | null;
  description: string | null;
  brand: string | null;
  model: string | null;
  serial_number: string | null;
  patrimony_tag: string | null;
  imei: string | null;
  ca_number: string | null;
  acquisition_date: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type AssetAssignment = {
  id: string;
  asset_id: string;
  employee_id: string;
  employee_name: string;
  delivered_by_employee_id: string | null;
  delivered_by_name: string | null;
  delivery_date: string;
  return_date: string | null;
  returned_by_employee_id: string | null;
  returned_by_name: string | null;
  returned_to_employee_id: string | null;
  returned_to_name: string | null;
  returned_condition: AssetPhysicalCondition | null;
  return_notes: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type AssetInspection = {
  id: string;
  asset_id: string;
  inspection_type: string;
  inspection_date: string;
  expiration_months: number | null;
  expiration_date: string | null;
  responsible_company: string | null;
  report_attachment_id: string | null;
  notes: string | null;
  expiration_alert: ExpirationAlertLevel | null;
  created_at: string;
  updated_at: string;
};

export type AssetAttachment = {
  id: string;
  asset_id: string;
  file_name: string;
  file_type: AssetAttachmentType;
  mime_type: string | null;
  created_at: string;
  download_url: string | null;
};

export type AssetTimelineEvent = {
  kind: string;
  at: string;
  title: string;
  detail: string | null;
};

export type AssetDetail = AssetRead & {
  assignments: AssetAssignment[];
  inspections: AssetInspection[];
  attachments: AssetAttachment[];
  timeline: AssetTimelineEvent[];
};

export type AssetCreatePayload = {
  name: string;
  category: string;
  subcategory?: string | null;
  tags?: string[] | null;
  size?: string | null;
  description?: string | null;
  brand?: string | null;
  model?: string | null;
  serial_number?: string | null;
  patrimony_tag?: string | null;
  imei?: string | null;
  ca_number?: string | null;
  status?: AssetStatus;
  physical_condition?: AssetPhysicalCondition | null;
  acquisition_date?: string | null;
  purchase_value?: number | null;
  notes?: string | null;
  cost_center_ref?: string | null;
};

export async function fetchAssetCategories(): Promise<string[]> {
  const { data } = await api.get<string[]>("/assets/meta/categories");
  return data;
}

export async function listAssets(params?: {
  q?: string;
  category?: string;
  status?: AssetStatus;
  employee_id?: string;
  cost_center_ref?: string;
  expiration?: string;
  size?: string;
  without_holder?: boolean;
  physical_condition?: AssetPhysicalCondition;
}): Promise<AssetListItem[]> {
  const { data } = await api.get<AssetListItem[]>("/assets", { params });
  return data;
}

export async function createAsset(payload: AssetCreatePayload): Promise<AssetRead> {
  const { data } = await api.post<AssetRead>("/assets", payload);
  return data;
}

export async function getAssetDetail(assetId: string): Promise<AssetDetail> {
  const { data } = await api.get<AssetDetail>(`/assets/${assetId}`);
  return data;
}

export async function updateAsset(assetId: string, payload: Partial<AssetCreatePayload>): Promise<AssetRead> {
  const { data } = await api.patch<AssetRead>(`/assets/${assetId}`, payload);
  return data;
}

export async function deleteAsset(assetId: string): Promise<void> {
  await api.delete(`/assets/${assetId}`);
}

export async function createAssignment(
  assetId: string,
  payload: {
    employee_id: string;
    delivered_by_employee_id: string;
    delivery_date: string;
    notes?: string | null;
  },
): Promise<AssetAssignment> {
  const { data } = await api.post<AssetAssignment>(`/assets/${assetId}/assignments`, payload);
  return data;
}

export async function returnAssignment(
  assetId: string,
  assignmentId: string,
  payload: {
    return_date: string;
    returned_to_employee_id: string;
    returned_condition: AssetPhysicalCondition;
    return_notes?: string | null;
  },
): Promise<AssetAssignment> {
  const { data } = await api.post<AssetAssignment>(
    `/assets/${assetId}/assignments/${assignmentId}/return`,
    payload,
  );
  return data;
}

export async function updateReturnAssignment(
  assetId: string,
  assignmentId: string,
  payload: {
    return_date?: string;
    returned_to_employee_id?: string;
    returned_condition?: AssetPhysicalCondition;
    return_notes?: string | null;
  },
): Promise<AssetAssignment> {
  const { data } = await api.patch<AssetAssignment>(
    `/assets/${assetId}/assignments/${assignmentId}/return`,
    payload,
  );
  return data;
}

export async function deleteReturnAssignment(
  assetId: string,
  assignmentId: string,
): Promise<AssetAssignment> {
  const { data } = await api.delete<AssetAssignment>(
    `/assets/${assetId}/assignments/${assignmentId}/return`,
  );
  return data;
}

export async function deleteAssignment(assetId: string, assignmentId: string): Promise<void> {
  await api.delete(`/assets/${assetId}/assignments/${assignmentId}`);
}

export async function createInspection(
  assetId: string,
  payload: {
    inspection_type: string;
    inspection_date: string;
    expiration_months?: number | null;
    expiration_date?: string | null;
    responsible_company?: string | null;
    notes?: string | null;
  },
): Promise<AssetInspection> {
  const { data } = await api.post<AssetInspection>(`/assets/${assetId}/inspections`, payload);
  return data;
}

export async function deleteInspection(assetId: string, inspectionId: string): Promise<void> {
  await api.delete(`/assets/${assetId}/inspections/${inspectionId}`);
}

export async function uploadAssetAttachment(
  assetId: string,
  file: File,
  fileType: AssetAttachmentType,
): Promise<AssetAttachment> {
  const form = new FormData();
  form.append("file", file);
  form.append("file_type", fileType);
  const { data } = await api.post<AssetAttachment>(`/assets/${assetId}/attachments`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteAssetAttachment(assetId: string, attachmentId: string): Promise<void> {
  await api.delete(`/assets/${assetId}/attachments/${attachmentId}`);
}
