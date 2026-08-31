# SGC — Sistema de Gestão Corporativa
## Documentação Técnica Completa

**Estado documentado:** commit `21f4c07` (29/08/2026)
**Escopo:** o que existe implementado hoje. O histórico de mudanças fica em
[`CHANGELOG.md`](../CHANGELOG.md).

> Este documento foi gerado a partir do código-fonte: a lista de endpoints vem das rotas
> registradas no FastAPI, as tabelas vêm dos modelos SQLAlchemy e as permissões vêm de
> `app/core/permission_codes.py`. Ao alterar o sistema, regenere ou atualize as seções
> correspondentes — a versão anterior deste documento era de junho e ficou dois meses
> atrás do código, ao ponto de não mencionar módulos inteiros.

---

## Índice

1. [Visão geral](#1-visão-geral)
2. [Arquitetura e stack](#2-arquitetura-e-stack)
3. [Estrutura de diretórios](#3-estrutura-de-diretórios)
4. [Módulos funcionais](#4-módulos-funcionais)
5. [Autorização — o modelo de permissões](#5-autorização--o-modelo-de-permissões)
6. [Modelo de dados](#6-modelo-de-dados)
7. [API — endpoints por módulo](#7-api--endpoints-por-módulo)
8. [Frontend — telas e rotas](#8-frontend--telas-e-rotas)
9. [Armazenamento de arquivos](#9-armazenamento-de-arquivos)
10. [Variáveis de ambiente](#10-variáveis-de-ambiente)
11. [Banco de dados e migrations](#11-banco-de-dados-e-migrations)
12. [Testes automatizados](#12-testes-automatizados)
13. [Infraestrutura e deploy](#13-infraestrutura-e-deploy)
14. [Ambiente local](#14-ambiente-local)
15. [Documentos complementares](#15-documentos-complementares)

---

## 1. Visão geral

O SGC é uma aplicação web para a gestão financeira e operacional de uma empresa de
consultoria e engenharia. Ele cobre cinco áreas de trabalho (*workspaces*), cada uma com o
seu próprio menu e conjunto de permissões:

| Workspace | O que resolve |
|---|---|
| **Projetos** | Cadastro de projetos e contratos, estrutura de custos (mão de obra, veículos, sistemas, fixos), colaboradores, frota, faturamento e dashboard operacional |
| **Financeiro** | Contas a Pagar, Contas a Receber, Notas Fiscais, Antecipações de recebíveis, Endividamento e Custos Fixos da empresa |
| **Indicadores** | Dashboards executivos — ROI operacional e Evolução Financeira |
| **Gestão de Ativos** | Patrimônio, EPIs, entregas e devoluções, inspeções e vencimentos |
| **Jurídico** | Processos, pessoas, empresas e projetos do contencioso, com carga pela planilha oficial |

Dois conceitos atravessam o sistema inteiro e explicam boa parte das regras:

- **Competência** — o mês de referência de um custo ou lançamento. Quase todo dado
  financeiro é indexado por competência, e a folha de um mês é paga no Contas a Pagar do
  mês seguinte.
- **Centro de Custo** — o agrupamento que liga colaboradores, veículos e custos a um
  projeto ou a uma área administrativa (Administrativo, Financeiro, TI, Diretoria…). O
  vocabulário é único e centralizado: Centros Administrativos fixos mais os centros dos
  projetos ativos.

---

## 2. Arquitetura e stack

```
┌──────────────────────────┐        ┌──────────────────────────┐
│  Frontend (React + Vite) │  HTTPS │  Backend (FastAPI)       │
│  React 18 · TS · Tailwind│ ─────► │  Python · SQLAlchemy 2   │
│  ECharts · Recharts      │  JWT   │  Pydantic v2 · Alembic   │
└──────────────────────────┘        └───────────┬──────────────┘
                                                │ asyncpg
                                    ┌───────────▼──────────────┐
                                    │  PostgreSQL              │
                                    └──────────────────────────┘
                                    ┌──────────────────────────┐
                                    │  Volume persistente      │
                                    │  (anexos: NF, ativos,    │
                                    │   documentos de projeto) │
                                    └──────────────────────────┘
```

**Backend** — FastAPI ≥ 0.115, SQLAlchemy 2 (async, `asyncpg`), Pydantic v2 +
pydantic-settings, Alembic, python-jose (JWT), passlib/bcrypt, openpyxl (Excel) e
reportlab (PDF). Servido por uvicorn.

**Frontend** — React 18 com TypeScript, React Router 6, Axios, Tailwind. Gráficos em
Apache ECharts (padrão dos dashboards executivos) e Recharts (telas mais antigas). Em
produção é servido por um Express (`server.js`).

**Padrões que valem para o código todo:**

- Regra de negócio vive em `app/services/`; o router só autoriza, valida entrada e
  serializa saída. Consultas ficam em `app/repositories/`.
- Autorização por **permissão**, nunca por nome de perfil.
- Valores financeiros passam pelo eixo de **Dados Sensíveis**: ter acesso ao módulo não
  implica ver valores.
- Recursos auxiliares de tela (filtros, vocabulários) carregam por `useAuxiliaryResource`:
  se o usuário não tiver permissão, o controle some — a página não quebra.

---

## 3. Estrutura de diretórios

```
.
├── app/                      # Backend
│   ├── main.py               # App FastAPI, middlewares, startup (migrations + storage)
│   ├── api/                  # Dependências, middleware, registro de rotas, eixo sensível
│   ├── core/                 # Config, segurança, códigos de permissão, bootstrap
│   ├── models/               # Modelos SQLAlchemy (66 tabelas)
│   ├── schemas/              # Contratos Pydantic de entrada e saída
│   ├── modules/              # Um pacote por módulo, cada um com o seu router
│   ├── services/             # Regra de negócio (60 serviços)
│   ├── repositories/         # Consultas ao banco
│   ├── utils/                # Datas, dinheiro, ciclo de vida, storage, JSON
│   └── database/             # Sessão e base declarativa
├── alembic/versions/         # 119 migrations
├── frontend/src/
│   ├── pages/                # 30 telas
│   ├── components/           # Componentes reutilizáveis
│   ├── services/             # Clientes HTTP por módulo
│   ├── context/              # Auth, workspace, cenário, sidebar
│   ├── hooks/                # usePermission, useAuxiliaryResource, …
│   └── permissions.ts        # Espelho do grafo de permissões do backend
├── docs/                     # Esta documentação e os documentos por funcionalidade
├── scripts/                  # Utilitários operacionais e relatórios pontuais
├── tests/                    # 48 arquivos de teste
└── var/                      # Uploads em ambiente local
```

---

## 4. Módulos funcionais

### Projetos e estrutura de custos

Cadastro de projetos com contrato, aditivos (prazo e valor) e documentos anexados. Cada
projeto tem um **Centro de Custo** próprio, que é o que liga colaboradores e veículos a
ele.

A estrutura de custos do projeto tem quatro abas — **Mão de Obra**, **Veículos**,
**Sistemas** e **Custos Diversos** — sempre por competência e por cenário
(**Previsto** × **Realizado**). Recursos relevantes:

- **Inicializar Competência**: copia a estrutura de um mês para outro, incluindo os
  Componentes Variáveis; o que não puder ser copiado é informado na tela, nunca descartado
  em silêncio.
- **Exclusão em massa** por aba, com prévia que avisa quantos itens já têm pagamento
  lançado no Contas a Pagar.
- Tudo o que é lançado aqui alimenta o Contas a Pagar por sincronização (ver adiante).

### Colaboradores

Relação de cadastro com filtros de **Centro de Custo** e **Situação**, coluna com todos os
centros em que a pessoa atua e cards de Cadastrados, Situação e Vínculo CLT × PJ, mais a
distribuição por centro. O **custo mensal CLT** é calculado no cadastro (salário,
periculosidade, função dirigida, encargos das Configurações, VR e opcionais) e gravado no
colaborador; PJ tem cálculo próprio por hora ou valor fixo.

Recursos ligados ao colaborador:

- **Alocações** (`employee_assignments`): a pessoa pode atuar em vários contratos, com
  remuneração **independente** (padrão) ou por **rateio**. É a camada que destravou o
  multi-contrato — o teto de 100% só vale para o rateio.
- **Histórico de Centro de Custo**: o centro é temporal; competências anteriores preservam
  o centro que valia à época.
- **Override mensal da folha**: valores reais do holerite por competência.
- **Componentes Variáveis de Pagamento**: benefícios e ajudas de custo que seguem um
  pipeline único até o Contas a Pagar e o relatório de folha.

### Frota

Veículos com custo mensal, Centro de Custo (também temporal), usos e vínculo com projetos.

### Financeiro — Contas a Pagar

O CAP é montado a partir de *snapshots* por competência (`payable_snapshots`), gerados de
várias origens: mão de obra do projeto, veículos, sistemas, custos diversos, Custos Fixos
e Endividamento da empresa, componentes variáveis e despesas avulsas.

Invariantes que o código protege — e que já custaram defeitos em produção:

- Título **pago nunca tem o valor reescrito** pela sincronização.
- O casamento de um título existente **nunca é feito pelo nome** (o nome muda quando o
  cadastro é corrigido; usa-se a chave do lançamento e o rótulo do componente).
- Valor digitado na grade **sempre** vira título, mesmo que a vigência do cadastro não
  cubra a competência.
- A folha da competência M é paga no CAP de M+1.

### Financeiro — Contas a Receber, NFs e Antecipações

Notas fiscais com PDF anexado, competência, status e histórico. Sobre elas operam as
**Antecipações**: operações com instituições financeiras, com deságio e tarifa,
liquidação parcial ou multi-origem das NFs e um **ledger de repasse** append-only
(retiradas e movimentos, fora do Contas a Pagar).

### Financeiro corporativo — Custos Fixos e Endividamento

Itens da empresa com vigência (`start_date`/`end_date`), que geram títulos no CAP de forma
idempotente. Custos Fixos aceitam **vários lançamentos na mesma competência**;
Endividamento aceita um **Cronograma Financeiro personalizado**, que passa a ser a fonte
oficial das parcelas.

### Indicadores

Dashboards executivos em ECharts: **ROI Operacional** e **Evolução Financeira** — esta com
custo total do projeto e um modo alternativo que troca a origem do custo pelos títulos do
Contas a Pagar (visão da empresa inteira, porque a maior parte do CAP é corporativa).

### Gestão de Ativos e EPIs

Patrimônio com categorias, código gerado, anexos, entregas e devoluções por colaborador,
inspeções e vencimentos, além de um dashboard próprio. EPIs são tratados como uma faixa
separada dos demais ativos.

### Jurídico

Workspace fechado: processos (entidade principal), pessoas, empresas e projetos do
contencioso, dashboard, relatório próprio e importação pela **planilha oficial** — que
inclui e atualiza registros, mas nunca exclui. As permissões são por menu e não dependem
do módulo de Relatórios corporativo.

### Relatórios

Catálogo único com dois motores de exportação (Excel e PDF). Cada relatório exige, além do
acesso ao módulo de Relatórios, a permissão de leitura do **seu** módulo. Grupos
disponíveis: Financeiro, Projetos, Patrimônio, Jurídico e Administrativo (Colaboradores,
Folha de Pagamento, Frota, Usuários).

### Administração do sistema

Usuários, perfis administráveis (os perfis são presets de permissões guardados no banco),
Configurações (encargos, percentuais e tipos de componente de pagamento), log de auditoria
com exportação e o diagnóstico de arquivos ausentes no servidor.

### Módulos de apoio

`collaborators` e `hr` expõem colaboradores para seletores de outras telas com permissões
mais baixas; `cost-centers` serve o vocabulário único de Centros de Custo; `alerts` guarda
verificações operacionais (NFs a vencer, margem negativa) disparadas por administrador;
`dashboard` serve os resumos operacional e de diretoria.

---

## 5. Autorização — o modelo de permissões

Autorização é sempre por **permissão**, nunca por nome de perfil. Perfis (ADMIN, GESTOR,
FINANCEIRO, CONSULTA, ADMINISTRATIVO, RECURSOS HUMANOS, SUPER ADMIN) são apenas conjuntos
de permissões guardados em `role_permissions`, editáveis pela tela de Perfis.

**Modelo por verbos** — cada capacidade é `recurso.ação`, com as ações
`reference`, `list`, `read`, `create`, `update`, `delete` e `sensitive`. Um grafo de
implicação (`PERMISSION_IMPLIES`) deriva as permissões menores das maiores, e os códigos
legados (`recurso.view`, `recurso.edit`) continuam válidos implicando os novos — foi assim
que a migração pôde ser feita sem quebrar quem já tinha acesso.

**Eixo de Dados Sensíveis** — `recurso.sensitive` separa "acessar o módulo" de "ver
valores financeiros". Sem ele, os campos monetários voltam da API redigidos (nulos), não
apenas escondidos na tela.

**Workspaces** — `workspace.*.access` controla quais áreas aparecem no menu, e a navegação
inicial leva à primeira tela permitida do workspace.

Permissões ativas hoje, por recurso:

| Recurso | Ações |
|---|---|
| `alerts` | read, view |
| `assets` | create, delete, edit, list, read, reference, sensitive, update, view |
| `audit` | export |
| `billing` | create, delete, list, read, update, view |
| `company_finance` | create, delete, edit, list, read, update, view |
| `cost_center` | reference |
| `costs` | create, delete, edit, list, read, update, view |
| `dashboard` | director, read, view |
| `debts` | create, delete, edit, list, read, update, view |
| `employees` | create, delete, edit, export, list, read, reference, sensitive, update, view |
| `financial_dashboard` | read, sensitive |
| `indicators` | director, read, view |
| `invoices` | create, delete, edit, list, reactivate, read, update, view |
| `legal_cases` | create, delete, list, read, reference, sensitive, update |
| `legal_companies` | create, delete, list, read, update |
| `legal_dashboard` | read |
| `legal_imports` | create, list |
| `legal_persons` | create, delete, list, read, reference, sensitive, update |
| `legal_projects` | create, delete, list, read, update |
| `legal_reports` | export, read |
| `payable_snapshot` | reconcile |
| `payables` | create, delete, edit, list, read, update, view |
| `projects` | create, delete, documents.delete, documents.upload, documents.view, edit, list, read, reference, update, view, view_detail, view_list |
| `receivables` | create, delete, edit, list, read, update, view |
| `reports` | export, read, view |
| `settings` | edit, read, update, view |
| `system` | admin, all_projects |
| `users` | manage |
| `vehicles` | create, delete, edit, export, list, read, reference, sensitive, update, view |
| `workspace` | assets.access, finance.access, indicators.access, legal.access, projects.access |

---

## 6. Modelo de dados

66 tabelas, agrupadas por domínio:

**Alertas**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `alerts` | 9 | project_id, competencia, alert_type, severity, message, is_resolved |

**Antecipações**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `advance_institutions` | 7 | name, institution_type, operation_profile, is_active |
| `advance_repasse_ledger` | 15 | institution_id, direction, amount, source_type, withdrawal_purpose, source_batch_id, source_movement_id, occurred_at, de |
| `advance_settlement_events` | 13 | number, creation_source, status, institution_id, funding_source, payment_date, total_amount, invoice_count, observation, |
| `advance_settlement_movements` | 15 | batch_item_id, batch_id, invoice_id, institution_id, amount, funding_source, settled_at, event_id, observation, reversed |
| `invoice_anticipations` | 7 | invoice_id, anticipated_at, fee_amount, notes |

**Ativos e EPIs**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `asset_assignments` | 15 | asset_id, employee_id, delivered_by_employee_id, received_by_employee_id, delivery_date, return_date, returned_by_employ |
| `asset_attachments` | 10 | asset_id, file_name, file_type, stored_path, mime_type, uploaded_by_user_id, deleted_at |
| `asset_inspections` | 12 | asset_id, inspection_type, inspection_date, expiration_months, expiration_date, responsible_company, report_attachment_i |
| `assets` | 25 | asset_code, name, category, subcategory, tags, size, description, brand, model, serial_number, patrimony_tag, imei, ca_n |

**Auditoria**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `audit_logs` | 12 | user_id, user_email, action, entity, entity_id, field_changes, context, ip_address, user_agent |

**Centro de Custo**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `cost_center_aliases` | 7 | alias_name, alias_name_normalized, target_cost_center, created_by_user_id |

**Colaboradores**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `employee_allocations` | 11 | employee_id, project_id, scenario, start_date, end_date, allocation_percent, monthly_cost, hours_allocated |
| `employee_assignments` | 20 | employee_id, project_id, cost_center, allocation_type, role_title, salary_base, allowance, hours_per_month, employment_t |
| `employee_cost_center_history` | 7 | employee_id, cost_center, start_date, end_date |
| `employee_monthly_payroll_overrides` | 9 | employee_id, competence_month, net_salary_amount, vr_amount, vacation_advance_amount, notes |
| `employees` | 24 | full_name, email, role_title, employment_type, pix_key_type, pix_key, salary_base, additional_costs, total_cost, is_acti |

**Configurações**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `system_settings` | 17 | tax_rate, overhead_rate, anticipation_rate, clt_charges_rate, vehicle_light_cost, vehicle_pickup_cost, vehicle_sedan_cos |

**Contas a Pagar**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `payable_import_templates` | 7 | user_id, name, header_row, column_mapping |
| `payable_payments` | 10 | payable_snapshot_id, amount, payment_date, observation, created_by, reversed_at, reversal_reason |
| `payable_snapshot_generations` | 2 | month |
| `payable_snapshots` | 25 | month, type, ref_id, entry_id, project_id, origin, name, item_description, cost_center, category, amount_original, amoun |
| `payables` | 12 | description, supplier_name, amount, due_date, payment_date, competence, chart_account_id, cost_center, project_id |

**Contas a Receber e NFs**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `invoices` | 10 | project_id, competencia, amount, due_date, status, supplier, description |
| `receivable_advance_batch_items` | 8 | batch_id, invoice_id, invoice_amount, advance_basis, advanced_amount |
| `receivable_advance_batches` | 24 | sgc_number, batch_number, operation_type, operation_code, institution, institution_id, gross_amount, received_amount, ex |
| `receivable_invoice_anticipations` | 10 | invoice_id, institution, amount_received, amount_to_repay, received_date, due_date, include_in_dashboard |
| `receivable_invoice_files` | 8 | invoice_id, file_name, stored_path, content_type, size_bytes |
| `receivable_invoices` | 26 | project_id, nf_number, issue_date, due_days, due_date, competence_month, gross_amount, net_amount, client_name, notes, i |
| `receivable_manual_items` | 15 | workspace_id, descricao, cliente, numero_referencia, data_emissao, data_vencimento, valor_liquido, valor_recebido, data_ |

**Custos**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `chart_of_accounts` | 6 | code, name, type |
| `cost_allocations` | 8 | corporate_cost_id, project_id, competencia, allocated_amount_real, allocated_amount_calculated |

**Faturamento**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `revenues` | 10 | project_id, competencia, scenario, amount, description, status, has_retention |

**Financeiro Corporativo**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `company_financial_items` | 30 | tipo, item_type, employee_id, percentual, nome, item_description, valor_referencia, category, cost_center, cost_center_p |
| `company_financial_payments` | 9 | item_id, competencia, valor, due_date, descricao, schedule_seq |
| `company_staff_costs` | 7 | employee_id, competencia, scenario, valor |
| `corporate_costs` | 7 | competencia, name, amount_real, amount_calculated |

**Frota**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `vehicle_cost_center_history` | 7 | vehicle_id, cost_center, start_date, end_date |
| `vehicle_usages` | 10 | vehicle_id, project_id, scenario, usage_date, competencia, cost_amount, notes |
| `vehicles` | 14 | plate, model, description, vehicle_type, monthly_cost, driver_employee_id, cost_center, is_active, deleted_at, start_dat |

**Indicadores**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `kpis` | 7 | project_id, competencia, name, value |

**Jurídico**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `legal_cases` | 29 | case_number, jusbrasil_url, person_id, status, case_type, nature, uf, court, city, company, project, client, claimant_na |
| `legal_change_logs` | 11 | entity_type, entity_id, action, field, old_value, new_value, changed_by_id, changed_by_email |
| `legal_companies` | 7 | name, cnpj, notes, is_active |
| `legal_import_runs` | 18 | spreadsheet_name, panel_name, rows_read, people_new, people_updated, cases_new, cases_updated, unchanged, ignored, dupli |
| `legal_persons` | 15 | full_name, cpf, company, project, client, role, admission_date, termination_date, severance_amount, fgts_balance, notes, |
| `legal_projects` | 7 | name, client, notes, is_active |

**Pagamentos**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `payment_component_types` | 8 | name, code, description, is_active, display_order |
| `payment_variable_components` | 10 | type_id, employee_id, competencia, amount, note, project_labor_id, company_financial_item_id |

**Projetos**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `project_contract_additives` | 7 | project_id, additive_date, additive_value, additive_duration |
| `project_costs` | 9 | project_id, name, cost_type, value, cost_date, category |
| `project_documents` | 11 | project_id, category, title, original_filename, storage_path, uploaded_by, uploaded_at, is_active |
| `project_fixed_costs` | 9 | project_id, competencia, scenario, name, amount_real, amount_calculated |
| `project_labors` | 16 | project_id, competencia, scenario, employee_id, allocation_percentage, cost_salary_base, cost_additional_costs, cost_ext |
| `project_operational_fixed` | 8 | project_id, competencia, scenario, name, value |
| `project_results` | 9 | project_id, competencia, revenue_total, cost_total, profit, margin |
| `project_system_costs` | 8 | project_id, competencia, scenario, name, value |
| `project_users` | 6 | project_id, user_id, access_level |
| `project_vehicles` | 11 | project_id, competencia, scenario, vehicle_id, fuel_type, km_per_month, fuel_cost_realized, monthly_cost |
| `projects` | 20 | name, code, description, cost_center, contract_number, contract_value, contract_start_date, contract_duration, buyer_nam |

**Usuários e Permissões**

| Tabela | Colunas | Principais campos |
|---|---|---|
| `permissions` | 4 | name |
| `role_permissions` | 5 | role_id, permission_id |
| `roles` | 7 | name, description, is_system, is_active |
| `user_permissions` | 6 | user_id, permission_id, granted |
| `user_roles` | 5 | user_id, role_id |
| `users` | 8 | email, full_name, password_hash, is_active, deleted_at |

---

## 7. API — endpoints por módulo

Prefixo: `/api/v1`. Todos exigem autenticação por JWT, exceto `/auth/login` e os health
checks (`/health`, `/health/ready`, fora do prefixo).

#### `accounts-receivable` — 40 rotas

| Método | Caminho |
|---|---|
| DELETE | `/invoices/advance-batches/{batch_id}` |
| DELETE | `/invoices/advance-batches/{batch_id}/hard` |
| DELETE | `/invoices/advance-institutions/{institution_id}` |
| DELETE | `/invoices/advance-settlement-movements/{movement_id}` |
| DELETE | `/invoices/{invoice_id}` |
| DELETE | `/invoices/{invoice_id}/anticipations/{anticipation_id}` |
| DELETE | `/invoices/{invoice_id}/pdf` |
| GET | `/invoices` |
| GET | `/invoices/advance-batches` |
| GET | `/invoices/advance-batches/eligible-invoices` |
| GET | `/invoices/advance-batches/{batch_id}` |
| GET | `/invoices/advance-institutions` |
| GET | `/invoices/advance-repasse-ledger` |
| GET | `/invoices/advance-settlement-events` |
| GET | `/invoices/advance-settlement-events/{event_id}` |
| GET | `/invoices/advance-settlements` |
| GET | `/invoices/advance-settlements/history/batch/{batch_id}` |
| GET | `/invoices/advance-settlements/history/invoice/{invoice_id}` |
| GET | `/invoices/advance-settlements/kpis` |
| GET | `/invoices/advance-settlements/management-summary` |
| GET | `/invoices/advance-settlements/{batch_item_id}/timeline` |
| GET | `/invoices/kpis` |
| GET | `/invoices/{invoice_id}/files` |
| GET | `/invoices/{invoice_id}/files/{file_id}` |
| GET | `/invoices/{invoice_id}/pdf` |
| PATCH | `/invoices/advance-batches/{batch_id}` |
| PATCH | `/invoices/advance-institutions/{institution_id}` |
| PATCH | `/invoices/{invoice_id}` |
| PATCH | `/invoices/{invoice_id}/anticipations/{anticipation_id}` |
| POST | `/invoices` |
| POST | `/invoices/advance-batches` |
| POST | `/invoices/advance-batches/{batch_id}/confirm` |
| POST | `/invoices/advance-institutions` |
| POST | `/invoices/advance-repasse-ledger/withdrawals` |
| POST | `/invoices/advance-settlement-events` |
| POST | `/invoices/advance-settlements` |
| POST | `/invoices/{invoice_id}/anticipations` |
| POST | `/invoices/{invoice_id}/pdf` |
| POST | `/invoices/{invoice_id}/reactivate` |
| PUT | `/invoices/advance-batches/{batch_id}` |

#### `admin` — 2 rotas

| Método | Caminho |
|---|---|
| GET | `/admin/audit/export` |
| GET | `/admin/storage/missing-files` |

#### `alerts` — 4 rotas

| Método | Caminho |
|---|---|
| GET | `/alerts/` |
| PATCH | `/alerts/{alert_id}` |
| POST | `/alerts/checks/invoices-due` |
| POST | `/alerts/checks/negative-margin` |

#### `assets` — 18 rotas

| Método | Caminho |
|---|---|
| DELETE | `/assets/{asset_id}` |
| DELETE | `/assets/{asset_id}/assignments/{assignment_id}` |
| DELETE | `/assets/{asset_id}/assignments/{assignment_id}/return` |
| DELETE | `/assets/{asset_id}/attachments/{attachment_id}` |
| DELETE | `/assets/{asset_id}/inspections/{inspection_id}` |
| GET | `/assets` |
| GET | `/assets/dashboard` |
| GET | `/assets/epis` |
| GET | `/assets/meta/categories` |
| GET | `/assets/{asset_id}` |
| GET | `/assets/{asset_id}/attachments/{attachment_id}/download` |
| PATCH | `/assets/{asset_id}` |
| PATCH | `/assets/{asset_id}/assignments/{assignment_id}/return` |
| POST | `/assets` |
| POST | `/assets/{asset_id}/assignments` |
| POST | `/assets/{asset_id}/assignments/{assignment_id}/return` |
| POST | `/assets/{asset_id}/attachments` |
| POST | `/assets/{asset_id}/inspections` |

#### `auth` — 4 rotas

| Método | Caminho |
|---|---|
| POST | `/auth/login` |
| POST | `/auth/login/` |
| POST | `/auth/register` |
| POST | `/auth/register/` |

#### `collaborators` — 3 rotas

| Método | Caminho |
|---|---|
| GET | `/collaborators` |
| GET | `/collaborators/cost-centers` |
| GET | `/collaborators/search` |

#### `company-finance` — 15 rotas

| Método | Caminho |
|---|---|
| DELETE | `/company-finance/items/{item_id}` |
| GET | `/company-finance/chart-series` |
| GET | `/company-finance/items` |
| GET | `/company-finance/items/{item_id}/entries` |
| GET | `/company-finance/items/{item_id}/schedule` |
| GET | `/company-finance/kpis/custos-fixos` |
| GET | `/company-finance/kpis/endividamento` |
| GET | `/company-finance/pendencias` |
| GET | `/company-finance/pendencias/custos-fixos` |
| PATCH | `/company-finance/items/{item_id}` |
| POST | `/company-finance/items` |
| POST | `/company-finance/items/{item_id}/schedule/preview` |
| PUT | `/company-finance/items/{item_id}/entries` |
| PUT | `/company-finance/items/{item_id}/payments` |
| PUT | `/company-finance/items/{item_id}/schedule` |

#### `cost-centers` — 1 rotas

| Método | Caminho |
|---|---|
| GET | `/cost-centers/reference` |

#### `costs` — 4 rotas

| Método | Caminho |
|---|---|
| POST | `/costs/allocations` |
| POST | `/costs/corporate` |
| POST | `/costs/corporate/{corporate_cost_id}/auto-allocate` |
| POST | `/costs/project-fixed` |

#### `dashboard` — 5 rotas

| Método | Caminho |
|---|---|
| GET | `/dashboard/director/summary` |
| GET | `/dashboard/kpis` |
| GET | `/dashboard/project/{project_id}` |
| GET | `/dashboard/projects/{project_id}/summary` |
| GET | `/dashboard/summary` |

#### `employees` — 19 rotas

| Método | Caminho |
|---|---|
| DELETE | `/employees/staff-costs/{cost_id}` |
| DELETE | `/employees/{employee_id}` |
| GET | `/employees` |
| GET | `/employees/payroll` |
| GET | `/employees/staff-costs` |
| GET | `/employees/{employee_id}/assignments` |
| GET | `/employees/{employee_id}/monthly-payroll/{competence}` |
| PATCH | `/employees/staff-costs/{cost_id}` |
| PATCH | `/employees/{employee_id}` |
| PATCH | `/employees/{employee_id}/assignments/{assignment_id}` |
| POST | `/employees` |
| POST | `/employees/preview-clt-cost` |
| POST | `/employees/staff-costs` |
| POST | `/employees/{employee_id}/assignments` |
| POST | `/employees/{employee_id}/assignments/{assignment_id}/cancel` |
| POST | `/employees/{employee_id}/assignments/{assignment_id}/close` |
| POST | `/employees/{employee_id}/assignments/{assignment_id}/reopen` |
| POST | `/employees/{employee_id}/monthly-payroll/{competence}` |
| PUT | `/employees/{employee_id}/monthly-payroll/{competence}` |

#### `financial` — 33 rotas

| Método | Caminho |
|---|---|
| DELETE | `/financial/cost-center-aliases/{alias_id}` |
| DELETE | `/financial/payables/import/templates/{template_id}` |
| DELETE | `/financial/payables/{snapshot_id}` |
| DELETE | `/financial/receivables/manual/{item_id}` |
| DELETE | `/financial/revenues/{revenue_id}` |
| GET | `/financial/cost-center-aliases` |
| GET | `/financial/dashboard` |
| GET | `/financial/dashboard/breakdown` |
| GET | `/financial/dashboard/timeseries` |
| GET | `/financial/invoices` |
| GET | `/financial/payables` |
| GET | `/financial/payables/import/templates` |
| GET | `/financial/receivables` |
| GET | `/financial/revenues` |
| PATCH | `/financial/payables/{snapshot_id}` |
| PATCH | `/financial/receivables/manual/{item_id}` |
| PATCH | `/financial/revenues/{revenue_id}` |
| POST | `/financial/cost-center-aliases` |
| POST | `/financial/invoices` |
| POST | `/financial/invoices/anticipations` |
| POST | `/financial/payables` |
| POST | `/financial/payables/import/analyze` |
| POST | `/financial/payables/import/confirm` |
| POST | `/financial/payables/import/mapped/confirm` |
| POST | `/financial/payables/import/mapped/preview` |
| POST | `/financial/payables/import/mapped/scan-cost-centers` |
| POST | `/financial/payables/import/preview` |
| POST | `/financial/payables/import/templates` |
| POST | `/financial/payables/reconcile` |
| POST | `/financial/payables/{snapshot_id}/register-payment` |
| POST | `/financial/payables/{snapshot_id}/reverse-payment` |
| POST | `/financial/receivables/manual` |
| POST | `/financial/revenues` |

#### `hr` — 4 rotas

| Método | Caminho |
|---|---|
| DELETE | `/hr/employees/{employee_id}` |
| GET | `/hr/employees` |
| PATCH | `/hr/employees/{employee_id}` |
| POST | `/hr/employees` |

#### `indicators` — 7 rotas

| Método | Caminho |
|---|---|
| GET | `/indicators/catalog` |
| GET | `/indicators/evolucao-financeira` |
| GET | `/indicators/filtros` |
| GET | `/indicators/roi/consolidado` |
| GET | `/indicators/roi/evolucao` |
| GET | `/indicators/roi/operacional` |
| GET | `/indicators/roi/projetos/{project_id}` |

#### `legal` — 28 rotas

| Método | Caminho |
|---|---|
| GET | `/legal/cases` |
| GET | `/legal/cases/overview` |
| GET | `/legal/cases/{case_id}` |
| GET | `/legal/change-logs` |
| GET | `/legal/companies` |
| GET | `/legal/imports` |
| GET | `/legal/persons` |
| GET | `/legal/persons/facets` |
| GET | `/legal/persons/{person_id}` |
| GET | `/legal/projects` |
| PATCH | `/legal/cases/{case_id}` |
| PATCH | `/legal/companies/{company_id}` |
| PATCH | `/legal/persons/{person_id}` |
| PATCH | `/legal/projects/{project_id}` |
| POST | `/legal/cases` |
| POST | `/legal/cases/{case_id}/deactivate` |
| POST | `/legal/cases/{case_id}/restore` |
| POST | `/legal/companies` |
| POST | `/legal/companies/{company_id}/deactivate` |
| POST | `/legal/companies/{company_id}/restore` |
| POST | `/legal/imports/confirm` |
| POST | `/legal/imports/preview` |
| POST | `/legal/persons` |
| POST | `/legal/persons/{person_id}/deactivate` |
| POST | `/legal/persons/{person_id}/restore` |
| POST | `/legal/projects` |
| POST | `/legal/projects/{project_id}/deactivate` |
| POST | `/legal/projects/{project_id}/restore` |

#### `payables` — 5 rotas

| Método | Caminho |
|---|---|
| DELETE | `/payables/{payable_id}` |
| GET | `/payables` |
| PATCH | `/payables/{payable_id}` |
| PATCH | `/payables/{payable_id}/pay` |
| POST | `/payables` |

#### `payment-variable-components` — 6 rotas

| Método | Caminho |
|---|---|
| DELETE | `/payment-variable-components/{component_id}` |
| GET | `/payment-variable-components` |
| PATCH | `/payment-variable-components/{component_id}` |
| POST | `/payment-variable-components` |
| PUT | `/payment-variable-components/company-item/{item_id}` |
| PUT | `/payment-variable-components/project-labor/{labor_id}` |

#### `project-structure` — 20 rotas

| Método | Caminho |
|---|---|
| DELETE | `/projects/{project_id}/structure/fixed-operational/{fixed_id}` |
| DELETE | `/projects/{project_id}/structure/labors/{labor_id}` |
| DELETE | `/projects/{project_id}/structure/systems/{system_id}` |
| DELETE | `/projects/{project_id}/structure/vehicles/{vehicle_id}` |
| GET | `/projects/{project_id}/labor-details` |
| GET | `/projects/{project_id}/structure/fixed-operational` |
| GET | `/projects/{project_id}/structure/labors` |
| GET | `/projects/{project_id}/structure/systems` |
| GET | `/projects/{project_id}/structure/vehicles` |
| PATCH | `/projects/{project_id}/structure/fixed-operational/{fixed_id}` |
| PATCH | `/projects/{project_id}/structure/labors/{labor_id}` |
| PATCH | `/projects/{project_id}/structure/systems/{system_id}` |
| PATCH | `/projects/{project_id}/structure/vehicles/{vehicle_id}` |
| POST | `/projects/{project_id}/structure/bulk-delete` |
| POST | `/projects/{project_id}/structure/fixed-operational` |
| POST | `/projects/{project_id}/structure/initialize-competencia` |
| POST | `/projects/{project_id}/structure/labors` |
| POST | `/projects/{project_id}/structure/labors/copy-from-previous` |
| POST | `/projects/{project_id}/structure/systems` |
| POST | `/projects/{project_id}/structure/vehicles` |

#### `projects` — 16 rotas

| Método | Caminho |
|---|---|
| DELETE | `/projects/{project_id}` |
| DELETE | `/projects/{project_id}/additives/{additive_id}` |
| DELETE | `/projects/{project_id}/documents/{document_id}` |
| GET | `/projects/` |
| GET | `/projects/{project_id}` |
| GET | `/projects/{project_id}/additives` |
| GET | `/projects/{project_id}/documents` |
| GET | `/projects/{project_id}/documents/{document_id}/download` |
| PATCH | `/projects/{project_id}` |
| PATCH | `/projects/{project_id}/activate` |
| PATCH | `/projects/{project_id}/additives/{additive_id}` |
| PATCH | `/projects/{project_id}/deactivate` |
| POST | `/projects/` |
| POST | `/projects/{project_id}/additives` |
| POST | `/projects/{project_id}/documents` |
| POST | `/projects/{project_id}/users/{user_id}` |

#### `reports` — 1 rotas

| Método | Caminho |
|---|---|
| POST | `/reports/generate` |

#### `settings` — 6 rotas

| Método | Caminho |
|---|---|
| DELETE | `/settings/payment-component-types/{type_id}` |
| GET | `/settings` |
| GET | `/settings/payment-component-types` |
| PATCH | `/settings/payment-component-types/{type_id}` |
| POST | `/settings/payment-component-types` |
| PUT | `/settings` |

#### `users` — 13 rotas

| Método | Caminho |
|---|---|
| DELETE | `/users/roles/{role_id}` |
| DELETE | `/users/{user_id}` |
| GET | `/users/` |
| GET | `/users/me` |
| GET | `/users/roles` |
| PATCH | `/users/roles/{role_id}` |
| PATCH | `/users/{user_id}` |
| PATCH | `/users/{user_id}/activate` |
| PATCH | `/users/{user_id}/deactivate` |
| POST | `/users/` |
| POST | `/users/roles` |
| POST | `/users/{user_id}/reset-password` |
| POST | `/users/{user_id}/roles` |

#### `vehicles` — 6 rotas

| Método | Caminho |
|---|---|
| DELETE | `/vehicles/{vehicle_id}` |
| GET | `/vehicles` |
| GET | `/vehicles/active` |
| PATCH | `/vehicles/{vehicle_id}` |
| POST | `/vehicles` |
| POST | `/vehicles/usages` |

---

## 8. Frontend — telas e rotas

| Workspace | Rota | Tela |
|---|---|---|
| Projetos | `/projects/dashboard` | Dashboard operacional |
| Projetos | `/projects/list` · `/projects/list/:id` | Lista e detalhe do projeto (contrato, documentos, custos) |
| Projetos | `/projects/employees` | Colaboradores |
| Projetos | `/projects/vehicles` | Frota |
| Projetos | `/projects/revenue` | Faturamento |
| Projetos | `/projects/users` | Usuários |
| Projetos | `/projects/reports` | Relatórios |
| Financeiro | `/finance/dashboard` | Dashboard financeiro |
| Financeiro | `/finance/payables` | Contas a Pagar |
| Financeiro | `/finance/receivables` | Contas a Receber |
| Financeiro | `/finance/invoices` | Notas Fiscais |
| Financeiro | `/finance/advance-batches` | Antecipações — operações |
| Financeiro | `/finance/advance-institutions` | Instituições de antecipação |
| Financeiro | `/finance/debt` | Endividamento |
| Financeiro | `/finance/fixed-costs` | Custos Fixos |
| Financeiro | `/finance/reports` | Relatórios |
| Indicadores | `/indicators/roi` | ROI operacional |
| Indicadores | `/indicators/evolucao-financeira` | Evolução financeira |
| Ativos | `/assets/dashboard` · `/assets` · `/assets/:id` | Dashboard, lista e detalhe |
| Ativos | `/epis` · `/epis/:id` | EPIs |
| Jurídico | `/legal/dashboard` · `/legal/cases` · `/legal/persons` · `/legal/reports` · `/legal/admin` | Workspace jurídico |
| Sistema | `/settings` | Configurações, auditoria e arquivos ausentes |

Rotas antigas (`/projects`, `/invoices`, `/employees`…) redirecionam para os caminhos
atuais.

---

## 9. Armazenamento de arquivos

Três tipos de anexo são gravados em disco: **PDFs de NF**, **anexos de ativos** e
**documentos de projeto**. Todos derivam de uma raiz única:

- `STORAGE_ROOT` quando definida (em produção, o mount do volume persistente: `/data`);
- senão, a pasta que contém `RECEIVABLE_UPLOAD_DIR`;
- senão, os defaults relativos (`var/…`), usados em desenvolvimento.

Uma variável específica (`PROJECT_DOCUMENT_DIR`, `ASSET_UPLOAD_DIR`,
`RECEIVABLE_UPLOAD_DIR`) sempre vence a raiz. No startup o sistema registra em log os
diretórios em uso, alerta se em produção algum for relativo (portanto efêmero) e copia uma
única vez o que tenha sobrado nos diretórios legados.

Em Configurações há o diagnóstico **Arquivos ausentes no servidor**, que confronta os
registros do banco com o disco e lista o que precisa ser reenviado. O mesmo relatório está
em `GET /api/v1/admin/storage/missing-files` e em
`python -m scripts.relatorio_arquivos_ausentes`.

---

## 10. Variáveis de ambiente

**Backend** (`app/core/config.py`):

| Variável | Padrão | Descrição |
|---|---|---|
| `ENV` | `local` | `production` ativa validações extras de segurança |
| `DATABASE_URL` | — | **Crítica**. URL asyncpg do PostgreSQL |
| `JWT_SECRET_KEY` | `change-me` | **Crítica**. Em produção, mínimo de 32 caracteres |
| `JWT_ALGORITHM` · `ACCESS_TOKEN_EXPIRE_MINUTES` | `HS256` · `60` | Emissão do token |
| `CORS_ORIGINS` | vazio | **Crítica** em produção: domínios do frontend |
| `AUTH_DEBUG` | `false` | Proibido em produção |
| `APP_SUPERUSER_EMAILS` | vazio | Lista de emergência |
| `DB_POOL_SIZE` · `DB_MAX_OVERFLOW` · `DB_POOL_RECYCLE_SECONDS` | `5` · `15` · `1800` | Pool asyncpg |
| `STORAGE_ROOT` | vazio | **Crítica em produção**: raiz dos uploads (`/data`) |
| `RECEIVABLE_UPLOAD_DIR` · `ASSET_UPLOAD_DIR` · `PROJECT_DOCUMENT_DIR` | derivados da raiz | Diretórios por tipo de anexo |
| `RECEIVABLE_PDF_MAX_BYTES` · `ASSET_UPLOAD_MAX_BYTES` · `PROJECT_DOCUMENT_MAX_BYTES` | 5 MB · 15 MB · 25 MB | Limites de upload |

**Frontend**: `VITE_API_BASE` (ex.: `https://…/api/v1`), lida **em tempo de build**.

---

## 11. Banco de dados e migrations

PostgreSQL, com 119 migrations Alembic (`0001` … `0119`). O `upgrade head` roda
automaticamente no startup do backend, o que faz o deploy aplicar o schema sem passo
manual.

Migrations recentes que vale conhecer:

| Revisão | O que faz |
|---|---|
| `0119` | `payable_snapshots.name` e `.item_description` → TEXT (nota longa derrubava a geração do mês) |
| `0103` | Flag do Cronograma Financeiro do Endividamento |
| `0101`/`0102` | Múltiplos lançamentos por competência em Custos Fixos (`entry_id`) |
| `0100` | Componentes Variáveis de Pagamento |
| `0098` | Dashboard Financeiro como recurso próprio (não vaza valores por `billing.read`) |
| `0092` | Modelo de permissões por verbos (aditiva) |
| `0091` | Perfis administráveis (`role_permissions`) |
| `0090` | Isolamento de permissões por módulo |

---

## 12. Testes automatizados

48 arquivos em `tests/`, majoritariamente de regressão: cada defeito encontrado em
produção vira um teste que trava o comportamento. As frentes com mais cobertura são
Contas a Pagar e competências, antecipações e repasse, permissões e eixo sensível, Centro
de Custo (incluindo o histórico temporal) e o módulo Jurídico.

```bash
.venv/bin/python -m pytest --ignore=tests/test_roles.py -q
```

> **Atenção**: `tests/test_roles.py` escreve no banco de desenvolvimento (que é um clone
> de produção) e já renomeou perfis. Rode a suíte com o `--ignore` acima.

Dois testes falham hoje por questões pré-existentes de ambiente
(`test_advance_batch_payables` e `test_users_permission_grid`), sem relação com o código
de produção.

Há ainda uma varredura estática (`test_endpoint_names_resolve.py`) que percorre **todos**
os handlers procurando nomes usados fora de escopo — ela nasceu de um `NameError` que só
aparecia depois do `commit`, e já encontrou um segundo caso em outro módulo.

---

## 13. Infraestrutura e deploy

Hospedagem no **Railway**, com três serviços: PostgreSQL, backend e frontend, cada um
implantado a partir do GitHub. O backend tem um **volume persistente montado em `/data`**,
onde ficam todos os anexos.

O deploy é disparado pelo push na `main`. No startup o backend executa
`alembic upgrade head`, verifica o schema de cenários, garante o usuário administrador e
registra os diretórios de armazenamento.

Backups do PostgreSQL: `scripts/backup_postgres.sh` (ver
[`docs/operacao-e-backups.md`](operacao-e-backups.md)).

---

## 14. Ambiente local

```bash
# Backend (porta 8000)
.venv/bin/python -m uvicorn app.main:app --reload

# Frontend (porta 3000)
npm run dev --prefix frontend
```

O banco local é um **clone de produção** (`sgp_local_test`), sem qualquer conexão com o
Railway — o procedimento está em
[`docs/LOCAL_PRODUCTION_CLONE_SETUP.md`](LOCAL_PRODUCTION_CLONE_SETUP.md). Os arquivos de
anexo **não** vêm no clone: os registros existem no banco, mas o download falha com
"arquivo não encontrado", o que é esperado fora de produção.

---

## 15. Documentos complementares

| Documento | Assunto |
|---|---|
| [`CHANGELOG.md`](../CHANGELOG.md) | Histórico de mudanças por mês |
| [`SGC_HANDOFF_TECNICO.md`](../SGC_HANDOFF_TECNICO.md) | Migração do modelo de permissões |
| [`SGC_DADOS_SENSIVEIS_HANDOFF.md`](../SGC_DADOS_SENSIVEIS_HANDOFF.md) | Eixo de Dados Sensíveis |
| [`PERMISSOES_MODELO_VERBOS.md`](PERMISSOES_MODELO_VERBOS.md) | Modelo por verbos e rollout |
| [`ETAPA0_LIQUIDACAO_ANTECIPACOES.md`](ETAPA0_LIQUIDACAO_ANTECIPACOES.md) | Liquidação de NFs e ledger de repasse |
| [`ETAPA0_EDICAO_ANTECIPACOES.md`](ETAPA0_EDICAO_ANTECIPACOES.md) | Edição de operações de antecipação |
| [`ETAPA0_CRONOGRAMA_ENDIVIDAMENTO.md`](ETAPA0_CRONOGRAMA_ENDIVIDAMENTO.md) | Cronograma Financeiro personalizado |
| [`CUSTOS_FIXOS_MULTIPLOS_LANCAMENTOS.md`](CUSTOS_FIXOS_MULTIPLOS_LANCAMENTOS.md) | Vários lançamentos por competência |
| [`JURIDICO_IMPORTACAO_PLANILHA.md`](JURIDICO_IMPORTACAO_PLANILHA.md) · [`JURIDICO_RUNBOOK_DEPLOY.md`](JURIDICO_RUNBOOK_DEPLOY.md) | Workspace Jurídico |
| [`SGC_AUDITORIA_SEGURANCA_PRIVACIDADE_FINANCEIRO.md`](SGC_AUDITORIA_SEGURANCA_PRIVACIDADE_FINANCEIRO.md) | Auditoria de segurança e privacidade |
| [`operacao-e-backups.md`](operacao-e-backups.md) | Rotina de backup |
| [`LOCAL_PRODUCTION_CLONE_SETUP.md`](LOCAL_PRODUCTION_CLONE_SETUP.md) | Clone local de produção |

Documentos anteriores mantidos por referência histórica, já desatualizados em relação ao
código: `SGC_ARQUITETURA_PERMISSOES_FUTURAS.md`, `SGC_MATRIZ_PERMISSOES_DEFINITIVA.md` e
`SGC_RELATORIO_EXECUTIVO.md` (todos de 12/06/2026).
