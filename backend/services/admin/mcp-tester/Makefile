.PHONY: package clean

# No third-party dependencies: the MCP client and auth helpers live in the `ai`
# layer, boto3 comes from the Lambda runtime.
package:
	rm -rf dist
	mkdir -p dist
	cp src/handler.py dist/handler.py
	cd dist && zip -qX function.zip handler.py

clean:
	rm -rf dist
