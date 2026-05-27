import type { ReactNode } from "react";

type PrimaryAddButtonProps = {
  open: boolean;
  onToggle: () => void;
  disabled?: boolean;
  addLabel?: string;
  closeLabel?: string;
};

/** Botão primário indigo — mesmo padrão de «Adicionar despesa» (Contas a pagar). */
export function PrimaryAddButton({
  open,
  onToggle,
  disabled,
  addLabel = "Adicionar item",
  closeLabel = "Fechar",
}: PrimaryAddButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onToggle}
      className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {open ? closeLabel : addLabel}
    </button>
  );
}

type CollapsiblePanelProps = {
  open: boolean;
  children: ReactNode;
  className?: string;
};

/** Painel com expansão/recolhimento suave (grid 0fr → 1fr). */
export function CollapsiblePanel({ open, children, className = "" }: CollapsiblePanelProps) {
  return (
    <div
      className={`grid transition-[grid-template-rows] duration-200 ease-in-out ${
        open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
      }`}
      aria-hidden={!open}
    >
      <div className="min-h-0 overflow-hidden">
        <div className={className}>{children}</div>
      </div>
    </div>
  );
}
