import { Outlet } from "react-router-dom";
import { ScenarioProvider } from "@/context/ScenarioContext";
import { SidebarProvider } from "@/context/SidebarContext";
import { Header } from "./Header";
import { AssetsSidebar } from "./AssetsSidebar";
import { FinanceSidebar } from "./FinanceSidebar";
import { IndicatorsSidebar } from "./IndicatorsSidebar";
import { ProjectsSidebar } from "./ProjectsSidebar";
import { useWorkspace } from "@/context/WorkspaceContext";

export function Layout() {
  const { workspace } = useWorkspace();
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
              <Outlet />
            </main>
          </div>
        </div>
      </SidebarProvider>
    </ScenarioProvider>
  );
}
