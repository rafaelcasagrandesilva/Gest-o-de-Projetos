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
  /** Lista também projetos encerrados (com "(encerrado)"): vínculo do Jurídico com contrato antigo. */
  includeClosed?: boolean;
  /** Primeira opção vazia selecionável — para quando "sem centro de custo" é uma resposta válida. */
  emptyLabel?: string;
};

export function CostCenterSelect({
  value,
  onChange,
  projects,
  disabled,
  className,
  legacyLabel,
  includeClosed,
  emptyLabel,
}: Props) {
  const merged = mergeProjectsForCostCenter(projects, value);
  const isOpen = (p: Project) => p.is_active && !p.closed_at;
  // Opções saem da lista recebida, não de `merged`: o marcador "legado" de `merged` só serve de rótulo.
  const projectOptions = projects
    .filter((p) => !p.deleted_at && (includeClosed || isOpen(p)))
    .filter((p) => !CC_FIXED_OPTIONS.some((o) => o.label === p.name.trim()))
    .sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));

  const inactiveSelected =
    value && !isSystemCostCenterRef(value) && !projectOptions.some((p) => p.id === value);

  return (
    <select
      required={emptyLabel === undefined}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className={className ?? "rounded-lg border border-slate-300 bg-white px-3 py-2"}
    >
      {emptyLabel !== undefined ? (
        <option value="">{emptyLabel}</option>
      ) : !value ? (
        <option value="">Selecione…</option>
      ) : null}
      {CC_FIXED_OPTIONS.map((o) => (
        <option key={o.ref} value={o.ref}>
          {o.label}
        </option>
      ))}
      {projectOptions.map((p) => (
        <option key={p.id} value={p.id}>
          {isOpen(p) ? p.name : `${p.name} (encerrado)`}
        </option>
      ))}
      {inactiveSelected ? (
        <option value={value}>{legacyLabel ?? costCenterLabelFromRef(value, merged)}</option>
      ) : null}
    </select>
  );
}
