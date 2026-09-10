.PHONY: install upgrade downgrade revision current history

# Local usage:
#   export DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/get1agent
#   make upgrade
install:
	uv sync

upgrade:
	uv run alembic upgrade head

downgrade:
	uv run alembic downgrade -1

revision:
	uv run alembic revision --autogenerate -m "$(m)"

current:
	uv run alembic current

history:
	uv run alembic history --verbose
