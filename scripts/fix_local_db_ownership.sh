#!/usr/bin/env bash
# Corrige ownership do schema public quando tabelas foram criadas pelo usuário do macOS
# (ex.: rafaelcasagrande) mas o app/Alembic usam postgres via DATABASE_URL.
#
# Uso (no Mac, com Postgres local):
#   ./scripts/fix_local_db_ownership.sh
#   ./scripts/fix_local_db_ownership.sh outro_banco

set -euo pipefail

DB_NAME="${1:-sgp}"
TARGET_ROLE="${TARGET_ROLE:-postgres}"

echo "Ajustando ownership em database=${DB_NAME} -> role=${TARGET_ROLE}"

psql -d "$DB_NAME" -v ON_ERROR_STOP=1 <<SQL
ALTER SCHEMA public OWNER TO ${TARGET_ROLE};

DO \$\$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public' AND tableowner <> '${TARGET_ROLE}'
  LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO ${TARGET_ROLE}', r.tablename);
  END LOOP;
END \$\$;

DO \$\$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT sequence_name FROM information_schema.sequences
    WHERE sequence_schema = 'public'
  LOOP
    EXECUTE format('ALTER SEQUENCE public.%I OWNER TO ${TARGET_ROLE}', r.sequence_name);
  END LOOP;
END \$\$;

DO \$\$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT t.typname
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typtype IN ('e', 'd')
      AND pg_get_userbyid(t.typowner) <> '${TARGET_ROLE}'
  LOOP
    EXECUTE format('ALTER TYPE public.%I OWNER TO ${TARGET_ROLE}', r.typname);
  END LOOP;
END \$\$;

GRANT ALL ON SCHEMA public TO ${TARGET_ROLE};
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ${TARGET_ROLE};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${TARGET_ROLE};
SQL

echo "OK. Rode: alembic upgrade head"
