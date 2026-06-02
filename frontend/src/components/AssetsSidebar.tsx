import { useAuth } from "@/context/AuthContext";
import { hasPermission } from "@/permissions";
import { AppSidebarShell } from "@/components/AppSidebarShell";
import { SidebarNavItem } from "@/components/SidebarNavItem";

export function AssetsSidebar() {
  const { user } = useAuth();
  const canView = hasPermission(user?.permission_names, "assets.view");
  const canSettings =
    hasPermission(user?.permission_names, "settings.view") ||
    hasPermission(user?.permission_names, "audit.export");

  return (
    <AppSidebarShell subtitle="Gestão de Ativos">
      {canView ? (
        <>
          <SidebarNavItem to="/assets/dashboard" label="Dashboard" />
          <SidebarNavItem to="/assets" end label="Patrimônio" />
          <SidebarNavItem to="/epis" end label="EPIs" />
        </>
      ) : null}
      {canSettings ? <SidebarNavItem to="/settings" end={false} label="Configurações" /> : null}
    </AppSidebarShell>
  );
}
