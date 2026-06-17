# SGC — Matriz de Permissões Definitiva
## Especificação Oficial do RBAC Futuro

**Data:** 2026-06-11
**Status:** Especificação normativa (não implementada)
**Base:** [Documentação Completa](SGC_DOCUMENTACAO_COMPLETA.md) · [Auditoria de Segurança](SGC_AUDITORIA_SEGURANCA_PRIVACIDADE_FINANCEIRO.md) · [Relatório Executivo](SGC_RELATORIO_EXECUTIVO.md) · [Arquitetura de Permissões Futuras](SGC_ARQUITETURA_PERMISSOES_FUTURAS.md)

> Este é o **documento de referência único** para o controle de acesso do SGC. Define roles oficiais, classificação de módulos e o mapa completo de autorização. Nenhuma alteração de código, preset, migration ou banco é feita aqui — é a especificação que orientará a implementação futura.

---

## 0. CONVENÇÕES

**Classes de escopo** (da Arquitetura de Permissões Futuras):
- **Classe A — Corporativo puro:** dado da empresa, sem contrato. Visível a Financeiro/Diretoria/Admin/RH conforme o caso.
- **Classe B — Project-scoped:** dado de contrato, respeita `project_users`. Gestor vê só os seus.
- **Classe C — Híbrido:** `project_id` opcional. Vinculado → gestor do contrato + Financeiro. Não vinculado / agregado → exige escopo corporativo financeiro.

**Símbolos de acesso:**
- ✅ Leitura + Escrita
- 👁️ Somente Leitura
- ✍️ Escrita restrita (subconjunto/condição)
- 🔒 Concessão explícita (explicit-grant-only — nunca herdada por preset)
- — Sem acesso

**Escopo de visibilidade:**
- `[G]` Global (toda a empresa) · `[C]` Por contrato (project_users) · `[H]` Híbrido (regra Classe C) · `[S]` Sistema

---

## 1. ROLES OFICIAIS DO SISTEMA

O SGC passa de **3 roles** (ADMIN, GESTOR, CONSULTA) para **6 roles oficiais**, alinhadas às personas de uma empresa de engenharia:

| Role | Persona | Escopo dominante | Natureza |
|------|---------|------------------|----------|
| **ADMIN** | TI / Administração do sistema | Sistema `[S]` | Técnica |
| **DIRETORIA** | Sócios / Diretores | Global, leitura `[G]` | Estratégica |
| **FINANCEIRO** | Tesouraria / Controladoria | Corporativo financeiro `[G/H]` | Financeira |
| **GESTOR_CONTRATO** | Gerente de contrato/obra | Por contrato `[C]` | Operacional |
| **RH** | Recursos Humanos / DP | Corporativo de pessoas `[G]` | Pessoas |
| **CONSULTA** | Auditor interno / leitura | Conforme concessão explícita | Restrita |

> **Migração de roles legadas:**
> - `GESTOR` (legado) → desmembrar em **GESTOR_CONTRATO** (operação de contrato) e/ou **FINANCEIRO** (se a pessoa atua em tesouraria).
> - `CONSULTA` (legado) → mantém o nome, mas **perde** o acesso financeiro corporativo e de folha que hoje vem no preset (achado F4-01).

---

## 2. DEFINIÇÃO DETALHADA POR ROLE

### 2.1 ADMIN

| Dimensão | Definição |
|----------|-----------|
| **Propósito** | Administração técnica do sistema. Não é, por si, um papel de negócio. |
| **Módulos acessíveis** | Todos (usuários, configurações, auditoria) + negócio apenas se acumular papel de negócio |
| **Leitura** | Global em todos os módulos |
| **Edição** | Usuários, roles, permissões, configurações |
| **Permissões corporativas** | Todas (técnicas) |
| **Permissões restritas** 🔒 | `users.grant_admin` (nova), `audit.export` |
| **Indicadores** | Acesso total (inclui director) |
| **Financeiro** | Acesso técnico total `[G]` |
| **Folha** | 👁️ (técnico; recomenda-se segregar até para ADMIN em ambientes sensíveis) |
| **PIX** | 👁️ (idem) |
| **Auditoria** | ✅ + exportação 🔒 |
| **Restrição-chave** | Conceder ADMIN a terceiros exige `users.grant_admin` (separado de gerenciar usuários) — fecha F4-04 |

### 2.2 DIRETORIA

| Dimensão | Definição |
|----------|-----------|
| **Propósito** | Visão consolidada da empresa para decisão estratégica. Predominantemente leitura. |
| **Módulos acessíveis** | Todos os de negócio, em modo leitura consolidada |
| **Leitura** | Global `[G]`: projetos, financeiro, indicadores, ativos, folha |
| **Edição** | Por exceção (não default) — escrita não faz parte do papel |
| **Permissões corporativas** | `finance.corporate.access`, `indicators.director`, `dashboard.director` |
| **Permissões restritas** 🔒 | `audit.export` (visão de governança), `payroll.view` |
| **Indicadores** | 👁️ Global + ranking (director) |
| **Financeiro** | 👁️ Global consolidado `[G]` |
| **Folha** | 👁️ `payroll.view` |
| **PIX** | — (não necessário para decisão estratégica) |
| **Auditoria** | 👁️ + exportação 🔒 |
| **Restrição-chave** | Acesso amplo de leitura; **escrita restrita** para evitar interferência operacional |

### 2.3 FINANCEIRO

| Dimensão | Definição |
|----------|-----------|
| **Propósito** | Gestão do fluxo de caixa corporativo: pagar, receber, NFs, antecipações, endividamento, custos fixos. |
| **Módulos acessíveis** | Contas a pagar/receber, NFs, borderôs, endividamento, custos fixos, plano de contas, dashboard financeiro |
| **Leitura** | Global financeiro `[G/H]` |
| **Edição** | ✅ Financeiro (pagar/receber/NF/antecipação/endividamento/custos fixos) |
| **Permissões corporativas** | `finance.corporate.access` (chave do escopo global financeiro) |
| **Permissões restritas** 🔒 | `invoices.reactivate`, `payroll.pix.view` (para liquidar pagamentos PIX) |
| **Indicadores** | 👁️ Indicadores financeiros; ranking só se acumular director |
| **Financeiro** | ✅ Global `[G/H]` |
| **Folha** | — por padrão (vê *custo de pessoal corporativo* agregado, **não** salário individual, salvo concessão) |
| **PIX** | ✍️ `payroll.pix.view` 🔒 — apenas a chave PIX para pagamento, **sem** salário |
| **Auditoria** | — (salvo concessão) |
| **Restrição-chave** | **Não edita** estrutura operacional do projeto (alocações/escopo técnico) — separação de responsabilidade |

### 2.4 GESTOR_CONTRATO

| Dimensão | Definição |
|----------|-----------|
| **Propósito** | Gerir os contratos/obras sob sua responsabilidade: receita, custo, margem, equipe, recebíveis e pagáveis **do contrato**. |
| **Módulos acessíveis** | Projetos, receitas, alocações, veículos/uso, custos do projeto, contas a pagar/receber **dos seus contratos**, NFs do contrato, indicadores do contrato |
| **Leitura** | Por contrato `[C/H]` — apenas seus projetos (`project_users`) |
| **Edição** | ✅ Estrutura e dados dos **seus** contratos |
| **Permissões corporativas** | Nenhuma (`finance.corporate.access` = não) |
| **Permissões restritas** | — |
| **Indicadores** | 👁️ ROI/margem **dos seus contratos** (sem ranking global) |
| **Financeiro** | 👁️/✍️ Contas a pagar/receber **vinculadas aos seus contratos** `[H]`; **não** vê corporativo nem agregado da empresa |
| **Folha** | — (vê *quem* está alocado, não *quanto* ganha) |
| **PIX** | — |
| **Auditoria** | — |
| **Restrição-chave** | Escopo estritamente confinado a `project_users`. **Não** vê endividamento, custos fixos corporativos, contratos de terceiros nem consolidado |

### 2.5 RH

| Dimensão | Definição |
|----------|-----------|
| **Propósito** | Gestão de pessoas: cadastro de colaboradores, folha, encargos, PIX. |
| **Módulos acessíveis** | Colaboradores (cadastro), folha, custo de pessoal corporativo |
| **Leitura** | Global de pessoas `[G]` |
| **Edição** | ✅ Cadastro de colaboradores, folha, overrides |
| **Permissões corporativas** | `payroll.view` (nova) |
| **Permissões restritas** 🔒 | `payroll.pix.view` |
| **Indicadores** | — (ou apenas indicadores de pessoas, se existirem) |
| **Financeiro** | — (não vê contas a pagar/receber/endividamento) |
| **Folha** | ✅ `payroll.view` |
| **PIX** | ✅ `payroll.pix.view` 🔒 |
| **Auditoria** | — |
| **Restrição-chave** | Acesso a dado sensível de pessoas (LGPD), **isolado** do financeiro de contratos |

### 2.6 CONSULTA

| Dimensão | Definição |
|----------|-----------|
| **Propósito** | Leitura restrita para auditoria interna / acompanhamento. Concessão deliberada, não default amplo. |
| **Módulos acessíveis** | Apenas o que for explicitamente concedido |
| **Leitura** | 👁️ Conforme atribuição (por contrato ou global, conforme concessão) |
| **Edição** | — (nunca) |
| **Permissões corporativas** | Nenhuma por default; financeiro corporativo **só** com `finance.corporate.access` concedido |
| **Permissões restritas** | — |
| **Indicadores** | 👁️ Se concedido |
| **Financeiro** | — por default (**mudança em relação ao legado**, que concedia `payables.view`/`receivables.view`/`company_finance.view` — F4-01) |
| **Folha** | — |
| **PIX** | — |
| **Auditoria** | — |
| **Restrição-chave** | **Preset enxuto**: leitura básica de projetos/indicadores conforme escopo concedido; **sem** financeiro corporativo nem folha automáticos |

---

## 3. CLASSIFICAÇÃO DOS MÓDULOS DO SGC

| # | Módulo / Domínio | Classe | Escopo | Permissões necessárias (alvo) |
|---|------------------|:------:|:------:|-------------------------------|
| 1 | **Projetos** (cadastro/lifecycle) | B | `[C]` | `projects.view`, `projects.create`, `projects.edit`, `projects.delete` |
| 2 | **Receitas / Faturamento** | B | `[C]` | `billing.view` (+ edit no contrato) |
| 3 | **Alocações de colaboradores** | B | `[C]` | `employees.view` (vínculo), `projects.edit` |
| 4 | **Uso de veículos (no projeto)** | B | `[C]` | `vehicles.view`, `projects.edit` |
| 5 | **Custos operacionais do projeto** | B | `[C]` | `costs.view`, `costs.edit` |
| 6 | **Indicadores do contrato (ROI projeto)** | B | `[C]` | `indicators.view` |
| 7 | **Contas a Pagar** | C | `[H]` | `payables.view` (+ `finance.corporate.access` p/ corporativo), `costs.edit` |
| 8 | **Contas a Receber / NFs** | C | `[H]` | `receivables.view`, `invoices.view`, `invoices.edit` (+ corporativo) |
| 9 | **Antecipações / Borderôs** | C | `[H]` | `invoices.edit`, `invoices.reactivate` 🔒 |
| 10 | **Endividamento corporativo** | A | `[G]` | `debts.view`, `debts.edit` + `finance.corporate.access` |
| 11 | **Custos fixos corporativos** | A | `[G]` | `company_finance.view/edit` + `finance.corporate.access` |
| 12 | **Folha / Custo de pessoal corp.** | A | `[G]` | `payroll.view` 🔒 (nova) |
| 13 | **Colaboradores — cadastro** | A* | `[G]` | `employees.view`, `employees.edit` |
| 14 | **Colaboradores — salário** | A | `[G]` | `payroll.view` 🔒 (nova) |
| 15 | **Colaboradores — PIX** | A | `[G]` | `payroll.pix.view` 🔒 (nova) |
| 16 | **Frota — cadastro** | A* | `[G]` | `vehicles.view`, `vehicles.edit` |
| 17 | **Ativos / EPIs** | A | `[G]` | `assets.view`, `assets.edit` |
| 18 | **Plano de contas** | A | `[G]` | `finance.corporate.access` + `costs.view` |
| 19 | **Dashboard de projetos** | B | `[C]` agregado | `dashboard.view` (consolida só visíveis) |
| 20 | **Dashboard financeiro consolidado** | A | `[G]` | `finance.corporate.access`, `dashboard.view` |
| 21 | **Indicadores globais / ranking** | A | `[G]` | `indicators.director` |
| 22 | **Relatórios** | herda | escopo da fonte | `reports.view`, `reports.export` + perm. do dado |
| 23 | **Alertas** | B | `[C]` | `alerts.view` |
| 24 | **Usuários / Roles / Permissões** | A | `[S]` | `users.manage`, `users.grant_admin` 🔒 (nova) |
| 25 | **Configurações** | A | `[S]` | `settings.view`, `settings.edit` |
| 26 | **Auditoria** | A | `[S]` | `audit.export` 🔒 |

\* "A*": cadastro é corporativo (Classe A); o **vínculo operacional** (alocação/uso no contrato) é Classe B e visível ao gestor do contrato.

---

## 4. MAPEAMENTO DAS PERMISSÕES ATUAIS

As **41 permissões** hoje em `app/core/permission_codes.py`, com a disposição recomendada:

### 4.1 MANTER (sem mudança)

| Código atual | Observação |
|--------------|-----------|
| `system.admin` | Núcleo técnico ADMIN |
| `system.all_projects` | Escopo global de projetos |
| `projects.view` | Leitura de projeto |
| `projects.create` | Criar projeto |
| `projects.edit` | Editar projeto |
| `projects.delete` | Excluir projeto |
| `employees.view` | Cadastro/vínculo (não confundir com folha) |
| `employees.edit` | Editar cadastro |
| `vehicles.view` | Frota leitura |
| `vehicles.edit` | Frota edição |
| `billing.view` | Faturamento/receita |
| `invoices.view` | NFs leitura |
| `invoices.edit` | NFs edição |
| `invoices.reactivate` 🔒 | Já explicit-only — manter |
| `debts.view` | Endividamento leitura |
| `debts.edit` | Endividamento edição |
| `costs.view` | Custos leitura |
| `costs.edit` | Custos edição |
| `company_finance.view` | Custos fixos corp. leitura |
| `company_finance.edit` | Custos fixos corp. edição |
| `assets.view` | Ativos leitura |
| `assets.edit` | Ativos edição |
| `settings.view` | Config leitura |
| `settings.edit` | Config edição |
| `reports.view` | Relatórios leitura |
| `reports.export` | Relatórios exportação |
| `audit.export` 🔒 | Já explicit-only — manter |
| `alerts.view` | Alertas |
| `indicators.view` | Indicadores de contrato |
| `indicators.director` | Ranking global |
| `dashboard.view` | Dashboard |
| `dashboard.director` | Dashboard consolidado |
| `payables.view` | **Manter, porém ressignificar escopo** (ver §4.4) |
| `receivables.view` | **Manter, porém ressignificar escopo** (ver §4.4) |

### 4.2 RENOMEAR

| Código atual | Renomear para | Motivo |
|--------------|---------------|--------|
| `users.manage` | manter o nome, mas **dividir** (ver §4.3) | Hoje concentra gestão + concessão de ADMIN (F4-04) |

> *Nenhum outro código exige renome.* Os nomes atuais são semânticos e estáveis. A mudança principal é de **divisão** e **adição**, não de renomeação.

### 4.3 DIVIDIR

| Código atual | Dividir em | Motivo |
|--------------|-----------|--------|
| `users.manage` | `users.manage` (CRUD de usuários, atribuir roles não-elevadas) **+** `users.grant_admin` 🔒 (conceder ADMIN / permissões elevadas) | Fecha auto-escalação (F4-04). Gerir usuário ≠ criar admin |
| `employees.view` (parte sensível) | `employees.view` (cadastro/vínculo) **+** `payroll.view` 🔒 (salário/encargos/overrides) **+** `payroll.pix.view` 🔒 (chave PIX) | LGPD (F5-01). Gestor vê quem trabalha; só RH/Diretoria vê quanto ganha; só RH/tesouraria vê PIX |
| `payables.view` / `receivables.view` (escopo) | manter o código + introduzir `finance.corporate.access` 🔒 como **gate de escopo** | Separa visão por-contrato (gestor) da visão corporativa/agregada (financeiro) — resolve F4-02/F4-03/F4-05 sem multiplicar códigos |

### 4.4 NOVAS PERMISSÕES (introduzir)

| Código novo | Tipo | Função |
|-------------|:----:|--------|
| `finance.corporate.access` | 🔒 corporativo | Habilita escopo **global/agregado** do financeiro (sem ela, financeiro fica restrito aos contratos do usuário — regra Classe C) |
| `users.grant_admin` | 🔒 | Conceder role ADMIN / permissões elevadas |
| `payroll.view` | 🔒 | Ver salário, encargos, overrides de folha |
| `payroll.pix.view` | 🔒 | Ver chave PIX (mínimo necessário para pagamento) |

### 4.5 DEPRECIAR / REAVALIAR

| Código atual | Disposição | Motivo |
|--------------|-----------|--------|
| `projects.view_list` | **Depreciar** (consolidar em `projects.view`) | No backend já é equivalente a `projects.view` (comentário no próprio código). Granularidade nunca efetivada |
| `projects.view_detail` | **Depreciar** (consolidar em `projects.view`) | Idem — mantém complexidade sem benefício |
| `workspace.projects.access` | **Reavaliar / derivar** | Hoje é *derivada* de outras permissões (`user_has_permission` infere). Pode virar permissão calculada, não armazenada |
| `workspace.finance.access` | **Reavaliar / derivar** | Idem |
| `workspace.assets.access` | **Reavaliar / derivar** | Idem |
| `workspace.indicators.access` | **Reavaliar / derivar** | Idem |

> As `workspace.*.access` são **derivadas** (segmentam a UI, não a segurança — a autorização real é por endpoint). Recomenda-se mantê-las como **permissões calculadas** em vez de concedidas, reduzindo a superfície de configuração. **Decisão de implementação**, fora do escopo desta especificação.

---

## 5. TABELA FINAL DE AUTORIZAÇÃO COMPLETA

Linhas = permissões-alvo · Colunas = roles. Legenda: ✅ ler+escrever · 👁️ leitura · ✍️ escrita restrita · 🔒 explicit-grant · — sem acesso.

| Permissão (alvo) | Classe | ADMIN | DIRETORIA | FINANCEIRO | GESTOR_CONTRATO | RH | CONSULTA |
|------------------|:-----:|:-----:|:---------:|:----------:|:---------------:|:--:|:--------:|
| `system.admin` | S | ✅ | — | — | — | — | — |
| `system.all_projects` | S | ✅ | 👁️ | 👁️ | — | — | — |
| `users.manage` | A | ✅ | — | — | — | — | — |
| `users.grant_admin` 🔒 | A | 🔒 | — | — | — | — | — |
| `settings.view` | A | 👁️ | 👁️ | — | — | — | — |
| `settings.edit` | A | ✅ | — | — | — | — | — |
| `audit.export` 🔒 | A | 🔒 | 🔒 | — | — | — | — |
| `projects.view` | B | 👁️ | 👁️[G] | 👁️[G] | 👁️[C] | — | 👁️* |
| `projects.create` | B | ✅ | — | — | ✍️[C] | — | — |
| `projects.edit` | B | ✅ | — | — | ✅[C] | — | — |
| `projects.delete` | B | ✅ | — | — | ✍️[C] | — | — |
| `billing.view` (receita) | B | ✅ | 👁️[G] | 👁️[G] | ✅[C] | — | 👁️* |
| `costs.view` | B | ✅ | 👁️[G] | 👁️[G] | 👁️[C] | — | 👁️* |
| `costs.edit` | B | ✅ | — | ✍️ | ✅[C] | — | — |
| `employees.view` (cadastro/vínculo) | A*/B | ✅ | 👁️ | — | 👁️[C] | ✅ | 👁️* |
| `employees.edit` | A* | ✅ | — | — | — | ✅ | — |
| `payroll.view` 🔒 (salário) | A | 🔒 | 🔒 | — | — | 🔒 | — |
| `payroll.pix.view` 🔒 (PIX) | A | 🔒 | — | 🔒 | — | 🔒 | — |
| `vehicles.view` | A*/B | ✅ | 👁️ | — | 👁️[C] | — | 👁️* |
| `vehicles.edit` | A* | ✅ | — | — | — | — | — |
| `assets.view` | A | ✅ | 👁️ | — | 👁️[C] | — | 👁️* |
| `assets.edit` | A | ✅ | — | — | — | — | — |
| `finance.corporate.access` 🔒 | A | 🔒 | 🔒 | 🔒 | — | — | — |
| `payables.view` | C | 👁️[H] | 👁️[G]¹ | ✅[G]¹ | 👁️[C] | — | — |
| `receivables.view` | C | 👁️[H] | 👁️[G]¹ | ✅[G]¹ | 👁️[C] | — | — |
| `invoices.view` | C | 👁️[H] | 👁️[G]¹ | ✅[G]¹ | 👁️[C] | — | — |
| `invoices.edit` | C | ✅ | — | ✅[G]¹ | ✍️[C] | — | — |
| `invoices.reactivate` 🔒 | C | 🔒 | — | 🔒 | — | — | — |
| `debts.view` | A | 👁️ | 👁️[G] | ✅[G] | — | — | — |
| `debts.edit` | A | ✅ | — | ✅ | — | — | — |
| `company_finance.view` | A | 👁️ | 👁️[G] | ✅[G] | — | — | — |
| `company_finance.edit` | A | ✅ | — | ✅ | — | — | — |
| `dashboard.view` | B/A | ✅ | 👁️[G] | 👁️[G]¹ | 👁️[C] | — | 👁️* |
| `dashboard.director` | A | 👁️ | 👁️ | 👁️ | — | — | — |
| `indicators.view` | B | 👁️ | 👁️[G] | 👁️ | 👁️[C] | — | 👁️* |
| `indicators.director` | A | 👁️ | 👁️ | 👁️¹ | — | — | — |
| `reports.view` | herda | ✅ | 👁️ | 👁️ | 👁️[C] | 👁️ | 👁️* |
| `reports.export` | herda | ✅ | 👁️ | 👁️ | ✍️[C] | 👁️ | — |
| `alerts.view` | B | ✅ | 👁️ | 👁️ | 👁️[C] | — | 👁️* |

**Notas da tabela:**
- ¹ Acesso **global/agregado** financeiro condicionado a `finance.corporate.access`. Sem ela, o portador de `payables.view`/`receivables.view`/`invoices.view` enxerga **apenas** os registros vinculados aos seus contratos (regra Classe C nível-contrato).
- `*` CONSULTA: acessos marcados só existem **se concedidos explicitamente** na atribuição do usuário; o **preset CONSULTA não os concede automaticamente** (correção de F4-01). O escopo (`[G]` ou `[C]`) segue a concessão.
- `[G]` global · `[C]` por contrato (`project_users`) · `[H]` híbrido · `[S]` sistema.
- 🔒 = só vale se marcada em `user_permissions` (nunca herdada por preset de role).

---

## 6. REGRAS DE AUTORIZAÇÃO NORMATIVAS

1. **Escopo precede ação.** A classe do dado (A/B/C) define a visibilidade base; a permissão de ação define o que se faz dentro do que é visível.
2. **Financeiro é híbrido por padrão.** Visão corporativa/agregada exige `finance.corporate.access`. Sem ela, financeiro = escopo de contrato.
3. **Explicit-grant nunca é herdado.** `users.grant_admin`, `payroll.view`, `payroll.pix.view`, `finance.corporate.access`, `invoices.reactivate`, `audit.export` só valem se marcados em `user_permissions`.
4. **Folha e PIX são segregados do cadastro.** `employees.view` ≠ ver salário/PIX.
5. **Gestor de contrato é confinado a `project_users`.** Nenhum acesso corporativo por default.
6. **CONSULTA é leitura mínima e deliberada.** Sem financeiro corporativo nem folha automáticos.
7. **Diretoria é leitura ampla, escrita por exceção.**
8. **Conceder ADMIN ≠ gerenciar usuários.** Requer `users.grant_admin`.

---

## 7. RASTREABILIDADE — Achados de Auditoria Endereçados

| Achado | Severidade | Resolvido por |
|--------|:----------:|---------------|
| F4-01 — Registro → leitura total do financeiro | 🔴 | Preset CONSULTA enxuto + `finance.corporate.access` (§2.6, §5) |
| F4-02 — IDOR em payables | 🔴 | Payables como Classe C híbrida (§3, §5) |
| F4-03 — IDOR receivables com project_id | 🟠 | Gate de escopo `finance.corporate.access` (§4.3) |
| F4-04 — Auto-escalação via users.manage | 🟠 | Divisão `users.grant_admin` (§4.3) |
| F4-05 — Financeiro global por design | 🟠 | Decisão formal: financeiro híbrido (§6.2) |
| F5-01 — PIX/salário expostos | 🟠 | `payroll.view` / `payroll.pix.view` (§4.3) |

---

## 8. RESUMO DE TRANSIÇÃO (legado → alvo)

| De (legado) | Para (alvo) |
|-------------|-------------|
| 3 roles (ADMIN, GESTOR, CONSULTA) | 6 roles (ADMIN, DIRETORIA, FINANCEIRO, GESTOR_CONTRATO, RH, CONSULTA) |
| Financeiro global p/ qualquer `*.view` | Financeiro híbrido; corporativo só com `finance.corporate.access` |
| `employees.view` cobre folha/PIX | Segregado em `payroll.view` / `payroll.pix.view` |
| `users.manage` concede ADMIN | `users.grant_admin` separado |
| CONSULTA com financeiro+folha no preset | CONSULTA enxuto; acessos por concessão explícita |
| `projects.view_list/detail` | Consolidados em `projects.view` |
| `workspace.*.access` armazenadas | Reavaliar como derivadas/calculadas |

**Contagem de permissões-alvo:** 41 atuais − 2 depreciadas (`view_list`, `view_detail`) + 4 novas (`finance.corporate.access`, `users.grant_admin`, `payroll.view`, `payroll.pix.view`) = **43 permissões**, com 4 `workspace.*` em reavaliação.

---

*Especificação normativa. Nenhuma alteração de código, preset, migration ou banco foi realizada. Este documento é a referência única para a implementação futura do RBAC do SGC e depende das decisões de negócio registradas na Seção 7 da [Arquitetura de Permissões Futuras](SGC_ARQUITETURA_PERMISSOES_FUTURAS.md).*
