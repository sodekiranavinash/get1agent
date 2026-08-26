package handler_test

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"get1agent/tools/challan-extractor/internal/fetch"
	"get1agent/tools/challan-extractor/internal/handler"
	"get1agent/tools/challan-extractor/internal/model"
)

type stubFetch struct {
	res *fetch.Result
	err error
}

func (s stubFetch) Get(ctx context.Context, raw string) (*fetch.Result, error) {
	return s.res, s.err
}

func TestHandle_UnwrapsArgumentsURL(t *testing.T) {
	html, err := os.ReadFile(filepath.Join("..", "..", "testdata", "print-page.html"))
	if err != nil {
		t.Fatal(err)
	}
	h := handler.New(stubFetch{res: &fetch.Result{
		Body:     html,
		Attempts: 1,
		FinalURL: "https://echallan.parivahan.gov.in/report/print-page?challan_no=token",
	}})

	inner := "https://echallan.parivahan.gov.in/report/print-page?challan_no=token"
	resp, err := h.Handle(context.Background(), model.Request{
		Arguments: &model.Request{URL: inner},
	})
	if err != nil {
		t.Fatal(err)
	}
	if !resp.OK {
		t.Fatalf("not ok: %+v", resp.Error)
	}
	if resp.ChallanNo != "AP186219260426195306" {
		t.Fatalf("challanNo = %s", resp.ChallanNo)
	}
}

func TestHandle_InvalidURL(t *testing.T) {
	h := handler.New(stubFetch{err: fetch.ValidationError{Msg: "host not allowed"}})
	resp, err := h.Handle(context.Background(), model.Request{URL: "https://evil.example/report/print-page"})
	if err != nil {
		t.Fatal(err)
	}
	if resp.OK || resp.Error == nil || resp.Error.Code != "invalid_url" {
		t.Fatalf("%+v", resp)
	}
}

func TestHandle_RateLimited(t *testing.T) {
	h := handler.New(stubFetch{err: fetch.FetchError{Code: "rate_limited", Msg: "origin rate limited", Attempts: 3}})
	resp, err := h.Handle(context.Background(), model.Request{URL: "https://echallan.parivahan.gov.in/report/print-page?challan_no=x"})
	if err != nil {
		t.Fatal(err)
	}
	if resp.OK || resp.Error == nil || resp.Error.Code != "rate_limited" {
		t.Fatalf("%+v", resp)
	}
}

func TestHandle_ParseFailedWhenEmpty(t *testing.T) {
	h := handler.New(stubFetch{res: &fetch.Result{Body: []byte("<html><body>nope</body></html>"), FinalURL: "https://echallan.parivahan.gov.in/report/print-page"}})
	resp, err := h.Handle(context.Background(), model.Request{URL: "https://echallan.parivahan.gov.in/report/print-page"})
	if err != nil {
		t.Fatal(err)
	}
	if resp.OK || resp.Error == nil || resp.Error.Code != "parse_failed" {
		t.Fatalf("%+v", resp)
	}
}
