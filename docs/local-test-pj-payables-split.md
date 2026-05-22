# Teste local — split PJ em Contas a Pagar

Guia para validar a separação **Salário Base PJ** / **Ajuda de Custo PJ** sem tocar produção (Railway).

## 1. Banco local (isolado de produção)

```bash
# Postgres dedicado (porta 5432 local)
docker run --name sgp-postgres-dev \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=sgp \
  -p 5432:5432 \
  -d postgres:16
```

Crie `.env` na raiz (nunca use `DATABASE_URL` de produção):

```bash
cp .env.example .env
```

Confirme em `.env`:

```env
ENV=local
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/sgp
```

## 2. Migrations

```bash
cd "/caminho/para/Novo - TESTE SGP"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
```

## 3. Backend local

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger: http://localhost:8000/docs

## 4. Frontend local → API local

```bash
cd frontend
npm install
```

Opcional `frontend/.env.local`:

```env
VITE_API_BASE=http://localhost:8000/api/v1
```

```bash
npm run dev
```

Abra http://localhost:5173 — login padrão (se seed): `admin@admin.com` / `123456`

## 5. Cenário de teste PJ

1. Cadastre colaborador **PJ** com `salary_base` e `pj_additional_cost` (ajuda de custo) > 0.
2. Vincule ao projeto em **Custos do projeto** (REALIZADO) com % de alocação.
3. Abra **Contas a Pagar** no mês de pagamento (ex.: competência seguinte ao REALIZADO).
4. Se o mês já tinha snapshot antigo, use **Regerar** (superuser) ou apague o marcador localmente:

```sql
-- somente DEV local
DELETE FROM payable_snapshots WHERE month = '2026-06-01' AND type = 'COLLABORATOR';
DELETE FROM payable_snapshot_generations WHERE month = '2026-06-01';
```

5. Recarregue Contas a Pagar — devem aparecer **duas linhas** para o mesmo PJ (se ajuda > 0).

## 6. Logs esperados (backend)

```
payables collaborator snapshot employee_id=... integral_components=[('Salário Base PJ', ...), ('Ajuda de Custo PJ', ...)]
payables collaborator line ... name=... — Salário Base PJ amount=...
payables collaborator line ... name=... — Ajuda de Custo PJ amount=...
```

`consolidated` no log = soma das linhas rateadas (= total proporcional anterior).

## 7. Checklist de validação

| Caso | Esperado |
|------|----------|
| PJ com ajuda de custo | 2 linhas em Contas a Pagar |
| PJ sem ajuda | 1 linha (nome simples) |
| CLT | 1 linha (salário base rateado) |
| Dashboard / custo projeto | Total **inalterado** (usa `project_labor_monthly_cost_breakdown`, não payables) |
| Unique constraint | Sem erro 500 na geração (nomes distintos) |

## 8. Não afetar Railway

- Não defina `DATABASE_URL` de produção no `.env` local.
- Não rode `git push` até validar.
- Frontend em dev usa `localhost:8000` por padrão, não o host Railway.
