"""Operações de antecipação: renumeração do SGC em ordem cronológica.

A numeração do SGC é alocada como "maior número existente + 1" (regra que
CONTINUA valendo — ver `_allocate_sgc_number`). Isso produz uma sequência
cronológica enquanto as operações são lançadas na ordem em que acontecem; mas as
operações da Lepta foram lançadas primeiro e as do Banco Daycoval depois, todas
retroativas, e a numeração deixou de acompanhar a data de recebimento.

Esta migration reordena UMA VEZ os números existentes por data de recebimento
(empate → ordem de criação → id, determinístico), deixando 1..N contíguo. Depois
dela o alocador segue automático a partir do novo maior número, e os números
atribuídos não mudam mais.

O número do SGC está COPIADO em texto em dois lugares, ambos ligados à operação
por chave estrangeira — por isso são reescritos aqui, na mesma transação, a
partir do vínculo (nunca por casamento de texto solto):
  - `payable_snapshots.name` / `.observation` — "Deságio • SGC 7", "Tarifas • SGC 7"
    e os nomes completos (ref_id = batch.id);
  - `advance_repasse_ledger.description` — "Repasse retido — Operação SGC 7"
    (source_batch_id = batch.id).
Nada mais no banco guarda o número: verificado varrendo TODAS as colunas de texto
do schema. `batch_number` (BT-AAAA-N) e `operation_code` (número da instituição)
são identificadores independentes e não são tocados.

Revision ID: 0126_advance_sgc_renumber_chronological
Revises: 0125_payment_component_attachments
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0126_advance_sgc_renumber_chronological"
down_revision = "0125_payment_component_attachments"
branch_labels = None
depends_on = None

# Ordem oficial da renumeração. Usada no cálculo e na conferência final.
_ORDER = "receive_date ASC, created_at ASC, id ASC"


def upgrade() -> None:
    bind = op.get_bind()

    # Mapa antigo→novo, calculado ANTES de qualquer escrita: serve para reescrever os
    # textos e para deixar o de-para no log do deploy (é o registro de como voltar).
    mapping = list(
        bind.execute(
            sa.text(
                f"""
                SELECT id, sgc_number AS antigo,
                       ROW_NUMBER() OVER (ORDER BY {_ORDER}) AS novo
                FROM receivable_advance_batches
                """
            )
        )
    )
    if not mapping:
        return

    mudam = [row for row in mapping if int(row.antigo) != int(row.novo)]
    print(f"[0126] Renumeração do SGC: {len(mapping)} operações, {len(mudam)} mudam de número.")
    for row in mudam:
        print(f"[0126]   SGC {row.antigo} -> SGC {row.novo}")

    # `sgc_number` é UNIQUE, então a permutação não cabe em um UPDATE só: qualquer
    # ordem de linhas colidiria no meio do caminho. O desvio pelos negativos esvazia
    # a faixa positiva antes de reatribuí-la (os negativos são únicos entre si porque
    # os originais são).
    op.execute("UPDATE receivable_advance_batches SET sgc_number = -sgc_number")
    op.execute(
        f"""
        WITH ordenado AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY {_ORDER}) AS seq
            FROM receivable_advance_batches
        )
        UPDATE receivable_advance_batches AS b
        SET sgc_number = ordenado.seq
        FROM ordenado
        WHERE b.id = ordenado.id
        """
    )

    # Textos que carregam o número, reescritos A PARTIR DO VÍNCULO com a operação.
    # O regexp troca só o número que segue "SGC", preservando o resto do rótulo
    # ("Deságio • SGC 7" e "Tarifas bancárias - Operação SGC 7" seguem a mesma regra).
    op.execute(
        """
        UPDATE payable_snapshots AS p
        SET name = regexp_replace(p.name, 'SGC [0-9]+', 'SGC ' || b.sgc_number, 'g'),
            observation = regexp_replace(
                COALESCE(p.observation, ''), 'SGC [0-9]+', 'SGC ' || b.sgc_number, 'g'
            )
        FROM receivable_advance_batches AS b
        WHERE p.ref_id = b.id
          AND (p.name ~ 'SGC [0-9]' OR COALESCE(p.observation, '') ~ 'SGC [0-9]')
        """
    )
    op.execute(
        """
        UPDATE advance_repasse_ledger AS l
        SET description = regexp_replace(l.description, 'SGC [0-9]+', 'SGC ' || b.sgc_number, 'g')
        FROM receivable_advance_batches AS b
        WHERE l.source_batch_id = b.id
          AND l.description ~ 'SGC [0-9]'
        """
    )

    # Conferência: a sequência tem que ter ficado 1..N contígua e na ordem oficial.
    # Se não ficou, algo mudou o schema por baixo — melhor abortar o deploy do que
    # publicar identificadores duplicados ou fora de ordem.
    total, maximo, distintos = bind.execute(
        sa.text(
            "SELECT COUNT(*), MAX(sgc_number), COUNT(DISTINCT sgc_number) FROM receivable_advance_batches"
        )
    ).one()
    if not (total == maximo == distintos):
        raise RuntimeError(
            f"[0126] Renumeração inconsistente: {total} operações, maior número {maximo}, "
            f"{distintos} números distintos — esperado os três iguais."
        )

    fora_de_ordem = bind.execute(
        sa.text(
            f"""
            SELECT COUNT(*) FROM (
                SELECT sgc_number, ROW_NUMBER() OVER (ORDER BY {_ORDER}) AS esperado
                FROM receivable_advance_batches
            ) t WHERE t.sgc_number <> t.esperado
            """
        )
    ).scalar_one()
    if fora_de_ordem:
        raise RuntimeError(f"[0126] {fora_de_ordem} operação(ões) ficaram fora da ordem cronológica.")

    # Restam textos com número de SGC sem vínculo com operação? Não dá para corrigi-los
    # com segurança (não se sabe a qual operação pertencem); avisa em vez de abortar.
    orfaos = bind.execute(
        sa.text(
            """
            SELECT (SELECT COUNT(*) FROM payable_snapshots
                    WHERE name ~ 'SGC [0-9]' AND ref_id IS NULL)
                 + (SELECT COUNT(*) FROM advance_repasse_ledger
                    WHERE description ~ 'SGC [0-9]' AND source_batch_id IS NULL)
            """
        )
    ).scalar_one()
    if orfaos:
        print(f"[0126] ATENÇÃO: {orfaos} texto(s) com número de SGC sem vínculo — conferir à mão.")

    print(f"[0126] Concluído: SGC 1..{maximo} em ordem de data de recebimento.")


def downgrade() -> None:
    # Sem volta automática: a numeração anterior não era derivável de nenhum dado
    # (tinha buracos de operações excluídas), então recalcular NÃO reproduziria os
    # números antigos — daria uma terceira numeração, pior que as duas. O de-para
    # completo fica impresso no log do deploy, e o caminho de reversão de verdade é o
    # backup tirado antes de publicar (ver docs/PUBLICAR_EM_PRODUCAO.md, Parte 1).
    raise NotImplementedError(
        "0126 não tem downgrade: restaure o backup anterior à publicação. "
        "O de-para antigo→novo está no log do deploy."
    )
