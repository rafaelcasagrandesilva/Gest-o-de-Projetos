import { useState } from "react";

import { costCenterOptionLabel } from "@/services/costCenters";

const NEW_SENTINEL = "__new_cost_center__";

/**
 * Seleção de Centro de Custo (agrupamento reutilizável) no padrão de select do sistema,
 * com a opção de CRIAR um novo centro. Usa a lista de centros já existentes; ao escolher
 * "Novo centro de custo…" alterna para um input de texto (bootstrap de novos agrupamentos).
 * Emite/recebe sempre a string do centro (compatível com projects.cost_center /
 * employees.cost_center). Não altera backend/API.
 */
export function CostCenterCombo({
  value,
  onChange,
  options,
  disabled,
  required,
  className,
  id,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  disabled?: boolean;
  required?: boolean;
  className?: string;
  id?: string;
}) {
  const [creating, setCreating] = useState(false);
  // Modo "novo" apenas quando o usuário optou explicitamente por criar um centro.
  // Um valor já gravado que não está na lista atual (ex.: projeto encerrado) NÃO vira input de
  // texto: ele é reexibido como opção selecionada rotulada "(encerrado)" — preserva o vínculo
  // legado sem oferecê-lo para novos cadastros.
  const isNewMode = creating;
  const isLegacySelected = !!value && !options.includes(value);

  if (isNewMode) {
    return (
      <div className="flex gap-2">
        <input
          id={id}
          required={required}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder="Novo centro de custo (ex.: Fiscalização AT)"
          className={className}
          autoFocus
        />
        {options.length > 0 ? (
          <button
            type="button"
            onClick={() => {
              setCreating(false);
              onChange("");
            }}
            disabled={disabled}
            className="shrink-0 rounded-lg border border-slate-200 px-2 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            Lista
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <select
      id={id}
      required={required}
      value={value}
      onChange={(e) => {
        if (e.target.value === NEW_SENTINEL) {
          setCreating(true);
          onChange("");
        } else {
          onChange(e.target.value);
        }
      }}
      disabled={disabled}
      className={className}
    >
      <option value="">Selecione…</option>
      {/* Preserva um centro já gravado que não está mais na lista (legado/encerrado) —
          reexibido como selecionado e rotulado, sem ser oferecido para novos cadastros. */}
      {isLegacySelected ? (
        <option value={value}>{costCenterOptionLabel(value, options)}</option>
      ) : null}
      {options.map((cc) => (
        <option key={cc} value={cc}>
          {cc}
        </option>
      ))}
      <option value={NEW_SENTINEL}>➕ Novo centro de custo…</option>
    </select>
  );
}
