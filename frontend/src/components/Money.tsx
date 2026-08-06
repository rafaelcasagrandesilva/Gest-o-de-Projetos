import { formatNumberBR } from "@/utils/currency";

/**
 * Valor monetário em COLUNA, alinhado estilo Excel/contábil:
 * "R$" fixo à esquerda e o número alinhado à direita (dígitos tabulares).
 * Assim, em uma tabela, todos os "R$" formam uma coluna e todos os números
 * alinham pela vírgula/decimal, independente do tamanho do número.
 *
 * `null`/`undefined` (valor redigido por "Dados sensíveis") → "—".
 * Use em CÉLULAS DE TABELA (o pai deve ter largura definida — numa <td> funciona direto).
 */
export function Money({
  value,
  className = "",
}: {
  value: number | null | undefined;
  className?: string;
}) {
  if (value == null) {
    return <span className={`block text-right text-slate-400 ${className}`}>—</span>;
  }
  return (
    <span className={`flex items-baseline justify-between gap-2 tabular-nums ${className}`}>
      <span className="text-slate-400">R$</span>
      <span>{formatNumberBR(value)}</span>
    </span>
  );
}
