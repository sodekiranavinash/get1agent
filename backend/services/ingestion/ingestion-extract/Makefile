PACKAGES=core data retrieval ingestion prompts
PKG_ROOT=../../../packages

# Native wheels (pymupdf, lxml) must match the **Lambda's** runtime, which is
# arm64 — not the build host. On macOS a plain `uv sync` installs Mach-O binaries
# ("invalid ELF header" inside a Linux container) and on an x86_64 CI runner it
# installs x86_64 manylinux wheels, which the arm64 Lambda cannot import — so the
# target is pinned everywhere instead of only on Darwin. Override it for the one
# case that needs a different target: a developer on x86_64 Linux whose local
# Floci Lambda containers are x86_64 (`make package DEP_PLATFORM=x86_64-manylinux_2_28`).
DEP_PLATFORM ?= aarch64-manylinux_2_28

package:
	rm -rf dist
	mkdir -p dist
	cp handler.py dist/
	@if [ -d src ]; then cp -R src dist/; fi
	for p in $(PACKAGES); do cp -R "$(PKG_ROOT)/$$p" "dist/$$p"; done
	# Install Python dependencies into site-packages, resolved for the Lambda's
	# platform rather than the build host's.
	if [ -f pyproject.toml ]; then \
		uv export --project . --no-dev --format requirements-txt --no-hashes --no-emit-project -o .requirements.txt --quiet || { echo "uv export failed" >&2; exit 1; }; \
		uv pip install --target dist --python-platform $(DEP_PLATFORM) --python-version 3.14 -r .requirements.txt --quiet || { echo "uv pip install (native wheels) failed" >&2; exit 1; }; \
		rm -f .requirements.txt; \
		rm -rf dist/bin dist/*.pth dist/INSTALLER dist/_virtualenv.py; \
	fi
	find dist -type d -name __pycache__ -prune -exec rm -rf {} +
	find dist -type d -name "*.dist-info" -prune -exec rm -rf {} +
	find dist -type d -name "tests" -prune -exec rm -rf {} +
	cd dist && zip -qXr function.zip .

# Unit tests live in ./tests (stdlib unittest). No-op when the app has none.
test:
	@if [ -d tests ]; then PYTHONPATH="$(PKG_ROOT):." uv run --project . --python 3.14 python -m unittest discover -s tests -t tests -v; else echo "no unit tests for $(notdir $(CURDIR))"; fi

clean:
	rm -rf dist .venv

# Check if source files are newer than package
check-rebuild:
	@if [ -f dist/function.zip ]; then \
		latest_src="$$(find . -name "*.py" -o -name "*.js" -o -name "*.mjs" -o -name "Makefile" -o -name "pyproject.toml" 2>/dev/null | xargs ls -1t 2>/dev/null | head -1)"; \
		if [ -n "$$latest_src" ] && [ "$$latest_src" -nt dist/function.zip ]; then \
			echo "Source files newer than package in $(basename $(PWD))"; \
			exit 0; \
		else \
			exit 1; \
		fi; \
	else \
		echo "No package found in $(basename $(PWD))"; \
		exit 0; \
	fi
