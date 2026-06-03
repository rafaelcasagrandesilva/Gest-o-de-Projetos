/**
 * Testes de regressão do utilitário de moeda (rodar: node frontend/scripts/test-currency.mjs).
 * Espelha casos de tests/test_money.py no backend.
 */

import assert from "node:assert/strict";

const BRL_FIELD = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function stripCurrencyDecorations(raw) {
  return raw.replace(/R\$\s?/gi, "").replace(/\s/g, "").trim();
}

function parseCurrencyInput(raw) {
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

function formatCurrencyInputFromApi(n) {
  if (n == null || !Number.isFinite(n)) return "";
  return BRL_FIELD.format(n);
}

function normalizeCurrencyForApi(value) {
  if (value == null || value === "") return 0;
  if (typeof value === "number") return Math.round(value * 100) / 100;
  return Math.round(parseCurrencyInput(String(value)) * 100) / 100;
}

const cases = [
  ["365.575,21", 365575.21],
  ["10.000,00", 10000],
  ["1.234,56", 1234.56],
  ["0,01", 0.01],
  ["0,10", 0.1],
  ["100.000.000,99", 100000000.99],
  ["365575.21", 365575.21],
];

for (const [raw, expected] of cases) {
  const got = parseCurrencyInput(raw);
  assert.equal(got, expected, `parseCurrencyInput(${JSON.stringify(raw)})`);
}

const stored = 365575.21;
const field = formatCurrencyInputFromApi(stored);
assert.equal(field, "365.575,21");
assert.equal(normalizeCurrencyForApi(field), stored, "re-save after edit description only");

assert.notEqual(parseCurrencyInput("365575.21"), 36557521, "must not strip decimal dot");

console.log("currency.mjs: all tests passed");
