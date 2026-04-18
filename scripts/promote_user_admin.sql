-- Referência: tabelas `users`, `roles`, `user_roles`, `permissions`, `user_permissions`, `project_users`.
-- Para ADMIN completo (role + todas as permissões + limpar projetos), prefira:
--   python manage.py promote_admin --email admin@sgp.com
-- ou
--   python scripts/promote_user_admin.py --email admin@sgp.com
--
-- O trecho abaixo apenas troca a role para ADMIN e remove vínculos em project_users.
-- As permissões explícitas em `user_permissions` continuam como estavam até você rodar o script Python
-- (que substitui pelo preset ADMIN).

BEGIN;

DELETE FROM user_roles ur
USING users u
WHERE ur.user_id = u.id AND lower(u.email) = lower('admin@sgp.com');

INSERT INTO user_roles (id, created_at, updated_at, user_id, role_id)
SELECT gen_random_uuid(), now(), now(), u.id, r.id
FROM users u
CROSS JOIN roles r
WHERE lower(u.email) = lower('admin@sgp.com')
  AND r.name = 'ADMIN';

DELETE FROM project_users pu
USING users u
WHERE pu.user_id = u.id AND lower(u.email) = lower('admin@sgp.com');

COMMIT;
