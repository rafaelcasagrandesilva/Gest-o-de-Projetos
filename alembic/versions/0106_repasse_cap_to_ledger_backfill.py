"""Antecipações — Fase 1B: migração do Repasse do CAP para o Ledger. ADITIVA + reconciliável.

Muda o "onde" do Repasse SEM mudar o valor: o que estava no Contas a Pagar passa a viver no Ledger.

upgrade():
  1. BACKFILL: para cada operação confirmada (OPEN/SETTLED) com repasse (`repasse_enabled` e
     `repasse_amount > 0`) e instituição cadastrada, cria 1 CREDIT `OPERATION` no Ledger
     (`amount = repasse_amount`, `occurred_at = receive_date`). Idempotente por
     (source_type=OPERATION, source_batch_id) ativo.
  2. POLÍTICA D1 p/ o Repasse já PAGO no CAP (preserva histórico): para cada linha de repasse no CAP
     com pagamento (`amount_paid > 0`), mantém a linha e cria um DEBIT `ADJUSTMENT` de mesmo valor no
     Ledger (o repasse já foi consumido) — sem apagar histórico e sem dupla contagem no saldo.
  3. Remove do CAP as linhas de repasse NÃO pagas (o valor já está representado como crédito no
     Ledger). Deságio/tarifas permanecem intactos.

Diagnóstico no dev (clone de produção) na data desta migração: 6 operações com repasse (Σ
115.858,51), 6 linhas de repasse no CAP com o MESMO total, 0 pagas → a etapa (2) não dispara e a (3)
remove as 6 linhas. A neutralidade (scripts/fase1b_repasse_neutrality_report.py) deve acusar
diferença = 0 (Ledger == CAP anterior), por instituição e por competência.

Reconciliável: o downgrade recria as linhas de repasse no CAP e remove os lançamentos de operação do
Ledger (válido enquanto ainda não houver liquidações — janela de rollout da 1B).

Revision ID: 0106_repasse_cap_to_ledger_backfill
Revises: 0105_advance_settlement_repasse_ledger
"""

from __future__ import annotations

from alembic import op

revision = "0106_repasse_cap_to_ledger_backfill"
down_revision = "0105_advance_settlement_repasse_ledger"
branch_labels = None
depends_on = None

_REPASSE_LIKE = "Repasse%"


def upgrade() -> None:
    # 1. Backfill dos créditos de operação (idempotente).
    op.execute(
        """
        INSERT INTO advance_repasse_ledger
            (id, created_at, updated_at, institution_id, direction, amount, source_type,
             source_batch_id, source_movement_id, occurred_at, description, created_by_id)
        SELECT gen_random_uuid(), now(), now(), b.institution_id,
               'CREDIT'::repasse_ledger_direction, b.repasse_amount,
               'OPERATION'::repasse_ledger_source, b.id, NULL, b.receive_date,
               'Repasse retido — Operação SGC ' || b.sgc_number, NULL
        FROM receivable_advance_batches b
        WHERE b.status IN ('OPEN', 'SETTLED')
          AND b.repasse_enabled = true
          AND b.repasse_amount IS NOT NULL
          AND b.repasse_amount > 0
          AND b.institution_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM advance_repasse_ledger l
              WHERE l.source_batch_id = b.id
                AND l.source_type = 'OPERATION'::repasse_ledger_source
                AND l.reversed_at IS NULL
          )
        """
    )

    # 2. Repasse já PAGO no CAP → preserva a linha + DEBIT ADJUSTMENT compensatório (idempotente).
    op.execute(
        """
        INSERT INTO advance_repasse_ledger
            (id, created_at, updated_at, institution_id, direction, amount, source_type,
             source_batch_id, source_movement_id, occurred_at, description, created_by_id)
        SELECT gen_random_uuid(), now(), now(), b.institution_id,
               'DEBIT'::repasse_ledger_direction, ps.amount_paid,
               'ADJUSTMENT'::repasse_ledger_source, b.id, NULL, ps.month,
               'Repasse liquidado via CAP (legado) — SGC ' || b.sgc_number, NULL
        FROM payable_snapshots ps
        JOIN receivable_advance_batches b ON b.id = ps.ref_id
        WHERE ps.type = 'ANTECIPACAO_OPERACAO'
          AND ps.name LIKE 'Repasse%'
          AND ps.amount_paid > 0
          AND NOT EXISTS (
              SELECT 1 FROM advance_repasse_ledger l
              WHERE l.source_batch_id = b.id
                AND l.source_type = 'ADJUSTMENT'::repasse_ledger_source
                AND l.reversed_at IS NULL
          )
        """
    )

    # 3. Remove do CAP as linhas de repasse NÃO pagas (o valor virou crédito no Ledger).
    op.execute(
        """
        DELETE FROM payable_snapshots
        WHERE type = 'ANTECIPACAO_OPERACAO'
          AND name LIKE 'Repasse%'
          AND amount_paid = 0
        """
    )


def downgrade() -> None:
    # Recria as linhas de repasse no CAP para operações confirmadas com repasse que não têm mais
    # uma linha de repasse no CAP (espelha o formato de add_operation_payable_line da LEPTA).
    op.execute(
        """
        INSERT INTO payable_snapshots
            (id, created_at, updated_at, month, type, origin, ref_id, entry_id, project_id,
             name, category, cost_center, amount_original, amount_final, amount_paid,
             due_date, observation)
        SELECT gen_random_uuid(), now(), now(), date_trunc('month', b.receive_date)::date,
               'ANTECIPACAO_OPERACAO', 'ANTECIPACAO', b.id, NULL, NULL,
               'Repasse não apropriado • SGC ' || b.sgc_number,
               'Despesas financeiras', 'Financeiro', b.repasse_amount, b.repasse_amount, 0,
               b.receive_date,
               'Repasse não apropriado - Operação SGC ' || b.sgc_number
        FROM receivable_advance_batches b
        WHERE b.status IN ('OPEN', 'SETTLED')
          AND b.repasse_enabled = true
          AND b.repasse_amount IS NOT NULL
          AND b.repasse_amount > 0
          AND NOT EXISTS (
              SELECT 1 FROM payable_snapshots ps
              WHERE ps.ref_id = b.id AND ps.type = 'ANTECIPACAO_OPERACAO' AND ps.name LIKE 'Repasse%'
          )
        """
    )
    # Remove os lançamentos de operação do Ledger (válido na janela de rollout, sem liquidações).
    op.execute(
        """
        DELETE FROM advance_repasse_ledger
        WHERE source_type IN ('OPERATION'::repasse_ledger_source, 'ADJUSTMENT'::repasse_ledger_source)
        """
    )
