import { useRef } from "react";
import type { MouseEvent } from "react";

/**
 * Handlers do fundo escuro de janelas/gavetas: só fecha quando o clique COMEÇA e
 * TERMINA no próprio fundo.
 *
 * Fechar só no `onClick` fazia a janela sumir quando o usuário selecionava texto num
 * campo arrastando até fora da caixa — o navegador dispara o click no ancestral comum
 * (o fundo) ao soltar o botão ali. Fechar só no `onMouseDown` fechava ao começar no
 * fundo e soltar dentro da caixa.
 *
 * Uso (antes de qualquer `return` condicional — regra dos hooks):
 *   const fundo = useBackdropClose(onClose);
 *   <div className="fixed inset-0 ..." {...fundo}>
 *     <div className="...caixa...">  // e.stopPropagation() não é mais necessário
 */
export function useBackdropClose(onClose: () => void) {
  const cliqueNoFundo = useRef(false);
  return {
    onMouseDown: (e: MouseEvent<HTMLElement>) => {
      cliqueNoFundo.current = e.target === e.currentTarget;
    },
    onClick: (e: MouseEvent<HTMLElement>) => {
      if (cliqueNoFundo.current && e.target === e.currentTarget) onClose();
      cliqueNoFundo.current = false;
    },
  };
}
