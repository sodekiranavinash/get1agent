# AI Assistant — the in-product assistant.
#
# One deployable lives here:
#
#   dist/function.zip   the Lambda behind the two API Gateway routes, registered
#                       in backend/registry.json as `ai-assistant`. It bundles the
#                       agent framework (LangChain Deep Agents *is* the product)
#                       and the shared `core`/`data`/`retrieval` packages.
#   dist/pkg/           the same zip, unpacked, for local handler testing.
#
# `Dockerfile.dev` is **not** a deployable: it builds the local ASGI bridge
# (`main.py`) that the Floci stack runs as the `ai-assistant` compose service.
# It exists because this zip is built from the **host's** wheels, which on a Mac
# are macOS binaries a Linux Lambda container cannot import.
#
# Shared application code is copied in, not layered — the repo rule.
PACKAGES=core data retrieval
# Resolved from the Makefile's own location, because `make -C <dir>` leaves
# CURDIR at the invocation directory — a relative ../packages breaks there.
AI_ASSISTANT_DIR:=$(realpath $(CURDIR)/$(dir $(lastword $(MAKEFILE_LIST))))
PKG_ROOT:=$(AI_ASSISTANT_DIR)/../packages

# The agent framework is **in** the zip: it is what the Lambda runs. What is
# dropped is anything the Lambda runtime already provides (boto3/botocore and
# their transitive deps are ~28 MB of dead weight) plus the ASGI server, which
# only the local development image needs — `Dockerfile.dev` installs it from
# the dev dependency group, where it costs a deploy nothing.
RUNTIME_EXCLUDE=boto3 botocore s3transfer jmespath fastapi uvicorn starlette

package:
	rm -rf dist
	mkdir -p dist/unpacked
	cp handler.py dist/unpacked/
	cp -R src dist/unpacked/
	rm -rf dist/unpacked/src/__pycache__
	for p in $(PACKAGES); do cp -R "$(PKG_ROOT)/$$p" "dist/unpacked/$$p"; done
	@if [ -d .venv ]; then \
		cp -R .venv/lib/python*/site-packages/* dist/unpacked/ ; \
		for x in $(RUNTIME_EXCLUDE); do rm -rf "dist/unpacked/$$x" "dist/unpacked/$$x"-*.dist-info; done; \
		rm -rf dist/unpacked/bin dist/unpacked/*.pth dist/unpacked/INSTALLER dist/unpacked/_virtualenv.py; \
	fi
	@# Keep the unpacked copy as `dist/pkg/` for `python -c "import handler"` checks.
	mv dist/unpacked dist/pkg
	find dist/pkg -type d -name __pycache__ -prune -exec rm -rf {} +
	find dist/pkg -type d -name "*.dist-info" -prune -exec rm -rf {} +
	find dist/pkg -type d -name tests -prune -exec rm -rf {} +
	cd dist/pkg && zip -qXr ../function.zip .
	@echo "ai-assistant zip: $$(du -h dist/function.zip | cut -f1) (unzipped $$(du -sh dist/pkg | cut -f1))"

test:
	@PYTHONPATH="$(PKG_ROOT):$(AI_ASSISTANT_DIR)" .venv/bin/python -m unittest discover -s tests -t . -v

clean:
	rm -rf dist dist-guest .venv

check-rebuild:
	@if [ -f dist/function.zip ]; then \
		latest_src="$$(find . -name '*.py' -o -name Makefile -o -name pyproject.toml 2>/dev/null | xargs ls -1t 2>/dev/null | head -1)"; \
		if [ -n "$$latest_src" ] && [ "$$latest_src" -nt dist/function.zip ]; then \
			echo "Source files newer than package in ai-assistant"; exit 0; \
		else exit 1; fi; \
	else echo "No package found in ai-assistant"; exit 0; fi
