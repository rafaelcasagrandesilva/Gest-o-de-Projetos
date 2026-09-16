import type { WorkspaceName } from "@/context/WorkspaceContext";
import {
  COLUMN_ORDER,
  GRID_RESOURCES,
  RESOURCE_LABELS,
  resourceCells,
  type PermissionColumn,
  type PermissionGridCell,
} from "@/permissions";
import { WORKSPACE_MENUS } from "@/workspaces/navigation";

/**
 * Tela de permissões em BLOCOS POR WORKSPACE — o tamanho da tela acompanha o sistema.
 *
 * Cada bloco é um workspace: o "Acessar" fica no cabeçalho e as linhas são os MENUS do workspace, lidos
 * de `WORKSPACE_MENUS` (a mesma lista das Sidebars). Menu novo na navegação = linha nova aqui, sem
 * mexer nesta tela. As colunas de cada linha são as ações que o recurso do menu já tem no catálogo.
 *
 * Menus que usam a MESMA permissão (Antecipações e Instituições → Notas fiscais; Dashboard, Patrimônio
 * e EPIs → Ativos; Relatórios em Projetos e no Financeiro) aparecem como linhas LIGADAS: a caixa é o
 * mesmo código, então marcar numa marca nas outras.
 *
 * O bloco Sistema reúne o que não é de um workspace (Usuários, Configurações, administração, escopo
 * global…). Qualquer recurso do catálogo que não caia em bloco nenhum vai para "Outros recursos" —
 * salvaguarda para nenhuma permissão sumir da tela.
 */

export type PermissionBlockRow = {
  key: string;
  label: string;
  resource: string;
  cells: PermissionGridCell[];
  /** Outras linhas que usam a mesma permissão (rótulo com o bloco quando é de outro workspace). */
  linkedWith: string[];
  hint?: string;
};

export type PermissionBlock = {
  key: string;
  label: string;
  /** Código do "Acessar" do workspace; `null` nos blocos que não são workspace. */
  accessCode: string | null;
  rows: PermissionBlockRow[];
  /** Colunas com ao menos uma célula no bloco (na ordem canônica). */
  columns: PermissionColumn[];
};

const WORKSPACE_BLOCKS: { key: WorkspaceName; label: string }[] = [
  { key: "projects", label: "Projetos" },
  { key: "finance", label: "Financeiro" },
  { key: "assets", label: "Gestão de Ativos" },
  { key: "indicators", label: "Indicadores" },
  { key: "legal", label: "Jurídico" },
];

/** Recursos que aparecem SÓ no bloco Sistema, mesmo quando um workspace tem o menu (Usuários, Configurações). */
const SYSTEM_ROWS: { resource: string; label: string; hint?: string }[] = [
  { resource: "users", label: "Usuários" },
  {
    resource: "settings",
    label: "Configurações",
    hint: "Inclui regime tributário e modo da antecipação",
  },
  {
    resource: "audit",
    label: "Auditoria",
    hint: "Exportar o log de auditoria (só por marcação individual)",
  },
  { resource: "alerts", label: "Alertas" },
  { resource: "project_documents", label: "Documentos do projeto" },
  {
    resource: "system_all_projects",
    label: "Escopo global de projetos",
    hint: "Vê todos os projetos, não só os vinculados",
  },
  { resource: "system_admin", label: "Administração do sistema" },
  {
    resource: "cost_center",
    label: "Centro de Custo",
    hint: "Escolher centro de custo nos seletores",
  },
];
const SYSTEM_RESOURCES = new Set(SYSTEM_ROWS.map((r) => r.resource));

/** Recursos sem menu próprio que pertencem a um workspace. */
const EXTRA_ROWS: Partial<
  Record<WorkspaceName, { resource: string; label: string; hint: string }[]>
> = {
  projects: [
    {
      resource: "costs",
      label: "Custos do projeto (rateio)",
      hint: "Sem menu próprio: custos dentro da tela do projeto",
    },
  ],
};

const resourceOf = (code: string) => code.slice(0, code.indexOf("."));
const shortLabel = (resource: string) =>
  (RESOURCE_LABELS[resource] ?? resource).split(" · ").pop() as string;
const hasCells = (resource: string) => GRID_RESOURCES.includes(resource);

function columnsOf(rows: PermissionBlockRow[]): PermissionColumn[] {
  const used = new Set(rows.flatMap((r) => r.cells.map((c) => c.column)));
  return COLUMN_ORDER.filter((c) => used.has(c));
}

function buildBlocks(): PermissionBlock[] {
  type Draft = Omit<PermissionBlock, "columns" | "rows"> & {
    rows: Omit<PermissionBlockRow, "linkedWith">[];
  };
  const drafts: Draft[] = [];

  for (const ws of WORKSPACE_BLOCKS) {
    const rows: Draft["rows"] = [];
    for (const item of WORKSPACE_MENUS[ws.key] ?? []) {
      const codes = Array.isArray(item.perm) ? item.perm : [item.perm];
      const resources = [...new Set(codes.map(resourceOf))].filter(
        (r) => hasCells(r) && !SYSTEM_RESOURCES.has(r),
      );
      if (resources.length === 1) {
        rows.push({
          key: `${ws.key}:${item.to}`,
          label: item.label,
          resource: resources[0],
          cells: resourceCells(resources[0]),
        });
        continue;
      }
      // Menu que junta vários recursos (ex.: Administração do Jurídico): uma linha por recurso que ainda
      // não tem linha no bloco.
      for (const r of resources) {
        if (rows.some((row) => row.resource === r)) continue;
        rows.push({
          key: `${ws.key}:${item.to}:${r}`,
          label: `${item.label} · ${shortLabel(r)}`,
          resource: r,
          cells: resourceCells(r),
        });
      }
    }
    for (const extra of EXTRA_ROWS[ws.key] ?? []) {
      if (!hasCells(extra.resource)) continue;
      rows.push({
        key: `${ws.key}:${extra.resource}`,
        label: extra.label,
        resource: extra.resource,
        cells: resourceCells(extra.resource),
        hint: extra.hint,
      });
    }
    drafts.push({
      key: ws.key,
      label: ws.label,
      accessCode: `workspace.${ws.key}.access`,
      rows,
    });
  }

  drafts.push({
    key: "system",
    label: "Sistema",
    accessCode: null,
    rows: SYSTEM_ROWS.filter((r) => hasCells(r.resource)).map((r) => ({
      key: `system:${r.resource}`,
      label: r.label,
      resource: r.resource,
      cells: resourceCells(r.resource),
      hint: r.hint,
    })),
  });

  const placed = new Set(drafts.flatMap((d) => d.rows.map((r) => r.resource)));
  const leftovers = GRID_RESOURCES.filter(
    (r) => !placed.has(r) && !r.startsWith("workspace_"),
  );
  if (leftovers.length) {
    drafts.push({
      key: "other",
      label: "Outros recursos",
      accessCode: null,
      rows: leftovers.map((r) => ({
        key: `other:${r}`,
        label: RESOURCE_LABELS[r] ?? r,
        resource: r,
        cells: resourceCells(r),
      })),
    });
  }

  // Linhas ligadas: mesma permissão em mais de um menu.
  const byResource = new Map<
    string,
    { block: string; label: string; key: string }[]
  >();
  for (const d of drafts) {
    for (const r of d.rows) {
      byResource.set(r.resource, [
        ...(byResource.get(r.resource) ?? []),
        { block: d.key, label: r.label, key: r.key },
      ]);
    }
  }
  const blockLabel = new Map(drafts.map((d) => [d.key, d.label]));

  return drafts.map((d) => {
    const rows = d.rows.map((r) => ({
      ...r,
      linkedWith: (byResource.get(r.resource) ?? [])
        .filter((o) => o.key !== r.key)
        .map((o) =>
          o.block === d.key
            ? o.label
            : `${blockLabel.get(o.block)} › ${o.label}`,
        ),
    }));
    return { ...d, rows, columns: columnsOf(rows) };
  });
}

export const PERMISSION_BLOCKS: PermissionBlock[] = buildBlocks();
