import { api } from "@/services/api";

export type AuditExportFilters = {
  date_start?: string;
  date_end?: string;
  user_id?: string;
  entity?: string;
};

function parseFilename(contentDisposition: string | undefined): string | null {
  if (!contentDisposition) return null;
  const m = /filename="([^"]+)"/i.exec(contentDisposition);
  return m?.[1] ?? null;
}

/** Baixa relatório de auditoria (.txt) com streaming no backend. */
export async function downloadAuditLogExport(filters: AuditExportFilters = {}): Promise<void> {
  const params: Record<string, string> = {};
  if (filters.date_start) params.date_start = filters.date_start;
  if (filters.date_end) params.date_end = filters.date_end;
  if (filters.user_id) params.user_id = filters.user_id;
  if (filters.entity) params.entity = filters.entity;

  const res = await api.get("/admin/audit/export", {
    params,
    responseType: "blob",
    timeout: 120_000,
  });

  const blob = res.data as Blob;
  const cd = res.headers["content-disposition"] as string | undefined;
  const name = parseFilename(cd) ?? `audit-export-${new Date().toISOString().slice(0, 10)}.txt`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
