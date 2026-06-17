# SGC — Auditoria de Segurança, Privacidade (LGPD) e Riscos Financeiros
## Fases 4, 5 e 6

**Data:** 2026-06-11  
**Escopo:** análise estática profunda do código-fonte (`Gest-o-de-Projetos/`)  
**Complementa:** [SGC_DOCUMENTACAO_COMPLETA.md](SGC_DOCUMENTACAO_COMPLETA.md)

> ⚠️ Nenhuma alteração de código foi feita. Esta é uma fase exclusivamente de análise. As referências usam `arquivo:linha` para rastreabilidade.

---

## SUMÁRIO DOS ACHADOS

| ID | Categoria | Severidade | Título |
|----|-----------|-----------|--------|
| **F4-01** | AuthZ / Exposição | 🔴 CRÍTICO | Cadeia: registro aberto → preset CONSULTA → leitura de TODO o financeiro |
| **F4-02** | AuthZ / IDOR | 🔴 CRÍTICO | `/payables` sem nenhuma verificação de escopo de projeto |
| **F4-03** | AuthZ / IDOR | 🟠 ALTO | `/financial/receivables?project_id=` ignora escopo quando project_id explícito |
| **F4-04** | Privilege Escalation | 🟠 ALTO | `users.manage` permite auto-promoção a ADMIN |
| **F4-05** | AuthZ (design) | 🟠 ALTO | Dados financeiros são globais a qualquer usuário com `*.view` de finanças |
| **F4-06** | Mass Assignment | 🟠 ALTO | `PATCH /payables/{id}` permite reatribuir `project_id` livremente |
| **F4-07** | Auth | 🔴 CRÍTICO | JWT 24h hardcoded (config ignorada) — confirmado |
| **F4-08** | Infra / Hardcoded | 🔴 CRÍTICO | E-mail superusuário + admin default — confirmado |
| **F4-09** | API / Info Leak | 🟡 MÉDIO | Endpoint de payables retorna stacktrace/contexto interno em erro 500 |
| **F4-10** | Upload | 🟡 MÉDIO | Validação de upload por `content_type` (falsificável), sem magic bytes |
| **F4-11** | Frontend | 🟠 ALTO | JWT em localStorage + permissões/projetos em claims decodificáveis |
| **F5-01** | LGPD | 🟠 ALTO | Dados pessoais sensíveis (PIX, salário) sem criptografia nem minimização |
| **F5-02** | LGPD | 🟡 MÉDIO | Audit logs retêm dados pessoais indefinidamente (sem política de retenção) |
| **F5-03** | LGPD | 🟡 MÉDIO | Ausência de base legal/consentimento e de mecanismo de eliminação (direito do titular) |
| **F6-01** | Financeiro | 🟠 ALTO | Agregações financeiras usando `float` (risco de imprecisão monetária) |
| **F6-02** | Financeiro | 🟡 MÉDIO | Exclusões físicas (hard delete) em payables/invoices sem reversão |
| **F6-03** | Financeiro | 🟡 MÉDIO | Prevenção de duplicidade depende de constraints frágeis (description no unique key) |

---

# FASE 4 — AUDITORIA DE SEGURANÇA

## 4.1 AUTENTICAÇÃO

### F4-07 — JWT de 24h hardcoded, ignorando configuração (🔴 CRÍTICO)
**Confirmado por leitura de código.**
- `app/core/security.py:98` — `def create_access_token(data: dict, expires_delta: int = 60 * 24)` → padrão de **1440 minutos (24h)**.
- `app/services/auth_service.py:79` — `create_access_token(data={"sub": str(user.id), **claims})` chama **sem** `expires_delta`.
- `app/core/config.py:16` — `access_token_expire_minutes` (padrão 60) **nunca é referenciado** no fluxo de login.

**Impacto:** Token roubado é válido por 24h. Não há refresh token, blacklist ou revogação. Logout apenas remove o token do `localStorage` (client-side). Troca de senha **não** invalida sessões ativas (não há verificação de timestamp de senha no token).

### Outros pontos de autenticação
- ✅ Senha com bcrypt + rehash automático de algoritmos legados (`security.py`).
- ✅ `session_version=2` invalida tokens antigos globalmente.
- ⚠️ Senha mínima de 6 caracteres sem complexidade (`schemas/auth.py:13`, `schemas/users.py`).
- ⚠️ `AUTH_DEBUG=true` imprime trechos do token no console (`deps.py:288`). Bloqueado em produção pelo validator de config, mas o código de log permanece.

## 4.2 AUTORIZAÇÃO

### F4-01 — Cadeia de exposição: registro aberto → leitura total de finanças (🔴 CRÍTICO)
**A vulnerabilidade mais grave encontrada.** Composição de três fatos verificados:

1. `POST /api/v1/auth/register` é público (`app/modules/auth/router.py:15-19`, sem `dependencies`). Cria usuário com `is_active=True` e **nenhuma role** (`auth_service.py:register`).
2. Quando o usuário não tem role nem `user_permissions`, o sistema aplica o **preset da role primária**, que cai em `CONSULTA` (`deps.py:effective_permission_names` → `primary_role_name` retorna `CONSULTA` por padrão).
3. O preset `CONSULTA` (`permission_codes.py:PRESET_CONSULTA`) **inclui**: `payables.view`, `receivables.view`, `invoices.view`, `debts.view`, `costs.view`, `company_finance.view`, `billing.view`.

E ainda: a camada financeira **ignora o escopo de projeto** (ver F4-05). 

**Resultado:** Qualquer pessoa com acesso à URL da API pode se autocadastrar e, imediatamente, ler **todas as contas a pagar, a receber, notas fiscais, endividamento e custos fixos de toda a empresa** — incluindo nomes de fornecedores/clientes, valores e datas.

> Esta cadeia transforma o "registro aberto" (já citado na Fase 1) de um problema de cadastro indevido em um **vazamento de dados financeiros corporativos completo**.

### F4-02 — `/payables` sem verificação de escopo de projeto (🔴 CRÍTICO / IDOR)
`app/modules/payables/router.py` — nenhum endpoint chama `ensure_project_access`:
- `GET /payables` (linha 48) — lista todas as contas a pagar; filtro `project_id` é opcional e **não validado** contra os projetos do usuário.
- `PATCH /payables/{id}` (linha 84) — `db.get(Payable, payable_id)` sem checagem de propriedade/escopo.
- `PATCH /payables/{id}/pay` (linha 120) e `DELETE /payables/{id}` (linha 137) — idem.

Qualquer usuário com `payables.view`/`costs.edit` opera sobre **qualquer** conta a pagar, de qualquer projeto. **IDOR horizontal** confirmado.

### F4-03 — `/financial/receivables` ignora escopo com `project_id` explícito (🟠 ALTO / IDOR)
`app/modules/financial/router.py:104-135`:
```python
sees_all = user_sees_all_projects(user)
allowed = None if sees_all else await get_accessible_project_ids(user, db)
...
project_ids=None if (project_id is not None or sees_all) else allowed
```
Quando o cliente envia `?project_id=<X>`, o filtro `allowed` é **descartado** (`project_ids=None`) e **não há** `ensure_project_access(project_id=X)`. Um usuário com escopo restrito a um projeto pode enumerar recebíveis de **qualquer** projeto passando o UUID. (Na prática, mitigado por F4-05, que já torna o financeiro global — mas é um defeito de controle de acesso real.)

### F4-04 — Auto-escalação de privilégio via `users.manage` (🟠 ALTO)
`PATCH /users/{id}` e `POST /users/{id}/roles` exigem apenas `users.manage`. O schema `UserUpdate` (`schemas/users.py:48-55`) aceita `role_name` e `permission_names`. Não há verificação que impeça:
- o ator de atribuir `role_name="ADMIN"` a si mesmo ou a terceiros;
- conceder a si mesmo permissões `EXPLICIT_GRANT_ONLY` (`invoices.reactivate`, `audit.export`) via `permission_names`.

Ou seja, `users.manage` é, efetivamente, equivalente a **ADMIN total**. Não há separação entre "gerenciar usuários" e "conceder privilégios elevados".

### F4-05 — Dados financeiros globais por design (🟠 ALTO)
`app/modules/financial/router.py:740-744` (e `_ensure_payable_snapshot_edit_access`):
```python
if not sees_all and (not allowed):
    # Financeiro ignora escopo de project_users: fallback para todos projetos.
    all_ids = await ProjectRepository(db).list_all_project_ids()
    allowed = set(all_ids)
```
Além disso, com `month=None`, `list_payables_snapshot` retorna `svc.list_all()` — **todos os snapshots, sem qualquer filtro de projeto**. A consequência é que `project_users` não confina dados financeiros: qualquer detentor de permissão de visualização financeira vê a empresa inteira. Decisão arquitetural que precisa ser **explicitamente aprovada pelo negócio** ou corrigida.

### Pontos positivos de autorização
- ✅ O módulo `/invoices` (receivables) chama `ensure_project_access` **consistentemente** em create/update/delete/reactivate/anticipations.
- ✅ `EXPLICIT_GRANT_ONLY` (`invoices.reactivate`, `audit.export`) corretamente não herdado por ADMIN.
- ✅ `force_regenerate` de snapshots restrito a superusuário (`financial/router.py:736`).
- ✅ NFs canceladas só são visíveis a quem tem `invoices.reactivate` (`financial/router.py:128`).

## 4.3 BANCO DE DADOS

### SQL Injection — Baixo risco (✅)
- Todo acesso a dados via SQLAlchemy ORM parametrizado.
- Os poucos `text()` encontrados usam **bind params** (`payable_snapshot_service.py:391,1445,1491,1544` — `{"m": comp}`, `{"k": lock_key}`). Sem concatenação de strings com input do usuário.
- Não há `f"...{user_input}..."` em queries.

### Filtros insuficientes
- F4-02 e F4-03 acima são, na raiz, **filtros de escopo ausentes** na camada de query.

## 4.4 API

### F4-06 — Mass assignment de `project_id` em payables (🟠 ALTO)
`payables/router.py:115-117` — `PATCH` aplica `row.project_id = data["project_id"]` sem validar acesso ao projeto de origem **nem** ao de destino. Permite "mover" uma conta a pagar para um projeto ao qual o usuário não pertence.

### F4-09 — Vazamento de contexto interno em erro 500 (🟡 MÉDIO)
`financial/router.py:766-776` retorna no corpo do 500: `str(e)`, `month`, `source_month`, `sees_all_projects`, `accessible_project_count`, `force_regenerate`. Comentário no código admite ser "temporário para diagnóstico". Expõe estrutura interna a clientes não confiáveis.

### Validação de entrada
- ✅ Boa validação via Pydantic + `Query(pattern=...)` em vários filtros (status, tipo, period_field).
- ⚠️ Schemas de update são amplos (`UserUpdate`, `PayableUpdate`) — risco de mass assignment já citado.

## 4.5 FRONTEND

### F4-11 — Armazenamento inseguro de token e claims (🟠 ALTO)
- `frontend/src/services/api.ts` — JWT em `localStorage["sgp_access_token"]` (acessível a qualquer script → XSS rouba sessões).
- O JWT carrega `permissions`, `roles`, `linked_projects` em claims. JWT é **assinado, não criptografado** — qualquer um que obtenha o token lê a estrutura de permissões e os UUIDs de projetos (Base64 decode).
- `localStorage` também guarda `sgp_user`, `sgp_permissions`, `sgp_user_context` em texto plano.
- Sem cabeçalhos de segurança (CSP/X-Frame-Options) no `server.js` → superfície de XSS/clickjacking ampla.

### Secrets no frontend
- ✅ Nenhum secret hardcoded encontrado no frontend. `VITE_API_BASE` é apenas a URL pública da API, injetada em runtime via `/sgp-runtime-config.js`.

## 4.6 UPLOADS

### F4-10 — Validação fraca de upload (🟡 MÉDIO)
`receivables/router.py:574` e `assets/router.py`:
- ✅ Path traversal **mitigado**: `_pdf_disk_path` usa `.resolve()` + valida `relative_to(base)`; nome de arquivo armazenado é `uuid4().pdf` (não usa nome do cliente no disco).
- ✅ Limite de tamanho aplicado (5MB / 15MB).
- ⚠️ Validação de tipo só pelo `content_type` enviado pelo cliente (`file.content_type in (...)`) — **falsificável**. Não há checagem de magic bytes (`%PDF-`).
- ⚠️ Conteúdo servido com `FileResponse` e `media_type="application/pdf"` — risco baixo de execução, mas um arquivo malicioso pode ser entregue a outros usuários.

## 4.7 INFRAESTRUTURA

### F4-08 — Credenciais hardcoded (🔴 CRÍTICO, confirmado)
- `app/api/deps.py:81-84` — superusuário `rafael.casagrande@meconsulting.com.br` hardcoded com bypass total de RBAC.
- `app/core/bootstrap.py:53-60` — cria `admin@admin.com` / `123456` se não houver ADMIN.
- `app/core/config.py:13` — `jwt_secret_key` default `"change-me"` (validado contra uso em produção, mas presente em dev e em `.env.local`).

### URLs internas / variáveis sensíveis
- `.env.local` não contém credenciais de produção reais (apenas `postgres/postgres` local).
- ⚠️ `DATABASE_URL` de produção fica no painel Railway (fora do repo) — bom; verificar que não há vazamento em logs.

---

# FASE 5 — PRIVACIDADE E DADOS (LGPD)

## 5.1 Inventário de Dados Pessoais

| Dado | Onde é armazenado | Sensibilidade LGPD |
|------|-------------------|--------------------|
| Nome completo | `users.full_name`, `employees.name` | Pessoal |
| E-mail | `users.email`, `audit_logs.user_email` | Pessoal |
| Senha (hash) | `users.password_hash` | Sensível (credencial) |
| Chave PIX | `employees.pix_key`, `pix_key_type` | **Sensível (financeiro)** |
| Salário base | `employees.salary_base`, overrides | **Sensível (financeiro)** |
| Encargos/custos individuais | `employees.*`, `employee_monthly_payroll_overrides` | Sensível |
| Atribuição de ativos/EPIs | `asset_assignments.assignee_name` | Pessoal |
| Endereço IP / User-Agent | `audit_logs.ip_address`, `user_agent` | Pessoal (rastreamento) |
| Nomes de fornecedores/clientes (PF/PJ) | `payables.supplier_name`, `receivable_invoices.client_name` | Pessoal (se PF) |

> **Não foram encontrados** campos explícitos de CPF, CNPJ ou telefone como colunas dedicadas. Atenção: nomes de fornecedores/clientes podem conter dados de pessoas físicas (MEI/autônomos), e campos livres de descrição/observação podem conter PII não estruturado.

## 5.2 Quem tem acesso

| Dado | Acesso |
|------|--------|
| PIX / salário de colaboradores | Quem tem `employees.view` (preset CONSULTA inclui!) → potencialmente **qualquer usuário autenticado**, dado F4-01 |
| Financeiro (fornecedores/clientes/valores) | Qualquer `*.view` financeiro = global (F4-05) |
| Audit logs (com IP, e-mail, diffs) | Exportável por `audit.export` (explicit grant) |

## 5.3 Telas e APIs que expõem dados pessoais

- **Telas:** `Employees.tsx` (PIX, salário), `Payables/Receivables/Invoices.tsx` (fornecedores/clientes), `Users.tsx` (e-mails).
- **APIs:** `GET /employees` (dados de folha), `GET /financial/*`, `GET /payables`, `GET /invoices`, `GET /admin/audit/export`.

## 5.4 Riscos LGPD

### F5-01 — Dados sensíveis sem criptografia nem minimização (🟠 ALTO)
- `pix_key` e `salary_base` em texto plano. Em vazamento do banco (ou backup `pg_dump` sem proteção), expõem dados financeiros de colaboradores.
- O preset `CONSULTA` concede `employees.view` — combinado com F4-01, **dados de folha e PIX ficam acessíveis a contas autocadastradas**. Violação de princípios de **necessidade** e **finalidade** (Art. 6º LGPD).

### F5-02 — Retenção indefinida de audit logs (🟡 MÉDIO)
- `audit_logs` guarda IP, e-mail, user-agent e diffs com PII, **sem política de retenção/expurgo** documentada. Conflita com princípio de **necessidade** e limitação temporal.

### F5-03 — Ausência de mecanismos de direito do titular (🟡 MÉDIO)
- Não há funcionalidade de exportação/eliminação de dados pessoais de um titular (Art. 18 LGPD). Soft delete de `users`/`employees` mantém os dados (incluindo PIX) no banco indefinidamente — não atende ao direito de eliminação.
- Backups (`backup_postgres.sh`) sem criptografia e sem controle de acesso documentado.

### Recomendações LGPD
1. Restringir `employees.view` (remover do preset CONSULTA) e segregar visualização de dados de folha/PIX em permissão dedicada (ex.: `payroll.view`).
2. Criptografar `pix_key` e `salary_base` em nível de aplicação (ou pgcrypto).
3. Definir política de retenção de `audit_logs` (ex.: expurgo > 24 meses) e anonimização de IP.
4. Implementar rotina de eliminação efetiva (hard delete + remoção de backups) mediante solicitação do titular.
5. Mapear base legal do tratamento e registrar no RoPA (Registro de Operações).

---

# FASE 6 — RISCOS FINANCEIROS

## Módulos críticos mapeados

| Módulo | Tabelas | Operações de risco |
|--------|---------|--------------------|
| Faturamento | revenues, invoices | create/update/delete de receitas |
| Contas a Receber | receivable_invoices, anticipations, advance_batches | antecipações, borderôs, recebimentos |
| Contas a Pagar | payables, payable_snapshots, payable_payments | pagamentos, snapshots, importação Excel |
| Custos Fixos | company_financial_items (CUSTO_FIXO) | parcelas recorrentes |
| Endividamento | company_financial_items (ENDIVIDAMENTO) | renegociação, parcelas |
| Indicadores | dashboard (KPI), cálculo ROI | agregações |

## 6.1 Cálculos e Precisão

### F6-01 — `float` em agregações financeiras (🟠 ALTO)
Apesar de existir `utils/money.py` com `Decimal`/`ROUND_HALF_UP` (boa base), a camada de leitura/agregação usa **`float`**:
- `financial/router.py:146-149` — `float(sum(float(a.amount_received or 0.0) for a in ants))`, `recv_customer + recv_advance`.
- `payables/router.py:_to_read` — `float(row.amount or 0)`.

Somatórios de muitos lançamentos em `float` acumulam erro de ponto flutuante (ex.: `0.1+0.2`). Em relatórios e KPIs financeiros, pode gerar divergências de centavos que **não fecham** com a contabilidade. Recomenda-se manter `Decimal` ponta a ponta nas somas e converter para `float` apenas na serialização final.

✅ **Positivo:** payables snapshots usam `pg_advisory_xact_lock` (`payable_snapshot_service.py:1445`) para evitar geração concorrente duplicada — boa proteção contra corrida.

## 6.2 Lançamentos Duplicados

### F6-03 — Prevenção de duplicidade frágil (🟡 MÉDIO)
- `revenues`: `UniqueConstraint(project_id, competencia, description)` (`0001_init`). A unicidade depende de `description` — duas receitas legítimas com mesma descrição no mês colidem; e mudar 1 caractere na descrição **burla** a proteção, permitindo duplicata real.
- Importação de payables via Excel (`/financial/payables/import/confirm`): conferir se há deduplicação por chave natural (fornecedor+valor+vencimento). O fluxo de preview existe, mas a confirmação repetida do mesmo arquivo pode reinserir lançamentos — **validar manualmente**.
- Antecipações (`add_anticipation`): índice único em `0035_payable_snapshot_anticipation_unique_index` mitiga duplicidade de antecipação por snapshot. ✅

## 6.3 Pagamentos Incorretos

- `PATCH /payables/{id}/pay` e `register_payables_payment` atualizam `amount_paid`. **Não foi confirmada** validação que impeça `amount_paid > amount` (pagamento acima do devido) nem valores negativos no fluxo de snapshot. **Recomenda-se** auditar `payable_snapshot_service.update_row`/`register payment` para garantir `0 <= amount_paid <= amount`.
- Reversão de pagamento (`reverse_payables_payment`, `financial/router.py:865`) existe — bom para correção, mas precisa de trilha de auditoria (verificar log).

## 6.4 Exclusões Indevidas

### F6-02 — Hard delete em payables/invoices (🟡 MÉDIO)
- `DELETE /payables/{id}` (`payable_service.delete_payable`) e `DELETE /invoices/{id}` fazem **exclusão física**. Diferente de `projects`/`users`/`vehicles` que têm soft delete.
- Combinado com F4-02 (payables sem escopo) e F4-04 (escalonamento), um usuário indevido pode **apagar permanentemente** registros financeiros. A exclusão de NF remove também o PDF do disco (`receivables/router.py` no delete) — perda irreversível de documento fiscal.
- ✅ `DELETE /invoices/{id}` registra `log_user` e checa acesso ao projeto.

## 6.5 Inconsistência Financeira

- **Cenários PREVISTO/REALIZADO**: a coluna `scenario` permeia receitas, alocações, custos. `schema_guard.py` alerta se faltar. Risco: se a UI/relatório misturar cenários por padrão divergente (`default_scenario_for_create` retorna PREVISTO para não-admin e REALIZADO para admin — `deps.py`), dois usuários podem lançar no cenário "errado", gerando divergência entre planejado e realizado. **Validar** consistência do cenário default na UI.
- **Snapshots imutáveis vs. edição**: `update_payables_snapshot` permite alterar `amount_final`/`due_date` de um snapshot supostamente imutável. Verificar regra de negócio: snapshots são a "foto" do mês — edições devem ser auditadas e não retroagir competências fechadas.

## 6.6 Resumo de Riscos Financeiros Priorizados

| Prioridade | Ação |
|-----------|------|
| 1 | Corrigir F4-01/F4-02 (acesso a dados e operações financeiras) — sem isso, todos os demais controles financeiros são contornáveis |
| 2 | Migrar agregações para `Decimal` (F6-01) |
| 3 | Validar limites de pagamento (`0 <= amount_paid <= amount`) |
| 4 | Substituir hard delete por soft delete em payables/invoices (F6-02) |
| 5 | Reforçar deduplicação por chave natural em receitas e importação (F6-03) |

---

# CONSOLIDAÇÃO — TOP 5 AÇÕES IMEDIATAS

1. **Fechar `POST /auth/register`** (ou exigir autenticação) — quebra a cadeia F4-01 de vazamento financeiro total.
2. **Aplicar escopo de projeto em `/payables`** e remover bypass de `project_id` em `/financial/receivables` (F4-02, F4-03).
3. **Remover credenciais hardcoded** (superusuário e admin default) e **corrigir expiração do JWT** (F4-07, F4-08).
4. **Separar `users.manage` de concessão de privilégios elevados** — impedir auto-promoção a ADMIN (F4-04).
5. **Restringir `employees.view`/dados de folha** e criptografar PIX/salário (F5-01) — exposição LGPD.

> Observação: vários achados (F4-03, F4-05, F4-06) só ficam totalmente neutralizados após decisão de negócio sobre **se o financeiro deve ou não respeitar o escopo de `project_users`**. Recomenda-se essa definição antes da fase de correção.

---

*Análise estática. Recomenda-se validação dinâmica (pentest) das cadeias F4-01 e F4-02 em ambiente controlado, e revisão das regras financeiras (F6-03/F6-04/pagamentos) com a área de contabilidade.*
