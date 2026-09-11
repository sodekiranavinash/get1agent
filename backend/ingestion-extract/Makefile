.PHONY: package lock clean

PYTHON_VERSION := 3.14
TARGET_PLATFORM := aarch64-unknown-linux-gnu
REQ := dist/requirements.txt

package: lock
	rm -rf dist
	mkdir -p dist
	cp src/handler.py dist/handler.py
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

clean:
	rm -rf dist
