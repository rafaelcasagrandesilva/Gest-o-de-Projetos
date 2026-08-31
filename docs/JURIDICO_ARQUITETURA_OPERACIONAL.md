# Jurídico — arquitetura da gestão do passivo

**Versão 3** · documento de arquitetura · **nenhuma linha de código escrita**
Estado analisado: `2517efe` (29/08/2026) · 148 processos e 159 pessoas em produção
Versões 1 e 2 permanecem no histórico do git.

---

## 0. Veredito, antes do detalhe

Você está certo, e a mudança de perspectiva **exige alterar a decisão estrutural mais central
da v2**: a raiz do modelo deixa de ser o processo judicial.

Os dados de produção sustentam a tese de um jeito que eu não esperava:

| Evidência | Número | O que significa |
|---|---|---|
| Pessoas com **mais de um processo** | **23 de 122** (19%) | O processo já não é a unidade natural. Uma pessoa é uma exposição; os processos são consequências dela |
| Processos com **data de distribuição** | **0 de 148** | O acervo tem classificação, não tem tempo |
| Processos com **data de audiência** | **0 de 148** | Idem |
| Pessoas com data de desligamento | 134 de 159 | O gatilho do ciclo existe |
| Defasagem desligamento → distribuição | **incalculável hoje** | A métrica de prevenção que você quer não é derivável do acervo atual |

A última linha é a mais importante: **nenhuma das perguntas de prevenção que você listou pode
ser respondida com o dado que temos**. Elas só passam a existir quando o SGC virar o sistema de
operação. Isso não enfraquece a proposta — é o argumento mais forte a favor dela, e obriga a
arquitetura a garantir que esses dados nasçam a partir de agora.

**O que muda estruturalmente nesta versão** (detalhe nas seções seguintes):

1. Nova raiz: **Caso** (`legal_matters`) — o risco administrado. O **processo** vira uma entidade
   *dentro* do caso, e um caso pode ter mais de um processo (19% já têm).
2. Timeline, eventos e negociações passam a pertencer ao **caso**, não ao processo — porque
   notificação extrajudicial, tentativa de acordo e prescrição acontecem **antes de existir
   processo**. Na v2 isso era impossível de registrar.
3. **Pedidos** (`legal_claim_items`) entram como entidade: sem eles não existe "reincidência de
   pedidos" nem "principais pedidos por obra".
4. **Contexto do desligamento congelado** no caso (obra, centro de custo, gestor, motivo): a
   análise de prevenção precisa do valor *da época*, não do vínculo atual.
5. **Motor de regras** com um primitivo único — o **Sinal** — do qual derivam alertas,
   indicadores, dashboards e futuras notificações.
6. Catálogos ganham **ficha 360º** como modelo de leitura: pessoa, empresa, projeto, escritório,
   advogado, sócio, conta bancária e câmara arbitral.

**E o que eu recuso fazer agora**, com o motivo (§10): event sourcing puro, linguagem de regras
(DSL), score de risco por machine learning, relação N:N entre caso e processo, e cadastro
bancário completo.

---

## 1. A mudança de perspectiva: a empresa administra risco

### 1.1 O ciclo completo

```
  ┌─────────────── CASO (legal_matters) — a unidade que a empresa administra ───────────────┐
  │                                                                                          │
  │  Desligamento ──▶ Período prescricional ──▶ Risco potencial ──▶ [ PROCESSO DISTRIBUÍDO ] │
  │   (RH)              (2 anos, contando)        (score, fatores)         │                 │
  │                                                                        ▼                 │
  │                                                            Contencioso ──▶ Negociação    │
  │                                                                        │        │        │
  │                                                              Execução ◀─┘        │        │
  │                                                                  │              │        │
  │                                                            Pagamento ◀──────────┘        │
  │                                                                  │                       │
  │                                                             Quitação ──▶ Arquivamento    │
  └──────────────────────────────────────────────────────────────────────────────────────────┘
                                      ▲
                    O processo é UMA FASE, não o começo nem o todo.
                    Um caso pode encerrar sem nunca gerar processo (prescrição
                    consumada) ou gerar mais de um (19% dos casos atuais).
```

### 1.2 O caso como raiz

`legal_matters` — o passivo em acompanhamento:

| Campo | Papel |
|---|---|
| `origin` | DESLIGAMENTO · CONTRATO · ACIDENTE · FISCAL · CIVEL_TERCEIRO · OUTRO |
| `matter_type` | TRABALHISTA · CIVEL · TRIBUTARIO · ADMINISTRATIVO |
| `lifecycle_stage` | POTENCIAL · EXTRAJUDICIAL · JUDICIALIZADO · EM_EXECUCAO · QUITADO · ENCERRADO · **PRESCRITO** |
| `person_id` | A pessoa exposta (quando há) |
| `prescription_deadline` | Data-limite calculada a partir do desligamento |
| `risk_score`, `risk_factors` | Score e os fatores que o compõem (§6.4) |
| `exposure_estimated` | Exposição estimada **antes** de existir valor de causa |
| Contexto congelado | §5 |

O **processo judicial** (`legal_cases`, a tabela que já existe) permanece com o que é
genuinamente judicial: número CNJ, vara, foro, rito, fases processuais, valor da causa.

> **Nota de vocabulário.** Mantenho `legal_cases` significando *processo*. Em terminologia
> jurídica anglófona, *matter* (o assunto que o cliente administra) e *case* (o litígio) são
> conceitos distintos e consagrados — a mesma distinção que você fez. Renomear a tabela custaria
> migração de permissões já semeadas nos perfis, com risco desproporcional ao ganho. Na tela, os
> nomes são **Caso** e **Processo**.

### 1.3 Um caso, N processos

Evidência: 22 pessoas com 2 processos e 1 com 3. Inspecionando os pares, eles compartilham vara
e sequência de numeração — são desdobramentos da mesma exposição, não riscos distintos.

**Decisão:** `legal_matters` **1 : N** `legal_cases`.

**Não** proponho N:N (um processo com vários casos, como na ação plúrima) agora. Ela existe no
mundo real, mas não no acervo atual, e a tabela de partes (`legal_case_parties`) já registra
vários reclamantes num mesmo processo — o que cobre a consulta sem antecipar a complexidade. Se
aparecer uma ação plúrima de verdade, a promoção de 1:N para N:N é uma migração aditiva.

### 1.4 A consequência que quebra a v2

Se o caso começa no desligamento, então **timeline, eventos e negociações não podem pertencer ao
processo** — eles existem antes dele. Uma notificação extrajudicial, uma tentativa de acordo
antes da ação, o vencimento do prazo prescricional: todos são fatos do caso.

Na v2 eu tinha pendurado tudo em `case_id`. Na v3, **tudo pendura em `matter_id`**, com
`case_id` **opcional** — preenchido quando o fato pertence a um processo específico. Isso
destrava um cenário que a v2 simplesmente não modelava: **acordo extrajudicial sem processo**.

---

## 2. O agregado e a disciplina que ele impõe

Sua preocupação — "daqui a dois anos cada funcionalidade nova cria uma tabela isolada sem um
centro claro" — é o problema certo. Mas a leitura ingênua de "tudo pertence ao processo"
produziria o erro oposto: um escritório de advocacia ou uma conta bancária **não** pertencem a
um caso; são entidades compartilhadas por muitos.

A distinção que resolve isso é clássica em DDD: **limite de consistência ≠ modelo de leitura**.

### 2.1 O que está dentro do agregado

Entidades sem vida própria: só existem em relação a um caso, são criadas e alteradas **através
da raiz**, e morrem com ela.

```
CASO (raiz)
├── processos (legal_cases)          ├── negociações → propostas → acordos → parcelas
├── timeline (fatos)                 ├── lançamentos financeiros
├── eventos (compromissos)           ├── restrições (bloqueios)
├── pedidos (claim items)            ├── documentos
├── partes (vínculo com catálogo)    ├── responsáveis (vínculo com catálogo)
└── observações                      └── sinais (§6)
```

### 2.2 O que é referenciado, não contido

Entidades com identidade e ciclo próprios, apontadas por id: **pessoa, empresa, projeto,
escritório, advogado, sócio, conta bancária, câmara arbitral, usuário**. Elas aparecem no caso
como vínculo (`legal_case_parties`, `legal_case_assignments`), nunca como cópia.

### 2.3 As quatro regras que impedem a proliferação

Esta subseção é a resposta direta ao seu receio. Ela vale como norma do módulo:

1. **Todo fato novo sobre um caso entra no agregado e escreve na timeline** pela mesma porta. Se
   uma funcionalidade nova precisa de tabela própria, ela é filha do caso e sua criação
   registra um fato.
2. **Toda entidade compartilhada vira catálogo com ficha 360º** (§3) — nunca uma tabela solta
   pendurada em um caso.
3. **Nada consulta as tabelas filhas por fora.** Leitura agregada é projeção (§3.3), não
   `SELECT` avulso espalhado em serviços.
4. **Consistência entre agregados é eventual e idempotente.** O pagamento vive no caso e vira
   título no Contas a Pagar por chave de origem — não por transação distribuída. É o mecanismo
   que Custos Fixos e Endividamento já usam.

### 2.4 Um aviso sobre agregados grandes

O agregado do caso é grande, e agregado grande tem custo: carregar tudo para alterar um campo é
desperdício, e transações longas causam contenção. **Não** proponho carregar o agregado inteiro
em memória a cada operação. A raiz é o **ponto de entrada dos comandos** e a dona das
invariantes; cada serviço carrega o que precisa. É disciplina de escrita, não um objeto
monolítico.

---

## 3. Catálogos e fichas 360º

### 3.1 As entidades

| Entidade | Situação | Observação |
|---|---|---|
| **Pessoa** | existe (`legal_persons`) | Ganha `person_type` (ex-colaborador, sócio, terceiro, advogado) e vínculo com `employees` |
| **Empresa** | existe (`legal_companies`) | Vazia em produção — passa a ser preenchida no lugar do texto livre |
| **Projeto** | existe (`legal_projects`) | Ganha vínculo com `projects.id` do SGC |
| **Escritório** | novo | Bancas contratadas, com honorários |
| **Advogado** | novo | Interno ou externo, vinculado a escritório |
| **Sócio** | pessoa com tipo | Titular de conta pessoal atingida |
| **Conta bancária** | novo | Titular (empresa ou sócio), banco, **identificação mascarada** (§10.5) |
| **Câmara arbitral** | novo | Referenciada pelas negociações |

### 3.2 O padrão único de ficha

Toda ficha tem a mesma anatomia, o que a torna barata de construir e previsível de usar:

```
┌──────────────────────────────────────────────────────────────┐
│ Identificação          │ Números                             │
│ (nome, documento,      │ casos · processos · passivo ·       │
│  vínculos)             │ acordos · pago · bloqueado          │
├────────────────────────┴─────────────────────────────────────┤
│ Casos relacionados          (lista, com estado e valor)      │
├──────────────────────────────────────────────────────────────┤
│ Timeline consolidada        (fatos de todos os casos)        │
├──────────────────────────────────────────────────────────────┤
│ Sinais abertos              (o que exige atenção)            │
└──────────────────────────────────────────────────────────────┘
```

O que muda por entidade é só o recorte:

- **Empresa** — processos, passivo, acordos, pagamentos, bloqueios, histórico.
- **Projeto/obra** — quantos processos, quanto já custou, **quanto ainda pode custar** (exposição
  + provisão), principais pedidos.
- **Desligado** — a linha do tempo inteira dentro do SGC: admissão, alocações, desligamento
  (dados de RH) **e** os fatos do caso jurídico. É uma ficha que atravessa módulos.
- **Escritório** — carteira, desfechos, tempo médio, custo em honorários.
- **Sócio** — casos em que é parte, contas atingidas, valor bloqueado.

### 3.3 Como se constroem — sem virar tabela nova

Fichas são **projeções de leitura**, montadas por consultas sobre o agregado. Nenhuma delas cria
entidade de negócio. Onde a soma ficar cara, o caminho é **cache derivado com dono único e
recálculo a partir dos fatos** — o mesmo padrão das colunas derivadas do caso.

O corolário: pedir uma ficha nova no futuro (ex.: por gestor) é escrever uma projeção, não
alterar o modelo.

---

## 4. Pedidos — o que faltava para prevenção

Você quer "reincidência de determinados pedidos" e "principais pedidos por projeto". Isso não é
derivável de nada que existe hoje ou que propus nas versões anteriores.

**`legal_claim_types`** (catálogo): horas extras, adicional de periculosidade, adicional de
insalubridade, verbas rescisórias, FGTS, dano moral, acúmulo de função, intervalo intrajornada,
equiparação salarial, reconhecimento de vínculo…

**`legal_claim_items`** (pedidos do caso): tipo, valor pedido, valor considerado, resultado
(procedente, improcedente, parcial, acordado) e o processo em que foi pleiteado.

O que isso destrava — e que é o coração da sua ideia de prevenção:

| Pergunta | Resposta |
|---|---|
| Qual pedido mais aparece contra nós? | Frequência por tipo |
| Qual pedido mais **custa**? | Valor deferido/acordado por tipo |
| Que obra concentra que tipo de pedido? | Cruzamento com o contexto (§5) |
| Onde está a falha operacional? | Pedido recorrente é sintoma de processo interno defeituoso — hora extra sistemática, intervalo não concedido, adicional não pago |

O último item é o salto de "software jurídico" para "ferramenta de gestão": o padrão dos pedidos
aponta a causa raiz na operação, não no jurídico.

---

## 5. Contexto congelado do desligamento

Para responder "quais gestores, contratos ou obras geram mais ações", o caso precisa guardar o
contexto **da época** — não o vínculo atual. Centro de custo muda, gestor muda, obra encerra; um
`JOIN` com o cadastro de hoje responderia a pergunta errada.

O caso congela, na abertura: obra/projeto, centro de custo, gestor responsável, cargo, data de
admissão e de desligamento, motivo do desligamento, tempo de casa e se houve homologação.

Boa parte disso já existe no SGC (`employees`, histórico de centro de custo, alocações). O caso
copia — deliberadamente — porque análise histórica exige o valor do momento.

---

## 6. Motor de regras

### 6.1 O primitivo único: o Sinal

Uma regra avaliada produz um **Sinal**: "este caso, nesta data, atende esta condição, com esta
severidade e este valor".

```
                        ┌──────────────────┐
   catálogo de regras   │      SINAL       │   parâmetros por regra
   (definidas em código)│  matter_id       │   (limiares, severidade,
            │           │  rule_id         │    papel destinatário)
            └──────────▶│  severity        │◀────────────┘
                        │  due_at, value   │
                        │  detected_at     │
                        └────────┬─────────┘
                                 │
        ┌────────────┬───────────┼────────────┬──────────────────┐
        ▼            ▼           ▼            ▼                  ▼
    ALERTAS     INDICADORES  DASHBOARDS   NOTIFICAÇÕES     SCORE DE RISCO
   (abertos)     (contagens    (séries)     (futuro,        (soma de sinais
                  e somas)                 mesmo motor)      ponderados)
```

Tudo o que você listou — audiência em menos de 7 dias, parcela vence amanhã, bloqueio novo,
acordo parado há 20 dias, processo sem andamento há 60 dias, etapa acima do SLA, execução há mais
de 180 dias, valor acima de R$ X — é a mesma coisa: **uma regra que produz sinais**. A diferença
entre alerta e indicador é só o que se faz com o sinal.

### 6.2 Regras em código, parâmetros no banco — e por que não uma DSL

Cada regra é uma definição **nomeada e versionada no código**, com parâmetros em
`legal_rules` (limiar, severidade, papel destinatário, ativa/inativa).

Você levantou a hipótese de um mecanismo genérico. **Recomendo não construir uma linguagem de
regras**, e o motivo é experiência com o padrão, não preguiça:

- Uma DSL vira uma linguagem de programação de segunda classe: sem depuração, sem teste, sem
  tipo. O primeiro bug de produção numa expressão salva no banco custa dias.
- Regras reais precisam de dados que uma expressão simples não alcança (agregações, janelas,
  permissões).
- O ganho prometido — "usuário cria regra sozinho" — quase nunca se materializa: quem escreve
  regra é quem entende o modelo.

O que **realmente** se ganha com um motor é o registro único e o primitivo comum. Isso se obtém
com regras em código e parâmetros configuráveis, que é o desenho que proponho. Se um dia
houver demanda concreta de regra criada pelo usuário, o caminho é um **construtor guiado**
(campo + operador + valor, dentro de um conjunto fechado), não uma linguagem livre.

### 6.3 Avaliação

Com 148 casos, os sinais são calculados **por consulta** quando a tela abre (a v2 já apontava:
não há agendador). O que acrescento aqui é a **persistência do sinal quando ele muda de estado**
— nasceu, foi reconhecido, foi resolvido —, porque isso permite medir o que nenhum cálculo
instantâneo mede: quanto tempo levamos para reagir a um bloqueio, quantos prazos venceram sem
ciência, se a operação está melhorando.

### 6.4 Score de risco: determinístico, não estatístico

"Pessoas com alto risco de ajuizamento" é a funcionalidade mais sedutora e a mais fácil de
errar. Com 148 casos, **não há volume para machine learning** — um modelo treinado nisso
produziria confiança injustificada.

Proponho um score **explicável**, composto por fatores observáveis e ponderados (regras, como
tudo o mais): tempo restante de prescrição, motivo do desligamento, existência de verbas em
aberto, índice de ações da obra e do gestor, reincidência de pedidos naquele contrato, e se
houve homologação. Cada caso mostra **quais fatores** compuseram a nota.

Quando houver alguns anos de histórico com desfechos registrados, revisitar com estatística faz
sentido — e aí o modelo já terá os dados rotulados, porque o desenho os coleta desde o começo.

---

## 7. O que muda em relação à v2

| Na v2 | Na v3 | Motivo |
|---|---|---|
| Processo como raiz | **Caso** (`legal_matters`) como raiz; processo é uma fase | A empresa administra risco; 19% dos casos já têm mais de um processo |
| Timeline, eventos e negociações em `case_id` | Em **`matter_id`**, com `case_id` opcional | Fatos existem antes do processo: prescrição, notificação, acordo extrajudicial |
| Sem pedidos | **`legal_claim_items`** + catálogo | Sem eles não há reincidência nem "principais pedidos" |
| Contexto por join com o cadastro atual | **Contexto congelado** no caso | Análise histórica exige o valor da época |
| Regras de alerta como tabela de limiares | **Motor de regras com Sinal** como primitivo comum | Alertas, indicadores, dashboards e notificações passam a derivar de uma fonte |
| Catálogos como listas de apoio | **Fichas 360º** como modelo de leitura padronizado | O processo deixa de ser o único ponto de consulta |
| Radar de prescrição como consulta | **Estágio do ciclo de vida** (`POTENCIAL`, `PRESCRITO`) | Prescrição vira estado do caso, não um relatório |

O que **não** muda: timeline como projeção (não fonte), eventos genéricos com calendário
derivado, pipeline configurável com SLA, negociação separada do acordo, lançamentos com direção
e recuperabilidade, papéis datados, alertas sem depender de agendador.

---

## 8. Modelo completo

```
        RH / SGC                          CATÁLOGOS (identidade própria, ficha 360º)
   ┌──────────────┐        ┌────────────┬────────────┬───────────┬──────────┬──────────┐
   │  employees   │───────▶│  pessoas   │  empresas  │  projetos │escritórios│ câmaras  │
   │ desligamento │        │  (+sócios) │            │ →projects │ advogados │  contas  │
   └──────────────┘        └─────┬──────┴──────┬─────┴─────┬─────┴─────┬────┴────┬─────┘
                                 │             │           │           │         │
                                 └─────────────┴─────┬─────┴───────────┴─────────┘
                                                     │  (vínculos: partes, responsáveis)
   ┌─────────────────────────────────────────────────▼──────────────────────────────────┐
   │                          CASO — legal_matters (raiz do agregado)                    │
   │  origem · tipo · lifecycle_stage · prescrição · score de risco · exposição          │
   │  contexto congelado: obra, centro de custo, gestor, motivo, tempo de casa           │
   ├────────────────────────────────────────────────────────────────────────────────────┤
   │  processos          timeline          eventos          pedidos                     │
   │  (legal_cases)      (fatos)           (compromissos)   (claim items)               │
   │  nº CNJ, vara,      append-only,      agenda, prazos,  tipo, valor,                │
   │  rito, fases        procedência       parcelas         resultado                   │
   │                                                                                     │
   │  negociações → propostas → acordos → parcelas                                      │
   │  lançamentos financeiros (saída/retorno · recuperável)                             │
   │  restrições → alvos (conta empresa · conta sócio · veículo · imóvel)               │
   │  documentos · partes · responsáveis · observações · sinais                         │
   └───────────────┬──────────────────────────────────────────────┬─────────────────────┘
                   │                                              │
     origem LEGAL  ▼                                              ▼
        ┌────────────────────┐                        ┌────────────────────────┐
        │  payable_snapshots │                        │  MOTOR DE REGRAS       │
        │  (Contas a Pagar)  │                        │  regras → SINAIS →     │
        └────────────────────┘                        │  alertas · indicadores │
                                                      │  dashboards · score    │
        ┌────────────────────┐                        └────────────────────────┘
        │  legal_provisions  │  provisão por competência → indicadores executivos
        └────────────────────┘
```

---

## 9. Fonte oficial e política de integração

O princípio que você reforçou vira **regra de arquitetura**, não intenção:

1. **Corte explícito.** Um marco encerra a carga; depois dele a importação fica desabilitada e
   reabri-la exige ação administrativa registrada.
2. **Procedência em todo fato** (`MANUAL · CARGA_INICIAL · PUBLICACAO · INTEGRACAO · SISTEMA`).
3. **Integração enriquece, nunca substitui.** Uma fonte externa pode *preencher lacuna* e
   *acrescentar fato novo*; não pode sobrescrever campo preenchido na operação. Esta regra já
   existe e está provada no importador atual ("campo vazio nunca sobrescreve informação
   existente" e a preservação dos dados enriquecidos) — a v3 apenas a promove a política do
   módulo inteiro.
4. **Toda ingestão é idempotente por chave natural** (número CNJ + hash do fato), para que
   captura repetida não duplique.
5. **Conflito é conflito, não sobrescrita.** Divergência entre a fonte externa e o registro
   operacional vira sinal para revisão humana.

---

## 10. O que eu recomendo não fazer agora

Espírito crítico, como você pediu — cinco tentações e por que recuso cada uma.

**10.1 Event sourcing puro.** A timeline parece convidar: por que não fazer dela a fonte da
verdade e derivar todo o estado? Porque o custo é alto (replay, versionamento de eventos,
projeções a manter) e o ganho não se realiza aqui: o módulo precisa de consultas relacionais
ricas — somar passivo por obra, listar parcelas vencidas — que ficam caras sobre um log. A
timeline continua **projeção**, e o estado vive em tabelas normalizadas.

**10.2 Linguagem de regras.** §6.2.

**10.3 Score por machine learning.** §6.4.

**10.4 N:N entre caso e processo.** §1.3 — aditivo depois, se aparecer.

**10.5 Cadastro bancário completo.** Guardar agência, conta e titularidade completa cria
responsabilidade de segurança desproporcional ao uso. O bloqueio precisa saber *qual conta*, não
*como acessá-la*: banco, identificação mascarada (final) e titular bastam.

**10.6 Módulo separado ou microserviço.** O valor do Jurídico no SGC vem justamente da
integração — RH origina, financeiro paga, indicadores consolidam. Separá-lo destruiria isso.

---

## 11. Horizonte de cinco a dez anos

**Dado pessoal e retenção.** O módulo acumula CPF, motivo de desligamento, valores, contas de
sócios e, em perícia, dado de saúde. Em dez anos serão milhares de pessoas, a maioria sem
relação atual com a empresa. Proponho decidir **agora** a política: prazo de retenção após o
arquivamento, anonimização do que passa desse prazo (preservando os números para estatística) e
registro de acesso a caso sob segredo. É mais barato desenhar isso antes do que retroagir sobre
dez anos de histórico.

**Volume.** 148 casos hoje; com o ciclo completo, cada desligamento vira um caso — algo como
centenas por ano. Nada que exija arquitetura especial; a atenção fica na timeline e nos sinais,
que crescem por fato e não por caso, e por isso precisam de índice por caso e data desde o
início.

**Multiempresa.** O grupo tem mais de uma entidade (a planilha já distingue). Se um dia houver
separação por empresa no acesso, o caminho é o vínculo com `legal_companies` — que já existe no
modelo. Nenhuma decisão nova é necessária hoje, apenas não amarrar consultas a uma empresa
implícita.

---

## 12. Migração dos dados atuais

| Item | Regra |
|---|---|
| Cada processo atual | Vira **1 caso + 1 processo**. Onde a mesma pessoa tem 2 ou 3 processos (23 pessoas), vira **1 caso com N processos** — revisado na triagem |
| Estágio do ciclo | Derivado do status atual: em andamento/com decisão/suspenso → `JUDICIALIZADO`; acordo → `JUDICIALIZADO`; acordo finalizado → `QUITADO`; encerrado → `ENCERRADO` |
| Pessoas com desligamento e sem processo | **Viram casos `POTENCIAL`** com prescrição calculada — 25 pessoas hoje sem `termination_date` ficam de fora até o dado ser preenchido |
| Contexto congelado | Preenchido com o que houver (empresa, projeto do texto atual); o que faltar entra no checklist de completude |
| Pedidos | Não existem no acervo. Passam a ser registrados dos novos casos em diante — sem retroagir |
| Timeline | Uma entrada `CARGA_INICIAL` por caso |
| Datas de distribuição e audiência | **Não existem** (0 de 148). A triagem preenche as dos casos ativos; nos encerrados, ficam vazias e assim são exibidas |

A honestidade do último item importa: o sistema deve mostrar "não informado", nunca uma data
inventada por inferência.

---

## 13. Roadmap revisado

| Fase | Entrega | Por quê nesta ordem |
|---|---|---|
| **0 — Fundação** | Caso como raiz · timeline · procedência · registro de regras e Sinal · migração dos 148 | Todas as fases seguintes escrevem sobre essas três coisas. Fazer depois é refazer |
| **A — Operação** | Eventos e agenda · pipeline configurável · papéis · central de alertas (sinais) · triagem | O uso diário, sem tocar em dinheiro |
| **B — Negociação e dinheiro** | Negociações · propostas · acordos · parcelas · lançamentos · integração com o CAP | Depende da timeline e da fundação |
| **C — Patrimônio** | Restrições · alvos · contas · depósitos · capital retido | Depende dos lançamentos |
| **D — Prevenção** | Vínculo RH · casos potenciais · prescrição · pedidos · contexto congelado · score · fichas 360º | É a fase que diferencia o produto — e a que mais depende de dado acumulado |
| **E — Automação** | Captura de publicações · notificações · resumo por IA · portal de escritórios | Só com a operação madura |

Mudança relevante em relação à v2: **a fundação virou fase própria**. A raiz do agregado, a
timeline e o motor de regras precisam existir antes de qualquer funcionalidade, senão cada fase
seguinte cria seu próprio centro — exatamente o que você quer evitar.

A fase D (prevenção) depende de dado que só nasce com a operação rodando: por isso ela vem
depois, mas **a coleta começa na fase 0**, com o contexto congelado e a procedência.

---

## 14. Decisões pendentes

Já resolvidas: caso como raiz · agenda derivada de eventos · pipeline configurável · negociação
separada · papéis múltiplos · alertas sem agendador · conta bancária como catálogo (mascarada) ·
integração enriquece sem substituir.

Em aberto — as quatro primeiras bloqueiam a fase 0:

1. **Prazo prescricional a adotar.** Dois anos após o desligamento é a regra geral trabalhista.
   Confirma? Casos cíveis e tributários têm prazos distintos — modelo por tipo de caso.
2. **Abertura automática de caso potencial no desligamento.** Todo desligado vira caso
   `POTENCIAL` automaticamente, ou só quando alguém marcar? Automático dá cobertura total e
   volume alto; manual dá curadoria e risco de esquecimento. **Recomendo automático**, com
   encerramento em massa por prescrição.
3. **Fatores e pesos do score de risco.** Preciso da sua leitura do negócio: o que faz um
   desligamento virar ação com mais frequência?
4. **SLA de cada etapa do pipeline** (pendente da v2).
5. **Percentuais de provisão por risco** (pendente da v2) — a série histórica só existe se
   começar.
6. **Política de retenção e anonimização** (§11).
7. **Honorários de escritório** como lançamento do caso ou financeiro corporativo (pendente).
8. **Quem preenche o papel "Responsável RH"** (pendente).

---

## 15. Riscos

| Risco | Mitigação |
|---|---|
| O agregado grande virar objeto monolítico e lento | §2.4: a raiz é ponto de entrada dos comandos, não um objeto carregado inteiro |
| Casos potenciais automáticos gerarem ruído (centenas abertos) | Encerramento automático por prescrição + filtro padrão que esconde os de risco baixo |
| O motor de regras crescer para uma DSL por pressão de flexibilidade | §6.2 registra a decisão e o caminho alternativo (construtor guiado) |
| Score de risco ser lido como previsão confiável | Score sempre exibido com os fatores que o compõem; nunca um número solto |
| A fase 0 parecer "não entregar nada" ao usuário final | Ela entrega a timeline e a triagem — visíveis desde o primeiro dia |
| Pedidos não serem registrados e a análise de prevenção nunca acontecer | Fazem parte do checklist de completude do caso judicializado |
| Reimportação da planilha sobrescrevendo a operação | Corte da fonte oficial (§9) |

---

## 16. Documentos relacionados

- [`JURIDICO_IMPORTACAO_PLANILHA.md`](JURIDICO_IMPORTACAO_PLANILHA.md) — a carga inicial e as
  regras de preservação que a §9 promove a política do módulo
- [`JURIDICO_RUNBOOK_DEPLOY.md`](JURIDICO_RUNBOOK_DEPLOY.md) — deploy do módulo
- [`SGC_DOCUMENTACAO_COMPLETA.md`](SGC_DOCUMENTACAO_COMPLETA.md) — estado atual do sistema
- [`CHANGELOG.md`](../CHANGELOG.md) — histórico de mudanças
