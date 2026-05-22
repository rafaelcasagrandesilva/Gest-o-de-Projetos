/** Formatação e parsing monetário pt-BR (valor em reais, não centavos-first). */

const BRL_FIELD = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Remove símbolos de moeda e espaços extras. */
function stripCurrencyDecorations(raw: string): string {
  return raw.replace(/R\$\s?/gi, "").replace(/\s/g, "").trim();
}

/**
 * Interpreta entrada do usuário como valor em reais.
 * - 500 -> 500
 * - 12,5 / 12.5 -> 12.5
 * - 1.250,90 -> 1250.9
 */
export function parseBRLInput(raw: string): number {
  let cleaned = stripCurrencyDecorations(raw);
  if (!cleaned) return 0;

  if (cleaned.includes(",")) {
    cleaned = cleaned.replace(/\./g, "").replace(",", ".");
    const n = Number(cleaned);
    return Number.isFinite(n) ? Math.max(0, n) : 0;
  }

  if (cleaned.includes(".")) {
    const parts = cleaned.split(".");
    const last = parts[parts.length - 1] ?? "";
    const isDecimalDot = parts.length === 2 && last.length > 0 && last.length <= 2;
    if (isDecimalDot) {
      const n = Number(cleaned);
      return Number.isFinite(n) ? Math.max(0, n) : 0;
    }
    const n = Number(cleaned.replace(/\./g, ""));
    return Number.isFinite(n) ? Math.max(0, n) : 0;
  }

  const digits = cleaned.replace(/\D/g, "");
  if (!digits) return 0;
  const n = Number(digits);
  return Number.isFinite(n) ? Math.max(0, n) : 0;
}

/** Exibe valor no campo (edição); vazio quando zero ou inválido. */
export function formatMoneyFieldBr(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "";
  return BRL_FIELD.format(n);
}

/** Inicializa campo a partir de valor numérico do backend (inclui zero explícito como vazio). */
export function moneyFieldFromNumber(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n <= 0) return "";
  return formatMoneyFieldBr(n);
}

/** Permite apenas caracteres válidos durante a digitação. */
export function sanitizeMoneyTyping(raw: string): string {
  return raw.replace(/[^\d.,]/g, "");
}
