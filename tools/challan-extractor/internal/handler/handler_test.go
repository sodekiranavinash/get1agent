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

func TestHandle_UnwrapsArgumentsURLs(t *testing.T) {
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
		Arguments: &model.Request{URLs: []string{inner}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if !resp.OK {
		t.Fatalf("not ok: %+v", resp.Error)
	}
	if len(resp.Items) != 1 || resp.Items[0].ChallanNo != "AP186219260426195306" {
		t.Fatalf("items = %+v", resp.Items)
	}
}

func TestHandle_LegacyURL(t *testing.T) {
	html, err := os.ReadFile(filepath.Join("..", "..", "testdata", "print-page.html"))
	if err != nil {
		t.Fatal(err)
	}
	h := handler.New(stubFetch{res: &fetch.Result{
		Body:     html,
		Attempts: 1,
		FinalURL: "https://echallan.parivahan.gov.in/report/print-page?challan_no=token",
	}})
	resp, err := h.Handle(context.Background(), model.Request{
		URL: "https://echallan.parivahan.gov.in/report/print-page?challan_no=token",
	})
	if err != nil {
		t.Fatal(err)
	}
	if !resp.OK || len(resp.Items) != 1 || !resp.Items[0].OK {
		t.Fatalf("%+v", resp)
	}
}

func TestHandle_MultipleURLsKeepsOrder(t *testing.T) {
	html, err := os.ReadFile(filepath.Join("..", "..", "testdata", "print-page.html"))
	if err != nil {
		t.Fatal(err)
	}
	good := "https://echallan.parivahan.gov.in/report/print-page?challan_no=ok"
	bad := "https://echallan.parivahan.gov.in/report/print-page?challan_no=bad"
	h := handler.New(mapFetch{byURL: map[string]fetchOutcome{
		good: {res: &fetch.Result{Body: html, Attempts: 1, FinalURL: good}},
		bad:  {err: fetch.ValidationError{Msg: "host not allowed"}},
	}})
	resp, err := h.Handle(context.Background(), model.Request{URLs: []string{good, bad}})
	if err != nil {
		t.Fatal(err)
	}
	if !resp.OK || len(resp.Items) != 2 {
		t.Fatalf("%+v", resp)
	}
	if !resp.Items[0].OK || resp.Items[0].ChallanNo != "AP186219260426195306" {
		t.Fatalf("item0 %+v", resp.Items[0])
	}
	if resp.Items[1].OK || resp.Items[1].Error == nil || resp.Items[1].Error.Code != "invalid_url" {
		t.Fatalf("item1 %+v", resp.Items[1])
	}
}

func TestHandle_MissingURLs(t *testing.T) {
	h := handler.New(stubFetch{})
	resp, err := h.Handle(context.Background(), model.Request{})
	if err != nil {
		t.Fatal(err)
	}
	if resp.OK || resp.Error == nil || resp.Error.Code != "invalid_url" {
		t.Fatalf("%+v", resp)
	}
}

func TestHandle_InvalidURL(t *testing.T) {
	h := handler.New(stubFetch{err: fetch.ValidationError{Msg: "host not allowed"}})
	resp, err := h.Handle(context.Background(), model.Request{URL: "https://evil.example/report/print-page"})
	if err != nil {
		t.Fatal(err)
	}
	if !resp.OK || len(resp.Items) != 1 {
		t.Fatalf("%+v", resp)
	}
	item := resp.Items[0]
	if item.OK || item.Error == nil || item.Error.Code != "invalid_url" {
		t.Fatalf("%+v", item)
	}
}

func TestHandle_RateLimited(t *testing.T) {
	h := handler.New(stubFetch{err: fetch.FetchError{Code: "rate_limited", Msg: "origin rate limited", Attempts: 3}})
	resp, err := h.Handle(context.Background(), model.Request{URL: "https://echallan.parivahan.gov.in/report/print-page?challan_no=x"})
	if err != nil {
		t.Fatal(err)
	}
	if !resp.OK || len(resp.Items) != 1 {
		t.Fatalf("%+v", resp)
	}
	item := resp.Items[0]
	if item.OK || item.Error == nil || item.Error.Code != "rate_limited" {
		t.Fatalf("%+v", item)
	}
}

func TestHandle_ParseFailedWhenEmpty(t *testing.T) {
	h := handler.New(stubFetch{res: &fetch.Result{Body: []byte("<html><body>nope</body></html>"), FinalURL: "https://echallan.parivahan.gov.in/report/print-page"}})
	resp, err := h.Handle(context.Background(), model.Request{URL: "https://echallan.parivahan.gov.in/report/print-page"})
	if err != nil {
		t.Fatal(err)
	}
	if !resp.OK || len(resp.Items) != 1 {
		t.Fatalf("%+v", resp)
	}
	item := resp.Items[0]
	if item.OK || item.Error == nil || item.Error.Code != "parse_failed" {
		t.Fatalf("%+v", item)
	}
}

type fetchOutcome struct {
	res *fetch.Result
	err error
}

type mapFetch struct {
	byURL map[string]fetchOutcome
}

func (m mapFetch) Get(ctx context.Context, raw string) (*fetch.Result, error) {
	o, ok := m.byURL[raw]
	if !ok {
		return nil, fetch.ValidationError{Msg: "unexpected url"}
	}
	return o.res, o.err
}
