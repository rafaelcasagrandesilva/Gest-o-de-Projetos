import { api } from "./api";
import { isAxiosError } from "axios";

export type ReportType =
  | "project_summary"
  | "company_summary"
  | "employees"
  | "payroll"
  | "vehicles"
  | "invoices"
  | "debt"
  | "fixed_costs"
  | "dashboard"
  | "users"
  | "revenues"
  | "payables_detailed"
  | "receivables_detailed"
  | "invoices_detailed"
  | "assets_inventory"
  | "assets_in_use"
  | "assets_inspections"
  | "assets_movements"
  | "antecipacoes";

export type ReportFormat = "xlsx" | "pdf";

export type ReportFilters = Record<string, string | number | boolean | undefined | null>;

export type ReportScenario = "PREVISTO" | "REALIZADO";

/**
 * Extrai o nome amigável do arquivo do cabeçalho Content-Disposition.
 * Prioriza `filename*` (RFC 5987, com acentos em pt-BR); usa `filename` como
 * alternativa. Sem nome técnico como fallback — apenas um genérico em português.
 */
function filenameFromDisposition(cd: string | undefined, ext: string): string {
  if (cd) {
    const star = cd.match(/filename\*=(?:UTF-8'')?([^;]+)/i);
    if (star?.[1]) {
      try {
        return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
      } catch {
        /* cai para filename simples */
      }
    }
    const plain = cd.match(/filename="([^"]+)"/i) ?? cd.match(/filename=([^;\s]+)/i);
    if (plain?.[1]) return plain[1].trim();
  }
  return `Relatório.${ext}`;
}

export async function generateReport(
  type: ReportType,
  format: ReportFormat,
  filters: ReportFilters,
  scenario?: ReportScenario,
): Promise<void> {
  const clean: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries(filters)) {
    if (v === undefined || v === null || v === "") continue;
    clean[k] = v as string | number | boolean;
  }
  const body: {
    type: ReportType;
    format: ReportFormat;
    filters: typeof clean;
    scenario?: ReportScenario;
  } = { type, format, filters: clean };
  if (scenario) body.scenario = scenario;
  try {
    const res = await api.post("/reports/generate/", body, { responseType: "blob" });
    const blob = res.data as Blob;
    const cd = res.headers["content-disposition"] as string | undefined;
    const name = filenameFromDisposition(cd, format);
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
