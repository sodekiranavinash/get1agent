.PHONY: package clean

package:
	rm -rf dist
	mkdir -p dist
	cp src/handler.py dist/handler.py
	cd dist && zip -qX function.zip handler.py

clean:
	rm -rf dist
