/** Texto para busca: minúsculo e sem acento ("Conceição" → "conceicao"). */
export function normalizeSearchText(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{M}/gu, "");
}

/**
 * Busca por PALAVRAS: cada palavra digitada precisa aparecer em algum dos campos, em qualquer
 * ordem e até pela metade. "Paulo Arieiro" encontra "Paulo Afonso da Silva Arieiro"; "arieir"
 * também. Sem acento e sem diferenciar maiúsculas.
 */
export function matchesSearchWords(fields: Array<string | null | undefined>, query: string): boolean {
  const words = normalizeSearchText(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = fields.map((f) => normalizeSearchText(f ?? "")).join(" ");
  return words.every((w) => haystack.includes(w));
}
