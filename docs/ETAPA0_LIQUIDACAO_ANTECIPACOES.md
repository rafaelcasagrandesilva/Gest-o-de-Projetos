# Etapa 0 — Antecipações: Liquidação de NFs + Ledger de Repasse

**Objetivo:** deslocar o controle do **Repasse** para o **ciclo de liquidação das NFs antecipadas**.
Hoje a obrigação da empresa perante a instituição (ex.: "ainda devemos essa NF para a LEPTA") não
é rastreada em lugar nenhum — é inferida indiretamente do status da NF, que **não** reflete essa
dívida. Esta evolução cria um controle **próprio e independente** dentro do módulo de Antecipações:

1. **Aba Liquidação de NFs** — toda NF antecipada por uma instituição "credora" (perfil LEPTA e
   afins) vira uma **obrigação** com situação própria: *Em aberto / Vencida / Liquidada*,
   **independente** do `invoice_status` da NF.
2. **Repasse deixa de gerar Contas a Pagar** e passa a viver como um **Ledger (extrato) append-only**
   dentro de Antecipações: cada operação credita o Repasse Retido; cada liquidação com origem
   "Saldo do Repasse" debita. Nunca editar, nunca excluir — só estornar por lançamento.
3. **Aba Operações** ganha cards, filtros e indicadores; a coluna "Bruto" (hoje inútil) dá lugar a
   **"Repasse Retido"**.

> **Status: ANÁLISE (Etapa 0) concluída. Nada implementado.** Ver §13 (decisões) e §14 (fases).
> Regra inquebrável do pedido: **o módulo de Notas Fiscais não muda** — sem status novo, sem
> campo novo, sem lógica nova. Todo o controle é do módulo de Antecipações. Migração **100% aditiva**.
> **Execução em duas etapas (§14):** *Fase 1A* entrega toda a infraestrutura **sem mudar nenhum
> comportamento** (a LEPTA continua gerando repasse no CAP); *Fase 1B* faz a integração (repasse sai
> do CAP → ledger) e a migração de dados só depois da infra pronta e testada. Situação e valores
> (`valor_total`/`valor_liquidado`/`valor_residual`) são **sempre computados no backend** (§5.7).

---

## 0. Descoberta-chave (por que é de risco controlado)

A infraestrutura necessária **já existe em 90%** — a evolução é sobretudo *composição*, não invenção:

1. **O vínculo NF ↔ operação já é N:N e reversível.** A tabela de junção
   `receivable_advance_batch_items` ([app/models/receivable_advance_batch.py:95](app/models/receivable_advance_batch.py:95))
   já é o registro por-participação de "esta NF foi antecipada nesta operação". A obrigação perante a
   instituição é **exatamente uma propriedade dessa participação** — não precisamos de vínculo novo
   entre NF e dívida.

2. **A lógica por instituição já é encapsulada em handlers** (`advance_operations/`: base, lepta,
   daycoval), resolvidos por `operation_profile`
   ([app/services/advance_operations/__init__.py:13](app/services/advance_operations/__init__.py:13)).
   "Quem cria obrigação de liquidação" e "quem tem repasse" viram **capacidades declaradas no
   handler** — genérico para qualquer instituição, sem `if instituição == LEPTA`.

3. **O Repasse já é um valor congelado na operação** (`repasse_amount`/`repasse_enabled`,
   [receivable_advance_batch.py:72-74](app/models/receivable_advance_batch.py:72)). Ele **só é
   duplicado** hoje ao gerar uma linha no CAP em `lepta.on_confirm`
   ([lepta.py:134-142](app/services/advance_operations/lepta.py:134)). Trocar essa única chamada por
   um lançamento no Ledger é uma alteração **cirúrgica**.

4. **Já existe um padrão append-only com estorno** no código: `PayablePayment`
   ([app/models/payable_payment.py](app/models/payable_payment.py)) — evento imutável, `reversed_at`/
   `reversal_reason` (nunca hard-delete), FK para a obrigação. O Ledger de Repasse e o registro de
   Liquidação seguem esse mesmo idioma.

5. **A UI já tem todas as peças**: status `SETTLED`="Liquidada" já existe
   ([AdvanceBatches.tsx status meta](frontend/src/pages/AdvanceBatches.tsx)); `Receivables.tsx` já é
   o espelho pronto de "KPIs + filtros + tabela sortável + modal"; `Users.tsx` é o padrão de abas
   internas; `OperationInvoicesTable` já lista NFs de uma operação. O endpoint `POST /confirm` e a
   função `confirmAdvanceBatch` estão **órfãos** (definidos e não usados) — sobra de API reaproveitável.

**Conclusão:** a evolução é **aditiva e reversível**. O único ponto que exige cuidado real é a
**migração do Repasse que já está no CAP** (§10/§11), porque parte pode já ter pagamento.

---

## 1. Arquitetura atual (resumo)

```
AdvanceInstitution (operation_profile: LEPTA | DAYCOVAL | …)
   └─ handler (LeptaOperationHandler | DaycovalOperationHandler | BaseOperationHandler)

ReceivableAdvanceBatch (operação/borderô)  status: DRAFT→OPEN→SETTLED / CANCELLED
   ├─ gross_amount, received_amount, discount_amount, fee_amount
   ├─ repasse_enabled, repasse_amount          ← 7% do ANTECIPADO, congelado no confirm
   ├─ receive_date, repayment_date
   └─ items: ReceivableAdvanceBatchItem[]       ← N:N (uq batch_id+invoice_id)
        ├─ invoice_id, invoice_amount
        ├─ advance_basis (BRUTO|LIQUIDO|LIQUIDO_MENOS_10|MANUAL)
        └─ advanced_amount                       ← congelado no confirm

ReceivableInvoice  invoice_status: EMITIDA | ANTECIPADA | RECEBIDA | CANCELADA (derivado)
   ├─ is_anticipated, institution, advance_batch_id (ponteiro denormalizado)
   └─ advance_batch_items (N:N, fonte de verdade)
```

**Fluxo de efeitos (hoje):** criar = `create_batch` + `confirm_batch` na mesma transação
([router.py:429](app/modules/receivables/router.py:429)). `confirm` → handler `on_confirm`. Editar =
`_revert_batch_effects`(→DRAFT) → `_populate_batch` → `on_confirm`. Cancelar =
`_revert_batch_effects`(→CANCELLED). Toda reversão passa por um núcleo único
([receivable_advance_batch_service.py:479](app/services/receivable_advance_batch_service.py:479)) com
**guarda de pagamento** (bloqueia se qualquer despesa do lote no CAP já foi paga).

**Perfis:**
- **LEPTA** (`lepta.py`): NFs → **ANTECIPADA**; gera no CAP até 3 linhas (deságio, tarifa, **repasse**),
  todas `ANTECIPACAO_OPERACAO`, `ref_id=batch.id`, competência/vencimento = `receive_date`. A obrigação
  perante a LEPTA **não é modelada** — é o que esta Etapa 0 resolve.
- **DAYCOVAL** (`daycoval.py`): NFs → **RECEBIDA** (encerra o ciclo da NF), `include_in_dashboard=False`
  para não duplicar receita; **não** gera CAP. É a antecipação "terminal".

**invoice_status** é **derivado** ([schemas/receivable.py:39](app/schemas/receivable.py:39)):
`CANCELADA` > `RECEBIDA` (recebido ≥ líquido) > `ANTECIPADA` > `EMITIDA`. **Não existe VENCIDA na NF** —
atraso é calculado só na camada de exibição. Isso confirma a tese do pedido: a "situação perante a
instituição" **não cabe** no `invoice_status` e precisa de dimensão própria.

---

## 2. Conceito central: a **Obrigação de Liquidação** (genérica)

A peça nova de domínio é a **obrigação de liquidação de uma NF antecipada perante a instituição**.
Ela é uma propriedade de **cada participação da NF numa operação confirmada** cujo handler declara
que "empresta contra a NF" (perfil credor).

- **Grão = `ReceivableAdvanceBatchItem`** (a participação NF↔operação), não a NF isolada. Motivo: no
  N:N, a mesma NF pode ter sido antecipada em **duas** operações LEPTA — são **duas** dívidas. Uma
  linha por participação torna a obrigação inequívoca. No caso comum (NF em uma só operação), 1
  participação = 1 NF, então a tela "lista de NFs" continua natural.
- **Quem gera obrigação:** capacidade `creates_settlement_obligation` no handler.
  LEPTA=**True**, DAYCOVAL=**False** (terminal — vira RECEBIDA e sai do ciclo), Base=configurável.
- **Vencimento da obrigação** = `batch.repayment_date` (data de devolução da operação).
- **Valor da obrigação** = `batch_item.advanced_amount` (o valor efetivamente antecipado pela
  instituição para aquela NF, congelado na confirmação).
- **Liquidação é 1:N (obrigação → movimentações).** Cada movimentação tem origem, valor, data,
  observação e auditoria (§3.1). A obrigação fica **Parcialmente Liquidada** até que a soma das
  movimentações ativas atinja o valor da obrigação; ao atingir 100% (com tolerância de centavos),
  passa automaticamente para **Liquidada**. Ex.: obrigação R$ 100.000 = R$ 30.000 (Saldo do Repasse)
  + R$ 20.000 (Caixa) + R$ 50.000 (Antecipação Daycoval).
- **Residual** = valor da obrigação − Σ movimentações ativas. É o que ainda se deve.
- **Situação (derivada, nunca escrita na NF)** — a partir do residual e do vencimento:
  - `LIQUIDADA` — residual ≤ 0 (Σ movimentações ≥ valor da obrigação);
  - `PARCIALMENTE_LIQUIDADA` — há movimentação ativa, mas ainda resta residual > 0;
  - `VENCIDA` — residual > 0 **e** `repayment_date < hoje` (aplica-se ao residual, mesmo com
    liquidação parcial);
  - `EM_ABERTO` — residual = valor integral e ainda não venceu.
- **Independência total do `invoice_status`:** uma NF pode estar **RECEBIDA** (porque o Daycoval a
  antecipou depois) e a obrigação LEPTA continuar **VENCIDA**. São dois eixos ortogonais. O módulo de
  NFs permanece intocado.

O **Repasse Retido** é a segunda peça: um **saldo acumulado por instituição** que nasce de cada
operação e é consumido nas liquidações com origem "Saldo do Repasse".

---

## 3. Modelo de dados proposto (aditivo)

Duas tabelas novas + um enum. Nada é alterado nas tabelas existentes (exceto, opcionalmente, um
`server_default` — ver §4). O `repasse_amount`/`repasse_enabled` do batch **permanecem** (continuam
sendo a fonte do valor congelado).

### 3.1 `advance_settlement_movements` — movimentações de liquidação (1:N, append-only + estorno)

Uma obrigação (participação `batch_item`) tem **N movimentações**. Cada movimentação é um **evento
imutável** (idioma de `PayablePayment`): uma origem, um valor, uma data. A obrigação é liquidada pela
**soma** das movimentações ativas — não existe um "registro de liquidação" único. Isso representa o
processo real (ex.: R$ 30k Saldo do Repasse + R$ 20k Caixa + R$ 50k Antecipação Daycoval = R$ 100k).

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | UUID PK | |
| `batch_item_id` | UUID FK → `receivable_advance_batch_items.id` (ondelete RESTRICT, index) | a obrigação (grão) |
| `batch_id` | UUID FK → `receivable_advance_batches.id` (index) | denormalizado p/ consulta/rastreio |
| `invoice_id` | UUID FK → `receivable_invoices.id` (index) | denormalizado p/ consulta/filtro |
| `institution_id` | UUID FK → `advance_institutions.id` | credor da obrigação |
| `amount` | Numeric(14,2) | valor **desta** movimentação (parcial) — sempre > 0 |
| `funding_source` | Enum `advance_funding_source` | origem **desta** movimentação (ver 3.3) |
| `settled_at` | Date | data da movimentação |
| `observation` | Text (null) | observação livre (obrigatória se `OUTRA`) |
| `reversed_at` | DateTime tz (null) | estorno soft (nunca hard-delete) |
| `reversal_reason` | Text (null) | |
| `created_by_id` | UUID FK → users | auditoria |
| timestamps | | `TimestampUUIDMixin` |

**Situação da obrigação** = derivada da soma das movimentações **ativas** (`reversed_at IS NULL`) do
`batch_item_id` versus o valor da obrigação (`advanced_amount`) e o `repayment_date` — ver §2
(LIQUIDADA / PARCIALMENTE_LIQUIDADA / VENCIDA / EM_ABERTO). **Guarda de integridade:** a soma das
movimentações ativas **nunca** pode exceder o valor da obrigação (bloqueia sobre-liquidação).

> **Confirmado (D3):** o modelo nasce **1:N** (parcial + multi-origem). A UI pode começar simples
> (adicionar várias linhas de origem na mesma tela de "Liquidar NF"), mas o dado já suporta o
> processo real — sem refatoração futura.

### 3.2 `advance_repasse_ledger` — extrato do Repasse (append-only + estorno)

Livro-razão por **instituição**. Saldo = `Σ CREDIT − Σ DEBIT` (ativos).

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | UUID PK | |
| `institution_id` | UUID FK → `advance_institutions.id` (index) | dono do saldo |
| `direction` | Enum `repasse_ledger_direction` = `CREDIT` \| `DEBIT` | |
| `amount` | Numeric(14,2) | sempre positivo |
| `source_type` | Enum `repasse_ledger_source` = `OPERATION` \| `SETTLEMENT` \| `ADJUSTMENT` | |
| `source_batch_id` | UUID FK → batches (null) | preenchido quando `OPERATION` |
| `source_movement_id` | UUID FK → `advance_settlement_movements` (null) | preenchido quando `SETTLEMENT` |
| `occurred_at` | Date | data-base do movimento |
| `description` | String(255) | ex.: "Repasse retido — Operação SGC 42" |
| `reversed_at` / `reversal_reason` | | estorno soft |
| `created_by_id` | UUID FK → users | |
| timestamps | | |

**Entradas (CREDIT):** toda operação confirmada de perfil com repasse (`repasse_enabled` e
`repasse_amount > 0`) → 1 CREDIT `source_type=OPERATION`, `amount=repasse_amount`.
**Saídas (DEBIT):** **apenas** a movimentação com `funding_source=SALDO_REPASSE` → 1 DEBIT
`source_type=SETTLEMENT`, `amount = movimentação.amount`. Origens diferentes (Caixa, Daycoval,
Recebimento, Outra) **não** tocam o ledger.
**Estorno:** cancelar/editar a operação estorna o CREDIT (soft); estornar a movimentação estorna o DEBIT.

### 3.3 Enum `advance_funding_source` (origem dos recursos)

`SALDO_REPASSE` | `RECEBIMENTO_CLIENTE` | `ANTECIPACAO_DAYCOVAL` | `CAIXA_EMPRESA` | `OUTRA`.

> **Importante (do pedido):** `ANTECIPACAO_DAYCOVAL` é **apenas um rótulo de origem** — **não** cria
> vínculo com nenhuma operação Daycoval específica. Só `SALDO_REPASSE` tem efeito colateral (debita o
> ledger). As demais são puramente informativas.

---

## 4. Impacto no banco / migrations

**Aditivo, e dividido em duas migrations para casar com as fases 1A/1B (§14):**

- **`0105` (Fase 1A) — só estrutura, dormant:**
  1. cria os 3 enums (`advance_funding_source`, `repasse_ledger_direction`, `repasse_ledger_source`);
  2. cria as tabelas `advance_settlement_movements` e `advance_repasse_ledger` com FKs e índices.
  **Sem backfill, sem tocar CAP/dados existentes.** Nenhum número de produção muda.
- **`0106` (Fase 1B) — migração de dados:** backfill do ledger a partir das operações confirmadas com
  repasse + política **D1** para as linhas de repasse já no CAP (ver §10). Só entra depois da 1A verde.

**Sem** alteração de tipos existentes, **sem** novo valor em enum já existente (evita
`ALTER TYPE ADD VALUE`, que não roda em transação — mesma lição da migration `0103`), **sem** tocar
`ReceivableInvoice`, **sem** tocar `PayableSnapshotType`. Reversível por `DROP TABLE`/`DROP TYPE`.

> Opcional (fora do caminho crítico): índice em `receivable_advance_batches(status, repayment_date)`
> e em `advance_repasse_ledger(institution_id, reversed_at)` para os cards/somatórios.

---

## 5. Serviços

### 5.1 Handlers — novas capacidades declarativas (`advance_operations/`)
- `BaseOperationHandler.creates_settlement_obligation: bool = False`
- `BaseOperationHandler.has_repasse: bool = False`
- **Lepta:** `creates_settlement_obligation = True`, `has_repasse = True`.
- **Daycoval:** ambos `False` (inalterado — continua liquidando a NF como RECEBIDA).

### 5.2 `AdvanceRepasseLedgerService` (novo) — **módulo financeiro INDEPENDENTE**
**Diretriz arquitetural (usuário):** o Ledger é um módulo financeiro genérico e **totalmente
independente** — ele **nunca** conhece regras da LEPTA (nem de qualquer instituição). Ele só **registra
créditos e débitos**; **quem** decide *quando* creditar/debitar é o fluxo de Antecipações. Qualquer
outra instituição poderá usar o mesmo Ledger no futuro.

- **Interface (Port) mínima e estável:** `credit(...)`, `debit(...)`, `balance(institution_id)` +
  `reverse_source(...)` (estorno). Assinaturas recebem apenas dados primitivos (institution_id, valor,
  `source_type`, ids de origem, data, descrição) — **sem** nenhum tipo de "batch"/"lepta"/"%".
- **A Liquidação (Settlement) conversa SÓ com essa interface** (`credit/debit/balance/reverse`),
  **nunca** com as tabelas do Ledger diretamente. Isso é enforçado por tipagem: o Settlement recebe um
  `RepasseLedgerPort` (Protocol), não o modelo ORM.
- Append-only; estorno por lançamento. Nunca update/delete de linha.
- Saldo = `Σ CREDIT − Σ DEBIT` (lançamentos ativos) por instituição.

### 5.3 `AdvanceSettlementService` (novo)
- `list_obligations(filtros)` — deriva as participações de operações **OPEN/SETTLED** de perfil
  credor. **O backend calcula e devolve os totais explicitamente — o frontend NUNCA recalcula**
  (ver §5.7). Cada obrigação retorna: `valor_total`, `valor_liquidado`, `valor_residual`, `situacao`
  (EM_ABERTO/PARCIALMENTE_LIQUIDADA/VENCIDA/LIQUIDADA), `dias_em_atraso`, `origens_resumo` (resumo das
  origens usadas, §5.7) e a lista de movimentações ativas. Reaproveita `operations_for_invoices` /
  `confirmed_operation_counts` já existentes.
- `add_movements(batch_item_id, [(funding_source, amount, settled_at, observation), …])` — registra
  **uma ou várias** movimentações numa transação. Guardas: (a) Σ movimentações ativas ≤ valor da
  obrigação (não sobre-liquidar); (b) a soma das parcelas `SALDO_REPASSE` ≤ **saldo disponível** do
  ledger daquela instituição — bloqueia **só** o excesso de repasse, **sem** impedir a liquidação por
  outras origens (decisão D4). Para cada parcela `SALDO_REPASSE`, chama `ledger.debit_settlement`.
- `reverse_movement(movement_id, reason)` — estorno soft + estorno do DEBIT correspondente (se houver).
- `settlement_kpis(filtros)` — alimenta os cards (§7.2/§7.3).

### 5.4 `LeptaOperationHandler.on_confirm` — **repasse sai do CAP, entra no ledger** *(Fase 1B)*
Trocar [lepta.py:134-142](app/services/advance_operations/lepta.py:134) (o `add_operation_payable_line`
do repasse) por `AdvanceRepasseLedgerService.credit_operation(batch)`. **Deságio e tarifa continuam
no CAP** (são despesas reais — o pedido só tira o repasse). Congelamento de `repasse_amount`
inalterado. **⚠️ Esta é a única mudança de comportamento — só na Fase 1B; na 1A a LEPTA segue gerando
repasse no CAP.**

### 5.5 Reversão (cancel/edit) — estender `_revert_batch_effects` *(Fase 1B)*
Além de apagar as linhas de CAP do lote (deságio/tarifa, com a guarda de pagamento atual),
[receivable_advance_batch_service.py:479](app/services/receivable_advance_batch_service.py:479) passa a:
- estornar o CREDIT de repasse do lote no ledger;
- **bloquear** se houver **liquidação ativa** consumindo saldo desse repasse (análogo à guarda de
  pagamento — não se pode reverter uma operação cujo repasse já foi usado para liquidar).

### 5.6 Router (`app/modules/receivables/router.py`)
Novos endpoints (mesma permissão `INVOICES_UPDATE`/`INVOICES_READ` já usada no módulo):
- `GET  /invoices/advance-settlements` — lista de obrigações (+ residual/situação) + filtros.
- `POST /invoices/advance-settlements` — liquidar: `batch_item_id` + **lista de movimentações**
  (`[{funding_source, amount, settled_at, observation}]`) numa transação.
- `DELETE /invoices/advance-settlement-movements/{id}` — estornar uma movimentação (soft).
- `GET  /invoices/advance-repasse-ledger?institution_id=…` — extrato + saldo.
- `GET  /invoices/advance-settlements/kpis` — cards.

O `POST /advance-batches/{id}/confirm` órfão pode ser removido nesta faxina (ou mantido no-op).

### 5.7 Contrato da API — totais explícitos + resumo de origens
**Regra:** a situação e os valores são **sempre computados no backend**; o frontend só exibe (nunca
recalcula soma/residual/situação). Cada obrigação retornada por `GET /invoices/advance-settlements`
(e no detalhe) traz:

```jsonc
{
  "batch_item_id": "…",
  "invoice_number": "12345", "client_name": "…", "sgc_number": 42, "institution": "LEPTA Multissetorial",
  "valor_total":     100000,   // = batch_item.advanced_amount (valor da obrigação)
  "valor_liquidado":  65000,   // = Σ movimentações ATIVAS (reversed_at IS NULL)
  "valor_residual":   35000,   // = valor_total − valor_liquidado
  "situacao": "PARCIALMENTE_LIQUIDADA",   // derivada de residual + repayment_date
  "vencimento": "2026-09-30", "dias_em_atraso": 0,
  "origens_resumo": "Repasse + Caixa",    // resumo legível das origens usadas (ver abaixo)
  "movimentacoes": [ /* detalhe: origem, valor, data, obs, auditoria, reversed_at */ ]
}
```

- **`origens_resumo`** — string curta com as **origens distintas** das movimentações **ativas**, em
  ordem de valor desc. (ou ordem fixa), rótulos amigáveis: *Repasse* (`SALDO_REPASSE`), *Caixa*
  (`CAIXA_EMPRESA`), *Cliente* (`RECEBIMENTO_CLIENTE`), *Daycoval* (`ANTECIPACAO_DAYCOVAL`), *Outra*
  (`OUTRA`). Exemplos: `"Repasse"`, `"Repasse + Caixa"`, `"Daycoval"`, `"Repasse + Daycoval"`,
  `"Repasse + Caixa + Cliente"`. Vazio (`""` ou `null`) quando não há movimentação.
- A tela da Aba Liquidação exibe **apenas** esse resumo; o **detalhe** das movimentações continua
  vindo por `movimentacoes` (drill-down / modal). Assim a listagem é barata e o detalhe é sob demanda.
- Também exposto de forma agregada nos **cards/KPIs** (`GET …/kpis`): totais por situação e o
  Saldo do Repasse por instituição — todos calculados no backend.

---

## 6. Impacto no CAP (Contas a Pagar)

- **Repasse deixa de virar CAP.** Novas operações não criam mais a linha "Repasse não apropriado".
  Deságio e tarifa **permanecem** exatamente como hoje (`ANTECIPACAO_OPERACAO`, `ref_id=batch.id`).
- **Linhas de repasse já existentes no CAP** (legado) são tratadas na migração (§10). Como
  `ANTECIPACAO_OPERACAO` está em `PAYABLE_PRESERVED_TYPES`
  ([payable_snapshot_service.py:81](app/services/payable_snapshot_service.py:81)), elas **não somem**
  sozinhas em `invalidate_months` — exigem tratamento explícito.
- **Guardas de pagamento** intactas para deságio/tarifa. O repasse ganha guarda **equivalente** no
  ledger (não reverter operação com repasse já consumido em liquidação).

---

## 7. Frontend

### 7.1 Abas em `AdvanceBatches.tsx`
Adotar o padrão de abas internas de `Users.tsx` (state `tab: "operacoes" | "liquidacao"`, pill group),
extraindo a tabela atual para um `<Operations>` e criando `<Settlements>`. Sem rota nova
obrigatória (opcional: querystring `?tab=`). Menu em `workspaces/navigation.ts` inalterado.

### 7.2 Aba **Operações** (evolução)
- **Coluna "Bruto" → "Repasse Retido"** (`repasse_amount`), como pedido.
- **Cards** (candidatos — ver §13 D5): Operações em Aberto · Valor Antecipado (Σ `advanced_amount`) ·
  Deságio Acumulado · Tarifas · **Repasse Retido (saldo)** · Líquido Creditado.
- **Filtros:** período (recebimento/devolução), instituição, situação (status da operação), NF, borderô.
- Adotar `SortableTh`/`useTableSort` (alinha com `Receivables.tsx`).

### 7.3 Aba **Liquidação de NFs** (nova) — espelho de `Receivables.tsx`
- **Tabela** (1 linha por obrigação/participação): Nº NF · Cliente · Borderô (SGC) · Instituição ·
  Valor (`valor_total`) · **Liquidado** (`valor_liquidado`) · **Residual** (`valor_residual`) ·
  **Origens** (`origens_resumo`, ex.: "Repasse + Caixa") · Vencimento (`repayment_date`) · **Dias em
  atraso** · **Situação** (badge Em aberto / Parcialmente liquidada / Vencida / Liquidada). **Todos os
  valores e a situação vêm prontos do backend** (§5.7) — a tela não recalcula nada.
- **Filtros:** período, instituição, cliente, borderô, número da NF, situação.
- **Cards:** NFs Pendentes · NFs Vencidas · Valor Total Vencido (Σ residual das vencidas) · Total
  Liquidado · Saldo do Repasse.
- **Botão "Liquidar NF"** → modal com **múltiplas linhas de origem** (adicionar/remover): cada linha =
  origem (`advance_funding_source`) + valor + data + observação (obrigatória se "Outra"). Mostra
  residual restante e ajuda a **completar a diferença** (auto ou manual) com outra origem quando o
  Saldo do Repasse é insuficiente. Ao salvar → soma as movimentações; situação vira
  **Parcialmente liquidada** (residual > 0) ou **Liquidada** (residual = 0). As parcelas
  `SALDO_REPASSE` debitam o ledger e atualizam os cards de saldo. Reaproveita `OperationInvoicesTable`
  e o chrome de modal existente.
- **Extrato do Repasse** (sub-visão ou modal): lista CREDIT/DEBIT + saldo, read-only, com botão
  "Estornar" por linha (nunca editar/excluir).

### 7.4 Serviços TS novos
`advanceSettlements.ts` (list/create/reverse/kpis) e `advanceRepasseLedger.ts` (statement/balance),
no mesmo estilo de `receivableAdvanceBatches.ts`.

---

## 8. Dashboards

- **Dashboard Financeiro (regime de caixa)** — o único consumidor sensível
  ([financial_dashboard_service.py](app/services/financial_dashboard_service.py)):
  - **Receita:** inalterada. `batch.received_amount` já é **líquido** (Lepta net-received,
    [lepta.py:72/95](app/services/advance_operations/lepta.py:72)); repasse nunca entrou como receita.
  - **Custos/Pago:** hoje o repasse **pago** entra em `pago`/`custos` (query sem filtro de tipo,
    [financial_dashboard_service.py:187-204/293-311](app/services/financial_dashboard_service.py:187)).
    Ao sair do CAP, esse custo **some** e `caixa = faturamento − pago` **sobe**. ⚠️ **Decisão D2**:
    isso é o comportamento correto (repasse não é despesa a pagar, é retenção), mas muda um número
    histórico do dashboard — validar com o financeiro e alinhar a migração dos rows pagos.
- **Dashboard de Projetos/Executivo:** a linha "antecipacao" é uma **provisão percentual**
  (`receita × anticipation_rate`, [financial_service.py:226](app/services/financial_service.py:226))
  sem relação com borderô/repasse — **não afetada**.
- **Novo indicador possível:** expor "Saldo de Repasse" e "Dívida perante instituições (Σ vencido)"
  como cards do dashboard financeiro (reaproveita o framework ECharts/`KpiCard`).

---

## 9. Relatórios

- **Nenhum report_type de repasse/liquidação existe hoje** ([schemas/reports.py:8](app/schemas/reports.py:8)).
- **`payables_detailed`**: hoje inclui as linhas de repasse (`ANTECIPACAO_OPERACAO`). Ao sair do CAP,
  o repasse deixa de aparecer nele — **esperado**. Deságio/tarifa continuam.
- **Novos relatórios** (motor operacional, padrão já estabelecido — memória
  [[reports-module-export]]): adicionar em `ReportType`, `REPORT_TITLES`, `_OPERATIONAL_COLUMNS`, um
  `generate_*` em `operational_report_service.py` e o dispatch:
  - **`repasse_ledger`** — extrato por instituição (entradas/saídas/saldo);
  - **`liquidacao_antecipacoes`** — obrigações com situação, vencimento, dias em atraso, origem da
    liquidação. Fonte: as tabelas novas (não o `PayableSnapshot`).
- `receivables_detailed`/`invoices_detailed`: inalterados (leem NF/operação, não repasse-CAP).

---

## 10. Estratégia de migração / backfill

**Aditiva, idempotente, validável.** Ordem na migration `0105` (ou script de dados acoplado):

1. **Ledger a partir das operações:** para cada `ReceivableAdvanceBatch` **OPEN/SETTLED** com
   `repasse_enabled` e `repasse_amount > 0`, criar 1 CREDIT `OPERATION` (`amount = repasse_amount`).
   Idempotente por `(source_type=OPERATION, source_batch_id)`.
2. **Repasse já no CAP (o ponto sensível):** as linhas "Repasse não apropriado" existentes são
   `ANTECIPACAO_OPERACAO`/`ref_id=batch.id`. Política recomendada (**decisão D1**):
   - **Não pagas:** remover (deixam de ser obrigação de CAP) — o valor já está representado como saldo
     no ledger.
   - **Pagas:** **preservar** a linha e o pagamento (histórico financeiro é intocável) **e** registrar
     no ledger, além do CREDIT, um DEBIT `ADJUSTMENT` de mesmo valor com descrição "Repasse liquidado
     via CAP (legado)" — assim o saldo do ledger reflete que aquele repasse **já foi consumido**, sem
     apagar histórico e sem dupla contagem.
3. **Relatório de neutralidade** (espelhando `scripts/etapa0_neutrality_report.py`): script que, sobre
   um clone de produção, compara **antes/depois**: (a) saldo de repasse por instituição = Σ repasse
   das operações − repasse já pago no CAP; (b) nenhum pagamento de CAP alterado; (c) total de
   deságio/tarifa no CAP inalterado; (d) receita do dashboard inalterada. Só sobe com o relatório
   **APROVADO**.

> **Pré-requisito de dados (rodar no clone de produção antes de decidir D1):** quantas linhas
> "Repasse não apropriado" existem, quantas estão **pagas**, e qual o saldo resultante. Isso
> dimensiona o risco real (o handoff sugere ~9 operações OPEN — volume pequeno, favorável).

---

## 11. Riscos

| # | Risco | Sev. | Mitigação |
|---|---|---|---|
| 1 | Repasse já **pago** no CAP + novo saldo no ledger = **dupla contagem** | **Alta** | Migração D1: preservar pago + DEBIT `ADJUSTMENT` compensatório; relatório de neutralidade obrigatório |
| 2 | `caixa` do Dashboard Financeiro **muda** (repasse sai dos custos) | Média | Decisão D2 com o financeiro; comunicar; validar que só o custo-repasse muda (receita/deságio/tarifa iguais) |
| 3 | Reverter/editar operação cujo **repasse já foi liquidado** | Média | Guarda no ledger análoga à guarda de pagamento (bloqueia revert com DEBIT ativo vinculado) |
| 4 | N:N: mesma NF em 2 operações LEPTA → 2 obrigações | Média | Grão = participação (`batch_item`), não NF; 1 linha por participação na tela |
| 5 | Liquidar com Saldo do Repasse **insuficiente** | Média | Guarda **por parcela**: só a soma `SALDO_REPASSE` é limitada ao saldo; demais origens completam a diferença. Ledger nunca negativo (D4) |
| 5b | **Sobre-liquidação** (Σ movimentações > obrigação) | Média | Guarda: Σ ativas ≤ `advanced_amount`; concorrência tratada com recomputo dentro da transação |
| 6 | Situação Vencida/Parcial depende de `today()` → não-determinismo/teste | Baixa | Derivar na leitura; congelar `date.today()` nos testes (padrão do projeto) |
| 7 | NF **RECEBIDA** (via Daycoval) ainda com obrigação LEPTA aberta confunde usuário | Baixa | É o objetivo do pedido; deixar explícito na UI que são eixos independentes |
| 8 | Estorno de liquidação/ledger reabrir obrigação | Baixa | `reversed_at` soft; situação recalculada exclui estornados |
| 9 | Migração não-idempotente ao rodar 2× | Baixa | Chaves `(source_type, source_batch_id/settlement_id)`; guard de existência |

---

## 12. Compatibilidade

- **Módulo de Notas Fiscais:** **zero** alteração. Sem status/campo/lógica nova. `invoice_status`
  continua derivado como hoje; RECEBIDA continua encerrando o ciclo da NF.
- **Operações existentes (OPEN/SETTLED/CANCELLED):** intactas. `repasse_amount` preservado.
- **Deságio/tarifa no CAP:** inalterados. Pagamentos existentes: intocados.
- **Fluxo criar/editar/cancelar:** inalterado, exceto o repasse migrar de CAP→ledger (transparente).
- **Dashboards/relatórios existentes:** inalterados, exceto o efeito esperado do repasse sair do CAP
  (§8/§9).
- Tudo reversível: `DROP TABLE`/`DROP TYPE` + reativar a linha de repasse no `on_confirm`.

---

## 13. Decisões (✅ = confirmadas pelo usuário) e pendências

| # | Decisão | Resolução |
|---|---|---|
| **D3** ✅ | Liquidação **parcial** e **multi-origem** | **CONFIRMADO:** modelo **1:N** (obrigação → movimentações) desde a v1. Parcialmente Liquidada → Liquidada quando Σ movimentações = valor da obrigação |
| **D4** ✅ | Saldo de repasse **insuficiente** | **CONFIRMADO:** bloquear **só** a parcela `SALDO_REPASSE` acima do saldo; completar a diferença com outra origem. Ledger nunca negativo; a liquidação **não** é impedida |
| **D6** ✅ | Grão da obrigação | **CONFIRMADO:** participação (`batch_item`), não NF — cobre N:N |
| **D1** ✅ | Repasse **pago** já no CAP na migração | **RESOLVIDO:** diagnóstico no dev acusou **0 linhas de repasse pagas** (6 ops, Σ 115.858,51, todas não pagas) → a migração `0106` remove as 6 do CAP e credita o Ledger; ramo "pago → preserva + ADJUSTMENT" fica no código por segurança/futuro. Neutralidade APROVADA (diff 0) |
| **D2** ⏳ | Dashboard Financeiro perde o custo-repasse (caixa sobe) | Recomendo aceitar (correto) — **validar o número com o financeiro** antes de subir |
| **D5** ⏳ | Conjunto final de **cards** | Começar com os do §7.2/§7.3; ajustar após ver dados reais |
| **D7** ⏳ | Perfis que geram obrigação | LEPTA sim; Daycoval não; Base configurável (flag no handler) — default proposto |
| **D6** | Grão da obrigação | **Participação (`batch_item`)**, não NF — cobre N:N |
| **D7** | Perfis que geram obrigação | LEPTA sim; Daycoval não; Base configurável (flag no handler) |

---

## 14. Plano de implementação em fases

**Fase 0 — Dados & decisão (sem código de produção)**
- Rodar no clone de produção o **diagnóstico do repasse no CAP** (contagem, pagos, saldo).
- Fechar **D1/D2** com o financeiro. (D3/D4/D6 já confirmados; D5/D7 = defaults.)

> **Princípio da divisão 1A/1B (redução de risco):** toda a **infraestrutura** é entregue e testada
> **sem alterar nenhum comportamento de produção** (Fase 1A). A **mudança de comportamento** (repasse
> deixa o CAP + migração de dados) só acontece depois, quando a infra já está pronta e verde (Fase 1B).

**Fase 1A — Infraestrutura (ZERO mudança de comportamento)** — ✅ **IMPLEMENTADA** (dev, dormant)
Nada do fluxo atual muda; **a LEPTA continua gerando Repasse no CAP** exatamente como hoje.

> Entregue: migration `0105` (aplicada no dev via `alembic upgrade head` no boot; tabelas vazias,
> dados existentes intactos — 9 operações), models (`advance_settlement_movement.py`,
> `advance_repasse_ledger.py`), `AdvanceRepasseLedgerService` + Port `RepasseLedgerPort` (independente),
> `AdvanceSettlementService` (fala só com a interface), schemas, 4 endpoints, testes
> `tests/test_advance_settlement_ledger.py` (9 verdes). `lepta.on_confirm`/`_revert_batch_effects`
> **NÃO** tocados (é 1B). "Perfis que geram obrigação" = constante provisória `{"LEPTA"}` no settlement
> service (migra p/ flag no handler na 1B).
- Migration `0105` — **apenas** tabelas novas (`advance_settlement_movements`,
  `advance_repasse_ledger`) + enums. **Sem backfill, sem tocar CAP/dados existentes.** Aditiva.
- Models (`advance_settlement_movement.py`, `advance_repasse_ledger.py`) + schemas (incl. os campos
  explícitos do §5.7: `valor_total`/`valor_liquidado`/`valor_residual`/`situacao`/`origens_resumo`).
- `AdvanceRepasseLedgerService` + `AdvanceSettlementService` (com totais/derivação no backend, §5.7).
- Capacidades **declaradas** nos handlers (`creates_settlement_obligation`, `has_repasse`) — porém
  **`lepta.on_confirm` NÃO é alterado** nesta fase (repasse segue no CAP; o ledger ainda não recebe
  crédito de operação real).
- Endpoints (settlements + ledger + kpis) + `_revert_batch_effects` **inalterado**.
- **Testes unitários + de banco** exercitam a infra de forma isolada (ledger semeado diretamente nos
  testes, já que ainda não há crédito automático): liquidação parcial e multi-origem (ex.: 30k
  Repasse + 20k Caixa + 50k Daycoval → Liquidada; só a parcela Repasse debita o ledger); totais
  explícitos e `origens_resumo` corretos; situação EM_ABERTO/PARCIALMENTE_LIQUIDADA/VENCIDA/LIQUIDADA
  + residual; guarda de **sobre-liquidação** (Σ ≤ obrigação); guarda de **saldo do repasse** (bloqueia
  só o excesso da parcela Repasse, completa por outra origem); N:N (2 obrigações); estorno de
  movimentação reabre residual/estorna DEBIT.
- **Resultado:** infra completa em produção, **dormant** — nenhum número existente muda.

**Fase 1B — Integração + migração + neutralidade** — ✅ **IMPLEMENTADA** (dev; neutralidade APROVADA)
Aqui o comportamento muda. **Três refinamentos do usuário incorporados** (ver abaixo).
- **Capability no handler (constante ELIMINADA):** `BaseOperationHandler.creates_settlement_obligation`
  / `has_repasse` (Lepta=True, Daycoval=False). O settlement resolve via
  `resolve_handler_class(profile).creates_settlement_obligation` — **`SETTLEMENT_OBLIGATION_PROFILES`
  removida do código**. Qualquer instituição entra no fluxo só ligando o flag no handler do seu perfil.
- `lepta.on_confirm`: **repasse deixa de gerar CAP** e passa a gerar **CREDIT no ledger**
  (`source_type=OPERATION`, `source_batch_id`). Deságio/tarifa **intactos** no CAP.
- **Reversão simétrica (criar→crédito / cancelar→estorno, sem resíduo):** `_revert_batch_effects`
  estorna o CREDIT do lote (`reverse_source(source_batch_id)`) e **bloqueia** cancelar/editar se o
  repasse já foi consumido em liquidação (guarda: saldo ficaria negativo). Teste dedicado do ciclo:
  `tests/test_advance_repasse_ledger_integration.py::test_cancel_reverses_credit_no_residue`.
- **Migração `0106`** (aditiva + reconciliável): backfill dos créditos das operações OPEN/SETTLED com
  repasse; **política D1** para o repasse já no CAP (não pago → remove; pago → preserva + DEBIT
  `ADJUSTMENT`). Diagnóstico no dev: 6 operações, Σ **115.858,51** (toda Lepta), **0 pagas** → remove
  as 6 linhas do CAP e credita o Ledger.
- **Relatório de neutralidade** `scripts/fase1b_repasse_neutrality_report.py` (detalhado: quantidade,
  valor total, por instituição, por competência, diferenças). **Resultado: APROVADO — diferença 0,00**
  em todos os cortes. Regra: 1B só concluída se diff = 0.
- **Testes (verdes):** ciclo criar→crédito→cancelar→estorno **sem resíduo**; editar re-credita; cancelar
  bloqueado com repasse consumido; **deságio/tarifa continuam no CAP** (repasse não); capability dirige
  a obrigação (sem constante). Regressão: 36 testes de antecipações passam (a única falha é ambiental —
  clone com pagamentos em 2026‑06 — fora do caminho da 1B).

**Fase 2 — Frontend** — ✅ **IMPLEMENTADA E VERIFICADA** (preview; sem regra de negócio no front)
- Filosofia (Custos Fixos/Cronograma/Componentes Variáveis): **o front só consome o contrato**; nada
  de recalcular situação/residual/liquidado/dias em atraso/origens/KPIs — tudo vem pronto (§5.7).
- Entregue: `services/advanceSettlements.ts` + `advanceRepasseLedger.ts` (só chamadas de API);
  abas Operações/Liquidação em `AdvanceBatches.tsx` (padrão Users.tsx); coluna Bruto→**Repasse
  Retido**; aba Liquidação em `components/AdvanceSettlementsTab.tsx` (cards = KPIs do backend, filtros
  client-side sobre o conjunto carregado, tabela com todos os valores do backend); modal Liquidar
  **multi-origem** (cada linha = movimentação; conferência VISUAL ao vivo; validação oficial no
  backend); `components/RepasseLedgerModal.tsx` (Extrato read-only: Entradas/Saídas + saldo, rótulos
  amigáveis — o usuário nunca vê Ledger/CAP). tsc limpo (0 erros); verificado no preview (cards,
  tabela, modal multi-origem, extrato) sem erros de console.
- Legado do texto original desta fase: abas Operações/Liquidação; coluna Bruto→Repasse Retido; cards
  e filtros; modal "Liquidar NF" (multi-origem); coluna **Origens** (`origens_resumo`) + totais prontos do backend (§5.7); extrato do
  Repasse (read-only + estornar). Serviços TS novos.

**Fase 3 — Gerencial, Auditoria & Timeline** — ✅ **IMPLEMENTADA E VERIFICADA** (foco em decisão)
Backend-driven, capability-driven (nunca regra fixa de LEPTA); tudo computado no backend.
- **Indicadores gerenciais** (`management_summary`, endpoint `/advance-settlements/management-summary`):
  valor ainda antecipado (Σ residual), vencido, a vencer 30d, **tempo médio antecipação→liquidação**
  (amount-weighted), liquidado com Repasse × outras origens, **distribuição das origens**.
- **Timeline append-only** (`obligation_timeline`, endpoint `/{batch_item_id}/timeline`): eventos
  derivados dos fatos — Antecipada → Venceu → Liquidação parcial → … → Liquidada / Estorno. Nunca
  recalcula; só ordena a história.
- **Históricos de auditoria** (endpoints): extrato completo do Repasse (`/advance-repasse-ledger`),
  histórico de liquidações de uma NF (`/history/invoice/{id}`), de um borderô (`/history/batch/{id}`).
  Sempre append-only.
- **Frontend** (`AdvanceSettlementsTab.tsx`): painel "Visão gerencial" (indicadores + barra de
  distribuição de origens); **timeline "Histórico da NF"** no modal (Antecipada → Venceu → …). Só
  consome o backend. tsc 0 erros; verificado no preview (painel + timeline) sem erro de console.
- **Preparação para o futuro:** nenhum indicador/tela assume LEPTA — a obrigação é dirigida por
  `creates_settlement_obligation` do handler do perfil (Daycoval fica de fora automaticamente).
- **Testes:** `tests/test_advance_settlement_management.py` (5 verdes: distribuição+tempo médio, a
  vencer 30d/vencido, timeline parcial→liquidada, capability exclui Daycoval, histórico da NF).

**Auditoria final — ✅ APROVADA** (`scripts/fase3_final_audit.py`, read-only, exit 0):
- **C1 Neutralidade financeira:** Σ créditos OPERATION == Σ repasse_amount (115.858,51), diff **0**.
- **C2 Integridade do Ledger:** saldo por instituição = Σcredit−Σdebit, **nunca negativo**.
- **C3 Integridade das liquidações:** sem sobre-liquidação (Σmov ≤ obrigação); cada `SALDO_REPASSE`
  ativa tem 1 DEBIT ativo casado (estornadas ⇒ DEBIT estornado).
- **C4 Ausência de dupla contagem:** 0 repasse não-pago no CAP; pago preservado == Σ ADJUSTMENT.
- **C5 Consistência de dashboards:** repasse pago no CAP == 0 (não vira custo); deságio/tarifa
  preservados (16 linhas).
- **C6 Consistência de indicadores:** liquidado_repasse+outras == total; Σ residual == ainda antecipado.

> **Total de testes do módulo:** 27 verdes (9 infra 1A + 6 integração 1B + 5 gerenciais 3 + 7 legados).
> Diferença financeira **zero** em todos os cortes. **Módulo encerrado.**

---

## Resumo dos arquivos previstos
- **Migration:** `alembic/versions/0105_advance_settlement_repasse_ledger.py` (aditiva).
- **Models:** `app/models/advance_settlement_movement.py`, `app/models/advance_repasse_ledger.py`.
- **Services:** `app/services/advance_settlement_service.py`,
  `app/services/advance_repasse_ledger_service.py`; edições em
  `advance_operations/{base,lepta,daycoval}.py` (capacidades) e
  `receivable_advance_batch_service.py` (`_revert_batch_effects`).
- **Router:** `app/modules/receivables/router.py` (endpoints novos).
- **Schemas:** `app/schemas/advance_settlement.py`, `app/schemas/advance_repasse_ledger.py`.
- **Frontend:** `AdvanceBatches.tsx` (abas + Operações), novo `Settlements`/`RepasseLedger`,
  `services/advanceSettlements.ts`, `services/advanceRepasseLedger.ts`.
- **Relatórios:** `schemas/reports.py`, `export/report_meta.py`, `operational_report_*`.
- **Scripts:** diagnóstico do repasse-CAP + relatório de neutralidade.
- **Notas Fiscais:** **nada.**
