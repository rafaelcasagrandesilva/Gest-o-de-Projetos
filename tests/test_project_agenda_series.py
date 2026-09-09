"""Repetição da Agenda de Projetos — acrescentar e encerrar a série.

As ocorrências são MATERIALIZADAS (uma linha por semana), então a série não tem regra guardada:
o intervalo é lido das próprias ocorrências. Isso é o que estes testes protegem —

- o RITMO manda, não a última data: uma quarta remarcada em caráter de exceção não pode arrastar
  as próximas para o dia errado;
- encerrar é "não acontece mais", nunca "nunca aconteceu": o que já passou fica;
- o resumo avisa antes de apagar o que já tem ata ou pauta.

Testes de banco NÃO commitam (rollback ao final).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4


def _quarta_9h(semanas_a_frente: int = 40) -> datetime:
    """Uma quarta-feira bem no futuro, para não colidir com dado real restaurado."""
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    base += timedelta(weeks=semanas_a_frente)
    return base + timedelta(days=(2 - base.weekday()) % 7)


class ProjectAgendaSeriesTests(unittest.IsolatedAsyncioTestCase):
    async def _prelude(self, session):
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        try:
            await session.execute(text("SELECT series_id FROM project_commitments LIMIT 1"))
        except ProgrammingError:
            self.skipTest("Coluna series_id ausente (rode alembic upgrade head).")

    def _dados(self, inicio: datetime) -> dict:
        return {
            "kind": "REUNIAO",
            "title": f"Gerencial de teste {uuid4().hex[:6]}",
            "starts_at": inicio,
            "location": "Sala 1",
        }

    async def test_extensao_segue_o_ritmo_e_nao_a_ultima_data(self) -> None:
        """Remarcar uma ocorrência não pode tirar as próximas da quarta-feira."""
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_agenda_service import ProjectAgendaService

        await engine.dispose()
        inicio = _quarta_9h()
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                svc = ProjectAgendaService(session)
                serie = await svc.create_series(
                    data=self._dados(inicio), every_weeks=1, count=4, actor_id=None
                )
                # A 3ª foi remarcada da quarta para a quinta, em caráter de exceção.
                await svc.update(
                    commitment_id=serie[2].id, data={"starts_at": inicio + timedelta(weeks=2, days=1)}
                )
                novas = await svc.extend_series(
                    commitment_id=serie[0].id, count=2, actor_id=None
                )

                self.assertEqual(len(novas), 2)
                self.assertEqual(novas[0].starts_at, inicio + timedelta(weeks=4))
                self.assertEqual(novas[1].starts_at, inicio + timedelta(weeks=5))
                self.assertEqual({n.series_id for n in novas}, {serie[0].series_id})
                # Molde da última: local e título seguem adiante.
                self.assertEqual(novas[0].location, "Sala 1")
            finally:
                await session.rollback()

    async def test_extensao_copia_participantes_e_prazo_relativo(self) -> None:
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.user import User
        from app.services.project_agenda_service import ProjectAgendaService

        await engine.dispose()
        inicio = _quarta_9h(41)
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                alguem = (
                    await session.execute(
                        select(User.id).where(User.is_active.is_(True), User.deleted_at.is_(None)).limit(1)
                    )
                ).scalars().first()
                if alguem is None:
                    self.skipTest("Sem usuário ativo no banco de teste.")
                svc = ProjectAgendaService(session)
                dados = {
                    **self._dados(inicio),
                    "due_at": inicio + timedelta(days=2),
                    "participant_ids": [alguem],
                }
                serie = await svc.create_series(data=dados, every_weeks=1, count=3, actor_id=None)
                nova = (await svc.extend_series(commitment_id=serie[0].id, count=1, actor_id=None))[0]

                # O prazo acompanha a ocorrência — senão nasceria com a data-limite da primeira.
                self.assertEqual(nova.due_at, nova.starts_at + timedelta(days=2))
                # A linha recém-criada NÃO traz a relação carregada — é por isso que o router
                # recarrega antes de serializar; ler direto daqui estoura MissingGreenlet.
                from sqlalchemy import inspect as sa_inspect

                self.assertIn("participants", sa_inspect(nova).unloaded)
                carregada = await svc._load(nova.id)
                self.assertEqual([p.user_id for p in carregada.participants], [alguem])
            finally:
                await session.rollback()

    async def test_quinzenal_continua_quinzenal(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_agenda_service import ProjectAgendaService

        await engine.dispose()
        inicio = _quarta_9h(42)
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                svc = ProjectAgendaService(session)
                serie = await svc.create_series(
                    data=self._dados(inicio), every_weeks=2, count=3, actor_id=None
                )
                nova = (await svc.extend_series(commitment_id=serie[1].id, count=1, actor_id=None))[0]
                self.assertEqual(nova.starts_at, inicio + timedelta(weeks=6))
            finally:
                await session.rollback()

    async def test_encerrar_apaga_daqui_para_frente_e_preserva_o_passado(self) -> None:
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal, engine
        from app.models.project_agenda import ProjectCommitment
        from app.services.project_agenda_service import ProjectAgendaService

        await engine.dispose()
        inicio = _quarta_9h(43)
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                svc = ProjectAgendaService(session)
                serie = await svc.create_series(
                    data=self._dados(inicio), every_weeks=1, count=5, actor_id=None
                )
                sid = serie[0].series_id
                apagadas = await svc.delete_series_from(commitment_id=serie[2].id)
                self.assertEqual(apagadas, 3)

                restantes = (
                    await session.execute(
                        select(ProjectCommitment.starts_at).where(ProjectCommitment.series_id == sid)
                    )
                ).scalars().all()
                self.assertEqual(sorted(restantes), [inicio, inicio + timedelta(weeks=1)])
            finally:
                await session.rollback()

    async def test_resumo_avisa_o_que_ja_tem_pauta(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_agenda_service import ProjectAgendaService

        await engine.dispose()
        inicio = _quarta_9h(44)
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                svc = ProjectAgendaService(session)
                serie = await svc.create_series(
                    data=self._dados(inicio), every_weeks=1, count=4, actor_id=None
                )
                await svc.add_agenda_item(
                    meeting_id=serie[3].id, data={"title": "Assunto pendente"}, actor_id=None
                )
                resumo = await svc.series_summary(commitment_id=serie[1].id)

                self.assertEqual(resumo["total"], 4)
                self.assertEqual(resumo["every_weeks"], 1)
                self.assertEqual(resumo["from_here"], 3)
                self.assertEqual(resumo["from_here_with_content"], 1)
                self.assertEqual(resumo["last_starts_at"], inicio + timedelta(weeks=3))
            finally:
                await session.rollback()

    async def test_limites(self) -> None:
        from fastapi import HTTPException
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_agenda_service import ProjectAgendaService

        await engine.dispose()
        inicio = _quarta_9h(45)
        async with AsyncSessionLocal() as session:
            await self._prelude(session)
            try:
                svc = ProjectAgendaService(session)
                avulso = await svc.create(data=self._dados(inicio), actor_id=None)
                with self.assertRaises(HTTPException):
                    await svc.extend_series(commitment_id=avulso.id, count=1, actor_id=None)
                self.assertIsNone(await svc.series_summary(commitment_id=avulso.id))

                serie = await svc.create_series(
                    data=self._dados(inicio), every_weeks=1, count=3, actor_id=None
                )
                with self.assertRaises(HTTPException):
                    await svc.extend_series(commitment_id=serie[0].id, count=0, actor_id=None)
                with self.assertRaises(HTTPException):  # estoura o teto de 52
                    await svc.extend_series(commitment_id=serie[0].id, count=50, actor_id=None)
            finally:
                await session.rollback()


if __name__ == "__main__":
    unittest.main()
