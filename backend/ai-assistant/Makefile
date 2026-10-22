# AI Assistant — the in-product assistant.
#
# One deployable lives here:
#
#   dist/function.zip   the Lambda behind the two API Gateway routes, registered
#                       in backend/registry.json as `ai-assistant`. It bundles the
#                       agent framework (LangChain Deep Agents *is* the product)
#                       and the shared `core`/`data`/`retrieval` packages.
#   dist/pkg/           the same zip, unpacked, for inspection.
#
# `Dockerfile.dev` is **not** a deployable: it builds the local ASGI bridge
# (`main.py`) that the Floci stack runs as the `ai-assistant` compose service,
# with `uvicorn`/`fastapi` from the dev dependency group — which the zip below
# excludes, along with everything they would pull in.
#
# Shared application code is copied in, not layered — the repo rule.
PACKAGES=core data retrieval prompts
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

# The function is **arm64** (registry.json / the deploy module), while the build
# host need not be: CI runs on x86_64 Linux and a developer's Mac is
# arm64-darwin. A plain `uv sync` copies *host* wheels — `orjson.cpython-313-
# darwin.so` on a Mac, `*-x86_64-linux-gnu.so` on the runner — and the native
# dependencies here (pydantic-core, cryptography, numpy, orjson, …) then fail to
# import inside the Lambda. So dependencies are resolved for the Lambda's own
# platform instead, the same way `ingestion-extract` installs its pymupdf/lxml
# wheels, and a wrong-platform wheel in the result is a build failure.
LAMBDA_PLATFORM := aarch64-manylinux_2_28
LAMBDA_PYTHON := 3.13

# Host-platform resolution, used by `test` only: the unit suite runs on the build
# machine, so it wants host wheels — the zip below deliberately does not.
sync-deps:
	uv sync --project . --quiet --python $(LAMBDA_PYTHON) \
		|| { echo "uv sync failed — dependencies were not installed" >&2; exit 1; }

# Dependencies are bundled, not layered, and the zip is built on a **fresh CI
# runner where `.venv` does not exist** (nothing syncs it for this app: it lives
# outside `backend/services/*`, so neither `make test-unit` nor the per-service
# packaging steps reach it). The old `@if [ -d .venv ]` guard made that *silent*:
# the zip shipped with no site-packages at all — no LangChain, no `redis` — and
# still passed the `unzip -l | grep handler.py` check that gates the apply.
package:
	rm -rf dist
	mkdir -p dist/unpacked
	cp handler.py dist/unpacked/
	cp -R src dist/unpacked/
	rm -rf dist/unpacked/src/__pycache__
	for p in $(PACKAGES); do cp -R "$(PKG_ROOT)/$$p" "dist/unpacked/$$p"; done
	uv export --project . --no-dev --format requirements-txt --no-hashes --no-emit-project -o dist/requirements.txt --quiet \
		|| { echo "uv export failed — dependencies were not resolved" >&2; exit 1; }
	uv pip install --target dist/unpacked --python-platform $(LAMBDA_PLATFORM) --python-version $(LAMBDA_PYTHON) -r dist/requirements.txt --quiet \
		|| { echo "uv pip install failed — dependencies were not installed" >&2; exit 1; }
	rm -f dist/requirements.txt
	for x in $(RUNTIME_EXCLUDE); do rm -rf "dist/unpacked/$$x" "dist/unpacked/$$x"-*.dist-info; done
	rm -rf dist/unpacked/bin dist/unpacked/*.pth dist/unpacked/INSTALLER dist/unpacked/_virtualenv.py
	@# Import-time proof that the bundle is complete: the framework *is* the
	@# product and `redis` backs the exact cache, the semantic cache and the
	@# limiter, so a zip missing either one is not deployable.
	@for mod in deepagents redis; do \
		[ -d "dist/unpacked/$$mod" ] || { echo "$$mod missing from the zip — dependencies were not bundled" >&2; exit 1; }; \
	done
	@# ...and every native module has to be the Lambda's, or the breakage only
	@# shows up on the first invocation, after the apply has already gone green.
	@bad="$$(find dist/unpacked \( -name '*darwin*.so' -o -name '*.dylib' -o -name '*x86_64*linux*.so' \) -print | head -5)"; \
	[ -z "$$bad" ] || { echo "host-platform wheels in the zip — expected $(LAMBDA_PLATFORM):" >&2; echo "$$bad" >&2; exit 1; }
	@# A build stamp, so no two builds are byte-identical. Terraform compares
	@# `source_code_hash` with what the last apply recorded, not with what AWS is
	@# actually running: a reproducible zip plus any out-of-band code change (or a
	@# deploy that was replaced by hand) then plans "no change" and leaves the
	@# Lambda on old code indefinitely — which is exactly what happened here.
	@printf '{"commit":"%s","builtAt":"%s"}\n' \
		"$$(git rev-parse --short HEAD 2>/dev/null || echo unknown)" \
		"$$(date -u +%Y-%m-%dT%H:%M:%SZ)" > dist/unpacked/build-info.json
	@# Keep the unpacked copy as `dist/pkg/`, which is also the zip's source.
	mv dist/unpacked dist/pkg
	find dist/pkg -type d -name __pycache__ -prune -exec rm -rf {} +
	find dist/pkg -type d -name "*.dist-info" -prune -exec rm -rf {} +
	find dist/pkg -type d -name tests -prune -exec rm -rf {} +
	cd dist/pkg && zip -qXr ../function.zip .
	@echo "ai-assistant zip: $$(du -h dist/function.zip | cut -f1) (unzipped $$(du -sh dist/pkg | cut -f1))"

test: sync-deps
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
