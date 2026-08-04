# Etapa 0 — Cronograma Financeiro Personalizado (Endividamento)

**Objetivo:** permitir que um endividamento use, em vez de "parcelas iguais", um
**cronograma financeiro** (agenda de pagamentos data/valor/descrição), que passa a ser a
**fonte única da verdade** para geração do Contas a Pagar (CAP), progresso, saldo e indicadores.

**Princípio inegociável:** 100% aditivo, reversível, preserva todos os dados e **não altera
nenhum comportamento** dos itens atuais (parcelas iguais).

> Status: **Fases 1–4 CONCLUÍDAS.** Backend (fundação + geração do CAP + leitura fonte única) e frontend
> (editor de cronograma reutilizável, gerador de faixas, conferência/validação, parcelas pagas travadas,
> timeline; frontend só consome o contrato). Próximo: Fase 5 (relatórios/export + verificação e2e).

---

## Refinamento v2 — Cronograma como FONTE OFICIAL e conceito de primeira classe

Após revisão, dois ajustes de arquitetura passam a valer (aprovados):

### R1. O cronograma é a fonte oficial da dívida renegociada (não só um alimentador do CAP)

Quando `uses_custom_schedule = true`, **todos** os indicadores da dívida derivam
**exclusivamente** de `cronograma (obrigações planejadas) + pagamentos reais do CAP (via
`entry_id`)` — nunca da soma das linhas nem de qualquer segunda fonte:

| Indicador | Origem no Modo 2 |
|---|---|
| Total negociado | `renegotiated_amount` (contrato) = Σ cronograma (invariante de fechamento) |
| Total do cronograma | Σ `amount` das linhas |
| Valor pago | Σ `amount_paid` dos títulos do CAP vinculados às linhas (`entry_id`) |
| Saldo restante | Total negociado − Valor pago |
| Progresso | Valor pago ÷ Total negociado |
| Parcelas restantes | linhas sem título quitado |
| Próxima parcela | 1ª linha em aberto por vencimento |
| Última parcela | linha de maior vencimento |
| Data de encerramento | vencimento da última linha |

O **item** passa a representar apenas o **contrato** (valor negociado, credor, metadados). O
**cronograma** representa a **execução financeira** desse contrato. **Sem duas fontes de verdade.**

### R2. "Cronograma Financeiro" é um conceito de primeira classe e reutilizável

O cronograma não é uma solução exclusiva do Endividamento. No futuro deve servir a acordos
judiciais, parcelamentos tributários, financiamentos, contratos de pagamento e qualquer obrigação
com calendário financeiro. Para isso, a arquitetura separa **lógica** de **armazenamento**:

- **Núcleo genérico (domain-agnostic)** — `app/services/financial_schedule.py`: estruturas puras
  (`ScheduleLine`, `RangeSpec`) e funções puras (`expand_range` = gerador de faixas;
  `build_schedule`; `validate_closure`; `compute_indicators`). **Não conhece ORM nem Endividamento.**
  É aqui que vivem a regra de fechamento e o cálculo ÚNICO dos 8 indicadores (R1). Qualquer domínio
  futuro reusa este núcleo alimentando `linhas + pagamentos por linha`.
- **Adaptador de domínio (Endividamento)** — mapeia ORM → núcleo: as linhas são
  `company_financial_payments` (o "lançamento" que já flui ao CAP por `entry_id`) e os pagamentos
  vêm de `payable_snapshots.amount_paid` via `entry_id`. É o **único** ponto de acoplamento.

**Decisão de armazenamento (Fase 1):** as linhas do cronograma **reutilizam
`company_financial_payments`** (não criamos tabela nova agora). Justificativa:
- é exatamente a estrutura que já vira título no CAP (`entry_id`), com reconciliação e proteção de
  pago **já prontas** — zero duplicação de regra;
- criar já uma tabela genérica exigiria repontar/afrouxar a FK `payable_snapshots.entry_id →
  company_financial_payments`, que é **compartilhada com os Custos Fixos** — risco direto ao
  mandato "não alterar comportamento dos itens atuais".

**Caminho de genericidade futura (documentado, não construído agora):** quando surgir o 2º
consumidor real (ex.: acordos judiciais), generaliza-se o armazenamento das linhas (owner
polimórfico ou header `financial_schedules`) em migração aditiva própria. Como toda a **lógica** já
está isolada no núcleo genérico, essa evolução é um refactor de storage — não uma reescrita de regra.

> Em resumo: **genérico na lógica desde já; genérico no armazenamento quando houver 2º consumidor.**
> Isso honra "primeira classe/reutilizável" sem pôr em risco os Custos Fixos.

---

## 0. Descoberta-chave (por que isso é barato de construir)

A infraestrutura já existe e serve quase inteira:

| Peça existente | Papel hoje | Papel no cronograma |
|---|---|---|
| `company_financial_items` | cadastro da dívida (renegociação, parcela fixa) | ganha 1 flag de modo |
| `company_financial_payments` (**lançamento**) | N lançamentos por competência → N títulos | **cada linha do cronograma = 1 lançamento** |
| `payable_snapshots.entry_id` (FK → payment) | 1 lançamento ↔ 1 título no CAP | **inalterado — é exatamente o vínculo do cronograma** |
| `_reconcile_company_finance_entries_for_month` | materializa/atualiza título por lançamento | reusado; só **desliga** a "linha de referência" |
| `replace_entries` | editor multi-lançamento de 1 competência | vira base do editor de cronograma |
| `origin_is_missing` (dívida) | **já** detecta órfão por `entry_id` (`payable_snapshot_service.py:2829`) | reusado sem mudança |
| paid-protection (`_entry_is_paid`, `skipped_paid`) | bloqueia editar/excluir lançamento pago | reusado — atende "parcela paga só é visualizada" |

**Conclusão:** um cronograma é um conjunto de `CompanyFinancialPayment` (um por parcela), cada um
na competência do seu vencimento, com `valor` e `due_date` exatos. O pipeline de CAP já transforma
cada lançamento em um título. **Não é preciso tabela nova para as parcelas.**

---

## 1. Arquitetura proposta

### 1.1 Modelo de dados (mínimo)

- **`company_financial_items`**: nova coluna `renegotiation_uses_schedule BOOLEAN NOT NULL DEFAULT false`.
  - `false` (todos os legados) → comportamento atual (UNIQUE / INSTALLMENTS iguais). **Nada muda.**
  - `true` → **Modo 2**: o cronograma governa tudo.
  - Optamos por **coluna booleana** em vez de estender o enum `renegotiation_type` com `SCHEDULE`
    porque `ALTER TYPE ... ADD VALUE` no Postgres não roda em transação e não é reversível — a
    coluna é aditiva e reversível por `DROP COLUMN`.

- **`company_financial_payments`** (opcional, recomendado): `installment_number INTEGER NULL`.
  - Rótulo/ordenação estável da parcela ("Parcela 7"). Puramente descritivo; não entra em cálculo.
  - Alternativa zero-migração: usar o campo `descricao` já existente ("Parcela 7"). Viável, mas
    `installment_number` deixa a ordenação robusta e o relatório limpo.

Nenhuma outra coluna nova. As parcelas reusam `competencia` (1º dia do mês do vencimento),
`valor`, `due_date` (data exata) e `descricao`.

### 1.2 Discriminador de comportamento

Toda a lógica nova fica atrás de **um único predicado**:

```
def uses_schedule(item) -> bool:
    return item.tipo == "endividamento" and bool(item.renegotiation_uses_schedule)
```

Se `False`, **todos** os caminhos caem exatamente no código de hoje (garantia de não-regressão).

### 1.3 Fonte única da verdade (ponto sensível — ver Risco #1)

O cronograma (as linhas) é a fonte de **planejamento**. O **pagamento realizado** continua vivendo
no CAP. Portanto, no Modo 2:

- **Total do cronograma** = Σ `valor` das linhas (planejado).
- **Total pago** = Σ `amount_paid` dos títulos do CAP vinculados (`entry_id` das linhas) — **não** a
  soma das linhas.
- **Saldo restante** = `renegotiated_amount` − Total pago.
- **Pagamentos futuros** = linhas cujos títulos ainda não foram quitados.

> Isto **difere** do legado, onde `total_pago = Σ it.payments.valor` (`company_finance_service.py:305`),
> porque no legado a linha só nascia quando o usuário registrava pagamento. No cronograma as linhas
> nascem **planejadas**, então somá-las mostraria 100% pago no dia zero. É o item de maior atenção.

---

## 2. Impacto no banco

| Objeto | Mudança | Tipo |
|---|---|---|
| `company_financial_items` | + `renegotiation_uses_schedule BOOLEAN NOT NULL DEFAULT false` | Aditiva |
| `company_financial_payments` | + `installment_number INTEGER NULL` (opcional) | Aditiva |

- Sem alteração de tipos existentes, sem `DROP`, sem `NOT NULL` retroativo sem default.
- Sem alteração de dados existentes (todo legado assume `false`/`NULL`).
- Índices: nenhum novo obrigatório. `payable_snapshots.entry_id` já é indexado.

---

## 3. Migrations necessárias

1. **`0103_debt_custom_schedule_flag`** (aditiva):
   - `ADD COLUMN renegotiation_uses_schedule BOOLEAN NOT NULL DEFAULT false` em `company_financial_items`.
   - `downgrade`: `DROP COLUMN`. **Totalmente reversível.**
2. **`0104_payment_installment_number`** (aditiva, opcional):
   - `ADD COLUMN installment_number INTEGER NULL` em `company_financial_payments`.
   - `downgrade`: `DROP COLUMN`.

Sem backfill. Nenhuma migração de dados. Compatível com a estratégia de deploy do Railway
(`alembic upgrade head` no startup), pois são colunas com default/nulo.

---

## 4. Compatibilidade com dados atuais

- Todo item existente fica com `renegotiation_uses_schedule = false` → **Modo 1**, idêntico a hoje.
- O invariante atual de parcelas iguais (`renegotiated_amount == installment_count × installment_value`,
  `schemas/company_finance.py:95`) **permanece** para Modo 1. O Modo 2 usa outro invariante
  (Σ cronograma == renegociado), aplicado **apenas** quando `uses_schedule`.
- Nenhum título de CAP existente é tocado. Nenhum pagamento é recalculado.
- Itens legados nunca entram no caminho novo a menos que o usuário ative o modo explicitamente.

---

## 5. Impacto na geração do CAP

Local: `_reconcile_company_finance_entries_for_month` e `_generate_company_finance_payables`
(`payable_snapshot_service.py`).

Mudanças, **todas atrás de `uses_schedule`**:

1. **Desligar a "linha de referência"** (bloco `if not entries and not cap_lines:` ~linha 808):
   no Modo 2 **nunca** materializamos parcela inventada. Só existem títulos para linhas que o
   cronograma tem. → Consequência direta do requisito: *"cronograma termina em jan/2029 ⇒ fev/2029
   não gera título"* — fevereiro simplesmente não tem linha, e a referência está desligada.
2. **Elegibilidade** (`_company_finance_item_eligible_for_comp`): no Modo 2 a elegibilidade da
   competência = "existe linha do cronograma naquele mês" (ativo + vigência), **ignorando**
   `is_monthly_required` (que é conceito do Modo 1). Cada linha vira 1 título com **valor e
   vencimento exatos da linha** (o reconciliador já faz isso por lançamento).
3. **Valor mensal** (`_company_finance_monthly_value`): não é usado no Modo 2 (não há referência a
   materializar); o valor vem da própria linha.

O resto do reconciliador (adoção de título legado, atualização de título aberto, preservação de
título pago) é reusado **sem alteração**.

Resultado: cada linha do cronograma ⇒ exatamente 1 título, valor = valor da linha, vencimento =
data da linha; fim do cronograma ⇒ fim dos títulos.

---

## 6. Impacto na reconciliação

- `origin_is_missing` para dívida **já** trata `entry_id`
  (`payable_snapshot_service.py:2823-2831`): título cuja linha (`CompanyFinancialPayment`) foi
  removida vira resíduo/obsoleto. **Nenhuma mudança.**
- Excluir uma parcela **aberta** do cronograma remove o título aberto (mesmo caminho do
  `replace_entries`), e a reconciliação do mês cuida de resíduos.
- Excluir/alterar parcela **paga** é bloqueado (ver §7). O título pago permanece e é reconciliado
  pelo `entry_id` como hoje.

---

## 7. Impacto no histórico de pagamentos

Requisito: parcela já paga **não** pode ser excluída nem alterada, apenas visualizada — mesmo
princípio dos múltiplos lançamentos.

- Reuso direto de `_entry_is_paid(snapshot)` + acúmulo em `skipped_paid` (já em `replace_entries`).
- No editor de cronograma (novo `replace_schedule`, espelho do `replace_entries` porém sobre
  **todas** as competências do item):
  - linha com título pago → **imutável** (valor/vencimento) e **não excluível**; tentativa é
    reportada em `skipped_paid` e ignorada;
  - linha aberta → editável/excluível, sincroniza o título correspondente;
  - o pagamento nunca é apagado (vive em `payable_payments`, `ON DELETE SET NULL` no `entry_id`).

Garante: "pagamentos já realizados nunca podem ser perdidos".

---

## 8. Riscos

| # | Risco | Sev. | Mitigação |
|---|---|---|---|
| 1 | **Semântica de `total_pago`**: somar linhas planejadas mostraria 100% pago no dia zero | **Alta** | No Modo 2, derivar Pago/Saldo/Progresso do CAP (`amount_paid` via `entry_id`), com branch por `uses_schedule` em `_item_to_read`, `pendencias`, `kpis_endividamento`, `chart_series` |
| 2 | **Vazamento da "linha de referência"** gerando título após o fim do cronograma | Média | Gate explícito no reconciliador (desliga materialização no Modo 2) + teste "mês pós-cronograma não cria título" |
| 3 | **Grade legada** (`replace_payments`, caixa por mês) achatar/editar linhas do cronograma | Média | No Modo 2 a grade fica **somente leitura**; guarda análoga ao `len(existing) > 1` já existente |
| 4 | **Validação de fechamento** (Σ cronograma ≠ renegociado) | Média | Invariante Modo 2 no schema + serviço; bloquear salvar salvo flag explícito de exceção |
| 5 | **Pendências** do Modo 1 (âncora + `installment_count`) contarem errado no Modo 2 | Média | `pendencias` deriva do cronograma (linhas sem título pago no mês), não da fórmula de parcela |
| 6 | **Piso de implantação** (`AUTOGEN_FIRST_COMPETENCE = 2026-07-01`) x parcelas anteriores | Baixa | Cronograma real começa 08/2026 (acima do piso); linhas abaixo do piso, se houver, só geram título por lançamento explícito — comportamento já existente |
| 7 | Editar `renegotiated_amount` depois do cronograma pronto / com parcelas pagas | Média | Revalidar fechamento na edição; nunca tocar linhas pagas; avisar diferença |

---

## 9. Estratégia de migração

- **Aditiva e dormente:** as migrations entram com default seguro; o modo só é acessível quando o
  usuário liga o toggle. Produção segue 100% no comportamento atual até uso explícito.
- **Reversível:** `DROP COLUMN` desfaz o schema; como nenhum dado legado depende das colunas novas,
  o rollback é limpo. Itens que porventura já tenham virado cronograma voltam a ser lidos como
  Modo 1 apenas se o flag existir — por isso o rollback de schema deve vir acompanhado de reversão
  de eventuais itens em Modo 2 (procedimento no plano de fases).
- **Sem recomputo:** nada de regenerar meses fechados; títulos e pagamentos existentes intactos.
- **Feature-flaggável:** o toggle na UI pode ficar oculto até a Fase 3 concluída (backend pronto e
  testado antes de expor).

---

## 10. Plano de implementação em fases

**Fase 1 — Fundação (schema + contratos), dormente**
- Migration `0103` (flag) e `0104` (installment_number, opcional).
- Modelo: campos novos; `uses_schedule(item)` helper.
- Schemas: branch de validação Modo 2 (Σ cronograma == renegociado) sem quebrar Modo 1.
- ✅ Critério: suíte atual verde; nenhum caminho novo acionável ainda.

**Fase 2 — Geração do CAP (núcleo)**
- Gate `uses_schedule` no reconciliador: desliga referência; elegibilidade por "linha existe".
- `replace_schedule` (serviço) espelhando `replace_entries` para N competências, com paid-protection.
- Gerador de faixas (função pura + endpoint de _preview_): entrada
  `{parcela_inicial, parcela_final, valor, dia, primeiro_vencimento}` → linhas (reusa `add_months`).
- ✅ Critério: dado um cronograma, o CAP tem 1 título por linha (valor/venc. exatos); mês pós-fim não gera título; parcela paga preservada.

**Fase 3 — Fonte única (leitura/indicadores)**
- Branch por `uses_schedule` em `_item_to_read`, `pendencias`, `kpis_endividamento`, `chart_series`:
  Pago/Saldo/Progresso vindos do CAP; pagamentos futuros = linhas em aberto.
- Grade legada somente leitura no Modo 2.
- ✅ Critério: progresso reflete pagamentos reais; validação de fechamento visível.

**Fase 4 — Frontend**
- Toggle **Parcelas iguais ↔ Cronograma personalizado** no form de renegociação
  (`CompanyFinanceExecutive.tsx` / `CompanyFinanceAnalyticTable.tsx`).
- Editor de cronograma (tabela data/valor/descrição) reusando o padrão do
  `LancamentosCompetenciaModal.tsx`; parcelas pagas em modo leitura.
- Gerador de faixas (UI) + painel de validação: Renegociado / Total do cronograma / Diferença
  (✔ válido | ⚠ não fecha), bloqueio de salvar com diferença.
- ✅ Critério: montar 30 parcelas via 3 faixas em segundos; salvar bloqueado enquanto há diferença.

**Fase 5 — Relatórios/Export e verificação**
- Relatórios/exportações de Endividamento refletindo o cronograma (reuso das colunas existentes).
- Verificação ponta a ponta (restaurar backup de produção no ambiente de teste e exercitar).
- ✅ Critério: exportações corretas; nenhuma regressão nos itens Modo 1.

---

## Resumo das mudanças de arquivo previstas (para a implementação)

- **Migrations:** `0103_debt_custom_schedule_flag.py`, `0104_payment_installment_number.py`.
- **Modelo:** `app/models/company_finance.py` (flag + installment_number + helper).
- **Serviços:** `app/services/payable_snapshot_service.py` (gate no reconciliador),
  `app/services/company_finance_service.py` (`replace_schedule`, gerador de faixas, branch de
  leitura/indicadores, grade read-only).
- **Schemas/Router:** `app/schemas/company_finance.py` (validação Modo 2, payloads de cronograma e
  de preview de faixa), `app/modules/company_finance/router.py` (endpoints do cronograma/preview).
- **Frontend:** `CompanyFinanceExecutive.tsx`, `CompanyFinanceAnalyticTable.tsx`,
  novo editor de cronograma (padrão `LancamentosCompetenciaModal.tsx`), `services/companyFinance.ts`.

Tudo atrás do flag; Modo 1 permanece byte-a-byte como hoje.
