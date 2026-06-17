# SGC — Relatório Executivo de Auditoria Técnica
## Sistema de Gestão Corporativa

**Data:** 2026-06-11  
**Escopo:** auditoria estática completa (backend FastAPI, frontend React, banco PostgreSQL)  
**Documentos relacionados:**
- [SGC_DOCUMENTACAO_COMPLETA.md](SGC_DOCUMENTACAO_COMPLETA.md) — Fases 1–3 (levantamento, funcional, técnico)
- [SGC_AUDITORIA_SEGURANCA_PRIVACIDADE_FINANCEIRO.md](SGC_AUDITORIA_SEGURANCA_PRIVACIDADE_FINANCEIRO.md) — Fases 4–6
- Este documento — Fases 7–11 + inventário final

> ⚠️ Auditoria sem qualquer alteração de código, migrations, banco, frontend ou backend.

---

## 1. RESUMO EXECUTIVO

O **SGC** é um ERP financeiro/operacional fullstack, funcional e em produção (Railway), com arquitetura em camadas bem definida (Router → Service → Repository → ORM), RBAC granular, trilha de auditoria completa e código Python moderno e tipado. A engenharia base é **sólida**.

Contudo, a auditoria identificou uma **cadeia crítica de exposição de dados financeiros**: o endpoint de registro é público, usuários sem papel herdam o preset `CONSULTA` (que inclui visualização financeira), e a camada financeira ignora o escopo de projetos. Na prática, **qualquer pessoa com a URL da API pode se cadastrar e ler todo o financeiro da empresa** (fornecedores, clientes, valores, salários, chaves PIX). Há ainda credenciais hardcoded, IDOR em contas a pagar, e auto-escalação de privilégios.

A boa notícia: o núcleo das correções críticas é de **baixo esforço** (~5–8 horas para os 5 itens mais graves). O sistema não tem falhas arquiteturais que exijam reescrita — são lacunas pontuais de controle de acesso e configuração.

**Veredito:** sistema bom em construção, **inadequado para produção no estado atual de segurança**. Após a Fase 1 do plano (30 dias), torna-se aceitável.

---

## 2. NOTA GERAL DO SISTEMA

### 🎯 Nota global: **5.8 / 10**

> A nota é puxada para baixo pela dimensão Segurança (crítica). As demais dimensões estão entre boas e muito boas.

| Dimensão | Nota | Tendência |
|----------|:----:|-----------|
| **Segurança** | 3.0 / 10 | 🔴 Crítico |
| **Arquitetura** | 7.5 / 10 | 🟢 Bom |
| **Escalabilidade** | 6.0 / 10 | 🟡 Adequado |
| **Manutenibilidade** | 6.5 / 10 | 🟡 Adequado |
| **Performance** | 6.0 / 10 | 🟡 Adequado |
| **Riscos Financeiros** | 5.0 / 10 | 🟠 Atenção |
| **Qualidade de Código** | 6.5 / 10 | 🟡 Adequado |
| **Privacidade / LGPD** | 4.0 / 10 | 🟠 Atenção |

*Média ponderada com peso dobrado em Segurança e Riscos Financeiros (natureza do sistema).*

---

## 3. SEGURANÇA — Nota 3.0

**Pontos fortes:** bcrypt com rehash, RBAC granular, audit log com IP/diff, sem SQL injection, path traversal mitigado em uploads, session versioning.

**Pontos críticos:** registro público → vazamento financeiro total; credenciais hardcoded (superusuário + admin default `123456`); JWT de 24h sem revogação; IDOR em `/payables`; auto-escalação via `users.manage`; sem rate limiting; JWT em localStorage; sem CSP.

→ Detalhamento completo na Fase 4 (documento de segurança).

---

## 4. ARQUITETURA — Nota 7.5

**Pontos fortes:**
- Separação de camadas limpa e consistente: `modules/*/router.py` → `services/*` → `repositories/*` → ORM.
- 20 módulos bem delimitados por domínio de negócio.
- Dependências FastAPI bem usadas (`require_permission`, `get_current_user`, `get_current_workspace`).
- Migrations versionadas e sequenciais (67), com `schema_guard` defensivo no boot.
- Frontend com Context API + serviços de API isolados por domínio.

**Pontos de atenção:**
- `admin_router` registrado fora do bloco `protected` (inconsistência defensiva — F4-08).
- Dois sistemas de permissão sobrepostos (presets de role + `user_permissions`) tornam a lógica de autorização complexa e difícil de auditar (`deps.py` tem ~503 linhas, muitas em `user_has_permission`).
- Lógica de negócio financeiro concentrada em `financial/router.py` (1.202 linhas) — deveria estar em service.

---

## 5. ESCALABILIDADE — Nota 6.0

**Favorável:**
- Stack async (FastAPI + asyncpg + SQLAlchemy async) — boa base para concorrência.
- Pool de conexões configurável; `pool_pre_ping` habilitado.
- 122 índices no schema — boa cobertura.
- Snapshots financeiros com `pg_advisory_xact_lock` evitam corrida.

**Limitações:**
- Migrations rodam **no startup** (`run_alembic_upgrade()`) — em múltiplas réplicas, há risco de corrida/lock no deploy. Não escala horizontalmente sem cuidado.
- Pool padrão de 5+15 conexões; para crescimento, precisa tuning.
- Uploads em **disco local** (sem object storage) — impede réplicas múltiplas e perde arquivos em redeploy.
- Sem cache (Redis) para KPIs/dashboards recalculados a cada request.
- `seed_admin()` e schema-guard no boot adicionam latência de startup.

---

## 6. MANUTENIBILIDADE — Nota 6.5

**Favorável:**
- Código tipado (type hints Python, TypeScript no front).
- Nomenclatura clara em português/inglês, comentários explicativos pertinentes.
- 11 testes unitários cobrindo regras de negócio financeiras delicadas.

**Dívida técnica (ver Fase 7):**
- Arquivos gigantes: `payable_snapshot_service.py` (2.277 linhas), `ProjectDetail.tsx` (1.982), `CompanyFinanceExecutive.tsx` (1.924).
- Ausência de testes de integração HTTP e de autenticação/autorização.
- `bcrypt<4.0.0` fixado por incompatibilidade com passlib — dívida que bloqueia atualizações.
- Migrations sem `downgrade` — rollback impossível.
- Sem lockfile no backend (apenas `requirements.txt` com `>=`) — builds não reprodutíveis.

---

## 7. PERFORMANCE — Nota 6.0

→ Detalhamento na **Fase 8** abaixo.

**Resumo:** boa adoção de eager loading (61 ocorrências de `selectinload`/`joinedload`) e queries batched em pontos sensíveis. Porém há **N+1 confirmado** no dashboard consolidado e ausência total de memoização no frontend (`React.memo` = 0 usos) em páginas de 1.000–2.000 linhas.

---

## 8. RISCOS FINANCEIROS — Nota 5.0

→ Detalhamento na Fase 6 (documento de segurança).

**Resumo:** uso de `float` em agregações monetárias (apesar de existir `money.py` com `Decimal`), hard delete irreversível em payables/invoices, prevenção de duplicidade frágil (dependente de `description`), e falta de validação confirmada de `amount_paid <= amount`. Combinados com as falhas de acesso (F4-02/F4-04), permitem manipulação/exclusão indevida de registros financeiros.

---

## 9. RISCOS DE SEGURANÇA — síntese

Os 5 riscos que devem bloquear a operação até correção:

1. **Registro público → leitura total do financeiro** (cadeia F4-01)
2. **Credenciais hardcoded** (superusuário + admin `123456`)
3. **IDOR em `/payables`** (acesso/edição/exclusão de qualquer conta)
4. **Auto-escalação a ADMIN** via `users.manage`
5. **JWT 24h sem revogação** + armazenamento em localStorage

---

## 10. PRIORIDADES

| Ordem | Ação | Esforço | Prazo |
|:----:|------|:------:|:----:|
| 1 | Fechar/proteger `POST /auth/register` | 1h | Imediato |
| 2 | Remover credenciais hardcoded + admin default | 2h | Imediato |
| 3 | Corrigir expiração JWT (usar config) | 30min | Imediato |
| 4 | Escopo de projeto em `/payables` + fix IDOR receivables | 4h | 7 dias |
| 5 | Separar `users.manage` de concessão de ADMIN | 3h | 7 dias |
| 6 | Restringir `employees.view` + criptografar PIX/salário | 8h | 30 dias |
| 7 | Rate limiting + headers de segurança | 6h | 30 dias |
| 8 | Migrar agregações financeiras para Decimal | — | 90 dias |

---

# FASE 7 — QUALIDADE DE CÓDIGO

## 7.1 Código duplicado (🟠 Média)

- **Lógica de permissão duplicada** entre `app/api/deps.py` e `app/core/session_context.py`: `permission_names_from_user`, `effective_permission_names`, `user_has_permission`, `primary_role_name` aparecem nas **duas**, com pequenas variações (`is_superuser` flag). Risco de divergência de comportamento de autorização. **Consolidar em um único módulo.**
- **Mapeamento de workspace→permissões** repetido em `deps.py` (`user_has_permission`) e `session_context.py` (constantes `*_WORKSPACE_PERMISSIONS`).
- Padrão `try/except MissingGreenlet → fallback` repetido ~8× em `receivable_service.py` e `financial/router.py` — deveria ser um helper.

## 7.2 Componentes/arquivos excessivamente grandes (🔴 Alta)

| Arquivo | Linhas | Classificação |
|---------|:-----:|:-------------:|
| `app/services/payable_snapshot_service.py` | 2.277 | 🔴 Crítica |
| `frontend/.../ProjectDetail.tsx` | 1.982 | 🔴 Crítica |
| `frontend/.../CompanyFinanceExecutive.tsx` | 1.924 | 🔴 Crítica |
| `frontend/.../Invoices.tsx` | 1.391 | 🟠 Alta |
| `app/modules/financial/router.py` | 1.202 | 🟠 Alta |
| `frontend/.../Payables.tsx` | 1.163 | 🟠 Alta |
| `frontend/.../Employees.tsx` | 1.132 | 🟠 Alta |
| `app/services/assets_service.py` | 963 | 🟡 Média |

**Recomendação:** quebrar componentes React por responsabilidade (tabela, filtros, modais, hooks de dados); extrair lógica de negócio de `financial/router.py` para services; dividir `payable_snapshot_service.py` por tipo de snapshot.

## 7.3 Serviços com muitas responsabilidades (🟠 Média/Alta)

- `payable_snapshot_service.py` (2.277 linhas): geração, listagem, atualização, pagamento, regeneração, locks, importação — **viola SRP**. Candidato a divisão em `SnapshotGenerator`, `SnapshotQuery`, `PaymentService`.
- `financial/router.py`: agrega receivables, revenues, invoices, payables, dashboard, importação — 6 domínios em um router.

## 7.4 Acoplamento excessivo (🟡 Média)

- `deps.py` importa ~40 constantes de permissão e conhece detalhes de workspace, projeto e cenário — hub de acoplamento.
- Routers acessam diretamente `request.state.workspace`, criando dependência implícita do middleware.

## 7.5 Dívida técnica — classificação

| Item | Classificação |
|------|:-------------:|
| Arquivos de 1.000–2.300 linhas | 🔴 Alta |
| Lógica de autorização duplicada (deps × session_context) | 🔴 Alta |
| Ausência de testes de integração/auth | 🔴 Alta |
| Migrations sem downgrade | 🟠 Média |
| Sem lockfile backend (`>=` em requirements) | 🟠 Média |
| `bcrypt<4` fixado (bloqueia upgrades) | 🟠 Média |
| `try/except MissingGreenlet` repetido | 🟡 Baixa |
| Bloco de erro 500 "temporário" expondo contexto | 🟡 Baixa |

---

# FASE 8 — PERFORMANCE

## 8.1 Consultas N+1 (🟠 Alta)

**Confirmado:** `app/services/dashboard_service.py:339` — `list_projects_financial_summaries` itera sobre `project_ids` e, por iteração, executa `await self.session.get(Project, pid)` **e** `await self.resumo_por_projeto(pid, ...)` (que dispara várias subqueries). Para um dashboard consolidado de N projetos: **N × (1 + k) queries**. É o principal gargalo do dashboard de diretoria/global.
→ *Recomendação:* carregar projetos em lote (`WHERE id IN (...)`) e agregar receitas/custos em queries set-based com `GROUP BY project_id`.

**Padrão defensivo (não é N+1, mas sintoma):** ~8 `try/except MissingGreenlet` indicam relacionamentos nem sempre eager-loaded; o fallback usa campos denormalizados (`advance_amount_received`) — funciona, mas mascara a causa raiz.

**Bem feito:** `_snapshots_to_read` usa queries **batched** (`last_payment_dates_by_snapshot_ids`, `paid_in_period_by_snapshot_ids`) — padrão correto a replicar no dashboard.

## 8.2 Carregamentos excessivos (🟡 Média)

- `GET /financial/payables` sem `month` chama `list_all()` — retorna **todos** os snapshots históricos sem paginação. Cresce indefinidamente.
- `GET /payables` e várias listagens financeiras não têm paginação (`limit/offset`). Em produção madura, retornam datasets grandes inteiros.

## 8.3 Gargalos de banco (🟡 Média)

- Conversões `float → Decimal → str → Decimal` em `_snapshot_to_read` (overhead por linha, além do risco de precisão — F6-01).
- Migrations no startup podem segurar o boot sob lock.
- ✅ 122 índices — cobertura de schema adequada.

## 8.4 Frontend — renderizações desnecessárias (🟠 Alta)

- **`React.memo`: 0 ocorrências** em todo o frontend.
- Memoização (`useMemo`/`useCallback`) esparsa: `ProjectDetail.tsx` (1.982 linhas) tem apenas 11; `Invoices.tsx` (1.391) e outras páginas grandes têm pouquíssimas.
- Páginas grandes recalculam derivações e re-renderizam tabelas inteiras a cada mudança de estado (filtros, modais). Em listas longas, gera lentidão perceptível.
→ *Recomendação:* memoizar linhas de tabela, extrair sub-componentes, virtualizar listas longas (react-window).

## 8.5 Gargalos de frontend (🟡 Média)

- `timeout` de 15s no Axios — adequado, mas sem retry/backoff.
- Sem code-splitting por rota evidente (bundle único do Vite) — páginas de 1–2k linhas incham o bundle inicial.

---

# FASE 10 — MATRIZ DE RISCO

Legenda — Esforço: P (≤2h), M (≤1 dia), G (≤1 semana), GG (>1 semana).

## 🔴 CRÍTICO

| ID | Descrição | Impacto | Probabilidade | Recomendação | Esforço |
|----|-----------|---------|:------------:|--------------|:------:|
| C1 | Registro público → leitura total do financeiro (F4-01) | Vazamento de todos os dados financeiros e de folha | Alta | Remover/autenticar `/auth/register` | P |
| C2 | Admin default `admin@admin.com`/`123456` (V-004) | Acesso total via credencial conhecida | Média | Remover seed de credencial; exigir setup explícito | M |
| C3 | E-mail superusuário hardcoded (F4-08) | Bypass total de RBAC; PII no código | Média | Migrar para env, sem fallback no código | P |
| C4 | IDOR em `/payables` (F4-02) | Ler/editar/excluir qualquer conta a pagar | Alta | Aplicar `ensure_project_access` ou escopo financeiro definido | M |
| C5 | JWT 24h hardcoded, sem revogação (F4-07) | Janela longa de token comprometido | Média | Usar `settings.access_token_expire_minutes`; invalidar na troca de senha | P |

## 🟠 ALTO

| ID | Descrição | Impacto | Probabilidade | Recomendação | Esforço |
|----|-----------|---------|:------------:|--------------|:------:|
| A1 | Auto-escalação via `users.manage` (F4-04) | Qualquer gestor de usuários vira ADMIN | Média | Separar concessão de role elevada; impedir auto-promoção | M |
| A2 | IDOR receivables com `project_id` explícito (F4-03) | Enumerar recebíveis de outros projetos | Média | Validar acesso ao `project_id` informado | P |
| A3 | Mass assignment `project_id` em payables (F4-06) | Mover conta para projeto sem acesso | Média | Validar projeto destino; restringir campos | M |
| A4 | Sem rate limiting (V-005) | Força bruta de senha, DDoS | Alta | SlowAPI em login/register/global | M |
| A5 | JWT em localStorage + claims expostos (F4-11) | Roubo de sessão via XSS | Baixa-Média | Cookie httpOnly ou mitigar XSS + CSP | G |
| A6 | Dados financeiros globais por design (F4-05) | Sem confinamento por projeto | Alta | Decisão de negócio + aplicar escopo | M |
| A7 | PIX/salário em texto plano, em preset CONSULTA (F5-01) | Exposição LGPD de folha/PIX | Alta | Permissão dedicada + criptografia | G |
| A8 | `float` em agregações financeiras (F6-01) | Divergência de centavos em KPIs/relatórios | Média | Decimal ponta a ponta | G |
| A9 | Arquivos 1k–2.3k linhas (F7) | Manutenção difícil, bugs | Alta | Refatorar/dividir | GG |

## 🟡 MÉDIO

| ID | Descrição | Impacto | Probabilidade | Recomendação | Esforço |
|----|-----------|---------|:------------:|--------------|:------:|
| M1 | Sem CSP/headers de segurança (V-010) | XSS/clickjacking | Média | `helmet` no server.js | P |
| M2 | Upload validado só por content_type (F4-10) | Arquivo malicioso entregue | Baixa | Validar magic bytes | M |
| M3 | Hard delete em payables/invoices (F6-02) | Perda irreversível + PDF fiscal | Média | Soft delete + retenção | M |
| M4 | N+1 no dashboard consolidado (F8) | Lentidão com muitos projetos | Média | Queries set-based | M |
| M5 | Sem memoização no frontend (F8) | UI lenta em listas grandes | Média | React.memo/virtualização | G |
| M6 | Erro 500 expõe contexto interno (F4-09) | Info leak | Baixa | Remover bloco de diagnóstico | P |
| M7 | Retenção indefinida de audit logs (F5-02) | Acúmulo de PII | Média | Política de expurgo + anonimizar IP | M |
| M8 | Duplicidade frágil de receitas (F6-03) | Lançamentos duplicados | Média | Chave natural robusta | M |
| M9 | Sem paginação em listagens financeiras (F8) | Resposta cresce sem limite | Média | Paginar | M |
| M10 | Senha mínima 6 sem complexidade (V-009) | Senhas fracas | Média | min 8 + complexidade | P |
| M11 | Uploads sem volume persistente (V-015) | Perda de arquivos em redeploy | Média | Volume/object storage | M |

## 🔵 BAIXO

| ID | Descrição | Impacto | Recomendação | Esforço |
|----|-----------|---------|--------------|:------:|
| B1 | Migrations no startup (escala) | Risco em múltiplas réplicas | Job de migração separado | M |
| B2 | Sem lockfile backend | Builds não reprodutíveis | pip-tools/uv lock | P |
| B3 | `bcrypt<4` fixado | Bloqueia upgrades | Acompanhar passlib | P |
| B4 | Migrations sem downgrade | Rollback manual | Adicionar downgrades | G |
| B5 | `try/except MissingGreenlet` repetido | Code smell | Eager load + helper | M |
| B6 | AUTH_DEBUG loga token parcial | Vazamento se ativado em prod | Já bloqueado por validator; remover logs | P |

---

# FASE 11 — PLANO DE EVOLUÇÃO (ROADMAP)

## 🗓️ 30 DIAS — Estabilização de Segurança

### Correções obrigatórias
- [ ] C1 — Fechar/autenticar `POST /auth/register`
- [ ] C2 — Remover criação de admin default; setup via env/CLI
- [ ] C3 — Remover e-mail superusuário hardcoded (usar `APP_SUPERUSER_EMAILS`)
- [ ] C5 — Corrigir expiração JWT (usar `settings.access_token_expire_minutes`)
- [ ] C4 — Aplicar escopo de projeto (ou decisão de negócio) em `/payables`
- [ ] A2 — Corrigir IDOR de `project_id` em `/financial/receivables`
- [ ] A1 — Impedir auto-promoção a ADMIN via `users.manage`
- [ ] M6 — Remover bloco de erro 500 que expõe contexto
- [ ] **Definição de negócio:** financeiro deve respeitar `project_users`? (bloqueia A6, F4-03/05/06)

### Melhorias recomendadas
- [ ] A4 — Rate limiting (login/register)
- [ ] M1 — Headers de segurança (helmet) no frontend
- [ ] M10 — Senha mínima 8 + complexidade
- [ ] Definir `JWT_SECRET_KEY` forte em produção (verificar Railway)

## 🗓️ 90 DIAS — Hardening e Conformidade

### Correções obrigatórias
- [ ] A7 — Restringir `employees.view` (sair do preset CONSULTA) + criptografar PIX/salário
- [ ] M3 — Soft delete em payables/invoices
- [ ] M11 — Volume persistente / object storage para uploads
- [ ] M2 — Validação de magic bytes em uploads
- [ ] A5 — Mitigar XSS (CSP madura) e avaliar cookie httpOnly

### Melhorias recomendadas
- [ ] A8 — Migrar agregações financeiras para `Decimal`
- [ ] M4 — Eliminar N+1 do dashboard consolidado (queries set-based)
- [ ] M7 — Política de retenção de audit logs + anonimização de IP
- [ ] M8/M9 — Deduplicação robusta + paginação em listagens financeiras
- [ ] Testes de integração para auth/RBAC e fluxos financeiros críticos
- [ ] Implementar invalidação de token na troca de senha

### Melhorias futuras
- [ ] Backup automatizado com destino remoto e criptografia
- [ ] Mecanismos LGPD de direito do titular (exportação/eliminação)

## 🗓️ 180 DIAS — Evolução Estrutural

### Melhorias recomendadas
- [ ] A9/F7 — Refatorar arquivos gigantes (services e páginas React)
- [ ] Consolidar lógica de autorização duplicada (`deps.py` × `session_context.py`)
- [ ] M5 — Memoização/virtualização no frontend; code-splitting por rota
- [ ] Cache (Redis) para KPIs/dashboards

### Melhorias futuras
- [ ] B1 — Mover migrations para job de deploy dedicado (escala horizontal)
- [ ] B2/B4 — Lockfile backend + downgrades de migration
- [ ] B3 — Atualizar bcrypt ≥4 quando passlib permitir
- [ ] Observabilidade: métricas, tracing, alertas de erro

---

# VALIDAÇÃO FINAL — INVENTÁRIO

| Item | Quantidade |
|------|:----------:|
| **Módulos backend (routers registrados)** | 20 |
| **Telas frontend (páginas)** | 23 |
| **Endpoints HTTP** | 175 |
| **Tabelas no banco** (`create_table`) | 49 |
| **Migrations** | 67 |
| **Permissões (códigos RBAC)** | 41 |
| **Roles** | 3 (ADMIN, GESTOR, CONSULTA) |
| **Workspaces** | 4 (projects, finance, assets, indicators) |
| **Testes automatizados** | 11 (unitários) |
| **Linhas de código backend** | ~26.700 |
| **Linhas de código frontend** | ~24.600 |

### Endpoints por módulo
`financial: 32 · receivables: 21 · assets: 18 · project_structure: 18 · employees: 13 · projects: 10 · users: 10 · company_finance: 9 · fleet: 6 · dashboard: 5 · hr: 5 · indicators: 5 · alerts: 4 · auth: 4 · costs: 4 · payables: 5 · collaborators: 2 · settings: 2 · admin: 1 · reports: 1`

### Vulnerabilidades e riscos

| Métrica | Quantidade |
|---------|:----------:|
| **Vulnerabilidades/achados totais** | 35 |
| **Riscos CRÍTICOS** | 5 |
| **Riscos ALTOS** | 9 |
| **Riscos MÉDIOS** | 11 |
| **Riscos BAIXOS** | 6 |
| Achados LGPD/privacidade | 3 |
| Achados financeiros específicos | 3 |
| Itens de dívida técnica | 8 |

---

## CONCLUSÃO

O SGC tem **fundação de engenharia boa** e está a poucas correções de baixo esforço de atingir um patamar de segurança aceitável. O risco dominante não é arquitetural, mas de **controle de acesso e configuração**: a combinação registro-aberto + preset-CONSULTA-com-finanças + financeiro-global é a falha mais severa e deve ser tratada antes de qualquer outra coisa.

**Recomendação final:** executar integralmente o bloco de **30 dias** (especialmente C1–C5) como pré-condição para continuidade segura em produção, e tomar a **decisão de negócio sobre o escopo financeiro** o quanto antes, pois ela destrava um conjunto inteiro de correções.

---

*Auditoria estática. Recomenda-se validação dinâmica (pentest) das cadeias críticas C1 e C4, e revisão das regras financeiras com a área de contabilidade. Nenhum arquivo de código, migration, banco, frontend ou backend foi modificado nesta auditoria.*
