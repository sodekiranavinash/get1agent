# Root local-dev Makefile.
#
# Everything runs locally on Floci — a free, LocalStack-compatible AWS emulator
# (no AWS account, no auth token). Lambda, API Gateway, S3, SQS, EventBridge and
# Step Functions run in Docker; DynamoDB Local stores operational data.
#
#   make floci        Build + start + provision; prints the API URL
#   make ui           React app -> http://localhost:5173
#   make floci-logs   Follow Floci logs
#   make floci-down   Stop and remove the stack
.DEFAULT_GOAL := help
SHELL := /bin/bash

COMPOSE := docker compose --env-file .env -f infra/local/floci/docker-compose.yml
FLOCI_API_URL := http://get1agent.execute-api.localhost.floci.io:4566
LOCAL_EMBED_MODEL ?= mxbai-embed-large

# Local cross-encoder reranker (TEI). TEI's CPU image is amd64; Apple Silicon
# runs it under Rosetta. Override RERANKER_IMAGE to pin a different tag.
RERANKER_IMAGE ?= ghcr.io/huggingface/text-embeddings-inference:cpu-1.9
RERANKER_PORT ?= 8080
export RERANKER_IMAGE RERANKER_PORT

.PHONY: help ui agent test test-unit floci floci-env floci-artifacts floci-build floci-up floci-wait \
	floci-embed floci-rerank floci-reload floci-down floci-logs floci-oauth-proxy

help:
	@echo "get1agent local dev (Floci + DynamoDB Local)"
	@echo ""
	@echo "  make floci            One command: build, start Floci + DynamoDB Local,"
	@echo "                        provision S3/SQS/EventBridge/Step Functions/Lambda"
	@echo "                        + API Gateway, and print the local API URL"
	@echo "  make ui               Start the React app (localhost:5173)"
	@echo "  make agent            Run the agent runtime locally (:8080)"
	@echo "  make test             Run backend integration tests (no Docker; moto)"
	@echo ""
	@echo "  Floci stack:"
	@echo "    make floci          Build + up + provision"
	@echo "    make floci-build    Build Lambda zips (after code changes)"
	@echo "    make floci-reload   Rebuild + re-upload code to the running stack"
	@echo "    make floci-up       Start the stack and provision resources"
	@echo "    make floci-logs     Follow the Floci logs"
	@echo "    make floci-down     Stop and remove the stack"
	@echo ""
	@echo "  API base URL: $(FLOCI_API_URL)"

ui:
	cd frontend && npm run dev

# Run the AgentCore agent runtime locally on :8080 against the local Floci stack.
# Installs the venv on first run; loads the repo-root .env for the OpenCode Go key.
agent:
	@test -x backend/agents/.venv/bin/python || $(MAKE) -C backend/agents install
	$(MAKE) -C backend/agents run

# Backend integration tests: moto-backed DynamoDB + in-memory S3. No Docker/AWS.
test:
	cd backend/services/integration-tests && uv run pytest

# Per-lambda unit tests (stdlib unittest in each app's tests/ dir). No-op for
# apps that don't have any yet.
test-unit:
	@for app in backend/services/*; do \
		[ -f "$$app/Makefile" ] || continue; \
		$(MAKE) -C "$$app" test || exit 1; \
	done

# --- Floci local stack -------------------------------------------------------

floci-env:
	@test -f .env || cp infra/local/floci/env.example .env

floci-build:
	bash infra/aws/build-backend-layers.sh base,genai,extra-tools
	$(MAKE) -C backend/services/user-api package
	$(MAKE) -C backend/services/knowledge-mcp package
	$(MAKE) -C backend/services/mcp-tester package
	$(MAKE) -C backend/services/web-search package
	$(MAKE) -C backend/services/code-interpreter package
	$(MAKE) -C backend/services/mcp-connections package
	$(MAKE) -C backend/services/ingestion-dispatcher package
	$(MAKE) -C backend/services/ingestion-extract package
	$(MAKE) -C backend/services/ingestion-embed package
	$(MAKE) -C backend/services/ingestion-index package
	$(MAKE) -C backend/services/ingestion-mark-failed package
	$(MAKE) -C backend/services/ingestion-watchdog package

# Build only if any artifact is missing (fast first run).
floci-artifacts:
	@missing=0; \
	for f in backend/services/dependency-layers/base/dist/layer.zip \
		backend/services/dependency-layers/genai/dist/layer.zip \
		backend/services/dependency-layers/extra-tools/dist/layer.zip \
		backend/services/user-api/dist/function.zip \
		backend/services/knowledge-mcp/dist/function.zip \
		backend/services/mcp-tester/dist/function.zip \
		backend/services/web-search/dist/function.zip \
		backend/services/code-interpreter/dist/function.zip \
		backend/services/mcp-connections/dist/function.zip \
		backend/services/ingestion-dispatcher/dist/function.zip \
		backend/services/ingestion-extract/dist/function.zip \
		backend/services/ingestion-embed/dist/function.zip \
		backend/services/ingestion-index/dist/function.zip \
		backend/services/ingestion-mark-failed/dist/function.zip \
		backend/services/ingestion-watchdog/dist/function.zip; do \
		[ -f "$$f" ] || missing=1; \
	done; \
	if [ "$$missing" = "1" ]; then \
		echo "Lambda artifacts missing; building..."; \
		$(MAKE) floci-build; \
	else \
		echo "Lambda artifacts present (run 'make floci-build' after code changes)"; \
	fi

floci-up: floci-env
	$(COMPOSE) up -d

floci-wait:
	bash infra/local/floci/wait.sh

# After changing Lambda code: rebuild the zips and re-upload them to the running
# Floci instance (re-runs the init hook in place; keeps S3/DynamoDB state).
floci-reload: floci-env
	$(MAKE) floci-build
	$(COMPOSE) exec -T floci python3 /etc/floci/init/ready.d/10-provision.py

# Pull the local embedding model (only needed for EMBED_MODE=local).
floci-embed: floci-env
	@mode=$$(grep -E '^EMBED_MODE=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]'); \
	if [ "$${mode:-voyage}" != "local" ]; then \
		echo "EMBED_MODE=$${mode:-voyage}; skipping Ollama (not needed)."; \
	else \
		$(COMPOSE) --profile local-embeddings up -d ollama; \
		echo "waiting for ollama..."; \
		until $(COMPOSE) --profile local-embeddings exec -T ollama ollama list >/dev/null 2>&1; do sleep 2; done; \
		$(COMPOSE) --profile local-embeddings exec -T ollama ollama pull $(LOCAL_EMBED_MODEL); \
	fi

# Wait for the local reranker (only needed for RERANK_MODE=local).
floci-rerank: floci-env
	@mode=$$(grep -E '^RERANK_MODE=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]'); \
	if [ "$${mode:-voyage}" != "local" ]; then \
		echo "RERANK_MODE=$${mode:-voyage}; skipping local reranker (not needed)."; \
	else \
		$(COMPOSE) --profile local-rerank up -d reranker; \
		echo "waiting for reranker (first run downloads the model)..."; \
		until curl -fsS "http://localhost:$(RERANKER_PORT)/health" >/dev/null 2>&1; do sleep 3; done; \
		echo "reranker ready on http://localhost:$(RERANKER_PORT)"; \
	fi

floci-down: floci-env
	$(COMPOSE) down

floci-logs: floci-env
	$(COMPOSE) logs -f floci

# Loopback OAuth callback forwarder: providers reject plaintext HTTP redirects
# unless they are loopback, and Floci only serves the API on its own host. Run
# this and set MCP_OAUTH_REDIRECT_URI=http://127.0.0.1:8765/v1/mcp/oauth/callback.
floci-oauth-proxy:
	python3 infra/local/floci/oauth-loopback.py --port $${OAUTH_PROXY_PORT:-8765}

# One command: build (if needed), start, provision, print the API URL.
floci: floci-env
	$(MAKE) floci-artifacts
	$(MAKE) floci-up
	$(MAKE) floci-wait
	$(MAKE) floci-embed
	$(MAKE) floci-rerank
	@echo ""
	@echo "Floci stack ready."
	@echo "  API base URL: $(FLOCI_API_URL)"
	@echo "  Point the UI at it (dev server proxies /v1 to Floci):"
	@echo "    printf 'VITE_API_URL=/\\nVITE_API_PROXY_TARGET=$(FLOCI_API_URL)\\n' > frontend/.env.local"
	@echo "  Logs:  make floci-logs     Stop:  make floci-down"
