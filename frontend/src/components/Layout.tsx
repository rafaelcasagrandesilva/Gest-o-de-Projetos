import { Outlet, useLocation } from "react-router-dom";
import { ScenarioProvider } from "@/context/ScenarioContext";
import { SidebarProvider } from "@/context/SidebarContext";
import { Header } from "./Header";
import { AssetsSidebar } from "./AssetsSidebar";
import { FinanceSidebar } from "./FinanceSidebar";
import { IndicatorsSidebar } from "./IndicatorsSidebar";
import { ProjectsSidebar } from "./ProjectsSidebar";
import { ErrorBoundary } from "./ErrorBoundary";
import { useWorkspace } from "@/context/WorkspaceContext";

export function Layout() {
  const { workspace } = useWorkspace();
  const location = useLocation();
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
                  <Outlet />
                </ErrorBoundary>
              </div>
            </main>
          </div>
        </div>
      </SidebarProvider>
    </ScenarioProvider>
  );
}
