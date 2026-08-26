package handler

import (
	"context"
	"errors"
	"log"
	"sync"
	"time"

	"get1agent/tools/challan-extractor/internal/fetch"
	"get1agent/tools/challan-extractor/internal/model"
	"get1agent/tools/challan-extractor/internal/parse"
)

const maxConcurrent = 4

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
	urls := req.ResolveURLs()
	if len(urls) == 0 {
		return model.Response{
			OK:    false,
			Error: &model.ErrorBody{Code: "invalid_url", Message: "urls is required"},
			Items: []model.Item{},
		}, nil
	}

	items := make([]model.Item, len(urls))
	jobs := make(chan int)
	workers := maxConcurrent
	if len(urls) < workers {
		workers = len(urls)
	}
	var wg sync.WaitGroup
	for range workers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := range jobs {
				items[i] = h.extractOne(ctx, urls[i])
			}
		}()
	}
	for i := range urls {
		jobs <- i
	}
	close(jobs)
	wg.Wait()

	okCount := 0
	for _, it := range items {
		if it.OK {
			okCount++
		}
	}
	log.Printf("ok=%d/%d durationMs=%d", okCount, len(items), time.Since(start).Milliseconds())

	return model.Response{OK: true, Items: items}, nil
}

func (h *Handler) extractOne(ctx context.Context, rawURL string) model.Item {
	start := time.Now()
	res, err := h.Fetch.Get(ctx, rawURL)
	if err != nil {
		return failItem(rawURL, err)
	}

	extracted, err := parse.HTML(res.Body, res.FinalURL)
	if err != nil {
		return model.Item{
			OK:        false,
			SourceURL: res.FinalURL,
			Error:     &model.ErrorBody{Code: "parse_failed", Message: "could not parse print page"},
		}
	}
	if extracted.ChallanNo == "" && extracted.VehicleNo == "" {
		return model.Item{
			OK:        false,
			SourceURL: res.FinalURL,
			Error:     &model.ErrorBody{Code: "parse_failed", Message: "print page missing challan and vehicle numbers"},
		}
	}

	log.Printf("ok=true challanNo=%s attempts=%d durationMs=%d", extracted.ChallanNo, res.Attempts, time.Since(start).Milliseconds())

	return model.Item{
		OK:               true,
		SourceURL:        res.FinalURL,
		ExtractedChallan: extracted,
	}
}

func failItem(sourceURL string, err error) model.Item {
	item := model.Item{OK: false, SourceURL: sourceURL}
	var v fetch.ValidationError
	if errors.As(err, &v) {
		item.Error = &model.ErrorBody{Code: "invalid_url", Message: v.Msg}
		return item
	}
	var f fetch.FetchError
	if errors.As(err, &f) {
		code := f.Code
		if code == "" {
			code = "fetch_failed"
		}
		item.Error = &model.ErrorBody{Code: code, Message: f.Msg}
		return item
	}
	item.Error = &model.ErrorBody{Code: "fetch_failed", Message: err.Error()}
	return item
}
