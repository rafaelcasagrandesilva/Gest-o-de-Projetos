"""Classificação EXIBIDA de um lançamento do Contas a Pagar — fonte ÚNICA de verdade.

Espelha exatamente a regra da tela do Contas a Pagar (frontend `Payables.tsx`:
`typeLabel` + `payableTipoLabel`). O relatório de fechamento da folha consome estas
funções em vez de ter uma regra própria: se a tela do CAP classifica uma linha como
"Colaborador", ela é folha; se surgir um novo tipo de folha amanhã, ambos os lugares
passam a considerá-lo sem alterar o relatório.

A classificação NÃO usa nome/descrição — apenas `type` (+ `category` para os lançamentos
de Custos Fixos gerados do cadastro, que a tela exibe pela categoria).
"""

from __future__ import annotations

from app.models.payable_snapshot import PayableSnapshotType

# Rótulo exibido por TIPO — idêntico a `typeLabel` do frontend.
PAYABLE_TYPE_LABELS: dict[str, str] = {
    PayableSnapshotType.COLLABORATOR.value: "Colaborador",
    PayableSnapshotType.VEHICLE.value: "Veículos",
    PayableSnapshotType.FIXED_COST.value: "Custo diverso",
    PayableSnapshotType.ENDIVIDAMENTO.value: "Endividamento",
    PayableSnapshotType.FINANCIAL.value: "Endividamento",
    PayableSnapshotType.ANTECIPACAO.value: "Antecipação",
    PayableSnapshotType.ANTECIPACAO_OPERACAO.value: "Antecipação",
    PayableSnapshotType.MANUAL.value: "Manual",
}

COLLABORATOR_GROUP = "Colaborador"
ENDIVIDAMENTO_GROUP = "Endividamento"

# Categorias de FIXED_COST que a tela exibe pela própria categoria (custos gerados do
# cadastro corporativo), em vez do rótulo do tipo — idêntico a `payableTipoLabel`.
_FIXED_COST_CATEGORY_AS_LABEL = ("Custo Fixo", "Colaborador")


def payable_display_group(*, type_: object, category: str | None) -> str:
    """Grupo EXIBIDO da linha no Contas a Pagar (o mesmo texto que aparece na coluna Tipo).

    FIXED_COST com categoria "Custo Fixo"/"Colaborador" aparece pela categoria; os demais
    pelo rótulo do tipo. Regra única — não interpretar nome/descrição.
    """
    type_value = getattr(type_, "value", type_)
    if (
        type_value == PayableSnapshotType.FIXED_COST.value
        and category in _FIXED_COST_CATEGORY_AS_LABEL
    ):
        return str(category)
    return PAYABLE_TYPE_LABELS.get(str(type_value), str(type_value))


def is_collaborator_payroll(*, type_: object, category: str | None) -> bool:
    """A linha é FOLHA do colaborador (a tela do CAP a exibe como "Colaborador")?"""
    return payable_display_group(type_=type_, category=category) == COLLABORATOR_GROUP


def is_employee_debt(*, type_: object, category: str | None) -> bool:
    """A linha é Endividamento (compõe o pagamento do colaborador, coluna própria)?"""
    return payable_display_group(type_=type_, category=category) == ENDIVIDAMENTO_GROUP
