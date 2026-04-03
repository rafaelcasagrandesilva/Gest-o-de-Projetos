# SGP Backend (FastAPI + PostgreSQL)

Backend modular e pronto para produção usando FastAPI, SQLAlchemy 2.0 (async), Alembic, JWT e RBAC.

## Requisitos
- Python 3.11+
- PostgreSQL 14+

## Setup rápido

Crie um ambiente virtual e instale dependências:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Crie seu `.env`:

```bash
cp .env.example .env
```

Suba o Postgres (exemplo com Docker):

```bash
docker run --name sgp-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=sgp -p 5432:5432 -d postgres:16
```

## Migrations (Alembic)

Inicializar o schema (já existe migration inicial no repo):

```bash
alembic upgrade head
```

Gerar nova migration após alterar models:

```bash
alembic revision --autogenerate -m "descricao"
alembic upgrade head
```

## Rodar o servidor

```bash
uvicorn app.main:app --reload
```

Swagger: `http://localhost:8000/docs`

## Frontend (React + Vite)

Interface web em `frontend/` (login, dashboard, projetos, usuários).

```bash
cd frontend
npm install
npm run dev
```

Abra **http://localhost:5173** com o backend em **http://localhost:8000** (CORS já configurado para a origem do Vite).

Mais detalhes: [frontend/README.md](frontend/README.md).

## Usuário admin inicial

No startup, o backend cria **admin@admin.com** / **123456** com role **Admin** se ainda não existir administrador.

