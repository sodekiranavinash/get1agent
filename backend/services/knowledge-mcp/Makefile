.PHONY: package clean

PYTHON_VERSION := 3.14
TARGET_PLATFORM := aarch64-unknown-linux-gnu
MCP_HANDLER_VERSION := 0.1.15

# boto3/botocore come from the Lambda runtime; only the MCP handler and its one
# non-AWS dependency are bundled.
package:
	rm -rf dist
	mkdir -p dist
	cp src/handler.py dist/handler.py
	uv pip install \
		--python-version $(PYTHON_VERSION) \
		--python-platform $(TARGET_PLATFORM) \
		--target dist \
		--no-deps \
		"awslabs.mcp-lambda-handler==$(MCP_HANDLER_VERSION)" \
		"python-dateutil>=2.8.2"
	cd dist && zip -qXr function.zip .

clean:
	rm -rf dist
