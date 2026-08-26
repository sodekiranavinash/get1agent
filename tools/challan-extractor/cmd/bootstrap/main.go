package main

import (
	"context"

	"github.com/aws/aws-lambda-go/lambda"

	"get1agent/tools/challan-extractor/internal/fetch"
	"get1agent/tools/challan-extractor/internal/handler"
	"get1agent/tools/challan-extractor/internal/model"
)

func main() {
	h := handler.New(fetch.New(fetch.ConfigFromEnv()))
	lambda.Start(func(ctx context.Context, req model.Request) (model.Response, error) {
		return h.Handle(ctx, req)
	})
}
