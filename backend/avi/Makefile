# Avi — the in-product assistant.
#
# Two deployable artifacts live here plus a container:
#
#   dist/function.zip   the stateless **guest** Lambda (registered in
#                       backend/registry.json as `avi-guest`, Python). LangChain is
#                       deliberately NOT installed for it: the guest path is a
#                       single direct model call, so the zip and the cold start
#                       stay small. `avi/agent.py` imports the framework lazily
#                       precisely so this works, and tests/test_guest_packaging.py
#                       fails the build if that ever regresses.
#   dist/avi/           the same zip, unpacked, for local handler testing.
#   ../services/avi/*   the control-plane Lambda, the MicroVM proxy and the
#                       container image (see their own Makefiles and Dockerfile).
#
# Shared application code is copied in, not layered — the repo rule.
PACKAGES=core data retrieval
# Resolved from the Makefile's own location, because `make -C <dir>` leaves
# CURDIR at the invocation directory — a relative ../packages breaks there.
AVI_DIR:=$(realpath $(CURDIR)/$(dir $(lastword $(MAKEFILE_LIST))))
PKG_ROOT:=$(AVI_DIR)/../packages

# Everything the guest path must never need: an agent framework, the other
# provider SDKs, and a numerical stack. `numpy` matters because langchain-aws
# depends on it, so excluding it is what keeps the zip near 25 MB rather than 90.
GUEST_EXCLUDE=langchain langchain_core langchain_aws langchain_anthropic \
	langchain_google_genai langchain_community langgraph langgraph_sdk \
	langgraph_checkpoint langgraph_prebuilt langgraph_checkpoint_sqlite \
	deepagents langsmith anthropic google numpy aws_sdk_bedrock_runtime \
	aws_bedrock_token_generator

package:
	rm -rf dist
	mkdir -p dist/unpacked
	cp handler.py dist/unpacked/
	cp -R avi dist/unpacked/
	rm -rf dist/unpacked/avi/__pycache__
	for p in $(PACKAGES); do cp -R "$(PKG_ROOT)/$$p" "dist/unpacked/$$p"; done
	@if [ -d .venv ]; then \
		cp -R .venv/lib/python*/site-packages/* dist/unpacked/ ; \
		for x in $(GUEST_EXCLUDE); do rm -rf "dist/unpacked/$$x" "dist/unpacked/$$x"-*.dist-info; done; \
		rm -rf dist/unpacked/bin dist/unpacked/*.pth dist/unpacked/INSTALLER dist/unpacked/_virtualenv.py; \
	fi
	@# Keep the unpacked copy as `dist/avi/` for `python -c "import handler"` checks.
	mv dist/unpacked dist/avi
	find dist/avi -type d -name __pycache__ -prune -exec rm -rf {} +
	find dist/avi -type d -name "*.dist-info" -prune -exec rm -rf {} +
	find dist/avi -type d -name tests -prune -exec rm -rf {} +
	cd dist/avi && zip -qXr ../function.zip .
	@echo "avi-guest zip: $$(du -h dist/function.zip | cut -f1) (unzipped $$(du -sh dist/avi | cut -f1))"

test:
	@PYTHONPATH="$(PKG_ROOT):$(AVI_DIR)" .venv/bin/python -m unittest discover -s tests -t . -v

clean:
	rm -rf dist dist-guest .venv

check-rebuild:
	@if [ -f dist/function.zip ]; then \
		latest_src="$$(find . -name '*.py' -o -name Makefile -o -name pyproject.toml 2>/dev/null | xargs ls -1t 2>/dev/null | head -1)"; \
		if [ -n "$$latest_src" ] && [ "$$latest_src" -nt dist/function.zip ]; then \
			echo "Source files newer than package in avi"; exit 0; \
		else exit 1; fi; \
	else echo "No package found in avi"; exit 0; fi
