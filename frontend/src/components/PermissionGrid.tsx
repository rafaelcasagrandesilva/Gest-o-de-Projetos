import { Fragment } from "react";
import {
  COLUMN_LABELS,
  COLUMN_ORDER,
  RESOURCE_LABELS,
  permissionGridGroups,
} from "@/permissions";

type Props = {
  /** Códigos atualmente marcados. */
  selected: Set<string>;
  /** Alterna um código. */
  onToggle: (code: string) => void;
  disabled?: boolean;
};

/**
 * Grade de permissões — MODELO ÚNICO. Cada linha é um recurso e cada coluna é uma AÇÃO. Toda
 * permissão administrável do sistema aparece aqui (não existe mais "Outras permissões"): permissões
 * transversais viram células nas colunas Exportar/Executar/Diretoria/Acessar/Administrar. Recursos e
 * células são DERIVADOS do catálogo (`ALL_PERMISSION_CODES` em permissions.ts). Quando uma ação não
 * se aplica ao recurso, mostra "—".
 *
 * Layout: preenche a altura do container (`h-full`) e rola nos DOIS eixos dentro de si mesma, com
 * cabeçalho de colunas fixo na vertical (sticky top) e a coluna "Recurso" fixa na horizontal
 * (sticky left) — o admin nunca perde o contexto de linha/coluna. Reutilizada por Usuários e Perfis.
 */
export function PermissionGrid({ selected, onToggle, disabled }: Props) {
  const groups = permissionGridGroups();
  const colCount = COLUMN_ORDER.length + 1;

  return (
    <div className="h-full overflow-auto rounded-lg border border-slate-200">
      <table className="w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th
              scope="col"
              className="sticky left-0 top-0 z-30 min-w-[15rem] whitespace-nowrap border-b border-r border-slate-200 bg-slate-100 px-3 py-2 text-left font-medium text-slate-600"
            >
              Recurso
            </th>
            {COLUMN_ORDER.map((c) => (
              <th
                key={c}
                scope="col"
                className="sticky top-0 z-20 whitespace-nowrap border-b border-slate-200 bg-slate-100 px-3 py-2 text-center text-xs font-medium text-slate-600"
              >
                {COLUMN_LABELS[c]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map(({ group, resources }) => (
            <Fragment key={group}>
              <tr>
                <td colSpan={colCount} className="border-b border-slate-200 bg-slate-100/80 p-0">
                  <div className="sticky left-0 inline-block px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {group}
                  </div>
                </td>
              </tr>
              {resources.map(({ resource, cells }) => {
                const byColumn = new Map(cells.map((c) => [c.column, c.code]));
                return (
                  <tr key={resource} className="group">
                    <th
                      scope="row"
                      className="sticky left-0 z-10 min-w-[15rem] whitespace-nowrap border-b border-r border-slate-200 bg-white px-3 py-2 text-left font-medium text-slate-800 group-hover:bg-slate-50"
                    >
                      {RESOURCE_LABELS[resource] ?? resource}
                    </th>
                    {COLUMN_ORDER.map((c) => {
                      const code = byColumn.get(c);
                      return (
                        <td
                          key={c}
                          className="border-b border-slate-100 px-3 py-2 text-center group-hover:bg-slate-50/60"
                        >
                          {code ? (
                            <input
                              type="checkbox"
                              disabled={disabled}
                              checked={selected.has(code)}
                              onChange={() => onToggle(code)}
                              title={code}
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
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
