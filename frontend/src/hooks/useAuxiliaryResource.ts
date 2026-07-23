import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";
import { isAxiosError } from "axios";

/** Negativa de AUTORIZAÇÃO (403) — ou não autenticado (401) — de um recurso auxiliar. */
export function isAuthDenied(error: unknown): boolean {
  return isAxiosError(error) && (error.response?.status === 403 || error.response?.status === 401);
}

export type AuxiliaryResource<T> = {
  /** Dados carregados; `fallback` enquanto carrega ou quando indisponível. */
  data: T;
  /** true = carregou com sucesso (usuário tem acesso). false = 403/401 ou falha → OCULTE o controle. */
  available: boolean;
  /** true enquanto a primeira carga (ou um reload) está em andamento. */
  loading: boolean;
  /** Recarrega manualmente (ex.: após uma ação que altere o vocabulário auxiliar). */
  reload: () => void;
};

/**
 * PADRÃO ARQUITETURAL DO SGC — recursos auxiliares resilientes a permissão.
 *
 * Um módulo NUNCA deve deixar de funcionar por causa de um recurso auxiliar (filtro, select,
 * autocomplete, vocabulário, lista de apoio). Use este hook para carregar esses recursos de forma
 * INDEPENDENTE do recurso principal da tela:
 *
 *   - o recurso principal é carregado à parte (obrigatório) e NÃO passa por aqui;
 *   - se o loader auxiliar retornar 403/401 (ou qualquer erro), a página NÃO falha: `available`
 *     fica false e nenhum erro é propagado para a UI;
 *   - o componente deve OCULTAR ou DESABILITAR o controle correspondente quando `available` for false;
 *   - o usuário nunca vê mensagem de erro de um recurso auxiliar que não tem permissão para acessar.
 *
 * Reutilizável em Financeiro, Ativos, Indicadores, Relatórios etc. — qualquer tela com filtros/listas
 * de apoio protegidos por permissões diferentes do recurso principal.
 *
 * @param loader   função que busca o recurso (ex.: `() => listProjects()`).
 * @param fallback valor usado enquanto carrega e quando indisponível (ex.: `[]`).
 * @param deps     dependências que disparam recarga (mesma semântica de useEffect).
 * @param enabled  quando false, nem tenta buscar (ex.: pré-gate por permissão) — evita o 403 no console.
 */
export function useAuxiliaryResource<T>(
  loader: () => Promise<T>,
  fallback: T,
  deps: DependencyList = [],
  enabled: boolean = true,
): AuxiliaryResource<T> {
  const [data, setData] = useState<T>(fallback);
  const [available, setAvailable] = useState(false);
  const [loading, setLoading] = useState(enabled);
  // Mantém `loader`/`fallback` atuais sem forçá-los nas deps — a recarga é controlada por `deps`/`enabled`.
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const fallbackRef = useRef(fallback);
  fallbackRef.current = fallback;

  const run = useCallback(async (): Promise<void> => {
    if (!enabled) {
      setData(fallbackRef.current);
      setAvailable(false);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const result = await loaderRef.current();
      setData(result);
      setAvailable(true);
    } catch (error) {
      // Recurso AUXILIAR: nunca derruba a página nem exibe erro. 403/401 = sem permissão (controle oculto).
      setData(fallbackRef.current);
      setAvailable(false);
      if (!isAuthDenied(error)) {
        // Erros não relacionados a autorização (rede/500): log discreto para diagnóstico, sem UI de erro.
        console.warn("[auxiliary-resource] recurso auxiliar indisponível:", error);
      }
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  useEffect(() => {
    void run();
  }, [run]);

  return { data, available, loading, reload: run };
}
