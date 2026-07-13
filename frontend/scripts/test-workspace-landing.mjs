/**
 * Testes do resolvedor central de rota inicial de Workspace
 * (rodar: node frontend/scripts/test-workspace-landing.mjs).
 *
 * Importa o MÓDULO REAL `src/workspaces/navigation.ts` (via esbuild, resolvendo o alias @/),
 * de modo que os testes validam o registro único de menus + `resolveWorkspaceLanding` de verdade,
 * sem duplicar as listas de menus/permissões.
 */

import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { build } from "esbuild";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(__dirname, "..", "src");

const result = await build({
  entryPoints: [path.join(srcDir, "workspaces", "navigation.ts")],
  bundle: true,
  format: "esm",
  write: false,
  logLevel: "silent",
  alias: { "@": srcDir },
});
const code = result.outputFiles[0].text;
const mod = await import("data:text/javascript;base64," + Buffer.from(code).toString("base64"));
const { resolveWorkspaceLanding, visibleWorkspaceMenu } = mod;

let passed = 0;
function check(desc, actual, expected) {
  assert.deepEqual(actual, expected, `${desc} — esperado ${JSON.stringify(expected)}, obtido ${JSON.stringify(actual)}`);
  passed += 1;
}

// --- Financeiro: primeira tela permitida por permissão -----------------------------------
check("debts.view -> Endividamento", resolveWorkspaceLanding("finance", ["debts.view"]), "/finance/debt");
check("payables.view -> CAP", resolveWorkspaceLanding("finance", ["payables.view"]), "/finance/payables");
check("receivables.view -> Contas a Receber", resolveWorkspaceLanding("finance", ["receivables.view"]), "/finance/receivables");
check("company_finance.view -> Custos Fixos", resolveWorkspaceLanding("finance", ["company_finance.view"]), "/finance/fixed-costs");
check("invoices.view -> Notas fiscais", resolveWorkspaceLanding("finance", ["invoices.view"]), "/finance/invoices");
check("acesso total -> Dashboard Financeiro", resolveWorkspaceLanding("finance", ["billing.view", "payables.view", "debts.view"]), "/finance/dashboard");
check("sem permissão de finanças -> null", resolveWorkspaceLanding("finance", ["assets.view"]), null);
check("nenhuma permissão -> null", resolveWorkspaceLanding("finance", []), null);
check("system.admin -> Dashboard (primeira)", resolveWorkspaceLanding("finance", ["system.admin"]), "/finance/dashboard");

// Ordem preservada: com debts + custos, ganha o primeiro na ordem (Endividamento antes de Custos Fixos).
check("debts + custos -> Endividamento (ordem)", resolveWorkspaceLanding("finance", ["company_finance.view", "debts.view"]), "/finance/debt");

// --- Projetos ----------------------------------------------------------------------------
check("projetos: employees.view -> Colaboradores", resolveWorkspaceLanding("projects", ["employees.view"]), "/projects/employees");
check("projetos: projects.view -> Projetos", resolveWorkspaceLanding("projects", ["projects.view"]), "/projects/list");
check("projetos: vehicles.view -> Veículos", resolveWorkspaceLanding("projects", ["vehicles.view"]), "/projects/vehicles");
check("projetos: dashboard.view -> Dashboard", resolveWorkspaceLanding("projects", ["dashboard.view", "employees.view"]), "/projects/dashboard");
check("projetos: só settings -> Configurações", resolveWorkspaceLanding("projects", ["settings.view"]), "/settings");

// --- Gestão de Ativos --------------------------------------------------------------------
check("ativos: assets.view -> Dashboard", resolveWorkspaceLanding("assets", ["assets.view"]), "/assets/dashboard");
check("ativos: sem assets -> null", resolveWorkspaceLanding("assets", ["billing.view"]), null);

// --- Indicadores -------------------------------------------------------------------------
check("indicadores: indicators.view -> ROI", resolveWorkspaceLanding("indicators", ["indicators.view"]), "/indicators/roi");
check("indicadores: sem perm -> null", resolveWorkspaceLanding("indicators", []), null);

// --- Sidebar (mesma fonte): itens visíveis batem com a permissão -------------------------
check(
  "sidebar finance: debts.view mostra só Endividamento",
  visibleWorkspaceMenu("finance", ["debts.view"]).map((i) => i.to),
  ["/finance/debt"],
);
check(
  "sidebar finance: acesso total inclui Dashboard e Endividamento",
  visibleWorkspaceMenu("finance", ["billing.view", "debts.view"]).map((i) => i.to),
  ["/finance/dashboard", "/finance/debt"],
);

console.log(`OK — ${passed} asserções passaram (resolvedor de rota inicial de Workspace).`);
