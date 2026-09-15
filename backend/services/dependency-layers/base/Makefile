.PHONY: build clean lock install-deps install-deps-docker

LAYER_DIR := $(CURDIR)
DIST := $(LAYER_DIR)/dist/python
REQ := $(LAYER_DIR)/dist/requirements.txt
HOST_OS := $(shell uname -s)
HOST_ARCH := $(shell uname -m)
PYTHON_VERSION := 3.14
LAMBDA_IMAGE := public.ecr.aws/lambda/python:3.14

build: lock
	rm -rf "$(LAYER_DIR)/dist"
	mkdir -p "$(DIST)"
	uv export --project . --no-dev --no-hashes -o "$(REQ)"
	$(MAKE) install-deps
	find "$(DIST)" -type d -name __pycache__ -prune -exec rm -rf {} +
	cd "$(LAYER_DIR)/dist" && zip -qXr layer.zip python

install-deps:
ifeq ($(HOST_OS),Linux)
ifeq ($(HOST_ARCH),aarch64)
	uv pip install --python-version $(PYTHON_VERSION) -r "$(REQ)" --target "$(DIST)"
else
	$(MAKE) install-deps-docker
endif
else
	$(MAKE) install-deps-docker
endif

install-deps-docker:
	@command -v docker >/dev/null 2>&1 || { echo "Docker required to build arm64 layers." >&2; exit 1; }
	docker run --rm --platform linux/arm64 \
		--user "$$(id -u):$$(id -g)" \
		--entrypoint /bin/bash \
		-v "$(REQ):/tmp/requirements.txt:ro" \
		-v "$(DIST):/out" \
		$(LAMBDA_IMAGE) \
		-c "/var/lang/bin/python$(PYTHON_VERSION) -m pip install --no-cache-dir --no-compile -r /tmp/requirements.txt -t /out"

lock:
	uv lock

clean:
	rm -rf dist
