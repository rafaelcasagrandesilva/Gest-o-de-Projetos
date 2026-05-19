import {
  CC_FIXED_OPTIONS,
  costCenterLabelFromRef,
  isSystemCostCenterRef,
  mergeProjectsForCostCenter,
} from "@/components/company-finance/costCenter";
import type { Project } from "@/services/projects";

type Props = {
  value: string;
  onChange: (ref: string) => void;
  projects: Project[];
  disabled?: boolean;
  className?: string;
  legacyLabel?: string | null;
};

export function CostCenterSelect({ value, onChange, projects, disabled, className, legacyLabel }: Props) {
  const merged = mergeProjectsForCostCenter(projects, value);
  const projectOptions = merged
    .filter((p) => p.is_active && !p.deleted_at && !p.closed_at)
    .filter((p) => !CC_FIXED_OPTIONS.some((o) => o.label === p.name.trim()))
    .sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));

  const inactiveSelected =
    value && !isSystemCostCenterRef(value) && !projectOptions.some((p) => p.id === value);

  return (
    <select
      required
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className={className ?? "rounded-lg border border-slate-300 bg-white px-3 py-2"}
    >
      {!value ? <option value="">Selecione…</option> : null}
      {CC_FIXED_OPTIONS.map((o) => (
        <option key={o.ref} value={o.ref}>
          {o.label}
        </option>
      ))}
      {projectOptions.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
      {inactiveSelected ? (
        <option value={value}>{legacyLabel ?? costCenterLabelFromRef(value, merged)}</option>
      ) : null}
    </select>
  );
}
