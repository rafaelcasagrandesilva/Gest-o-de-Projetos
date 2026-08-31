# Jurídico — análise operacional

**Documento de operação, não de arquitetura.** Escrito do ponto de vista de quem vai usar o
Workspace todos os dias pelos próximos cinco anos. Sem código, sem migrations, sem endpoints.
Complementa [`JURIDICO_ARQUITETURA_OPERACIONAL.md`](JURIDICO_ARQUITETURA_OPERACIONAL.md) (v3).

---

## 1. Um dia de trabalho

*Gerente Jurídico da M&E. Terça-feira, 8h15.*

### 8h15 — a primeira tela

Abro o SGC e caio direto na **Central de Trabalho** do Jurídico. Não quero um dashboard: quero
saber o que **quebra hoje se ninguém agir**. A tela abre com um recorte fixo — *hoje, minha
equipe* — e no máximo três blocos acima da dobra:

```
┌── AGORA (exige ação hoje) ────────────────────────────────────┐
│ ⚖ 2 audiências hoje    · 1 SEM PREPOSTO DESIGNADO   14h · Campinas
│ ⏰ 1 prazo fatal vence hoje  · contestação — Ana         (17h)
│ 🔒 1 bloqueio novo (ontem)   · R$ 12.400 — conta Itaú
└───────────────────────────────────────────────────────────────┘
┌── ATÉ SEXTA ──────────────────────────────────────────────────┐
│ 4 audiências · 3 prazos · 6 parcelas vencendo (R$ 38.200)
└───────────────────────────────────────────────────────────────┘
┌── PRECISA DE DONO ────────────────────────────────────────────┐
│ 3 casos sem responsável · 2 processos novos aguardando triagem
└───────────────────────────────────────────────────────────────┘
```

O que eu faço nos primeiros dez minutos, na ordem: **designo o preposto** da audiência das 14h
(um clique, na própria linha), **confirmo com a Ana** que a contestação sai hoje, e **abro o
bloqueio** — é o único item que pode virar crise.

### 8h30 — o bloqueio

Clico no alerta e caio no **caso**, não numa tela de bloqueios. Preciso ver, na mesma tela: de
quem é a conta (empresa ou sócio), quanto foi bloqueado, qual processo originou, em que fase
está e o que já pagamos nele. Se for conta de sócio, isso vira ligação para a diretoria antes das
9h — é o único evento do módulo que muda o dia de outra pessoa.

Registro o fato, anexo o comprovante do bloqueio, marco a providência (embargos, prazo) e a
timeline já mostra tudo em ordem. **Não abro cinco telas para isso.**

### 9h00 — a fila de trabalho

Volto à central e trabalho a lista de **providências abertas**, ordenada por vencimento. Cada
item resolve em uma de três ações: concluir, reprogramar ou repassar. O que não é meu, eu passo;
o que travou, eu comento — o comentário vira fato na timeline, não um post-it perdido.

### 10h30 — as negociações

Duas vezes por semana, olho a fila de **negociações abertas**, ordenada por dias desde a última
interação. Aqui eu não quero saber de valor total: quero saber **quem está esperando resposta
nossa**. Uma proposta parada há 20 dias é dinheiro que fica mais caro.

### 14h00 — a audiência

Terminada a audiência, o preposto (ou eu) registra o **resultado** no evento: houve acordo?
adiou? virou perícia? O sistema, a partir daí, faz o encadeamento sozinho — resultado vira fato
na timeline, muda a fase quando for o caso e, se houve proposta, abre a negociação.

### 17h00 — fecho o dia

Volto à central. Quero vê-la **vazia** na coluna "agora". Se sobrou item, ele passa para amanhã
com motivo — não some.

---

## 2. O que cada papel precisa

A mesma base de dados, quatro leituras diferentes. Este é o ponto que mais influencia as telas.

| | **Analista jurídico** | **Gerente jurídico** | **Financeiro** | **RH** | **Diretoria** |
|---|---|---|---|---|---|
| **Primeira tela** | Minha fila de trabalho | Central de trabalho da equipe | Parcelas e desembolso do mês | Radar de prescrição | Painel do passivo |
| **Frequência** | O dia inteiro | 3× ao dia | 2× por semana | Semanal | Mensal |
| **Pergunta** | O que eu faço agora? | O que a equipe está deixando cair? | Quanto sai este mês e para quem? | Quem desligamos e ainda pode processar? | Quanto isso nos custa e por quê? |
| **A um clique** | Timeline do caso · prazos · documentos | Carteira por analista · alertas críticos | Parcela → título no CAP · comprovante | Desligado → caso → contexto | Passivo por obra · provisão · tendência |
| **Não precisa ver** | Provisão, indicadores | Detalhe de cada documento | Fase processual | Valores de acordo | Prazos e providências |

Três observações que mudam o desenho:

- **O RH é usuário do módulo**, não fonte de dados. Ele tem uma pergunta própria (quem ainda pode
  processar) e uma tela própria (radar de prescrição). Se ele só existir como origem de
  desligamento, a prevenção não acontece.
- **O financeiro não quer entrar no caso.** Ele quer a lista de parcelas do mês, com o vínculo
  para o título. Navegação caso a caso é o que o faz abandonar o módulo e voltar para a planilha.
- **A diretoria olha mensalmente e quer causa, não número.** "R$ 4,1 milhões de passivo" não muda
  decisão nenhuma; "78% dos pedidos de horas extras vêm de três obras" muda.

---

## 3. Ritmo: o que é diário, semanal, mensal e raro

| Cadência | Tarefas |
|---|---|
| **Diário** | Central de trabalho · audiências do dia · prazos que vencem · bloqueios novos · registrar andamentos e resultados · concluir ou reprogramar providências · triar processos novos |
| **Semanal** | Revisão da carteira por analista · negociações paradas · casos sem movimentação · radar de prescrição (RH) · designar prepostos da semana seguinte |
| **Quinzenal** | Conferência de parcelas a vencer com o financeiro · revisão de casos em execução |
| **Mensal** | Fechamento: provisão da competência · conciliação com o Contas a Pagar · painel do passivo para a diretoria · relatório de desfechos e custo · revisão dos casos parados há mais de 60 dias |
| **Trimestral** | Revisão de SLA das etapas · desempenho por escritório · ajuste das regras de alerta · análise de pedidos recorrentes → devolutiva para a operação |
| **Semestral/anual** | Revisão dos percentuais de provisão · política de retenção · auditoria de completude do acervo · revisão de perfis e permissões |
| **Uma vez** | Importação da planilha (carga inicial) · triagem inicial dos 148 · corte da fonte oficial |

A leitura desta tabela é a base da §6: **só o que é diário e semanal merece estar no menu
principal.**

---

## 4. Os fluxos operacionais

Trinta fluxos, agrupados por natureza. Os cinco que você descreveu estão aqui, com o restante
que aparece quando se opera de verdade.

### A. Originação — como um caso nasce

**A1 · Desligamento vira caso potencial** *(automático)*
RH registra o desligamento → nasce caso `POTENCIAL` com prescrição calculada → score de risco →
entra no radar. **Ninguém digita nada.** Sem isso, prevenção é boa intenção.

**A2 · Prescrição consumada** *(automático)*
Passados os dois anos sem ação → caso vai para `PRESCRITO` e sai do radar. Encerramento em massa,
não um a um. **É o fluxo que impede o radar de virar um cemitério de 8.000 linhas.**

**A3 · Citação recebida — o caso judicializa**
Chega a citação → localizo o caso potencial pelo CPF/nome → confirmo → vinculo o processo
(número CNJ, vara, valor da causa, pedidos) → designo responsável → gero as providências de
abertura (contestação, prazo, audiência). O caso **não nasce agora**: ele muda de estágio, e a
prescrição que estava correndo vira histórico.

**A4 · Processo sem caso prévio**
Terceiro, cível, tributário, ou ex-colaborador anterior à implantação. Cria caso e processo na
mesma ação, com origem diferente de desligamento.

**A5 · Processo importado (legado) → triagem**
Os 148 atuais. Cada um passa por: confirmar partes → definir responsável → definir etapa →
registrar o que se sabe (fase, próxima audiência) → completar o mínimo. Depois disso ele entra no
regime normal.

**A6 · Notificação extrajudicial**
Sindicato, MPT, notificação do reclamante. Vira fato no caso (ou cria caso), com prazo de
resposta — **sem processo**. Este fluxo não existia até a v3.

### B. Condução — o dia a dia do processo

**B1 · Registro de andamento** — manual hoje; por publicação no futuro. Se abrir prazo, gera
providência no mesmo gesto.

**B2 · Triagem de publicação** *(futuro)* — publicação capturada entra numa fila; o analista
confirma, descarta ou converte em prazo. **Nunca entra direto no caso**: fonte externa enriquece,
não governa.

**B3 · Providência: abrir → cumprir** — com responsável e vencimento; concluir exige dizer o quê.

**B4 · Mudança de fase processual** — sentença, recurso, execução. Muda o eixo processual e,
quase sempre, a etapa operacional.

**B5 · Reatribuição de responsável** — saída de analista, férias, redistribuição. Precisa ser em
lote: 200 casos não se movem um a um.

**B6 · Contratação ou troca de escritório** — com data, porque o desempenho por escritório se
mede por período.

**B7 · Comentário/observação** — o mais usado de todos. Vira fato datado, não campo de texto que
alguém sobrescreve.

### C. Agenda

**C1 · Audiência: agendar → designar preposto → realizar → registrar resultado → timeline**
O seu Fluxo 5. Acrescento a **designação de preposto** como passo próprio: é o que mais falha na
prática, e por isso é alerta ("audiência hoje sem preposto").

**C2 · Adiamento ou cancelamento** — o evento não é apagado: muda de status e o novo é criado
apontando o anterior. Audiência adiada três vezes é informação sobre o processo.

**C3 · Perícia: agendar → laudo → impugnação** — com o laudo anexado e prazo de manifestação.

**C4 · Compromisso interno** — reunião com a obra, alinhamento com o RH. Entra na mesma agenda.

### D. Negociação e acordo

**D1 · Abrir negociação** — por iniciativa nossa, do reclamante ou do juízo, com canal (direto,
conciliação, câmara arbitral, mediação).

**D2 · Ciclo de propostas** — propor → recusa com motivo → contraproposta → aceite. Cada volta é
registro; o motivo da recusa é o que ensina.

**D3 · Acordo homologado** — nasce da proposta aceita → parcelas geradas → cada uma vira título
no Contas a Pagar e evento de vencimento.

**D4 · Acordo extrajudicial** — o seu Fluxo 3: negociação → acordo → parcelas → quitação, **sem
processo nenhum**. O caso encerra como quitado, e essa é uma das melhores notícias possíveis:
resolveu antes de virar ação.

**D5 · Acordo descumprido** — parcela vencida não paga → caso vai para inadimplente → retomada da
execução. Reversão, não apagamento.

### E. Financeiro

**E1 · Parcela vence → pagamento → baixa → quitação** — a baixa acontece no financeiro e retorna
para o caso.

**E2 · Depósito recursal ou garantia → levantamento** — dinheiro que sai e pode voltar; não é
custo enquanto não for perdido.

**E3 · Custas, honorários, perícia** — lançamentos do caso que compõem o custo real.

**E4 · Estorno** — pagamento errado, devolução. Fato novo apontando o anterior.

**E5 · Fechamento mensal** — provisão da competência + conciliação com o CAP. Mensal, em lote,
nunca caso a caso.

### F. Patrimônio

**F1 · Bloqueio: registrar → acompanhar → liberar** — o seu Fluxo 4.

**F2 · Bloqueio convertido em pagamento** — o dinheiro não volta; vira quitação parcial.

**F3 · Bloqueio em conta de sócio** — mesmo fluxo, **escalonamento imediato**: alerta crítico,
notificação à diretoria, tratamento prioritário.

**F4 · Penhora de bem ou de faturamento** — alvo diferente de conta, com impacto operacional
(veículo penhorado é veículo que a obra não usa).

### G. Encerramento

**G1 · Quitado → aguardando arquivamento → arquivado** — a fila que hoje some dentro de
"encerrado".

**G2 · Improcedência** — arquiva sem obrigação. Vitória, e precisa aparecer como tal nos
indicadores de desfecho.

**G3 · Arquivamento definitivo → retenção** — depois de N anos, anonimização preservando os
números.

### H. Gestão

**H1 · Revisão semanal de carteira** — por analista: quantos casos, quantos parados, quantos
prazos na semana. É onde se enxerga sobrecarga antes do prazo perdido.

**H2 · Auditoria de completude** — casos ativos sem responsável, sem etapa, sem valor, sem
próximo compromisso.

**H3 · Devolutiva para a operação** *(o fluxo mais valioso e o mais esquecido)* — trimestral:
pedidos recorrentes → causa provável → conversa com a obra. É o que fecha o ciclo entre jurídico
e prevenção. **Se este fluxo não acontecer, o módulo vira um belo arquivo.**

**H4 · Onboarding de analista** — recebe carteira, vê só a sua fila.

**H5 · Configuração** — SLA, regras, percentuais de provisão, catálogos. Trimestral ou menos.

---

## 5. Dashboard: minha opinião crítica

**Concordo com você, com uma ressalva que muda o desenho.**

Um painel operacional é mais útil que um estatístico porque responde à pergunta que o usuário
realmente tem às 8h da manhã: *o que eu faço agora?* Números respondem a uma pergunta que
ninguém faz diariamente: *como estamos?*

### A ressalva: um painel operacional só funciona se puder ser esvaziado

O modo de falha de painéis de pendências é sempre o mesmo: eles listam tudo o que está fora do
ideal, a lista nunca zera, e em três semanas as pessoas param de olhar. Vira uma segunda caixa de
entrada — que ninguém lê.

A disciplina que evita isso:

1. **A coluna "agora" precisa ser finalizável em um dia.** Se tem 40 itens, não é lista de
   trabalho: é relatório. Só entram aí: audiência de hoje, prazo que vence hoje, bloqueio novo,
   parcela que vence hoje.
2. **Cada item tem dono.** Alerta sem responsável é alerta de ninguém. O padrão da tela é *meus
   itens*; a visão da equipe é uma escolha, não o default.
3. **Todo item tem ação na própria linha** — concluir, reprogramar, repassar, dar ciência. Se
   obriga a abrir três telas, o item não é trabalhado.
4. **O que não é de hoje não fica no bloco de hoje.** "Sem movimentação há 60 dias" é revisão
   *semanal*, não urgência diária. Misturar horizonte é o que faz o painel inchar.
5. **Silenciar é um recurso, não uma falha.** Dar ciência e adiar com motivo mantém a lista
   honesta. Sem isso, as pessoas passam a ignorar categorias inteiras — inclusive as críticas.

### Então os números somem?

Não: **mudam de lugar e de cadência**.

| | Painel operacional | Painel estratégico |
|---|---|---|
| Quem | Analista, gerente | Diretoria |
| Quando | Várias vezes ao dia | Uma vez por mês |
| Pergunta | O que faço agora? | Onde estamos errando? |
| Onde | Tela inicial do workspace | Aba separada, ou dentro de Indicadores |

E um critério para o painel estratégico: **todo número precisa sugerir uma decisão**. "Passivo:
R$ 4,1 milhões" não sugere nada. "Três obras concentram 60% dos pedidos de horas extras" sugere
uma conversa com a operação. Se um indicador não muda nenhuma decisão, ele não merece espaço —
merece um relatório mensal.

---

## 6. O que quase nunca será usado

Tudo o que é mensal ou mais raro sai do menu principal e vai para **Administração**:

| Funcionalidade | Uso real |
|---|---|
| Importação da planilha | **Uma vez na vida** — e depois fica desabilitada |
| Catálogos: empresas, projetos, câmaras, tipos de pedido | Raro, ao aparecer um caso novo |
| Escritórios e advogados | Algumas vezes por ano |
| Configuração de etapas e SLA | Trimestral |
| Regras de alerta e limiares | Trimestral |
| Percentuais de provisão | Semestral |
| Perfis e permissões | Raro |
| Histórico de alterações (auditoria) | Só em incidente |
| Política de retenção | Anual |
| Relatórios completos | Mensal |

**Menu principal do Jurídico** (o que é diário ou semanal):

```
Central de trabalho      ← abre aqui
Casos                    ← lista, busca, filtros salvos
Agenda                   ← calendário e prazos
Negociações              ← fila por tempo parado
Financeiro do caso       ← parcelas, desembolso, capital retido
Radar de prescrição      ← RH e prevenção
Painel do passivo        ← diretoria (mensal)
Administração ▸          ← todo o resto
```

Sete itens. Um menu com quinze opções faz o usuário parar de ler o menu.

---

## 7. Teste de escala: 2031

**Cenário:** 5.000 processos, 8.000 ex-colaboradores, centenas de acordos, milhares de eventos e
parcelas, vários escritórios e advogados. Onde o desenho de hoje quebra — e o que mudar **antes**
de implementar.

### 7.1 O radar de prescrição vira 8.000 linhas

**O problema.** Se todo desligamento abre caso potencial, em cinco anos são 8.000 casos
potenciais, dos quais talvez 15% viram ação. A lista de casos fica dominada por ruído e o radar
vira inútil.

**Mudar agora:**
- Casos potenciais **não aparecem na lista de casos** por padrão — vivem no radar, que é outra
  tela.
- O radar mostra **os próximos a prescrever e os de score alto**, não todos.
- **Encerramento automático por prescrição**, sem intervenção.
- O RH trabalha o radar por **safra** (desligados do mês), não pelo acervo inteiro.

### 7.2 A central de alertas vira 300 itens por dia

**O problema.** Sinais escalam com o acervo. Com 5.000 casos, "sem movimentação há 60 dias"
sozinho pode gerar centenas de itens.

**Mudar agora:**
- Alerta **sempre tem dono**; a tela padrão é a do usuário.
- **Teto explícito para "crítico"**: se tudo é crítico, nada é. Crítico só o que estoura hoje.
- Regras com **volume esperado** monitorado: uma regra que dispara em 20% do acervo está mal
  calibrada, e isso precisa ser visível para quem configura.
- **Agregação por categoria** com detalhe sob demanda: "18 casos sem movimentação" numa linha, não
  18 linhas.

### 7.3 O kanban com 5.000 cartões

**O problema.** Pipeline visual é ótimo com 50 cartões e inútil com 5.000.

**Mudar agora:** o kanban nasce **escopado** (minha carteira / meu time), com contagem por coluna
e paginação dentro da coluna. A visão global do pipeline é um **gráfico de contagem**, não um
quadro arrastável.

### 7.4 A busca vira a funcionalidade mais usada

**O problema.** Com 5.000 processos, ninguém navega: todo mundo busca. E busca por coisas
imperfeitas — número parcial, nome com grafia diferente, CPF com ou sem pontuação. O acervo atual
já tem números mascarados (`010XXXX-54.2025...`), o que prova o ponto.

**Mudar agora:** busca única no topo do workspace, tolerante a pontuação e a fragmento de número,
cobrindo caso, processo, pessoa, CPF e empresa — com resultado tipado. **É a tela mais importante
que ninguém lembra de projetar.**

### 7.5 Ações em lote deixam de ser conveniência

**O problema.** Redistribuir a carteira de um analista que saiu, encerrar 400 casos prescritos,
dar ciência em 30 alertas: um a um é inviável.

**Mudar agora:** seleção múltipla e ação em lote nas listas — atribuir responsável, mudar etapa,
encerrar por prescrição, dar ciência. Com prévia do que vai acontecer, como já fazemos na
exclusão em massa dos custos de projeto.

### 7.6 O financeiro não pode navegar caso a caso

**O problema.** Centenas de parcelas por mês. Abrir cada caso é o caminho mais curto para o
financeiro voltar à planilha.

**Mudar agora:** tela de **parcelas do mês** como lista transacional — filtro, ordenação, baixa em
lote, exportação e vínculo com o título do CAP. O caso é um link, não o caminho.

### 7.7 A timeline de um caso antigo terá 300 fatos

**O problema.** Cinco anos de andamentos, eventos e comentários viram uma rolagem infinita, e o
que importa se perde.

**Mudar agora:** timeline com **filtro por tipo de fato** e visão **"só marcos"** como padrão em
casos com muito histórico (distribuição, sentença, acordo, pagamento, arquivamento). O detalhe
fica a um clique.

### 7.8 Sem notificação, a operação não escala

**O problema.** O modelo puxado (o usuário abre a tela) funciona para uma equipe pequena. Com
vários analistas e escritórios externos, quem não abrir o sistema perde prazo.

**Mudar agora:** nada de infraestrutura — mas **projetar as regras já com destinatário e canal**,
para que ligar notificação seja configuração, não redesenho. O canal em si fica para quando
houver agendador (hoje não há).

### 7.9 Visões salvas viram necessidade

**O problema.** Cada papel reconstrói o mesmo filtro todo dia.

**Mudar agora:** **filtros salvos por usuário**, com uma visão padrão por papel. É barato de
construir junto com as listas e caro de acrescentar depois, quando cada tela já tem sua própria
lógica de filtro.

### 7.10 Duplicidade de processo

**O problema.** Com 5.000 processos e várias fontes (manual, importação, futura captura), o mesmo
número entra duas vezes.

**Mudar agora:** número CNJ como **chave forte**, com aviso na criação quando já existir e uma
rotina de conciliação de duplicados na Administração.

### O que **não** muda com a escala

Timeline como projeção, agregado do caso, eventos genéricos, regras em código com parâmetros,
integração com o CAP por chave de origem. Nenhum desses vira gargalo por volume — todos são
consultas indexadas por caso e data.

---

## 8. As mudanças que proponho antes de implementar

Consolidando o que a análise operacional revelou e que a v3 não previa:

| # | Mudança | Motivo |
|---|---|---|
| 1 | **Casos potenciais fora da lista de casos**, em radar próprio com encerramento automático | Sem isso, 8.000 registros de ruído afogam 800 casos reais |
| 2 | **Busca global tolerante** como elemento fixo do workspace | Com 5.000 processos, busca substitui navegação |
| 3 | **Ações em lote** nas listas, com prévia | Redistribuição e encerramento em massa são operação normal, não exceção |
| 4 | **Tela de parcelas do mês** para o financeiro | Impede o retorno à planilha |
| 5 | **Designação de preposto** como passo e alerta próprios | É a falha operacional mais comum em audiência |
| 6 | **Teto e calibragem de alertas críticos**, com volume monitorado | Impede que a central vire ruído |
| 7 | **Timeline com "só marcos"** como padrão em casos longos | 300 fatos sem hierarquia escondem o que importa |
| 8 | **Filtros salvos por usuário e visão padrão por papel** | Barato agora, caro depois |
| 9 | **Kanban escopado** por carteira, nunca global | Quadro com 5.000 cartões é inutilizável |
| 10 | **Regras já com destinatário e canal** | Ligar notificação vira configuração, não redesenho |
| 11 | **Fluxo de devolutiva para a operação** (trimestral) como parte do módulo | É o que transforma o jurídico em prevenção — e o que mais some se não for previsto |
| 12 | **RH como usuário com tela própria**, não apenas origem de dado | Sem tela, o radar não é olhado por ninguém |

---

## 9. O que eu não mudaria

Para não confundir refinamento com inchaço:

- **Não** criaria tela separada para bloqueios, documentos ou partes: são abas do caso.
- **Não** criaria dashboard por escritório antes de ter vários escritórios.
- **Não** faria o kanban a tela principal: a fila de trabalho é mais eficiente que arrastar
  cartão.
- **Não** acrescentaria personalização de layout: a padronização é o que permite que uma pessoa
  ajude a outra.
- **Não** criaria app móvel agora. O que é móvel de fato — confirmar audiência, ver o dia — cabe
  numa tela responsiva.

---

## 10. Como eu saberia que deu certo

Métricas de adoção que valem mais que qualquer indicador jurídico:

| Sinal de que funcionou | Sinal de que falhou |
|---|---|
| A central de trabalho é esvaziada quase todo dia | Itens críticos com semanas de idade |
| Nenhum prazo perdido por falta de registro | Prazo descoberto pelo tribunal, não pelo sistema |
| A timeline dos casos ativos tem fatos toda semana | Casos parados com "carga inicial" como último fato |
| O financeiro paga a partir do módulo | O financeiro mantém uma planilha paralela |
| A devolutiva trimestral gerou mudança na obra | Relatório bonito, operação inalterada |
| Analista novo produz na primeira semana | Cada um usa o sistema de um jeito |

O segundo item de cada linha é o que eu observaria nos primeiros três meses. Nenhum deles é sobre
tecnologia.
