#!/usr/bin/env node
/**
 * Guardrail estrutural — Dados Sensíveis / null-safety de moeda.
 *
 * Toda formatação de valores monetários DEVE passar por `src/utils/currency.ts`
 * (fonte única null-safe: valores redigidos → "—", nunca exceção nem "R$ 0,00").
 * Este verificador falha (exit 1) se qualquer OUTRO arquivo formatar moeda direto,
 * o que reintroduziria a classe de bug que gerava tela branca.
 *
 * Proíbe, fora de utils/currency.ts:
 *   - `Intl.NumberFormat`            (construção de formatador de número)
 *   - `style: "currency"`            (toLocaleString/NumberFormat de moeda)
 *   - o literal `"BRL"`              (moeda do sistema)
 *   - `.toLocaleString(... currency` (moeda inline em uma linha)
 *
 * Percentuais e datas (toFixed / toLocaleString sem moeda) permanecem permitidos:
 * não são a classe de crash de moeda e têm seus próprios helpers null-safe
 * (roiFormat.ts, DeltaPill, formatPct locais guardados por Number.isFinite).
 *
 * Rode: `npm run check:currency`. Encadeado em `npm run build`.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = join(__dirname, "..", "src");
const ALLOWED = new Set([join(SRC, "utils", "currency.ts")]);

const RULES = [
  { re: /\bIntl\.NumberFormat\b/, msg: "use os helpers de utils/currency.ts em vez de Intl.NumberFormat" },
  { re: /style:\s*["']currency["']/, msg: 'formatação de moeda (style: "currency") só é permitida em utils/currency.ts' },
  { re: /["']BRL["']/, msg: 'o literal "BRL" só é permitido em utils/currency.ts' },
  { re: /\.toLocaleString\([^)]*currency/, msg: "toLocaleString de moeda só é permitido em utils/currency.ts" },
];

/** Remove comentários de linha e o conteúdo de strings simples para evitar falsos positivos em docs. */
function stripNoise(line) {
  const noComment = line.replace(/\/\/.*$/, "");
  return noComment;
}

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      if (name === "node_modules" || name === "dist") continue;
      out.push(...walk(full));
    } else if (/\.(ts|tsx)$/.test(name)) {
      out.push(full);
    }
  }
  return out;
}

const violations = [];
for (const file of walk(SRC)) {
  if (ALLOWED.has(file)) continue;
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((raw, i) => {
    const line = stripNoise(raw);
    for (const { re, msg } of RULES) {
      // Não sinaliza a linha que é claramente um comentário JSDoc mencionando a regra.
      if (re.test(line) && !/^\s*\*/.test(raw)) {
        violations.push({ file: relative(join(SRC, ".."), file), line: i + 1, text: raw.trim(), msg });
        break;
      }
    }
  });
}

if (violations.length) {
  console.error("\n✖ check:currency — formatação de moeda fora de src/utils/currency.ts:\n");
  for (const v of violations) {
    console.error(`  ${v.file}:${v.line}`);
    console.error(`    ${v.text}`);
    console.error(`    → ${v.msg}\n`);
  }
  console.error(
    `Total: ${violations.length} ocorrência(s). Use formatCurrencyOrDash / formatCurrencyShortOrDash /\n` +
      `formatCurrencyField / sumCurrencyOrNull de "@/utils/currency" (null-safe: redigido → "—").\n`,
  );
  process.exit(1);
}

console.log("✓ check:currency — toda formatação de moeda passa por utils/currency.ts");
