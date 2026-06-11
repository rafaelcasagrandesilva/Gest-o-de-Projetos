import { useAuth } from "@/context/AuthContext";
import { hasPermission } from "@/permissions";
import { AppSidebarShell } from "@/components/AppSidebarShell";
import { SidebarNavItem } from "@/components/SidebarNavItem";

export function IndicatorsSidebar() {
  const { user } = useAuth();
  const canView = hasPermission(user?.permission_names, "indicators.view");

  return (
    <AppSidebarShell subtitle="Workspace: Indicadores">
      {canView ? <SidebarNavItem to="/indicators/roi" label="ROI Operacional" /> : null}
    </AppSidebarShell>
  );
}
