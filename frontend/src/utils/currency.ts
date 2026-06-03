/**
 * Utilitário central de moeda (BRL, reais com 2 casas decimais).
 * Valores da API chegam como número (ex.: 365575.21); na UI use sempre pt-BR (365.575,21).
 */

const BRL_CURRENCY = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const BRL_FIELD = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Remove símbolo de moeda e espaços. */
export function stripCurrencyDecorations(raw: string): string {
  return raw.replace(/R\$\s?/gi, "").replace(/\s/g, "").trim();
}

/**
 * Interpreta texto digitado ou colado pelo usuário (pt-BR ou número simples).
 * Nunca trata ponto como separador de milhar quando é separador decimal (ex.: "365575.21" da API).
 */
export function parseCurrencyInput(raw: string): number {
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

export function roundCurrency(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 100) / 100;
}

/** Ex.: 365575.21 → "R$ 365.575,21" */
export function formatCurrency(n: number): string {
  if (!Number.isFinite(n)) return BRL_CURRENCY.format(0);
  return BRL_CURRENCY.format(n);
}

/** Ex.: 365575.21 → "365.575,21" (campos de formulário, sem símbolo R$). */
export function formatCurrencyField(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "";
  return BRL_FIELD.format(n);
}

/** Inicializa campo a partir de valor numérico da API (evita String(n) → "365575.21"). */
export function formatCurrencyInputFromApi(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "";
  return formatCurrencyField(n);
}

/** Valor seguro para payload JSON da API (número com 2 casas). */
export function normalizeCurrencyForApi(value: string | number | null | undefined): number {
  if (value == null || value === "") return 0;
  if (typeof value === "number") return roundCurrency(value);
  return roundCurrency(parseCurrencyInput(String(value)));
}

/** Durante digitação: apenas dígitos, vírgula e ponto. */
export function sanitizeCurrencyTyping(raw: string): string {
  return raw.replace(/[^\d.,]/g, "");
}
