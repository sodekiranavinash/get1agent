.PHONY: package test clean

# Bundles the app's handler + src/ + the shared packages it uses.
# Third-party deps ship in the attached layers, not in this zip.
PACKAGES := core data retrieval
PKG_ROOT := $(CURDIR)/../../packages

package:
	rm -rf dist
	mkdir -p dist
	cp handler.py dist/
	@if [ -d src ]; then cp -R src dist/; fi
	for p in $(PACKAGES); do cp -R "$(PKG_ROOT)/$$p" "dist/$$p"; done
	find dist -type d -name __pycache__ -prune -exec rm -rf {} +
	cd dist && zip -qXr function.zip .

# Unit tests live in ./tests (stdlib unittest). No-op when the app has none.
test:
	@if [ -d tests ]; then uv run --no-project --python 3.14 python -m unittest discover -s tests -t tests -v; else echo "no unit tests for $(notdir $(CURDIR))"; fi

clean:
	rm -rf dist
