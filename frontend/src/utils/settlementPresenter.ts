// Presenter dos Eventos de Liquidação — fonte ÚNICA de formatação amigável no frontend.
// A API devolve dados estruturados (number, nf_numbers…); a montagem das strings fica aqui,
// reutilizada por Extrato de Liquidações, detalhe do evento e Timeline.

const EVENT_PREFIX = "LQ";

/** Identificador operacional amigável do evento. Ex.: 42 -> "LQ-000042". */
export function eventCode(numberValue: number | null | undefined): string {
  if (numberValue == null) return "—";
  return `${EVENT_PREFIX}-${String(numberValue).padStart(6, "0")}`;
}

/** Resumo legível das NFs. "NF 3397" (uma) ou "NFs 3351, 3353, 3364" (várias). */
export function nfSummary(nfNumbers: (string | null | undefined)[] | null | undefined): string {
  const seen: string[] = [];
  for (const n of nfNumbers ?? []) {
    const s = (n ?? "").toString().trim();
    if (s && !seen.includes(s)) seen.push(s);
  }
  if (seen.length === 0) return "—";
  if (seen.length === 1) return `NF ${seen[0]}`;
  return `NFs ${seen.join(", ")}`;
}
