/**
 * Nome curto de pessoa para eixos de gráfico: "Rafael Casagrande" → "Rafael C.".
 *
 * Rótulo de eixo tem pouquíssimo espaço horizontal; nome completo quebra em duas linhas e
 * as linhas de colaboradores vizinhos se sobrepõem. O nome COMPLETO continua no tooltip —
 * o encurtamento é só de exibição, nunca de dado.
 */

/** Partículas que não valem como sobrenome ("Amanda do Amaral" → "Amanda A.", não "Amanda D."). */
const PARTICULAS = new Set([
  "de", "da", "do", "das", "dos", "e", "di", "du", "del", "della",
  "la", "le", "van", "von", "y", "dal", "d'",
]);

function tokens(fullName: string): string[] {
  return String(fullName ?? "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
}

/** Primeiro sobrenome que não é partícula. */
function primeiroSobrenome(parts: string[]): string | null {
  for (const p of parts.slice(1)) {
    if (!PARTICULAS.has(p.toLowerCase())) return p;
  }
  return null;
}

/**
 * "Rafael Casagrande Silva" → "Rafael C."
 * Nome único ("Madonna") volta inteiro; vazio volta vazio.
 */
export function shortPersonName(fullName: string): string {
  const parts = tokens(fullName);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0];
  const sobrenome = primeiroSobrenome(parts);
  return sobrenome ? `${parts[0]} ${sobrenome[0].toUpperCase()}.` : parts[0];
}

/**
 * Versão para uma LISTA: encurta e desfaz empates.
 *
 * Dois "Luiz C." no mesmo gráfico seriam pior que o nome comprido — o leitor não saberia
 * qual barra é de quem. Quando o rótulo curto colide, o sobrenome vai por extenso; se ainda
 * colidir, cai no nome completo. Devolve na mesma ordem da entrada.
 */
export function shortPersonNames(fullNames: string[]): string[] {
  const curtos = fullNames.map(shortPersonName);

  const contagem = new Map<string, number>();
  for (const c of curtos) contagem.set(c, (contagem.get(c) ?? 0) + 1);

  const resolvidos = curtos.map((curto, i) => {
    if ((contagem.get(curto) ?? 0) <= 1) return curto;
    const parts = tokens(fullNames[i]);
    const sobrenome = primeiroSobrenome(parts);
    return sobrenome ? `${parts[0]} ${sobrenome}` : fullNames[i];
  });

  // Segunda passada: se o desempate ainda empatar, usa o nome completo.
  const contagem2 = new Map<string, number>();
  for (const r of resolvidos) contagem2.set(r, (contagem2.get(r) ?? 0) + 1);
  return resolvidos.map((r, i) => ((contagem2.get(r) ?? 0) > 1 ? fullNames[i] : r));
}
