.PHONY: build push run install test clean

REGION ?= ap-south-1
IMAGE ?= get1agent-prod-agent-worker
TAG ?= latest
IMAGE_URI ?= $(IMAGE):$(TAG)
BACKEND_ROOT := $(abspath $(CURDIR)/..)
REPO_ROOT := $(abspath $(CURDIR)/../..)
VENV := $(CURDIR)/.venv
PY := $(VENV)/bin/python

# Build the ARM64 image from the backend/ context so shared packages are copied.
build:
	docker build --platform linux/arm64 -f "$(CURDIR)/Dockerfile" -t "$(IMAGE_URI)" "$(BACKEND_ROOT)"

push: build
	docker push "$(IMAGE_URI)"

# Create the local venv with the container's dependencies (host dev only).
install:
	uv venv --python 3.13 "$(VENV)"
	uv pip install --python "$(PY)" -r "$(CURDIR)/requirements.txt"

# Run the AgentCore app locally on :8080 against the local Floci stack.
# Loads the repo-root .env; overrides the Docker-internal DynamoDB host with the
# host-reachable one.
run:
	@set -a; [ -f "$(REPO_ROOT)/.env" ] && . "$(REPO_ROOT)/.env"; set +a; \
	export DYNAMODB_ENDPOINT_URL="http://localhost:8000"; \
	cd "$(CURDIR)" && PYTHONPATH="$(BACKEND_ROOT)/packages:$(CURDIR)" "$(PY)" main.py

test:
	@if [ -d tests ]; then uv run --no-project --python 3.13 python -m unittest discover -s tests -t tests -v; else echo "no unit tests for agents"; fi

clean:
	rm -rf dist
