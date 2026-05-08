import { isAxiosError } from "axios";

/** Converte `detail` do FastAPI (string, lista de erros de validação ou objeto) em texto legível. */
export function formatApiError(e: unknown): string {
  if (!isAxiosError(e)) {
    return e instanceof Error ? e.message : "Erro inesperado.";
  }
  const d = e.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d
      .map((item: { loc?: (string | number)[]; msg?: string }) => {
        const loc = item.loc?.filter((x) => x !== "body").join(".") ?? "";
        const m = item.msg ?? "";
        return loc ? `${loc}: ${m}` : m;
      })
      .filter(Boolean)
      .join(" ");
  }
  if (d && typeof d === "object" && "message" in d && typeof (d as { message: unknown }).message === "string") {
    return (d as { message: string }).message;
  }
  return e.message;
}
