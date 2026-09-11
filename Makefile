# Root local-dev Makefile.
#
# Runs the apps locally, ready to receive traffic. No AWS, no Docker, no layers:
# each Lambda is launched with its own uv-managed environment.
#
#   make dev                All local Lambdas + gateway -> http://localhost:9000
#   make ui                 React app                  -> http://localhost:5173
#   make gateway            Path-routing proxy only    -> http://localhost:9000
#   make account-settings   account-settings Lambda    -> http://localhost:9001
#   make health-check       health-check Lambda        -> http://localhost:9003
#
# Migrations are a separate script (not a make target):
#   bash scripts/migrate.sh up|down|current|history|revision
#
# Copy .env.example to .env.local first (sets DATABASE_URL, optional PORT).

.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help ui dev gateway account-settings health-check knowledge-bases

help:
	@echo "get1agent local dev"
	@echo ""
	@echo "  make dev                Run ALL local Lambdas + gateway (single URL :9000)"
	@echo "  make ui                 Start the React app (localhost:5173)"
	@echo "  make gateway            Run the path-routing proxy only (localhost:9000)"
	@echo ""
	@echo "  make account-settings   Run account-settings Lambda locally (localhost:9001)"
	@echo "  make health-check       Run health-check Lambda locally (localhost:9003)"
	@echo "  make knowledge-bases    Run knowledge-bases Lambda locally (localhost:9004)"
	@echo ""
	@echo "  Migrations:  bash scripts/migrate.sh up|down|current|history|revision"
	@echo "  Tip: copy .env.example to .env.local and set DATABASE_URL."

ui:
	cd frontend && npm run dev

dev:
	bash local/dev.sh

gateway:
	python3 -u local/gateway.py

account-settings:
	bash local/run.sh account-settings

health-check:
	bash local/run.sh health-check

knowledge-bases:
	bash local/run.sh knowledge-bases
