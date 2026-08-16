# SGC — HANDOFF: Feature "Dados Sensíveis" (ocultação de valores financeiros)

> Documento de transferência de contexto entre chats. Escrito para permitir continuação
> exata sem depender do histórico anterior. Data de referência: 2026-07-23.

---

## 0. TL;DR — LEIA PRIMEIRO (STATUS CRÍTICO)

**O bug reportado no prompt de handoff (Dashboard de Projetos = tela branca sem "Dados
Sensíveis") JÁ FOI DIAGNOSTICADO E CORRIGIDO nesta sessão.** Não é preciso re-investigar.

- **Componente que quebrava:** `frontend/src/pages/Dashboard.tsx` (Dashboard operacional de Projetos).
- **Causa exata:** os formatadores monetários chamavam métodos de `Number` diretamente em `null`
  (`n.toLocaleString(...)`, `pctOfRevenue.toFixed(1)`) → **`TypeError` durante o render** → como
  não há error boundary na rota, o React desmonta a árvore inteira → **tela branca**.
- **Correção:** formatadores tornados null-safe (`→ "—"`), remoção de coerções `?? 0` nos displays,
  guarda no cálculo de Δ e estado "Valores ocultos" no gráfico exclusivamente financeiro.
- **Validado:** sem sensitive → sem tela branca, tudo `—`, 0 valores `R$`; com sensitive (admin)
  → valores reais; `tsc` + `vite build` limpos.

**Ação recomendada para o próximo chat:** apenas **VERIFICAR** (reproduzir com o perfil da
Michele) e, se surgir alguma tela branca residual em OUTRA rota, aplicar o mesmo padrão null-safe.
Não refatorar, não mexer no backend, não remover redação.

---

## 1. Arquitetura (NÃO ALTERAR)

Fonte única no backend, espelho passivo no frontend.

### Backend — `app/api/sensitive.py`
- `redact(model, sensitive_fields, include)` — `model_copy` zerando (`None`) os campos quando `include=False`.
- `@dataclass SensitiveSpec(code: str, fields: tuple[str,...], nested: tuple[tuple[str,str],...] = ())`
  - `code` = permissão que libera (`<recurso>.sensitive`).
  - `fields` = campos monetários a omitir.
  - `nested` = `(atributo, recurso_filho)` para redação **recursiva** (listas/objetos aninhados).
- `SENSITIVE_SPECS: dict[str, SensitiveSpec]` — **registro central (48 specs atualmente)**.
- `sensitive_include(resource, user)` → `user_has_permission(user, spec.code)` (usa o efetivo).
- `redact_for(resource, model, user)` → se tem permissão devolve o modelo; senão `_redact_model`
  (zera campos próprios + recursivamente os `nested`; decisão de permissão feita 1x no topo).

### Frontend
- Helper compartilhado `formatCurrencyOrDash(n: number | null | undefined)` em
  `frontend/src/utils/currency.ts` → `"—"` quando `null`, senão `formatCurrency(n)`. Também
  `SENSITIVE_PLACEHOLDER = "—"`.
- **Regra:** todo valor monetário que pode vir `null` deve ser renderizado via `formatCurrencyOrDash`
  (ou um formatador local null-safe equivalente). Sem tratamento específico por tela.

### Regras invioláveis
- Backend é a fonte da verdade: sem a permissão, **o valor não é enviado (null)**.
- Nenhuma regra de negócio/cálculo/consulta SQL alterada — só a exposição.
- Não ativar/renomear permission codes (usa os `*.sensitive` já existentes).
- Compatibilidade por grafo: `<r>.view ⇒ <r>.sensitive` (perfis legados continuam vendo valores).

---

## 2. DIAGNÓSTICO DETALHADO DO BUG (já corrigido)

### 2.1. Por que só o Dashboard de Projetos quebrava
O endpoint `/dashboard/summary` passou (Etapa 3) a redigir os campos como `null` para quem não
tem `dashboard.sensitive`. O `Dashboard.tsx` assumia `number` e formatava direto. Outras telas
(Endividamento, Contas a Receber, etc.) já usavam `formatCurrencyOrDash` (null-safe) e por isso
não quebravam — só mostravam `—`. O Dashboard tinha formatadores **próprios** não null-safe.

### 2.2. Linhas que lançavam a exceção (antes da correção)
Em `frontend/src/pages/Dashboard.tsx`:
```ts
function formatMoney(n: number): string { return n.toLocaleString("pt-BR", {...}); } // null.toLocaleString → TypeError
function formatMoneyVsRevenue(money, pctOfRevenue) { return `${formatMoney(money)} (${pctOfRevenue.toFixed(1)}%)`; } // null.toFixed → TypeError
```
Campos que passaram a chegar `null` (todos de `DirectorSummary`/`ProjectSummary`/`MonthlyPoint`):
`revenue_total, total_revenue, cost_total, total_cost, total_retention, operational_profit,
net_profit, margin_operational, margin_net, profit, margin, ebitda, ebitda_margin,
operational_cost, labor_cost, vehicle_cost, system_cost, fixed_operational_cost, tax_amount,
overhead_amount, anticipation_amount, *_pct`, e no wrapper `lucro_liquido_previsto/realizado`.

Confirmação no console (reproduzido): `The above error occurred in the <Dashboard> component`.

### 2.3. Efeitos secundários (mostravam `R$ 0,00` em vez de `—`)
- Displays com `?? 0` (ex.: `formatMoney(s.total_retention ?? 0)`, seção "Custos operacionais por
  projeto") coagiam `null → 0`.
- `ScenarioCompareCard`: `delta = realizado - previsto` com `null - null === 0` → `R$ 0,00`.
- Gráfico "Evolução financeira" (`FinancialEvolutionProjectChart`) coagia `Number(... ?? 0)`.

---

## 3. CORREÇÃO APLICADA (arquivos e o quê)

Somente frontend. Nenhuma alteração de backend/redação.

### `frontend/src/pages/Dashboard.tsx`
- `formatMoney`, `formatPct`, `formatPercentage`, `getProfitColor`, `formatMoneyVsRevenue`
  passaram a aceitar `number | null | undefined` e retornam `"—"` (const `SENSITIVE_DASH`) quando `null`.
- Removido `?? 0` dos displays monetários (Retenção, EBITDA, e as 8 linhas de "Custos operacionais
  por projeto" via `formatMoneyVsRevenue(s.campo, s.campo_pct)`).
- `ScenarioCompareCard`: `previsto/realizado: number | null`; `hasBoth = previsto != null &&
  realizado != null`; `delta = hasBoth ? realizado - previsto : null` → Δ vira `—` quando redigido.

### `frontend/src/components/FinancialEvolutionProjectChart.tsx`
- `formatBRL(n: number | null | undefined)` null-safe (`→ "—"`).
- Detecção de redação (`monthlySeries.every(p => (p as {total_revenue:number|null}).total_revenue == null)`)
  → renderiza estado **"Valores ocultos — sem permissão de Dados Sensíveis."** (gráfico exclusivamente
  financeiro; mantém o card na tela). Early-return **após** todos os hooks.

### `frontend/src/components/FinancialDashboardCharts.tsx`
- `formatCurrency(n: number | null | undefined)` null-safe (defensivo).

### Também (mesmo problema, resolvido em Endividamento/Custos Fixos)
- `frontend/src/services/companyFinance.ts`: `PagamentoMes.valor`, `valor_referencia`, `total_pago`,
  `pago_mes`, KPIs → `number | null`.
- `frontend/src/components/company-finance/CompanyFinanceAnalyticTable.tsx`: helpers (`baseOf`,
  `pctQuitadoOf`, `saldoOf`, `valorMensalOf`, `valorAnualOf`, `capPaidOf`, `saldoMensalOf`) agora
  propagam `null`; células usam `formatCurrencyOrDash`/`formatPctOrDash`; `isRedacted(item)=valor_referencia==null`.
- `frontend/src/components/company-finance/CompanyFinanceExecutive.tsx`: cards/KPIs via `formatCurrencyOrDash`;
  guardas de `null` no editor de grade.
- Backend: `PagamentoMes.valor` → Optional e spec `company_finance_payment` (nested em `debt_item`/
  `custo_fixo_item`) — **fechou um leak da grade mensal** encontrado na varredura.

---

## 4. VALIDAÇÃO REALIZADA (nesta sessão)

Usuário de teste verbo-puro (`dashboard.read`+`dashboard.director`+`projects.*`+`workspace.*`+
`system.all_projects`, **sem** `*.sensitive`) e admin. Ambos descartados/removidos ao final.

| Rota / estado | Sem Dados Sensíveis | Com Dados Sensíveis (admin) |
|---|---|---|
| `/projects/dashboard` | Sem tela branca; **0 valores `R$`**; **29 `—`**; gráfico "Valores ocultos"; navegação ok | Valores reais (ex.: R$ 672.469,56); gráfico normal; sem crash |
| `/finance/debt` (Endividamento) | 0 `R$`; KPIs/Extrato = `—` | Valores reais |
| `/dashboard/summary` (API) | Todos os campos `null` (sem vazamento) | Valores presentes |

`npx tsc --noEmit` limpo; `npx vite build` ok. Backend: **219 passed, 1 failed** (ambiental
pré-existente — ver §7).

---

## 5. ESTADO COMPLETO DA FEATURE (Etapas 1–3)

### Módulos com redação ATIVA via `redact_for` + `SENSITIVE_SPECS`
Referência (produção anterior): **employees, vehicles, assets**.
Etapa 1: **payables** (Contas a Pagar).
Etapa 2: **receivables** (+ manual + kpis), **invoices/NF** (+ nested `invoice_anticipations`,
`advance_batch_summary`, `advance_operations`), **billing_revenue/billing_invoice** (Faturamento).
Etapa 3: **projects** (`project`, `project_labor`, `project_labor_detail`+`labor_breakdown`,
`project_vehicle`, `project_value`, `employee_allocation`), **Endividamento/Custos Fixos**
(`debt_item`/`custo_fixo_item`+`company_finance_payment`, `kpi_endividamento`, `kpi_custos_fixos`,
`debt_chart`/`custo_fixo_chart`+`chart_point`, `debt_pendencias`/`custo_fixo_pendencias`+`pendencia_item`),
**dashboard** (`dashboard_point`, `dashboard_summary`, `dashboard_financial_summary`,
`dashboard_project_response`), **indicadores** (`indicator_roi`, `roi_ranking`, `roi_evolution`+
`roi_evolution_point`, `financial_evolution`+`fin_evolution_point`, `financial_kpi(s)`,
`financial_insights`, `indicator_highlight`), **custos** (`cost_item`, `cost_allocation`).

- **~48 SensitiveSpecs** registradas; **~154 campos** monetários convertidos para Optional.
- **Endividamento vs Custos Fixos** compartilham endpoints de `company_finance`; o router escolhe
  o recurso por `tipo` via `_sensitive_resource_for_tipo(tipo)` → `debt_item` (`debts.sensitive`)
  ou `custo_fixo_item` (`company_finance.sensitive`).

### Routers integrados (chamam `redact_for` no retorno)
`payables`, `financial` (receivables/revenues/invoices/anticipations/manual), `receivables`
(invoices_router: NF + kpis + create/patch/reactivate/pdf), `company_finance` (items/kpis/chart/
pendencias/payments), `project_structure` (labors/labor-details/vehicles/systems/fixed-operational),
`projects` (list/detail/allocations/additives/create/update/(de)activate), `dashboard`
(summary/kpis/director/project), `indicators` (roi-*/evolucao-financeira), `costs` (project-fixed/
corporate/allocations/auto-allocate).

### Correções de autorização/nomenclatura (Etapa 3)
- **Item 5 — Faturamento (authz):** backend já gated (`billing.create/update/delete`). Bug era
  frontend: `Revenue.tsx` gate por `billing.read` → corrigido para `billing.create` (criar) e
  `billing.delete` (excluir).
- **Item 6 — "Custos" órfão:** `costs.*` protege só `/costs/*` (custos de projeto/rateio), não
  usado pelo frontend atual, sem menu. Não é misconfiguração. Rótulo (grid) → **"Custos de projeto
  (rateio)"** em `frontend/src/permissions.ts`.
- **Item 7 — "Finanças da empresa":** controla a tela "Custos Fixos - Matriz" (só divergência de
  nome). Rótulo (grid) → **"Finanças da empresa (Custos Fixos - Matriz)"**.

---

## 6. GUARDAS / TESTES (`tests/test_sensitive_registry.py`)
- `test_registry_codes_end_with_sensitive` — todo `code` termina em `.sensitive`; tem `fields` OU
  `nested`; `nested` aponta para recurso registrado.
- `test_all_registered_fields_exist_and_are_optional` — campos dos recursos da Etapa 2 existem/nulláveis.
- `test_every_financial_resource_fields_optional` — **varredura**: para cada recurso registrado, os
  campos presentes no schema aceitam `None` (helper `_accepts_none`). Módulos de referência
  (employees/vehicles/assets) ficam de fora (têm campo legado não-Optional que só funciona pela
  serialização do FastAPI).
- `test_nested_invoice_redaction_is_recursive` — NF sem sensitive → topo + aninhados omitidos; com → preservados.

Observação técnica importante: **FastAPI serializa um retorno já tipado sem revalidar**, por isso
um campo `float` (não-Optional) com valor `None` até "passa"; mesmo assim, o padrão adotado é
tornar os campos **Optional** explicitamente (correto e seguro).

---

## 7. PENDÊNCIAS / CONSIDERAÇÕES
- **Falha ambiental de teste (pré-existente, NÃO relacionada):**
  `tests/test_advance_batch_payables.py::BorderoPayablesAsyncTests::test_create_batch_payables_survive_invalidate_and_regenerate`
  — falha por estado acumulado no banco de teste (91 lançamentos automáticos pagos em 2026-06
  bloqueiam a regeração). Documentada; ignorar.
- **Cosmético (sem crash, sem leak):** telas de **Indicadores** (ECharts) e **detalhe de Projeto**
  estão protegidas no backend (valores `null`), mas alguns pontos do frontend ainda podem exibir
  `R$ 0,00`/`0%` em vez de `—`. Não é vazamento (o valor real é `null` no payload). Se quiser o
  polimento visual, aplicar `formatCurrencyOrDash` / o mesmo padrão null-safe nesses componentes.
- **Migrations:** nenhuma criada nesta feature (Optional é só schema Pydantic; permissões usam
  códigos já existentes).

---

## 8. COMO VERIFICAR (próximo chat) — reproduzir o cenário da Michele
1. Servidores: backend em `:8000` (uvicorn), frontend em `:3000` (`preview_start name:"frontend"`).
2. Gerar token para um usuário SEM `dashboard.sensitive` (ou usar a Michele — perfil
   `ADMINISTRATIVO`). Token mínimo: `{"sub": <user_id>, "session_version": SESSION_VERSION}` via
   `app.core.security.create_access_token` (o `get_current_user` recarrega o usuário do banco).
   Injetar em `localStorage.sgp_access_token`.
3. Navegar para `/projects/dashboard` → **deve renderizar com `—`, sem tela branca**.
4. Conferir payload: `GET /api/v1/dashboard/summary?competencia=YYYY-MM-01` → campos monetários `null`.
5. Repetir com admin (com sensitive) → valores reais.
6. **Sempre reverter** grants temporários e limpar `localStorage` ao final; excluir usuários de teste.

### Comandos úteis
- Backend: `.venv/bin/python -m pytest tests/ -q` (esperado: 1 falha ambiental §7; resto passa).
- Guard sensitive: `.venv/bin/python -m pytest tests/test_sensitive_registry.py -q`.
- Frontend: `cd frontend && npx tsc --noEmit && npx vite build`.
- Contagem de specs: `.venv/bin/python -c "from app.api.sensitive import SENSITIVE_SPECS; print(len(SENSITIVE_SPECS))"`.

---

## 9. PRINCÍPIOS A PRESERVAR
- Toda proteção passa por `redact_for()` + `SENSITIVE_SPECS`; nada de tratamento por tela no backend.
- Frontend só renderiza; valor oculto = `null` → `formatCurrencyOrDash` → `"—"` (ou estado
  "Valores ocultos" para gráfico exclusivamente financeiro).
- Não alterar backend/redação para resolver problemas de renderização — o fix é sempre tornar o
  componente null-safe.
- Correções mínimas; sem refatoração desnecessária.

*Fim do handoff.*
