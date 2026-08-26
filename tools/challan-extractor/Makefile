.PHONY: test tidy package clean invoke invoke-mcp

GO ?= go
DIST := dist
BINARY := bootstrap
EVENT ?= event.json

test:
	$(GO) test ./...

tidy:
	$(GO) mod tidy

invoke:
	$(GO) run ./cmd/local -event $(EVENT)

invoke-mcp:
	$(GO) run ./cmd/local -event event-mcp.json

package: tidy test
	mkdir -p $(DIST)
	CGO_ENABLED=0 GOOS=linux GOARCH=arm64 $(GO) build -trimpath -ldflags="-s -w" -tags lambda.norpc -o $(DIST)/$(BINARY) ./cmd/bootstrap
	cd $(DIST) && zip -q function.zip $(BINARY)

clean:
	rm -rf $(DIST)
