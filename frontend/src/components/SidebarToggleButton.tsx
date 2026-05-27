import { useSidebar } from "@/context/SidebarContext";

export function SidebarToggleButton({ className = "" }: { className?: string }) {
  const { collapsed, toggle } = useSidebar();

  return (
    <button
      type="button"
      onClick={toggle}
      className={`inline-flex items-center justify-center rounded-lg border border-slate-200 p-2 text-slate-600 transition hover:bg-slate-50 hover:text-slate-900 ${className}`}
      aria-label={collapsed ? "Expandir menu lateral" : "Recolher menu lateral"}
      title={collapsed ? "Expandir menu" : "Recolher menu"}
    >
      <span className="select-none text-sm font-semibold leading-none">{collapsed ? "›" : "‹"}</span>
    </button>
  );
}
