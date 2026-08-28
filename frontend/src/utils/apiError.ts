import { isAxiosError } from "axios";

function cleanValidationMsg(msg: string): string {
  return msg.replace(/^Value error,\s*/i, "");
}

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
        const m = cleanValidationMsg(item.msg ?? "");
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

/**
 * Respostas com `responseType: "blob"` também entregam o corpo de ERRO como Blob,
 * então o `detail` do FastAPI se perde. Converte o corpo para JSON no próprio erro
 * para que `formatApiError` consiga ler a causa real.
 */
export async function hydrateBlobError(e: unknown): Promise<unknown> {
  if (isAxiosError(e) && e.response?.data instanceof Blob) {
    try {
      e.response.data = JSON.parse(await e.response.data.text());
    } catch {
      /* corpo não-JSON: mantém o Blob e o chamador usa a mensagem padrão */
    }
  }
  return e;
}
