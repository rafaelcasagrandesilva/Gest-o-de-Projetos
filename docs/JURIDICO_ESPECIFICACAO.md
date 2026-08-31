# Jurídico — especificação funcional definitiva

**Documento de aprovação.** Sem código, migrations ou endpoints.
Base: [`JURIDICO_ARQUITETURA_OPERACIONAL.md`](JURIDICO_ARQUITETURA_OPERACIONAL.md) (v3) e
[`JURIDICO_OPERACAO.md`](JURIDICO_OPERACAO.md).

**A régua deste documento:** cada menu, campo, estado e alerta precisa justificar a própria
existência. O que não passou está registrado em "o que eu cortei" — porque cortar é a parte
difícil.

---

## 0. Três decisões que simplificam tudo

Antes da especificação, as três escolhas que mais reduzem complexidade — duas delas revertem
propostas minhas anteriores:

**1. O radar de risco não cria casos.** Na v3 eu propus abrir um caso `POTENCIAL` a cada
desligamento. Estava errado: em cinco anos seriam 8.000 registros vazios. O radar passa a ser
uma **visão calculada sobre os desligados do RH** — nenhum caso nasce até existir fato concreto
(notificação, citação, contato de advogado). **Zero casos fantasmas**, e o RH continua dono do
desligamento.

**2. Casos e Processos são um único menu.** São a mesma pergunta operacional em dois níveis. Duas
listas quase idênticas seriam a duplicação que queremos evitar. O processo é uma aba do caso, e
buscar por número de processo leva ao caso.

**3. Acordos não é menu.** Um acordo só é consultado por quem veio da negociação que o gerou ou
das parcelas que ele criou. Um menu próprio seria uma terceira porta para o mesmo dado.

---

## 1. Estrutura do Workspace

### Menu principal — sete itens

| Menu | Quem usa | Pergunta que responde | Ação típica ali | Frequência |
|---|---|---|---|---|
| **Central de Trabalho** | Analista, gerente | O que eu preciso resolver hoje? | Concluir, reprogramar, repassar, dar ciência | Várias vezes ao dia |
| **Casos** | Analista, gerente | Onde está o caso X? Quais casos têm característica Y? | Buscar, filtrar, abrir, registrar fato | Diária |
| **Agenda** | Analista, gerente, preposto | O que acontece nos próximos dias? | Agendar, designar preposto, registrar resultado | Diária |
| **Negociações** | Gerente, analista | Quem está esperando resposta nossa? | Propor, registrar recusa, fechar acordo | Semanal |
| **Financeiro do contencioso** | Financeiro, gerente | Quanto sai este mês? Quanto está indisponível? | Baixar parcela, registrar depósito e bloqueio | Semanal |
| **Radar de risco** | RH, gerente | Quem ainda pode processar? Onde o risco se concentra? | Analisar safra, converter em caso | Semanal |
| **Painel executivo** | Diretoria | Quanto isso custa e onde está concentrado? | Ler e clicar para investigar | Mensal |

### Administração — tudo o que é mensal ou mais raro

Importação (uma vez na vida, depois desabilitada) · catálogos (empresas, projetos, câmaras,
tipos de pedido) · escritórios e advogados · etapas operacionais e SLA · regras de alerta ·
percentuais de provisão · política de retenção · relatórios completos · histórico de alterações.

### Sobreposições que eu resolvi

| Sobreposição | Resolução |
|---|---|
| Casos × Processos | **Um menu.** Processo é aba do caso; a busca por número leva ao caso |
| Negociações × Acordos | **Um menu.** O acordo aparece dentro da negociação que o gerou e nas parcelas |
| Bloqueios × Financeiro | **Aba de Financeiro.** Mesma pergunta (dinheiro), mesmo público. A urgência do bloqueio novo é tratada na Central |
| Agenda × Central | **Recortes diferentes.** A Central mostra hoje e o que precisa de ação; a Agenda mostra o calendário e permite planejar |
| Radar × Casos | **Separados por natureza.** Radar não tem casos — tem pessoas com risco |
| Painel executivo × Relatórios | Painel responde perguntas fixas na tela; relatórios são extrações sob demanda, em Administração |

### O que eu cortei

- **Quadro kanban.** A etapa operacional continua existindo como campo (filtro e agrupamento nas
  listas, base do alerta de SLA), mas **sem tela de arrastar cartão**: com 5.000 casos ela é
  inutilizável, e a fila de trabalho resolve melhor o mesmo problema.
- **Menu de documentos, partes e bloqueios** — abas do caso.
- **Dashboard por escritório** — só faz sentido com vários escritórios; vira relatório.
- **Menu de Relatórios no principal** — uso mensal, vai para Administração.

---

## 2. Central de Trabalho

> **Regra fundadora:** não é um relatório de problemas. É uma fila de trabalho executável.
> Se não pode ser esvaziada, está errada.

### Escopo padrão

Abre em **meus itens, hoje**. O gerente tem um alternador para *minha equipe*. Não há visão
"tudo do sistema" — ela é a origem da lista infinita.

### Os três blocos

**AGORA** — o que quebra hoje se ninguém agir. Só quatro famílias de regra podem chegar aqui:

| Item | Quando aparece | Ações na linha |
|---|---|---|
| Audiência de hoje | Evento de audiência hoje | Designar preposto · Registrar resultado · Abrir caso |
| Audiência hoje **sem preposto** | Idem, sem designação | Designar (destaque crítico) |
| Prazo que vence hoje ou vencido | Prazo não cumprido | Concluir · Reprogramar · Repassar |
| Bloqueio novo (24h) | Restrição criada ontem ou hoje | Dar ciência · Abrir caso |
| Parcela que vence hoje | Parcela sem baixa | Marcar paga · Reprogramar |

**Nenhuma outra regra entra em AGORA.** Se o bloco passar de ~12 itens num dia normal, o
problema é de calibragem ou de equipe — e isso precisa ser visível, não escondido com rolagem.

**ATÉ SEXTA** — os próximos sete dias, **agregado por tipo**, uma linha cada:
`4 audiências · 3 prazos · 6 parcelas (R$ 38.200) · 2 perícias`. Clicar expande a lista. Serve
para planejar, não para executar hoje.

**PRECISA DE DONO** — o que não é de ninguém: casos ativos sem responsável jurídico, processos
novos aguardando triagem, publicações não triadas (quando existirem). Ação: atribuir, em lote se
preciso.

### O que fica fora da Central

Casos sem movimentação há 60 dias, negociações paradas, etapa acima do SLA e completude
incompleta **não aparecem na Central**. São a **Revisão semanal** — uma tela própria, aberta uma
vez por semana pelo gerente. Misturar horizontes é o que incha o painel.

### Ciclo de vida de um item

| Situação | O que acontece |
|---|---|
| **Resolvido** | O item some quando o fato que o gerou muda: prazo cumprido, audiência com resultado, parcela baixada, bloqueio com ciência |
| **Reprogramado** | Nova data e motivo obrigatórios. Sai da lista de hoje, volta na data nova. O motivo vira fato na timeline |
| **Repassado** | Novo responsável. Sai da minha lista, entra na dele — nunca desaparece do sistema |
| **Silenciado** | Ciência com motivo, por prazo máximo de **30 dias**. Não existe "silenciar para sempre" |
| **Sem ação** | Permanece e envelhece visivelmente (idade em dias na linha) |

### Cinco travas contra a lista infinita

1. Só quatro famílias de regra podem ser críticas.
2. Todo item tem dono; a visão padrão é pessoal.
3. Toda ação é executável na linha, sem abrir outra tela.
4. Regras de horizonte semanal vivem na Revisão semanal.
5. Toda regra tem **volume esperado monitorado**: se dispara em mais de 10% do acervo, aparece
   sinalizada em Administração para recalibragem.

---

## 3. Painel executivo

A diretoria não navega pelo Jurídico: entra, lê, e no máximo clica para investigar. Uma tela, um
conjunto de filtros, oito respostas.

### Os indicadores que ficam

| Indicador | Pergunta | Decisão que ele muda | Histórico |
|---|---|---|---|
| **Exposição em andamento** | Quanto temos em processos ativos? | Provisionar mais ou menos | Mensal |
| **Em negociação** | Quanto está na mesa? | Autorizar alçada, priorizar acordos | Mensal |
| **Acordos firmados (a pagar)** | Quanto está comprometido? | Fluxo de caixa dos próximos meses | Mensal |
| **A pagar nos próximos 90 dias** | Quanto sai? | Programação de caixa | Mensal |
| **Pago no período** | Quanto já saiu? | Comparar com o provisionado | Mensal |
| **Capital indisponível** | Quanto está bloqueado ou depositado? | Ação urgente (é dinheiro parado) | Mensal |
| **Desfecho do período** | Quantos encerramos, com que custo, com que desconto? | Avaliar a estratégia de acordo | Mensal |
| **Concentração de risco** | Onde está o risco? | Onde intervir na operação | Trimestral |

### O que eu descarto — e por quê

| Descartado | Motivo |
|---|---|
| **Valor da causa como número principal** | É o que o reclamante pede, inflado por definição. Nosso acervo pede R$ 6,1 milhões; o que pagamos é uma fração. Um número que não prevê desembolso não orienta decisão. Fica como contexto na ficha do caso |
| Contagem total de processos | Vaidade. 148 ou 300 não muda decisão nenhuma sem valor associado |
| Pizza por status | Bonito, não acionável |
| Evolução da quantidade de casos | Cresce com a empresa; não diz nada sobre gestão |
| Ranking de advogados | Convite a conclusão errada com amostra pequena |
| Tempo médio de processo | Governado pelo tribunal, não por nós. Vira relatório trimestral |

### Segmentação — filtros, não telas

Um só painel com três filtros combináveis: **Empresa** (entidade do grupo), **Projeto/obra** e
**Estado (UF)**. Três dashboards separados seriam três telas para manter e nenhuma resposta a
mais.

### Gráficos que ajudam de fato

Só três, e cada um com uma decisão atrás:

1. **Barras horizontais — concentração por obra/empresa** (valor). *Onde intervir.*
2. **Linha — provisão × desembolso, 12 meses.* Estamos provisionando certo?*
3. **Barras — os 10 pedidos mais frequentes e mais caros.** *Que falha operacional corrigir.*

Nada de pizza, gauge ou mapa.

### Tudo é clicável

Todo número abre a lista de casos que o compõe, com o filtro já aplicado. Um indicador que não
permite chegar aos casos é um indicador em que ninguém confia.

---

## 4. Ciclo de vida — cinco eixos pequenos

O erro original foi um campo tentando representar coisas diferentes. A correção **não** é um
campo maior: são eixos pequenos e independentes. **Vinte valores no total.**

### 4.1 Caso (macro) — 4 estados

```
POTENCIAL ──▶ ATIVO ──▶ ENCERRADO
     └────────────────▶ PRESCRITO
```

`POTENCIAL` só existe quando houve fato concreto sem processo (notificação, contato). O radar
não usa este estado — ele nem cria caso.

### 4.2 Situação processual — 5 + 1, só quando existe processo

```
DISTRIBUIDO ──▶ CONHECIMENTO ──▶ RECURSO ──▶ EXECUCAO ──▶ ARQUIVADO
                      SUSPENSO (transversal, retorna ao anterior)
```

Reduzi de oito para cinco: instrução, aguardando sentença e sentença publicada viram
`CONHECIMENTO`. O detalhe do rito está na timeline; o eixo só precisa do que muda decisão.

### 4.3 Situação financeira — 5

```
SEM_OBRIGACAO ──▶ EM_DISCUSSAO ──▶ A_PAGAR ──▶ QUITADO
                                       └──▶ INADIMPLENTE
```

`A_PAGAR` = acordo formalizado ou condenação líquida. `INADIMPLENTE` = parcela vencida sem baixa.

### 4.4 Negociação — 4, por rodada (não por caso)

`ABERTA · SUSPENSA · ENCERRADA_COM_ACORDO · ENCERRADA_SEM_ACORDO`

### 4.5 Bloqueio — 3, por restrição

`ATIVO · LIBERADO · CONVERTIDO_EM_PAGAMENTO`

### 4.6 Encerramento — motivo, não estado

Quando o caso vai para `ENCERRADO`, registra-se **por quê**: `ACORDO_QUITADO` ·
`CONDENACAO_PAGA` · `IMPROCEDENTE` · `DESISTENCIA` · `PRESCRICAO` · `ARQUIVADO_SEM_PAGAMENTO`.
É o que permite medir desfecho sem inventar estados.

### 4.7 Os caminhos paralelos que você listou

| Caminho | Como o modelo representa |
|---|---|
| Processo sem acordo | Processual `ARQUIVADO` + financeira `SEM_OBRIGACAO` + motivo `IMPROCEDENTE` |
| Acordo extrajudicial | Caso `ATIVO` sem processo → negociação → financeira `A_PAGAR` → `QUITADO` |
| Arbitragem | Negociação com canal `CAMARA_ARBITRAL`; o resto é idêntico |
| Acordo rompido | Negociação `ENCERRADA_COM_ACORDO` + financeira `INADIMPLENTE` + processual `EXECUCAO` |
| Decisão sem pagamento | Processual `ARQUIVADO` + financeira `SEM_OBRIGACAO` |
| Execução | Processual `EXECUCAO` (o dinheiro está no eixo financeiro) |
| Bloqueio | Eixo próprio: não altera os demais até liberar ou converter |
| Encerrado sem pagamento | `ENCERRADO` + motivo `IMPROCEDENTE` ou `ARQUIVADO_SEM_PAGAMENTO` |
| Encerrado e quitado | `ENCERRADO` + motivo `ACORDO_QUITADO` + financeira `QUITADO` |

Nenhum caminho exigiu estado novo. **É esse o teste de que os eixos estão certos.**

---

## 5. Agenda

### Tipos de evento — oito

`AUDIENCIA · PERICIA · SESSAO_ARBITRAL · REUNIAO · PRAZO_PROCESSUAL · PRAZO_INTERNO ·
VENCIMENTO_PARCELA · DILIGENCIA`

Tarefa sem data não é evento: é **prazo interno sem data marcada**, que aparece na lista de
pendências, não no calendário. Despacho não é evento — é fato da timeline (já aconteceu).

### Campos

Caso e processo (opcional) · tipo · data e hora · **responsável** (um) · participantes (preposto,
advogado, testemunhas) · local · modalidade (presencial, virtual, híbrida) · link · status ·
resultado · observações.

### Status — 5

`AGENDADO · REALIZADO · ADIADO · CANCELADO · NAO_COMPARECIDO`

### Adiamento com histórico — a regra que você pediu

Uma audiência remarcada **nunca desaparece**:

1. O evento original vai para `ADIADO`, com **motivo** e a data em que foi adiado.
2. Um evento novo é criado, apontando o anterior.
3. A timeline registra os dois fatos.
4. A ficha do caso mostra "audiência adiada 3×" — porque isso é informação sobre o processo, não
   ruído.

O mesmo vale para cancelamento (sem evento novo) e para não comparecimento (com consequência
processual).

### Visões

**Semana** (padrão, com hoje destacado) · **Mês** · **Lista de prazos** ordenada por vencimento.
Filtros: responsável (padrão: eu), tipo, obra. Sem visão "todos os eventos de todos" como padrão.

---

## 6. Negociação e acordo

### Onde uma termina e o outro começa

> **A negociação termina no aceite. O acordo começa na formalização.**

Entre um e outro há um intervalo que importa: proposta aceita verbalmente não é obrigação
exigível. Por isso:

| Momento | O que existe | Situação financeira |
|---|---|---|
| Propostas indo e vindo | Negociação `ABERTA` | `EM_DISCUSSAO` |
| Proposta aceita | Negociação `ENCERRADA_COM_ACORDO` + acordo criado como `ACEITO` | `EM_DISCUSSAO` |
| Acordo assinado ou homologado | Acordo `FORMALIZADO` → **parcelas geradas** | `A_PAGAR` |
| Todas as parcelas pagas | Acordo `CUMPRIDO` | `QUITADO` |

**Parcela só nasce na formalização.** Antes disso não há o que cobrar nem o que provisionar como
obrigação — e nada vai para o Contas a Pagar.

### O que se registra na negociação

Canal (direto, conciliação, câmara arbitral, mediação, advogados) · responsável · data de abertura
· última interação · **prazo para resposta** · status.

### O que se registra em cada proposta

Quem propôs (empresa, reclamante, juízo, câmara) · valor · número de parcelas · condições ·
data · prazo de validade · resultado (aceita, recusada, expirada, substituída) · **motivo da
recusa** · **percentual de desconto**.

Sobre o desconto: calculado sobre o **valor de risco** (nossa estimativa), com o percentual sobre
o valor da causa exibido apenas como contexto. Descontar sobre um pedido inflado produz "85% de
desconto" em todo acordo — um número que parece ótimo e não significa nada.

---

## 7. O dinheiro

> **Princípio:** o Jurídico é dono da **informação jurídica** sobre valores. O Financeiro é dono
> do **movimento de caixa**. Nenhum valor existe nos dois lugares com significados diferentes.

### Os onze valores

| Valor | Natureza | Onde vive | Gera lançamento no CAP? |
|---|---|---|---|
| **Valor da causa** | O que o reclamante pede | Jurídico | Não — não é obrigação nossa |
| **Valor de risco** | Nossa estimativa de perda | Jurídico | Não — vira provisão contábil, não título |
| **Valor negociado** | Proposta na mesa | Jurídico | Não — proposta não é obrigação |
| **Valor do acordo** | Total formalizado | Jurídico | Não diretamente — quem gera título é a parcela |
| **Parcela** | Obrigação com vencimento | Jurídico (origem) | **Sim** — um título por parcela, no vencimento |
| **Pagamento** | Baixa efetiva | Financeiro (origem) | **Sim** — é a baixa do título |
| **Condenação líquida** | Obrigação por sentença | Jurídico | **Sim** — mesmo tratamento da parcela |
| **Custas, honorários, perícia** | Despesa do processo | Jurídico (registro) | **Sim** — título comum |
| **Depósito judicial ou recursal** | Saída de caixa **recuperável** | Ambos | **Sim**, com natureza que marca a recuperabilidade |
| **Bloqueio** | Indisponibilidade, não despesa | Jurídico | **Não** — ver abaixo |
| **Levantamento / liberação** | Retorno de caixa | Financeiro | **Não é título** — é entrada |

### A regra que evita a segunda contabilidade

> **O Contas a Pagar recebe apenas o que a empresa vai pagar por vontade própria, na data em que
> vai pagar. Constrição judicial e estimativa ficam no Jurídico.**

Consequências práticas:

- **Bloqueio nunca vira título.** O dinheiro foi retirado pelo juízo; não há o que pagar. Ele
  aparece como indisponibilidade no Jurídico e como movimento na conciliação bancária.
- **Bloqueio convertido em pagamento** baixa a obrigação no Jurídico **sem** gerar título — se
  gerasse, a empresa pagaria duas vezes o mesmo valor.
- **Provisão não é título.** Ela alimenta a contabilidade por competência, não o contas a pagar.
- **Depósito é título** (a empresa emite guia e paga), mas fica marcado como recuperável, para
  não inflar o custo do contencioso.

### Custo real do contencioso

`pagamentos de acordo e condenação + custas + honorários + perícia + depósitos perdidos +
bloqueios convertidos` — **menos** o que voltou. Depósito ainda não levantado é **capital
retido**, não custo.

---

## 8. Bloqueios

### A pergunta que a tela responde

*"Quanto dinheiro da empresa ou dos sócios está indisponível agora, e por causa de quê?"*

O número principal é a **soma dos bloqueios ativos**, quebrada por tipo de titular.

### Tipos de titular

| Titular | Tratamento |
|---|---|
| Conta da empresa | Normal |
| **Conta salário** | **Crítico e impenhorável** — indica erro a impugnar imediatamente |
| **Conta pessoal de sócio** | **Crítico** — escalonamento à diretoria no mesmo dia |
| Conta de terceiro | Crítico — atinge quem não é parte |
| Outro patrimônio | Veículo, imóvel, recebível — com impacto operacional (veículo penhorado é veículo que a obra não usa) |

### Campos

Caso e processo · titular (tipo + quem) · instituição · valor bloqueado · data · motivo ·
status · data de liberação · **valor liberado** · **valor convertido em pagamento** · documento.

### Como os três números se fecham

```
valor bloqueado = valor liberado (voltou) + valor convertido (perdeu) + saldo ativo (indisponível)
```

É essa identidade que permite responder as três perguntas com um dado só: quanto está retido,
quanto perdemos e quanto recuperamos.

---

## 9. Radar de risco

### Como funciona sem casos fantasmas

O radar **não cria registros**. É uma visão calculada sobre os desligados do RH, cruzada com o
acervo jurídico:

```
employees (desligados)  ──▶  cruza com casos existentes  ──▶  lista ordenada por risco
   dono: RH                    dono: Jurídico                  nenhum registro novo
```

Um caso só nasce quando existe **fato concreto**: citação, notificação extrajudicial, contato de
advogado ou decisão do jurídico de acompanhar. Nesse momento alguém clica em "abrir caso" e o
contexto do desligamento é congelado.

### O que o radar mostra

| Visão | Responde |
|---|---|
| **Safra do mês** | Quem desligamos neste mês e qual o perfil de risco |
| **Prescrição próxima** | Quem está a menos de 90 dias do prazo — depois disso, o risco acaba |
| **Reincidência** | Pessoas que já processaram a empresa antes |
| **Por obra/projeto** | Quais contratos geram mais ações — índice, não número absoluto |
| **Por gestor** | Mesma leitura, por responsável na época |
| **Por cliente** | Concentração por tomador |
| **Pedidos recorrentes** | O que mais nos cobram — e onde |

### O índice, não o número

Uma obra com 500 pessoas e 20 ações não é pior que uma com 30 pessoas e 8 ações. O radar mostra
sempre **ações por 100 desligados**, com o número absoluto ao lado. Sem isso, a leitura aponta
sempre para a maior obra.

### O que ele não faz

Não prevê quem vai processar. Ordena por fatores observáveis e mostra quais são. Com 148 casos
não há base estatística para mais que isso — e um número sem explicação seria pior que nenhum.

---

## 10. Timeline

### Uma linha do tempo por caso, com fatos de várias fontes

```
15/01  ⬤ Desligamento                       (RH · automático)
20/01  ⬤ Notificação extrajudicial recebida (manual)
03/02  ⬤ Processo distribuído               (manual)
15/03  ⬤ Audiência designada para 20/03     (agenda)
20/03  ⬤ Audiência realizada — sem acordo   (agenda · resultado)
25/03  ⬤ Proposta: R$ 28.000 em 4×          (negociação)
28/03  ⬤ Contraproposta recusada            (negociação · motivo)
10/04  ⬤ Acordo aceito — R$ 41.500          (acordo)
15/04  ⬤ Parcela 1/6 paga                   (financeiro)
```

### A distinção que você pediu

| Natureza | Está na timeline? | Onde vive |
|---|---|---|
| **Fato histórico** | Sim | É a própria timeline |
| **Movimentação judicial** | Sim, marcada como tal | Fato com origem |
| **Documento** | Sim, como "documento anexado" | Arquivo na aba Documentos |
| **Pagamento** | Sim | Lançamento financeiro |
| **Evento futuro** | **Não** | Painel "próximos" ao lado da timeline |
| **Tarefa aberta** | **Não** | Lista de pendências do caso |

> **Regra:** a timeline não mostra futuro. O futuro está na agenda do caso, ao lado. Quando um
> evento acontece, ele *vira* fato e entra na timeline.

Isso resolve a confusão que derruba esse tipo de tela: uma lista que mistura "vai acontecer" com
"aconteceu" não serve para nenhuma das duas leituras.

### Legibilidade em caso longo

Filtro por natureza e visão **"só marcos"** como padrão acima de 50 fatos — distribuição,
sentença, acordo, pagamento, encerramento. O detalhe fica a um clique.

---

## 11. Responsabilidade

| Papel | Quantos | Obrigatório | Responde por |
|---|---|---|---|
| **Responsável jurídico** | Um | **Sim, em caso ativo** | O caso inteiro: prazos, estratégia, atualização |
| **Responsável operacional** | Um | Não | A informação da obra: documentos, testemunhas, contexto |
| **Escritório** | Um por período | Não | A atuação processual quando terceirizada |
| **Advogado externo** | Um ou mais | Não | Atos processuais; vinculado ao escritório |
| **Preposto** | **Por evento** | Sim, na audiência | Comparecer e representar naquela audiência |
| **Gestor interno** | Um | Não | Apenas informativo, herdado do contexto do desligamento |

Três regras:

1. **Caso ativo sem responsável jurídico é alerta** no bloco "precisa de dono".
2. **Preposto é por audiência, não por caso** — muda conforme a comarca e a data. Amarrá-lo ao
   caso obrigaria a corrigir o cadastro a cada audiência.
3. **Papéis são datados.** Trocar de escritório não apaga quem respondia antes; o desempenho por
   escritório se mede por período.

---

## 12. Teste de 5.000 processos, tela a tela

| Tela | Gargalo em 2031 | Decisão de projeto |
|---|---|---|
| **Busca** | Vira a principal forma de navegação | Busca única no topo, tolerante a pontuação e a fragmento de número; resultado tipado (caso, pessoa, processo). **Nunca depender de listagem** |
| **Casos** | 5.000 linhas | Paginação no servidor, ordenação por colunas indexadas, filtros salvos por usuário, visão padrão por papel |
| **Filtros** | Excesso de filtros vira formulário | Máximo de seis filtros visíveis (estado, responsável, empresa, obra, etapa, período); o resto atrás de "mais filtros" |
| **Central** | Centenas de alertas | Escopo pessoal, quatro famílias críticas, agregação por categoria, volume de regra monitorado |
| **Agenda** | Milhares de eventos | Padrão: meus eventos, semana atual. Visão de equipe é escolha explícita |
| **Negociações** | Dezenas abertas | Ordenação por dias sem interação; a lista é naturalmente pequena |
| **Financeiro** | Centenas de parcelas por mês | Lista transacional com baixa em lote e vínculo ao título; nunca caso a caso |
| **Bloqueios** | Dezenas ativos | Lista pequena por natureza; o histórico fica em relatório |
| **Timeline** | 300 fatos por caso | "Só marcos" como padrão, filtro por natureza |
| **Relatórios** | Extrações pesadas | Assíncronas, com aviso quando prontas; fora do menu principal |
| **Radar** | 8.000 desligados | Trabalho por safra e por proximidade de prescrição; nunca o acervo inteiro |

### Riscos de excesso — e o teto que proponho

| Risco | Teto |
|---|---|
| Menus demais | **Sete**, mais Administração |
| Filtros demais | **Seis** visíveis por lista |
| Alertas demais | **Quatro** famílias críticas; regra que dispara em >10% do acervo é sinalizada |
| Estados demais | **Vinte** valores em cinco eixos |
| Informação duplicada | Desligamento é do RH; caixa é do Financeiro; o Jurídico referencia, não copia — exceto o contexto congelado, que é deliberado e documentado |

---

## 13. Fases

### Fase 0 — Fundamento

| Item | Por que aqui |
|---|---|
| Caso como raiz + vínculo com processos | Tudo o mais pendura nele; mudar depois é refazer |
| Os cinco eixos de estado | Definem toda leitura e todo filtro do módulo |
| Timeline com origem do fato | É o histórico oficial; sem ela, nada é rastreável |
| Papéis e responsável obrigatório | Sem dono, nenhum alerta funciona |
| Migração e triagem dos 148 | O acervo precisa entrar no modelo novo antes de operar |
| Busca | Sem ela, nada é encontrado nem em 2026 |

### Fase 1 — Operação (o MVP de uso diário)

| Item | Por que aqui |
|---|---|
| Central de Trabalho | É a razão de existir do módulo no dia a dia |
| Agenda com eventos e adiamento | Audiência e prazo são o trabalho diário |
| Prazos e providências | O que o analista faz o dia inteiro |
| Registro de fatos e documentos | Alimenta a timeline — sem isso o módulo morre em três meses |
| Revisão semanal | Onde vão as regras de horizonte semanal |
| Listas com filtros salvos | Uso diário desde o primeiro dia |

**Ao fim da Fase 1 o jurídico já pode abandonar a planilha.** É esse o critério do MVP.

### Fase 2 — Gestão

| Item | Por que aqui |
|---|---|
| Negociações e propostas | Depende da operação rodando para ter o que negociar |
| Acordos, parcelas e integração com o CAP | Envolve dinheiro: exige a base estável |
| Financeiro do contencioso | Idem |
| Bloqueios e depósitos | Depende dos lançamentos financeiros |
| Painel executivo | Precisa de dado acumulado para significar algo |
| Provisão por competência | Começa aqui porque a série histórica não se reconstrói |

### Fase 3 — Inteligência

| Item | Por que aqui |
|---|---|
| Radar de risco completo | Depende do vínculo com RH e de histórico |
| Pedidos e reincidência | Só tem sentido com pedidos registrados por um período |
| Score de risco | Exige base para calibrar os fatores |
| Concentração por obra, gestor e cliente | Depende de contexto congelado acumulado |
| Devolutiva trimestral para a operação | O ciclo se fecha aqui |
| Captura de publicações, notificações, IA | Automação sobre operação madura |

---

## 14. Decisões que precisam ser tomadas pelo negócio

Nenhuma é técnica. Cada uma muda o comportamento do sistema.

**1. Prazo prescricional.**
Opções: (a) dois anos do desligamento, regra geral trabalhista; (b) dois anos com alerta a partir
de 90 dias; (c) prazo por tipo de caso (trabalhista 2 anos, cível 3, tributário 5).
→ **Recomendo (c)**, com dois anos como padrão do trabalhista e alerta em 90 dias.

**2. Quando um caso nasce.**
Opções: (a) todo desligamento vira caso; (b) só com fato concreto — citação, notificação, contato.
→ **Recomendo (b).** É a decisão que evita 8.000 registros vazios; o radar cobre o resto.

**3. Quem pode encerrar um caso.**
Opções: (a) qualquer analista; (b) só o gerente jurídico; (c) analista propõe, gerente confirma.
→ **Recomendo (b)** — encerramento é irreversível na prática e some da operação.

**4. Quando um acordo é considerado quitado.**
Opções: (a) na última parcela paga; (b) na última parcela **mais** a comprovação da quitação nos
autos; (c) na homologação da quitação pelo juízo.
→ **Recomendo (b)**: o dinheiro saiu, mas o processo só arquiva com a comprovação — e é
exatamente a fila "quitado mas não arquivado" que queremos enxergar.

**5. Quais bloqueios são críticos.**
Opções: (a) todos; (b) acima de um valor; (c) por tipo de titular.
→ **Recomendo (c)**: conta salário, conta pessoal de sócio e conta de terceiro são sempre
críticos, independentemente do valor; conta da empresa é crítica acima de um valor que você
define.

**6. Quem pode alterar valores.**
Opções: (a) quem edita o caso; (b) valores jurídicos pelo jurídico, valores pagos só pelo
financeiro; (c) tudo pelo gerente.
→ **Recomendo (b)**: o Jurídico define risco e acordo; a baixa de pagamento é do Financeiro.
Ninguém "corrige" no Jurídico um valor que o caixa já registrou.

**7. Quais eventos geram alerta crítico.**
Opções: (a) tudo que vence; (b) só as quatro famílias (audiência de hoje, prazo vencendo,
bloqueio novo, parcela de hoje).
→ **Recomendo (b)** — é o que mantém a Central esvaziável.

**8. Quais valores entram no Financeiro.**
Opções: (a) tudo que tem valor; (b) só o que a empresa paga por vontade própria: parcela,
condenação, custas, honorários, perícia e depósito.
→ **Recomendo (b).** Bloqueio e provisão ficam fora do contas a pagar.

**9. Política de arquivamento e retenção.**
Opções: (a) manter tudo para sempre; (b) manter completo por N anos após o arquivamento e depois
anonimizar dados pessoais, preservando valores e estatísticas.
→ **Recomendo (b)** com N = 5 anos após o arquivamento, alinhado ao prazo de guarda trabalhista.

**10. SLA de negociação.**
Opções: (a) sem prazo; (b) alerta após N dias sem interação.
→ **Recomendo (b)** com **20 dias**, ajustável. Proposta parada é dinheiro que fica mais caro.

**11. Alçada de acordo.**
Quem aprova um acordo, e a partir de que valor? Hoje isso não existe no sistema.
→ **Recomendo** duas faixas: até um valor o gerente jurídico decide; acima, exige aprovação da
diretoria registrada no caso. Você define o corte.

**12. Percentuais de provisão por risco.**
Provável, possível e remota — quanto se provisiona em cada uma?
→ **Recomendo** 100% / 50% / 0% como ponto de partida, revisado com a contabilidade. **Esta é a
única decisão que não pode ser adiada**: a série histórica só existe se começar a ser gravada.

**13. Quem é o "Responsável RH" do caso.**
→ **Recomendo** um usuário do SGC por obra ou por região, para que o alerta chegue a alguém de
fato.

**14. Data do corte da fonte oficial.**
A partir de quando a planilha deixa de alimentar o módulo, e quem pode reabrir a importação.
→ **Recomendo** o corte no dia da entrada em produção da Fase 1, com reabertura restrita ao
administrador do sistema e registrada em auditoria.

---

## 15. O que este documento deliberadamente não tem

Para você conferir se algo importante ficou de fora — ou se a simplicidade foi mantida de
propósito:

- **Sem quadro kanban** — a etapa existe como campo; a tela não.
- **Sem menu de Processos, Acordos, Documentos, Partes ou Bloqueios** — todos são abas ou filtros.
- **Sem previsão estatística** — o score ordena e explica; não adivinha.
- **Sem notificação por e-mail na Fase 1** — o sistema não tem agendador nem serviço de e-mail; as
  regras já nascem com destinatário para que ligar isso depois seja configuração.
- **Sem app móvel** — a Central e a Agenda respondem bem em tela pequena.
- **Sem personalização de layout** — padronização é o que permite uma pessoa ajudar a outra.
- **Sem workflow configurável** — o fluxo é o dos eixos; regras de transição em código, revisáveis.
