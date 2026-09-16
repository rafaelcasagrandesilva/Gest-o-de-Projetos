import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { ScenarioProvider } from "@/context/ScenarioContext";
import { SidebarProvider } from "@/context/SidebarContext";
import { Header } from "./Header";
import { AssetsSidebar } from "./AssetsSidebar";
import { FinanceSidebar } from "./FinanceSidebar";
import { IndicatorsSidebar } from "./IndicatorsSidebar";
import { LegalSidebar } from "./LegalSidebar";
import { ProjectsSidebar } from "./ProjectsSidebar";
import { ErrorBoundary } from "./ErrorBoundary";
import { WorkspaceNoAccess } from "./WorkspaceNoAccess";
import { useWorkspace, type WorkspaceName } from "@/context/WorkspaceContext";
import { useAuth } from "@/context/AuthContext";
import { hasPermission } from "@/permissions";

/**
 * Prefixo da rota → workspace. Entrar por link direto (ou por um "Abrir caso" vindo de outra
 * tela) tem de trazer o menu e o cabeçalho certos: sem isso a pessoa vê a tela do Jurídico com
 * o chrome de Projetos.
 */
const WORKSPACE_BY_PREFIX: [string, WorkspaceName][] = [
  ["/legal", "legal"],
  ["/finance", "finance"],
  ["/assets", "assets"],
  ["/epis", "assets"],
  ["/indicators", "indicators"],
  ["/projects", "projects"],
];

export function Layout() {
  const { workspace, setWorkspace } = useWorkspace();
  const { user } = useAuth();
  const location = useLocation();
  const alvo = WORKSPACE_BY_PREFIX.find(([prefixo]) => location.pathname.startsWith(prefixo))?.[1];
  // Rota de um workspace sem "Acessar": mostra "Sem permissão" em vez da tela. E NÃO troca o
  // workspace — senão disputaria com a sincronização da sessão, que devolve ao workspace padrão.
  const semAcesso = !!alvo && !hasPermission(user?.permission_names, `workspace.${alvo}.access`);

  useEffect(() => {
    if (alvo && !semAcesso && alvo !== workspace) setWorkspace(alvo);
  }, [alvo, semAcesso, workspace, setWorkspace]);

  return (
    <ScenarioProvider>
      <SidebarProvider>
        <div className="flex min-h-screen overflow-x-hidden">
          {workspace === "projects" ? (
            <ProjectsSidebar />
          ) : workspace === "assets" ? (
            <AssetsSidebar />
          ) : workspace === "indicators" ? (
            <IndicatorsSidebar />
          ) : workspace === "legal" ? (
            <LegalSidebar />
          ) : (
            <FinanceSidebar />
          )}
          <div className="flex min-w-0 flex-1 flex-col">
            <Header />
            <main className="flex-1 overflow-auto p-4 sm:p-5">
              {/* Container oficial de largura das páginas (padrão "Contas a Pagar").
                  Única fonte de verdade do aproveitamento horizontal: as páginas
                  NÃO devem declarar max-width própria — herdam esta largura. */}
              <div className="mx-auto w-full min-w-0 max-w-full">
                {/* Salvaguarda por-rota: uma tela que lançar exceção mostra fallback
                    aqui dentro (nav/sidebar seguem funcionando). Reseta ao navegar. */}
                <ErrorBoundary resetKey={location.pathname} label="route">
                  {semAcesso ? <WorkspaceNoAccess /> : <Outlet />}
                </ErrorBoundary>
              </div>
            </main>
          </div>
        </div>
      </SidebarProvider>
    </ScenarioProvider>
  );
}
