#!/usr/bin/env bash
# Dump lógico do PostgreSQL (pg_dump) com rotação local.
# Uso em cron (ex.: 1x/mês): 0 3 1 * * /caminho/.../backup_postgres.sh
#
# Variáveis (ou defina no ambiente do cron):
#   DATABASE_URL  — ex.: postgresql://user:pass@host:5432/dbname
#   BACKUP_DIR    — padrão: ./var/backups/postgres
#   RETENTION    — manter últimos N arquivos (padrão 12 ≈ 1 ano mensal)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

BACKUP_DIR="${BACKUP_DIR:-${ROOT_DIR}/var/backups/postgres}"
RETENTION="${RETENTION:-12}"
STAMP="$(date +%Y%m%d_%H%M%S)"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "Erro: defina DATABASE_URL (postgresql://user:pass@host:5432/db)" >&2
  exit 1
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "Erro: pg_dump não encontrado. Instale postgresql-client." >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

OUT="${BACKUP_DIR}/sgp_${STAMP}.sql.gz"

# DATABASE_URL pode ser postgresql+asyncpg:// — pg_dump espera postgresql://
PGURL="${DATABASE_URL}"
PGURL="${PGURL//postgresql+asyncpg:\/\//postgresql:\/\/}"

echo "Gerando ${OUT} ..."
pg_dump --dbname="${PGURL}" --format=plain --no-owner --no-acl | gzip -9 > "${OUT}"

SIZE="$(du -h "${OUT}" | cut -f1)"
echo "OK (${SIZE})"

# Rotação: mantém os RETENTION arquivos mais recentes
ls -1t "${BACKUP_DIR}"/sgp_*.sql.gz 2>/dev/null | tail -n +"$((RETENTION + 1))" | while read -r old; do
  [[ -z "${old}" ]] && continue
  echo "Removendo backup antigo: ${old}"
  rm -f "${old}"
done

echo "Backups em: ${BACKUP_DIR}"
