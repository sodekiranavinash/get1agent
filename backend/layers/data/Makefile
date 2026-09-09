.PHONY: build clean lock

ROOT := $(abspath ../..)
SHARED := $(ROOT)/shared
DIST := dist/python
# Cross-build arm64 deps on x86_64 CI via Docker (greenlet has no cp314 aarch64 wheel to download).
BUILD_IMAGE := public.ecr.aws/sam/build-python3.14:latest

build: lock
	@command -v docker >/dev/null 2>&1 || { echo "Docker is required to build arm64 Lambda layers." >&2; exit 1; }
	rm -rf dist
	mkdir -p $(DIST)
	uv export --project . --no-dev --no-hashes -o dist/requirements.txt
	docker run --rm --platform linux/arm64 \
		-v "$(PWD)/dist/requirements.txt:/tmp/requirements.txt:ro" \
		-v "$(PWD)/$(DIST):/out" \
		$(BUILD_IMAGE) \
		/bin/sh -c "pip install --no-cache-dir -r /tmp/requirements.txt -t /out"
	cp -R $(SHARED) $(DIST)/
	cd dist && zip -qXr layer.zip python

lock:
	uv lock

clean:
	rm -rf dist
