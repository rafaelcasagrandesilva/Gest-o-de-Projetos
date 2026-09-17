"""Pauta da reunião — itens (ASSUNTO) com obrigações, vínculo com a reunião e andamentos.

- o item de pauta é um ASSUNTO: sem responsável/prazo, fora do calendário; quem cobra são as
  obrigações filhas, cada uma com um ou mais responsáveis (todos veem no "só os meus");
- um compromisso avulso levado para a reunião vira a primeira obrigação de um item novo; uma
  obrigação de item leva o próprio item; nada entra duas vezes, nem reunião dentro de reunião;
- concluir e alterar prazo de obrigação ficam no histórico do item; concluir o item pode concluir
  junto as obrigações abertas;
- andamentos: só o autor (ou quem pode excluir) apaga; reabrir não apaga histórico.

Testes de banco NÃO commitam (rollback ao final).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException


def _futuro(semanas: int) -> datetime:
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    return base + timedelta(weeks=semanas)


async def _dois_usuarios(session):
    from sqlalchemy import select
    from app.models.user import User

    ids = (await session.execute(select(User.id).order_by(User.created_at).limit(2))).scalars().all()
    if len(ids) < 2:
        raise unittest.SkipTest("Precisa de 2 usuários no banco de teste.")
    return ids


class ObligationsTests(unittest.IsolatedAsyncioTestCase):
    async def test_item_com_obrigacoes_de_varios_responsaveis(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_agenda_service import ProjectAgendaService

        await engine.dispose()
        async with AsyncSessionLocal() as session:
            try:
                a, b = await _dois_usuarios(session)
                svc = ProjectAgendaService(session)
                reuniao = await svc.create(
                    data={"kind": "REUNIAO", "title": "Gerencial", "starts_at": _futuro(42)}, actor_id=None
                )
                titulo = f"Pendências {uuid4().hex[:6]}"
                topico = await svc.add_agenda_item(
                    meeting_id=reuniao.id,
                    data={
                        "title": titulo,
                        "first_obligation": {"title": "Entregar documentos", "owner_ids": [a, b], "due_at": _futuro(43)},
                    },
                    actor_id=a,
                )
                self.assertEqual(topico.kind, "ASSUNTO")
                obs = await svc.list_obligations(topico.id)
                self.assertEqual(len(obs), 1)
                lida = (await svc.to_read(obs))[0]
                self.assertEqual({o["user_id"] for o in lida["owners"]}, {a, b})
                self.assertEqual(lida["parent_title"], titulo)

                # Os DOIS responsáveis veem a obrigação no "só os meus"; o assunto não vai ao calendário.
                for uid in (a, b):
                    meus = {c.id for c in await svc.list_between(only_user_id=uid)}
                    self.assertIn(obs[0].id, meus)
                    self.assertNotIn(topico.id, meus)

                segunda = await svc.create_obligation(
                    topic_id=topico.id, data={"title": "Abrir as contas", "owner_ids": [b]}, actor_id=a
                )
                pauta = await svc.agenda_items(reuniao.id)
                self.assertEqual(
                    (pauta[0]["obligations_total"], pauta[0]["obligations_open"]), (2, 2)
                )

                # Prazo alterado e conclusão da obrigação vão para o histórico do ITEM.
                await svc.reschedule(
                    commitment_id=segunda.id, due_at=_futuro(44), reason="Aguardando contador",
                    actor_id=a, meeting_id=reuniao.id,
                )
                await svc.complete(commitment_id=obs[0].id, note="Enviado ao Kleison", actor_id=a)
                hist = await svc.list_updates(topico.id)
                self.assertEqual([h["kind"] for h in hist], ["CONCLUSAO", "PRAZO"])
                self.assertIn("Enviado ao Kleison", hist[0]["body"])
                self.assertIn("Aguardando contador", hist[1]["body"])
                self.assertEqual(hist[1]["meeting_id"], reuniao.id)

                # Trocar os responsáveis: o que saiu deixa de ver.
                await svc.update(commitment_id=segunda.id, data={"owner_ids": [a]})
                self.assertNotIn(segunda.id, {c.id for c in await svc.list_between(only_user_id=b)})

                # Concluir o item concluindo junto a obrigação que restou.
                pauta = await svc.agenda_items(reuniao.id)
                await svc.set_outcome(
                    occurrence_id=pauta[0]["occurrence_id"], outcome="DONE", actor_id=a, complete_obligations=True
                )
                self.assertTrue(all(o.status == "CONCLUIDO" for o in await svc.list_obligations(topico.id)))
            finally:
                await session.rollback()


class MeetingLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_avulso_vira_obrigacao_de_um_item_novo(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_agenda_service import ProjectAgendaService

        await engine.dispose()
        async with AsyncSessionLocal() as session:
            try:
                svc = ProjectAgendaService(session)
                reuniao = await svc.create(
                    data={"kind": "REUNIAO", "title": "Gerencial", "starts_at": _futuro(42)}, actor_id=None
                )
                avulsa = await svc.create(
                    data={"kind": "OBRIGACAO", "title": f"Avulsa {uuid4().hex[:6]}", "due_at": _futuro(43)},
                    actor_id=None,
                )
                self.assertEqual(
                    [c.id for c in await svc.open_for_meeting(meeting_id=reuniao.id, search=avulsa.title)],
                    [avulsa.id],
                )
                await svc.link_to_meeting(meeting_id=reuniao.id, commitment_id=avulsa.id)
                pauta = await svc.agenda_items(reuniao.id)
                self.assertEqual(len(pauta), 1)
                self.assertEqual(pauta[0]["kind"], "ASSUNTO")
                self.assertEqual(pauta[0]["title"], avulsa.title)
                self.assertEqual(pauta[0]["obligations_total"], 1)
                self.assertEqual((await svc._load(avulsa.id)).parent_id, pauta[0]["id"])

                # Nem o item nem a obrigação são oferecidos de novo; levar de novo é recusado.
                self.assertEqual(await svc.open_for_meeting(meeting_id=reuniao.id, search=avulsa.title), [])
                with self.assertRaises(HTTPException):
                    await svc.link_to_meeting(meeting_id=reuniao.id, commitment_id=avulsa.id)

                # A obrigação leva o próprio item para outra reunião.
                outra = await svc.create(
                    data={"kind": "REUNIAO", "title": "Gerencial 2", "starts_at": _futuro(44)}, actor_id=None
                )
                await svc.link_to_meeting(meeting_id=outra.id, commitment_id=avulsa.id)
                self.assertEqual([p["id"] for p in await svc.agenda_items(outra.id)], [pauta[0]["id"]])
            finally:
                await session.rollback()

    async def test_recusas(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_agenda_service import ProjectAgendaService

        await engine.dispose()
        async with AsyncSessionLocal() as session:
            try:
                svc = ProjectAgendaService(session)
                reuniao = await svc.create(
                    data={"kind": "REUNIAO", "title": "Gerencial", "starts_at": _futuro(42)}, actor_id=None
                )
                obrigacao = await svc.create(
                    data={"kind": "OBRIGACAO", "title": "Avulsa", "due_at": _futuro(43)}, actor_id=None
                )
                outra = await svc.create(
                    data={"kind": "REUNIAO", "title": "Outra", "starts_at": _futuro(44)}, actor_id=None
                )
                with self.assertRaises(HTTPException):  # reunião dentro de reunião
                    await svc.link_to_meeting(meeting_id=reuniao.id, commitment_id=outra.id)
                with self.assertRaises(HTTPException):  # destino que não é reunião
                    await svc.link_to_meeting(meeting_id=obrigacao.id, commitment_id=obrigacao.id)
                with self.assertRaises(HTTPException):  # obrigação só nasce dentro de item
                    await svc.create_obligation(topic_id=obrigacao.id, data={"title": "x"}, actor_id=None)
                await svc.complete(commitment_id=obrigacao.id, note=None)
                with self.assertRaises(HTTPException):  # já concluído
                    await svc.link_to_meeting(meeting_id=reuniao.id, commitment_id=obrigacao.id)
                with self.assertRaises(HTTPException):  # prazo de concluída
                    await svc.reschedule(
                        commitment_id=obrigacao.id, due_at=_futuro(45), reason=None, actor_id=None
                    )
            finally:
                await session.rollback()


class UpdatesTests(unittest.IsolatedAsyncioTestCase):
    async def test_andamentos(self) -> None:
        from app.database.session import AsyncSessionLocal, engine
        from app.services.project_agenda_service import ProjectAgendaService

        await engine.dispose()
        async with AsyncSessionLocal() as session:
            try:
                autor, _ = await _dois_usuarios(session)
                svc = ProjectAgendaService(session)
                reuniao = await svc.create(
                    data={"kind": "REUNIAO", "title": "Gerencial", "starts_at": _futuro(45)}, actor_id=None
                )
                proxima = await svc.create(
                    data={"kind": "REUNIAO", "title": "Gerencial 2", "starts_at": _futuro(46)}, actor_id=None
                )
                item = await svc.add_agenda_item(
                    meeting_id=reuniao.id, data={"title": f"Item {uuid4().hex[:6]}"}, actor_id=None
                )
                await svc.add_update(
                    commitment_id=item.id, kind="OBSERVACAO", body=" Villela vai abrir as contas ",
                    meeting_id=reuniao.id, author_id=autor,
                )
                for kind, body in (("CONCLUSAO", "x"), ("OBSERVACAO", "   ")):
                    with self.assertRaises(HTTPException):
                        await svc.add_update(
                            commitment_id=item.id, kind=kind, body=body, meeting_id=None, author_id=autor
                        )

                pauta = await svc.agenda_items(reuniao.id)
                occ = pauta[0]["occurrence_id"]
                self.assertEqual(pauta[0]["updates_count"], 1)

                await svc.set_outcome(occurrence_id=occ, outcome="EXTENDED", next_meeting_id=proxima.id,
                                      note="Falta o contador", actor_id=autor)
                await svc.set_outcome(occurrence_id=occ, outcome="DONE", note="Contas abertas", actor_id=autor)
                linha = await svc.list_updates(item.id)
                self.assertEqual([u["kind"] for u in linha], ["CONCLUSAO", "ATUALIZACAO", "OBSERVACAO"])

                await svc.reopen(commitment_id=item.id)
                self.assertEqual(len(await svc.list_updates(item.id)), 3)

                outro = uuid4()
                with self.assertRaises(HTTPException):
                    await svc.delete_update(update_id=linha[2]["id"], actor_id=outro, can_delete_any=False)
                await svc.delete_update(update_id=linha[2]["id"], actor_id=outro, can_delete_any=True)
                self.assertEqual(len(await svc.list_updates(item.id)), 2)
            finally:
                await session.rollback()


if __name__ == "__main__":
    unittest.main()
