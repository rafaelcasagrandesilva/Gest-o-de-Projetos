# Clone Local da Produção — Ambiente de Testes Seguro

Procedimento para restaurar uma cópia fiel da produção em um banco **local e
isolado**, sem qualquer conexão com o Railway. Gerado em **2026-06-17**.

> **Garantias:** nenhuma conexão com o banco de produção (Railway), nenhum dado
> remoto alterado, nenhuma `DATABASE_URL` de produção utilizada. O Railway CLI
> permanece não autenticado.

---

## 1. Banco criado

| Item | Valor |
|------|-------|
| Nome do banco | `sgc_producao_clone` |
| Owner | `postgres` |
| PostgreSQL | 18.4 (Homebrew) |
| Encoding / Locale | UTF8 / en_US.UTF-8 |
| Fonte do dump | `backups/producao/sgc_producao_20260617_0839.backup` (formato custom, base de origem `railway`, criado em 2026-06-17 08:39:53) |

Bancos **não** reutilizados/alterados: `sgp`, `sgp_local_test`, `postgres`.

---

## 2. DATABASE_URL utilizada

```
postgresql+asyncpg://postgres:postgres@localhost:5432/sgc_producao_clone
```

Fornecida **como variável de ambiente no momento do launch** — **nenhum arquivo
`.env` foi criado ou editado**.

> **Observação de configuração (importante):** `app/core/config.py` carrega
> `.env` (`SettingsConfigDict(env_file=".env")`). Esse arquivo **não existe** no
> projeto, então, sem variável de ambiente, a aplicação usa o default
> `postgresql+asyncpg://postgres:postgres@localhost:5432/sgp`. O arquivo
> `.env.local` **não é lido por nada** (nenhum `load_dotenv`/`--env-file`).
> Por isso o clone é selecionado via `export DATABASE_URL=...` antes do uvicorn.

---

## 3. Comandos executados (recriação futura)

```bash
# Pré-requisito: PostgreSQL 18 rodando localmente.
cd /Users/rafaelcasagrande/Documents/Work/SGP/Gest-o-de-Projetos

# (1) Backup das configs locais
mkdir -p backup_env
cp -p .env.local   backup_env/.env.local.bak
cp -p .env.example backup_env/.env.example.bak

# (2) Criar banco isolado (owner postgres)
createdb -U rafaelcasagrande -O postgres sgc_producao_clone

# (3) Restaurar o dump (como postgres → postgres vira dono de tudo)
PGPASSWORD=postgres pg_restore \
  --host=localhost --username=postgres \
  --dbname=sgc_producao_clone \
  --no-owner --no-acl --exit-on-error \
  backups/producao/sgc_producao_20260617_0839.backup

# (4) Validar
PGPASSWORD=postgres psql -h localhost -U postgres -d sgc_producao_clone -c "\dt"
PGPASSWORD=postgres psql -h localhost -U postgres -d sgc_producao_clone \
  -tAc "SELECT version_num FROM alembic_version;"
```

---

## 4. Como iniciar o ambiente

> A inicialização do backend executa **`alembic upgrade head` + `seed_admin`**
> automaticamente no startup (`app/main.py:startup_event`). Contra o clone isso
> aplica as migrations pendentes (`0066`, `0067`) e garante um admin.
> **Isto foi autorizado explicitamente.** Se quiser o clone exatamente em `0065`
> (igual à produção), **não inicie o backend** — use o clone apenas via `psql`.

```bash
cd /Users/rafaelcasagrande/Documents/Work/SGP/Gest-o-de-Projetos

# Backend apontando para o clone (variável só nesta shell)
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/sgc_producao_clone"
export ENV=local
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (outra shell) — consome a API em :8000
cd frontend && npm run dev   # http://localhost:3000
```

---

## 5. Estado verificado

| Verificação | Resultado |
|-------------|-----------|
| Tabelas | 49 |
| Índices | 192 |
| Constraints | 503 |
| Objetos não-`postgres` | 0 |
| `alembic_version` após restauração | `0065_audit_export_permission` |
| `alembic_version` após startup (autorizado) | `0067_company_finance_monthly_required` |
| Usuários / Projetos / Payables / Receivables / Employees | 8 / 8 / 0 / 43 / 69 |
| `/health/ready` | `{"status":"ready","database":"ok"}` |
| Endpoints protegidos sem token | 401 (auth + roteamento OK) |
| Conexões backend | somente `localhost` (`::1`) |

> **Login autenticado:** os 8 usuários são reais (senhas em hash). O
> `seed_admin` **não** criou `admin@admin.com/123456` porque já existe um admin.
> Para testar telas autenticadas, use a senha de um usuário real ou crie um
> usuário de teste manualmente (fora do escopo deste procedimento).

---

## 6. Plano de reversão (voltar ao banco local original)

```bash
# (1) Parar os serviços do clone
pkill -f "uvicorn app.main"
pkill -f "vite"

# (2) Restaurar configs (se tiverem sido tocadas — neste setup NÃO foram)
#     Como nada foi editado, basta conferir. Caso necessário:
cp -p backup_env/.env.local.bak   .env.local
cp -p backup_env/.env.example.bak .env.example

# (3) Voltar ao banco local padrão (sgp): basta NÃO exportar DATABASE_URL.
#     Sem a variável, a app usa o default (.../sgp).
unset DATABASE_URL ENV
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# (4) (Opcional) Remover o clone
dropdb -U rafaelcasagrande sgc_producao_clone
```

Como a `DATABASE_URL` do clone existiu **apenas como variável de ambiente na
shell de launch**, encerrar o processo / abrir uma shell nova já desfaz o
apontamento — não há estado persistente para limpar nos arquivos.
