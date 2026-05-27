import { NavLink } from "react-router-dom";
import { useSidebar } from "@/context/SidebarContext";

type Props = {
  to: string;
  label: string;
  end?: boolean;
};

function abbrev(label: string): string {
  const parts = label
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  const letters = parts.map((p) => p[0] ?? "").join("");
  const out = (letters || label.slice(0, 3)).toUpperCase();
  return out.slice(0, 3);
}

function linkClass(collapsed: boolean, isActive: boolean): string {
  const layout = collapsed
    ? "flex items-center justify-center rounded-lg px-2 py-2.5"
    : "flex items-center rounded-lg px-3 py-2.5";
  const tone = isActive
    ? "bg-indigo-600 text-white shadow-sm"
    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900";
  return `${layout} text-sm font-medium transition-colors duration-200 ${tone}`;
}

export function SidebarNavItem({ to, label, end }: Props) {
  const { collapsed } = useSidebar();

  return (
    <NavLink
      to={to}
      end={end}
      title={collapsed ? label : undefined}
      aria-label={collapsed ? label : undefined}
      className={({ isActive }) => linkClass(collapsed, isActive)}
    >
      {collapsed ? (
        <span className="select-none text-[11px] font-semibold tracking-wide">
          {abbrev(label)}
        </span>
      ) : (
        <span className="truncate">{label}</span>
      )}
    </NavLink>
  );
}
