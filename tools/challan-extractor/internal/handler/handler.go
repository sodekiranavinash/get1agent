package handler

import (
	"context"
	"errors"
	"log"
	"time"

	"get1agent/tools/challan-extractor/internal/fetch"
	"get1agent/tools/challan-extractor/internal/model"
	"get1agent/tools/challan-extractor/internal/parse"
)

type Fetcher interface {
	Get(ctx context.Context, raw string) (*fetch.Result, error)
}

type Handler struct {
	Fetch Fetcher
}

func New(f Fetcher) *Handler {
	return &Handler{Fetch: f}
}

func (h *Handler) Handle(ctx context.Context, req model.Request) (model.Response, error) {
	start := time.Now()
	rawURL := req.ResolveURL()

	res, err := h.Fetch.Get(ctx, rawURL)
	if err != nil {
		return fail(err), nil
	}

	extracted, err := parse.HTML(res.Body, res.FinalURL)
	if err != nil {
		return model.Response{
			OK:    false,
			Error: &model.ErrorBody{Code: "parse_failed", Message: "could not parse print page"},
		}, nil
	}
	if extracted.ChallanNo == "" && extracted.VehicleNo == "" {
		return model.Response{
			OK:    false,
			Error: &model.ErrorBody{Code: "parse_failed", Message: "print page missing challan and vehicle numbers"},
		}, nil
	}

	log.Printf("ok=true challanNo=%s attempts=%d durationMs=%d", extracted.ChallanNo, res.Attempts, time.Since(start).Milliseconds())

	return model.Response{
		OK:               true,
		SourceURL:        res.FinalURL,
		ExtractedChallan: extracted,
	}, nil
}

func fail(err error) model.Response {
	var v fetch.ValidationError
	if errors.As(err, &v) {
		return model.Response{OK: false, Error: &model.ErrorBody{Code: "invalid_url", Message: v.Msg}}
	}
	var f fetch.FetchError
	if errors.As(err, &f) {
		code := f.Code
		if code == "" {
			code = "fetch_failed"
		}
		return model.Response{OK: false, Error: &model.ErrorBody{Code: code, Message: f.Msg}}
	}
	return model.Response{OK: false, Error: &model.ErrorBody{Code: "fetch_failed", Message: err.Error()}}
}
