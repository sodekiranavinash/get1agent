.PHONY: build clean lock install-deps install-deps-docker

LAYER_DIR := $(CURDIR)
ROOT := $(abspath $(LAYER_DIR)/../..)
SHARED := $(ROOT)/shared
DIST := $(LAYER_DIR)/dist/python
REQ := $(LAYER_DIR)/dist/requirements.txt
HOST_OS := $(shell uname -s)
HOST_ARCH := $(shell uname -m)
PYTHON_VERSION := 3.14
# Same base as the managed Lambda runtime (smaller than SAM build images).
LAMBDA_IMAGE := public.ecr.aws/lambda/python:3.14

build: lock
	rm -rf "$(LAYER_DIR)/dist"
	mkdir -p "$(DIST)"
	uv export --project . --no-dev --no-hashes -o "$(REQ)"
	$(MAKE) install-deps
	cp -R "$(SHARED)" "$(DIST)/"
	cd "$(LAYER_DIR)/dist" && zip -qXr layer.zip python

# Linux arm64 (e.g. GitHub ubuntu-24.04-arm): install directly for Lambda target arch.
install-deps:
ifeq ($(HOST_OS),Linux)
ifeq ($(HOST_ARCH),aarch64)
	uv pip install \
		--python-version $(PYTHON_VERSION) \
		-r "$(REQ)" \
		--target "$(DIST)"
else
	$(MAKE) install-deps-docker
endif
else
	$(MAKE) install-deps-docker
endif

# macOS / x86_64 Linux: build inside the Lambda Python image (needs QEMU on x86_64).
install-deps-docker:
	@command -v docker >/dev/null 2>&1 || { \
		echo "Docker is required to build arm64 Lambda layers on $(HOST_OS)/$(HOST_ARCH)." >&2; \
		echo "On x86_64 Linux/macOS enable QEMU: docker run --privileged --rm tonistiigi/binfmt --install all" >&2; \
		exit 1; \
	}
	docker run --rm --platform linux/arm64 \
		--entrypoint /bin/bash \
		-v "$(REQ):/tmp/requirements.txt:ro" \
		-v "$(DIST):/out" \
		$(LAMBDA_IMAGE) \
		-c "/var/lang/bin/python$(PYTHON_VERSION) -m pip install --no-cache-dir -r /tmp/requirements.txt -t /out"

lock:
	uv lock

clean:
	rm -rf dist
