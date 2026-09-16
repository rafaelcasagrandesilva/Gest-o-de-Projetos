import { useState } from "react";
import { PERMISSION_BLOCKS, type PermissionBlock } from "@/permissionBlocks";
import {
  COLUMN_LABELS,
  PERMISSION_LABELS,
  workspaceRequiredFor,
} from "@/permissions";

type Props = {
  /** Códigos atualmente marcados. */
  selected: Set<string>;
  /** Alterna um código. */
  onToggle: (code: string) => void;
  disabled?: boolean;
};

/**
 * Grade de permissões em BLOCOS POR WORKSPACE (montagem em `permissionBlocks.ts`). Cada bloco traz o
 * "Acessar" do workspace no cabeçalho e uma linha por menu; as colunas são as ações que existem no bloco.
 * Linhas ligadas usam o mesmo código — marcar uma marca as outras. Sem o "Acessar", as linhas exclusivas
 * do workspace ficam esmaecidas: continuam editáveis, mas não valem enquanto o acesso estiver desmarcado.
 *
 * Layout: preenche a altura do container (`h-full`) e rola dentro de si; o cabeçalho do bloco e o das
 * colunas ficam fixos enquanto o bloco está na tela. Reutilizada por Usuários e Perfis.
 */
export function PermissionGrid({ selected, onToggle, disabled }: Props) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  function toggleCollapsed(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <div className="h-full space-y-3 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-3">
      {PERMISSION_BLOCKS.map((block) => (
        <Block
          key={block.key}
          block={block}
          selected={selected}
          onToggle={onToggle}
          disabled={disabled}
          collapsed={collapsed.has(block.key)}
          onToggleCollapsed={() => toggleCollapsed(block.key)}
        />
      ))}
    </div>
  );
}

function Block({
  block,
  selected,
  onToggle,
  disabled,
  collapsed,
  onToggleCollapsed,
}: Props & {
  block: PermissionBlock;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  const codes = [
    ...new Set(block.rows.flatMap((r) => r.cells.map((c) => c.code))),
  ];
  const marked = codes.filter((c) => selected.has(c)).length;
  const semAcesso =
    block.accessCode !== null && !selected.has(block.accessCode);

  return (
    <section className="w-max min-w-full rounded-lg border border-slate-200 bg-white">
      <header className="sticky top-0 z-30 h-11 rounded-t-lg border-b border-slate-200 bg-white">
        <div className="sticky left-0 flex h-full w-fit items-center gap-4 px-3">
          <button
            type="button"
            onClick={onToggleCollapsed}
            className="flex items-center gap-2 text-sm font-semibold text-slate-800"
            aria-expanded={!collapsed}
          >
            <span
              className={`inline-block text-slate-400 transition-transform ${collapsed ? "" : "rotate-90"}`}
            >
              ›
            </span>
            {block.label}
          </button>
          <span className="text-xs text-slate-400">
            {marked} de {codes.length} marcadas
          </span>
          {block.accessCode && (
            <label className="flex cursor-pointer items-center gap-2 rounded-md border border-slate-200 px-2 py-1 text-sm font-medium text-slate-700">
              <input
                type="checkbox"
                disabled={disabled}
                checked={selected.has(block.accessCode)}
                onChange={() => onToggle(block.accessCode as string)}
                title={PERMISSION_LABELS[block.accessCode] ?? block.accessCode}
              />
              Acessar
            </label>
          )}
          {semAcesso && (
            <span className="text-xs text-amber-700">
              Sem acesso: o workspace some e as telas dele ficam bloqueadas
            </span>
          )}
        </div>
      </header>

      {!collapsed && (
        <div>
          <table className="w-full border-separate border-spacing-0 text-sm">
            <thead>
              <tr>
                <th
                  scope="col"
                  className="sticky left-0 top-11 z-20 min-w-[16rem] border-b border-r border-slate-200 bg-slate-100 px-3 py-2 text-left text-xs font-medium text-slate-600"
                >
                  Menu
                </th>
                {block.columns.map((c) => (
                  <th
                    key={c}
                    scope="col"
                    className="sticky top-11 z-10 whitespace-nowrap border-b border-slate-200 bg-slate-100 px-3 py-2 text-center text-xs font-medium text-slate-600"
                  >
                    {COLUMN_LABELS[c]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row) => {
                const byColumn = new Map(
                  row.cells.map((c) => [c.column, c.code]),
                );
                const esmaecida =
                  semAcesso &&
                  row.cells.some(
                    (c) => workspaceRequiredFor(c.code) === block.accessCode,
                  );
                return (
                  <tr
                    key={row.key}
                    className={`group ${esmaecida ? "opacity-50" : ""}`}
                  >
                    <th
                      scope="row"
                      className="sticky left-0 z-[5] min-w-[16rem] border-b border-r border-slate-200 bg-white px-3 py-2 text-left align-top font-medium text-slate-800 group-hover:bg-slate-50"
                    >
                      <div>{row.label}</div>
                      {row.linkedWith.length > 0 && (
                        <div
                          className="mt-0.5 text-xs font-normal text-indigo-600"
                          title="Mesma permissão — marcar aqui marca nas outras linhas"
                        >
                          ⇄ mesma permissão de {row.linkedWith.join(", ")}
                        </div>
                      )}
                      {row.hint && (
                        <div className="mt-0.5 text-xs font-normal text-slate-400">
                          {row.hint}
                        </div>
                      )}
                    </th>
                    {block.columns.map((c) => {
                      const code = byColumn.get(c);
                      return (
                        <td
                          key={c}
                          className="border-b border-slate-100 px-3 py-2 text-center align-top group-hover:bg-slate-50/60"
                        >
                          {code ? (
                            <input
                              type="checkbox"
                              disabled={disabled}
                              checked={selected.has(code)}
                              onChange={() => onToggle(code)}
                              title={PERMISSION_LABELS[code] ?? code}
                              aria-label={`${row.label} · ${COLUMN_LABELS[c]}`}
                            />
                          ) : (
                            <span className="text-slate-300">—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
