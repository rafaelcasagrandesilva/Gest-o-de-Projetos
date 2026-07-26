# Custos Fixos — Múltiplos Lançamentos por Competência

Documentação técnica e handoff. Permite **N lançamentos na mesma competência** para
qualquer item de Custo Fixo (genérico — sem regra por fornecedor). Cada lançamento vira um
**título independente** no Contas a Pagar (CAP), com pagamento próprio; a tela de Custos Fixos
continua exibindo apenas a **soma** do mês.

## Princípio arquitetural — Fonte Única de Verdade

```
Cadastro (CompanyFinancialItem)
   └─ N lançamentos (company_financial_payments)   ← vencimento + valor + descrição livre
        └─ Reconciliador (pipeline de geração/sync do CAP)
             └─ PayableSnapshot (1 título por lançamento, via entry_id)
                  └─ Consumidores: Contas a Pagar, Relatórios, Dashboards, Exportações
```

- Toda a lógica de múltiplos lançamentos está **encapsulada no pipeline de geração/sincronização
  do CAP** (`_reconcile_company_finance_entries_for_month`). Para os consumidores, os títulos são
  apenas linhas independentes — a mudança é transparente (muda só a granularidade).
- **Nenhum consumidor lê diretamente os lançamentos da grade.** O modal também não altera
  `PayableSnapshot` direto: `replace_entries()` → pipeline → snapshot.
- `Σ(lançamentos) == Σ(títulos do CAP) == valor exibido na grade == Σ(relatórios)`.

## Modelo de dados

- `company_financial_payments` (mal-nomeada por herança — cada linha é um **lançamento**, não um
  pagamento): perdeu `UniqueConstraint(item_id, competencia)`; ganhou `due_date` e `descricao`
  (texto livre; coluna `VARCHAR(255)`, UI limita a 150). Sem coluna de sequência (ordena por
  `due_date` → `created_at`).
- `payable_snapshots.entry_id` (FK → `company_financial_payments.id`, `ON DELETE SET NULL`): chave
  1:1 do título com o lançamento. `ref_id` continua apontando para o **item** (metadados/centro/
  exclusão por item). `entry_id` entrou na `uq_payable_snapshot_identity`.
- Migrations: `0101_fixed_cost_multi_entries`, `0102_payable_snapshot_entry_id` (ambas aditivas e
  reversíveis; backfill preserva vínculos e vencimentos existentes).

## Descrição = subtítulo oficial (padronização)

A descrição do lançamento acompanha o título em todo o fluxo, no MESMO padrão do Endividamento e
dos Componentes Variáveis:

- **CAP (tela)**: subtítulo cinza abaixo do nome (`PayableSnapshot.item_description`; render já
  existente em `Payables.tsx`, truncado com reticências — valor completo preservado no banco).
- **Relatório do CAP (XLSX/PDF)**: coluna **Observações** (`payables_detailed`) preenchida com a
  descrição.
- **Grade de Custos Fixos**: NÃO exibe descrição (só a soma do mês + indicador "(N)").

No reconciliador, `item_description` da linha = `entry.descricao` (fallback ao `item_description`
do item — descrição da dívida no Endividamento; `None` em Custos Fixos). A edição do cadastro
(`sync_company_finance_item_metadata`) **preserva** a descrição por lançamento.

## Backend — pontos-chave

- `app/services/payable_snapshot_service.py`
  - `_reconcile_company_finance_entries_for_month(...)`: reconciliador único (materializa 1
    lançamento de referência quando vazio/elegível/acima do piso; adota título legado sem vínculo;
    cria/atualiza título por lançamento; guarda de pagamento). Geração e
    `sync_company_finance_item_months` delegam a ele.
  - `origin_is_missing(...)`: título FIXED_COST/DEBT vinculado é órfão quando o lançamento
    (`entry_id`) some; legado sem vínculo (`entry_id NULL`) segue regido pela existência do item.
- `app/services/company_finance_service.py`
  - `replace_entries(item_id, competencia, lancamentos)`: caminho canônico do modal (cria/edita/
    exclui lançamentos; bloqueia pagos; sincroniza o CAP).
  - `list_entries(...)`: leitura dos lançamentos + status de pagamento (espelho do CAP).
  - `replace_payments(...)`: grade legada — virou **UPSERT in-place** (não recria a linha; preserva
    o `entry_id`). Ignora meses com N>1 (geridos no modal).
  - `_item_to_read`: `pagamentos` agregado por mês (soma) com `count`; `pago_mes` = soma.
- Endpoints: `GET`/`PUT /company-finance/items/{id}/entries`.

## Frontend — pontos-chave

- `components/company-finance/LancamentosCompetenciaModal.tsx`: componente **genérico e
  reutilizável** ("Lançamentos da Competência"). Só exibe/edita a coleção (vencimento, valor,
  descrição opcional, remover, +adicionar, **total no rodapé**). Nenhuma regra de negócio dentro;
  lançamentos pagos vêm bloqueados; redação sensível desabilita a edição.
- Indicador discreto "(N)" **só quando há mais de um lançamento**:
  - Grade de 12 meses (Visão Executiva): rótulo do mês clicável abre o modal; N>1 vira célula
    read-only = soma + badge; 0/1 mantém input inline (experiência idêntica à atual).
  - Extrato Analítico: célula "Valor Mensal" clicável + badge "(N)".
- **Endividamento permanece inalterado** (modal restrito a `custo_fixo`).

## Validação executada

- Migrations aplicadas + validação pré/pós + round-trip reversível.
- Suíte: 252 passam; 1 falha **ambiental pré-existente** (`test_advance_batch_payables` regenerate —
  dado real pago em 2026-06 no banco local; falha idêntica sem estas alterações).
- Regressão permanente: `tests/test_fixed_cost_multi_entries.py` (1 lançamento idêntico ao anterior;
  N no CAP + consolidado na grade + Observações; exclusão/pagamento por lançamento; descrição
  preservada na edição do cadastro).
- Invariantes conferidos: `Σ(CAP)==Σ(Relatório)==3950`; descrição como subtítulo no CAP e em
  Observações; 1 lançamento = comportamento anterior; N aparece individual no CAP e somado na grade.
- Frontend: `tsc -b` e `check:currency` limpos; bundle carrega sem erro de console.

## Riscos residuais

- **Títulos legados órfãos** (`entry_id NULL`, sem lançamento — históricos gerados só da referência):
  seguem funcionando pela lógica por-item (não são auto-curados ao apenas visualizar, para evitar
  mudança surpresa em meses fechados). Se, no futuro, quiser que apareçam no modal de meses
  históricos, fazer um backfill pontual que materialize um lançamento espelho por título.
- **Validação ao vivo autenticada** do fluxo no browser não foi executada (login exige senha, não
  inserida por política). Verificado em todas as demais camadas (serviço, serialização, endpoints,
  bundle).
- **Numeração de migration**: `0101/0102` foram tomadas por esta feature; a docstring da `0100`
  mencionava um `0101` (dados de `project_labors.cost_pj_additional_cost`) nunca criado — se surgir,
  renumerar.
