package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"

	"get1agent/tools/challan-extractor/internal/fetch"
	"get1agent/tools/challan-extractor/internal/handler"
	"get1agent/tools/challan-extractor/internal/model"
)

func main() {
	eventPath := flag.String("event", "event.json", "Lambda event JSON file")
	timeout := flag.Duration("timeout", 25*time.Second, "overall invoke timeout")
	flag.Parse()

	raw, err := os.ReadFile(*eventPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read event: %v\n", err)
		os.Exit(1)
	}

	var req model.Request
	if err := json.Unmarshal(raw, &req); err != nil {
		fmt.Fprintf(os.Stderr, "parse event: %v\n", err)
		os.Exit(1)
	}

	ctx, cancel := context.WithTimeout(context.Background(), *timeout)
	defer cancel()

	h := handler.New(fetch.New(fetch.ConfigFromEnv()))
	resp, err := h.Handle(ctx, req)
	if err != nil {
		fmt.Fprintf(os.Stderr, "invoke: %v\n", err)
		os.Exit(1)
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(resp); err != nil {
		fmt.Fprintf(os.Stderr, "encode: %v\n", err)
		os.Exit(1)
	}
	if !resp.OK {
		os.Exit(2)
	}
}
