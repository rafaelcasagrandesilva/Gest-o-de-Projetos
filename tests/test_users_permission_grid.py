"""Regressão do editor de permissões de USUÁRIO (grade do modelo de verbos).

Incidente: a resposta administrativa (`_user_payload`) usava `session_permission_names`, que filtra
os códigos INATIVOS (modelo de verbos). Assim os checkboxes de códigos novos voltavam desmarcados ao
reabrir e o save recalculava deltas com um `full_set` incompleto (poluição de user_permissions).

Correção: telas administrativas usam `effective_permission_names` (efetivo completo). `/me` (gating)
continua com a projeção de sessão filtrada.

Estes testes exercem o fluxo REAL: `UsersService.update_user` (grava deltas + commita) e a projeção
real `_to_user_read(admin_view=True/False)`.
"""

from __future__ import annotations

import unittest
from uuid import uuid4

_EMAIL_PREFIX = "grid-"


class UsersPermissionGridDBTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        from sqlalchemy import text
        from app.database.session import AsyncSessionLocal, engine

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                await s.execute(
                    text("DELETE FROM users WHERE email LIKE :p"), {"p": f"{_EMAIL_PREFIX}%@ex.com"}
                )
                await s.commit()
            except Exception:
                await s.rollback()

    async def _mk_user(self, s, role_name: str):
        from sqlalchemy import text
        from app.core.security import hash_password
        from app.models.user import User, UserRole

        role_id = (
            await s.execute(text("SELECT id FROM roles WHERE name=:n"), {"n": role_name})
        ).scalar_one()
        u = User(
            email=f"{_EMAIL_PREFIX}{uuid4().hex[:8]}@ex.com",
            full_name="Grid",
            password_hash=hash_password("secret1"),
            is_active=True,
        )
        s.add(u)
        await s.flush()
        s.add(UserRole(user_id=u.id, role_id=role_id))
        await s.flush()
        await s.commit()
        return u.id

    async def _raw_deltas(self, s, uid) -> set[tuple[str, bool]]:
        from sqlalchemy import text

        s.expire_all()
        rows = (
            await s.execute(
                text(
                    "SELECT p.name, up.granted FROM user_permissions up "
                    "JOIN permissions p ON p.id = up.permission_id WHERE up.user_id = :u"
                ),
                {"u": uid},
            )
        ).all()
        return {(n, g) for n, g in rows}

    async def _admin_perm_names(self, s, uid) -> set[str]:
        """Exatamente o que o editor de usuários recebe (projeção administrativa real)."""
        from app.modules.users.router import _to_user_read
        from app.repositories.users import UserRepository

        s.expire_all()
        u = await UserRepository(s).get_with_roles(uid)
        read = await _to_user_read(s, u, admin_view=True)
        return set(read.permission_names)

    async def _me_perm_names(self, s, uid) -> set[str]:
        """O que `/me` (gating) recebe — projeção de sessão FILTRADA."""
        from app.modules.users.router import _to_user_read
        from app.repositories.users import UserRepository

        s.expire_all()
        u = await UserRepository(s).get_with_roles(uid)
        read = await _to_user_read(s, u, admin_view=False)
        return set(read.permission_names)

    async def _save(self, s, uid, perm_names: set[str], role_name: str) -> None:
        from app.services.users_service import UsersService

        await UsersService(s).update_user(
            actor_user_id=uid,
            user_id=uid,
            data={"role_name": role_name, "permission_names": sorted(perm_names)},
            actor=None,
            request=None,
        )

    async def test_noop_save_does_not_change_user_permissions(self) -> None:
        """Abrir → salvar SEM alterar nada → nenhuma linha de user_permissions criada/removida/alterada."""
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError
        from app.database.session import AsyncSessionLocal, engine

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT granted FROM user_permissions LIMIT 1"))
                await s.execute(text("SELECT 1 FROM permissions WHERE name='employees.read'"))
            except ProgrammingError:
                self.skipTest("Infra do modelo de verbos ausente (rode alembic upgrade head).")
            if (
                await s.execute(text("SELECT count(*) FROM permissions WHERE name='employees.read'"))
            ).scalar() == 0:
                self.skipTest("Migration 0092 não aplicada (código employees.read ausente).")

            uid = await self._mk_user(s, "CONSULTA")

            # Estabelece um estado com DELTAS: adiciona um código novo (que CONSULTA não tem).
            base = await self._admin_perm_names(s, uid)
            await self._save(s, uid, base | {"employees.create"}, "CONSULTA")

            before = await self._raw_deltas(s, uid)
            self.assertIn(("employees.create", True), before)  # delta de adição gravado

            # NO-OP: reabre (projeção administrativa) e salva exatamente o mesmo conjunto.
            admin_read = await self._admin_perm_names(s, uid)
            await self._save(s, uid, admin_read, "CONSULTA")
            after = await self._raw_deltas(s, uid)

            self.assertEqual(
                before, after,
                f"Save no-op alterou user_permissions.\n  antes={sorted(before)}\n  depois={sorted(after)}",
            )

    async def test_new_permission_round_trips(self) -> None:
        """Marcar código novo → salvar → reabrir → continua marcado (e /me segue neutro)."""
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError
        from app.database.session import AsyncSessionLocal, engine

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT granted FROM user_permissions LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Infra ausente.")
            if (
                await s.execute(text("SELECT count(*) FROM permissions WHERE name='payables.sensitive'"))
            ).scalar() == 0:
                self.skipTest("Migration de verbos não aplicada.")

            uid = await self._mk_user(s, "CONSULTA")

            # Usa payables.sensitive: código novo AINDA INATIVO que CONSULTA não concede —
            # garante que o round-trip administrativo funciona E que o /me segue neutro (não vaza inativo).
            # (assets.sensitive deixou de servir: foi ATIVADO ao aplicar o eixo Dados Sensíveis a Ativos.)
            code = "payables.sensitive"

            # [1] Abrir: CONSULTA não concede o código.
            admin1 = await self._admin_perm_names(s, uid)
            self.assertNotIn(code, admin1)

            # [2] Marcar o código novo e salvar.
            await self._save(s, uid, admin1 | {code}, "CONSULTA")

            # [3] Reabrir (projeção administrativa): continua marcado.
            admin2 = await self._admin_perm_names(s, uid)
            self.assertIn(code, admin2, "código novo não persistiu no editor administrativo")

            # [4] /me (gating) permanece NEUTRO: código inativo não vaza para a sessão do usuário.
            me = await self._me_perm_names(s, uid)
            self.assertNotIn(code, me, "código inativo vazou para /me (quebra a neutralidade)")


if __name__ == "__main__":
    unittest.main()
