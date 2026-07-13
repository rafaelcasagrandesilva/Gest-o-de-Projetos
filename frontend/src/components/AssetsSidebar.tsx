import { useAuth } from "@/context/AuthContext";
import { AppSidebarShell } from "@/components/AppSidebarShell";
import { SidebarNavItem } from "@/components/SidebarNavItem";
import { visibleWorkspaceMenu } from "@/workspaces/navigation";

export function AssetsSidebar() {
  const { user } = useAuth();
  const visible = visibleWorkspaceMenu("assets", user?.permission_names);

  return (
    <AppSidebarShell subtitle="Gestão de Ativos">
      {visible.map((item) => (
        <SidebarNavItem key={item.to} to={item.to} end={item.end ?? false} label={item.label} />
      ))}
    </AppSidebarShell>
  );
}
