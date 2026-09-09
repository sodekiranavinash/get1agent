.PHONY: test build zip package clean

package: build zip

test:
	npm run test

build:
	npm ci
	npm run build
	TZ=UTC touch -t 198001010000 dist/index.js

zip:
	npm run zip

clean:
	rm -rf dist node_modules
