#!/usr/bin/env bash
# Backup COMPLETO do SGC em produção: banco + arquivos, com verificação e rotação.
#
# Existe porque as duas metades precisam ser copiadas juntas: restaurar só o banco devolve os
# REGISTROS dos documentos, mas os arquivos apareceriam como "não encontrado".
#
# Uso:
#   PROD_DB_URL="postgresql://..." ./scripts/backup_completo.sh
#
# Requisitos (uma vez): `railway login`, `railway link` nesta pasta e uma chave SSH
# (`ssh-keygen -t ed25519`). O passo a passo está em docs/PUBLICAR_EM_PRODUCAO.md.
#
# Variáveis:
#   PROD_DB_URL   — URL PÚBLICA do Postgres de produção (sem o prefixo +asyncpg)
#   BACKUP_DIR    — padrão: ~/sgc-backups
#   SERVICE       — serviço do Railway com o volume (padrão: celebrated-nature)
#   RETENTION     — quantos backups manter (padrão: 30)

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/sgc-backups}"
SERVICE="${SERVICE:-celebrated-nature}"
RETENTION="${RETENTION:-30}"
STAMP="$(date +%Y%m%d_%H%M%S)"

DUMP="${BACKUP_DIR}/backup_producao_${STAMP}.dump"
TARBALL="${BACKUP_DIR}/arquivos_${STAMP}.tar.gz"

falhou() {
  echo ""
  echo "❌ BACKUP INCOMPLETO — $1"
  echo "   Não publique nada até resolver."
  exit 1
}

if [[ -z "${PROD_DB_URL:-}" ]]; then
  falhou "defina PROD_DB_URL com a URL pública do Postgres de produção."
fi

# O endereço que o Railway mostra em DATABASE_URL vem com o prefixo do nosso backend Python;
# o pg_dump não entende e trataria a linha inteira como nome de banco.
PGURL="${PROD_DB_URL//postgresql+asyncpg:\/\//postgresql:\/\/}"
if [[ "${PGURL}" == *"railway.internal"* ]]; then
  falhou "a URL aponta para o host interno do Railway, inalcançável daqui. Use DATABASE_PUBLIC_URL."
fi

command -v pg_dump >/dev/null 2>&1 || falhou "pg_dump não encontrado (instale postgresql-client)."
command -v railway >/dev/null 2>&1 || falhou "railway CLI não encontrado."

mkdir -p "${BACKUP_DIR}"

# ---------------------------------------------------------------- banco de dados
echo "1/4 · Copiando o banco de produção…"
pg_dump --dbname="${PGURL}" --format=custom --file="${DUMP}" || falhou "pg_dump falhou."

# Um dump que não abre é pior que nenhum: parece proteção e não é.
pg_restore --list "${DUMP}" >/dev/null 2>&1 || falhou "o dump do banco está corrompido."
OBJETOS="$(pg_restore --list "${DUMP}" | grep -c ';' || true)"
echo "      ok — $(du -h "${DUMP}" | cut -f1), ${OBJETOS} objetos"

# ---------------------------------------------------------------- arquivos do volume
echo "2/4 · Copiando os arquivos do servidor…"
# A mensagem "Removing leading '/' from member names" é normal — é o tar do servidor.
railway ssh --service "${SERVICE}" "tar czf - /data" > "${TARBALL}" 2>/dev/null \
  || falhou "não consegui copiar os arquivos (rode 'railway link' nesta pasta)."

tar tzf "${TARBALL}" >/dev/null 2>&1 || falhou "o arquivo de anexos está corrompido."
ARQUIVOS="$(tar tzf "${TARBALL}" | grep -vc '/$' || true)"
if [[ "${ARQUIVOS}" -eq 0 ]]; then
  falhou "o backup de arquivos veio vazio."
fi
echo "      ok — $(du -h "${TARBALL}" | cut -f1), ${ARQUIVOS} arquivos"

# ---------------------------------------------------------------- limpeza e rotação
echo "3/4 · Limpando restos de tentativas falhas…"
find "${BACKUP_DIR}" -name "arquivos_*.tar.gz" -size -10k -delete 2>/dev/null || true
find "${BACKUP_DIR}" -name "backup_producao_*.dump" -size -10k -delete 2>/dev/null || true

echo "4/4 · Mantendo os ${RETENTION} backups mais recentes…"
ls -t "${BACKUP_DIR}"/backup_producao_*.dump 2>/dev/null | tail -n +$((RETENTION + 1)) | xargs -I{} rm -f {} || true
ls -t "${BACKUP_DIR}"/arquivos_*.tar.gz 2>/dev/null | tail -n +$((RETENTION + 1)) | xargs -I{} rm -f {} || true

echo ""
echo "✅ BACKUP COMPLETO — $(date '+%d/%m/%Y %H:%M')"
echo "   Banco:    $(basename "${DUMP}")"
echo "   Arquivos: $(basename "${TARBALL}")"
echo ""
echo "   Lembre-se: este backup contém CPF, salários e dados de processos."
echo "   A cópia fora desta máquina deve ficar em local privado e protegido."
