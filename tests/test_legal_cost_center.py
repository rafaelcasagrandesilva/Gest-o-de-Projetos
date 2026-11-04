"""Vínculo projeto do Jurídico → centro de custo do SGC (validação do ref, sem banco)."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.services.legal_cost_center import cost_center_labels, validate_cost_center_ref


class _FakeDb:
    def __init__(self, projects: dict):
        self.projects = projects

    async def get(self, _model, key):
        return self.projects.get(key)


class ValidateRefTests(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    def test_vazio_vira_sem_vinculo(self) -> None:
        self.assertIsNone(self.run_async(validate_cost_center_ref(_FakeDb({}), "  ")))
        self.assertIsNone(self.run_async(validate_cost_center_ref(_FakeDb({}), None)))

    def test_codigo_sistemico_aceito(self) -> None:
        self.assertEqual(self.run_async(validate_cost_center_ref(_FakeDb({}), "FINANCEIRO")), "FINANCEIRO")

    def test_projeto_encerrado_aceito(self) -> None:
        pid = uuid4()
        encerrado = SimpleNamespace(deleted_at=None, is_active=False, closed_at="2026-01-01")
        self.assertEqual(self.run_async(validate_cost_center_ref(_FakeDb({pid: encerrado}), str(pid))), str(pid))

    def test_projeto_inexistente_ou_excluido_recusado(self) -> None:
        pid = uuid4()
        with self.assertRaises(ValueError):
            self.run_async(validate_cost_center_ref(_FakeDb({}), str(pid)))
        with self.assertRaises(ValueError):
            self.run_async(validate_cost_center_ref(_FakeDb({pid: SimpleNamespace(deleted_at="x")}), str(pid)))
        with self.assertRaises(ValueError):
            self.run_async(validate_cost_center_ref(_FakeDb({}), "texto livre"))

    def test_rotulo_dos_codigos_sem_consultar_projetos(self) -> None:
        labels = self.run_async(cost_center_labels(_FakeDb({}), ["RH", None, "ADMINISTRATIVO"]))
        self.assertEqual(labels, {"RH": "RH", "ADMINISTRATIVO": "Administrativo"})


if __name__ == "__main__":
    unittest.main()
