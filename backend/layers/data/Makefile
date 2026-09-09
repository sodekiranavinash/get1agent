.PHONY: build clean lock

ROOT := $(abspath ../..)
SHARED := $(ROOT)/shared
DIST := dist/python
PYTHON_VERSION := 3.14
PYTHON_PLATFORM := aarch64-manylinux2014

build: lock
	rm -rf dist
	mkdir -p $(DIST)
	uv export --project . --no-dev --no-hashes -o dist/requirements.txt
	uv pip install \
		--python-platform $(PYTHON_PLATFORM) \
		--python-version $(PYTHON_VERSION) \
		-r dist/requirements.txt \
		--target $(DIST)
	cp -R $(SHARED) $(DIST)/
	cd dist && zip -qXr layer.zip python

lock:
	uv lock

clean:
	rm -rf dist
