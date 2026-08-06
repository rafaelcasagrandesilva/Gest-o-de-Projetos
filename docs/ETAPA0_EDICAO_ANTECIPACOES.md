# Etapa 0 — Antecipações: remover "Confirmar" + permitir Editar operação

**Objetivo:** simplificar o dia a dia do Borderô. Hoje o fluxo é **criar → Confirmar → (só) Cancelar**.
Passa a ser **criar (já ativo) → Editar (corrigir) / Cancelar**. Elimina o passo de Confirmar
(redundante na prática) e permite corrigir a base de uma NF (ou qualquer dado) sem recriar tudo.

> Status: **IMPLEMENTADO (Fases 1–3)** no ambiente de teste, aguardando validação do usuário.
> Backend: `_revert_batch_effects` (compartilhado cancel/edit), `create` atômico (create+confirm no
> router), `edit_batch` + `PUT /advance-batches/{id}`. Frontend: `editAdvanceBatch`, modo edição no
> modal (form pré-preenchido), botão "Editar" no detalhe, "Confirmar" removido. Testes:
> tests/test_advance_batch_edit.py (4 verdes). Sem migration.

---

## 0. Descoberta-chave (por que é de baixo risco)

A infraestrutura de efeitos já é **reversível e por perfil de instituição**:

- Os efeitos financeiros vivem em **handlers** (`advance_operations/`: base, Lepta, Daycoval) nos
  ganchos `on_confirm` (aplica: congela antecipado, calcula repasse, marca NFs ANTECIPADA, gera
  deságio/tarifa/repasse no CAP, invalida meses) e `on_cancel` (reversões específicas do perfil).
- `create_batch` cria em **DRAFT** e **não aplica nada**; `confirm_batch` (DRAFT→OPEN) aplica via
  `on_confirm`; `cancel_batch` reverte tudo (apaga CAP do lote se não houver pagamento, recompõe o
  estado das NFs via `_recompute_invoice_advance_state`, invalida meses) e marca **CANCELLED**.
- Produção hoje: **0 rascunhos** (9 OPEN + 1 CANCELLED) — ninguém usa DRAFT como staging; criar e
  confirmar sempre andam juntos. Logo, remover o "Confirmar" não abandona nenhum dado.

**Conclusão:** "Editar" = **reverter → alterar → reaplicar**, reusando `on_cancel`/`on_confirm`. Toda
a regra por instituição é respeitada de graça, sem `if instituição == X`.

---

## 1. Arquitetura proposta

### 1.1 Criar já nasce ATIVO (sem "Confirmar")
O endpoint de criação passa a fazer **create_batch + confirm_batch numa única transação** → a
operação nasce **Em aberto (OPEN)**, com efeitos aplicados. O estado interno DRAFT/OPEN **permanece**
(é o mecanismo de reverter/aplicar); só a UX deixa de expor o botão Confirmar.

### 1.2 Editar (OPEN → editar → OPEN)
Novo serviço `edit_batch(batch_id, novos_dados)` numa **única transação**:
1. **Guarda:** operação está OPEN (não SETTLED) e **sem pagamento** em suas despesas de CAP.
2. **Reverte** os efeitos (mesma reversão do Cancelar, porém status → **DRAFT** e **mantém** o lote/itens).
3. **Aplica** os novos dados (rebuild dos itens/totais via `prepare_draft` do handler — base por NF,
   deságio/tarifa/repasse, datas, instituição, NFs incluídas).
4. **Reaplica** os efeitos (`on_confirm`) → volta a OPEN.

Se qualquer passo falhar, a transação faz rollback e a operação continua exatamente como estava.

### 1.3 Refactor de reuso (chave para consistência)
Extrair um helper **`_revert_batch_effects(batch)`** com o miolo hoje dentro de `cancel_batch`
(on_cancel + apagar CAP com guarda-de-pagamento + `_recompute` das NFs + invalidar meses). Passa a
ser usado por **ambos**: `cancel_batch` (finaliza em CANCELLED) e `edit_batch` (finaliza em DRAFT e
reaplica). Um só caminho de reversão = zero divergência.

---

## 2. Impacto no banco
**Nenhum.** Os estados (DRAFT/OPEN/SETTLED/CANCELLED) já existem; a mudança é de **fluxo + serviço +
UI**. Sem colunas novas, sem alteração de tipos.

## 3. Migrations necessárias
**Nenhuma.** (Confirmado: 0 rascunhos em produção; nada a converter.)

## 4. Compatibilidade com dados atuais
- Operações **OPEN/CANCELLED** existentes: intactas.
- **Cancelar** e **Excluir definitivamente**: **inalterados**.
- A única mudança de comportamento é o **momento** dos efeitos: passam a ocorrer na **criação**
  (antes, no Confirmar). Como criar+confirmar já eram sequenciais na prática, o efeito líquido para o
  usuário é o mesmo, com um clique a menos.

## 5. Impacto no fluxo de criação/confirmação
- `POST /advance-batches` passa a retornar a operação **já OPEN** (create+confirm atômico).
- `POST /advance-batches/{id}/confirm` torna-se **obsoleto** (pode ser mantido como no-op/compat por
  um tempo, ou removido — decisão de rollout).
- Novo `PUT /advance-batches/{id}` (editar) e o serviço `edit_batch`.

## 6. Impacto no CAP e no estado das NFs
- Editar **apaga e recria** os títulos de deságio/tarifa/repasse do lote (via revert→reaplica). Como
  a edição é **bloqueada quando há pagamento**, nunca se perde histórico financeiro.
- O estado das NFs é sempre **rederivado** (`_recompute_invoice_advance_state`) a partir das operações
  CONFIRMADAS — igual ao Cancelar. Durante a edição, a operação fica transitoriamente DRAFT (fora do
  agregado), então uma NF que também esteja em OUTRA operação válida permanece ANTECIPADA por ela.

## 7. Impacto no N:N e no histórico
- **N:N (1 NF → N operações):** preservado. A reversão/reaplicação usa o mesmo `_recompute` já
  validado; editar a operação A não corrompe o vínculo da NF com a operação B.
- **Histórico de pagamento:** intocável — a guarda "sem pagamento" impede editar/reverter operações
  cujas despesas já foram pagas (mesma trava que o Cancelar já aplica hoje).

## 8. Riscos
| # | Risco | Sev. | Mitigação |
|---|---|---|---|
| 1 | Editar operação com despesa **paga** corromper histórico | Alta | Guarda "sem pagamento" (reusa a checagem do cancel); bloqueia edição → só Cancelar |
| 2 | Estado N:N inconsistente no meio da edição | Média | Transação única; reversão e reaplicação usam `_recompute` (deriva das confirmadas) |
| 3 | Refactor de `cancel_batch` introduzir regressão | Média | Extrair `_revert_batch_effects` com testes cobrindo cancel **antes** de reusar em edit |
| 4 | Efeitos passam a ocorrer na criação (mudança de timing) | Baixa | É o objetivo; validar que criar+confirmar atômico == comportamento atual |
| 5 | Edição de **quais NFs** compõem a operação (add/remove) reabrir elegibilidade | Média | Revalidar elegibilidade na reaplicação; NF removida volta a elegível via `_recompute` |
| 6 | `SETTLED` (liquidada) não pode ser editada | Baixa | Guarda permite editar só OPEN |

## 9. Estratégia de migração
- **Aditiva e reversível:** adiciona `edit_batch` + compõe create+confirm; mantém cancel/delete.
- Sem migration, sem recomputo de dados existentes.
- O endpoint `/confirm` pode virar no-op de compatibilidade na primeira fase e ser removido depois.

## 10. Plano de implementação em fases

**Fase 1 — Backend**
- Extrair `_revert_batch_effects(batch)` (com testes de regressão do `cancel_batch`).
- `create` passa a create+confirm atômico; `/confirm` vira no-op/compat.
- `edit_batch(batch_id, dados)`: guarda → revert(→DRAFT) → prepare_draft(novos dados) → on_confirm.
- Endpoint `PUT /advance-batches/{id}`.
- ✅ Testes: criar (já OPEN); editar base de uma NF → deságio/tarifa/repasse recalculados e CAP
  atualizado; editar bloqueado quando há pagamento; N:N preservado (NF em 2 operações).

**Fase 2 — Frontend**
- "Nova antecipação" cria **direto como ativa** (remove o passo Confirmar).
- Botão **"Editar"** na operação (reusa o modal de criação, pré-preenchido).
- Desabilitar Editar quando houver pagamento (mostrar motivo) — só Cancelar nesse caso.

**Fase 3 — Verificação e2e**
- Restaurar produção no teste e exercitar: criar → editar base → conferir CAP/NF → cancelar.

---

## Resumo dos arquivos previstos
- **Serviço:** `app/services/receivable_advance_batch_service.py` (`_revert_batch_effects`,
  `edit_batch`, create atômico).
- **Handlers:** `advance_operations/*` — sem mudança (reusados via on_confirm/on_cancel).
- **Router:** `app/modules/receivables/router.py` (create já confirma; novo `PUT`; `/confirm` compat).
- **Frontend:** `AdvanceBatches.tsx`, `AdvanceBatchModal.tsx` (remove Confirmar; adiciona Editar).
- **Sem migration.**
