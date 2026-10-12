# Avi control plane (`POST /v1/avi/session`, `POST /v1/avi/badge`).
#
# Launches the Avi MicroVM, mints its ingress token, and signs the session token
# the agent service verifies. Node because API Gateway HTTP APIs cannot stream and
# this Lambda must stay small — it never touches the model.
DIST := $(CURDIR)/dist

package:
	rm -rf $(DIST)/lambda && mkdir -p $(DIST)/lambda
	cp index.mjs package.json $(DIST)/lambda/
	cd $(DIST)/lambda && npm install --omit=dev --no-audit --no-fund --cache $${NPM_CACHE:-/tmp/avi-npm-cache}
	rm -f $(DIST)/function.zip
	cd $(DIST)/lambda && zip -qXr ../function.zip .

test:
	@if [ -d tests ]; then node --test tests/*.test.mjs; else echo "no unit tests for avi control-plane"; fi

clean:
	rm -rf dist node_modules

check-rebuild:
	@if [ -f dist/function.zip ]; then \
		latest_src="$$(find . -name '*.mjs' -o -name Makefile -o -name package.json 2>/dev/null | xargs ls -1t 2>/dev/null | head -1)"; \
		if [ -n "$$latest_src" ] && [ "$$latest_src" -nt dist/function.zip ]; then exit 0; else exit 1; fi; \
	else exit 0; fi
