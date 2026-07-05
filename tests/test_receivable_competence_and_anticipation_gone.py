"""Testes da competência da NF e da descontinuação das antecipações individuais.

- Competência é obrigatória na criação e normalizada para o primeiro-de-mês;
- Competência é opcional na edição (registros antigos permanecem NULL);
- Os endpoints de antecipação individual da NF respondem 410 Gone.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import date
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.receivables.router import (
    _ANTICIPATION_DISCONTINUED_MSG,
    add_anticipation,
    delete_anticipation,
    update_anticipation,
)
from app.schemas.receivable import ReceivableInvoiceCreate, ReceivableInvoiceUpdate


class TestCompetenceSchema(unittest.TestCase):
    def _create(self, **over: object) -> ReceivableInvoiceCreate:
        base: dict = {
            "project_id": uuid4(),
            "number": "NF-1",
            "issue_date": date(2026, 7, 15),
            "due_days": 30,
            "competence_month": date(2026, 6, 15),
            "gross_amount": 1000.0,
        }
        base.update(over)
        return ReceivableInvoiceCreate.model_validate(base)

    def test_create_normaliza_para_primeiro_de_mes(self) -> None:
        inv = self._create(competence_month=date(2026, 6, 15))
        self.assertEqual(inv.competence_month, date(2026, 6, 1))

    def test_create_competencia_independente_da_emissao(self) -> None:
        # Competência Junho, emitida em Julho — suportado.
        inv = self._create(issue_date=date(2026, 7, 1), competence_month=date(2026, 6, 1))
        self.assertEqual(inv.competence_month, date(2026, 6, 1))
        self.assertEqual(inv.issue_date, date(2026, 7, 1))

    def test_create_competencia_obrigatoria(self) -> None:
        with self.assertRaises(ValidationError):
            ReceivableInvoiceCreate.model_validate(
                {
                    "project_id": uuid4(),
                    "number": "NF-2",
                    "issue_date": date(2026, 7, 15),
                    "due_days": 30,
                    "gross_amount": 1000.0,
                }
            )

    def test_update_competencia_opcional_e_normalizada(self) -> None:
        upd = ReceivableInvoiceUpdate.model_validate({"competence_month": date(2026, 5, 20)})
        self.assertEqual(upd.competence_month, date(2026, 5, 1))

    def test_update_sem_competencia_fica_none(self) -> None:
        upd = ReceivableInvoiceUpdate.model_validate({"notes": "x"})
        self.assertIsNone(upd.competence_month)


class TestAnticipationEndpointsGone(unittest.TestCase):
    def test_mensagem_padrao(self) -> None:
        self.assertIn("descontinuadas", _ANTICIPATION_DISCONTINUED_MSG)
        self.assertIn("módulo Antecipações", _ANTICIPATION_DISCONTINUED_MSG)

    def test_post_410(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(add_anticipation(invoice_id=uuid4()))
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertEqual(ctx.exception.detail, _ANTICIPATION_DISCONTINUED_MSG)

    def test_patch_410(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(update_anticipation(invoice_id=uuid4(), anticipation_id=uuid4()))
        self.assertEqual(ctx.exception.status_code, 410)

    def test_delete_410(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(delete_anticipation(invoice_id=uuid4(), anticipation_id=uuid4()))
        self.assertEqual(ctx.exception.status_code, 410)


if __name__ == "__main__":
    unittest.main()
