/**
 * Testes do nome curto usado nos eixos de gráfico (rodar: node frontend/scripts/test-person-name.mjs).
 *
 * Espelha a lógica de src/utils/personName.ts. O ponto sensível é a COLISÃO: dois "Luiz C."
 * no mesmo gráfico seriam pior que o nome comprido, porque o leitor não saberia qual barra
 * é de quem.
 */

import assert from "node:assert/strict";

const PARTICULAS = new Set([
  "de", "da", "do", "das", "dos", "e", "di", "du", "del", "della",
  "la", "le", "van", "von", "y", "dal", "d'",
]);

function tokens(fullName) {
  return String(fullName ?? "").trim().split(/\s+/).filter(Boolean);
}

function primeiroSobrenome(parts) {
  for (const p of parts.slice(1)) {
    if (!PARTICULAS.has(p.toLowerCase())) return p;
  }
  return null;
}

function shortPersonName(fullName) {
  const parts = tokens(fullName);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0];
  const sobrenome = primeiroSobrenome(parts);
  return sobrenome ? `${parts[0]} ${sobrenome[0].toUpperCase()}.` : parts[0];
}

function shortPersonNames(fullNames) {
  const curtos = fullNames.map(shortPersonName);
  const contagem = new Map();
  for (const c of curtos) contagem.set(c, (contagem.get(c) ?? 0) + 1);
  const resolvidos = curtos.map((curto, i) => {
    if ((contagem.get(curto) ?? 0) <= 1) return curto;
    const parts = tokens(fullNames[i]);
    const sobrenome = primeiroSobrenome(parts);
    return sobrenome ? `${parts[0]} ${sobrenome}` : fullNames[i];
  });
  const contagem2 = new Map();
  for (const r of resolvidos) contagem2.set(r, (contagem2.get(r) ?? 0) + 1);
  return resolvidos.map((r, i) => ((contagem2.get(r) ?? 0) > 1 ? fullNames[i] : r));
}

// --- forma básica ---
for (const [entrada, esperado] of [
  ["Rafael Casagrande", "Rafael C."],
  ["Rafael Casagrande Silva", "Rafael C."],
  ["Dener Pioli", "Dener P."],
  ["Henrique Souza Nobre", "Henrique S."],
]) {
  assert.equal(shortPersonName(entrada), esperado, `shortPersonName(${entrada})`);
}

// --- partículas não valem como sobrenome ---
for (const [entrada, esperado] of [
  ["Amanda do Amaral Peraro", "Amanda A."],
  ["Jolly da Silva Lemos", "Jolly S."],
  ["Luciano De França Silva", "Luciano F."],
  ["Maria de Souza", "Maria S."],
  ["Ícaro Cunha Farias da Silva", "Ícaro C."],
]) {
  assert.equal(shortPersonName(entrada), esperado, `partícula: ${entrada}`);
}

// --- degenerados não podem quebrar o gráfico ---
assert.equal(shortPersonName("Madonna"), "Madonna", "nome único volta inteiro");
assert.equal(shortPersonName("Ana de"), "Ana", "só partícula depois do nome");
assert.equal(shortPersonName(""), "");
assert.equal(shortPersonName("   "), "");
assert.equal(shortPersonName(null), "");
assert.equal(shortPersonName(undefined), "");

// --- colisão: rótulos precisam ficar distintos ---
const colidem = ["Luiz Carlos Pereira", "Luiz Carlos Domingos", "Ana Souza"];
const saida = shortPersonNames(colidem);
assert.equal(new Set(saida).size, saida.length, "rótulos precisam ser distintos");
assert.equal(saida[2], "Ana S.", "quem não colide mantém o rótulo curto");
assert.ok(saida[0] !== "Luiz C." && saida[1] !== "Luiz C.", "os que colidem são desambiguados");

// --- colisão parcial: só quem empata cresce ---
const mistos = ["Luiz Carlos Pereira", "Luiz Eduardo Domingos", "Bruno Lima"];
const s2 = shortPersonNames(mistos);
assert.deepEqual(s2, ["Luiz C.", "Luiz E.", "Bruno L."], "iniciais diferentes não colidem");

// --- ordem preservada (o gráfico casa rótulo com barra por índice) ---
const ordem = ["Zeca Alves", "Ana Souza", "Bruno Lima"];
assert.deepEqual(shortPersonNames(ordem), ["Zeca A.", "Ana S.", "Bruno L."], "ordem de entrada");

// --- nomes completos idênticos: não há o que desambiguar, mas não pode quebrar ---
assert.deepEqual(shortPersonNames(["Ana Souza", "Ana Souza"]), ["Ana Souza", "Ana Souza"]);

console.log("person-name.mjs: all tests passed");
