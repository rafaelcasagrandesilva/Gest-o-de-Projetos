# Jurídico — de repositório do passivo a gestão operacional do contencioso

**Documento de arquitetura. Nenhuma linha de código foi escrita.**
Estado analisado: commit `1f41280` (29/08/2026) · 148 processos e 159 pessoas em produção.

---

## 1. Sumário executivo

O módulo atual responde bem à pergunta **"qual é o nosso passivo?"**. Ele não consegue
responder **"o que precisa ser feito esta semana?"** — e essa é a diferença entre um
repositório e uma ferramenta operacional.

A causa não é falta de telas: é o **modelo de dados**. Hoje um processo é uma linha achatada,
com um único campo de status que mistura situação processual e situação financeira, valores
como colunas escalares, acordo em texto livre, uma única data de audiência e a última
movimentação copiada do JusBrasil. Não existem prazos, providências, bloqueios, parcelas nem
pagamentos.

A proposta é decompor o processo em **eventos ao longo do tempo**, mantendo o cadastro atual
como núcleo. Onze entidades novas, dois eixos de estado independentes, quatro painéis e seis
fluxos de trabalho. A carga inicial (planilha + JusBrasil) permanece como o marco zero: a
partir da implantação, o SGC é a fonte oficial.

---

## 2. O que existe hoje

### Estrutura

| Entidade | Papel | Registros |
|---|---|---|
| `legal_cases` | Processo — todo o dado em colunas na própria linha | 148 |
| `legal_persons` | Ex-colaborador (reclamante) | 159 |
| `legal_companies` · `legal_projects` | Catálogos de apoio | 0 · 0 |
| `legal_import_runs` | Histórico das importações | 1 |
| `legal_change_logs` | Trilha de alterações do módulo | 5 |

O processo carrega hoje: número, URL do JusBrasil, status, tipo, natureza, UF/foro/cidade,
empresa/projeto/cliente **como texto**, reclamante e reclamado, cinco valores
(`amount_claimed`, `considered`, `agreed`, `paid`, `pending`), condições do acordo em texto
livre (`agreement_terms`, ex.: `"3 X 2.333,34"`), última movimentação (texto + data), uma
data de audiência, data de distribuição e observações.

### Acervo por status

| Status atual | Processos | Valor da causa |
|---|---|---|
| EM_ANDAMENTO | 51 | R$ 1.645.832 |
| ENCERRADO | 41 | R$ 1.569.642 |
| COM_DECISAO | 19 | R$ 1.098.658 |
| ACORDO_FINALIZADO | 17 | R$ 667.213 |
| ACORDO | 13 | R$ 937.110 |
| SUSPENSO | 7 | R$ 248.619 |

### O que funciona bem e deve ser preservado

- **A importação como carga inicial**, com idempotência, pré-visualização e histórico.
- **A regra de nunca excluir**: baixa lógica com trilha em `legal_change_logs`.
- **Permissão por menu**, com recurso próprio para cada área do workspace.
- **O eixo de Dados Sensíveis** separando "ver o processo" de "ver os valores".

Nada disso muda. O que muda é o que o processo *contém*.

---

## 3. Por que as nove perguntas não têm resposta hoje

Este é o diagnóstico central — cada pergunta falha por um motivo estrutural diferente.

| Pergunta | Por que não é respondível hoje |
|---|---|
| Quais audiências acontecem esta semana? | `hearing_date` é **um** campo. Guarda uma data, sem tipo, local, resultado ou histórico. Uma segunda audiência sobrescreve a primeira. |
| Quais processos aguardam providência? | **Não existe o conceito.** Não há tarefa, responsável nem prazo em lugar nenhum do módulo. |
| Quais acordos estão em negociação? | `status = ACORDO` cobre da primeira conversa à homologação. Negociação, proposta e acordo assinado são o mesmo valor. |
| Quais acordos aguardam pagamento? | O plano de pagamento é **texto livre** (`"3 X 2.333,34"`). Não há parcela, vencimento nem baixa — logo não há "a vencer" nem "vencido". |
| Quais processos foram quitados mas não arquivados? | Exige cruzar situação **financeira** (quitado) com **processual** (aguardando arquivamento). O campo é único: ACORDO_FINALIZADO e ENCERRADO não se combinam. |
| Quais processos têm bloqueios ativos em contas da empresa? | **Bloqueio judicial não existe** no modelo. |
| Quais processos atingem contas pessoais dos sócios? | Não há bloqueio, não há sócio (`legal_persons` são ex-colaboradores) e não há conta. |
| Qual o valor bloqueado por tipo de restrição? | Idem — não há o que somar. |
| Quais processos estão sem atualização há muito tempo? | `last_movement_date` é a data da movimentação **do JusBrasil na carga inicial**. Ela mede o andamento no tribunal, não a gestão interna, e congela no dia da importação. |

Três causas explicam as nove: **status único para eixos independentes**, **campo escalar
onde o mundo real tem coleção** (audiências, parcelas, bloqueios, providências) e **ausência
de linha do tempo própria**.

---

## 4. Princípios do novo desenho

1. **O processo é um agregado, não uma linha.** O cadastro guarda identidade e classificação;
   o que acontece com ele vira registro datado em tabela filha.
2. **Situação processual e situação financeira são eixos independentes.** Um processo pode
   estar em execução e quitado; encerrado e com bloqueio ativo.
3. **Todo estado tem origem rastreável.** Uma mudança de situação aponta o movimento, a
   decisão ou o pagamento que a causou.
4. **A agenda é derivada, nunca digitada duas vezes.** Audiências, prazos e parcelas são
   entidades próprias; o painel da semana é consulta, não cadastro paralelo.
5. **O financeiro do jurídico conversa com o financeiro da empresa.** Pagamento de acordo
   vira título no Contas a Pagar pelo mesmo mecanismo de origem já usado por Custos Fixos e
   Endividamento — sem terceira contabilidade.
6. **Valor é dado sensível.** Bloqueio, acordo e pagamento nascem sob `*.sensitive`.
7. **Nada é excluído.** Baixa lógica e trilha, como hoje.

---

## 5. Modelo de domínio proposto

```
                          ┌───────────────────┐
                          │   legal_persons   │  ← ganha person_type
                          │ (pessoa / sócio / │    (EX_COLABORADOR, SOCIO,
                          │  terceiro)        │     TERCEIRO, ADVOGADO)
                          └─────────┬─────────┘
                                    │
                       ┌────────────▼────────────┐
                       │   legal_case_parties    │  N:N com papel
                       │ (reclamante, reclamada, │
                       │  terceiro, sócio)       │
                       └────────────┬────────────┘
                                    │
   ┌──────────────┐      ┌──────────▼──────────┐      ┌─────────────────────┐
   │legal_companies│─────│    legal_cases      │──────│   legal_projects    │
   │ (grupo M&E)  │      │  PROCESSO (núcleo)  │      │ (obra / contrato)   │
   └──────────────┘      │ ─────────────────── │      └─────────────────────┘
                         │ procedural_status   │
                         │ financial_status    │
                         │ phase · risk_level  │
                         │ responsible_user_id │
                         └──┬───┬───┬───┬───┬──┘
        ┌───────────────────┘   │   │   │   └───────────────────┐
        │           ┌───────────┘   │   └────────┐              │
        ▼           ▼               ▼            ▼              ▼
┌───────────────┐ ┌──────────────┐ ┌───────────┐ ┌──────────────────┐ ┌──────────────┐
│legal_movements│ │ legal_events │ │legal_tasks│ │legal_restrictions│ │legal_documents│
│ andamentos    │ │ audiências,  │ │providências│ │ bloqueios,       │ │ petições,    │
│ (linha do     │ │ perícias,    │ │ + prazos   │ │ penhoras,        │ │ sentenças,   │
│  tempo)       │ │ reuniões     │ │ (fatais)   │ │ indisponibilidade│ │ comprovantes │
└───────────────┘ └──────────────┘ └───────────┘ └────────┬─────────┘ └──────────────┘
                                                          │
                         ┌────────────────────────────────┘
                         ▼
                  ┌──────────────────┐
                  │ legal_restriction│  conta da empresa · conta pessoal de sócio ·
                  │ _targets         │  veículo · imóvel · recebível
                  └──────────────────┘

        ┌─────────────────────┐        ┌────────────────────────────────┐
        │  legal_agreements   │───1:N──│ legal_agreement_installments   │
        │ acordo: negociação →│        │ parcela: vencimento, valor,    │
        │ proposto → homologa-│        │ status, data de pagamento      │
        │ do → cumprido       │        └──────────────┬─────────────────┘
        └──────────┬──────────┘                       │
                   │                                  │
                   └──────────────┬───────────────────┘
                                  ▼
                        ┌────────────────────┐        ┌──────────────────┐
                        │   legal_payments   │───────▶│ payable_snapshots│
                        │ acordo, condenação,│ origin │  (Contas a Pagar)│
                        │ custas, honorários,│ =LEGAL │                  │
                        │ depósito recursal  │        └──────────────────┘
                        └────────────────────┘
```

---

## 6. Os dois eixos de estado

O campo `status` atual vira **dois**, independentes e com transições próprias.

### Situação processual — onde o processo está no rito

```
DISTRIBUIDO → EM_INSTRUCAO → AGUARDANDO_SENTENCA → COM_SENTENCA
                                                        │
                                    ┌───────────────────┴──────────────┐
                                    ▼                                  ▼
                              EM_RECURSO ──────────────────────▶ EM_EXECUCAO
                                                                       │
                                                          AGUARDANDO_ARQUIVAMENTO
                                                                       │
                                                                  ARQUIVADO
```

`SUSPENSO` é transversal: suspende a partir de qualquer estado e retorna ao anterior.

### Situação financeira — o que devemos e em que estágio

```
SEM_OBRIGACAO → EM_NEGOCIACAO → ACORDO_HOMOLOGADO → PAGAMENTO_EM_CURSO → QUITADO
                                        │                    │
                                        └──── INADIMPLENTE ◀──┘   (parcela vencida
                                                                   não paga)
```

Quando um processo transita para `ARQUIVADO` sem passar por `QUITADO`, significa
improcedência ou desistência: a situação financeira termina em `SEM_OBRIGACAO`. O
cruzamento dos dois eixos é o que responde "quitado mas não arquivado".

**Mapeamento do acervo atual** (os 148 processos migram sem perda):

| Status hoje | → Processual | → Financeira |
|---|---|---|
| EM_ANDAMENTO (51) | EM_INSTRUCAO | SEM_OBRIGACAO |
| COM_DECISAO (19) | COM_SENTENCA | SEM_OBRIGACAO |
| SUSPENSO (7) | SUSPENSO | SEM_OBRIGACAO |
| ACORDO (13) | (mantém a fase) | EM_NEGOCIACAO |
| ACORDO_FINALIZADO (17) | (mantém a fase) | QUITADO |
| ENCERRADO (41) | ARQUIVADO | QUITADO ou SEM_OBRIGACAO |

Os casos ambíguos — ENCERRADO com e sem obrigação paga, e a fase processual dos acordos —
entram numa **fila de revisão** na tela, não num palpite do sistema. São poucos e o jurídico
resolve em uma sessão.

---

## 7. Entidades propostas

### 7.1 `legal_movements` — andamentos

A linha do tempo oficial do processo dentro do SGC. Substitui `last_movement` (que passa a
ser derivado: o movimento mais recente).

| Campo | Observação |
|---|---|
| `case_id`, `occurred_at`, `description` | O andamento em si |
| `source` | MANUAL · IMPORTACAO · PUBLICACAO — de onde veio |
| `movement_type` | DESPACHO · DECISAO · SENTENCA · ACORDAO · PUBLICACAO · INTERNO |
| `created_by_id` | Quem registrou |
| `generates_deadline` | Marca que o andamento abriu prazo (cria a providência) |

Responde **"sem atualização há muito tempo"** de verdade: a métrica passa a ser a data do
último movimento **registrado por nós**, não a da carga.

### 7.2 `legal_events` — agenda (audiências, perícias, reuniões)

| Campo | Observação |
|---|---|
| `case_id`, `event_type`, `starts_at` | INICIAL · INSTRUCAO · CONCILIACAO · JULGAMENTO · PERICIA · REUNIAO |
| `location`, `is_virtual`, `link` | Presencial ou telepresencial |
| `status` | AGENDADA · REALIZADA · ADIADA · CANCELADA |
| `outcome`, `outcome_notes` | Resultado (ex.: acordo proposto, sem acordo, convertido em diligência) |
| `attendees` | Quem participa (preposto, advogado) |

Responde **"audiências desta semana"** — e passa a manter histórico de todas.

### 7.3 `legal_tasks` — providências e prazos

Uma única entidade cobre os dois casos, com um campo que distingue prazo fatal de tarefa
interna.

| Campo | Observação |
|---|---|
| `case_id`, `title`, `description` | A providência |
| `task_type` | PRAZO_FATAL · PRAZO_ADMINISTRATIVO · PROVIDENCIA_INTERNA · DILIGENCIA |
| `due_date`, `assigned_to_id` | Quando e de quem |
| `status` | ABERTA · EM_ANDAMENTO · CONCLUIDA · PERDIDA |
| `movement_id` | O andamento que originou o prazo |

Responde **"aguardando providência"**, e o painel destaca o que está atrasado ou vence hoje.

### 7.4 `legal_agreements` — acordos

Substitui `agreement_terms` (texto livre) e o status ACORDO.

| Campo | Observação |
|---|---|
| `case_id`, `total_amount`, `installment_count` | O acordo |
| `status` | EM_NEGOCIACAO · PROPOSTO · ACEITO · HOMOLOGADO · CUMPRIDO · DESCUMPRIDO · ROMPIDO |
| `proposed_by` | EMPRESA · RECLAMANTE · JUÍZO |
| `signed_at`, `homologated_at` | Marcos formais |
| `terms` | Condições em texto (o que hoje é `agreement_terms`) |
| `penalty_clause` | Multa por descumprimento — muda o valor devido |

Um processo pode ter **mais de um** acordo ao longo do tempo (proposta recusada, novo
acordo). Responde **"em negociação"** e **"aguardando pagamento"** por status.

### 7.5 `legal_agreement_installments` — parcelas

| Campo | Observação |
|---|---|
| `agreement_id`, `number`, `due_date`, `amount` | A parcela |
| `status` | A_VENCER · VENCIDA · PAGA · RENEGOCIADA |
| `paid_at`, `payment_id` | Baixa |

É o que transforma `"3 X 2.333,34"` em fluxo de caixa: parcelas a vencer no mês, vencidas,
valor pendente por processo — tudo somável.

### 7.6 `legal_payments` — pagamentos

| Campo | Observação |
|---|---|
| `case_id`, `amount`, `paid_at` | O pagamento |
| `payment_type` | ACORDO · CONDENACAO · CUSTAS · HONORARIOS · DEPOSITO_RECURSAL · PERICIA |
| `installment_id` | Quando quita uma parcela |
| `payable_snapshot_entry_id` | Vínculo com o título no Contas a Pagar |
| `receipt_document_id` | Comprovante anexado |

`amount_paid` do processo passa a ser **derivado** da soma dos pagamentos — hoje é digitado e
pode divergir.

### 7.7 `legal_restrictions` — bloqueios e restrições judiciais

A entidade que hoje simplesmente não existe, e que responde três das nove perguntas.

| Campo | Observação |
|---|---|
| `case_id`, `restriction_type` | BLOQUEIO_SISBAJUD · PENHORA · ARRESTO · RENAJUD · INDISPONIBILIDADE · PENHORA_FATURAMENTO |
| `target_id` | O que foi atingido (ver 7.8) |
| `amount_blocked`, `blocked_at` | Valor e data |
| `status` | ATIVO · LIBERADO · CONVERTIDO_EM_PAGAMENTO · SUBSTITUIDO |
| `released_at`, `released_amount` | Liberação parcial ou total |
| `converted_payment_id` | Quando o bloqueio vira pagamento definitivo |
| `institution` | Banco ou órgão |

### 7.8 `legal_restriction_targets` — o que é atingido

| Campo | Observação |
|---|---|
| `target_type` | CONTA_EMPRESA · CONTA_PESSOAL_SOCIO · VEICULO · IMOVEL · RECEBIVEL · OUTRO |
| `owner_person_id` | Sócio, quando pessoal |
| `owner_company_id` | Empresa do grupo, quando empresarial |
| `description`, `institution`, `account_ref` | Identificação (sem dado bancário completo) |

Separar o alvo do bloqueio é o que responde **"quais processos atingem contas pessoais dos
sócios"** — uma pergunta sobre o *titular*, não sobre o processo. E permite ver todos os
bloqueios sobre um mesmo alvo, de processos diferentes.

### 7.9 `legal_case_parties` — partes do processo

Hoje `claimant_name` e `defendant_name` são texto. Vira N:N com papel
(RECLAMANTE · RECLAMADA · TERCEIRO_INTERESSADO · SOCIO_INCLUIDO · LITISCONSORTE),
apontando para `legal_persons` ou `legal_companies`.

Isso importa porque **sócio incluído no polo passivo** é justamente o caso que leva a
bloqueio em conta pessoal — e hoje não há como marcar.

### 7.10 `legal_documents` — anexos do processo

Petições, sentenças, acordos assinados, comprovantes. Usa o mesmo mecanismo de armazenamento
já corrigido no SGC (raiz `STORAGE_ROOT` no volume persistente), com categoria e vínculo
opcional a movimento, acordo ou pagamento.

### 7.11 `legal_law_firms` — escritórios e responsáveis

Catálogo simples (nome, contato, honorários contratados) com vínculo ao processo. Permite
distribuir carteira e medir volume por escritório.

### Alterações no `legal_cases`

| Campo | Mudança |
|---|---|
| `status` | **Desdobrado** em `procedural_status` + `financial_status` |
| `hearing_date` · `last_movement*` | **Derivados** de `legal_events` e `legal_movements` |
| `agreement_terms` · `amount_agreed` | **Migram** para `legal_agreements` |
| `amount_paid` · `amount_pending` | **Derivados** dos pagamentos e parcelas |
| `company` · `project` (texto) | Normalizados em `company_id` · `project_id` |
| `phase` (novo) | CONHECIMENTO · RECURSO · EXECUCAO |
| `risk_level` (novo) | PROVAVEL · POSSIVEL · REMOTA — base de provisão contábil |
| `responsible_user_id`, `law_firm_id` (novos) | Quem responde pelo processo |
| `secrecy` (novo) | Segredo de justiça restringe visualização |

---

## 8. As nove perguntas, respondidas

| Pergunta | Consulta no novo modelo |
|---|---|
| Audiências desta semana | `legal_events` onde `event_type` é audiência, `starts_at` na semana, `status = AGENDADA` |
| Aguardando providência | `legal_tasks` com `status IN (ABERTA, EM_ANDAMENTO)`, ordenado por `due_date` |
| Acordos em negociação | `legal_agreements` com `status IN (EM_NEGOCIACAO, PROPOSTO, ACEITO)` |
| Acordos aguardando pagamento | `legal_agreement_installments` com `status IN (A_VENCER, VENCIDA)` em acordos homologados |
| Quitados mas não arquivados | `financial_status = QUITADO` **e** `procedural_status <> ARQUIVADO` |
| Bloqueios ativos em contas da empresa | `legal_restrictions` `status = ATIVO` com alvo `CONTA_EMPRESA` |
| Processos que atingem contas de sócios | `legal_restrictions` com alvo `CONTA_PESSOAL_SOCIO` (+ `legal_case_parties` com papel `SOCIO_INCLUIDO`) |
| Valor bloqueado por tipo | Soma de `amount_blocked − released_amount` agrupada por `restriction_type` |
| Sem atualização há muito tempo | Processos cujo último `legal_movements.occurred_at` é anterior a N dias, com `procedural_status` ativo |

Todas viram **consulta**, não relatório manual — e todas alimentam painel.

---

## 9. Integração com o resto do SGC

**Contas a Pagar.** O CAP já materializa títulos por `(origin, ref_id, competência)`, de forma
idempotente — é como Custos Fixos e Endividamento funcionam. Proponho uma origem nova,
`LEGAL`, com `ref_id` = parcela do acordo. Efeito: a parcela homologada aparece no Contas a
Pagar do mês do vencimento, é paga pelo fluxo normal do financeiro e a baixa retorna para o
processo. **Sem essa integração o jurídico vira uma segunda contabilidade** — e a empresa
descobre o desembolso duas vezes.

**Documentos.** Reusar a raiz `STORAGE_ROOT` no volume persistente, o mesmo padrão dos
documentos de projeto e das NFs.

**Auditoria.** Manter `legal_change_logs` como está e estendê-lo às entidades novas: quem
mudou a situação de um processo é informação de compliance.

**Indicadores.** Passivo provisionado por `risk_level` e por competência pode entrar nos
dashboards executivos, se o financeiro quiser — decisão em aberto (§13).

---

## 10. Painéis propostos

| Painel | Para quem | Conteúdo |
|---|---|---|
| **Operação da semana** | Jurídico, no dia a dia | Audiências dos próximos 7 dias · providências vencidas e a vencer · prazos fatais · processos parados há mais de N dias |
| **Passivo** (evolui o atual) | Diretoria | Valor por situação processual × financeira · por risco (provável/possível/remota) · por empresa, projeto e UF |
| **Acordos e pagamentos** | Jurídico + Financeiro | Em negociação · aguardando homologação · parcelas a vencer no mês · vencidas · desembolso realizado por mês |
| **Bloqueios e impactos patrimoniais** | Diretoria + Financeiro | Valor bloqueado por tipo · por titular (empresa × sócio) · bloqueios ativos com maior valor · liberações do período |

O painel de bloqueios é o que hoje simplesmente não existe e é o de maior valor para a
diretoria: bloqueio em conta pessoal de sócio é evento crítico.

---

## 11. Permissões

Seguindo a regra do módulo — **um recurso por menu**, verbos padrão e `sensitive` para valores:

| Recurso | Verbos | Observação |
|---|---|---|
| `legal_movements` | list, read, create, update | Andamentos |
| `legal_events` | list, read, create, update, delete | Agenda |
| `legal_tasks` | list, read, create, update, delete | Providências e prazos |
| `legal_agreements` | list, read, create, update, delete, **sensitive** | Valores do acordo |
| `legal_payments` | list, read, create, update, **sensitive** | Desembolso |
| `legal_restrictions` | list, read, create, update, **sensitive** | Valor bloqueado |
| `legal_documents` | list, read, create, delete | Anexos |

Dois pontos de atenção:

- **Bloqueio em conta de sócio é o dado mais sensível do módulo.** Recomendo que
  `legal_restrictions.sensitive` seja concedido apenas à diretoria e ao jurídico —
  não ao perfil de consulta.
- **Segredo de justiça** (`secrecy` no processo) deve restringir a leitura ao responsável e
  a quem tiver `legal_cases.sensitive`, independentemente das demais permissões.

---

## 12. Fluxos de trabalho

**1. Distribuição.** Novo processo → partes → responsável → primeira providência
(contestação) com prazo → situação `DISTRIBUIDO` / `SEM_OBRIGACAO`.

**2. Andamento.** Movimento registrado (manual ou publicação) → se abre prazo, gera
providência → pode mudar a situação processual.

**3. Audiência.** Evento agendado → notificação no painel da semana → realizada, com
resultado → gera movimento e, se houve proposta, abre acordo em negociação.

**4. Acordo.** Negociação → proposta → aceite → homologação → parcelas geradas → cada
parcela vira título no CAP no mês do vencimento → pagamento baixa parcela e título →
todas pagas: `CUMPRIDO` e situação financeira `QUITADO`. Parcela vencida não paga →
`INADIMPLENTE`, com alerta.

**5. Bloqueio.** Registro do bloqueio com alvo e valor → alerta imediato no painel →
desfecho: liberação (parcial ou total) ou conversão em pagamento — que baixa o valor devido.

**6. Encerramento.** Quitado → aguardando arquivamento → arquivado. O par de eixos é o que
permite acompanhar essa fila, que hoje some dentro de "ENCERRADO".

---

## 13. Decisões que preciso de você

Nenhuma linha de código deve ser escrita antes destas respostas — cada uma muda o desenho:

1. **Acordo vira título no Contas a Pagar?** Recomendo que sim (origem `LEGAL`). Se não,
   o jurídico controla o desembolso por fora e os dois números vão divergir.
2. **Sócios entram como `legal_persons` com tipo, ou como cadastro novo?** Recomendo
   estender `legal_persons` com `person_type` — o mesmo CPF pode ser sócio e parte.
3. **Contas bancárias**: o SGC não tem cadastro de contas. Registro o alvo do bloqueio como
   texto identificador (banco + final da conta), ou criamos cadastro de contas da empresa?
4. **Provisão contábil por risco** entra agora ou fica para depois? Ela conecta o jurídico
   aos indicadores executivos, mas exige definição contábil (percentual por classificação).
5. **Andamentos**: entrada manual apenas, ou vale investigar integração com publicações
   (JusBrasil/DJe) numa fase futura? O desenho já prevê `source = PUBLICACAO`.
6. **Honorários de escritório** entram como pagamento do processo (visão custo total do
   contencioso) ou ficam fora do módulo?

---

## 14. Roadmap sugerido

| Fase | Entrega | Destrava |
|---|---|---|
| **A — Núcleo operacional** | Dois eixos de estado, `legal_movements`, `legal_events`, `legal_tasks` + painel da semana | Audiências, providências, processos parados, quitado-não-arquivado |
| **B — Acordos e pagamentos** | `legal_agreements`, parcelas, `legal_payments`, integração com o CAP | Acordos em negociação e aguardando pagamento, desembolso real |
| **C — Bloqueios** | `legal_restrictions` + alvos + painel patrimonial | Bloqueios ativos, contas de sócios, valor por tipo |
| **D — Suporte** | Documentos, escritórios, partes normalizadas, segredo de justiça | Operação completa e compliance |
| **E — Analítico** | Provisão por risco, indicadores executivos, relatórios novos | Visão de diretoria |

A ordem não é arbitrária: **A** entrega as respostas mais usadas no dia a dia com o menor
risco (nenhuma mudança financeira), e cada fase seguinte depende da anterior. A migração dos
148 processos acontece na fase A, com a fila de revisão descrita em §6.

---

## 15. Riscos

| Risco | Mitigação |
|---|---|
| A fila de revisão dos ENCERRADO (41 processos) trava a migração | Migrar com o par mais conservador e revisar na tela — o sistema segue utilizável |
| Duplicidade de desembolso entre jurídico e CAP | Decisão 1 resolvida antes da fase B; a origem `LEGAL` é idempotente por construção |
| Dado de sócio e bloqueio vazando para perfil de consulta | `sensitive` próprio + revisão dos presets antes de publicar a fase C |
| O jurídico não alimentar a timeline (volta a virar repositório) | O indicador "sem atualização há N dias" é justamente o termômetro disso — e fica no painel principal |
| Crescimento do escopo (integração com tribunais) | Fora das fases A–E; o modelo já reserva `source = PUBLICACAO` |

---

## 16. Documentos relacionados

- [`JURIDICO_IMPORTACAO_PLANILHA.md`](JURIDICO_IMPORTACAO_PLANILHA.md) — a carga inicial, que
  permanece válida como marco zero
- [`JURIDICO_RUNBOOK_DEPLOY.md`](JURIDICO_RUNBOOK_DEPLOY.md) — deploy do módulo
- [`SGC_DOCUMENTACAO_COMPLETA.md`](SGC_DOCUMENTACAO_COMPLETA.md) — estado atual do sistema
