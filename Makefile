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
# RERANKER_IMAGE / RERANKER_PORT come from .env (via `--env-file`); these are
# only fallbacks for the make targets themselves (do not export — that would
# override .env for docker compose).
RERANKER_IMAGE ?= ghcr.io/huggingface/text-embeddings-inference:cpu-1.9
RERANKER_PORT ?= 8080

.PHONY: help ui architecture agent test test-unit floci floci-env floci-artifacts floci-build floci-up floci-wait \
	floci-embed floci-rerank floci-reload floci-down floci-logs floci-oauth-proxy

help:
	@echo "get1agent local dev (Floci + DynamoDB Local)"
	@echo ""
	@echo "  make floci            One command: build, start Floci + DynamoDB Local,"
	@echo "                        provision S3/SQS/EventBridge/Step Functions/Lambda"
	@echo "                        + API Gateway, and print the local API URL"
	@echo "  make ui               Start the React app (localhost:5173)"
	@echo "  make agent            (Re)build + start the local agent container (:8090)"
	@echo "  make architecture     Regenerate the README architecture diagrams"
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

# Regenerate the README architecture diagrams (docs/assets/*.svg + *.png) from
# the app's own diagram spec + layout engine.
architecture:
	cd frontend && npm run gen:architecture

# Run the AgentCore agent runtime locally on :8090 against the local Floci stack.
# Installs the venv on first run; forwards your AWS credentials (Bedrock) from the
# repo-root .env / host chain. The agent runtime runs continuously as the `agent`
# service in the Floci stack (started by `make floci`; rebuilt by
# `make floci-reload`). This target just (re)builds + starts that container.
agent: floci-env
	@eval "$$(aws configure export-credentials --format env 2>/dev/null)" 2>/dev/null || true; \
	$(COMPOSE) up -d --build agent

# Backend integration tests: moto-backed DynamoDB + in-memory S3. No Docker/AWS.
test:
	cd backend/services/integration-tests && uv run pytest

# Per-lambda unit tests (stdlib unittest in each app's tests/ dir). No-op for
# apps that don't have any yet.
test-unit:
	@for app in $$(find backend/services -maxdepth 3 -name Makefile -exec dirname {} \; | sort); do \
		[ -f "$$app/Makefile" ] || continue; \
		$(MAKE) -C "$$app" test || exit 1; \
	done

# --- Floci local stack -------------------------------------------------------

floci-env:
	@test -f .env || cp infra/local/floci/env.example .env

floci-build:
	@echo "Building all Lambda packages in parallel..."
	$(MAKE) -j 8 floci-build-parallel

# Direct parallel build using make -j
floci-build-parallel: \
	floci-build-user-api \
	floci-build-knowledge-mcp \
	floci-build-mcp-tester \
	floci-build-code-interpreter \
	floci-build-http-fetch \
	floci-build-custom-tools \
	floci-build-mcp-connections \
	floci-build-ingestion-dispatcher \
	floci-build-ingestion-extract \
	floci-build-ingestion-embed \
	floci-build-ingestion-index \
	floci-build-ingestion-mark-failed \
	floci-build-ingestion-watchdog \
	floci-build-scheduler \
	floci-build-browser

# Individual build targets
floci-build-user-api:
	$(MAKE) -C backend/services/apis/user-api package

floci-build-knowledge-mcp:
	$(MAKE) -C backend/services/mcp/knowledge-mcp package

floci-build-mcp-tester:
	$(MAKE) -C backend/services/admin/mcp-tester package

floci-build-code-interpreter:
	$(MAKE) -C backend/services/mcp/code-interpreter package

floci-build-http-fetch:
	$(MAKE) -C backend/services/mcp/http-fetch package

floci-build-custom-tools:
	$(MAKE) -C backend/services/mcp/custom-tools package

floci-build-mcp-connections:
	$(MAKE) -C backend/services/mcp/mcp-connections package

floci-build-ingestion-dispatcher:
	$(MAKE) -C backend/services/ingestion/ingestion-dispatcher package

floci-build-ingestion-extract:
	$(MAKE) -C backend/services/ingestion/ingestion-extract package

floci-build-ingestion-embed:
	$(MAKE) -C backend/services/ingestion/ingestion-embed package

floci-build-ingestion-index:
	$(MAKE) -C backend/services/ingestion/ingestion-index package

floci-build-ingestion-mark-failed:
	$(MAKE) -C backend/services/ingestion/ingestion-mark-failed package

floci-build-ingestion-watchdog:
	$(MAKE) -C backend/services/ingestion/ingestion-watchdog package

floci-build-scheduler:
	$(MAKE) -C backend/services/scheduler package

floci-build-browser:
	$(MAKE) -C backend/services/mcp/browser package

# Check and rebuild only Lambdas that have changed key files
floci-rebuild-changed:
	@echo "Quick check for Lambda changes..."
	@for dir in $$(find backend/services -maxdepth 3 -name Makefile -exec dirname {} \; | sort); do \
		if [ -f "$$dir/Makefile" ]; then \
			name=$$(basename "$$dir"); \
			package_path="$$dir/dist/function.zip"; \
			if [ ! -f "$$package_path" ]; then \
				echo "🔄 Rebuilding $$name (missing package)..."; \
				($(MAKE) -C "$$dir" package >/dev/null 2>&1 && echo "✅ Rebuilt $$name" || echo "❌ Failed to rebuild $$name") & \
			elif [ "$$dir/Makefile" -nt "$$package_path" ] || [ -f "$$dir/handler.py" -a "$$dir/handler.py" -nt "$$package_path" ] || [ -f "$$dir/pyproject.toml" -a "$$dir/pyproject.toml" -nt "$$package_path" ]; then \
				echo "🔄 Rebuilding $$name (key files changed)..."; \
				($(MAKE) -C "$$dir" package >/dev/null 2>&1 && echo "✅ Rebuilt $$name" || echo "❌ Failed to rebuild $$name") & \
			fi; \
		fi; \
	done; \
	wait



# Check if all Lambda artifacts exist
floci-artifacts:
	@missing=0; \
	for f in backend/services/apis/user-api/dist/function.zip \
		backend/services/mcp/knowledge-mcp/dist/function.zip \
		backend/services/admin/mcp-tester/dist/function.zip \
		backend/services/mcp/code-interpreter/dist/function.zip \
		backend/services/mcp/http-fetch/dist/function.zip \
		backend/services/mcp/custom-tools/dist/function.zip \
		backend/services/mcp/mcp-connections/dist/function.zip \
		backend/services/ingestion/ingestion-dispatcher/dist/function.zip \
		backend/services/ingestion/ingestion-extract/dist/function.zip \
		backend/services/ingestion/ingestion-embed/dist/function.zip \
		backend/services/ingestion/ingestion-index/dist/function.zip \
		backend/services/ingestion/ingestion-mark-failed/dist/function.zip \
		backend/services/ingestion/ingestion-watchdog/dist/function.zip \
		backend/services/scheduler/dist/function.zip \
		backend/services/mcp/browser/dist/function.zip; do \
		[ -f "$$f" ] || missing=1; \
	done; \
	if [ "$$missing" = "1" ]; then \
		echo "Lambda artifacts missing (quick incremental build)..."; \
		$(MAKE) floci-rebuild-changed; \
	else \
		echo "✓ All Lambda artifacts present (run 'make floci-reload' after code changes)"; \
	fi

floci-up: floci-env
	@# Forward real AWS credentials from the host chain (env, ~/.aws, SSO) to the
	@# Floci container so non-emulated services (Bedrock) work locally. Skipped
	@# silently when the AWS CLI is unavailable or logged out (emulator default).
	@eval "$$(aws configure export-credentials --format env 2>/dev/null)" 2>/dev/null || true; \
	$(COMPOSE) up -d

floci-wait:
	bash infra/local/floci/wait.sh

# After changing Lambda **or agent** code: rebuild only changed Lambdas,
# rebuild + restart the agent container, and re-run the init hook in place.
floci-reload: floci-env
	@touch .floci-last-rebuild-timestamp
	$(MAKE) floci-rebuild-changed
	@eval "$$(aws configure export-credentials --format env 2>/dev/null)" 2>/dev/null || true; \
	# Only rebuild agent if agent code changed
	if [ "agents/main.py" -nt ".floci-agent-last-built" ] || \
	   [ "agents/agentflow/" -nt ".floci-agent-last-built" ] || \
	   [ "agents/workflow/" -nt ".floci-agent-last-built" ] || \
	   [ "backend/agents/Dockerfile" -nt ".floci-agent-last-built" ] || \
	   [ ! -f ".floci-agent-last-built" ]; then \
		echo "🔄 Agent code changed, rebuilding agent container..."; \
		$(COMPOSE) up -d --build agent; \
		touch ".floci-agent-last-built"; \
	else \
		echo "✓ Agent unchanged, restarting only..."; \
		$(COMPOSE) up -d agent; \
	fi
	# Check if any Lambda ZIP files were rebuilt (newer than timestamp)
	@lambda_updated=0; \
	for dir in $$(find backend/services -maxdepth 3 -name Makefile -exec dirname {} \; | sort); do \
		zip_file="$$dir/dist/function.zip"; \
		if [ -f "$$zip_file" ] && [ "$$zip_file" -nt ".floci-last-rebuild-timestamp" ]; then \
			lambda_updated=1; \
			break; \
		fi; \
	done; \
	if [ $$lambda_updated -eq 1 ]; then \
		echo "🔄 Some Lambdas were rebuilt, running provision script..."; \
		$(COMPOSE) exec -T floci python3 /etc/floci/init/ready.d/10-provision.py; \
	else \
		echo "✓ No Lambdas rebuilt, skipping provision script"; \
	fi

# Pull the local embedding model (only needed for EMBED_MODE=local).
floci-embed: floci-env
	@mode=$$(grep -E '^EMBED_MODE=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]'); \
	model=$$(grep -E '^LOCAL_EMBED_MODEL=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]'); \
	if [ "$${mode:-local}" != "local" ]; then \
		echo "EMBED_MODE=$${mode:-local}; skipping Ollama (not needed)."; \
	else \
		$(COMPOSE) --profile local-embeddings up -d ollama; \
		echo "waiting for ollama..."; \
		until $(COMPOSE) --profile local-embeddings exec -T ollama ollama list >/dev/null 2>&1; do sleep 2; done; \
		$(COMPOSE) --profile local-embeddings exec -T ollama ollama pull $${model:-$(LOCAL_EMBED_MODEL)}; \
	fi

# Wait for the local reranker (only needed for RERANK_MODE=local).
floci-rerank: floci-env
	@mode=$$(grep -E '^RERANK_MODE=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]'); \
	rport=$$(grep -E '^RERANKER_PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]'); \
	if [ "$${mode:-none}" != "local" ]; then \
		echo "RERANK_MODE=$${mode:-none}; skipping local reranker (not needed)."; \
	else \
		$(COMPOSE) --profile local-rerank up -d reranker; \
		echo "waiting for reranker (first run downloads the model)..."; \
		until curl -fsS "http://localhost:$${rport:-$(RERANKER_PORT)}/health" >/dev/null 2>&1; do sleep 3; done; \
		echo "reranker ready on http://localhost:$${rport:-$(RERANKER_PORT)}"; \
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
