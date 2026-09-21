.PHONY: package package-lambda package-microvm test clean

# Two artifacts:
#  * function.zip — the control-plane Lambda (Function URL): verifies the Auth0
#    token and mints the MicroVM ingress token. Bundles its AWS SDK dep.
#  * microvm.zip  — the Dockerfile + streaming server that Lambda builds into a
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
	rm -rf $(DIST)/microvm && mkdir -p $(DIST)/microvm
	cp proxy.mjs $(DIST)/microvm/
	cp microvm/app.mjs microvm/Dockerfile microvm/package.json $(DIST)/microvm/
	rm -f $(DIST)/microvm.zip
	cd $(DIST)/microvm && zip -qXr ../microvm.zip .

test:
	node --test tests/*.test.mjs

clean:
	rm -rf dist
