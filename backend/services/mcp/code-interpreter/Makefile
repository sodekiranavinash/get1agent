PACKAGES=core data
PKG_ROOT=../../../packages

package:
	rm -rf dist
	mkdir -p dist
	cp handler.py dist/
	@if [ -d src ]; then cp -R src dist/; fi
	for p in $(PACKAGES); do cp -R "$(PKG_ROOT)/$$p" "dist/$$p"; done
	# Install Python dependencies into site-packages
	if [ -f pyproject.toml ]; then \
		uv sync --project . --no-dev --quiet; \
		cp -R .venv/lib/python3.14/site-packages/* dist/ 2>/dev/null || true; \
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
