"""Limpeza segura: remove Custos Fixos/Endividamento automáticos gerados indevidamente
antes da implantação (competência < JUL/2026).

A geração automática desses lançamentos no Contas a Pagar não retroage (o piso passa a
ser JUL/2026, aplicado no serviço). Esta migration limpa os resíduos já criados em
competências anteriores, de forma 100% segura:

Remove SOMENTE linhas que atendem TODAS as condições:
  - origin ∈ ('FIXED_COST', 'DEBT')  → gerados automaticamente pelo cadastro corporativo;
  - month < 2026-07-01;
  - amount_paid <= 0 E sem qualquer linha em payable_payments (nenhum pagamento, ativo ou
    estornado, jamais registrado).

NUNCA remove: lançamentos manuais (origin MANUAL), de projeto/colaborador
(origin PROJECT ou NULL), antecipações, nem qualquer linha com pagamento registrado.

Idempotente (rodar de novo não remove mais nada). `downgrade` é no-op: linhas removidas
não podem ser restauradas (limpeza de resíduo). Emite RAISE NOTICE com o total removido e
as competências afetadas (visível no log do deploy).

Revision ID: 0087_purge_pre_launch_company_finance_payables
Revises: 0086_endividamento_item_description
"""

from __future__ import annotations

from alembic import op

revision = "0087_purge_pre_launch_company_finance_payables"
down_revision = "0086_endividamento_item_description"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            removed_count integer;
            comp_list text;
        BEGIN
            -- Competências afetadas (contagem por mês) — apenas para o relatório do log.
            SELECT string_agg(t.line, ', ' ORDER BY t.line)
              INTO comp_list
              FROM (
                SELECT to_char(ps.month, 'YYYY-MM') || ' (' || count(*) || ')' AS line
                  FROM payable_snapshots ps
                 WHERE ps.month < DATE '2026-07-01'
                   AND ps.origin IN ('FIXED_COST', 'DEBT')
                   AND ps.amount_paid <= 0
                   AND NOT EXISTS (
                        SELECT 1 FROM payable_payments pp
                         WHERE pp.payable_snapshot_id = ps.id
                   )
                 GROUP BY to_char(ps.month, 'YYYY-MM')
              ) t;

            WITH del AS (
                DELETE FROM payable_snapshots ps
                 WHERE ps.month < DATE '2026-07-01'
                   AND ps.origin IN ('FIXED_COST', 'DEBT')
                   AND ps.amount_paid <= 0
                   AND NOT EXISTS (
                        SELECT 1 FROM payable_payments pp
                         WHERE pp.payable_snapshot_id = ps.id
                   )
                RETURNING 1
            )
            SELECT count(*) INTO removed_count FROM del;

            RAISE NOTICE 'purge pre-launch company_finance payables: removed=% competences=[%]',
                removed_count, COALESCE(comp_list, '(nenhuma)');
        END $$;
        """
    )


def downgrade() -> None:
    # Limpeza de resíduo — linhas removidas não são restauráveis. No-op intencional.
    pass
