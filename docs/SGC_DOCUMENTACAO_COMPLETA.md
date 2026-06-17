# SGC — Sistema de Gestão Corporativa
## Documentação Técnica Completa — Auditoria

**Data da auditoria:** 2026-06-11  
**Versão analisada:** branch principal (`Gest-o-de-Projetos/`)  
**Auditor:** Claude Code (Sonnet 4.6)

---

## ÍNDICE

1. [Visão Geral do Sistema](#1-visão-geral-do-sistema)
2. [Arquitetura](#2-arquitetura)
3. [Estrutura de Diretórios](#3-estrutura-de-diretórios)
4. [Backend — Modelos de Dados](#4-backend--modelos-de-dados)
5. [Backend — Endpoints da API](#5-backend--endpoints-da-api)
6. [Backend — Serviços](#6-backend--serviços)
7. [Backend — Repositórios](#7-backend--repositórios)
8. [Autenticação e Autorização](#8-autenticação-e-autorização)
9. [Banco de Dados — Migrations](#9-banco-de-dados--migrations)
10. [Frontend — Estrutura](#10-frontend--estrutura)
11. [Variáveis de Ambiente](#11-variáveis-de-ambiente)
12. [Infraestrutura e Deploy](#12-infraestrutura-e-deploy)
13. [Scripts e Utilitários](#13-scripts-e-utilitários)
14. [Testes Automatizados](#14-testes-automatizados)
15. [Documentação Funcional dos Módulos](#15-documentação-funcional-dos-módulos)
16. [Análise de Segurança](#16-análise-de-segurança)
17. [Riscos Identificados](#17-riscos-identificados)
18. [Recomendações Priorizadas](#18-recomendações-priorizadas)
19. [Plano de Correção](#19-plano-de-correção)

---

## 1. VISÃO GERAL DO SISTEMA

O **SGC (Sistema de Gestão Corporativa)** é uma aplicação web fullstack destinada à gestão financeira e operacional de uma empresa de consultoria/engenharia. O sistema centraliza:

- Gestão de projetos e alocação de recursos
- Controle financeiro (contas a pagar, receber, faturamento)
- Gestão de ativos e EPIs
- Indicadores de performance (ROI operacional)
- Gestão de frota de veículos
- Controle de colaboradores CLT e PJ
- Endividamento e custos fixos corporativos
- Auditoria de todas as ações

### Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.x + FastAPI |
| ORM | SQLAlchemy 2.0 (async) |
| Banco de Dados | PostgreSQL (asyncpg driver) |
| Migrations | Alembic |
| Autenticação | JWT (python-jose, HS256) |
| Hashing de Senha | bcrypt (passlib, com suporte a argon2 e pbkdf2) |
| Frontend | React 18 + TypeScript + Vite |
| Estilização | Tailwind CSS |
| HTTP Client | Axios |
| Gráficos | Recharts |
| Roteamento | React Router v6 |
| Relatórios | openpyxl (Excel) + reportlab (PDF) |
| Deploy | Railway (backend + frontend como serviços separados) |

---

## 2. ARQUITETURA

### Diagrama de Camadas

```
┌─────────────────────────────────────────────────┐
│                   FRONTEND                       │
│   React 18 + TypeScript + Vite + Tailwind        │
│   Express.js (servidor estático de produção)     │
│   Deploy: Railway (porta dinâmica)               │
└──────────────────────┬──────────────────────────┘
                       │ HTTPS / REST JSON
                       │ Bearer JWT
                       ▼
┌─────────────────────────────────────────────────┐
│                   API FASTAPI                    │
│   app/main.py — CORSMiddleware, AuthStateMiddleware │
│   ForwardedProtoMiddleware                       │
│   /api/v1/ prefix                                │
│   22 módulos (routers)                           │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│               CAMADA DE DEPENDÊNCIAS             │
│   app/api/deps.py — get_current_user             │
│   require_permission, require_roles              │
│   get_current_workspace                          │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│               CAMADA DE SERVIÇOS                 │
│   app/services/*.py — lógica de negócio          │
│   AuthService, AuditService, ReportService, etc. │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│              CAMADA DE REPOSITÓRIOS              │
│   app/repositories/*.py — acesso a dados         │
│   UserRepository, ProjectRepository, etc.        │
└──────────────────────┬──────────────────────────┘
                       │ SQLAlchemy async ORM
                       ▼
┌─────────────────────────────────────────────────┐
│               PostgreSQL                         │
│   67 migrations / tabelas                        │
│   Schemas: public (produção) + cenários          │
└─────────────────────────────────────────────────┘
```

### Fluxo de Autenticação

```
1. POST /api/v1/auth/login {email, password}
2. AuthService.login():
   a. Busca usuário por email
   b. Verifica senha (bcrypt/argon2/pbkdf2 com rehash automático)
   c. Loga ação em audit_logs
   d. build_session_claims() — monta claims com roles, permissões, workspaces, projetos vinculados
3. create_access_token() — JWT HS256, expiry 24h (padrão)
4. Resposta: {access_token: "eyJ..."}
5. Frontend: armazena em localStorage["sgp_access_token"]
6. Interceptor Axios: adiciona header Authorization: Bearer <token> em toda requisição
7. Backend: HTTPBearer → decode_token() → UserRepository.get_with_roles() → request.state.user
```

### Fluxo de Autorização (RBAC)

```
Roles: ADMIN | GESTOR | CONSULTA
  │
  ├── ADMIN → preset: todas permissões (exceto EXPLICIT_GRANT_ONLY)
  ├── GESTOR → preset: leitura+escrita de quase tudo (sem users.manage em alguns casos)
  └── CONSULTA → preset: apenas leitura
  
Permissões granulares (user_permissions) sobrescrevem o preset da role.
EXPLICIT_GRANT_ONLY: invoices.reactivate, audit.export (nunca herdadas, apenas grant explícito)

Superusuário: email hardcoded "rafael.casagrande@meconsulting.com.br" OU APP_SUPERUSER_EMAILS
  → Acesso total a tudo, sem verificação de permissão
  
Workspaces: projects | finance | assets | indicators
  → Segmentação de interface (não de segurança — backend aplica permissões por endpoint)
```

---

## 3. ESTRUTURA DE DIRETÓRIOS

```
Gest-o-de-Projetos/
├── .env.example                  # Template de variáveis de ambiente
├── .env.local                    # Variáveis locais de desenvolvimento (NÃO commitar)
├── alembic.ini                   # Configuração do Alembic
├── alembic/
│   ├── env.py                    # Ambiente de migrations
│   ├── script.py.mako            # Template de migration
│   └── versions/                 # 67 migrations (0001–0067)
├── app/
│   ├── main.py                   # Ponto de entrada FastAPI, middlewares, startup
│   ├── api/
│   │   ├── deps.py               # Dependências: auth, permissões, workspace
│   │   ├── middleware.py         # ForwardedProtoMiddleware, AuthStateMiddleware
│   │   └── router.py             # Router principal, monta protected + admin
│   ├── core/
│   │   ├── bootstrap.py          # Seed admin (cria admin@admin.com se não existir)
│   │   ├── config.py             # Settings (Pydantic BaseSettings)
│   │   ├── permission_codes.py   # Constantes de permissões + presets por role
│   │   ├── run_migrations.py     # Roda alembic upgrade head no startup
│   │   ├── scenario.py           # Enum Scenario: PREVISTO | REALIZADO
│   │   ├── schema_guard.py       # Valida presença de colunas 'scenario' no boot
│   │   ├── security.py           # JWT, bcrypt, hash/verify senha
│   │   └── session_context.py    # Build de claims JWT, workspaces, permissões
│   ├── database/
│   │   ├── base.py               # Base declarativa + TimestampUUIDMixin
│   │   └── session.py            # Engine async + AsyncSessionLocal + get_db
│   ├── models/                   # 25 arquivos de modelos SQLAlchemy
│   ├── modules/                  # 22 módulos (cada um com router.py, schemas, service)
│   ├── repositories/             # 10 repositórios de acesso a dados
│   ├── schemas/                  # Pydantic schemas de entrada/saída
│   ├── services/                 # Serviços de lógica de negócio
│   └── utils/                    # Utilitários (money, dates, json, audit_diff)
├── docs/                         # Documentação interna
├── frontend/
│   ├── index.html
│   ├── server.js                 # Servidor Express para produção (Railway)
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx               # Roteamento principal React Router
│   │   ├── context/              # AuthContext, ScenarioContext, WorkspaceContext, SidebarContext
│   │   ├── hooks/                # usePermission, useConsultaReadOnly, useTableSort
│   │   ├── pages/                # 23 páginas
│   │   ├── services/             # 22 serviços de API (Axios)
│   │   ├── components/           # Componentes reutilizáveis
│   │   └── permissions.ts        # Função hasPermission (frontend)
├── manage.py                     # CLI: reset_db, promote_admin
├── Makefile                      # Targets: reset-db, reset-db-confirm
├── requirements.txt              # Dependências Python
├── scripts/
│   ├── backup_postgres.sh        # Script de backup PostgreSQL
│   ├── promote_user_admin.py     # Promove usuário a ADMIN
│   ├── promote_user_admin.sql    # SQL de promoção manual
│   ├── fix_local_db_ownership.sh
│   └── audit_payables_may_2026.sql
└── tests/                        # 11 arquivos de testes
```

---

## 4. BACKEND — MODELOS DE DADOS

### 4.1 Usuários e Autenticação

#### `users` (User)
| Campo | Tipo | Observações |
|-------|------|------------|
| id | UUID PK | |
| email | String(255) | unique, indexed |
| full_name | String(255) | |
| password_hash | String(255) | bcrypt/argon2/pbkdf2 |
| is_active | Boolean | default=True |
| deleted_at | DateTime(tz) | soft delete |
| created_at / updated_at | DateTime(tz) | auto |

#### `roles`
| Campo | Tipo |
|-------|------|
| id | UUID PK |
| name | String(50) unique — ADMIN, GESTOR, CONSULTA |
| description | String(255) nullable |

#### `user_roles` (UserRole)
| Campo | Tipo |
|-------|------|
| user_id | UUID FK → users |
| role_id | UUID FK → roles |
| UNIQUE | (user_id, role_id) |

#### `permissions`
| Campo | Tipo |
|-------|------|
| id | UUID PK |
| name | String(100) unique — código de permissão |
| description | String(255) |

#### `user_permissions`
| Campo | Tipo |
|-------|------|
| user_id | UUID FK → users |
| permission_id | UUID FK → permissions |

#### `project_users` (ProjectUser)
| Campo | Tipo |
|-------|------|
| project_id | UUID FK → projects |
| user_id | UUID FK → users |
| access_level | String(50) default="member" |

### 4.2 Projetos

#### `projects` (Project)
| Campo | Tipo |
|-------|------|
| id | UUID PK |
| name | String(255) |
| code | String(50) unique |
| description | Text nullable |
| is_active | Boolean default=True |
| deleted_at | DateTime(tz) nullable — soft delete |
| closed_at | DateTime(tz) nullable |
| cost_center | String(100) nullable |

### 4.3 Colaboradores

#### `employees` (Employee)
| Campo | Tipo | Observações |
|-------|------|------------|
| id | UUID PK | |
| name | String(255) | |
| type | String(10) | "CLT" ou "PJ" |
| is_active | Boolean | |
| salary_base | Numeric(14,2) | Salário base CLT |
| pix_key_type | String(32) | **DADO SENSÍVEL** |
| pix_key | String(255) | **DADO SENSÍVEL** |
| social_charge_rate | Numeric(6,4) | Encargos CLT |
| inss_rate / fgts_rate / ferias_rate | Numeric | CLT costs |
| pj_additional_cost | Numeric(14,2) | Custo extra PJ |
| clt_extra_monthly | Numeric(14,2) | Custo adicional mensal CLT |

#### `employee_allocations`
| Campo | Tipo |
|-------|------|
| employee_id | FK → employees |
| project_id | FK → projects |
| competencia | Date |
| allocation_pct | Numeric(5,2) — % de alocação |
| scenario | String — PREVISTO/REALIZADO |

### 4.4 Financeiro

#### `revenues` (Revenue)
| Campo | Tipo |
|-------|------|
| project_id | FK → projects |
| competencia | Date |
| amount | Numeric(14,2) |
| description | String(255) |
| scenario | String |
| retention_pct | Numeric(5,2) |

#### `invoices` (Invoice — Notas Fiscais internas)
| Campo | Tipo |
|-------|------|
| project_id | FK → projects |
| competencia | Date |
| nf_number | String |
| amount | Numeric(14,2) |
| status | EMITIDA/ANTECIPADA/FINALIZADA/CANCELADA |

#### `receivable_invoices` (NFs a receber)
| Campo | Tipo |
|-------|------|
| project_id | FK → projects (nullable) |
| nf_number | String |
| amount | Numeric(14,2) |
| net_value | Numeric(14,2) |
| status | EMITIDA/ANTECIPADA/RECEBIDA/CANCELADA |
| pdf_path | String — path relativo no disco |

#### `receivable_advance_batches` (Borderôs/Factoring)
| Campo | Tipo |
|-------|------|
| batch_number | String — número sequencial |
| operation_type | String — factoring/antecipação |
| bank | String |
| status | ABERTO/LIQUIDADO/CANCELADO |
| total_face_value | Numeric(14,2) |
| discount_rate | Numeric(6,4) |
| net_proceeds | Numeric(14,2) |

#### `payable_snapshots` (Snapshots mensais de obrigações)
| Campo | Tipo |
|-------|------|
| project_id | FK → projects (nullable) |
| competencia | Date |
| type | FORNECEDOR/FUNCIONARIO/FINANCIAL/ENDIVIDAMENTO |
| description | String |
| amount | Numeric(14,2) |
| amount_paid | Numeric(14,2) |
| status | PENDENTE/PAGO/PARCIAL/ANTECIPADO |
| cost_center | String |

#### `payable_payments` (Eventos de pagamento)
| Campo | Tipo |
|-------|------|
| snapshot_id | FK → payable_snapshots |
| amount_paid | Numeric(14,2) |
| paid_at | Date |
| payment_method | String |

### 4.5 Ativos e EPIs

#### `assets` (Ativo)
| Campo | Tipo |
|-------|------|
| asset_type | String — EQUIPMENT/EPI |
| code | String — gerado automaticamente |
| category | String |
| name | String(255) |
| status | AVAILABLE/IN_USE/MAINTENANCE/RETIRED |
| serial_number | String |
| purchase_value | Numeric(14,2) |
| tags | JSONB — array de strings |

#### `asset_assignments`
| Campo | Tipo |
|-------|------|
| asset_id | FK → assets |
| assignee_name | String(255) |
| project_id | FK nullable |
| assigned_at | Date |
| returned_at | Date nullable |

#### `asset_inspections`
| Campo | Tipo |
|-------|------|
| asset_id | FK → assets |
| inspection_date | Date |
| result | APPROVED/NEEDS_REPAIR/RETIRED |
| notes | Text |

#### `asset_attachments`
| Campo | Tipo |
|-------|------|
| asset_id | FK → assets |
| file_name | String |
| stored_path | String — caminho relativo no disco |
| content_type | String |
| size_bytes | Integer |

### 4.6 Frota

#### `vehicles` (Vehicle)
| Campo | Tipo |
|-------|------|
| plate | String(20) unique |
| model | String(255) |
| brand | String(100) |
| year | Integer |
| is_active | Boolean |
| monthly_fixed_cost | Numeric(14,2) |
| deleted_at | DateTime nullable |

#### `vehicle_usages`
| Campo | Tipo |
|-------|------|
| vehicle_id | FK → vehicles |
| project_id | FK → projects |
| competencia | Date |
| km_driven | Numeric(10,2) |
| scenario | String |

### 4.7 Financeiro Corporativo

#### `company_financial_items`
| Campo | Tipo |
|-------|------|
| type | ENDIVIDAMENTO/CUSTO_FIXO/EMPLOYEE |
| subtype | String — ex.: FINANCIAMENTO, LEASING |
| description | String |
| creditor | String |
| contract_value | Numeric(14,2) |
| interest_rate | Numeric(6,4) |
| monthly_required | Numeric(14,2) |
| is_active | Boolean |
| cost_center | String |

### 4.8 Auditoria

#### `audit_logs`
| Campo | Tipo |
|-------|------|
| user_id | FK → users (SET NULL on delete) |
| user_email | String(255) — desnormalizado |
| action | String(32) — login/create/update/delete |
| entity | String(80) — nome da entidade |
| entity_id | UUID |
| field_changes | JSONB — diff antes/depois |
| context | JSONB — metadados adicionais |
| ip_address | String(64) |
| user_agent | String(512) |

### 4.9 Outras Entidades

- **`settings`** — SystemSettings singleton: taxas de encargos, valores padrão
- **`alerts`** — Alertas por projeto/competência
- **`chart_of_accounts`** — Plano de contas
- **`cost_center_aliases`** — Aliases de centros de custo para importação
- **`payable_import_templates`** — Templates de mapeamento de colunas de importação Excel
- **`company_staff_costs`** — Custo de pessoal corporativo por competência
- **`employee_monthly_payroll_overrides`** — Override de salário por colaborador/mês
- **`receivable_manual_items`** — Itens manuais de contas a receber
- **`project_labors`**, **`project_vehicles`**, **`project_system_costs`**, **`project_operational_fixed`** — Custos operacionais por projeto/competência/cenário
- **`dashboard`** (KPI, ProjectResult) — Cache de indicadores calculados

---

## 5. BACKEND — ENDPOINTS DA API

Prefixo base: `/api/v1`

### 5.1 Autenticação (sem autenticação requerida)

| Método | Path | Descrição |
|--------|------|-----------|
| POST | `/auth/register` | Cadastro de novo usuário (ABERTO — sem autenticação) |
| POST | `/auth/login` | Login, retorna JWT |

### 5.2 Usuários (`/users`) — requer `users.manage`

| Método | Path | Permissão |
|--------|------|-----------|
| GET | `/users/me` | Qualquer autenticado |
| GET | `/users/` | users.manage |
| POST | `/users/` | users.manage |
| PATCH | `/users/{user_id}` | users.manage |
| DELETE | `/users/{user_id}` | users.manage |
| PATCH | `/users/{user_id}/activate` | users.manage |
| PATCH | `/users/{user_id}/deactivate` | users.manage |
| POST | `/users/{user_id}/reset-password` | users.manage |
| POST | `/users/roles` | users.manage |
| POST | `/users/{user_id}/roles` | users.manage |

### 5.3 Projetos (`/projects`) — requer permissões granulares

| Método | Path | Permissão |
|--------|------|-----------|
| GET | `/projects/` | projects.view |
| GET | `/projects/{project_id}` | projects.view |
| POST | `/projects/` | projects.create |
| PATCH | `/projects/{project_id}` | projects.edit |
| DELETE | `/projects/{project_id}` | projects.delete |
| PATCH | `/projects/{project_id}/activate` | projects.edit |
| PATCH | `/projects/{project_id}/deactivate` | projects.edit |
| GET | `/projects/allocations` | projects.view |
| POST | `/projects/{project_id}/allocations` | projects.edit |
| POST | `/projects/{project_id}/users/{user_id}` | users.manage |

### 5.4 Financeiro (`/financial`)

| Método | Path | Permissão |
|--------|------|-----------|
| GET | `/financial/receivables` | receivables.view |
| GET | `/financial/revenues` | receivables.view |
| POST/PATCH/DELETE | `/financial/revenues/*` | billing.view |
| GET | `/financial/invoices` | invoices.view |
| POST | `/financial/invoices` | invoices.edit |
| POST | `/financial/invoices/anticipations` | invoices.edit |
| GET | `/financial/dashboard` | (calculado) |
| GET | `/financial/payables` | payables.view |
| PATCH | `/financial/payables/{snapshot_id}` | costs.edit |
| POST | `/financial/payables/{snapshot_id}/payments` | costs.edit |
| POST | `/financial/payables/import/analyze` | costs.edit |
| POST | `/financial/payables/import/confirm` | costs.edit |

### 5.5 Contas a Pagar (`/payables`)

| Método | Path | Permissão |
|--------|------|-----------|
| GET | `/payables` | payables.view |
| POST | `/payables` | costs.edit |
| PATCH | `/payables/{payable_id}` | costs.edit |
| PATCH | `/payables/{payable_id}/pay` | costs.edit |
| DELETE | `/payables/{payable_id}` | costs.edit |

### 5.6 Notas Fiscais / Contas a Receber (`/invoices`)

| Método | Path | Permissão |
|--------|------|-----------|
| GET | `/invoices` | invoices.view |
| POST | `/invoices` | invoices.edit |
| PATCH | `/invoices/{id}` | invoices.edit |
| DELETE | `/invoices/{id}` | invoices.edit |
| POST | `/invoices/{id}/reactivate` | invoices.reactivate (EXPLICIT) |
| POST | `/invoices/{id}/anticipations` | invoices.edit |
| GET | `/invoices/{id}/pdf` | invoices.view |
| POST | `/invoices/{id}/pdf` | invoices.edit (upload) |
| GET | `/invoices/{id}/files` | invoices.view |
| GET | `/invoices/batches` | invoices.view |
| POST | `/invoices/batches` | invoices.edit |
| PATCH | `/invoices/batches/{id}` | invoices.edit |
| DELETE | `/invoices/batches/{id}` | invoices.edit |

### 5.7 Ativos (`/assets`)

| Método | Path | Permissão |
|--------|------|-----------|
| GET | `/assets` | assets.view |
| POST | `/assets` | assets.edit |
| GET | `/assets/{id}` | assets.view |
| PATCH | `/assets/{id}` | assets.edit |
| DELETE | `/assets/{id}` | assets.edit |
| POST | `/assets/{id}/assignments` | assets.edit |
| POST | `/assets/{id}/assignments/{aid}/return` | assets.edit |
| POST | `/assets/{id}/inspections` | assets.edit |
| POST | `/assets/{id}/attachments` | assets.edit (upload) |
| GET | `/assets/{id}/attachments/{fid}` | assets.view |
| GET | `/assets/epis` | assets.view |
| GET | `/assets/dashboard` | assets.view |

### 5.8 Outros Endpoints

| Módulo | Prefixo | Principais operações |
|--------|---------|---------------------|
| Empresa Financeira | `/company-finance` | CRUD itens, KPIs endividamento/custos fixos |
| Custos | `/costs` | Custos fixos de projeto, corporativos, alocações |
| Colaboradores | `/employees` | CRUD, upload de dados |
| Colaboradores externos | `/collaborators` | Gestão de PJs |
| Frota | `/vehicles` | CRUD veículos, usos |
| Dashboard | `/dashboard` | KPIs por projeto/global |
| Alertas | `/alerts` | Listagem de alertas |
| Configurações | `/settings` | SystemSettings |
| Relatórios | `/reports/generate` | POST — gera Excel/PDF |
| Admin | `/admin/audit/export` | GET — exporta logs (AUDIT_EXPORT explícito) |
| Indicadores | `/indicators` | ROI operacional |
| HR | `/hr` | Gestão de RH |
| Project Structure | `/projects` (shared) | Estrutura operacional do projeto |

### 5.9 Health Checks (sem autenticação)

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/health` | Retorna `{status: "ok"}` |
| GET | `/health/ready` | Executa `SELECT 1` no banco |

---

## 6. BACKEND — SERVIÇOS

| Serviço | Arquivo | Responsabilidade |
|---------|---------|-----------------|
| AuthService | `auth_service.py` | Login, registro, rehash de senhas, audit de login |
| AuditService | `audit_service.py` | Registro de todas ações no audit_logs com diff |
| AuditExportService | `audit_export_service.py` | Streaming de export de audit logs em .txt |
| ReportService | `report_service.py` | Geração de dados para relatórios |
| ReportExportService | `report_export.py` | Renderização Excel/PDF de relatórios |
| OperationalReportService | `operational_report_service.py` | Relatórios operacionais detalhados |
| PayableSnapshotService | `payable_snapshot_service.py` | Geração de snapshots mensais de obrigações |
| PayableImportService | `payable_import/` | Importação de planilhas Excel de payables |
| UsersService | `users_service.py` | CRUD usuários, atribuição de roles/permissões |

---

## 7. BACKEND — REPOSITÓRIOS

| Repositório | Arquivo | Tabelas Principais |
|-------------|---------|-------------------|
| UserRepository | `users.py` | users, roles, user_roles, user_permissions |
| ProjectRepository | `projects.py` | projects, project_users |
| FinancialRepository | `financial.py` | revenues, invoices, receivable_invoices |
| PayablesRepository | `costs.py` | payable_snapshots, payable_payments |
| EmployeeRepository | `employees.py` | employees, employee_allocations |
| FleetRepository | `fleet.py` | vehicles, vehicle_usages |
| CompanyStaffCostRepository | `company_staff_cost.py` | company_staff_costs |
| SettingsRepository | `settings_repository.py` | settings |
| PermissionsRepository | `permissions.py` | permissions, user_permissions |
| ProjectOperationalRepository | `project_operational.py` | project_labors, project_vehicles, etc. |

---

## 8. AUTENTICAÇÃO E AUTORIZAÇÃO

### 8.1 Mecanismo de Autenticação

- **Tipo:** JWT Bearer Token (HS256)
- **Armazenamento no cliente:** `localStorage["sgp_access_token"]`
- **Expiração:** 24 horas (hardcoded `60 * 24` minutos em `create_access_token`) — **ATENÇÃO:** o `ACCESS_TOKEN_EXPIRE_MINUTES` do config (padrão 60 min) **NÃO é usado** na chamada de `create_access_token`
- **Renovação:** não há refresh token — expirado, faz logout automático
- **Versão de sessão:** `SESSION_VERSION = 2` — invalida sessões antigas

### 8.2 Claims do JWT

```json
{
  "sub": "uuid-do-usuario",
  "session_version": 2,
  "workspace": "projects",
  "current_workspace": "projects",
  "default_workspace": "projects",
  "roles": ["ADMIN"],
  "permissions": ["system.admin", "projects.view", ...],
  "linked_projects": ["uuid1", "uuid2"],
  "exp": 1234567890
}
```

### 8.3 Sistema de Permissões (RBAC)

**Roles disponíveis:**
- `ADMIN` — acesso total (exceto permissões EXPLICIT_GRANT_ONLY)
- `GESTOR` — acesso de gestão completo (leitura + escrita da maioria)
- `CONSULTA` — apenas leitura

**Presets por role:** definidos em `permission_codes.py` como `PRESET_ADMIN`, `PRESET_GESTOR`, `PRESET_CONSULTA`

**Permissões EXPLICIT_GRANT_ONLY** (nunca herdadas por role):
- `invoices.reactivate` — reativar NF cancelada
- `audit.export` — exportar logs de auditoria

**Superusuário operacional** (bypassa todo RBAC):
- Email hardcoded: `rafael.casagrande@meconsulting.com.br`
- Configurável via `APP_SUPERUSER_EMAILS` no .env

### 8.4 Códigos de Permissão Completos

```
system.admin, system.all_projects
workspace.projects.access, workspace.finance.access
workspace.assets.access, workspace.indicators.access
dashboard.view, dashboard.director
indicators.view, indicators.director
projects.view, projects.view_list, projects.view_detail
projects.create, projects.edit, projects.delete
employees.view, employees.edit
vehicles.view, vehicles.edit
billing.view
payables.view, receivables.view
invoices.view, invoices.edit, invoices.reactivate (explicit)
debts.view, debts.edit
costs.view, costs.edit
settings.view, settings.edit
users.manage
reports.view, reports.export
audit.export (explicit)
alerts.view
company_finance.view, company_finance.edit
assets.view, assets.edit
```

---

## 9. BANCO DE DADOS — MIGRATIONS

Histórico completo de 67 migrations:

| # | Migration | O que criou/alterou |
|---|-----------|---------------------|
| 0001 | init | projects, users, roles, user_roles, project_users, revenues, invoices, employees, employee_allocations, vehicles, vehicle_usages, project_fixed_costs, corporate_costs, cost_allocations |
| 0002 | enterprise_financial | company_financial_items (endividamento/custos fixos) |
| 0003 | settings_and_project_operational | settings (singleton), project_labors, project_vehicles, project_system_costs, project_operational_fixed |
| 0004 | employee_clt_cost_fields | Campos de custo CLT (inss_rate, fgts_rate, ferias_rate, etc.) |
| 0005 | pj_additional_cost | Campo pj_additional_cost em employees |
| 0006 | project_labor_employee_only | Refatoração de project_labors para só employee |
| 0007 | labors_repair | Correção de colunas em project_labors |
| 0008 | labor_alloc_pct | Campo allocation_pct em project_labors |
| 0009 | fleet_project_vehicles | Relacionamento veículo/projeto |
| 0010 | revenue_retention | Campo retention_pct em revenues |
| 0011 | vehicle_monthly_cost | Campo monthly_fixed_cost em vehicles |
| 0012 | company_financial_items | Refinamentos em company_financial_items |
| 0013 | receivable_invoices | Tabela receivable_invoices (NFs a receber), pdf_path |
| 0014 | rbac_three_roles | Roles ADMIN/GESTOR/CONSULTA + seed inicial |
| 0015 | previsto_realizado_scenario | Coluna scenario (PREVISTO/REALIZADO) em todas tabelas de custos/receitas |
| 0016 | scenario_columns_ensure | Garante coluna scenario em tabelas pendentes |
| 0017 | proj_labor_costs | Campos de custo calculado em project_labors |
| 0018 | company_staff_costs | Tabela company_staff_costs |
| 0019 | project_vehicle_fuel_realized | Combustível realizado em project_vehicles |
| 0020 | permissions_rbac | Tabela permissions + user_permissions |
| 0021 | audit_logs_production | Tabela audit_logs com ip_address, user_agent, JSONB |
| 0022 | projects_view_granular | Permissões projects.view_list e projects.view_detail |
| 0023 | receivable_invoice_enhancements | Campos extras em receivable_invoices |
| 0024 | receivable_simplified | Simplificação do modelo de receivables |
| 0025 | payables_receivables_permissions | Permissões payables.view e receivables.view |
| 0026 | fix_alembic_version | Correção da tabela alembic_version |
| 0027 | chart_accounts_payables | Tabela chart_of_accounts |
| 0028 | payable_snapshots | Tabela payable_snapshots (snapshots imutáveis mensais) |
| 0029 | payable_snapshot_amount_paid | Campo amount_paid em payable_snapshots |
| 0030 | receivable_anticipation_details | Detalhes de antecipação em receivable_invoices |
| 0031 | receivable_status_recebida | Status RECEBIDA em receivable_invoices |
| 0032 | payable_snapshot_type_financial | Tipo FINANCIAL em payable_snapshots |
| 0033 | company_finance_debt_renegotiation | Campos de renegociação em company_financial_items |
| 0034 | invoice_anticipations | Tabela invoice_anticipations |
| 0035 | payable_snapshot_anticipation_unique_index | Índice único para antecipações |
| 0036 | receivable_invoice_files | Tabela receivable_invoice_files (múltiplos anexos) |
| 0037 | employee_pix_key | Campos pix_key_type e pix_key em employees |
| 0038 | company_finance_item_type_employee | Tipo EMPLOYEE em company_financial_items |
| 0039 | user_soft_delete | Campo deleted_at em users |
| 0040 | receivable_manual_items | Tabela receivable_manual_items |
| 0041 | project_lifecycle_soft_delete | Soft delete em projects |
| 0042 | project_closed_deleted_timestamptz | Campos closed_at/deleted_at com timezone |
| 0043 | vehicle_soft_delete | Soft delete em vehicles |
| 0044 | project_cost_center | Campo cost_center em projects |
| 0045 | normalize_revenue_competencia | Normalização de datas de competência |
| 0046 | receivable_anticipation_received_date | Data de recebimento de antecipação |
| 0047 | workspace_permissions | Permissões workspace.*.access |
| 0048 | payable_snapshot_type_endividamento | Tipo ENDIVIDAMENTO em payable_snapshots |
| 0049 | company_finance_structural_fields | Campos estruturais em company_financial_items |
| 0050 | company_finance_cost_center_structured | Campos de centro de custo estruturados |
| 0051 | assets_management_module | Tabelas assets, asset_assignments, asset_inspections, asset_attachments |
| 0052 | assets_refinements | Refinamentos no módulo de ativos |
| 0053 | asset_assignment_return_fields | Campos de devolução em asset_assignments |
| 0054 | asset_size_field | Campo size em assets |
| 0055 | asset_tags_field | Campo tags (JSONB) em assets |
| 0056 | employee_monthly_payroll_overrides | Tabela employee_monthly_payroll_overrides |
| 0057 | payable_import_templates | Tabela payable_import_templates |
| 0058 | cost_center_aliases | Tabela cost_center_aliases |
| 0059 | payable_payments | Tabela payable_payments (eventos de pagamento) |
| 0060 | fix_payable_snapshot_competence | Correção de datas de competência em snapshots |
| 0061 | payable_snapshot_competence_audit_note | Campo audit_note em payable_snapshots |
| 0062 | receivable_advance_batches | Tabela receivable_advance_batches (borderôs) |
| 0063 | advance_batch_operation_fields | Campos operacionais em advance_batches |
| 0064 | include_in_dashboard | Campo include_in_dashboard em entidades |
| 0065 | audit_export_permission | Permissão audit.export |
| 0066 | indicators_permissions | Permissões indicators.view e indicators.director |
| 0067 | company_finance_monthly_required | Campo monthly_required em company_financial_items |

---

## 10. FRONTEND — ESTRUTURA

### 10.1 Páginas (23 telas)

| Rota | Componente | Descrição |
|------|-----------|-----------|
| `/login` | Login.tsx | Autenticação |
| `/projects/dashboard` | Dashboard.tsx | Dashboard de projetos (KPIs) |
| `/projects/list` | Projects.tsx | Listagem de projetos |
| `/projects/list/:projectId` | ProjectDetail.tsx | Detalhe de projeto com abas |
| `/projects/reports` | Reports.tsx | Geração de relatórios |
| `/projects/users` | Users.tsx | Gestão de usuários |
| `/projects/employees` | Employees.tsx | Gestão de colaboradores |
| `/projects/vehicles` | Vehicles.tsx | Gestão de frota |
| `/projects/revenue` | Revenue.tsx | Receitas por projeto |
| `/finance/dashboard` | FinancialDashboard.tsx | Dashboard financeiro corporativo |
| `/finance/payables` | Payables.tsx | Contas a pagar |
| `/finance/receivables` | Receivables.tsx | Contas a receber |
| `/finance/invoices` | Invoices.tsx | Notas fiscais a receber |
| `/finance/advance-batches` | AdvanceBatches.tsx | Borderôs de antecipação |
| `/finance/debt` | CompanyDebt.tsx | Endividamento corporativo |
| `/finance/fixed-costs` | CompanyFixedCosts.tsx | Custos fixos corporativos |
| `/assets/dashboard` | AssetsDashboard.tsx | Dashboard de ativos |
| `/assets` | Assets.tsx | Listagem de ativos |
| `/assets/:assetId` | AssetDetail.tsx | Detalhe de ativo |
| `/epis` | Epis.tsx | EPIs |
| `/epis/:assetId` | AssetDetail.tsx | Detalhe de EPI |
| `/indicators/roi` | RoiOperacional.tsx | Indicador ROI operacional |
| `/settings` | Settings.tsx | Configurações do sistema |

### 10.2 Contextos React

| Contexto | Arquivo | Responsabilidade |
|----------|---------|-----------------|
| AuthContext | `AuthContext.tsx` | Usuário autenticado, login, logout, refreshUser |
| WorkspaceContext | `WorkspaceContext.tsx` | Workspace atual (projects/finance/assets/indicators) |
| ScenarioContext | `ScenarioContext.tsx` | Cenário selecionado (PREVISTO/REALIZADO) |
| SidebarContext | `SidebarContext.tsx` | Estado do sidebar (aberto/fechado) |

### 10.3 Hooks Customizados

| Hook | Arquivo | Responsabilidade |
|------|---------|-----------------|
| usePermission | `usePermission.ts` | Verifica permissões do usuário logado |
| useConsultaReadOnly | `useConsultaReadOnly.ts` | Retorna true se usuário é CONSULTA (read-only) |
| useGestorGlobalReadOnly | `useGestorGlobalReadOnly.ts` | Controle de escrita para gestores sem visão global |
| useTableSort | `useTableSort.ts` | Ordenação de tabelas |

### 10.4 Serviços de API (22 serviços)

Todos usam o cliente Axios configurado em `services/api.ts`:
- `api.ts` — cliente base com interceptors (auth header, 401 redirect, no-trailing-slash)
- `auth.ts` — login, logout, fetchMe
- `users.ts` — CRUD usuários, roles, permissões
- `projects.ts` — CRUD projetos, alocações
- `employees.ts` — colaboradores
- `vehicles.ts` — frota
- `financial.ts` — receitas, NFs internas, dashboard financeiro
- `payables.ts` — contas a pagar
- `receivables.ts` — NFs a receber, upload de PDFs
- `receivableAdvanceBatches.ts` — borderôs
- `companyFinance.ts` — endividamento/custos fixos
- `dashboard.ts` — dashboard de projetos
- `financialDashboard.ts` — dashboard financeiro
- `reports.ts` — geração de relatórios
- `assets.ts` — ativos
- `assetsDashboard.ts` — dashboard de ativos
- `settings.ts` — configurações
- `allocations.ts` — alocações de colaboradores
- `indicators.ts` — ROI operacional
- `audit.ts` — exportação de auditoria
- `projectStructure.ts` — estrutura operacional do projeto

### 10.5 Armazenamento no localStorage

```
sgp_access_token     — JWT de autenticação
sgp_workspace        — Workspace atual
sgp_permissions      — Lista de permissões (cache)
sgp_user             — Dados do usuário logado
sgp_user_context     — Contexto de sessão
sgp_linked_projects  — IDs de projetos vinculados
```

---

## 11. VARIÁVEIS DE AMBIENTE

### Backend (`.env` / `.env.local`)

| Variável | Padrão | Descrição | Obrigatório em Prod |
|----------|--------|-----------|---------------------|
| ENV | local | Ambiente (local/dev/production) | SIM |
| APP_NAME | SGP Backend | Nome da aplicação | Não |
| API_V1_PREFIX | /api/v1 | Prefixo da API | Não |
| **JWT_SECRET_KEY** | **change-me** | **Chave de assinatura JWT** | **CRÍTICO** |
| JWT_ALGORITHM | HS256 | Algoritmo JWT | Não |
| ACCESS_TOKEN_EXPIRE_MINUTES | 60 | Expiração (NÃO USADO no código!) | Não |
| AUTH_DEBUG | false | Loga tokens no console | Não — deve ser false |
| **CORS_ORIGINS** | (vazio) | Origens CORS permitidas | **CRÍTICO** |
| APP_SUPERUSER_EMAILS | (vazio) | E-mails superusuário | Recomendado |
| **DATABASE_URL** | postgresql+asyncpg://postgres:postgres@localhost:5432/sgp | URL do banco | **CRÍTICO** |
| DB_POOL_SIZE | 5 | Tamanho do pool | Recomendado |
| DB_MAX_OVERFLOW | 15 | Overflow do pool | Recomendado |
| DB_POOL_RECYCLE_SECONDS | 1800 | Recycle do pool | Não |
| RECEIVABLE_UPLOAD_DIR | var/receivable_uploads | Diretório de uploads de NFs | Prod: volume persistente |
| RECEIVABLE_PDF_MAX_BYTES | 5MB | Limite de tamanho de PDF | Não |
| ASSET_UPLOAD_DIR | var/asset_uploads | Diretório de uploads de ativos | Prod: volume persistente |
| ASSET_UPLOAD_MAX_BYTES | 15MB | Limite de upload de ativos | Não |

### Frontend (`.env`)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| VITE_API_BASE | http://localhost:8000/api/v1 | URL base da API (embutida no build) |

Em produção: `window.__SGP_API_BASE__` é injetado por `/sgp-runtime-config.js` via `server.js`

---

## 12. INFRAESTRUTURA E DEPLOY

### Plataforma: Railway

- **Backend:** container Python/Uvicorn
  - Startup: `run_alembic_upgrade()` + `seed_admin()` + `warn_if_scenario_schema_missing()`
  - X-Forwarded-Proto tratado por `ForwardedProtoMiddleware`
- **Frontend:** container Node.js com `server.js` (Express)
  - Serve arquivos estáticos do `dist/` gerado pelo Vite
  - Injeta URL da API em runtime via `/sgp-runtime-config.js`
  - Trust proxy configurado (`app.set("trust proxy", 1)`)
  - `x-powered-by` desabilitado

### Banco de Dados

- PostgreSQL (Railway ou local)
- Connection pooling: asyncpg, pool_pre_ping habilitado
- Migrations automáticas no startup (alembic upgrade head)

### Armazenamento de Arquivos

- **PDFs de NF:** armazenados localmente em `var/receivable_uploads/`
- **Attachments de Ativos:** armazenados em `var/asset_uploads/`
- **PROBLEMA:** Sem volume persistente configurado → perda de arquivos em redeploy

### Backup

- Script `scripts/backup_postgres.sh` — dump gzip via pg_dump
- Rotação: mantém últimos N arquivos (padrão 12)
- **PROBLEMA:** Backup manual/cron — não há automação documentada ou garantida

---

## 13. SCRIPTS E UTILITÁRIOS

| Script | Localização | Descrição |
|--------|-------------|-----------|
| backup_postgres.sh | scripts/ | Dump + rotação do banco |
| promote_user_admin.py | scripts/ | Promove usuário a ADMIN via ORM |
| promote_user_admin.sql | scripts/ | SQL manual de promoção de role |
| fix_local_db_ownership.sh | scripts/ | Corrige ownership no banco local |
| audit_payables_may_2026.sql | scripts/ | Query de auditoria de payables |
| manage.py | raiz | CLI: `reset_db`, `promote_admin` |
| Makefile | raiz | `make reset-db` (DESTRUTIVO — apaga todos dados) |

### Utilitários internos (`app/utils/`)

- `money.py` — formatação e operações monetárias
- `date_utils.py` — normalização de datas/competência
- `audit_diff.py` — geração de diffs estruturados para audit_logs
- `json_utils.py` — serialização JSON customizada
- `dashboard_inclusion.py` — lógica de inclusão no dashboard

---

## 14. TESTES AUTOMATIZADOS

| Arquivo | O que testa |
|---------|-------------|
| test_asset_epi_separation.py | Separação entre ativos e EPIs |
| test_cost_center_alias.py | Aliases de centro de custo |
| test_clt_monthly_payroll_override.py | Override de folha mensal CLT |
| test_indicators_roi.py | Cálculo de ROI operacional |
| test_advance_batch_payables.py | Borderôs e payables relacionados |
| test_payable_snapshot_competence.py | Competência de snapshots |
| test_asset_code_generation.py | Geração de código de ativo |
| test_payable_payments.py | Eventos de pagamento |
| test_company_finance_pendencias.py | Pendências de custos fixos/dívidas |
| test_advance_batch_number.py | Numeração de borderôs |
| test_money.py | Utilitários monetários |

**Cobertura:** Testes unitários de regras de negócio específicas. Não há testes de integração HTTP ou de autenticação.

---

## 15. DOCUMENTAÇÃO FUNCIONAL DOS MÓDULOS

### 15.1 Módulo: Projetos

**Objetivo:** Gestão do ciclo de vida de projetos (obras, contratos, iniciativas)

**Principais telas:** `/projects/list`, `/projects/list/:projectId`

**Fluxo de dados:**
```
Criar Projeto → Vincular Colaboradores/Veículos → Lançar Receitas/Custos 
→ Gerar Snapshots → Dashboard KPIs → Relatórios
```

**Regras de negócio:**
- Projetos têm ciclo: ativo → inativo → encerrado/deletado (soft delete)
- Acesso por projeto controlado via `project_users`
- Usuários ADMIN/GESTOR com `system.all_projects` enxergam todos os projetos
- Dados separados por cenário: PREVISTO vs REALIZADO

**Tabelas relacionadas:** projects, project_users, revenues, employee_allocations, vehicle_usages, project_labors, project_vehicles, project_system_costs, project_operational_fixed, project_fixed_costs

### 15.2 Módulo: Financeiro (Receitas e NFs internas)

**Objetivo:** Controle de receitas lançadas por projeto/competência e NFs internas

**Principais telas:** `/projects/revenue`

**Regras de negócio:**
- Receitas têm retention_pct (retenção)
- Cenários PREVISTO/REALIZADO independentes
- Faturamento = receitas vinculadas ao projeto

**Tabelas:** revenues, invoices, invoice_anticipations

### 15.3 Módulo: Contas a Receber (NFs a Receber)

**Objetivo:** Controle de Notas Fiscais emitidas para clientes, antecipações e borderôs

**Principais telas:** `/finance/receivables`, `/finance/invoices`, `/finance/advance-batches`

**Fluxo de dados:**
```
Emitir NF (EMITIDA) → Antecipar/Fatorar (ANTECIPADA) 
→ Receber (RECEBIDA) | Cancelar (CANCELADA)
```

**Regras de negócio:**
- NF pode ter múltiplos arquivos PDF anexados
- Reativação de NF cancelada requer permissão explícita `invoices.reactivate`
- Borderôs agrupam NFs para factoring com taxa de desconto e data de liquidação

**Tabelas:** receivable_invoices, receivable_invoice_files, receivable_advance_batches, receivable_manual_items

### 15.4 Módulo: Contas a Pagar

**Objetivo:** Controle de obrigações financeiras com snapshots mensais imutáveis

**Principais telas:** `/finance/payables`

**Fluxo de dados:**
```
Lançar Obrigação → Gerar Snapshot Mensal (imutável) 
→ Registrar Pagamentos → Status: PENDENTE/PARCIAL/PAGO
```

**Regras de negócio:**
- Snapshots são gerados automaticamente por competência
- Pagamentos são eventos que atualizam `amount_paid` no snapshot
- Tipos: FORNECEDOR, FUNCIONARIO, FINANCIAL, ENDIVIDAMENTO
- Importação via planilha Excel com mapeamento de colunas configurável
- Lock de banco (`pg_advisory_xact_lock`) para evitar snapshots duplicados

**Tabelas:** payables (legacy), payable_snapshots, payable_payments, payable_import_templates, cost_center_aliases

### 15.5 Módulo: Endividamento Corporativo

**Objetivo:** Controle do endividamento e compromissos financeiros da empresa

**Principais telas:** `/finance/debt`

**Regras de negócio:**
- Itens: financiamentos, leasing, empréstimos, etc.
- Campos: valor contratado, taxa de juros, parcela mensal obrigatória, vencimento
- KPIs: total devido, total atrasado, projeção mensal

**Tabelas:** company_financial_items (type=ENDIVIDAMENTO)

### 15.6 Módulo: Custos Fixos Corporativos

**Objetivo:** Controle de custos fixos operacionais da empresa (não alocados a projetos)

**Principais telas:** `/finance/fixed-costs`

**Regras de negócio:**
- Itens recorrentes mensais (aluguel, energia, etc.)
- Pendências identificadas por competência

**Tabelas:** company_financial_items (type=CUSTO_FIXO)

### 15.7 Módulo: Colaboradores

**Objetivo:** Cadastro e gestão de colaboradores CLT e PJ com cálculo de custos

**Principais telas:** `/projects/employees`

**Regras de negócio:**
- CLT: custo calculado com encargos (INSS, FGTS, férias)
- PJ: custo base + custo adicional PJ
- Alocação por projeto: % de tempo por competência e cenário
- Override de salário por mês específico disponível

**Dados sensíveis:** `pix_key`, `salary_base` — **ATENÇÃO: dados financeiros sensíveis**

**Tabelas:** employees, employee_allocations, employee_monthly_payroll_overrides

### 15.8 Módulo: Frota de Veículos

**Objetivo:** Controle de veículos e uso por projeto

**Principais telas:** `/projects/vehicles`

**Regras de negócio:**
- Soft delete de veículos
- Custo mensal fixo por veículo
- Uso por projeto: km rodados por competência/cenário

**Tabelas:** vehicles, vehicle_usages

### 15.9 Módulo: Gestão de Ativos e EPIs

**Objetivo:** Inventário de equipamentos e EPIs com histórico de atribuição e inspeções

**Principais telas:** `/assets`, `/epis`, `/assets/:id`

**Fluxo:**
```
Criar Ativo → Atribuir a Colaborador/Projeto → Inspecionar 
→ Devolver → AVAILABLE/IN_USE/MAINTENANCE/RETIRED
```

**Regras de negócio:**
- EPIs e equipamentos separados pelo campo `asset_type`
- Código automático gerado por categoria
- Atribuições com campos de devolução (data, condição)
- Anexos de arquivos por ativo
- Tags livres (JSONB)

**Tabelas:** assets, asset_assignments, asset_inspections, asset_attachments

### 15.10 Módulo: Dashboard de Projetos

**Objetivo:** KPIs consolidados por projeto e global

**Principais telas:** `/projects/dashboard`

**Indicadores exibidos:**
- Receita, Custo, Resultado, Margem
- Projeção mensal por projeto
- Ranking de projetos por resultado

**Tabelas:** dashboard (KPI, ProjectResult), revenues, employee_allocations, vehicle_usages

### 15.11 Módulo: Dashboard Financeiro

**Objetivo:** Visão financeira corporativa (receber × pagar × dívidas)

**Principais telas:** `/finance/dashboard`

**Indicadores:** NFs em aberto, recebimentos futuros, obrigações do mês, série temporal

### 15.12 Módulo: Indicadores (ROI)

**Objetivo:** Cálculo do ROI operacional da empresa

**Principais telas:** `/indicators/roi`

**Permissões especiais:** `indicators.director` para visão global

### 15.13 Módulo: Relatórios

**Objetivo:** Exportação de dados em Excel (.xlsx) e PDF

**Principais telas:** `/projects/reports`, `/finance/reports`

**Tipos de relatório disponíveis:**
- `project_summary` — Resumo de projeto por competência
- `company_summary` — Resumo da empresa
- `employees` — Relatório de colaboradores
- `vehicles` — Relatório de frota
- `invoices` — NFs internas
- `debt` — Endividamento
- `fixed_costs` — Custos fixos
- `users` — Usuários do sistema
- `revenues` — Receitas
- `dashboard` — Export do dashboard
- `payables_detailed` — Contas a pagar detalhado
- `receivables_detailed` — Contas a receber detalhado
- `invoices_detailed` — NFs detalhado
- `assets_inventory`, `assets_in_use`, `assets_inspections`, `assets_movements` — Ativos

### 15.14 Módulo: Usuários e Permissões

**Objetivo:** Gestão de usuários, roles e permissões

**Principais telas:** `/projects/users`

**Fluxo:**
```
Criar Usuário → Atribuir Role (ADMIN/GESTOR/CONSULTA) 
→ Vincular a Projetos → Permissões granulares opcionais
```

### 15.15 Módulo: Configurações

**Objetivo:** Parâmetros globais do sistema (taxas, valores padrão)

**Principais telas:** `/settings`

**Dados configuráveis:** taxas de encargos, consumo de combustível padrão, valores de referência

### 15.16 Módulo: Auditoria

**Objetivo:** Rastreabilidade de todas as ações do sistema

**Acesso:** exportação via `/admin/audit/export` (permissão `audit.export` — explicit only)

**Registra:** login, create, update, delete de todas entidades relevantes com diff JSON

---

## 16. ANÁLISE DE SEGURANÇA

### 16.1 Pontos Positivos

✅ **Autenticação JWT com bcrypt** — senhas armazenadas com bcrypt, suporte a rehash automático (migração de algoritmos legados)  
✅ **RBAC granular** — sistema de permissões bem estruturado com presets por role  
✅ **Permissões explicit-only** — `invoices.reactivate` e `audit.export` nunca herdadas automaticamente  
✅ **Audit log completo** — todas ações registradas com IP, user-agent e diff  
✅ **Session versioning** — invalidação de tokens em atualizações do sistema  
✅ **Soft delete** — usuários, projetos e veículos não são deletados fisicamente  
✅ **Proteção de path traversal em uploads** — uso de `.resolve()` e `relative_to()` para validar caminhos  
✅ **Validação de tipo de arquivo** — uploads de PDF verificam content_type  
✅ **Limites de tamanho** — PDFs (5MB) e attachments (15MB) com limites configuráveis  
✅ **CORS configurável** — com exigência de origens explícitas em produção  
✅ **Proxy headers tratados** — ForwardedProtoMiddleware evita HTTP downgrade  
✅ **Validação de JWT** — erros de JWTError e ExpiredSignatureError tratados adequadamente  
✅ **x-powered-by desabilitado** — no servidor Express do frontend  
✅ **SQL via ORM** — uso de SQLAlchemy parametrizado, sem SQL dinâmico com f-strings  
✅ **Sem credenciais reais em .env.local** — apenas valores padrão de desenvolvimento  

### 16.2 Vulnerabilidades Identificadas

#### CRÍTICO

**V-001: Endpoint de registro aberto sem autenticação**
- Localização: `POST /api/v1/auth/register`
- Problema: Qualquer pessoa com acesso à URL da API pode criar usuários no sistema. Não há autenticação, código de convite, ou limitação de taxa.
- Risco: Criação massiva de contas, enumeração de usuários registrados (via 409 Conflict)
- Evidência: `app/modules/auth/router.py:17` — sem `dependencies=[Depends(require_*)]`

**V-002: JWT com expiração de 24 horas (hardcoded, ignorando configuração)**
- Localização: `app/core/security.py:98` — `expires_delta: int = 60 * 24`
- Problema: `create_access_token` usa o valor padrão hardcoded de 24h. A variável `ACCESS_TOKEN_EXPIRE_MINUTES` definida no `.env` e no `config.py` **nunca é passada** para `create_access_token` em `auth_service.py:79`.
- Risco: Tokens roubados válidos por 24h sem possibilidade de revogação (não há blacklist/refresh token)
- Evidência: `app/services/auth_service.py:79` — `create_access_token(data={"sub": str(user.id), **claims})` sem `expires_delta`

**V-003: E-mail de superusuário hardcoded no código-fonte**
- Localização: `app/api/deps.py:81-84`
- Problema: `rafael.casagrande@meconsulting.com.br` está hardcoded como superusuário com acesso total, sem verificação de RBAC. Qualquer pessoa com acesso ao código tem essa informação.
- Risco: Vetor de ataque direcionado — atacante que comprometa essa conta tem acesso irrestrito; código exposto em repositórios compromete permanentemente
- Evidência: `_DEFAULT_SUPERUSER_EMAILS = frozenset({"rafael.casagrande@meconsulting.com.br"})`

**V-004: Credencial padrão de admin criada no bootstrap**
- Localização: `app/core/bootstrap.py:53-60`
- Problema: Se não houver nenhum usuário ADMIN, o sistema cria `admin@admin.com` com senha `123456` no startup
- Risco: Em caso de reset do banco ou nova instalação, conta padrão com credenciais conhecidas é criada automaticamente
- Evidência: `password_hash=hash_password("123456")`

#### ALTO

**V-005: Ausência de rate limiting**
- Localização: Toda a aplicação
- Problema: Não há limitação de taxa em nenhum endpoint, especialmente em `/auth/login` e `/auth/register`
- Risco: Ataques de força bruta a senhas, DDoS, enumeração de usuários

**V-006: JWT armazenado em localStorage (XSS)**
- Localização: `frontend/src/services/api.ts:59` — `localStorage.getItem(TOKEN_KEY)`
- Problema: JWT armazenado em `localStorage` é acessível via JavaScript, vulnerável a ataques XSS
- Risco: Script malicioso injetado pode roubar tokens de todos os usuários ativos

**V-007: Sem rotação/revogação de tokens JWT**
- Problema: Não há blacklist de tokens, refresh tokens ou mecanismo de logout com revogação server-side. Logout apaga apenas o token do localStorage.
- Risco: Token roubado permanece válido até a expiração (24h). Mudança de senha não invalida sessões ativas.

**V-008: Rota `/admin` fora do router protegido**
- Localização: `app/api/router.py:51` — `api_router.include_router(admin_router, prefix="/admin")`
- Problema: O `admin_router` é registrado **diretamente** em `api_router`, fora do bloco `protected`. A proteção depende exclusivamente do `require_permission(AUDIT_EXPORT)` dentro do endpoint. Um erro futuro pode resultar em endpoints admin sem autenticação.
- Risco: Inconsistência arquitetural — sem camada de proteção global no router

**V-009: Senha mínima de apenas 6 caracteres**
- Localização: `app/schemas/auth.py:13`, `app/schemas/users.py:44`
- Problema: `min_length=6` é insuficiente. Sem validação de complexidade (maiúsculas, números, símbolos).
- Risco: Senhas fracas facilmente comprometidas por força bruta ou dicionário

**V-010: Ausência de Content Security Policy (CSP)**
- Problema: O servidor Express do frontend não define headers de segurança HTTP (CSP, X-Frame-Options, X-Content-Type-Options, etc.)
- Risco: Vulnerabilidade a XSS, clickjacking, MIME sniffing

#### MÉDIO

**V-011: `AUTH_DEBUG` pode expor tokens em logs de produção**
- Localização: `app/api/deps.py:288` — `_debug_print(f"token (parcial): {token[:24]}...")`
- Problema: Se `AUTH_DEBUG=true` for acidentalmente ativado em produção, partes de tokens JWT são impressas nos logs
- Risco: Vazamento de tokens em logs de aplicação

**V-012: Dados bancários de colaboradores sem criptografia adicional**
- Localização: `app/models/employee.py:21-22`
- Problema: `pix_key` e `pix_key_type` armazenados como texto plano no banco
- Risco: Exposição de dados PIX em case de vazamento do banco

**V-013: Ausência de HTTPS enforcement no backend**
- Problema: Não há redirect HTTP→HTTPS ou HSTS no backend FastAPI
- Risco: Tokens podem trafegar sem criptografia em configurações incorretas

**V-014: Sem validação de tipo MIME além do Content-Type no upload**
- Localização: `app/modules/receivables/router.py:574`
- Problema: Valida apenas `content_type` enviado pelo cliente (facilmente falsificável). Não verifica o magic number/bytes do arquivo
- Risco: Upload de arquivos maliciosos com content_type falsificado

**V-015: Arquivos de upload armazenados localmente sem volume persistente garantido**
- Localização: `app/core/config.py:28` — `receivable_upload_dir: str = Field(default="var/receivable_uploads")`
- Problema: Sem volume persistente configurado em produção, uploads são perdidos em redeploy
- Risco: Perda de dados (PDFs de NFs, anexos de ativos)

---

## 17. RISCOS IDENTIFICADOS

### 17.1 Riscos de Segurança / Vazamento de Dados

| ID | Risco | Severidade | Probabilidade |
|----|-------|-----------|---------------|
| RS-001 | Registro aberto permite cadastro não autorizado | CRÍTICO | Alta |
| RS-002 | Credenciais admin padrão (admin@admin.com / 123456) | CRÍTICO | Média |
| RS-003 | Email de superusuário hardcoded exposto no código | CRÍTICO | Média |
| RS-004 | Token JWT de 24h sem revogação possível | ALTO | Média |
| RS-005 | JWT em localStorage vulnerável a XSS | ALTO | Baixa |
| RS-006 | Dados PIX de colaboradores sem criptografia | MÉDIO | Baixa |
| RS-007 | Sem CSP — vulnerável a injeção de scripts | MÉDIO | Baixa |
| RS-008 | AUTH_DEBUG pode vazar tokens em logs | MÉDIO | Baixa |

### 17.2 Riscos Financeiros

| ID | Risco | Severidade |
|----|-------|-----------|
| RF-001 | Conta admin padrão pode ser usada para manipular dados financeiros | CRÍTICO |
| RF-002 | Registro aberto + escalação de privilégios → acesso a dados financeiros sensíveis | ALTO |
| RF-003 | Sem rate limiting → ataques de força bruta à conta financeira | ALTO |
| RF-004 | Perda de PDFs de NF por ausência de volume persistente | MÉDIO |
| RF-005 | Token de 24h: janela longa para uso indevido após comprometimento | MÉDIO |

### 17.3 Riscos de Vazamento de Dados

| ID | Risco | Dado em Risco |
|----|-------|--------------|
| RD-001 | Registro aberto: enumerar usuários via 409 Conflict | Emails cadastrados |
| RD-002 | Dados PIX sem criptografia | Chaves PIX de colaboradores |
| RD-003 | Salary_base em texto plano no banco | Salários de colaboradores |
| RD-004 | Audit logs sem criptografia e com dados sensíveis em JSONB | Histórico completo de operações |
| RD-005 | JWT com payload de permissões e projetos decodificável (apenas assinado, não criptografado) | Estrutura organizacional |

### 17.4 Riscos de Manutenção

| ID | Risco | Impacto |
|----|-------|---------|
| RM-001 | `ACCESS_TOKEN_EXPIRE_MINUTES` ignorado no código | Confusão operacional, segurança falsa |
| RM-002 | Email hardcoded de superusuário — difícil de remover sem acesso ao código | Acoplamento indevido |
| RM-003 | 67 migrations sem downgrade (`down_revision` apenas) — rollback impossível | Operacional |
| RM-004 | Sem testes de integração HTTP ou de autenticação | Regressões silenciosas |
| RM-005 | `bcrypt<4.0.0` fixado por incompatibilidade com passlib — dívida técnica | Segurança futura |
| RM-006 | Uploads em disco local sem backup automatizado | Perda de dados |
| RM-007 | Dois sistemas de permissões sobrepostos (role presets + user_permissions) — lógica complexa | Bugs de autorização |
| RM-008 | `get_db` sem timeout de transação — queries longas bloqueiam pool | Performance/disponibilidade |

### 17.5 Riscos de Disponibilidade

| ID | Risco |
|----|-------|
| RD-001 | Sem rate limiting — DDoS/flooding de requests |
| RD-002 | Migrations automáticas no startup podem travar em banco com lock |
| RD-003 | Pool de conexões com configurações padrão (5 conexões) pode ser insuficiente em produção |

---

## 18. RECOMENDAÇÕES PRIORIZADAS

### PRIORIDADE 1 — CRÍTICO (corrigir imediatamente)

**R-001: Fechar endpoint de registro ou protegê-lo**
- Opção A (recomendada): Remover `POST /auth/register` e usar apenas criação de usuário via `POST /users/` (requer `users.manage`)
- Opção B: Adicionar autenticação ao register (require_permission ou token de convite)
- Impacto: Elimina cadastro não autorizado e enumeração de usuários

**R-002: Remover credencial admin padrão do bootstrap**
- Remover a criação automática de `admin@admin.com / 123456` do `bootstrap.py`
- Substituir por processo de configuração explícita (variáveis de ambiente ou CLI interativo)
- Impacto: Elimina conta de acesso universal conhecida publicamente

**R-003: Remover email hardcoded de superusuário**
- Mover `rafael.casagrande@meconsulting.com.br` para variável de ambiente `APP_SUPERUSER_EMAILS`
- Atualizar código para usar **apenas** a variável de ambiente, sem fallback hardcoded
- Impacto: Remove vetor de ataque direcionado e informação pessoal do código-fonte

**R-004: Corrigir expiração do token JWT**
- Passar `settings.access_token_expire_minutes` para `create_access_token` em `auth_service.py`
- Reduzir para 1h em produção (já é o valor padrão da config, mas não está sendo usado)
- Impacto: Elimina confusão, reduz janela de tokens comprometidos de 24h para 1h

### PRIORIDADE 2 — ALTO (corrigir em 30 dias)

**R-005: Implementar rate limiting**
- Adicionar SlowAPI ou similar no FastAPI
- Limites sugeridos: login (5/min), register (3/min), geral (100/min por IP)

**R-006: Adicionar headers de segurança HTTP no frontend**
- Configurar no `server.js`: CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, HSTS
- Biblioteca: `helmet` para Express

**R-007: Implementar mecanismo de invalidação de tokens**
- Opção A: Refresh token de curta duração + access token curto
- Opção B: Blacklist de tokens revogados em Redis/banco
- Mínimo: mudança de senha deve invalidar todas as sessões ativas

**R-008: Validar magic bytes de arquivos nos uploads**
- Verificar bytes iniciais do arquivo para confirmar que é PDF real
- Não confiar apenas no `content_type` do cliente

**R-009: Configurar volume persistente para uploads**
- Garantir que `RECEIVABLE_UPLOAD_DIR` e `ASSET_UPLOAD_DIR` apontam para volumes persistentes no Railway
- Documentar procedimento de backup desses diretórios

### PRIORIDADE 3 — MÉDIO (corrigir em 90 dias)

**R-010: Aumentar requisito mínimo de senha**
- Aumentar para min_length=8
- Adicionar validação de complexidade (ao menos 1 maiúscula, 1 número)

**R-011: Criptografar dados sensíveis de colaboradores**
- `pix_key`, `salary_base` — considerar criptografia em nível de aplicação

**R-012: Implementar backup automatizado**
- Configurar cron job no Railway para `backup_postgres.sh`
- Definir destino remoto (S3, GCS) para os backups

**R-013: Mover admin_router para dentro de protected**
- Arquitetura defensiva: toda rota deve herdar proteção do router pai

**R-014: Adicionar testes de integração para auth**
- Testar fluxos: login válido/inválido, permissões, 401/403

---

## 19. PLANO DE CORREÇÃO

### Fase 1 — Segurança Imediata (Sprint 1-2, ~1-2 semanas)

| Tarefa | Arquivo(s) | Estimativa |
|--------|-----------|-----------|
| 1.1 Remover/proteger endpoint `/auth/register` | `app/modules/auth/router.py` | 1h |
| 1.2 Remover email hardcoded de superusuário | `app/api/deps.py:81-84` | 30min |
| 1.3 Corrigir expiração do JWT | `app/services/auth_service.py:79` | 30min |
| 1.4 Remover credencial admin padrão do bootstrap | `app/core/bootstrap.py:53-60` | 2h |
| 1.5 Definir `JWT_SECRET_KEY` forte em produção | `.env` de produção (Railway) | 15min |
| 1.6 Verificar/definir `APP_SUPERUSER_EMAILS` em prod | `.env` de produção | 15min |
| **Total Fase 1** | | **~5 horas** |

### Fase 2 — Hardening (Sprint 3-4, ~2-4 semanas)

| Tarefa | Arquivo(s) | Estimativa |
|--------|-----------|-----------|
| 2.1 Implementar rate limiting (SlowAPI) | `app/main.py`, routers de auth | 4h |
| 2.2 Adicionar headers de segurança no frontend | `frontend/server.js` | 2h |
| 2.3 Configurar volumes persistentes no Railway | Deploy config | 2h |
| 2.4 Implementar backup automatizado com destino remoto | `scripts/backup_postgres.sh` + Railway cron | 4h |
| 2.5 Validação de magic bytes em uploads | `app/modules/receivables/router.py`, `app/modules/assets/router.py` | 3h |
| 2.6 Mover admin_router para dentro de protected | `app/api/router.py` | 30min |
| **Total Fase 2** | | **~16 horas** |

### Fase 3 — Melhoria Contínua (Sprint 5-8, ~1-2 meses)

| Tarefa | Estimativa |
|--------|-----------|
| 3.1 Implementar invalidação de tokens (logout server-side) | 8h |
| 3.2 Aumentar requisito mínimo de senha + validação de complexidade | 2h |
| 3.3 Criptografia de campos sensíveis (PIX, salário) | 8h |
| 3.4 Testes de integração para autenticação e RBAC | 16h |
| 3.5 Documentar procedimentos operacionais (deploy, backup, rotação de chaves) | 4h |
| 3.6 Atualizar bcrypt para ≥4.0 (quando passlib suportar) | 2h |
| **Total Fase 3** | **~40 horas** |

---

## SUMÁRIO EXECUTIVO

O SGC é um sistema funcional e bem estruturado, com arquitetura clara e código de qualidade razoável. O sistema possui autenticação JWT, RBAC granular, audit log completo e boa separação de camadas.

**Pontos fortes:** RBAC bem implementado, audit trail completo, código Python limpo e tipado, React moderno com TypeScript.

**Principais riscos a endereçar:**

1. **CRÍTICO — Registro público aberto:** Qualquer pessoa pode criar usuário no sistema
2. **CRÍTICO — Credenciais default:** `admin@admin.com / 123456` criadas automaticamente no bootstrap
3. **CRÍTICO — Email hardcoded:** Superusuário com email pessoal no código-fonte
4. **CRÍTICO — JWT ignorando configuração:** Token de 24h hardcoded, config de 60min ignorada
5. **ALTO — Sem rate limiting:** Vulnerável a força bruta e flooding

Com as correções da Fase 1 (~5 horas de trabalho), o sistema estará em nível de segurança aceitável para produção. As fases 2 e 3 elevam o padrão para produção robusta.

---

*Documento gerado automaticamente via análise estática do código-fonte. Não substitui um pentest profissional.*
