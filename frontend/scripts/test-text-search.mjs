/**
 * Testes da busca por palavras (rodar: node frontend/scripts/test-text-search.mjs).
 *
 * Espelha a lógica de src/utils/textSearch.ts. Caso que motivou: o nome do colaborador foi
 * completado no cadastro ("Paulo Afonso da Silva Arieiro") e a busca "Paulo Arieiro" deixou
 * de encontrar os títulos, porque procurava a frase inteira em sequência.
 */

import assert from "node:assert/strict";

function normalizeSearchText(value) {
  return value.trim().toLowerCase().normalize("NFD").replace(/\p{M}/gu, "");
}

function matchesSearchWords(fields, query) {
  const words = normalizeSearchText(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = fields.map((f) => normalizeSearchText(f ?? "")).join(" ");
  return words.every((w) => haystack.includes(w));
}

const titulo = ["Paulo Afonso da Silva Arieiro — Retirada de Capital", null, "Administrativo", "Colaborador"];
assert.ok(matchesSearchWords(titulo, "Paulo Arieiro"));
assert.ok(matchesSearchWords(titulo, "arieiro paulo")); // qualquer ordem
assert.ok(matchesSearchWords(titulo, "Paulo Arieir")); // palavra pela metade
assert.ok(matchesSearchWords(titulo, "retirada")); 
assert.ok(matchesSearchWords(titulo, "  ")); // busca vazia mostra tudo
assert.ok(!matchesSearchWords(titulo, "Paulo Marques"));
// Sem acento e sem diferenciar maiúsculas; o subtítulo também conta.
assert.ok(matchesSearchWords(["Paulo Arieiro — Reembolso", "Combustível ao Mateus"], "COMBUSTIVEL mateus"));
assert.ok(matchesSearchWords(["Conceição"], "conceicao"));

console.log("✓ test:text-search");
