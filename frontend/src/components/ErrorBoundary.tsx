import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  /**
   * Quando muda, o boundary reseta o estado de erro. Passe a rota atual
   * (location.pathname) para que navegar para outra tela recupere sozinho.
   */
  resetKey?: string;
  /** Rótulo opcional para diferenciar boundaries no console/telemetria. */
  label?: string;
  /** Fallback customizado; se ausente, usa o painel padrão. */
  fallback?: ReactNode;
};

type State = { error: Error | null };

/**
 * Salvaguarda de renderização. Uma exceção lançada durante o render de qualquer
 * descendente é capturada aqui — a árvore React NÃO é desmontada até a raiz, então
 * a aplicação nunca fica em tela branca. Defesa em profundidade: os valores monetários
 * já são null-safe (ver utils/currency.ts); este boundary cobre qualquer erro futuro.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    // Recupera automaticamente ao navegar (resetKey muda).
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Log estruturado para o console (aparece em produção sem tela branca).
    console.error(`[ErrorBoundary${this.props.label ? `:${this.props.label}` : ""}]`, error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="flex min-h-[50vh] flex-col items-center justify-center p-8 text-center">
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-amber-100 text-amber-700">
              <span aria-hidden className="text-xl">!</span>
            </div>
            <h2 className="text-base font-semibold text-slate-900">Algo deu errado nesta tela</h2>
            <p className="mt-1 text-sm text-slate-600">
              Ocorreu um erro ao exibir esta página. As demais telas continuam funcionando.
            </p>
            <div className="mt-4 flex justify-center gap-2">
              <button
                type="button"
                onClick={() => this.setState({ error: null })}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                Tentar novamente
              </button>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Recarregar a página
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
