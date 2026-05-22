import { Outlet } from "react-router-dom";
import { ScenarioProvider } from "@/context/ScenarioContext";
import { Header } from "./Header";
import { AssetsSidebar } from "./AssetsSidebar";
import { FinanceSidebar } from "./FinanceSidebar";
import { ProjectsSidebar } from "./ProjectsSidebar";
import { useWorkspace } from "@/context/WorkspaceContext";

export function Layout() {
  const { workspace } = useWorkspace();
  return (
    <ScenarioProvider>
      <div className="flex min-h-screen">
        {workspace === "projects" ? (
          <ProjectsSidebar />
        ) : workspace === "assets" ? (
          <AssetsSidebar />
        ) : (
          <FinanceSidebar />
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <main className="flex-1 overflow-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </ScenarioProvider>
  );
}
