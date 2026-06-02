import { useAuth } from "@/context/AuthContext";
import { hasPermission } from "@/permissions";
import { AppSidebarShell } from "@/components/AppSidebarShell";
import { SidebarNavItem } from "@/components/SidebarNavItem";

const items: {
  to: string;
  label: string;
  end: boolean;
  perm: string;
}[] = [
  { to: "/projects/dashboard", label: "Dashboard operacional", end: true, perm: "dashboard.view" },
  { to: "/projects/reports", label: "Relatórios", end: false, perm: "reports.view" },
  { to: "/projects/list", label: "Projetos", end: false, perm: "projects.view" },
  { to: "/projects/users", label: "Usuários", end: false, perm: "users.manage" },
  { to: "/projects/employees", label: "Colaboradores", end: false, perm: "employees.view" },
  { to: "/projects/vehicles", label: "Veículos", end: false, perm: "vehicles.view" },
  { to: "/projects/revenue", label: "Faturamento", end: false, perm: "billing.view" },
  { to: "/settings", label: "Configurações", end: false, perm: "settings.view" },
];

function visibleSidebarItems(perms: string[] | undefined) {
  return items.filter((i) => {
    if (i.to === "/settings") {
      return hasPermission(perms, "settings.view") || hasPermission(perms, "audit.export");
    }
    return hasPermission(perms, i.perm);
  });
}

export function ProjectsSidebar() {
  const { user } = useAuth();
  const perms = user?.permission_names;
  const visible = visibleSidebarItems(perms);

  return (
    <AppSidebarShell subtitle="Workspace: Projetos">
      {visible.map((item) => (
        <SidebarNavItem
          key={item.to}
          to={item.to}
          end={item.end}
          label={item.label}
        />
      ))}
    </AppSidebarShell>
  );
}
