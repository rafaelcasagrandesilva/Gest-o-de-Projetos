# SGC — Arquitetura de Permissões Futuras
## Modelo de Escopo: Corporativo × Project-Scoped

**Data:** 2026-06-11
**Status:** Proposta de design (não implementada)
**Base:** Fases 1–11 da auditoria técnica
**Contexto de negócio:** empresa de engenharia com gestores de contrato, equipe financeira e diretoria
**Documentos relacionados:** [SGC_RELATORIO_EXECUTIVO.md](SGC_RELATORIO_EXECUTIVO.md), [SGC_AUDITORIA_SEGURANCA_PRIVACIDADE_FINANCEIRO.md](SGC_AUDITORIA_SEGURANCA_PRIVACIDADE_FINANCEIRO.md)

> Este documento **define a arquitetura-alvo** de permissões. Resolve a questão de design levantada na Fase 4 (achado F4-05): _"o financeiro deve ou não respeitar o escopo de `project_users`?"_. Nenhuma alteração de código é proposta aqui — apenas o modelo conceitual e as decisões que o sustentam.

---

## 1. PROBLEMA ATUAL (recapitulação)

A auditoria identificou que o SGC hoje opera com **duas lógicas de escopo conflitantes**:

1. **Projetos e operações** respeitam `project_users` — um usuário sem visão global só vê os projetos aos quais está vinculado.
2. **Financeiro ignora `project_users`** — qualquer usuário com `*.view` financeiro enxerga a empresa inteira (comentário explícito no código: _"Financeiro ignora escopo de project_users: fallback para todos projetos"_).

Combinado com o preset `CONSULTA` (que inclui `payables.view`, `receivables.view`, `company_finance.view`, `employees.view`) e o registro público, isso criou a cadeia crítica de vazamento (F4-01).

A causa raiz **não é um bug** — é a **ausência de uma classificação formal** sobre o que é dado corporativo e o que é dado de contrato. Este documento estabelece essa classificação.

---

## 2. PRINCÍPIO ORGANIZADOR

> **Todo dado do SGC pertence a exatamente uma de três classes de escopo. O escopo da classe — não a role do usuário — determina a regra de visibilidade base.**

```
┌──────────────────────────────────────────────────────────────┐
│  CLASSE A — CORPORATIVO PURO                                  │
│  Não pertence a nenhum contrato. Visão da empresa.           │
│  → Visível apenas a Financeiro, Diretoria e Admin.           │
│  Ex.: endividamento, custos fixos corporativos, folha,       │
│       plano de contas, usuários, auditoria, configurações.   │
├──────────────────────────────────────────────────────────────┤
│  CLASSE B — PROJECT-SCOPED (de contrato)                     │
│  Pertence a um project_id obrigatório.                       │
│  → Respeita project_users. Gestor vê só os seus contratos.   │
│  Ex.: receitas, alocações, custos do projeto, uso de         │
│       veículos/colaboradores no contrato, NFs de contrato.   │
├──────────────────────────────────────────────────────────────┤
│  CLASSE C — HÍBRIDO (corporativo vinculável a contrato)      │
│  project_id é OPCIONAL.                                       │
│  → Se vinculado: visível ao gestor do contrato + Financeiro. │
│  → Se não vinculado: visível apenas a Financeiro/Diretoria.  │
│  Ex.: contas a pagar, contas a receber, antecipações,        │
│       borderôs (alguns têm vínculo de projeto, outros não).  │
└──────────────────────────────────────────────────────────────┘
```

A **regra de ouro do híbrido (Classe C)** resolve a tensão atual:
- O gestor de contrato passa a ver as contas a pagar/receber **dos seus contratos** (hoje ele vê tudo ou depende do bypass) — ganho de pertinência.
- A **agregação corporativa** (total a pagar da empresa, fluxo de caixa consolidado, itens sem projeto) fica restrita a Financeiro/Diretoria — fecha o vazamento.

---

## 3. PERSONAS E SEUS DIREITOS

| Persona | Escopo de dados | O que vê | O que NÃO vê |
|---------|-----------------|----------|--------------|
| **Gestor de Contrato** | Seus projetos (`project_users`) | Receitas, custos, margem, colaboradores alocados, veículos, contas a pagar/receber **dos seus contratos**, NFs do contrato, indicadores do contrato | Endividamento, custos fixos corporativos, folha global, contratos de terceiros, consolidado da empresa |
| **Financeiro** | Corporativo + todos os contratos (para fins financeiros) | Todo o fluxo de caixa (pagar/receber/NF/antecipação/borderô), endividamento, custos fixos, plano de contas, dashboards financeiros consolidados | Edição da estrutura operacional do projeto (alocações, escopo técnico); dados de RH além do necessário (PIX/folha sob permissão dedicada) |
| **Diretoria** | Global, predominantemente leitura | Tudo consolidado: dashboards globais, ROI/indicadores director, ranking de contratos, posição financeira | (acesso amplo; restrição é de *escrita*, não de *leitura*) |
| **RH / Pessoal** | Corporativo de pessoas | Cadastro de colaboradores, folha, PIX, encargos | Dados financeiros de contratos, endividamento |
| **Admin / TI** | Sistema | Usuários, permissões, configurações, auditoria | (dados de negócio só se também tiver papel de negócio) |
| **Consulta / Auditor interno** | Conforme atribuição explícita | Apenas leitura do que for concedido | Qualquer escrita; financeiro corporativo **não** por padrão |

> **Mudança-chave de política:** o preset `CONSULTA` **deixa de conceder automaticamente** visão financeira corporativa e dados de folha. Acesso financeiro corporativo passa a ser concessão **deliberada**, não default.

---

## 4. CLASSIFICAÇÃO DOS MÓDULOS

### 4.1 Matriz de escopo (decisão central)

| Módulo / Dado | Classe | Escopo base | Justificativa |
|---------------|:------:|-------------|---------------|
| **Projetos** (cadastro, lifecycle) | B | project_users | Núcleo do contrato |
| **Receitas / Faturamento** | B | project_users | Receita é sempre de um contrato |
| **Alocações de colaboradores** | B | project_users | Alocação é por contrato |
| **Uso de veículos** (no projeto) | B | project_users | Operação do contrato |
| **Custos operacionais do projeto** (labor, sistema, fixos do projeto) | B | project_users | Custo do contrato |
| **Indicadores do contrato** (ROI por projeto) | B | project_users | Performance do contrato |
| **Contas a Pagar** | C | híbrido (project_id opcional) | Algumas são de contrato (subcontratado, material), outras corporativas (impostos, overhead) |
| **Contas a Receber / NFs** | C | híbrido | NF de cliente está ligada a um contrato; manuais podem ser corporativas |
| **Antecipações / Borderôs** | C | híbrido | Seguem a NF de origem; agregação é tesouraria |
| **Endividamento corporativo** | A | corporativo | Empréstimos/financiamentos da PJ, sem contrato |
| **Custos fixos corporativos** | A | corporativo | Aluguel, overhead — rateado, não de um contrato |
| **Folha / Custo de pessoal corporativo** | A | corporativo (RH) | Dado sensível de pessoas |
| **Colaboradores — cadastro** (nome, tipo) | A* | corporativo (RH) | Cadastro é corporativo; *alocação* é Classe B |
| **Colaboradores — PIX / salário** | A | corporativo (RH, permissão dedicada) | LGPD — segregar (achado F5-01) |
| **Veículos — frota (cadastro)** | A* | corporativo (patrimônio) | Frota é da empresa; *uso* é Classe B |
| **Ativos / EPIs** | A | corporativo (patrimônio) | Patrimônio da empresa; atribuição é registro, não escopo de contrato |
| **Plano de contas** | A | corporativo | Estrutura contábil |
| **Dashboard de projetos** | B/agregado | project_users (consolida só os visíveis) | Soma apenas contratos do usuário |
| **Dashboard financeiro consolidado** | A | corporativo | Visão de tesouraria |
| **Indicadores globais / ROI director / ranking** | A | corporativo | Consolidado da empresa |
| **Relatórios** | herda | escopo do dado-fonte | Relatório respeita o escopo do que exporta |
| **Usuários / Roles / Permissões** | A | sistema | Administração |
| **Configurações** | A | sistema | Parâmetros globais |
| **Auditoria** | A | sistema (concessão explícita) | Trilha; `audit.export` já é explicit-only |

\* "A*" = o **cadastro** é corporativo, mas o **vínculo operacional** (alocação/uso) é Classe B. Ou seja: um gestor de contrato vê *que* o colaborador X está alocado no seu projeto, mas não acessa a folha/PIX dele (Classe A).

### 4.2 A regra do híbrido (Classe C) — detalhamento

Para contas a pagar, receber, NFs, antecipações e borderôs:

```
Visibilidade de um registro híbrido R para o usuário U:

  SE U é Financeiro/Diretoria/Admin (permissão corporativa financeira)
     → vê R sempre (com ou sem project_id)

  SENÃO SE R.project_id ∈ projetos_de(U)   (via project_users)
     → vê R (é uma conta do contrato dele)

  SENÃO
     → não vê R

Agregações corporativas (total a pagar da empresa, fluxo consolidado,
itens com project_id nulo) exigem permissão corporativa financeira.
```

Isso transforma o comportamento atual (financeiro 100% global para qualquer `*.view`) em um modelo de **dois níveis**: nível-contrato (gestor) e nível-corporativo (financeiro/diretoria).

---

## 5. MODELO DE PERMISSÕES PROPOSTO

### 5.1 Conceito: separar **escopo** de **ação**

O sistema atual mistura escopo e ação em um só código (`payables.view` = "ver todas as contas a pagar"). A arquitetura futura separa:

- **Permissão de ação** — o que pode fazer (view/edit/delete).
- **Permissão de escopo** — sobre qual conjunto de dados (contrato vs corporativo).

Exemplo conceitual (nomes ilustrativos, não para implementação imediata):

| Permissão de ação | + Escopo "contrato" | + Escopo "corporativo" |
|-------------------|---------------------|------------------------|
| `payables.view` | vê contas a pagar **dos seus contratos** | + vê contas **corporativas** e agregados |
| `receivables.view` | vê NFs **dos seus contratos** | + vê tesouraria consolidada |
| `indicators.view` | ROI **dos seus contratos** | `indicators.director` → ranking global |

A permissão de escopo corporativo financeiro poderia ser um código único, ex.: **`finance.corporate.access`**, concedido apenas a Financeiro/Diretoria. Sem ela, as permissões financeiras operam **restritas aos contratos do usuário** (Classe C nível-contrato).

> Observação: o sistema já tem precedente desse padrão — `dashboard.director` / `indicators.director` distinguem visão consolidada da visão de contrato. A proposta generaliza esse padrão para todo o financeiro.

### 5.2 Permissões de dados sensíveis (LGPD)

Criar segregação explícita para dados de folha/PIX (achado F5-01):

| Permissão | Concede |
|-----------|---------|
| `employees.view` | cadastro básico (nome, tipo, alocação) — pode ir a gestores de contrato |
| `payroll.view` (nova) | salário, encargos, overrides de folha — apenas RH/Diretoria |
| `payroll.pix.view` (nova) | chave PIX — mínimo necessário (RH/Financeiro de pagamento) |

Assim, gestor de contrato vê *quem* trabalha no contrato sem ver *quanto* ganha.

### 5.3 Permissões explicit-only (manter e expandir)

O padrão `EXPLICIT_GRANT_ONLY` atual (`invoices.reactivate`, `audit.export`) é correto. Expandir para:
- `finance.corporate.access` — não herdar por preset; concessão deliberada.
- `payroll.view` / `payroll.pix.view` — idem.
- `users.grant_admin` (nova) — separar "gerenciar usuários" de "conceder ADMIN", fechando o achado F4-04 (auto-escalação).

---

## 6. MAPA DE ROLES-ALVO (presets)

| Permissão / escopo | Gestor Contrato | Financeiro | Diretoria | RH | Admin |
|--------------------|:---:|:---:|:---:|:---:|:---:|
| Projetos (view/edit dos seus) | ✅ | 👁️ | 👁️ | — | ✅ |
| Receitas/custos do contrato | ✅ | 👁️ | 👁️ | — | ✅ |
| Indicadores do contrato | ✅ | 👁️ | 👁️ | — | ✅ |
| `finance.corporate.access` | — | ✅ | ✅ | — | ✅ |
| Contas a pagar/receber (contrato) | 👁️ | ✅ | 👁️ | — | ✅ |
| Endividamento / custos fixos corp. | — | ✅ | 👁️ | — | ✅ |
| Dashboard financeiro consolidado | — | ✅ | ✅ | — | ✅ |
| `indicators.director` (ranking global) | — | 👁️ | ✅ | — | ✅ |
| Colaboradores — cadastro | 👁️ | — | 👁️ | ✅ | ✅ |
| `payroll.view` / `payroll.pix.view` | — | parcial¹ | 👁️ | ✅ | ✅ |
| Frota / Ativos / EPIs | 👁️² | — | 👁️ | — | ✅ |
| Usuários / Roles | — | — | — | — | ✅ |
| `users.grant_admin` | — | — | — | — | ✅ (explicit) |
| Configurações | — | — | 👁️ | — | ✅ |
| Auditoria (`audit.export`) | — | — | 👁️ (explicit) | — | ✅ (explicit) |

Legenda: ✅ ler+escrever · 👁️ somente leitura · — sem acesso
¹ Financeiro de pagamento pode precisar de `payroll.pix.view` para liquidar PIX, sem ver salário.
² Gestor de contrato vê ativos/veículos **atribuídos ao seu contrato**, não o patrimônio inteiro.

---

## 7. PONTOS DE DECISÃO PARA O NEGÓCIO

Estas perguntas precisam de resposta da liderança antes de qualquer implementação:

1. **Gestor de contrato deve ver as contas a pagar/receber dos seus contratos?**
   _Recomendação: sim (Classe C nível-contrato)._ Isso dá autonomia de acompanhamento financeiro do contrato sem expor a empresa.

2. **Gestor de contrato pode ver a margem/lucratividade do próprio contrato?**
   _Recomendação: sim._ É essencial para gestão de contrato. (Hoje já é, via dashboard de projeto.)

3. **Financeiro precisa editar a estrutura operacional do projeto (alocações, escopo técnico)?**
   _Recomendação: não._ Financeiro tem leitura ampla, escrita restrita ao financeiro. Evita conflito de responsabilidade.

4. **Quem pode ver salário e PIX?**
   _Recomendação: segregar em `payroll.view` / `payroll.pix.view`, restrito a RH/Diretoria (+ PIX para tesouraria de pagamento)._ Crítico para LGPD.

5. **Contas a pagar sem `project_id` (impostos, overhead) — corporativas?**
   _Recomendação: sim, Classe A dentro do híbrido._ Só Financeiro/Diretoria.

6. **Diretoria tem escrita ou é read-only consolidado?**
   _Recomendação: predominantemente leitura;_ escrita por exceção, via role específica.

7. **"Conceder ADMIN" deve ser separado de "gerenciar usuários"?**
   _Recomendação: sim (`users.grant_admin` explicit-only)._ Fecha a auto-escalação (F4-04).

---

## 8. IMPACTO NO MODELO DE DADOS (observações, não migrations)

Para suportar o modelo, o esquema atual já está **majoritariamente pronto**:

- `payable_snapshots.project_id`, `receivable_invoices.project_id`, `payables.project_id` já são **nuláveis** → suportam Classe C nativamente.
- `project_users` já existe e é a fonte de verdade do escopo de contrato.
- Falta apenas: (a) novos códigos de permissão; (b) ajuste das funções de autorização para aplicar a regra do híbrido; (c) remoção do bypass financeiro global; (d) revisão dos presets de role.

Itens que merecem avaliação futura (sem decisão agora):
- Custos fixos corporativos têm `cost_center` estruturado — poderiam, no futuro, ser rateados por contrato (transformando parte da Classe A em visão derivada). **Fora de escopo desta arquitetura.**
- Antecipações/borderôs herdam o `project_id` da NF de origem — confirmar que a regra do híbrido propaga corretamente nesses agregados.

---

## 9. CONSISTÊNCIA COM A AUDITORIA

Esta arquitetura resolve diretamente:

| Achado | Como é endereçado |
|--------|-------------------|
| F4-01 (cadeia de vazamento) | Preset CONSULTA deixa de conceder financeiro corporativo + folha |
| F4-02 (IDOR payables) | Payables entram na regra do híbrido (escopo por contrato/corporativo) |
| F4-03 (IDOR receivables com project_id) | `finance.corporate.access` separa visão global da por-contrato |
| F4-04 (auto-escalação) | `users.grant_admin` explicit-only |
| F4-05 (financeiro global por design) | **Decisão formalizada:** financeiro é híbrido, não global por default |
| F5-01 (PIX/salário expostos) | `payroll.view` / `payroll.pix.view` dedicadas |

---

## 10. RESUMO EXECUTIVO DA ARQUITETURA

1. **Três classes de escopo** (Corporativo / Project-scoped / Híbrido) classificam todo dado do sistema.
2. **Financeiro passa a ser híbrido**, não global: gestor vê contas do seu contrato; agregação corporativa exige `finance.corporate.access`.
3. **Separar escopo de ação** nas permissões — o mesmo `payables.view` rende escopo de contrato ou corporativo conforme a permissão de escopo do usuário.
4. **Segregar dados sensíveis de RH** (folha, PIX) em permissões dedicadas (LGPD).
5. **Separar concessão de ADMIN** da gestão de usuários.
6. **Três personas de negócio** bem definidas: Gestor de Contrato (escopo), Financeiro (corporativo financeiro), Diretoria (consolidado/leitura) — mais RH e Admin transversais.
7. O **modelo de dados atual já suporta** o desenho; a mudança é de regras de autorização e presets, não de schema.

---

*Documento de design. Nenhuma alteração de código, migration ou banco foi feita. A implementação depende das decisões da Seção 7 e deve seguir o roadmap da Fase 11 (bloco de 30 dias para os itens de segurança que dependem desta classificação).*
