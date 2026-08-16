"""Relatório do Workspace Jurídico — monta o payload que replica cada MENU do módulo.

Reaproveita `LegalService` inteiro: os mesmos filtros, os mesmos agregados e a mesma noção de
"processo ativo". Assim o relatório nunca conta diferente da tela — se o Dashboard diz 146
processos e R$ 5,8 mi de passivo, o relatório imprime exatamente isso.

Uma aba por menu:
    Resumo      → os indicadores e as quebras do Dashboard (status, UF, empresa, projeto)
    Processos   → a tabela da tela de Processos
    Desligados  → a tabela da tela de Desligados

`include_*_sensitive` refletem `legal_cases.sensitive` / `legal_persons.sensitive`: sem a
permissão, o relatório sai SEM os valores daquele recurso (mesma regra da tela — o arquivo não
pode ser uma porta lateral para o passivo).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.legal_service import (
    STATUS_LABELS,
    TYPE_LABELS,
    CaseFilters,
    LegalService,
    PersonFilters,
)


def _money(value: float | None, *, include: bool) -> float | None:
    """Valor monetário do relatório: `None` quando o usuário não pode vê-lo (célula fica vazia)."""
    if not include:
        return None
    return float(value or 0.0)


class LegalReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.legal = LegalService(session)

    async def generate(
        self,
        *,
        filters: CaseFilters,
        include_cases_sensitive: bool,
        include_persons_sensitive: bool,
    ) -> dict[str, Any]:
        overview = await self.legal.overview(filters)
        cases = await self.legal.list_cases(filters)

        # Desligados no MESMO recorte. Regra ÚNICA, para o arquivo inteiro falar da mesma fatia:
        #
        #     aba Desligados = quem aparece nos processos desta fatia
        #                      ∪ quem não tem processo e casa com os filtros de pessoa
        #
        # Sem isso os números brigariam entre si: filtrando por empresa, o KPI contaria 52 pessoas
        # (as dos processos daquela empresa) enquanto a aba listaria 46 (as cujo CADASTRO tem
        # aquela empresa) — e o leitor não saberia qual vale. A segunda parte da união preserva os
        # desligados sem processo, que são justamente o que o menu Desligados acrescenta.
        person_filters = PersonFilters(
            companies=filters.companies,
            projects=filters.projects,
            clients=filters.clients,
            q=filters.q,
            include_inactive=filters.include_inactive,
        )
        candidates = await self.legal.list_persons(person_filters)
        in_scope = {c.person_id for c in cases if c.person_id is not None}
        by_id = {p.id: (p, t) for p, t in candidates}

        # Filtro que só faz sentido para PROCESSO (status/UF/tipo/faixa de valor): aí a pergunta é
        # sobre o contencioso, e quem não tem processo não pertence à resposta. Com filtros de
        # pessoa (empresa/projeto/busca) — ou sem filtro — os sem processo continuam listados,
        # porque é justamente o que o menu Desligados acrescenta ao de Processos.
        case_only_filter = bool(filters.statuses or filters.types or filters.ufs or filters.person_id) or (
            filters.value_min is not None or filters.value_max is not None
        )
        people = [
            (p, t)
            for p, t in candidates
            if p.id in in_scope or (t["case_count"] == 0 and not case_only_filter)
        ]
        # Pessoa que está nos processos da fatia mas não passou no filtro de pessoa (o cadastro dela
        # tem outra empresa, por exemplo) entra mesmo assim — ela pertence a esta fatia.
        missing = in_scope - set(by_id)
        if missing:
            for p, t in await self.legal.list_persons(
                PersonFilters(include_inactive=filters.include_inactive)
            ):
                if p.id in missing:
                    people.append((p, t))
            people.sort(key=lambda pair: pair[0].full_name)

        k = overview.kpis
        resumo: list[dict[str, Any]] = [
            {"indicador": "Processos", "quantidade": k.case_count, "valor": None},
            {"indicador": "Desligados com processo", "quantidade": k.person_count, "valor": None},
            {
                "indicador": "Passivo considerado",
                "quantidade": None,
                "valor": _money(k.total_considered, include=include_cases_sensitive),
            },
            {
                "indicador": "Valor da causa (bruto)",
                "quantidade": None,
                "valor": _money(k.total_claimed, include=include_cases_sensitive),
            },
            {
                "indicador": "Valor acordado",
                "quantidade": None,
                "valor": _money(k.total_agreed, include=include_cases_sensitive),
            },
            {
                "indicador": "Valor pago",
                "quantidade": None,
                "valor": _money(k.total_paid, include=include_cases_sensitive),
            },
            {
                "indicador": "Valor pendente",
                "quantidade": None,
                "valor": _money(k.total_pending, include=include_cases_sensitive),
            },
        ]

        def breakdown(titulo: str, buckets) -> list[dict[str, Any]]:
            return [
                {
                    "grupo": titulo,
                    "item": b.label,
                    "quantidade": b.count,
                    "valor": _money(b.value, include=include_cases_sensitive),
                }
                for b in buckets
            ]

        quebras = (
            breakdown("Status", overview.by_status)
            + breakdown("Estado", overview.by_uf)
            + breakdown("Tipo", overview.by_type)
            + breakdown("Empresa", overview.by_company)
            + breakdown("Projeto", overview.by_project)
        )

        processos = [
            {
                "processo": c.case_number,
                "situacao_cadastro": "Ativo" if c.is_active else "Inativo",
                "nome": (c.person.full_name if c.person else None) or c.claimant_name,
                "cpf": c.person.cpf if c.person else None,
                "empresa": c.company,
                "projeto": c.project,
                "cliente": c.client,
                "uf": c.uf,
                "foro": c.court,
                "comarca": c.city,
                "tipo": TYPE_LABELS.get(
                    getattr(c.case_type, "value", str(c.case_type)), str(c.case_type)
                ),
                "status": STATUS_LABELS.get(
                    getattr(c.status, "value", str(c.status)), str(c.status)
                ),
                "classe": c.nature,
                "reclamante": c.claimant_name,
                "reclamado": c.defendant_name,
                "valor_causa": _money(c.amount_claimed, include=include_cases_sensitive),
                "valor_considerado": _money(c.amount_considered, include=include_cases_sensitive),
                "valor_acordado": _money(c.amount_agreed, include=include_cases_sensitive),
                "valor_pago": _money(c.amount_paid, include=include_cases_sensitive),
                "valor_pendente": _money(c.amount_pending, include=include_cases_sensitive),
                "condicoes_acordo": c.agreement_terms if include_cases_sensitive else None,
                "ultima_movimentacao": c.last_movement,
                "data_movimentacao": c.last_movement_date,
                "audiencia": c.hearing_date,
                "distribuicao": c.distribution_date,
                "jusbrasil": c.jusbrasil_url,
                "observacoes": c.notes,
            }
            for c in cases
        ]

        desligados = [
            {
                "nome": p.full_name,
                "cpf": p.cpf,
                "situacao_cadastro": "Ativo" if p.is_active else "Inativo",
                "empresa": p.company,
                "projeto": p.project,
                "cliente": p.client,
                "cargo": p.role,
                "admissao": p.admission_date,
                "desligamento": p.termination_date,
                "qtd_processos": t["case_count"],
                "valor_causa_total": _money(t["total_claimed"], include=include_cases_sensitive),
                "valor_considerado_total": _money(
                    t["total_considered"], include=include_cases_sensitive
                ),
                "valor_acordado_total": _money(t["total_agreed"], include=include_cases_sensitive),
                "valor_pago_total": _money(t["total_paid"], include=include_cases_sensitive),
                "valor_pendente_total": _money(t["total_pending"], include=include_cases_sensitive),
                "rescisao": _money(p.severance_amount, include=include_persons_sensitive),
                "fgts": _money(p.fgts_balance, include=include_persons_sensitive),
                "observacoes": p.notes,
            }
            for p, t in people
        ]

        return {
            "resumo": resumo,
            "quebras": quebras,
            "processos": processos,
            "desligados": desligados,
        }
