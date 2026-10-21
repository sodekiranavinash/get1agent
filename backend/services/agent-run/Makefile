.PHONY: package package-lambda package-microvm test clean check-rebuild

# Two artifacts:
#  * function.zip — the control-plane Lambda (`POST /v1/agent-run/session`):
#    launches a MicroVM and mints its ingress token. Bundles its AWS SDK dep.
#  * microvm.zip  — the Dockerfile + streaming server Lambda builds into a
#    MicroVM image (runs up to 8 hours, unlike the 15-minute Function cap).
DIST := $(CURDIR)/dist

package: package-lambda package-microvm

# Install from the committed lockfile (`npm ci`), never a fresh resolve.
#
# `npm install` with no lockfile re-resolves the registry on every build. The
# AWS SDK publishes dozens of versions a day, and when the `latest` dist-tag
# briefly points at a version the registry has not replicated yet the install
# dies with a bare `ETARGET No matching version found for ` (the failure CI hit
# on 2026-10-21 — unreproducible, because the tag had moved on by the time it
# was looked at). `npm ci` installs exactly the tree in package-lock.json, so a
# build either uses the reviewed versions or fails loudly about the lockfile.
package-lambda:
	@test -f package-lock.json || { echo "package-lock.json is required: run npm install and commit it" >&2; exit 1; }
	rm -rf $(DIST)/lambda && mkdir -p $(DIST)/lambda
	cp index.mjs package.json package-lock.json $(DIST)/lambda/
	cd $(DIST)/lambda && npm ci --omit=dev --no-audit --no-fund \
		--fetch-retries=5 --fetch-retry-maxtimeout=60000
	@test -f $(DIST)/lambda/node_modules/@aws-sdk/client-lambda-microvms/package.json \
		|| { echo "npm install produced no @aws-sdk/client-lambda-microvms — refusing to ship a zip without its dependency" >&2; exit 1; }
	rm -f $(DIST)/function.zip
	cd $(DIST)/lambda && zip -qXr ../function.zip .

package-microvm:
	rm -rf $(DIST)/microvm-build && mkdir -p $(DIST)/microvm-build
	cp proxy.mjs $(DIST)/microvm-build/
	cp microvm/app.mjs microvm/Dockerfile microvm/package.json microvm/package-lock.json $(DIST)/microvm-build/
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
		latest_src="$$(find . \( -name '*.mjs' -o -name 'Makefile' -o -name 'package.json' -o -name 'package-lock.json' -o -name 'Dockerfile' \) 2>/dev/null | xargs ls -1t 2>/dev/null | head -1)"; \
		if [ -n "$$latest_src" ] && [ "$$latest_src" -nt dist/function.zip ]; then \
			exit 0; \
		else \
			exit 1; \
		fi; \
	else \
		exit 0; \
	fi
