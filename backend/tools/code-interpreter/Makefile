.PHONY: package lock clean test

PYTHON_VERSION := 3.14
TARGET_PLATFORM := aarch64-unknown-linux-gnu
REQ := dist/requirements.txt

# Bundles boto3 (for the bedrock-agentcore service model), the MCP handler and
# its one non-AWS dependency. The `ai` layer supplies the role/view checks.
package: lock
	rm -rf dist
	mkdir -p dist
	cp src/*.py dist/
	uv export --project . --no-dev --no-hashes -o "$(REQ)"
	uv pip install \
		-r "$(REQ)" \
		--python-version $(PYTHON_VERSION) \
		--python-platform $(TARGET_PLATFORM) \
		--target dist
	rm -f "$(REQ)"
	cd dist && zip -qXr function.zip .

lock:
	uv lock

test:
	python3 -m unittest discover -s tests -v

clean:
	rm -rf dist
