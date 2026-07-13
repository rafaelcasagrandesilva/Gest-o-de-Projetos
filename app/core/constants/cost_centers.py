"""Centros de Custo Administrativos fixos — fonte única compartilhada.

Estes centros existem SEMPRE, independentemente de projetos. Ficam nesta constante (e não dentro
de um serviço) para poderem ser reutilizados por qualquer módulo sem duplicação: a lista oficial
de Centros de Custo é a UNIÃO destes fixos com os Centros de Custo dos projetos ATIVOS
(ver `app/services/cost_center_service.py`).

Ordem canônica preservada (é a ordem em que os administrativos aparecem nos combos).
"""

from __future__ import annotations

ADMIN_COST_CENTERS: tuple[str, ...] = (
    "Administrativo",
    "Financeiro",
    "Comercial",
    "Diretoria",
    "RH",
    "TI",
    "Almoxarifado",
)
