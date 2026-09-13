.PHONY: build clean

# The `ai` layer has no third-party dependencies: it ships only our own
# lightweight Python package (stdlib + boto3 from the Lambda runtime).
LAYER_DIR := $(CURDIR)
DIST := $(LAYER_DIR)/dist/python

build:
	rm -rf "$(LAYER_DIR)/dist"
	mkdir -p "$(DIST)"
	cp -R "$(LAYER_DIR)/ai" "$(DIST)/"
	cd "$(LAYER_DIR)/dist" && zip -qXr layer.zip python

clean:
	rm -rf dist
