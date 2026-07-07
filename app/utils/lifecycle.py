"""Regras compartilhadas do ciclo de vida dos cadastros mestres.

Padroniza mensagens e validações do par (is_active, start_date, end_date) usadas por
Colaboradores, Veículos e itens corporativos (Custos Fixos / Endividamento), evitando
duplicação e mantendo o texto exato exigido pelo produto.
"""

from __future__ import annotations

from datetime import date

# Mensagem exata exibida ao tentar excluir fisicamente um cadastro com movimentação.
DELETE_WITH_MOVEMENT_MSG = (
    "Este cadastro possui movimentações vinculadas e não pode ser excluído. "
    "Altere o status para Inativo."
)

# Mensagem exibida quando se inativa um cadastro sem informar a data de encerramento.
INACTIVE_REQUIRES_END_DATE_MSG = (
    "Informe a competência/data em que este cadastro deixou de ser utilizado. "
    "Um cadastro inativo exige a data de encerramento."
)


def normalize_lifecycle(
    *,
    is_active: bool,
    end_date: date | None,
) -> date | None:
    """Aplica a invariante do ciclo de vida e retorna o `end_date` efetivo.

    Regras (confirmadas com o produto):
    - Inativo (is_active=False) exige `end_date` — caso contrário levanta ValueError.
    - Ativo (is_active=True) NÃO possui encerramento: `end_date` é sempre limpo (None),
      de modo que reativar um cadastro reabre o ciclo de vida.
    """
    if is_active:
        return None
    if end_date is None:
        raise ValueError(INACTIVE_REQUIRES_END_DATE_MSG)
    return end_date
