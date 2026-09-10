.PHONY: package clean

package:
	rm -rf dist
	mkdir -p dist/versions
	cp src/handler.py dist/handler.py
	cp ../migrations/alembic.ini dist/alembic.ini
	cp ../migrations/env.py dist/env.py
	cp ../migrations/script.py.mako dist/script.py.mako
	cp ../migrations/versions/*.py dist/versions/
	cd dist && zip -qXr function.zip .

clean:
	rm -rf dist
