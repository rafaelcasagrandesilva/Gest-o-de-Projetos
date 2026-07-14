"""Perfis de Usuário administráveis: CRUD, guardas de sistema, vínculo vivo e deltas individuais."""

from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi import HTTPException


class RolesServiceDBTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        # Os serviços commitam internamente; limpa artefatos de teste E restaura os perfis de
        # sistema ao estado canônico (os testes editam permissões de GESTOR/CONSULTA).
        from sqlalchemy import text
        from app.core.permission_codes import PRESET_ADMIN, PRESET_CONSULTA, PRESET_GESTOR
        from app.database.session import AsyncSessionLocal, engine
        from app.repositories.permissions import PermissionRepository

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("DELETE FROM users WHERE email LIKE 'u-%@ex.com'"))
                await s.execute(
                    text("DELETE FROM roles WHERE is_system = false AND "
                         "(name LIKE 'ADM-%' OR name LIKE 'INATIVO-%' OR name LIKE 'R1-%' OR name LIKE 'R2-%')")
                )
                repo = PermissionRepository(s)
                for name, preset in (("ADMIN", PRESET_ADMIN), ("GESTOR", PRESET_GESTOR), ("CONSULTA", PRESET_CONSULTA)):
                    rid = (await s.execute(text("SELECT id FROM roles WHERE name=:n"), {"n": name})).scalar_one_or_none()
                    if rid is not None:
                        await repo.replace_role_permissions(rid, set(preset))
                await s.commit()
            except Exception:
                await s.rollback()

    async def _mk_user(self, s, role_id):
        from app.models.user import User, UserRole
        from app.core.security import hash_password

        u = User(email=f"u-{uuid4().hex[:8]}@ex.com", full_name="T", password_hash=hash_password("secret1"), is_active=True)
        s.add(u)
        await s.flush()
        s.add(UserRole(user_id=u.id, role_id=role_id))
        await s.flush()
        return u

    async def _effective(self, s, user_id):
        from app.api.deps import effective_permission_names
        from app.repositories.users import UserRepository

        # Reflete o estado COMMITADO/flushed do banco (evita identidade em cache entre "requests").
        s.expire_all()
        u = await UserRepository(s).get_with_roles(user_id)
        return set(effective_permission_names(u))

    async def test_role_lifecycle_and_live_link(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.user import Role
        from app.repositories.permissions import PermissionRepository
        from app.services.roles_service import RolesService

        await engine.dispose()
        tag = uuid4().hex[:6]
        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT is_system FROM roles LIMIT 1"))
                await s.execute(text("SELECT granted FROM user_permissions LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Migration 0091 ausente (rode alembic upgrade head).")

            svc = RolesService(s)
            gestor = (await s.execute(text("SELECT id FROM roles WHERE name='GESTOR'"))).scalar_one()

            # --- create (duplicando de GESTOR) ---
            created = await svc.create_role(
                name=f"ADM-{tag}", description="Administrativo", is_active=True,
                permission_names=None, base_role_id=gestor, actor=None, request=None,
            )
            role_id = created["id"]
            self.assertFalse(created["is_system"])
            self.assertGreater(len(created["permission_names"]), 0)

            # usuário com o novo perfil herda as permissões do perfil (sem deltas)
            user = await self._mk_user(s, role_id)
            eff1 = await self._effective(s, user.id)
            self.assertEqual(eff1, set(created["permission_names"]))

            # --- vínculo VIVO: alterar as permissões do perfil muda o efetivo do usuário ---
            await svc.update_role(
                role_id=role_id, data={"permission_names": ["projects.view", "employees.view"]},
                actor=None, request=None,
            )
            eff2 = await self._effective(s, user.id)
            self.assertEqual(eff2, {"projects.view", "employees.view"})

            # --- delta individual: adição e remoção ---
            perm_repo = PermissionRepository(s)
            role_perms = await perm_repo.role_permission_names(role_id)
            # quer: role − employees.view (remoção) + vehicles.view (adição)
            desired = (role_perms - {"employees.view"}) | {"vehicles.view"}
            await perm_repo.set_user_permission_deltas(user.id, desired, role_perms)
            await s.flush()
            eff3 = await self._effective(s, user.id)
            self.assertIn("vehicles.view", eff3)       # adição mantida
            self.assertNotIn("employees.view", eff3)   # remoção individual respeitada
            self.assertIn("projects.view", eff3)       # herda o resto do perfil

            # --- guarda: excluir perfil em uso é bloqueado ---
            with self.assertRaises(HTTPException) as ctx:
                await svc.delete_role(role_id=role_id, actor=None, request=None)
            self.assertEqual(ctx.exception.status_code, 400)

            await s.rollback()

    async def test_system_role_guards(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.services.roles_service import RolesService

        await engine.dispose()
        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT is_system FROM roles LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Migration 0091 ausente.")
            svc = RolesService(s)
            admin_id = (await s.execute(text("SELECT id FROM roles WHERE name='ADMIN'"))).scalar_one()
            gestor_id = (await s.execute(text("SELECT id FROM roles WHERE name='GESTOR'"))).scalar_one()

            # ADMIN: não pode alterar permissões
            with self.assertRaises(HTTPException) as c1:
                await svc.update_role(role_id=admin_id, data={"permission_names": ["projects.view"]}, actor=None, request=None)
            self.assertEqual(c1.exception.status_code, 400)

            # Sistema: não pode renomear nem desativar nem excluir
            with self.assertRaises(HTTPException):
                await svc.update_role(role_id=gestor_id, data={"name": "OUTRO"}, actor=None, request=None)
            with self.assertRaises(HTTPException):
                await svc.update_role(role_id=gestor_id, data={"is_active": False}, actor=None, request=None)
            with self.assertRaises(HTTPException):
                await svc.delete_role(role_id=admin_id, actor=None, request=None)

            # GESTOR/CONSULTA: PODEM ter permissões editadas
            await svc.update_role(role_id=gestor_id, data={"permission_names": ["projects.view"]}, actor=None, request=None)
            await s.rollback()

    async def test_inactive_role_not_assignable(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.services.roles_service import RolesService
        from app.services.users_service import UsersService

        await engine.dispose()
        tag = uuid4().hex[:6]
        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT is_active FROM roles LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Migration 0091 ausente.")
            svc = RolesService(s)
            created = await svc.create_role(
                name=f"INATIVO-{tag}", description=None, is_active=False,
                permission_names=["projects.view"], base_role_id=None, actor=None, request=None,
            )
            self.assertFalse(created["is_active"])
            # Não pode atribuir a um novo usuário
            with self.assertRaises(HTTPException) as ctx:
                await UsersService(s)._resolve_assignable_role(created["name"], for_new_assignment=True)
            self.assertEqual(ctx.exception.status_code, 400)
            await s.rollback()

    async def test_two_roles_union(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from app.database.session import AsyncSessionLocal, engine
        from app.models.user import UserRole
        from app.services.roles_service import RolesService

        await engine.dispose()
        tag = uuid4().hex[:6]
        async with AsyncSessionLocal() as s:
            try:
                await s.execute(text("SELECT granted FROM user_permissions LIMIT 1"))
            except ProgrammingError:
                self.skipTest("Migration 0091 ausente.")
            svc = RolesService(s)
            r1 = await svc.create_role(name=f"R1-{tag}", description=None, is_active=True,
                                       permission_names=["projects.view"], base_role_id=None, actor=None, request=None)
            r2 = await svc.create_role(name=f"R2-{tag}", description=None, is_active=True,
                                       permission_names=["vehicles.view"], base_role_id=None, actor=None, request=None)
            user = await self._mk_user(s, r1["id"])
            s.add(UserRole(user_id=user.id, role_id=r2["id"]))  # dois perfis
            await s.flush()
            eff = await self._effective(s, user.id)
            self.assertIn("projects.view", eff)
            self.assertIn("vehicles.view", eff)  # UNIÃO dos dois perfis
            await s.rollback()


if __name__ == "__main__":
    unittest.main()
