# Jurídico — arquitetura da gestão operacional do contencioso

**Versão 2** · documento de arquitetura · **nenhuma linha de código escrita**
Estado analisado: `3c3346e` (29/08/2026) · 148 processos e 159 pessoas em produção
A versão 1 permanece no histórico do git (`docs/JURIDICO_ARQUITETURA_OPERACIONAL.md` em `3c3346e`).

---

## 0. O que mudou da versão 1

O feedback derrubou quatro decisões minhas e acrescentou três eixos que faltavam.
Registro aqui o que mudou e por quê, porque a diferença entre as versões é o próprio
raciocínio de projeto.

| Na v1 | Na v2 | Motivo |
|---|---|---|
| `legal_movements` (andamentos) + `legal_events` (agenda) como entidades irmãs | **Timeline de fatos** + **Eventos** (compromissos), com papéis distintos | Andamento e audiência não são a mesma coisa: um é fato passado, o outro é compromisso com data. Confundi-los gerava duas listas concorrentes |
| Agenda especializada em audiências | **Evento genérico** — audiência, perícia, sessão arbitral, reunião, prazo processual, prazo interno, vencimento de parcela, diligência, tarefa. Calendário é *visualização* | Sua observação: não criar estrutura só para audiências |
| `legal_tasks` como entidade separada | **Absorvida por eventos** (tipo `PRAZO_INTERNO` / `TAREFA`) | Pelo mesmo princípio: providência é um compromisso com responsável e data |
| Dois eixos de estado | **Três eixos**: processual, **operacional (pipeline da equipe)** e financeiro | Sua observação: o rito do tribunal não descreve como a equipe conduz o caso |
| Acordo com status `EM_NEGOCIACAO` | **Negociação → Propostas → Acordo**, entidades distintas | Sua observação: negociação é uma fase com idas e vindas, não um estado do acordo |
| Um responsável (`responsible_user_id`) | **Papéis múltiplos e datados** (jurídico, RH, financeiro, advogado externo, preposto) | Sua observação |
| `legal_payments` | **Lançamentos financeiros com direção e recuperabilidade** | Depósito recursal e bloqueio são dinheiro que sai e *pode voltar*. Tratá-los como pagamento erra o custo do contencioso |
| Dashboards | **Central de alertas** como tela principal; dashboards em segundo plano | Sua observação |

**Conceitos novos que proponho** (§13): prescrição bienal como radar de risco, provisão contábil
por competência, tempo em etapa (SLA), depósitos e garantias, reversões explícitas, checklist de
completude, custo total do contencioso e métricas de negociação.

---

## 1. Princípios

1. **O processo é uma linha do tempo, não uma ficha.** O cadastro guarda identidade e
   classificação; a vida do processo é uma sequência de fatos datados.
2. **Fato e compromisso são coisas diferentes.** Fato aconteceu (timeline). Compromisso tem data
   e pode ser futuro (evento). O calendário é uma visualização de eventos; a timeline é a
   história oficial.
3. **Três eixos independentes de estado**: onde o processo está no rito (processual), como a
   equipe está conduzindo (operacional) e o que devemos (financeiro).
4. **Toda informação tem procedência.** Cada fato registra de onde veio — manual, carga inicial,
   publicação, integração. É isso que permite automação futura conviver com registro manual.
5. **Nada é excluído; tudo é revertido.** Bloqueio liberado, depósito levantado, acordo rompido:
   todos são fatos novos que apontam para o anterior.
6. **O SGC é a fonte oficial após a carga.** A planilha é o marco zero e se encerra ali.
7. **O jurídico conversa com os outros workspaces.** RH origina, jurídico conduz, financeiro
   paga, contabilidade provisiona, diretoria acompanha.
8. **Valor é dado sensível**, e bloqueio em conta pessoal de sócio é o dado mais sensível do
   módulo.

---

## 2. A timeline como centro

### O que é

Uma tabela **append-only** — `legal_timeline` — com uma linha por fato relevante do processo,
em ordem cronológica. É a tela principal do processo e o histórico oficial.

```
06/03/2026  ⚖  DISTRIBUIÇÃO      Processo distribuído na 3ª Vara do Trabalho de Campinas
14/03/2026  📄  DOCUMENTO         Contestação protocolada                        [anexo]
02/04/2026  📅  EVENTO REALIZADO  Audiência inicial — sem acordo
02/04/2026  ↻  ESTADO            Processual: EM_INSTRUCAO → AGUARDANDO_SENTENCA
18/04/2026  💬  PROPOSTA          Empresa propôs R$ 28.000 em 4x — recusada
30/04/2026  💬  PROPOSTA          Empresa propôs R$ 41.500 em 6x — aceita
05/05/2026  🤝  ACORDO            Homologado: R$ 41.500 em 6 parcelas
10/06/2026  💰  PAGAMENTO         Parcela 1/6 — R$ 6.916,67
22/06/2026  🔒  BLOQUEIO          SISBAJUD R$ 12.400 — conta Itaú ****4471
```

### A regra que mantém o modelo íntegro

> **A timeline nunca é a fonte do fato. Ela é a projeção ordenada dos fatos.**

Um pagamento vive na tabela de lançamentos financeiros; a linha na timeline **aponta** para ele
(`ref_type` + `ref_id`). Isso evita a armadilha clássica de transformar o histórico num
depósito de texto solto, onde não se soma nada e não se corrige nada.

A exceção é a **nota**: um comentário da equipe cujo fato *é* a própria entrada.

### Estrutura

| Campo | Papel |
|---|---|
| `case_id`, `occurred_at` | O processo e quando o fato ocorreu (não quando foi digitado) |
| `entry_type` | DISTRIBUICAO · ANDAMENTO · PUBLICACAO · EVENTO_REALIZADO · MUDANCA_ESTADO · NEGOCIACAO · PROPOSTA · ACORDO · FINANCEIRO · BLOQUEIO · DOCUMENTO · NOTA · CARGA_INICIAL |
| `title`, `description` | O resumo que aparece na linha e o detalhe |
| `ref_type`, `ref_id` | O fato de origem (pagamento, proposta, evento, bloqueio…) |
| `source` | MANUAL · CARGA_INICIAL · PUBLICACAO · INTEGRACAO · SISTEMA |
| `created_by_id`, `created_at` | Quem registrou e quando |
| `is_milestone` | Marco (distribuição, sentença, acordo, arquivamento) — permite a visão resumida |

**Uma única porta de escrita.** Todo serviço do módulo registra pela mesma função. Se cada
serviço escrever direto na tabela, em seis meses metade dos fatos não estará na timeline — é o
tipo de erosão que só aparece quando já é caro consertar.

### Timeline × trilha de auditoria

Já existe `legal_change_logs`, que registra "o campo X mudou de A para B". Os dois convivem com
públicos diferentes: a **trilha** é técnica e de compliance (quem alterou o quê); a **timeline**
é a história do processo, escrita para quem conduz o caso. Não fundir os dois é deliberado —
misturar "campo `city` alterado" com "sentença publicada" destrói a legibilidade do histórico.

### Carga inicial na timeline

Os 148 processos importados recebem **uma** entrada: `CARGA_INICIAL`, com o texto da última
movimentação do JusBrasil e a data da importação. Não inventamos histórico que não temos — e
fica visível que a vida do processo no SGC começa ali.

---

## 3. Eventos — tudo o que tem data

Uma entidade genérica, `legal_events`, cobre todo compromisso do processo. O calendário, a
agenda da semana e a lista de prazos são **visualizações** dela.

| Campo | Papel |
|---|---|
| `case_id`, `event_type` | AUDIENCIA · PERICIA · SESSAO_ARBITRAL · REUNIAO · PRAZO_PROCESSUAL · PRAZO_INTERNO · VENCIMENTO_PARCELA · DILIGENCIA · TAREFA |
| `scheduled_for` | Quando acontece. **Nulo = backlog** (tarefa sem data marcada) |
| `due_at` | Prazo fatal, quando diferente do agendamento |
| `status` | AGENDADO · REALIZADO · CUMPRIDO · ADIADO · CANCELADO · **PERDIDO** |
| `responsible_id` | Quem responde por ele |
| `location`, `is_virtual`, `link` | Presencial ou telepresencial |
| `outcome`, `outcome_notes` | O que resultou — vira entrada na timeline ao concluir |
| `source_type`, `source_id` | Quando o evento **espelha** outra entidade (ver abaixo) |
| `source` | MANUAL · CARGA_INICIAL · PUBLICACAO · INTEGRACAO |

### Eventos espelhados — a decisão mais delicada desta seção

Vencimento de parcela é um compromisso com data: precisa aparecer no calendário e nos alertas.
Mas o dado verdadeiro é a parcela do acordo.

**Decisão:** o evento é criado, atualizado e cancelado **pelo serviço dono da entidade de
origem** (`source_type = INSTALLMENT`), nunca editado à mão. O ganho é ter uma única superfície
de agenda — calendário e alertas fazem uma consulta só, não uma união de cinco tabelas. O custo
é manter a sincronia; ela fica contida em um ponto do código e coberta por teste.

A alternativa — calendário unindo eventos + parcelas + prazos — evita a duplicação, mas espalha
a lógica de agenda por todas as telas e complica cada novo tipo de compromisso. Prefiro a
primeira, e registro a alternativa porque é uma escolha, não um óbvio.

---

## 4. Os três eixos de estado

### 4.1 Processual — onde o processo está no rito (fato externo)

```
DISTRIBUIDO → EM_INSTRUCAO → AGUARDANDO_SENTENCA → COM_SENTENCA
                                    ↓                    ↓
                              EM_RECURSO ─────────→ EM_EXECUCAO
                                                         ↓
                                            AGUARDANDO_ARQUIVAMENTO → ARQUIVADO
```
`SUSPENSO` é transversal. Muda por andamento, decisão ou publicação — nunca por vontade da
equipe.

### 4.2 Operacional — como a equipe está conduzindo (decisão interna)

```
NOVO → ANALISE → CONTESTACAO → PRODUCAO_DE_PROVAS → NEGOCIACAO → EXECUCAO → PAGAMENTO → ARQUIVADO
```

É um **pipeline (kanban)**, e a diferença em relação ao eixo processual é de dono: o tribunal
governa o primeiro, a equipe governa o segundo. Um processo pode estar `EM_INSTRUCAO` no rito e
`NEGOCIACAO` na condução — que é justamente o caso mais comum.

> **Decisão estrutural: as etapas são dados, não enum.** Uma tabela
> `legal_pipeline_stages` (ordem, nome, cor, SLA em dias, `is_terminal`) permite mudar o fluxo da
> equipe sem migration. E o campo **SLA por etapa** dá, de graça, a resposta genérica para
> "parado há muito tempo" — inclusive "negociações paradas", que deixa de ser uma regra
> especial. Cada processo guarda `stage_id` e `stage_since`; **tempo em etapa** é a métrica
> operacional central.

### 4.3 Financeiro — o que devemos

```
SEM_OBRIGACAO → EM_NEGOCIACAO → ACORDO_HOMOLOGADO → PAGAMENTO_EM_CURSO → QUITADO
                                       ↓                     ↓
                                       └──── INADIMPLENTE ◀──┘
```

Majoritariamente **derivado**: quem move este eixo são as propostas, o acordo e as parcelas.
Digitação manual só para os casos sem acordo (condenação transitada, improcedência).

---

## 5. Negociação, propostas e acordo

O ponto do seu feedback que mais muda o modelo. A negociação é uma **fase com histórico**, não
um estado do acordo.

```
Processo ──1:N── Negociação ──1:N── Proposta ──(aceita)──▶ Acordo ──1:N── Parcela
                     │                                        │              │
              canal, motivo,                            homologação,     vencimento,
              responsável                               cláusula penal      valor
                                                              │              │
                                                              └──────────────┴──▶ Lançamentos
                                                                                  financeiros
```

### `legal_negotiations` — a rodada

| Campo | Papel |
|---|---|
| `case_id`, `opened_at`, `closed_at` | O período da negociação |
| `channel` | DIRETO · AUDIENCIA_CONCILIACAO · CAMARA_ARBITRAL · MEDIACAO · ADVOGADOS |
| `status` | ABERTA · SUSPENSA · ENCERRADA_COM_ACORDO · ENCERRADA_SEM_ACORDO |
| `responsible_id`, `notes` | Quem conduz |
| `last_interaction_at` | Alimenta "negociações paradas há muito tempo" |

Um processo pode ter **várias** negociações ao longo do tempo — a que fracassou em março e a
que reabriu em agosto são rodadas distintas, e comparar as duas é informação de gestão.

### `legal_proposals` — cada proposta da mesa

| Campo | Papel |
|---|---|
| `negotiation_id`, `proposed_at` | A rodada e a data |
| `proposed_by` | EMPRESA · RECLAMANTE · JUIZO · CAMARA |
| `amount`, `installment_count`, `terms` | O que foi oferecido |
| `status` | APRESENTADA · RECUSADA · ACEITA · EXPIRADA · SUBSTITUIDA |
| `rejected_reason` | Por que não fechou — vira aprendizado |

O seu exemplo cabe inteiro: empresa propõe (proposta 1, recusada), melhora (proposta 2,
recusada), vai à câmara arbitral (nova negociação ou mesma rodada com canal atualizado), nova
proposta (aceita) → acordo homologado.

**Métricas que só existem com esse desenho:** desconto obtido sobre o valor da causa, tempo
médio até o acordo, taxa de aceite por canal, quantas rodadas até fechar.

### `legal_agreements` — o acordo

Nasce de uma proposta aceita (`accepted_proposal_id`), com homologação, cláusula penal e status
CUMPRIDO · DESCUMPRIDO · ROMPIDO. As parcelas (`legal_agreement_installments`) saem dele com
vencimento, valor e baixa — e cada uma projeta um evento de vencimento (§3) e um título no
Contas a Pagar (§9).

---

## 6. Dinheiro: o que sai, o que volta e o que está retido

Um erro comum — que eu cometi na v1 — é tratar tudo como "pagamento". Depósito recursal e
bloqueio judicial são **dinheiro que sai do caixa e pode voltar**. Somá-los ao custo do
contencioso infla o prejuízo; ignorá-los esconde o impacto no caixa.

### `legal_financial_entries` — um livro só, com direção

| Campo | Papel |
|---|---|
| `case_id`, `amount`, `occurred_at` | O lançamento |
| `direction` | **SAIDA** (paga, deposita, é bloqueado) · **RETORNO** (levanta, é liberado) |
| `entry_type` | PAGAMENTO_ACORDO · CONDENACAO · CUSTAS · HONORARIOS · PERICIA · DEPOSITO_RECURSAL · DEPOSITO_GARANTIA · LEVANTAMENTO · LIBERACAO_BLOQUEIO · CONVERSAO_BLOQUEIO |
| `recoverable` | Depósito é recuperável; pagamento de acordo não |
| `installment_id`, `restriction_id` | O que este lançamento quita ou libera |
| `reverses_entry_id` | Reversão aponta o lançamento revertido — nunca se apaga |
| `payable_entry_id` | Vínculo com o título no Contas a Pagar |
| `document_id` | Comprovante |

Disso saem, sem cálculo paralelo: **custo efetivo** (saídas não recuperáveis), **capital retido**
(saídas recuperáveis ainda não devolvidas) e **impacto de caixa no mês**.

### `legal_restrictions` — bloqueios e restrições

Como na v1 (SISBAJUD, penhora, arresto, RENAJUD, indisponibilidade, penhora de faturamento),
com alvo separado em `legal_restriction_targets`: conta da empresa, **conta pessoal de sócio**,
veículo, imóvel, recebível. O desfecho — liberação ou conversão em pagamento — é um lançamento
financeiro de RETORNO ou a conversão em SAIDA definitiva, sempre apontando o bloqueio de origem.

---

## 7. Papéis e responsáveis

`legal_case_assignments`: N papéis por processo, **datados**.

| Campo | Papel |
|---|---|
| `case_id`, `role` | RESPONSAVEL_JURIDICO · RESPONSAVEL_RH · RESPONSAVEL_FINANCEIRO · ADVOGADO_EXTERNO · PREPOSTO · ESCRITORIO |
| `user_id` · `person_id` · `law_firm_id` | Interno (usuário do SGC), pessoa externa ou escritório |
| `started_at`, `ended_at` | Histórico: quem respondia pelo caso em cada época |
| `is_primary` | O responsável principal daquele papel |

Três efeitos práticos: **"minha carteira"** (filtro por papel do usuário logado), **alertas
direcionados** a quem de fato responde, e **carga de trabalho por pessoa** — quantos processos
ativos, quantos eventos na semana.

O papel RH é o que amarra o módulo ao ciclo de desligamento (§9).

---

## 8. Central de alertas

A tela principal do workspace passa a ser a central de alertas, não um dashboard.

| Alerta | Regra | Severidade |
|---|---|---|
| Audiências de hoje | eventos de audiência com `scheduled_for` hoje | crítica |
| Audiências da semana | próximos 7 dias | atenção |
| Prazos vencendo | `due_at` dentro do horizonte configurado | atenção |
| **Prazos vencidos** | `due_at` passado e status ≠ cumprido | **crítica** |
| Parcelas vencendo | vencimento nos próximos N dias | atenção |
| **Parcelas atrasadas** | vencidas sem baixa | **crítica** |
| **Bloqueios novos** | restrições ativas criadas há menos de N dias | **crítica** |
| Processos sem movimentação | último fato na timeline há mais de N dias | atenção |
| Negociações paradas | `last_interaction_at` acima do limite | atenção |
| Etapa estourando o SLA | `stage_since` acima do SLA da etapa (§4.2) | atenção |
| Processos incompletos | checklist de completude (§13) | informativa |

### Como isso funciona sem inventar infraestrutura

O sistema **não tem serviço de e-mail nem agendador** — verifiquei. Então:

- **Agora**: os alertas são **calculados por consulta** quando a tela abre. Com 148 processos
  isso é instantâneo, e não há job para quebrar. Os limites (`N` dias) ficam em
  `legal_alert_rules`, configuráveis.
- **`legal_alert_acknowledgements`**: o usuário dá ciência ou adia um alerta, e ele para de
  incomodar até a data escolhida. Sem isso, uma central de alertas vira ruído em duas semanas e
  a equipe passa a ignorá-la — é o modo de falha mais comum desse tipo de tela.
- **Depois**: quando houver agendador e canal (e-mail, WhatsApp), um job lê **as mesmas regras**
  e dispara notificação. Nenhuma regra é reescrita; muda apenas o gatilho.

---

## 9. Integração com o restante do SGC

O ciclo que você descreveu, com o ponto de contato de cada workspace:

```
   RH                    JURÍDICO                FINANCEIRO           CONTABILIDADE        DIRETORIA
   │                        │                        │                     │                   │
desligamento ──┐            │                        │                     │                   │
(employees.    │            │                        │                     │                   │
 end_date)     └──▶ processo nasce                   │                     │                   │
                    (vínculo employee_id)            │                     │                   │
                            │                        │                     │                   │
                    conduz: timeline,                │                     │                   │
                    eventos, negociação              │                     │                   │
                            │                        │                     │                   │
                    acordo homologado ──▶ parcela vira título              │                   │
                            │             no CAP (origem LEGAL)            │                   │
                            │                        │                     │                   │
                            │                   pagamento ──▶ baixa a parcela                  │
                            │                        │                     │                   │
                    risco classificado ──────────────┴──▶ provisão por competência             │
                            │                                              │                   │
                            └──────────────────────────────────────────────┴──▶ passivo, custo,
                                                                                 desembolso
```

**RH → Jurídico.** `legal_persons` já prevê vínculo opcional com `employees` (está escrito no
próprio modelo). Formalizar esse vínculo destrava o **radar de prescrição** (§13): desligados
sem processo, ordenados pela proximidade dos dois anos.

**Jurídico → Financeiro.** Parcela homologada vira título no Contas a Pagar pela origem `LEGAL`,
idempotente por `(origem, referência, competência)` — a mesma mecânica de Custos Fixos e
Endividamento. A baixa no CAP retorna para a parcela. Você já concordou com esse ponto; ele é
pré-requisito da Fase B.

**Jurídico → Contabilidade.** `legal_provisions`: valor provisionado por processo e competência,
derivado do risco (provável/possível/remota) com percentuais configuráveis. Série histórica
mensal.

**Jurídico → Projetos.** Hoje `legal_projects` é um catálogo de texto, sem ligação com os
projetos reais do SGC. Ligá-lo a `projects.id` permite responder **quanto o contencioso de uma
obra custou** — informação de precificação para uma empresa que vende contratos de mão de obra.

**Jurídico → Indicadores.** Passivo, provisão e desembolso entram nos dashboards executivos já
existentes (ECharts), sem tela nova.

---

## 10. O SGC como fonte oficial

Virar fonte oficial não é uma frase no documento: são três mecanismos.

**1. Corte explícito da carga.** Um marco no módulo (`legal_source_cutover_at`) separa o antes
do depois. Depois dele, a importação da planilha fica **desabilitada por padrão** — reabri-la
exige ação administrativa consciente e registrada. Sem isso, um dia alguém reimporta a planilha
antiga e sobrescreve meses de operação.

**2. Procedência em todo fato.** `source` em timeline, eventos e lançamentos distingue o que
veio da carga, do registro manual, de uma publicação ou de uma integração. É o que permite
confiar em números mistos e, no futuro, deixar automação e digitação convivendo.

**3. Completude como métrica visível.** Um processo importado tem 8 campos preenchidos; um
processo operado tem responsáveis, etapa, eventos e timeline. O checklist de completude (§13)
mostra a diferença e é o termômetro de que o módulo virou operação de verdade — não uma tela
nova em cima do mesmo dado velho.

---

## 11. Modelo completo

```
                    ┌──────────────────┐        ┌────────────────────┐
   RH: employees ───│  legal_persons   │        │   legal_law_firms  │
                    │ + person_type    │        │  escritórios       │
                    │ + employee_id    │        └─────────┬──────────┘
                    └────────┬─────────┘                  │
                             │                            │
                    ┌────────▼────────────────────────────▼──────────┐
                    │            legal_case_assignments              │
                    │  papéis datados: jurídico, RH, financeiro,     │
                    │  advogado externo, preposto, escritório        │
                    └────────────────────┬───────────────────────────┘
                                         │
   ┌───────────────┐          ┌──────────▼──────────┐         ┌──────────────────┐
   │legal_companies│──────────│    legal_cases      │─────────│  legal_projects  │
   └───────────────┘          │  ─────────────────  │         │  → projects.id   │
                              │ procedural_status   │         └──────────────────┘
   ┌───────────────┐          │ stage_id + since  ──┼──▶ legal_pipeline_stages
   │legal_case_    │──────────│ financial_status    │         (etapas configuráveis + SLA)
   │  parties      │          │ risk_level · phase  │
   └───────────────┘          │ secrecy             │
                              └──┬────┬────┬────┬───┘
        ┌────────────────────────┘    │    │    └────────────────────┐
        │                             │    │                         │
┌───────▼────────┐          ┌─────────▼──┐ │              ┌──────────▼─────────┐
│ legal_timeline │◀─────────│legal_events│ │              │ legal_restrictions │
│ FATOS          │  projeta │COMPROMISSOS│ │              │ bloqueios, penhoras│
│ append-only    │          │ agenda,    │ │              └──────────┬─────────┘
│ ref → o fato   │          │ prazos,    │ │                         │
└───────┬────────┘          │ tarefas    │ │              ┌──────────▼─────────┐
        │                   └────────────┘ │              │legal_restriction_  │
        │ projeta                          │              │  targets           │
        │                                  │              │ conta empresa ·    │
┌───────┴──────────────────────────────────▼─────────┐    │ conta sócio ·      │
│  legal_negotiations ──1:N── legal_proposals        │    │ veículo · imóvel   │
│         └──(aceita)──▶ legal_agreements            │    └────────────────────┘
│                    └──1:N── installments           │
└────────────────────────────┬───────────────────────┘
                             │
                  ┌──────────▼────────────┐        ┌────────────────────┐
                  │legal_financial_entries│───────▶│  payable_snapshots │
                  │ SAIDA / RETORNO       │ origem │  (Contas a Pagar)  │
                  │ recuperável ou não    │ =LEGAL └────────────────────┘
                  └───────────────────────┘
                             │
                  ┌──────────▼────────────┐        ┌────────────────────┐
                  │   legal_provisions    │        │  legal_documents   │
                  │ por competência       │        │  anexos (volume)   │
                  └───────────────────────┘        └────────────────────┘

     Transversais: legal_alert_rules · legal_alert_acknowledgements · legal_change_logs
```

**Entidades novas (16):** `legal_timeline`, `legal_events`, `legal_pipeline_stages`,
`legal_case_assignments`, `legal_negotiations`, `legal_proposals`, `legal_agreements`,
`legal_agreement_installments`, `legal_financial_entries`, `legal_restrictions`,
`legal_restriction_targets`, `legal_case_parties`, `legal_documents`, `legal_law_firms`,
`legal_provisions`, `legal_alert_rules` (+ `legal_alert_acknowledgements`).

**Mudanças no `legal_cases`:** ganha `procedural_status`, `stage_id`/`stage_since`,
`financial_status`, `phase`, `risk_level`, `secrecy`, `employee_id`, `company_id`/`project_id`
normalizados e as colunas derivadas de leitura rápida — `last_timeline_at`, `next_event_at`,
`open_alerts_count`. Perde `status`, `hearing_date`, `last_movement*`, `agreement_terms` e os
valores digitados, que passam a ser derivados.

> As três colunas derivadas são denormalização deliberada: ordenar 148 processos por "parado há
> mais tempo" ou "próximo compromisso" sem elas exigiria subconsulta por linha. Regra: são
> mantidas por um único serviço, e qualquer divergência é resolvida recalculando a partir dos
> fatos — nunca editando a coluna.

---

## 12. Escalabilidade: o que decidimos agora e o que isso destrava

| Decisão estrutural agora | Destrava depois |
|---|---|
| Timeline append-only com `source` e `ref` polimórfico | **Captura de publicações** e **integração com tribunais** escrevem na timeline como qualquer outro fato — sem redesenho |
| Idempotência por chave natural em toda ingestão (número CNJ + hash do andamento) | Publicação capturada duas vezes não duplica — pré-requisito de qualquer integração |
| `case_number` no padrão CNJ, com tribunal/vara/ano derivados | **JusBrasil, PJe e DataJud** são endereçados por esse número |
| Regras de alerta em tabela, não em código | **Notificações automáticas** quando houver agendador: mesmo motor, outro gatilho |
| Etapas do pipeline como dados | Mudar o fluxo da equipe sem migration |
| Timeline como fonte única do histórico textual | **IA para resumir processo**: um input só, já ordenado e com procedência |
| Papéis datados incluindo escritório externo | **Gestão de escritórios terceirizados** e, mais adiante, acesso externo restrito |
| `legal_provisions` por competência **desde a Fase D** | **Provisão contábil** e indicadores executivos com série histórica — que **não pode ser reconstruída depois**: se não registrarmos mês a mês, o histórico não existe |
| Documentos com categoria e vínculo ao fato | OCR e extração automática no futuro |

O item da provisão é o que mais me preocupa em adiar: todos os outros podem ser acrescentados
quando forem necessários; a série histórica, não — ela só existe se começar a ser gravada.

---

## 13. Conceitos que proponho e ainda não discutimos

**1. Prescrição bienal como radar de risco.** Na Justiça do Trabalho o ex-empregado tem dois
anos após o desligamento para ajuizar. Com o vínculo `employees ↔ legal_persons`, o módulo
mostra: desligados nos últimos 24 meses **sem processo**, ordenados pela data-limite. É
prevenção — e hoje ninguém no sistema tem essa visão.

**2. Provisão contábil por competência.** §9 e §12.

**3. Tempo em etapa (SLA).** §4.2 — resposta genérica a "parado há muito tempo".

**4. Depósitos, garantias e capital retido.** §6 — dinheiro que sai e pode voltar.

**5. Reversões explícitas.** Acordo rompido, bloqueio liberado, depósito levantado, pagamento
estornado: todos são fatos novos apontando o anterior (`reverses_entry_id`). Nunca `UPDATE` que
apaga o passado — a regra que o módulo já adota para exclusão.

**6. Checklist de completude.** Um processo ativo deveria ter responsável jurídico, etapa, valor
da causa, classificação de risco e ao menos um evento futuro. O que falta vira alerta
informativo e uma barra de completude na lista. É o termômetro da §10.

**7. Custo total do contencioso.** Acordo + custas + honorários + perícia + depósitos não
devolvidos, agregável por processo, projeto/obra, escritório e período. Hoje só existe "valor
pago do acordo".

**8. Métricas de negociação.** Desconto sobre o valor da causa, tempo até o acordo, taxa de
aceite por canal, número de rodadas. Saem de graça do modelo de propostas.

**9. Carteira por papel.** "Meus processos" filtrando por papel do usuário — o jurídico vê os
seus, o RH vê os que originou, o financeiro vê os que têm parcela a pagar.

**10. Modelos de eventos por rito.** Ao distribuir um processo trabalhista, criar
automaticamente os compromissos típicos (contestação, audiência inicial). Um catálogo simples
de "checklists de abertura" evita esquecimento — e é barato depois que eventos existem.

---

## 14. Telas

| Tela | Papel |
|---|---|
| **Central de alertas** | Entrada do workspace: o que exige ação hoje, agrupado por severidade |
| **Processo — timeline** | Tela principal do caso: histórico cronológico + registrar fato + painel lateral com estados, papéis, valores e próximos compromissos |
| **Pipeline (kanban)** | Processos por etapa operacional, com tempo em etapa e arrastar para mover |
| **Agenda / calendário** | Visualização dos eventos por semana e mês, filtrável por tipo e responsável |
| **Lista de processos** | A tela atual, com os filtros novos (etapa, risco, responsável, completude) |
| **Negociações** | Rodadas abertas e o histórico de propostas |
| **Financeiro do contencioso** | Parcelas a vencer, atrasadas, capital retido e desembolso do mês |
| **Bloqueios** | Restrições ativas por tipo e titular |
| **Passivo** (existente, evoluído) | Visão de diretoria: passivo, provisão, custo total |
| **Administração** | Catálogos, etapas do pipeline, regras de alerta, importação (encerrada após o corte) |

---

## 15. Permissões

Mantido o padrão do módulo — um recurso por menu, verbos padrão, `sensitive` onde há valor:

| Recurso | Observação |
|---|---|
| `legal_timeline` | list, read, create (registrar fato), update |
| `legal_events` | list, read, create, update, delete — cobre agenda, prazos e tarefas |
| `legal_pipeline` | read, update (mover etapa) · `legal_pipeline.configure` para editar etapas |
| `legal_negotiations` | + **sensitive** (valores das propostas) |
| `legal_agreements` | + **sensitive** |
| `legal_financial` | + **sensitive** — lançamentos, parcelas, depósitos |
| `legal_restrictions` | + **sensitive** — o dado mais crítico do módulo |
| `legal_documents` | list, read, create, delete |
| `legal_alerts` | read · `legal_alerts.configure` para as regras |
| `legal_provisions` | read + **sensitive** |

Duas regras que atravessam o módulo: **segredo de justiça** (`secrecy`) restringe a leitura aos
responsáveis do processo, independentemente das demais permissões; e **bloqueio em conta pessoal
de sócio** só para diretoria e jurídico — nunca para perfil de consulta.

---

## 16. Migração dos 148 processos

| Eixo | Regra |
|---|---|
| Processual | Mapeamento direto do status atual (em andamento → `EM_INSTRUCAO`, com decisão → `COM_SENTENCA`, suspenso → `SUSPENSO`, encerrado → `ARQUIVADO`) |
| Financeiro | Acordo → `EM_NEGOCIACAO` · acordo finalizado → `QUITADO` · encerrado → **fila de revisão** (quitado ou sem obrigação) |
| **Operacional** | **Todos entram em `NOVO`**, exceto arquivados. A etapa é o estado do *nosso* trabalho: não dá para inferir da planilha, e chutar seria pior que triar |
| Timeline | Uma entrada `CARGA_INICIAL` por processo, com o texto da última movimentação |
| Acordos | `agreement_terms` (texto) vira acordo + parcelas com **revisão assistida**: a tela sugere a leitura de `"3 X 2.333,34"` e o jurídico confirma |
| Valores | `amount_paid`/`amount_pending` viram lançamento de abertura, para o derivado bater com o histórico |

A triagem inicial (148 processos passando por `NOVO`) é trabalho real da equipe, mas é o
momento em que o acervo importado vira acervo operado — e cada processo ganha responsável,
etapa e próximo compromisso.

---

## 17. Roadmap revisado

| Fase | Entrega | Por que nesta ordem |
|---|---|---|
| **A — Núcleo operacional** | Timeline · eventos · pipeline configurável · papéis · central de alertas · migração e triagem | É o que você usa todo dia, e não toca em dinheiro: o menor risco com o maior ganho |
| **B — Negociação e acordo** | Negociações · propostas · acordos · parcelas · lançamentos financeiros · integração com o CAP | Depende da timeline (§2) e é onde entra o dinheiro |
| **C — Patrimônio** | Bloqueios · alvos · depósitos e garantias · capital retido · painel patrimonial | Depende dos lançamentos financeiros da fase B |
| **D — Integração interna** | Vínculo RH ↔ processo · radar de prescrição · provisão por competência · custo por projeto · indicadores executivos | Depende de acordo e financeiro para ter o que provisionar |
| **E — Automação** | Captura de publicações · notificações · resumo por IA · portal de escritórios | Só faz sentido com a operação rodando e a timeline alimentada |

As decisões estruturais da §12 são tomadas **na fase A**, mesmo que a funcionalidade
correspondente venha na E — é o que evita retrabalho.

---

## 18. Decisões pendentes

Resolvidas pelo seu feedback: acordo integra o CAP · agenda é derivada de eventos · pipeline
operacional entra · negociação separada de acordo · papéis múltiplos · alertas antes de
dashboards.

Ainda em aberto:

1. **Etapas iniciais do pipeline e SLA de cada uma.** Proponho as suas oito
   (Novo → Análise → Contestação → Produção de provas → Negociação → Execução → Pagamento →
   Arquivado). Faltam os prazos esperados por etapa, que alimentam os alertas — quantos dias em
   "Negociação" já é preocupante?
2. **Percentuais de provisão por risco.** Provável = 100%? Possível = 50%? Remota = 0%? É
   definição contábil, e o número muda o passivo publicado.
3. **Identificação da conta bloqueada.** O SGC não tem cadastro de contas bancárias. Registro
   como identificador (banco + final da conta) ou criamos o cadastro?
4. **Honorários de escritório** entram como lançamento do processo (custo total do contencioso)
   ou ficam no financeiro corporativo?
5. **Quem preenche o papel "Responsável RH"** — usuário do SGC ou pessoa externa? Isso define se
   o alerta chega a alguém de fato.
6. **Data do corte da fonte oficial** (§10) e quem pode reabrir a importação.
7. **Notificação por e-mail** exige infraestrutura que o sistema não tem (nem serviço de e-mail
   nem agendador). Fica para a fase E, ou entra antes como projeto próprio?
8. **Radar de prescrição** (§13.1): entra na fase D como proposto, ou é prioritário o suficiente
   para antecipar? É prevenção de passivo novo, não gestão do existente.

---

## 19. Riscos

| Risco | Mitigação |
|---|---|
| A timeline não ser alimentada e o módulo voltar a ser repositório | O alerta "sem movimentação há N dias" é o termômetro, e fica na tela principal. A completude (§13.6) mede o mesmo por outro ângulo |
| Central de alertas virar ruído e ser ignorada | Ciência e adiamento por alerta (§8) desde a primeira versão |
| Triagem dos 148 processos travar a adoção | O sistema é utilizável durante a triagem: processo em `NOVO` funciona, só não tem etapa definida |
| Duplicidade de desembolso entre jurídico e CAP | Origem `LEGAL` idempotente, decidida na fase B antes de qualquer título |
| Evento espelhado sair de sincronia com a parcela | Um único serviço dono da criação/atualização, coberto por teste de regressão |
| Dado de sócio e bloqueio vazando para consulta | `sensitive` próprio + revisão dos presets antes de publicar a fase C |
| Reimportação da planilha sobrescrevendo operação | Corte da fonte oficial (§10) desabilita a importação por padrão |
| Escopo crescer para integração com tribunais antes da operação estar madura | Fase E, explicitamente depois de A–D |

---

## 20. Documentos relacionados

- [`JURIDICO_IMPORTACAO_PLANILHA.md`](JURIDICO_IMPORTACAO_PLANILHA.md) — a carga inicial, que
  permanece válida como marco zero e se encerra no corte da fonte oficial
- [`JURIDICO_RUNBOOK_DEPLOY.md`](JURIDICO_RUNBOOK_DEPLOY.md) — deploy do módulo
- [`SGC_DOCUMENTACAO_COMPLETA.md`](SGC_DOCUMENTACAO_COMPLETA.md) — estado atual do sistema
- [`CHANGELOG.md`](../CHANGELOG.md) — histórico de mudanças
