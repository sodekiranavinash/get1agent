package fetch

import (
	"context"
	"crypto/rand"
	"crypto/tls"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

const defaultAllowedHost = "echallan.parivahan.gov.in"
const defaultAllowedPathPrefix = "/report/print-page"

type Config struct {
	Timeout        time.Duration
	MaxAttempts    int
	MaxBodyBytes   int64
	AllowedHosts   []string
	AllowedPath    string
	AllowedSchemes []string
	UserAgent      string
}

func DefaultConfig() Config {
	return Config{
		Timeout:        10 * time.Second,
		MaxAttempts:    3,
		MaxBodyBytes:   2 << 20,
		AllowedHosts:   []string{defaultAllowedHost},
		AllowedPath:    defaultAllowedPathPrefix,
		AllowedSchemes: []string{"https"},
		UserAgent:      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
	}
}

func ConfigFromEnv() Config {
	cfg := DefaultConfig()
	if v := os.Getenv("HTTP_TIMEOUT_MS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			cfg.Timeout = time.Duration(n) * time.Millisecond
		}
	}
	if v := os.Getenv("HTTP_MAX_ATTEMPTS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			cfg.MaxAttempts = n
		}
	}
	if v := os.Getenv("HTTP_MAX_BODY_BYTES"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			cfg.MaxBodyBytes = int64(n)
		}
	}
	if v := os.Getenv("ALLOWED_HOSTS"); v != "" {
		parts := strings.Split(v, ",")
		hosts := make([]string, 0, len(parts))
		for _, p := range parts {
			p = strings.TrimSpace(p)
			if p != "" {
				hosts = append(hosts, p)
			}
		}
		if len(hosts) > 0 {
			cfg.AllowedHosts = hosts
		}
	}
	return cfg
}

type Result struct {
	Body       []byte
	StatusCode int
	Attempts   int
	FinalURL   string
}

type Client struct {
	cfg        Config
	httpClient *http.Client
	sleep      func(time.Duration)
}

func (c *Client) SetSleep(fn func(time.Duration)) {
	if fn != nil {
		c.sleep = fn
	}
}

func New(cfg Config) *Client {
	if cfg.Timeout <= 0 {
		cfg.Timeout = DefaultConfig().Timeout
	}
	if cfg.MaxAttempts <= 0 {
		cfg.MaxAttempts = DefaultConfig().MaxAttempts
	}
	if cfg.MaxBodyBytes <= 0 {
		cfg.MaxBodyBytes = DefaultConfig().MaxBodyBytes
	}
	if len(cfg.AllowedHosts) == 0 {
		cfg.AllowedHosts = DefaultConfig().AllowedHosts
	}
	if cfg.AllowedPath == "" {
		cfg.AllowedPath = DefaultConfig().AllowedPath
	}
	if len(cfg.AllowedSchemes) == 0 {
		cfg.AllowedSchemes = DefaultConfig().AllowedSchemes
	}
	if cfg.UserAgent == "" {
		cfg.UserAgent = DefaultConfig().UserAgent
	}

	c := &Client{cfg: cfg, sleep: time.Sleep}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.ForceAttemptHTTP2 = false
	transport.TLSNextProto = map[string]func(authority string, c *tls.Conn) http.RoundTripper{}
	transport.TLSHandshakeTimeout = cfg.Timeout
	transport.ResponseHeaderTimeout = cfg.Timeout
	c.httpClient = &http.Client{
		Timeout:   0, // per-attempt deadline is applied on the request context
		Transport: transport,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) >= 3 {
				return errors.New("too many redirects")
			}
			if err := c.validateURL(req.URL); err != nil {
				return err
			}
			return nil
		},
	}
	return c
}

type ValidationError struct{ Msg string }

func (e ValidationError) Error() string { return e.Msg }

type FetchError struct {
	Code       string
	Msg        string
	StatusCode int
	Attempts   int
}

func (e FetchError) Error() string { return e.Msg }

func (c *Client) Validate(raw string) (*url.URL, error) {
	if raw == "" {
		return nil, ValidationError{Msg: "url is required"}
	}
	if len(raw) > 2048 {
		return nil, ValidationError{Msg: "url exceeds 2048 characters"}
	}
	u, err := url.Parse(raw)
	if err != nil {
		return nil, ValidationError{Msg: "url is not valid"}
	}
	if err := c.validateURL(u); err != nil {
		return nil, err
	}
	return u, nil
}

func (c *Client) validateURL(u *url.URL) error {
	schemeOK := false
	for _, s := range c.cfg.AllowedSchemes {
		if strings.EqualFold(u.Scheme, s) {
			schemeOK = true
			break
		}
	}
	if !schemeOK {
		return ValidationError{Msg: "url must use https"}
	}
	host := strings.ToLower(u.Hostname())
	okHost := false
	for _, h := range c.cfg.AllowedHosts {
		if host == strings.ToLower(h) {
			okHost = true
			break
		}
	}
	if !okHost {
		return ValidationError{Msg: "host not allowed"}
	}
	path := u.EscapedPath()
	if path == "" {
		path = "/"
	}
	if !strings.HasPrefix(path, c.cfg.AllowedPath) {
		return ValidationError{Msg: "path not allowed"}
	}
	return nil
}

func (c *Client) Get(ctx context.Context, raw string) (*Result, error) {
	u, err := c.Validate(raw)
	if err != nil {
		return nil, err
	}

	var lastFetch FetchError
	for attempt := 1; attempt <= c.cfg.MaxAttempts; attempt++ {
		body, status, ferr := c.doOnce(ctx, u.String())
		if ferr == nil {
			return &Result{Body: body, StatusCode: status, Attempts: attempt, FinalURL: u.String()}, nil
		}
		lastFetch = ferr.FetchError
		lastFetch.Attempts = attempt
		if !retryable(status, ferr) || attempt == c.cfg.MaxAttempts {
			if status == http.StatusTooManyRequests {
				lastFetch.Code = "rate_limited"
				lastFetch.Msg = "origin rate limited"
			} else if lastFetch.Code == "" {
				lastFetch.Code = "fetch_failed"
			}
			return nil, lastFetch
		}
		wait := backoff(attempt)
		if ra := ferr.retryAfter; ra > 0 {
			wait = ra
			if wait > 2*time.Second {
				wait = 2 * time.Second
			}
		}
		if err := ctx.Err(); err != nil {
			return nil, FetchError{Code: "fetch_failed", Msg: err.Error(), Attempts: attempt}
		}
		c.sleep(wait)
	}
	return nil, lastFetch
}

type onceErr struct {
	FetchError
	retryAfter time.Duration
}

func (c *Client) doOnce(ctx context.Context, raw string) ([]byte, int, *onceErr) {
	attemptCtx, cancel := context.WithTimeout(ctx, c.cfg.Timeout)
	defer cancel()

	req, err := http.NewRequestWithContext(attemptCtx, http.MethodGet, raw, nil)
	if err != nil {
		return nil, 0, &onceErr{FetchError: FetchError{Code: "fetch_failed", Msg: err.Error()}}
	}
	req.Header.Set("User-Agent", c.cfg.UserAgent)
	req.Header.Set("Accept", "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8")
	req.Header.Set("Accept-Language", "en-IN,en;q=0.9")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, 0, &onceErr{FetchError: FetchError{Code: "fetch_failed", Msg: err.Error()}}
	}
	defer resp.Body.Close()

	limited := io.LimitReader(resp.Body, c.cfg.MaxBodyBytes+1)
	b, err := io.ReadAll(limited)
	if err != nil {
		return nil, resp.StatusCode, &onceErr{FetchError: FetchError{Code: "fetch_failed", Msg: err.Error(), StatusCode: resp.StatusCode}}
	}
	if int64(len(b)) > c.cfg.MaxBodyBytes {
		return nil, resp.StatusCode, &onceErr{FetchError: FetchError{Code: "fetch_failed", Msg: "response body too large", StatusCode: resp.StatusCode}}
	}

	if resp.StatusCode == http.StatusOK {
		return b, resp.StatusCode, nil
	}

	oe := &onceErr{
		FetchError: FetchError{
			Code:       "fetch_failed",
			Msg:        fmt.Sprintf("unexpected status %d", resp.StatusCode),
			StatusCode: resp.StatusCode,
		},
		retryAfter: parseRetryAfter(resp.Header.Get("Retry-After")),
	}
	return nil, resp.StatusCode, oe
}

func retryable(status int, err *onceErr) bool {
	if err == nil {
		return false
	}
	switch status {
	case http.StatusTooManyRequests, http.StatusBadGateway, http.StatusServiceUnavailable, http.StatusGatewayTimeout:
		return true
	default:
		return false
	}
}

func backoff(attempt int) time.Duration {
	base := 80 * time.Millisecond
	d := base << (attempt - 1)
	n, err := rand.Int(rand.Reader, big.NewInt(41))
	if err != nil {
		return d
	}
	return d + time.Duration(n.Int64())*time.Millisecond
}

func parseRetryAfter(v string) time.Duration {
	v = strings.TrimSpace(v)
	if v == "" {
		return 0
	}
	if secs, err := time.ParseDuration(v + "s"); err == nil {
		return secs
	}
	return 0
}
