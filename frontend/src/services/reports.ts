import { api } from "./api";
import { isAxiosError } from "axios";

export type ReportType =
  | "project_summary"
  | "company_summary"
  | "employees"
  | "vehicles"
  | "invoices"
  | "debt"
  | "fixed_costs"
  | "dashboard"
  | "users"
  | "revenues";

export type ReportFormat = "xlsx" | "pdf";

export type ReportFilters = Record<string, string | number | boolean | undefined | null>;

export async function generateReport(
  type: ReportType,
  format: ReportFormat,
  filters: ReportFilters,
): Promise<void> {
  const clean: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries(filters)) {
    if (v === undefined || v === null || v === "") continue;
    clean[k] = v as string | number | boolean;
  }
  try {
    const res = await api.post("/reports/generate", { type, format, filters: clean }, { responseType: "blob" });
    const blob = res.data as Blob;
    const cd = res.headers["content-disposition"] as string | undefined;
    let name = `relatorio_${type}.${format}`;
    const m = cd?.match(/filename="([^"]+)"/i) ?? cd?.match(/filename=([^;\s]+)/i);
    if (m?.[1]) name = m[1].trim();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    if (isAxiosError(e) && e.response?.data instanceof Blob) {
      const text = await e.response.data.text();
      try {
        const j = JSON.parse(text) as { detail?: unknown };
        const d = j.detail;
        throw new Error(typeof d === "string" ? d : "Erro ao gerar relatório.");
      } catch {
        throw new Error(text.slice(0, 200) || "Erro ao gerar relatório.");
      }
    }
    throw e;
  }
}
