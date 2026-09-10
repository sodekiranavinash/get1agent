# Root local-dev Makefile.
#
# Runs the apps locally, ready to receive traffic. No AWS, no Docker, no layers:
# each Lambda is launched with its own uv-managed environment.
#
#   make ui                 React app          -> http://localhost:5173
#   make account-settings   account-settings   -> http://localhost:9001
#   make migration-runner   migration-runner   -> http://localhost:9002
#   make health-check       health-check       -> http://localhost:9003
#
#   make migrate-up         alembic upgrade head   (local DB)
#   make migrate-down       alembic downgrade -1   (local DB)
#   make migrate-current    alembic current
#
# Copy .env.example to .env.local first (sets DATABASE_URL, optional PORT).

.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help ui account-settings migration-runner health-check migrate-up migrate-down migrate-current

help:
	@echo "get1agent local dev"
	@echo ""
	@echo "  make ui                 Start the React app (localhost:5173)"
	@echo "  make account-settings   Run account-settings Lambda locally (localhost:9001)"
	@echo "  make migration-runner   Run migration-runner Lambda locally (localhost:9002)"
	@echo "  make health-check       Run health-check Lambda locally (localhost:9003)"
	@echo ""
	@echo "  make migrate-up         alembic upgrade head"
	@echo "  make migrate-down       alembic downgrade -1"
	@echo "  make migrate-current    alembic current"
	@echo ""
	@echo "  Tip: copy .env.example to .env.local and set DATABASE_URL."

ui:
	cd frontend && npm run dev

account-settings:
	bash local/run.sh account-settings

migration-runner:
	bash local/run.sh migration-runner

health-check:
	bash local/run.sh health-check

migrate-up:
	bash scripts/migrate.sh up

migrate-down:
	bash scripts/migrate.sh down

migrate-current:
	bash scripts/migrate.sh current
