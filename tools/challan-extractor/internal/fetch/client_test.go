package fetch_test

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"get1agent/tools/challan-extractor/internal/fetch"
)

func testClient(host, path string, maxBody int64, attempts int) *fetch.Client {
	cfg := fetch.DefaultConfig()
	cfg.AllowedHosts = []string{host}
	cfg.AllowedPath = path
	cfg.AllowedSchemes = []string{"http"}
	cfg.Timeout = 2 * time.Second
	if maxBody > 0 {
		cfg.MaxBodyBytes = maxBody
	}
	if attempts > 0 {
		cfg.MaxAttempts = attempts
	}
	return fetch.New(cfg)
}

func TestValidate_RejectsBadURLs(t *testing.T) {
	c := fetch.New(fetch.DefaultConfig())
	cases := []string{
		"http://echallan.parivahan.gov.in/report/print-page?challan_no=x",
		"https://evil.example/report/print-page?challan_no=x",
		"https://echallan.parivahan.gov.in/other?challan_no=x",
		"",
	}
	for _, raw := range cases {
		if _, err := c.Validate(raw); err == nil {
			t.Fatalf("expected error for %q", raw)
		} else if _, ok := err.(fetch.ValidationError); !ok {
			t.Fatalf("want ValidationError for %q, got %T %v", raw, err, err)
		}
	}
}

func TestGet_Retries429ThenSucceeds(t *testing.T) {
	var n atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if n.Add(1) == 1 {
			w.WriteHeader(http.StatusTooManyRequests)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = io.WriteString(w, "<html>ok</html>")
	}))
	t.Cleanup(srv.Close)

	u, _ := url.Parse(srv.URL)
	c := testClient(u.Hostname(), "/", 0, 3)
	c.SetSleep(func(time.Duration) {})

	res, err := c.Get(context.Background(), srv.URL+"/report/print-page?challan_no=x")
	if err != nil {
		t.Fatal(err)
	}
	if res.Attempts != 2 {
		t.Fatalf("attempts = %d", res.Attempts)
	}
	if string(res.Body) != "<html>ok</html>" {
		t.Fatalf("body = %s", res.Body)
	}
}

func TestGet_RateLimitedAfterRetries(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Retry-After", "1")
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	t.Cleanup(srv.Close)

	u, _ := url.Parse(srv.URL)
	c := testClient(u.Hostname(), "/", 0, 3)
	c.SetSleep(func(time.Duration) {})

	_, err := c.Get(context.Background(), srv.URL+"/report/print-page")
	if err == nil {
		t.Fatal("expected error")
	}
	fe, ok := err.(fetch.FetchError)
	if !ok {
		t.Fatalf("got %T %v", err, err)
	}
	if fe.Code != "rate_limited" {
		t.Fatalf("code = %s", fe.Code)
	}
	if fe.Attempts != 3 {
		t.Fatalf("attempts = %d", fe.Attempts)
	}
}

func TestGet_BodyTooLarge(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.WriteString(w, strings.Repeat("x", 64))
	}))
	t.Cleanup(srv.Close)

	u, _ := url.Parse(srv.URL)
	c := testClient(u.Hostname(), "/", 16, 1)

	_, err := c.Get(context.Background(), srv.URL+"/report/print-page")
	if err == nil {
		t.Fatal("expected error")
	}
	fe, ok := err.(fetch.FetchError)
	if !ok {
		t.Fatalf("got %T", err)
	}
	if fe.Code != "fetch_failed" {
		t.Fatalf("code = %s", fe.Code)
	}
}

func TestGet_HonorsRetryAfterCap(t *testing.T) {
	var slept time.Duration
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Retry-After", "1")
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	t.Cleanup(srv.Close)

	u, _ := url.Parse(srv.URL)
	c := testClient(u.Hostname(), "/", 0, 2)
	c.SetSleep(func(d time.Duration) { slept = d })

	_, _ = c.Get(context.Background(), srv.URL+"/report/print-page")
	if slept <= 0 {
		t.Fatal("expected sleep")
	}
	if slept > 2*time.Second {
		t.Fatalf("sleep too long: %s", slept)
	}
}
