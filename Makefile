# Raiz do repositório SGP
PYTHON ?= python3

.PHONY: reset-db
## Drop + create DB PostgreSQL (DATABASE_URL), alembic upgrade head, validação e seed admin. CUIDADO: apaga todos os dados.
reset-db:
	$(PYTHON) manage.py reset_db --yes

.PHONY: reset-db-confirm
## Mesmo que reset-db, mas pede confirmação digitando o nome do banco.
reset-db-confirm:
	$(PYTHON) manage.py reset_db
