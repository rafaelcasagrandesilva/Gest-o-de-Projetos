import type { ReactNode } from "react";
import { useSidebar } from "@/context/SidebarContext";
import { SidebarToggleButton } from "@/components/SidebarToggleButton";

type Props = {
  subtitle: string;
  children: ReactNode;
};

export function AppSidebarShell({ subtitle, children }: Props) {
  const { collapsed } = useSidebar();

  return (
    <aside
      className={`flex shrink-0 flex-col overflow-x-hidden border-r border-slate-200 bg-white transition-[width] duration-300 ease-in-out ${
        collapsed ? "w-[84px]" : "w-56"
      }`}
    >
      <div
        className={`flex shrink-0 border-b border-slate-100 transition-all duration-300 ${
          collapsed ? "flex-col items-center gap-2 px-2 py-4" : "items-start justify-between gap-2 px-4 py-5"
        }`}
      >
        {collapsed ? (
          <div
            className="text-base font-semibold tracking-tight text-indigo-600"
            title="SGC"
          >
            SGC
          </div>
        ) : (
          <div className="min-w-0 flex-1">
            <div className="text-lg font-semibold tracking-tight text-indigo-600">SGC</div>
            <p className="mt-0.5 truncate text-xs text-slate-500">{subtitle}</p>
          </div>
        )}
        <SidebarToggleButton className={collapsed ? "" : "shrink-0"} />
      </div>
      <nav
        className={`flex flex-1 flex-col gap-0.5 overflow-y-auto overflow-x-hidden ${
          collapsed ? "p-2" : "p-3"
        }`}
      >
        {children}
      </nav>
    </aside>
  );
}
