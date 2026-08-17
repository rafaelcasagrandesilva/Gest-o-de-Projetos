import { formatNumberBR } from "@/utils/currency";

/**
 * Valor monetário em COLUNA, alinhado estilo Excel/contábil:
 * "R$" fixo à esquerda e o número alinhado à direita (dígitos tabulares).
 * Assim, em uma tabela, todos os "R$" formam uma coluna e todos os números
 * alinham pela vírgula/decimal, independente do tamanho do número.
 *
 * `max-w` + `ml-auto`: numa tabela larga a célula pode ficar muito maior que o conteúdo, e sem
 * o teto o "R$" seria empurrado para a ponta esquerda, longe do número. Com o teto, o bloco tem
 * a MESMA largura em todas as linhas da coluna (o alinhamento continua exato) e encosta à
 * direita. O limite comporta valores na casa dos milhões sem apertar.
 *
 * `null`/`undefined` (valor redigido por "Dados sensíveis") → "—".
 * Use em CÉLULAS DE TABELA (o pai deve ter largura definida — numa <td> funciona direto).
 */
export function Money({
  value,
  sign,
  className = "",
}: {
  value: number | null | undefined;
  /**
   * Sinal exibido ANTES do "R$" (ledger de entradas/saídas). Fica no bloco da esquerda de
   * propósito: se fosse colado ao número, ele deslocaria os dígitos e quebraria a coluna.
   */
  sign?: "+" | "−";
  className?: string;
}) {
  if (value == null) {
    return <span className={`block text-right text-slate-400 ${className}`}>—</span>;
  }
  return (
    <span
      className={`ml-auto flex max-w-[11rem] items-baseline justify-between gap-2 tabular-nums ${className}`}
    >
      <span className="text-slate-400">{sign ? `${sign} R$` : "R$"}</span>
      <span>{formatNumberBR(value)}</span>
    </span>
  );
}
