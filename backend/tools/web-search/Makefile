.PHONY: package clean test

PYTHON_VERSION := 3.14
TARGET_PLATFORM := aarch64-unknown-linux-gnu
MCP_HANDLER_VERSION := 0.1.15

# Bundles the MCP handler (and its one non-AWS dependency); the `ai` layer
# supplies the role/view checks and the shared MCP transport.
package:
	rm -rf dist
	mkdir -p dist
	cp src/*.py dist/
	uv pip install \
		--python-version $(PYTHON_VERSION) \
		--python-platform $(TARGET_PLATFORM) \
		--target dist \
		--no-deps \
		"awslabs.mcp-lambda-handler==$(MCP_HANDLER_VERSION)" \
		"python-dateutil>=2.8.2"
	cd dist && zip -qXr function.zip .

test:
	python3 -m unittest discover -s tests -v

clean:
	rm -rf dist
