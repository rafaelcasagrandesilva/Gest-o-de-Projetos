"""Payables: classify debt snapshots as ENDIVIDAMENTO.

Revision ID: 0048_payable_snapshot_type_endividamento
Revises: 0047_workspace_permissions
Create Date: 2026-05-19

"""

from __future__ import annotations

from alembic import op


revision = "0048_payable_snapshot_type_endividamento"
down_revision = "0047_workspace_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL requires the new enum value to be committed before it can be used in UPDATEs.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE payable_snapshot_type ADD VALUE IF NOT EXISTS 'ENDIVIDAMENTO'")

    op.execute(
        """
        UPDATE payable_snapshots
           SET type = 'ENDIVIDAMENTO'
         WHERE type = 'FINANCIAL'
        """
    )
    op.execute(
        """
        UPDATE payable_snapshots ps
           SET type = 'ENDIVIDAMENTO',
               category = 'Endividamento',
               cost_center = 'Financeiro'
          FROM company_financial_items cfi
         WHERE ps.ref_id = cfi.id
           AND cfi.tipo = 'endividamento'
           AND ps.type = 'MANUAL'
        """
    )


def downgrade() -> None:
    # Keep the enum value; removing PostgreSQL enum values requires recreating the type.
    op.execute(
        """
        UPDATE payable_snapshots
           SET type = 'FINANCIAL'
         WHERE type = 'ENDIVIDAMENTO'
        """
    )
