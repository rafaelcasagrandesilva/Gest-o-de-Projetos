# Etapa 0 — Endividamento com motor de saldo (juros / correção mês a mês)

**Objetivo:** que uma dívida deixe de ser um **valor parado** e passe a ser um **saldo que
evolui sozinho**, mês a mês, com juros ou correção, mudança de taxa a partir de uma data,
aportes e pagamentos — exatamente como a planilha que o financeiro já usa hoje fora do
sistema. E que, com isso, o SGC consiga responder "quanto dessa dívida é principal e quanto
já virou encargo".

**Princípio inegociável:** nenhuma dívida já cadastrada muda de valor sozinha. O motor novo
nasce desligado em tudo o que existe; ligar é ato explícito, dívida por dívida.

> Status: **implementado e testável no ambiente local.** Núcleo puro + migration aditiva 0127
> (vigências de taxa e eventos) + endpoints de razão/taxa/evento + a nova tela padrão do
> Endividamento. Não deployado. Falta: cards consolidados (§9) e a conferência visual com o
> usuário.

---

## 1. O caso real que motivou

Planilha de controle de um acordo com fornecedor, conferida linha a linha (28 competências,
04/2024 a 07/2026, divergência total de **1 centavo** de arredondamento). A mecânica dela:

```
saldo final = saldo inicial + aporte + juros do mês − pagamento do mês
juros = saldo inicial × taxa do mês        (antes do aporte entrar)
```

O que essa planilha tem que o SGC hoje **não sabe representar**:

| Fato | Hoje no SGC |
|---|---|
| Saldo cresce sozinho quando ninguém paga | ❌ o valor da dívida é fixo |
| Taxa muda de 3% para 1,5% a.m. a partir de 01/01/2026 | ❌ não existe taxa |
| Juros não pagos são capitalizados (viram saldo) | ❌ não existe |
| "Aporte": dívida NOVA no meio do caminho (R$ 28.000 e R$ 60.000) | ❌ só dá para editar o valor total, perdendo o histórico |
| Plano de 8 parcelas que parou na 5ª, e um pagamento avulso de R$ 100.000 depois | ⚠️ o cronograma exige que Σ parcelas feche o total |

Números que o motor tem que reproduzir (são o **critério de aceite** da Fase 1):

| | |
|---|---|
| Principal em 01/04/2024 | R$ 100.000,00 |
| Aportes (dívida nova) | R$ 88.000,00 |
| Pago ao fornecedor | R$ 173.750,00 |
| Encargos cobrados no período | R$ 56.186,95 |
| — destes, efetivamente pagos | R$ 15.957,29 |
| — destes, capitalizados (viraram saldo) | R$ 40.229,66 |
| Amortização real de principal | R$ 157.792,71 |
| Saldo em 01/07/2026 (última linha da planilha) | R$ 70.436,94 |
| Saldo projetado em 01/09/2026 | R$ 72.565,90 |

---

## 2. A mudança conceitual (o coração do desenho)

Hoje o Endividamento tem **um "modo"** que mistura duas perguntas independentes. O modelo novo
as separa — e é essa separação que faz um único formato atender a todos os cenários:

**Eixo A — como o SALDO evolui** (motor):
- `FROZEN` — saldo só muda com pagamento/evento. É o comportamento atual, e o que uma taxa de 0% produz.
- `ACCRUAL` — saldo corrige mês a mês pela taxa vigente.

**Eixo B — como se PLANEJA pagar** (agenda):
- `NONE` — sem plano; paga-se quando dá (é o caso da planilha depois que o acordo original parou).
- `SCHEDULE` — cronograma de parcelas (o Cronograma Financeiro que já existe).
- `MONTHLY` — parcela fixa mensal.

Todo cenário citado vira uma célula:

| | Sem plano | Cronograma | Parcela fixa |
|---|---|---|---|
| **Congelado (0%)** | dívida atual do SGC | Cronograma Financeiro (Modo 2 atual) | renegociação em parcelas iguais |
| **Com juros** | **o caso da planilha** | cronograma + juros sobre o saldo | parcela fixa + juros |

**Por que separar importa:** hoje o cronograma carrega a invariante `Σ parcelas = total negociado`.
Com juros essa invariante é **impossível** — o total não é conhecido de antemão, ele é
*resultado* da evolução do saldo. Separando os eixos, o cronograma volta a ser o que sempre
deveria ter sido: um **plano de pagamento**, não a definição do tamanho da dívida. O saldo passa
a ser a única fonte da verdade do tamanho; o plano é o que gera título no Contas a Pagar.

Essa separação também explica a planilha: o plano era 8 × R$ 12.500, a execução parou na 5ª, e
o saldo seguiu vivo. **Plano e execução divergem na vida real** — o modelo tem que suportar isso
sem que nada fique inconsistente.

---

## 2.1 O ciclo de vida real de uma dívida (e por que ele não pede nada novo)

Refinamento trazido pelo financeiro: **a capitalização é a exceção, não a regra.** Quando a
empresa tem recurso para quitar, em quase 100% das vezes é feito um **acordo com parcelas
fixas** — que é justamente o Cronograma Financeiro que já existe. O caso da planilha foi
exceção, num momento de necessidade grave.

Isso define o ciclo de vida que o modelo precisa suportar:

```
   dívida nasce            acordo fechado              acordo cumprido
        │                        │                            │
        ▼                        ▼                            ▼
   ┌─────────────┐        ┌──────────────┐            ┌──────────────┐
   │  CORRENDO   │───────▶│  CONGELADA   │───────────▶│   QUITADA    │
   │ encargo a % │        │ 0% + parcelas│            │  saldo zero  │
   └─────────────┘        └──────────────┘            └──────────────┘
        ▲                        │
        └────────────────────────┘
           acordo descumprido
        (foi o que houve na planilha)
```

**O ponto importante: nenhuma dessas transições precisa de máquina nova.** Elas são expressas
com o que o modelo já tem:

| Transição | Como se representa |
|---|---|
| Dívida começa a correr | vigência de taxa a partir da competência de origem |
| **Acordo fechado** | **vigência de taxa 0% a partir do mês do acordo** — a dívida congela onde estava |
| Desconto negociado no acordo | evento `ABATIMENTO` no mês do acordo |
| Parcelas do acordo | cronograma (`SCHEDULE`), que já existe e já gera os títulos do CAP |
| Acordo descumprido | nova vigência devolvendo a taxa, a partir do mês da quebra |

Ou seja: **"acordo" é um congelamento com cronograma**, e "quebra de acordo" é o
descongelamento. Os dois eixos do §2 não são fixos na vida da dívida — eles mudam ao longo
dela, e as vigências de taxa são exatamente o mecanismo que registra quando mudaram, sem apagar
o histórico.

Conferido no simulador (`scripts/simular_divida.py`): dívida de R$ 100.000 correndo a 0,5% a.m.
por 13 meses chega a R$ 106.698,63; acordo em 02/2026 congela nesse valor; 10 parcelas de
R$ 10.669,86 zeram o saldo em 11/2026, sem nenhum encargo depois do acordo.

**Consequência de produto:** o modo "correndo a juros" é o **estado de espera** de uma dívida —
o que ela faz enquanto ninguém negocia. O acordo com parcelas fixas continua sendo o desfecho
normal. A tela nova precisa deixar isso óbvio: o botão que importa, numa dívida correndo, é
"fechar acordo" — que congela a taxa e abre o cronograma numa ação só.

---

## 3. Decisões já aprovadas

| # | Decisão | Consequência |
|---|---|---|
| D1 | **Trocar só a tela PADRÃO** (a grade de caixas) pelo formato da planilha | O Cronograma Financeiro não é tocado; os Custos Fixos seguem na grade de sempre |
| D2 | A taxa padrão de 0,5% a.m. vale **só para dívidas novas** | Nenhum valor muda no dia do deploy; dívida existente fica em 0% até alguém ligar |
| D3 | Juros/correção **não geram título** no Contas a Pagar | Título só nasce de plano de pagamento ou de valor lançado no mês |

### Sobre D1 — o escopo que sobrou (e por que ele é pequeno)

O escopo foi reduzido pelo próprio usuário depois de rever o módulo em uso: **o Cronograma
Financeiro funciona e não muda.** Fixar as parcelas e mandá-las para o Contas a Pagar é
exatamente o que ele precisa, e é o desfecho normal de toda dívida (§2.1).

O que muda é só a **tela padrão** — a que aparece quando a dívida NÃO tem cronograma: hoje uma
grade de 12 caixas soltas, que não sabe dizer se a dívida cresceu. Ela dá lugar ao razão.

Com isso a reescrita cabe em um componente novo (`DebtLedgerPanel.tsx`) e uma troca condicional
de uma tela só:

1. **Cronograma Financeiro:** intocado;
2. **Custos Fixos:** continua na grade de caixas (não tem saldo nem encargo) — a troca é
   condicionada a `tipo === "endividamento"`;
3. **A caixa de pagamento é a mesma de antes** — mesmo estado, mesmo "Salvar agora", mesmo
   caminho para o CAP. Ela só passa a ser lida DENTRO da linha do mês, cercada do saldo que
   movimenta. Nada mudou em como o pagamento é gravado ou sincronizado;
4. **Contrato do Contas a Pagar:** intocado.

A separação do Endividamento do componente de 3.239 linhas dos Custos Fixos deixa de ser
pré-requisito e vira dívida técnica a pagar quando incomodar.

---

## 4. Modelo de dados (100% aditivo)

Nada é removido nem alterado. Três acréscimos:

### 4.1 `company_financial_items` — duas colunas

```
balance_mode      VARCHAR(16)  NOT NULL DEFAULT 'FROZEN'   -- FROZEN | ACCRUAL
payment_plan_mode VARCHAR(16)  NOT NULL DEFAULT 'NONE'     -- NONE | SCHEDULE | MONTHLY
```

Backfill dos registros atuais: `FROZEN` para todos; `SCHEDULE` onde `uses_custom_schedule = true`,
`MONTHLY` onde há renegociação em parcelas, `NONE` no resto. **O default garante que o deploy é
funcionalmente neutro** (D2).

**Reuso deliberado:** o principal e a data de origem **não ganham colunas novas** —
`valor_referencia` é o principal e `start_date` é a data de origem. Já existem e já significam
isso.

### 4.2 `company_financial_rates` — vigências de taxa (tabela nova)

```
id, item_id FK, valid_from DATE (competência), monthly_rate NUMERIC(9,6),
note VARCHAR(255) NULL, created_by, created_at
UNIQUE (item_id, valid_from)
```

A taxa de um mês é a da **maior `valid_from` ≤ mês**. O caso da planilha vira duas linhas:
`(01/04/2024, 0.03)` e `(01/01/2026, 0.015)`. Uma dívida congelada é uma linha `0.000000` — ou
nenhuma linha, que dá no mesmo.

`system_settings` ganha `debt_default_monthly_rate NUMERIC(9,6) DEFAULT 0.005` (0,5% a.m. =
6,17% a.a. compostos), usado **só ao criar uma dívida nova**.

### 4.3 `company_financial_events` — eventos que mexem no saldo (tabela nova)

```
id, item_id FK, competencia DATE, kind VARCHAR(24), amount NUMERIC(14,2),
description VARCHAR(255) NULL, created_by, created_at
```

`kind`: `APORTE` (+, dívida nova), `ABATIMENTO` (−, perdão/desconto negociado),
`ENCARGO_MANUAL` (+, multa/honorário lançado à mão). Genérica de propósito — cobre o que a
planilha chama de "aporte" sem hardcode de fornecedor nem de motivo.

**Pagamento não é evento aqui.** Pagamento continua vindo de onde já vem: dos títulos do CAP
(`amount_paid`, via `entry_id`). Essa é a regra que o módulo já segue e que impede o saldo de
divergir do caixa.

---

## 5. O núcleo puro: `app/services/debt_accrual.py`

Mesmo padrão de `financial_schedule.py`: **sem ORM, sem banco, sem domínio** — funções puras
sobre estruturas simples, testáveis isoladamente e reutilizáveis por qualquer obrigação com
saldo (parcelamento tributário, financiamento, acordo judicial).

Entrada: principal + data de origem, vigências de taxa, eventos, pagamentos reais por mês.
Saída: uma linha por competência, com as mesmas colunas da planilha.

```python
@dataclass(frozen=True)
class LedgerLine:
    competencia: date
    saldo_inicial: Decimal
    aporte: Decimal
    taxa: Decimal          # taxa vigente no mês
    encargo: Decimal       # saldo_inicial × taxa
    pagamento: Decimal     # pagamento REAL do mês (CAP)
    juros_pagos: Decimal   # parte do pagamento que quitou encargo
    amortizacao: Decimal   # parte do pagamento que abateu principal
    saldo_final: Decimal
    encargo_acumulado: Decimal
```

### Regras de cálculo (todas conferidas contra a planilha)

1. **Encargo do mês = saldo inicial × taxa vigente.** Incide sobre o saldo de abertura, **antes**
   do aporte do mês — o aporte não rende no mês em que entra.
2. **Saldo final = saldo inicial + aporte + encargo − pagamento.**
3. **Encargo não pago é capitalizado**: fica no saldo e rende no mês seguinte. É o que fez a
   dívida da planilha subir de R$ 37.500 para R$ 42.206 sem nenhuma compra nova.
4. **Alocação do pagamento: encargo primeiro, principal depois** (proposta — ver §10). É o que
   permite dizer que dos R$ 100.000 pagos em nov/2025, R$ 4.707,29 foram encargo e
   R$ 95.292,71 abateram principal.
5. **Taxa 0% congela a dívida** — o motor roda, gera as linhas, e o saldo simplesmente não anda.
   `FROZEN` e `ACCRUAL @ 0%` produzem números idênticos, por construção.
6. **Arredondamento a cada mês**, 2 casas, `ROUND_HALF_UP` — a mesma convenção do resto do
   sistema (`_money`).

### Derivado, não armazenado

O razão **não é gravado**: é recalculado a partir de (principal, vigências, eventos, pagamentos
reais). Sem tabela de saldo, não há saldo defasado, não há reconciliação, e corrigir uma taxa
lançada errada conserta o histórico inteiro sozinho.

O que **é** imutável já é imutável hoje: o pagamento real, que vive no CAP e não é recalculado
por nada.

---

## 6. A tela

**Formato: o mesmo do Cronograma Financeiro** — no cartão fica só a leitura; a edição vive num
modal. Foi correção de rumo: a primeira versão trazia a planilha inteira inline no cartão e
ficou grande e confusa demais para algo que se expande no meio de uma lista.

**No cartão** (compacto, 4 números + uma frase): Principal · Juros acumulados · Pago · Saldo
hoje, mais a linha que diz em que regime a dívida está ("Correndo no padrão do SGC (0,5% ao
mês) — nenhuma taxa definida para esta dívida") e o botão **Gerenciar evolução**.

**No modal**, a planilha do financeiro, coluna por coluna:

```
MÊS · SALDO INICIAL · APORTE · TAXA % · JUROS · PAGAMENTO · SALDO FINAL
```

As três colunas digitáveis — **Aporte, Taxa e Pagamento** — são exatamente as três da planilha;
o resto é calculado. Acima, um bloco de **Parâmetros** (mês de início, valor de origem,
horizonte de projeção) no lugar onde o cronograma põe o gerador por faixas; abaixo, o resumo de
fechamento no lugar onde o cronograma põe o painel verde.

**A coluna Taxa é o coração da tela:**

| O que se digita | O que acontece |
|---|---|
| **em branco** | herda o mês anterior; se ninguém definiu nada em mês nenhum, vale o padrão do SGC |
| **um número** | cria a vigência NAQUELE mês e vale dali para frente |
| **zero** | congela a dívida a partir dali (é como se registra um acordo fechado) |

Cada tecla dispara um `preview` no backend, que devolve o razão recalculado pelo MESMO motor que
grava — o que se vê digitando é exatamente o que fica salvo. Salvar grava parâmetros, vigências,
aportes e pagamentos numa transação só, como o "Salvar cronograma".

### Taxa não definida herda o padrão do SGC

Regra de produto que **substitui a decisão D2 original**: uma dívida que ninguém configurou
mostra a evolução com correção, em vez de ficar parada no tempo — *"se eu não mexer em nada,
quero saber a evolução dessa dívida sempre calculando o juros mês a mês"*.

O padrão só entra quando **não há vigência nenhuma**. A partir do momento em que alguém define
uma, ela manda. E congelar continua sendo possível — de forma explícita, com uma vigência de 0%.

**Consequência a comunicar:** o "Saldo hoje" da evolução passa a divergir do "Restante" do
cabeçalho do item, que é nominal. É proposital (um é corrigido, o outro é contábil), e nada
disso toca o Contas a Pagar — §7 continua valendo.

---

## 7. Contas a Pagar (D3)

**Regra:** encargo movimenta saldo, **não cria título**. Título nasce só de:
- parcela do cronograma (`SCHEDULE`) — como já é hoje, por `entry_id`;
- parcela fixa mensal (`MONTHLY`) com item obrigatório — como já é hoje;
- valor lançado à mão na competência — como já é hoje.

Nada muda no `PayableSnapshot`, no `entry_id`, na reconciliação nem na geração automática. O
motor de saldo **lê** o pagamento realizado e nunca escreve no CAP.

Efeito colateral bom: a previsão de caixa não enche de títulos de juros que ninguém vai pagar —
que é exatamente o que acontece na planilha entre nov/2025 e hoje.

---

## 8. Compatibilidade com o que já existe

| Situação atual | Depois |
|---|---|
| Dívida com valor fixo + caixas mensais | `FROZEN` + `NONE`. Números **idênticos** |
| Dívida com Cronograma Financeiro (Modo 2) | `FROZEN` + `SCHEDULE`. Cronograma e CAP intocados |
| Renegociação em parcelas iguais | `FROZEN` + `MONTHLY`. Intocado |
| Custos Fixos | Não usa nada disto. Tela e código atuais preservados |

**Prova de equivalência exigida na Fase 2:** para toda dívida existente, o razão calculado com
taxa 0% tem que devolver, centavo a centavo, o saldo e o pago que a tela mostra hoje. É um
script de conferência que roda contra a cópia da produção antes de qualquer deploy — o mesmo
método usado na renumeração do SGC.

---

## 9. Indicadores que isso destrava

Com o razão, viram uma conta e não uma estimativa:

- **Principal × encargo** por dívida e no consolidado — quanto da dívida é dívida e quanto é juro;
- **Encargo pago × capitalizado** — quanto de juro virou caixa e quanto virou mais dívida;
- **Custo efetivo da dívida** (taxa média ponderada pelo saldo × prazo) — comparável entre credores,
  e comparável com o custo das antecipações, que já usa o mesmo conceito;
- **Projeção de saldo** — onde a dívida estará em 6/12/24 meses se ninguém pagar nada;
- **Quanto custa não pagar** — encargo que vai ser gerado no horizonte, por credor.

---

## 10. Decisões pendentes

1. **Alocação do pagamento** — encargo primeiro e principal depois (proposto, §5.4), ou
   proporcional? Muda só a leitura dos cards, nunca o saldo.
2. ~~**Capitalização**~~ — **RESOLVIDO.** Capitaliza sempre (encargo não pago vira saldo),
   como a planilha. O financeiro confirmou que esse regime só vale enquanto a dívida está
   *correndo*: fechado o acordo, a dívida congela (§2.1) e a capitalização deixa de existir. Como
   o caminho normal é o acordo, a capitalização fica restrita ao período de espera.
3. **Horizonte de projeção** para dívida sem plano de pagamento (sugestão: 24 meses, configurável).
4. **Taxa por índice** (IPCA, CDI, Selic) em vez de percentual fixo — fora do escopo desta etapa,
   mas o modelo de vigências já comporta: bastaria a vigência apontar para um índice.
5. **Dia da competência** — o motor trabalha por mês cheio (competência), como a planilha. Juros
   pro-rata die por data exata de pagamento fica fora do escopo.

---

## 11. Riscos

| # | Risco | Mitigação |
|---|---|---|
| R1 | Reescrita da tela quebrar o Endividamento em produção | Tela nova convive com a atual atrás de um flag por usuário/perfil; a antiga só sai depois do aceite |
| R2 | Custos Fixos ser afetado pela reescrita | Custos Fixos permanece 100% na tela atual; a separação é o **primeiro** passo da implementação |
| R3 | Saldo divergir do que o financeiro controla na planilha | Critério de aceite da Fase 1 é reproduzir a planilha do chefe, 28 linhas, centavo a centavo |
| R4 | Alguém ligar juros numa dívida por engano e mudar valores | Ligar é ato explícito, exige taxa e data, fica no log de auditoria, e o cabeçalho mostra "corrigida desde [data]" |
| R5 | Encargo virar título no CAP por engano e inflar a previsão | Regra D3 é do motor: ele não tem caminho de escrita para o CAP |

---

## 12. Plano de implementação em fases

| Fase | Entrega | Situação |
|---|---|---|
| **1** | `debt_accrual.py` (núcleo puro) + testes, com a planilha do chefe como caso real | ✅ concluída — 28 testes |
| **2** | Migration aditiva 0127 (`company_financial_rates`, `company_financial_events`, taxa padrão no `system_settings`) | ✅ concluída — neutra por construção: sem vigência, taxa é 0 |
| **3** | Leitura: endpoint do razão + indicadores; escrita de taxas e eventos | ✅ concluída |
| **4** | ~~Separar o Endividamento do componente dos Custos Fixos~~ | ⛔ desnecessária com o escopo reduzido |
| **5** | Tela padrão no formato da planilha (`DebtLedgerPanel`) | ✅ concluída — falta conferência visual |
| **6** | Cards consolidados de principal × encargo, projeção e custo efetivo (§9) | ⬜ pendente |

O que falta antes de publicar: a conferência visual com o usuário, os cards da Fase 6 e decidir
as pendências do §10.
