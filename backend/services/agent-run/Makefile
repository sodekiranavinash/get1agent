.PHONY: package test clean

# The proxy validates the Auth0 token before it invokes AgentCore, so its zip
# bundles the shared `core` package plus PyJWT (third-party, vendored into the
# zip — not a layer). Deps are installed for the arm64 Lambda runtime via the
# official image, mirroring the dependency-layer builds.
PKG_ROOT := $(CURDIR)/../../packages
DIST := $(CURDIR)/dist
LAMBDA_IMAGE := public.ecr.aws/lambda/python:3.14
PYTHON_VERSION := 3.14

package:
	rm -rf dist
	mkdir -p dist
	cp handler.py dist/
	cp -R "$(PKG_ROOT)/core" dist/core
	cp requirements.txt dist/requirements.txt
	$(MAKE) install-deps
	rm -f dist/requirements.txt
	find dist -type d -name __pycache__ -prune -exec rm -rf {} +
	cd dist && zip -qXr function.zip .

install-deps:
	docker run --rm --platform linux/arm64 \
		--user "$$(id -u):$$(id -g)" \
		--entrypoint /bin/bash \
		-v "$(DIST):/work" \
		$(LAMBDA_IMAGE) \
		-c "python$(PYTHON_VERSION) -m pip install --no-cache-dir --no-compile -r /work/requirements.txt -t /work"

test:
	@if [ -d tests ]; then PYTHONPATH="$(PKG_ROOT)" uv run --with 'PyJWT[crypto]>=2.8' --no-project --python $(PYTHON_VERSION) python -m unittest discover -s tests -t tests -v; else echo "no unit tests for agent-run"; fi

clean:
	rm -rf dist
