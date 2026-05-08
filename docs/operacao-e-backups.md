# Operação em produção e backups

## Checklist antes de publicar

1. **Variáveis de ambiente** (ver `.env.example`):
   - `ENV=production`
   - `JWT_SECRET_KEY` com **pelo menos 32 caracteres** aleatórios (o backend recusa valores fracos em produção).
   - `CORS_ORIGINS` com o(s) domínio(s) HTTPS do frontend (origens separadas por vírgula).
   - `DATABASE_URL` apontando para o Postgres gerenciado.
   - `AUTH_DEBUG=false`
   - Opcional: `APP_SUPERUSER_EMAILS` para definir quem tem privilégios operacionais de emergência (substitui a lista padrão no código).

2. **Migrations**: o app executa `alembic upgrade head` no startup. Com **vários workers** (vários processos Uvicorn/Gunicorn), pode haver corrida na primeira subida; o ideal é aplicar migrations **uma vez** no deploy (comando de release) e subir os workers depois, ou usar um único worker para o processo que roda migrations.

3. **HTTPS**: use sempre TLS na frente da API (proxy, CDN, Railway, etc.). O middleware `ForwardedProtoMiddleware` já trata `X-Forwarded-Proto`.

4. **Health checks**: use `GET /health` para “vivo” e `GET /health/ready` para “pronto” (inclui ping no banco). Balanceadores devem usar `/health/ready`.

5. **Arquivos**: PDFs de NF ficam em `RECEIVABLE_UPLOAD_DIR`. Faça **backup deste diretório** junto com o banco, ou use storage externo (S3, etc.) em evolução futura.

6. **Pool do banco**: ajuste `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` se tiver muitos usuários simultâneos (valores atuais são conservadores).

---

## Estratégia de backup

### Banco de dados (PostgreSQL)

- **Frequência recomendada**: backup **automático diário** no provedor (RDS, Supabase, Neon, Railway Postgres, etc.) + cópia **mensal** mantida por mais tempo (muitos provedores já oferecem “point in time recovery” — PITR).
- **Dump lógico próprio**: use o script `scripts/backup_postgres.sh`, que gera um `.sql.gz` e mantém os últimos `RETENTION` arquivos (padrão 12).

Exemplo manual:

```bash
export DATABASE_URL="postgresql://usuario:senha@host:5432/sgp"
./scripts/backup_postgres.sh
```

Cron (1º dia do mês, 03:00):

```cron
0 3 1 * * cd /caminho/do/projeto && DATABASE_URL="..." BACKUP_DIR=/backup/sgp RETENTION=12 ./scripts/backup_postgres.sh >> /var/log/sgp-backup.log 2>&1
```

Requisitos no servidor: cliente PostgreSQL (`pg_dump`).

### Restauração (dump `.sql.gz`)

```bash
gunzip -c var/backups/postgres/sgp_YYYYMMDD_HHMMSS.sql.gz | psql "postgresql://..."
```

Teste **restauração em ambiente de homologação** pelo menos uma vez.

### PDFs / uploads

Copie periodicamente o diretório `RECEIVABLE_UPLOAD_DIR` (ex.: `rsync`, snapshot de disco).

---

## Monitoramento

- Logs da aplicação (stdout/stderr no provedor).
- Alertas no banco: espaço em disco, conexões, CPU.
- Opcional: integrar Sentry ou similar para erros 500 não tratados.
