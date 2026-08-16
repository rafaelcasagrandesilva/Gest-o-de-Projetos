# SGC — HANDOFF TÉCNICO

> Documentação oficial do projeto de migração do sistema de permissões do SGC (Sistema de Gestão de Projetos).
> Escrita para permitir que uma **nova conversa** continue exatamente deste ponto sem depender do histórico anterior.
> Data de referência do handoff: **2026-07-22**.

---

## 1. Objetivo do projeto

### Objetivo geral
Migrar **toda a autorização do sistema** de um modelo baseado em **perfil (role)** para um modelo baseado **exclusivamente em permissões**, seguindo o padrão:

```
Permissão → comportamento         (correto)
Perfil    → comportamento         (proibido)
```

Perfis (ADMIN, GESTOR, CONSULTA, ADMINISTRATIVO, FINANCEIRO, etc.) passam a ser **apenas um conjunto padrão de permissões** (um "preset" armazenado em `role_permissions`). Nenhuma funcionalidade pode depender do **nome** do perfil.

### Motivação
- Flexibilidade: poder conceder/negar capacidades por usuário sem criar perfis novos.
- Auditabilidade: cada capacidade é um código explícito.
- Escalabilidade: um modelo de verbos uniforme (recurso × ação) que serve para todos os módulos.
- Introdução do eixo **Dados Sensíveis**: separar "acessar o módulo" de "ver valores financeiros".

### Problemas que existiam (removidos)
- `ROLE_ADMIN` bypass (o perfil ADMIN liberava tudo por nome).
- `system.admin` liberando funcionalidades de **negócio** (hoje só libera administração do próprio sistema).
- **Bypass por e-mail de superusuário** (removido — `is_app_superuser` retorna sempre `False`).
- Hooks de frontend baseados em `GESTOR`/`CONSULTA` (ex.: `useConsultaReadOnly`, `useGestorGlobalReadOnly` — **deletados**).
- Verificações de role para liberar edição.

### Filosofia atual
- **Backend** decide autorização exclusivamente por permissões (perfil + deltas individuais), com **fecho transitivo** de um grafo de implicação.
- **Frontend** espelha o mesmo grafo e gate a UI pelas mesmas permissões.
- O usuário `rafael.casagrande@meconsulting.com.br` é o administrador; **nunca** remover/restringir seu acesso (na prática, o perfil ADMIN já contém todos os códigos).
- Migrations **aditivas** apenas; nunca destrutivas; nunca recriar perfis; nunca apagar dados.
- **SEMPRE** validar o efetivo pré/pós em qualquer migration de permissões.

---

## 2. Arquitetura atual das permissões

### 2.1. Fim da dependência de perfil
`app/api/deps.py` e `app/core/session_context.py` calculam o **efetivo** assim:

```
efetivo = ∪ permissões de todos os perfis do usuário (role_permissions, "vínculo vivo")
          ∪ adições individuais (user_permissions.granted = True)
          − remoções individuais (user_permissions.granted = False)
```

Funções-chave (existem espelhadas em `deps.py` e `session_context.py`):
- `_db_role_permission_names(user)` — união das permissões dos perfis via `role_permissions`. Retorna `None` **apenas** se a infra de `role_permissions` estiver ausente (fallback para preset hardcoded).
- `_user_permission_deltas(user)` — `(adds, removes)`; `granted is False` = remoção; caso contrário adição.
- `effective_permission_names(user)` — aplica a fórmula acima.
- `_preset_union(user)` — fallback legado (só se `role_permissions` indisponível).

### 2.2. Permissões por verbos
Modelo recurso × verbo. Verbos internos:

```
reference < list < read < create/update/delete   +   export   +   sensitive
```

Nomes **internos** usam `read`/`update` (não `view`/`edit`) para não colidir com os códigos legados `<recurso>.view`/`<recurso>.edit`. A UI mostra rótulos pt-BR (Visualizar/Editar).

### 2.3. `role_permissions`
Tabela que liga `roles` a `permissions`. É o **vínculo vivo**: mudar as permissões de um perfil reflete imediatamente em todos os usuários daquele perfil. Semeada por migrations (0091 em diante). Perfis de sistema: `ADMIN`, `GESTOR`, `CONSULTA` (há também perfis não-sistema como `ADMINISTRATIVO`, `FINANCEIRO`).

### 2.4. `user_permissions`
Deltas individuais por usuário. Coluna **`granted`**:
- `granted = True` (ou ausente/None) → **adição** individual.
- `granted = False` → **remoção** individual (sobrepõe o perfil).

### 2.5. Permission graph (grafo de implicação)
`PERMISSION_IMPLIES: dict[str, frozenset[str]]` em `app/core/permission_codes.py`.
"A: {B, C}" = quem tem A tem B e C. Espelhado no frontend em `frontend/src/permissions.ts` (`PERMISSION_IMPLIES`).

Regras do grafo:
- Cadeia de verbos: `update`/`delete` ⇒ `read` ⇒ `list` ⇒ `reference`; `create` ⇒ `reference`.
- `create`/`update` ⇒ `cost_center.reference` (para escolher Centro de Custo em cadastros).
- `sensitive` é **independente** (bundle; não é implicado por read/update).
- **Aliases legados** apontam **só para códigos NOVOS** (nunca para outro legado), preservando neutralidade:
  - `<r>.view` ⇒ `<r>.read`, `<r>.sensitive`, (`<r>.export` onde há export), `cost_center.reference`.
  - `<r>.edit` ⇒ `<r>.create`, `<r>.update`, `<r>.delete`, `<r>.sensitive`, (`<r>.export`).
- `projects.view` ⇒ `view_list`/`view_detail` (atalho legado preservado).
- `system.admin` ⇒ `users.manage`, `settings.view`, `settings.edit` (**apenas** administração do sistema; nunca negócio).

### 2.6. Permission implication (fecho transitivo)
`expand_permissions(held)` (backend) e `expandPermissions(held)` (frontend) calculam o fecho transitivo sob o grafo. A autorização (`user_has_permission`) verifica `code in expand_permissions(effective)`.

### 2.7. Sessão
`session_context.session_permission_names(user)`:
```
names = effective_permission_names(user) ∪ permission_names_from_user(user)   # explícitos
names &= ACTIVE_PERMISSION_CODES        # NEUTRALIDADE: só expõe códigos ATIVOS
+ adiciona workspace.*.access derivados
```
- `SESSION_VERSION = 2`. Token com versão diferente → 401 (força novo login).
- **Só códigos ATIVOS entram na sessão** (o frontend só "vê" o que está ativo).

### 2.8. Frontend
`frontend/src/permissions.ts` é o espelho do catálogo backend:
- `ALL_PERMISSION_CODES` (ordem estável), `NEW_PERMISSION_CODES`, `PERMISSION_LABELS`.
- `PERMISSION_IMPLIES` + `expandPermissions`.
- `hasPermission(names, code)` — mesma lógica do backend (fecho + regras de workspace).
- Grade única: `permissionGridGroups()`, `permissionGrid()`, `RESOURCE_LABELS`, `COLUMN_ORDER`/`COLUMN_LABELS`.
- `usePermission(code)` (hook) e `hasPermission(user?.permission_names, code)` são as duas formas usadas.

### 2.9. Backend
- `app/core/permission_codes.py` — **fonte única** dos códigos, grafo, presets, catálogo (`PERMISSION_SPECS`), ativação.
- `app/api/deps.py` — `require_permission(*codes)` (OR), `require_admin`, `user_has_permission`, `user_has_any_permission`, escopo de projetos.
- `app/api/sensitive.py` — `redact()` + conjuntos de campos sensíveis por recurso.

### 2.10. Workspaces
Quatro workspaces: `projects`, `finance`, `assets`, `indicators`. Cada um tem `workspace.<nome>.access`. O acesso é **derivado**: ter qualquer permissão de módulo daquele workspace concede o acesso. A derivação está em `session_context._workspace_permission_from_module_permissions` e no `hasPermission` do frontend.

**⚠️ Observação importante (compatibilidade):** os conjuntos de derivação (`PROJECTS_WORKSPACE_PERMISSIONS`, `ASSETS_WORKSPACE_PERMISSIONS`, etc.) checam os códigos **legados** `*.view`/`*.edit`, **não** os verbos novos. Portanto um usuário só com `assets.read` (verbo novo) **não** ganha `workspace.assets.access` automaticamente — é preciso conceder o `workspace.*.access` explicitamente (foi assim nos testes de Ativos).

### 2.11. Permissões especiais / transversais
Concessão **explícita** (`EXPLICIT_GRANT_ONLY_PERMISSIONS`): `invoices.reactivate`, `audit.export` — só valem se marcadas em `user_permissions` (não herdam de ADMIN/preset).

### 2.12. Decisões arquiteturais tomadas
1. **Neutralidade por código**: legados `view`/`edit` viram bundles que implicam os verbos novos → 100% compatível sem tocar `user_permissions`.
2. **Ativação incremental** (`_ACTIVATED_NEW_CODES`): códigos novos nascem **inativos** e são ativados módulo a módulo. Inativo não entra na sessão e não é checado por endpoint.
3. **Migrations aditivas e idempotentes** (`ON CONFLICT DO NOTHING`); downgrade remove só o que a migration criou; nunca apaga se houver referência em `user_permissions`.
4. **`<recurso>.export` próprio por recurso** (regra arquitetural): exportação de um recurso específico usa `<recurso>.export`; `reports.export` fica **só** para o módulo Relatórios. **Não reutilizar** permissão transversal para exportação de módulo específico.
5. **Grade única** (não existe mais "Outras permissões"): 100% das permissões viram célula recurso × ação.

---

## 3. Recursos já migrados

Legenda: ✅ concluído · 🟡 parcial · ⛔ pendente · 🔒 sensitive ativado · 🔓 sensitive inativo

| Recurso | Verbos (backend) | Frontend | Sensitive | Export | Testes | Observações |
|---|---|---|---|---|---|---|
| **Colaboradores** (`employees`) | ✅ list/read/create/update/delete | ✅ | 🔒 **ativo** | ✅ `employees.export` (migration 0096) | ✅ | Menu = `employees.read`. Financeiro exige `employees.sensitive`. |
| **Veículos** (`vehicles`, módulo `fleet`) | ✅ | ✅ | 🔒 **ativo** | ✅ `vehicles.export` (migration 0097) | ✅ | Cadastro virou **modal** ("+ Novo veículo"). Coluna Centro de Custo + filtro. |
| **Ativos / Patrimônio** (`assets`) | ✅ | ✅ | 🔒 **ativo** (esta conversa) | ⛔ (sem `assets.export`; export segue `assets.read`) | ✅ | Dashboard/gráficos/cards/lista redigidos por `assets.sensitive`. |
| **Projetos** (`projects`) | ✅ reference/list/read/update (+ legados create/edit/delete) | ✅ | 🔓 inativo | — | ✅ | `projects.sensitive` semeado, **inativo**. |
| **Contas a pagar** (`payables`) | ✅ list/read/create/update/delete | ✅ | 🔓 inativo | — | ✅ | `payable_snapshot.reconcile` transversal. |
| **Contas a receber** (`receivables`) | ✅ | ✅ | 🔓 inativo | — | ✅ | |
| **Notas fiscais** (`invoices`) | ✅ | ✅ | 🔓 inativo | — | ✅ | `invoices.reactivate` explicit-grant. |
| **Endividamento** (`debts`) | ✅ (via `company_finance` por `tipo=endividamento`) | ✅ | 🔓 inativo | — | ✅ | Compartilha endpoints de `company_finance`. |
| **Custos** (`costs`) | ✅ read/create (+ update/delete no catálogo) | ✅ | 🔓 inativo | — | ✅ | |
| **Finanças da empresa** (`company_finance`) | ✅ (por `tipo=custo_fixo`) | ✅ | 🔓 inativo | — | ✅ | |
| **Faturamento** (`billing`) | ✅ | ✅ | 🔓 inativo | — | ✅ | |
| **Dashboard** (`dashboard`) | ✅ read (+ `dashboard.director`) | ✅ | 🔓 inativo | — | ✅ | |
| **Indicadores** (`indicators`) | ✅ read (+ `indicators.director`) | ✅ | 🔓 inativo | — | ✅ | |
| **Relatórios** (`reports`) | ✅ read (+ `reports.export`) | ✅ | — | `reports.export` (só Relatórios) | ✅ | |
| **Configurações** (`settings`) | ✅ read/update | ✅ | — | — | ✅ | `system.admin` ⇒ settings. |
| **Alertas** (`alerts`) | ✅ read | ✅ | — | — | ✅ | Transversal, na grade em "Gestão". |
| **Auditoria** (`audit`) | — | ✅ (grade) | — | `audit.export` (explicit-grant) | ✅ | |
| **Usuários** (`users`) | `users.manage` | ✅ | — | — | ✅ | |

**Eixo Sensitive — status:** ativos = **Colaboradores, Veículos, Ativos**. Todos os demais `*.sensitive` estão **semeados no banco mas inativos** (aguardando a etapa de cada módulo).

---

## 4. Modelo oficial de permissões (colunas da grade)

Ordem em `COLUMN_ORDER` (frontend `permissions.ts`) e `_VERB_ORDER`/`VERB_LABELS` (backend):

| Coluna (rótulo) | Chave interna | Quando usar |
|---|---|---|
| **Referenciar** | `reference` | Usar o recurso em selects/autocomplete/relacionamentos de **outros módulos**, sem abrir a tela do módulo. **NÃO** vê o menu. |
| **Listar** | `list` | Nível intermediário do grafo. Uso técnico: recuperar a lista para pickers/outros módulos. Sozinho **não** dá acesso à tela (o acesso é `read`). |
| **Visualizar** | `read` | **Controla o acesso ao módulo** (menu + página). Vê lista/detalhe SEM valores financeiros. |
| **Criar** | `create` | Botão "Novo"; cadastrar. Pode digitar valores; após salvar continua sem **ver** valores se não tiver `sensitive`. |
| **Editar** | `update` | Editar; pode alterar valores financeiros. Não concede **visualização** permanente. |
| **Excluir** | `delete` | Botão Excluir. **Independente** de Editar. |
| **Exportar** | `export` | Recurso aparece como opção de exportação. Sem `sensitive`, o export sai **sem** valores financeiros. Usar `<recurso>.export`. |
| **Executar** | `execute` | Operações privilegiadas não-CRUD. Ex.: `invoices.reactivate` (Notas fiscais · Executar), `payable_snapshot.reconcile` (Contas a pagar · Executar). |
| **Diretoria** | `director` | Visão consolidada/global (todos os projetos). Ex.: `dashboard.director`, `indicators.director`. |
| **Acessar** | `access` | Liberar acesso a uma área/escopo. Ex.: `workspace.*.access`, `system.all_projects`. |
| **Administrar** | `manage` | Gestão/administração plena. Ex.: `users.manage`, `system.admin`. |
| **Dados sensíveis** | `sensitive` | **NÃO** concede acesso ao módulo. Apenas amplia os campos: libera **todos os valores financeiros** (salários, custos, margens, PIX, custo mensal, valor patrimonial, etc.). Sempre a última coluna. |

**Como a grade é montada (frontend `permissions.ts`):**
- Colunas derivadas por sufixo (`DERIVED_COLUMNS`): reference/list/read/create/update/delete/export/director/manage/sensitive.
- `access` e `execute` **nunca** aparecem como sufixo literal — só via `CODE_PLACEMENT` (mapeamento explícito).
- `CODE_PLACEMENT` mapeia códigos irregulares → (recurso, coluna): `system.admin→system_admin/manage`, `system.all_projects→system_all_projects/access`, `workspace.*.access→workspace_*/access`, `invoices.reactivate→invoices/execute`, `payable_snapshot.reconcile→payables/execute`, `projects.documents.view/upload/delete→project_documents/read|create|delete`.
- `LEGACY_HIDDEN_CODES` = códigos sem célula (aliases `.view/.edit/.view_list/.view_detail`) — **ocultos** mas **preservados** ao salvar.
- `UNMAPPED_CODES` deve ser **sempre vazio** (guarda de cobertura 100%).

---

## 5. Regras específicas já definidas (por módulo)

### Colaboradores (`employees`)
- **read** (Visualizar) = acesso ao módulo (menu = `employees.read`). Vê lista/cargo/tipo/datas/admin **sem** salário/custo/encargos/PIX.
- **list** = sem responsabilidade própria distinta (uso compartilhado por pickers de outros módulos — `GET /employees` **mantido** em `employees.list`).
- **create/update/delete** = botões e endpoints próprios. Excluir independente de Editar.
- **export** = `employees.export` (migration 0096; ADMIN+GESTOR). Relatórios "Colaboradores"/"Folha" exigem `employees.export`. Sem `employees.sensitive`, o relatório sai sem valores.
- **sensitive** = `employees.sensitive` (**ativo**). Campos financeiros omitidos pelo backend (`redact` + `EMPLOYEE_SENSITIVE_FIELDS = salary_base, additional_costs, total_cost, pj_additional_cost, pj_hours_per_month, pix_key, pix_key_type`). Endpoints `/payroll`, `/staff-costs` (GET), `/{id}/monthly-payroll` (GET) exigem `employees.sensitive`. Blocos "Resumo da Competência" e "Custos da Competência" só existem com sensitive. Respostas de create/update também redigidas.

### Veículos (`vehicles`, módulo backend `fleet`, prefixo `/vehicles`)
- **read** = acesso ao módulo (menu `vehicles.read`). Vê placa/modelo/tipo/condutor/status.
- **list** = mantido (pickers de outros módulos — Projetos/Finanças usam `GET /vehicles`).
- **create/update/delete** = próprios; Excluir independente.
- **export** = `vehicles.export` (migration 0097). Relatório "Frota" exige `vehicles.export`.
- **sensitive** = `vehicles.sensitive` (**ativo**). Campo financeiro: `monthly_cost` (`VEHICLE_SENSITIVE_FIELDS = monthly_cost`). Sem sensitive: oculta coluna "Custo mensal", card "Custo total da frota" e custo por categoria (mantém contagem). Respostas de create/update redigidas.
- **Melhoria funcional:** coluna **Centro de Custo** + **filtro por Centro de Custo** (server-side, estrito) + cards refletindo o filtro. Cadastro virou **modal** ("+ Novo veículo"), fecha ao salvar e preserva filtro.

### Ativos / Patrimônio (`assets`)
- **read** = acesso ao módulo (dashboard + gráficos + lista). Vê quantidades, categorias, estados físicos, dados não financeiros.
- **sensitive** = `assets.sensitive` (**ativado nesta conversa**). Campo do item: `purchase_value` (`ASSET_SENSITIVE_FIELDS = purchase_value`).
  - Backend redige `purchase_value` em lista/EPIs/detalhe/create/update.
  - Dashboard: `_redact_dashboard()` **zera** os agregados monetários (`status.*.value`, `physical_condition[].value`, `by_category[].value`, `by_cost_center[].amount_total`/`average_value`, `alerts.*.amount_total`), **preservando** contagens.
  - Relatórios `assets_inventory`/`assets_in_use`: campo `valor` omitido sem sensitive (param `include_sensitive`).
  - Frontend oculta: coluna "Valor" da lista; "Valor do item" no detalhe (mantém input editável p/ quem tem update); strip "Financeiro"; linha de valor dos cards; barra "Valor (R$)"; card "Valor patrimonial por centro de custo"; valor dos alertas.
- **export** = **NÃO** implementado (`assets.export` não existe). Export de ativos segue `assets.read`. Pendente (ver §9).
- **Compatibilidade:** quem tem o **legado `assets.view`** continua vendo valores (grafo: `assets.view ⇒ assets.sensitive`). A ocultação vale para quem acessa pelo **verbo `assets.read`** sem view/sensitive.

### Demais módulos (Projetos, Financeiro, etc.)
- Verbos CRUD **ativos** e enforçados. `*.sensitive` **semeado mas inativo** — a etapa de Dados Sensíveis de cada um ainda não foi feita.
- Endividamento e Custos Fixos-Matriz compartilham os endpoints de `company_finance`, distinguidos por `?tipo=endividamento|custo_fixo`; a autorização é por `tipo` (`_verb_code_for_tipo`): endividamento → `debts.<verbo>`; custo_fixo → `company_finance.<verbo>`.

---

## 6. Padrões arquiteturais reutilizáveis

### `useAuxiliaryResource` (`frontend/src/hooks/useAuxiliaryResource.ts`)
**Regra:** um módulo NUNCA deve deixar de funcionar por causa de um recurso auxiliar (filtro, select, autocomplete, vocabulário).
- Assinatura: `useAuxiliaryResource(loader, fallback, deps, enabled)` → `{ data, available, loading, reload }`.
- Em 403/401 (ou qualquer erro), `available = false` e **nenhum erro é propagado**; o componente deve **ocultar/desabilitar** o controle.
- `enabled` (pré-gate por permissão) evita disparar a request que daria 403.
- `isAuthDenied(err)` exportado. Recurso **principal** carrega à parte (obrigatório); auxiliares em separado.
- **Aplicado em:** Colaboradores (filtro Projeto), Veículos (condutor/colaboradores + centros de custo). Reutilizar em Financeiro/Indicadores/Relatórios.

### Permissões Sensitive
Padrão de 3 camadas:
1. Ativar `<recurso>.sensitive` em `_ACTIVATED_NEW_CODES` (permission_codes.py).
2. Backend: `redact(model, <RECURSO>_SENSITIVE_FIELDS, include=user_has_permission(user, SENSITIVE))` nos endpoints (list/detail/create/update) + omissão em relatórios (param `include_sensitive`). Agregados nested (dashboards) via função dedicada que zera os campos monetários.
3. Frontend: `const canSeeSensitive = usePermission("<recurso>.sensitive")` (ou `hasPermission(user?.permission_names, ...)`), condicionar renderização das colunas/cards/gráficos monetários.
- **Legado `<recurso>.view` ⇒ `<recurso>.sensitive`** (compatibilidade): usuários legados continuam vendo valores.

### Exports por recurso
`<recurso>.export` próprio + migration aditiva (ADMIN+GESTOR) + catálogo BE/FE + grafo (`view ⇒ export`, `edit ⇒ export`). `reports.export` = só Relatórios. Mascarar financeiro por `<recurso>.sensitive` no payload do relatório.

### Permission Grid (grade única)
`permissionGridGroups()` monta grupos **Cadastros / Financeiro / Gestão / Sistema** + "Outros recursos" (salvaguarda). Célula = checkbox do código; "—" quando a ação não se aplica. Componente `PermissionGrid.tsx`. Cobertura 100% garantida por `UNMAPPED_CODES == []`.

### Layout fullscreen (editor de permissões)
Painel ~95vw × 95vh, `flex-col`: **cabeçalho fixo** + miolo (campos fixos + grade rolável) + **rodapé fixo** (Salvar/Cancelar). Grade: `sticky` header (top) e primeira coluna "Recurso" (left), coluna Recurso larga (`min-w-15rem`, `whitespace-nowrap`), `w-full` para caber sem rolagem horizontal na maioria dos casos.

### Modal padrão de cadastro
Botão "+ Novo X" acima da lista (gate pela permissão `create`) → modal (`fixed inset-0 z-50 flex items-center justify-center bg-black/40`; painel `max-w-2xl`, header com título + ✕, footer Cancelar/Cadastrar). Ao salvar com sucesso: fecha, `reload()` (preservando filtros), atualiza lista/cards. Aplicado em Veículos; padrão dos modais de Usuários/Perfis.

---

## 7. Estado atual do frontend

- **Permission Grid**: modelo **único** (não existe "Outras permissões"). Linhas = recursos (26), colunas = 12 ações. Grupos: Cadastros, Financeiro, Gestão, Sistema.
- **Modais**: Usuários e Perfis (`RolesManager`) usam `PermissionGrid` em painel fullscreen. Veículos usa modal de cadastro.
- **Sidebar** (`components/Sidebar.tsx`) e **navegação** (`workspaces/navigation.ts`): cada item de menu tem `perm`. Menus de módulo apontam para o **verbo `read`** (ex.: Colaboradores `employees.read`, Veículos `vehicles.read`).
- **Recursos agrupados**: `RESOURCE_GROUPS` (Cadastros/Financeiro/Gestão/Sistema).
- **Colunas**: `COLUMN_ORDER`/`COLUMN_LABELS`.
- **Layout**: grade sticky (header + 1ª coluna), fullscreen no editor.
- Arquivos-chave: `permissions.ts`, `components/PermissionGrid.tsx`, `hooks/usePermission.ts`, `hooks/useAuxiliaryResource.ts`, `pages/{Users,RolesManager,Employees,Vehicles,Assets,AssetDetail,AssetsDashboard,Reports}.tsx`, `components/assets/{AssetsDashboardCharts,AssetOperationalAlertCard}.tsx`.

---

## 8. Estado atual do backend

- **`permission_codes.py`**: fonte única. Contém constantes, `ALL_PERMISSION_CODES`, `NEW_PERMISSION_CODES`, `PERMISSION_IMPLIES`, `expand_permissions`, presets (`PRESET_ADMIN/GESTOR/CONSULTA`, `ROLE_PRESET`), `_ACTIVATED_NEW_CODES`, `ACTIVE_PERMISSION_CODES`, `EXPLICIT_GRANT_ONLY_PERMISSIONS`, `PERMISSION_SPECS` (catálogo), `RESOURCE_LABELS`/`VERB_LABELS`.
  - Ativos atualmente: legados + verbos CRUD de todos + `cost_center.reference` + `employees.export` + `vehicles.export` + `employees.sensitive` + `vehicles.sensitive` + `assets.sensitive`.
  - Inativos: todos os demais `*.sensitive`.
- **Migrations** (`alembic/versions/`): 0090 (decouple módulos), 0091 (admin roles + `role_permissions`), **0092** (infra verbos: employees/assets/cost_center), **0093** (vehicles verbos), **0094** (projects verbos), **0095** (finanças/leitura verbos), **0096** (`employees.export`), **0097** (`vehicles.export`). Todas aditivas/idempotentes. Head = `0097_vehicles_export`.
  - **⚠️ Não há migration para `assets.sensitive`/`vehicles.sensitive`/`employees.sensitive`**: a ativação é feita **em código** (`_ACTIVATED_NEW_CODES`), pois o código já foi semeado nos perfis pelas migrations 0092/0093. Ativar = mover para `_ACTIVATED_NEW_CODES`.
- **Permission graph**: `PERMISSION_IMPLIES` (ver §2.5).
- **Snapshot** (Contas a Pagar): `payable_snapshot_service.py` — ver §11.
- **Services**: `company_finance_service.py`, `payable_snapshot_service.py`, `employees_service.py`, `fleet_service.py`, `assets_service.py`, `assets_dashboard_service.py`, `report_service.py`, `operational_report_service.py`, `report_export.py`, `operational_report_export.py`.
- **Helpers**: `app/api/sensitive.py` (`redact`, `*_SENSITIVE_FIELDS`), `app/utils/date_utils.py` (`normalize_competencia`, `next_competencia`, `previous_competencia`), `app/utils/lifecycle.py`.

---

## 9. Pendências

### Alta prioridade
- ~~**Bug do Contas a Pagar (deslocamento de competência do Endividamento)**~~ — **RESOLVIDO** (2026-07-22). Refatoração da regra CAP × Custos Fixos/Endividamento: a **grade mensal é o valor oficial da competência** (fallback = valor de referência); o piso JUL/2026 deixou de bloquear a **manutenção de competências abertas** (ex.: DEX/Junho). Ver §10.1 e §11.
- **Eixo Sensitive dos módulos restantes**: Projetos, Contas a pagar, Contas a receber, Notas fiscais, Endividamento, Custos, Finanças da empresa, Dashboard (métricas financeiras), Indicadores financeiros, Faturamento. Aplicar o padrão Sensitive (§6).

### Média prioridade
- **`assets.export`**: hoje o export de Ativos usa `assets.read`. Para seguir a regra arquitetural (§2.12 item 4), criar `assets.export` (código + migration + catálogo BE/FE + grafo `view/edit ⇒ export`) e repointar os 4 relatórios de ativos.
- Revisar a **derivação de workspace** (§2.10): hoje só reconhece `*.view`/`*.edit` legados; usuários "verbo-puro" (ex.: só `assets.read`) não ganham `workspace.*.access` automaticamente.

### Baixa prioridade / decisões pendentes
- `projects.documents.*`: manter como sub-recurso (Documentos do projeto) ou converter para 7 verbos padrão (decisão adiada — recomendação atual: **manter**).
- `LISTAR`: documentado como "sem responsabilidade própria" na maioria dos módulos (uso técnico de pickers).

---

## 10. Problemas conhecidos

### 10.1. Deslocamento de competência no Contas a Pagar (Endividamento) — **RESOLVIDO (2026-07-22)**

**Correção implementada (refatoração, não pontual):** a regra CAP × Custos Fixos/Endividamento passou a seguir a nova regra de negócio:
- **Valor oficial da competência** = valor informado na grade mensal (`company_financial_payments`) quando existir; senão, o **valor de referência** (fallback). Vale igualmente na **geração** e no **sync** (fonte única: `_company_finance_grid_value`/`_company_finance_grid_map` + `_company_finance_monthly_value` para o fallback). O valor da grade é usado **exclusivamente** (igual/maior/menor não importa) e **não gera saldo/crédito/ajuste** (`amount_original == amount_final`).
- **Piso JUL/2026 preservado para o histórico, mas não bloqueia manutenção de competência ABERTA**: abaixo do piso, a geração/sync só agem quando há **valor explícito na grade** (nunca a partir só da referência). Assim o caso **DEX/Junho** passou a: (a) gerar a linha quando o mês é aberto (grade presente) e (b) criar/atualizar a linha ao editar a grade de uma competência aberta.
- **Histórico intacto**: linhas com pagamento (`amount_paid>0` ou pagamento ativo) nunca são alteradas — reportadas em `skipped_paid`. `purge_pre_launch_company_finance_payables` passou a **preservar** linhas pré-piso que tenham valor na grade.
- **Sem `relativedelta`** (a causa nunca foi incremento — era o piso). Validado nos 6 cenários (rollback, nada persistido) + suíte `pytest` (213 passam; 1 falha ambiental §10.3).

Métodos alterados: `_generate_company_finance_payables`, `sync_company_finance_item_months`, `purge_pre_launch_company_finance_payables` + helpers novos (`_company_finance_item_eligible_for_comp`, `_company_finance_grid_value`, `_company_finance_grid_map`). Testes: `test_grid_governs_payable.py`, `test_payable_auto_generation.py`, `test_pre_launch_payable_cleanup.py`.

<details><summary>Diagnóstico original (histórico) — deslocamento no CAP</summary>
- **Descrição**: Endividamento com 1º pagamento 01/06/2026, grade Junho=718,96; esperado CAP JUN/2026 = 718,96; obtido **CAP JUL/2026 = 718,96**.
- **Hipótese inicial do usuário**: `relativedelta(months=+1)` em algum ponto.
- **Investigação realizada** (item real `DEX CERTIFICADORA DE SISTEMA DE GESTAO`, id `f8fa3500-2453-4848-bb2b-abc343274823`):
  - Item: `has_renegotiation=True`, `renegotiation_type=INSTALLMENTS`, **`installment_value=718.96`**, `installment_count=36`, `renegotiation_first_payment_date=2026-06-01`, `start_date=2026-06-01`, `is_monthly_required=True`, `valor_referencia=25882.56`.
  - Grade (payments): `[(2026-06, 718.96), (2026-07, 733.44)]`.
  - CAP gerado (payable_snapshots): **`[(2026-07, 718.96, DEBT)]`** — nota: o valor é **718,96 (installment_value)**, **não** 733,44 (grade de julho). Isso prova que o CAP usa `installment_value`, não a grade.
- **Conclusão (causa-raiz)**: **NÃO há `relativedelta(+1)`**. O deslocamento é um **PISO de competência**:
  ```python
  # payable_snapshot_service.py:56
  COMPANY_FINANCE_AUTOGEN_FIRST_COMPETENCE = date(2026, 7, 1)
  # _generate_company_finance_payables (linha ~715) e sync (linha ~933):
  if comp < COMPANY_FINANCE_AUTOGEN_FIRST_COMPETENCE:
      return 0  # / continue
  ```
  Junho (< JUL/2026) é **descartado**; a primeira competência elegível é Julho, que recebe o `installment_value` (718,96) via `_company_finance_monthly_value` (ramo Endividamento INSTALLMENTS). O lançamento nasce com `month=comp` (sem incremento). O "valor de Junho em Julho" é coincidência: `installment_value == valor digitado em Junho`.
- **Status original**: diagnosticado. A correção adotada (ver topo desta seção) foi a **opção (a) generalizada**: o piso preserva o histórico, mas a grade governa e permite manutenção de competências abertas — não se ancorou no `renegotiation_first_payment_date` nem se introduziu `relativedelta`.

</details>

### 10.2. `MissingGreenlet` na criação de veículo — **REFUTADO (não é bug)**
- **Descrição**: suspeita de 500 ao criar veículo com condutor.
- **Investigação**: reprodução via HTTP real → **ambos os cenários (com e sem condutor) retornam HTTP 200**. O `MissingGreenlet` só aparecia num harness Python isolado (sessão avulsa + `flush()` sem `refresh`).
- **Conclusão**: `Vehicle.driver` é `lazy="joined"` e a sessão usa `expire_on_commit=False`; o `session.refresh(v)` do `create_vehicle` já carrega o driver → sem lazy load no request real. **Não há bug.** Um diagnóstico anterior (que apontava MissingGreenlet como causa-raiz) foi **retratado**.

### 10.3. Falha pré-existente de teste — **AMBIENTAL**
- `tests/test_advance_batch_payables.py::...survive_invalidate_and_regenerate` falha localmente por **estado acumulado no banco de teste** (lançamentos automáticos pagos bloqueiam regeração). Não relacionado a permissões nem às mudanças do projeto. Restante da suíte passa (~210).

### 10.4. Bug de UI "Não foi possível salvar" (turno anterior) — **RESOLVIDO por padrão**
- Causa: `Promise.all([listEmployees, listProjects])` — `listProjects` 403 derrubava a carga. Resolvido com `useAuxiliaryResource` (recurso auxiliar não impede a tela).

---

## 11. Regra de negócio oficial do Contas a Pagar (CAP)

> Esta seção consolida o entendimento desta conversa sobre a geração automática do CAP a partir dos cadastros corporativos (Custos Fixos e Endividamento). Fonte: `app/services/payable_snapshot_service.py` + `app/services/company_finance_service.py`.

### 11.1. Filosofia
**O CADASTRO governa a linha do Contas a Pagar.** A "matriz mensal" (grade) **não governa mais** a existência do lançamento — ela apenas ajusta o **valor** de lançamentos já existentes.

### 11.2. Geração automática (`_generate_company_finance_payables(payment_month=comp)`)
Cria a **linha** de cada competência elegível. Para cada item ativo cuja vigência cobre `comp`:
- **Piso de implantação** (JUL/2026): abaixo do corte, **NÃO** gera a partir do valor de **referência** (não retroage / preserva histórico); **gera apenas os itens que têm valor explícito na grade** daquela competência (manutenção deliberada de competência aberta — ex.: DEX/Junho). `comp >= JUL/2026` gera normalmente.
- Filtro: `tipo ∈ (custo_fixo, endividamento)`, `is_active=True`, `start_date <= fim_do_mês`, `end_date >= comp` (ou nulo).
- **Endividamento** só gera quando `is_monthly_required=True`.
- **Idempotência** por `(competência, ref_id)`: se já existe lançamento daquele item na competência, **não** cria de novo. **Nunca apaga.**
- **Valor oficial** = **grade** (`company_financial_payments`) se informada; senão **referência** (`_company_finance_monthly_value`). Gravado em `amount_original = amount_final = value`, `origin ∈ {FIXED_COST, DEBT}`, `due_date = _default_due_date(comp, day=10)`.

### 11.3. Valor de REFERÊNCIA / fallback (`_company_finance_monthly_value(item, comp)`)
> Usado **apenas como fallback**, quando a competência **não** possui valor na grade. Havendo valor na grade, o CAP usa **exclusivamente** o valor da grade (ver §11.4).
- **Custo fixo COLABORADOR_MATRIZ**: custo do colaborador no mês × percentual (CLT usa `calculate_clt_cost(comp)`; PJ usa `calculate_pj_total_cost`).
- **Custo fixo comum**: `valor_referencia`.
- **Endividamento** (parcela mensal de referência):
  - Se renegociação `INSTALLMENTS` e `installment_value` não nulo → **`installment_value`**.
  - Senão, se renegociado com `renegotiated_amount` → `renegotiated_amount`.
  - Senão → `valor_referencia`.

### 11.4. Grade mensal (`company_financial_payments`) e o "valor oficial da competência"
- `replace_payments` (`PUT /company-finance/items/{id}/payments`): converte a grade em linhas `CompanyFinancialPayment(competencia, valor)` (`comp = parse_month("YYYY-MM")`, **sem deslocamento**), depois chama `sync_company_finance_item_months(months)`.
- `sync_company_finance_item_months`: para cada mês, `new_amount = valor da grade (se lançado) senão _company_finance_monthly_value(...)`. Depois:
  - **Piso (só preserva histórico)**: abaixo de JUL/2026, só age quando **há valor explícito na grade**; sem grade → `continue` (nunca a partir só da referência).
  - Localiza a linha por `(ref_id + month + tipo corporativo)`.
    - **Existe + aberta** → atualiza `amount_original`/`amount_final` para `new_amount` (valor oficial; **não** gera saldo/ajuste).
    - **Existe + paga** (`amount_paid>0`/pagamento ativo) → **não altera** (preserva histórico) e reporta em `skipped_paid`.
    - **Não existe** → **cria** a linha quando o usuário informou o valor na grade (`grid_val` presente), o item é elegível (`_company_finance_item_eligible_for_comp`) e o mês já foi **materializado** (`is_generated`). Cobre a competência **ABERTA anterior ao piso** (DEX/Junho) sem poluir meses não gerados nem suprimir a geração de custos de projeto.
- Portanto o "valor oficial da competência" = **valor da grade se houver**, senão referência/parcela — e a linha pode ser **criada pela grade** em competências abertas (não só pela geração).

### 11.5. Integração com o CAP / competências abertas
- `get_or_create_for_month(payment_month)` monta o snapshot do mês, invocando `_ensure_company_finance_auto_entries(payment_month=comp)` → `_generate_company_finance_payables(comp)`.
- Regeração é **bloqueada** se houver lançamentos automáticos **pagos** na competência (preserva histórico) — origem da falha ambiental §10.3.
- `invalidate_months(months)`: remove snapshots recalculáveis; **recusa** invalidar meses com linhas automáticas pagas.

### 11.6. Preservação do histórico
- Nunca apaga manuais (`origin=MANUAL`), de projeto/colaborador (`origin=PROJECT/NULL`).
- Só sincroniza/regenera lançamentos automáticos **não pagos**.

### 11.7. Comportamento (após a correção de 2026-07-22)
- **Competência aberta anterior a JUL/2026 é editável**: informar o valor na grade cria/atualiza o lançamento do CAP daquela competência (ex.: DEX/Junho passa a exibir a parcela). O piso deixou de "descartar" competências abertas — só bloqueia geração retroativa **sem** valor na grade.
- **Grade governa**: qualquer valor informado (igual/maior/menor que a referência) vira o valor oficial da competência, sem gerar saldo/crédito/ajuste; pagar esse valor zera o saldo.
- **Histórico intocado**: competências pagas/consolidadas não mudam (`skipped_paid`).

---

## 12. Próximos passos (ordem sugerida)

1. ~~Correção do CAP/Endividamento~~ **FEITA (2026-07-22)** — ver §10.1/§11. Regra: grade = valor oficial da competência; piso preserva histórico mas permite manutenção de competências abertas.
2. **Aplicar o eixo Sensitive** aos módulos restantes (§9), começando pelos financeiros (payables, receivables, invoices, debts, costs, company_finance, billing) e depois dashboard/indicadores.
3. **Criar `assets.export`** (regra arquitetural de export por recurso).
4. **Corrigir a derivação de workspace** para reconhecer verbos novos (não só `*.view/*.edit`).

---

## 13. Arquivos alterados durante o projeto (principais)

### Backend
- `app/core/permission_codes.py` — catálogo, grafo, presets, ativação (employees/vehicles export + employees/vehicles/assets sensitive).
- `app/core/session_context.py`, `app/api/deps.py` — efetivo por vínculo vivo + deltas; sem bypass.
- `app/api/sensitive.py` — `redact` + `EMPLOYEE_/VEHICLE_/ASSET_SENSITIVE_FIELDS`.
- `app/modules/employees/router.py`, `app/modules/collaborators/router.py` — verbos + sensitive.
- `app/modules/fleet/router.py` — verbos + sensitive + filtro Centro de Custo.
- `app/modules/assets/router.py` — sensitive (redact list/detalhe/create/update + `_redact_dashboard`).
- `app/modules/reports/router.py` — export por recurso (`employees.export`, `vehicles.export`), `include_sensitive` (employees/vehicles/assets).
- `app/services/report_service.py`, `app/services/operational_report_service.py` — máscara financeira nos relatórios.
- `app/services/fleet_service.py`, `app/repositories/fleet.py`, `app/schemas/fleet.py` — Centro de Custo/filtro.
- `alembic/versions/0092..0097` — migrations aditivas.

### Frontend
- `frontend/src/permissions.ts` — grade única, catálogo, grafo, `CODE_PLACEMENT`, colunas.
- `frontend/src/components/PermissionGrid.tsx` — grade única (sem "Outras permissões"), sticky.
- `frontend/src/hooks/useAuxiliaryResource.ts` — **novo** padrão.
- `frontend/src/hooks/usePermission.ts`.
- `frontend/src/pages/{Users,RolesManager,Employees,Vehicles,Assets,AssetDetail,AssetsDashboard,Reports}.tsx`.
- `frontend/src/components/assets/{AssetsDashboardCharts,AssetOperationalAlertCard}.tsx`.
- `frontend/src/workspaces/navigation.ts`, `frontend/src/components/Sidebar.tsx` — menus por verbo `read`.
- **Deletados**: `frontend/src/hooks/{useConsultaReadOnly,useGestorGlobalReadOnly}.ts`.

---

## 14. Testes existentes

### Automatizados (backend, `pytest`)
- `tests/test_permission_verbs.py` — grafo, fecho, `test_activation_state` (verifica quais códigos estão ativos; atualizado para incluir employees/vehicles/assets sensitive + employees/vehicles export como ativos).
- `tests/test_sensitive_axis.py` — `redact` omite campos; `read` sozinho **não** concede `sensitive`; legado `view` concede.
- `tests/test_users_permission_grid.py` — round-trip do editor de permissões; usa um código **inativo** que CONSULTA não concede para testar neutralidade (**repontado para `payables.sensitive`** porque `assets.sensitive` foi ativado).
- `tests/test_reference_endpoints.py`, e outros. Suíte total ~210 passam (1 falha ambiental §10.3).
- Rodar: `.venv/bin/python -m pytest tests/ -q`. Frontend: `cd frontend && npx tsc --noEmit`.

### Validação manual (via injeção de token JWT no `localStorage.sgp_access_token`)
- Padrão de verificação: gerar token com `create_access_token(build_session_claims(user))`, injetar no browser, navegar, observar rede (`/api/v1/...` status) e DOM.
- **Sempre** reverter grants temporários no banco e limpar `localStorage` ao final.

### Usuários de teste
- `rafael.casagrande@meconsulting.com.br` — **ADMIN** (acesso total; nunca restringir).
- `Michele Viana Costa` (`michele.viana@...`, perfil `ADMINISTRATIVO`) — usada para cenários de permissão mínima (grants temporários + revert).
- `Robert Ugolini` — perfil **CONSULTA** (tem `assets.view` legado → **vê** valores; **não** serve para testar ocultação de sensitive; usar um usuário com `assets.read` verbo-puro).

### Comportamentos esperados (exemplos validados)
- Colaboradores (só `employees.list/read/reference`): lista carrega (200), filtro Projeto oculto (sem `projects.list`), sem erro.
- Veículos (`vehicles.read` sem sensitive): lista sem coluna "Custo mensal", sem card de custo total; menu aparece; sem erro.
- Ativos (`assets.read` verbo-puro, sem sensitive): dashboard mostra contagens (Total 10 / Em uso 8 / Disponíveis 2) e **nenhum R$**; sem strip Financeiro; lista sem coluna Valor.

---

## 15. Lições aprendidas (para NÃO repetir caminhos já descartados)

1. **Reproduzir bugs via HTTP real**, não via harness Python isolado. O caso `MissingGreenlet` (§10.2) foi um **falso positivo** de harness (`flush()` sem `refresh` + rollback). Em request real, `lazy="joined"` + `expire_on_commit=False` carregam o relacionamento. **Não "corrigir" lazy loading no `create_vehicle` — não há bug lá.**
2. **`assets.view` (legado) ⇒ `assets.sensitive`**: ao testar ocultação de sensitive, usar usuário com **verbo `read`**, não perfil legado com `.view`.
3. **Ativação de sensitive é em código** (`_ACTIVATED_NEW_CODES`), não migration — o código já foi semeado nos perfis. As migrations 0092/0093 já colocaram os `*.sensitive` nos perfis; ativar é só expor na sessão/enforcement.
4. **CONSULTA** não concede a maioria dos `*.sensitive` no banco atual (apesar do que a migration 0095 sugere) — sempre **verificar no banco** antes de assumir presets.
5. **Grade única**: manter `UNMAPPED_CODES == []` como invariante. Colunas `access`/`execute` só via `CODE_PLACEMENT`.
6. **Export por recurso** é regra arquitetural: nunca usar `reports.export` para exportação de módulo específico.
7. **Recursos auxiliares** nunca podem derrubar a tela — sempre `useAuxiliaryResource` (ou `.catch`), nunca `Promise.all` com auxiliar sem tratamento.
8. **Deslocamento de competência do CAP não é `relativedelta`** — é o **piso `COMPANY_FINANCE_AUTOGEN_FIRST_COMPETENCE = date(2026,7,1)`**. Não procurar `+1`.
9. **Sempre validar o efetivo pré/pós** em migrations de permissão; migrations **aditivas** e idempotentes.
10. **Compatibilidade por grafo**: alterar semântica de códigos legados quebra usuários antigos — usar aliases que implicam os verbos novos.

---

## 16. Como continuar este projeto

### Recuperar contexto
1. Ler este documento inteiro.
2. Abrir e ler `app/core/permission_codes.py` (fonte única) — em especial `PERMISSION_IMPLIES`, `_ACTIVATED_NEW_CODES`, `PRESET_*`, `PERMISSION_SPECS`.
3. Abrir `frontend/src/permissions.ts` (espelho) e confirmar paridade BE↔FE (`ALL_PERMISSION_CODES`).
4. Rodar `.venv/bin/python -m pytest tests/test_permission_verbs.py tests/test_sensitive_axis.py -q` e `cd frontend && npx tsc --noEmit` para confirmar que o baseline está verde.
5. Conferir `alembic heads` (deve ser `0097_vehicles_export`).

### Como interpretar este documento
- §4 é o **contrato** das colunas da grade.
- §5 é o **comportamento oficial** por módulo (fonte de verdade funcional).
- §11 é a **regra de negócio oficial do CAP** (consolidada nesta conversa).
- §15 lista **soluções já descartadas** — não repropor.

### Princípios que DEVEM ser preservados
- **Permissão → comportamento**; nunca perfil → comportamento.
- **Migrations aditivas/idempotentes**; nunca destrutivas; validar efetivo pré/pós.
- **Neutralidade por código** e **ativação incremental** do eixo Sensitive.
- **Export por recurso** (`<recurso>.export`).
- **Recurso auxiliar nunca derruba a tela** (`useAuxiliaryResource`).
- **Grade única** com cobertura 100% (`UNMAPPED_CODES == []`).
- **`rafael.casagrande@meconsulting.com.br` sempre com acesso total.**
- **Sem bypass** por role/e-mail/`system.admin` em negócio.

### Primeira ação recomendada da próxima conversa
Retomar a **decisão da correção do CAP/Endividamento** (§10.1 + §11.7): confirmar com o usuário se o piso JUL/2026 deve permanecer (JUN não gera) ou se a geração deve ancorar no `renegotiation_first_payment_date`. Só então implementar. **Não** introduzir `relativedelta`.

---

*Fim do handoff. Este arquivo é a documentação oficial; mantê-lo atualizado a cada etapa concluída.*
