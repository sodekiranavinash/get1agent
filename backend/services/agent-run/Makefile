.PHONY: package package-lambda package-microvm test clean check-rebuild

# Two artifacts:
#  * function.zip — the control-plane Lambda (`POST /v1/agent-run/session`):
#    launches a MicroVM and mints its ingress token. Bundles its AWS SDK dep.
#  * microvm.zip  — the Dockerfile + streaming server Lambda builds into a
#    MicroVM image (runs up to 8 hours, unlike the 15-minute Function cap).
DIST := $(CURDIR)/dist

package: package-lambda package-microvm

package-lambda:
	rm -rf $(DIST)/lambda && mkdir -p $(DIST)/lambda
	cp index.mjs package.json $(DIST)/lambda/
	cd $(DIST)/lambda && npm install --omit=dev --no-audit --no-fund
	rm -f $(DIST)/function.zip
	cd $(DIST)/lambda && zip -qXr ../function.zip .

package-microvm:
	rm -rf $(DIST)/microvm-build && mkdir -p $(DIST)/microvm-build
	cp proxy.mjs $(DIST)/microvm-build/
	cp microvm/app.mjs microvm/Dockerfile microvm/package.json $(DIST)/microvm-build/
	rm -f $(DIST)/microvm.zip
	cd $(DIST)/microvm-build && zip -qXr ../microvm.zip .

# Unit tests
test:
	node --test tests/*.test.mjs

clean:
	rm -rf dist node_modules

# True when a source file is newer than the built artifact (used by tooling).
check-rebuild:
	@if [ -f dist/function.zip ]; then \
		latest_src="$$(find . -name '*.mjs' -o -name 'Makefile' -o -name 'package.json' -o -name 'package-lock.json' 2>/dev/null | xargs ls -1t 2>/dev/null | head -1)"; \
		if [ -n "$$latest_src" ] && [ "$$latest_src" -nt dist/function.zip ]; then \
			exit 0; \
		else \
			exit 1; \
		fi; \
	else \
		exit 0; \
	fi
