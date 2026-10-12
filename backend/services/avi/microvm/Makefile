# Avi MicroVM image artifact.
#
# The MicroVM runs the agent container; this directory holds the Node streaming
# proxy that fronts it. `microvm.zip` is the artifact the Lambda MicroVM build
# consumes (a Dockerfile plus the server), and the Dockerfile copies the agent
# container image built from backend/avi.
DIST := $(CURDIR)/dist

package:
	rm -rf $(DIST)/microvm-build && mkdir -p $(DIST)/microvm-build
	cp app.mjs Dockerfile package.json $(DIST)/microvm-build/
	rm -f $(DIST)/microvm.zip
	cd $(DIST)/microvm-build && zip -qXr ../microvm.zip .

test:
	@if [ -d tests ]; then node --test tests/*.test.mjs; else echo "no unit tests for avi microvm"; fi

clean:
	rm -rf dist node_modules

check-rebuild:
	@if [ -f dist/microvm.zip ]; then \
		latest_src="$$(find . -name '*.mjs' -o -name Dockerfile -o -name Makefile -o -name package.json 2>/dev/null | xargs ls -1t 2>/dev/null | head -1)"; \
		if [ -n "$$latest_src" ] && [ "$$latest_src" -nt dist/microvm.zip ]; then exit 0; else exit 1; fi; \
	else exit 0; fi
