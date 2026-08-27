package nrouter

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

const testKey = KeyPrefix + "test0000000000000abcd"

func newTestClient(t *testing.T, handler http.HandlerFunc) *Client {
	t.Helper()
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	c, err := New(testKey, WithBaseURL(srv.URL), WithHTTPClient(srv.Client()))
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return c
}

func jsonHandler(status int, headers map[string]string, body any) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		for k, v := range headers {
			w.Header().Set(k, v)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_ = json.NewEncoder(w).Encode(body)
	}
}

// --- the connection contract ------------------------------------------------

func TestResolveAPIKey(t *testing.T) {
	t.Run("explicit wins", func(t *testing.T) {
		t.Setenv(EnvKey, KeyPrefix+"from-env")
		got, err := ResolveAPIKey(testKey)
		if err != nil || got != testKey {
			t.Fatalf("got %q, %v; want the explicit key", got, err)
		}
	})
	t.Run("falls back to the environment", func(t *testing.T) {
		t.Setenv(EnvKey, testKey)
		got, err := ResolveAPIKey("")
		if err != nil || got != testKey {
			t.Fatalf("got %q, %v; want the env key", got, err)
		}
	})
	t.Run("missing key is a configuration error, not transport", func(t *testing.T) {
		t.Setenv(EnvKey, "")
		_, err := ResolveAPIKey("")
		var e *Error
		if !errors.As(err, &e) || e.Kind != KindConfiguration {
			t.Fatalf("got %#v; want a KindConfiguration error", err)
		}
		if e.IsRetryable() {
			t.Fatal("a missing key is PERMANENT; retrying can never succeed")
		}
		if !strings.Contains(e.Message, EnvKey) {
			t.Fatalf("the error should name %s; got %q", EnvKey, e.Message)
		}
	})
	t.Run("a foreign key is refused locally, before any request", func(t *testing.T) {
		_, err := ResolveAPIKey("sk-proj-anopenaikey")
		var e *Error
		if !errors.As(err, &e) || e.Kind != KindConfiguration {
			t.Fatalf("got %#v; want a KindConfiguration error", err)
		}
		if !strings.Contains(e.Message, KeyPrefix) {
			t.Fatalf("the error should name the required prefix; got %q", e.Message)
		}
	})
}

func TestDefaultBaseURLIsTheGateway(t *testing.T) {
	if DefaultBaseURL != "https://api.nrouter.ai/v1" {
		t.Fatalf("base URL drifted: %q", DefaultBaseURL)
	}
	c, err := New(testKey)
	if err != nil {
		t.Fatal(err)
	}
	if c.BaseURL() != DefaultBaseURL {
		t.Fatalf("client base URL %q", c.BaseURL())
	}
}

// A single %+v in a caller's log must not print the key. Go's fmt reflects
// over unexported fields, so this holds only because String/GoString exist.
func TestClientNeverPrintsTheKey(t *testing.T) {
	c, err := New(testKey)
	if err != nil {
		t.Fatal(err)
	}
	for _, format := range []string{"%v", "%s", "%+v", "%#v"} {
		rendered := fmt.Sprintf(format, c)
		if strings.Contains(rendered, testKey) {
			t.Fatalf("%s leaked the api key: %s", format, rendered)
		}
		if !strings.Contains(rendered, "abcd") {
			t.Fatalf("%s should keep the last four to tell keys apart: %s", format, rendered)
		}
	}
}

func TestRequestCarriesBearerAuthAndPath(t *testing.T) {
	var seenAuth, seenPath string
	c := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		seenAuth = r.Header.Get("Authorization")
		seenPath = r.URL.Path
		jsonHandler(200, nil, map[string]any{"ok": true})(w, r)
	})
	if _, err := c.ChatCompletions(context.Background(), map[string]any{"model": "m"}); err != nil {
		t.Fatal(err)
	}
	if seenAuth != "Bearer "+testKey {
		t.Fatalf("Authorization header was %q", seenAuth)
	}
	if seenPath != "/chat/completions" {
		t.Fatalf("path was %q", seenPath)
	}
}

// --- metadata ---------------------------------------------------------------

func TestAllThirteenHeadersAreRead(t *testing.T) {
	headers := map[string]string{
		"x-nr-request-id":         "nrouter-abc123",
		"x-nr-request-cost":       "0.00347",
		"x-nr-cost-status":        "exact",
		"x-nr-model":              "claude-sonnet-4-5",
		"x-nr-input-tokens":       "42",
		"x-nr-output-tokens":      "18",
		"x-nr-total-tokens":       "60",
		"x-nr-cache-read-tokens":  "7",
		"x-nr-cache-write-tokens": "3",
		"x-nr-limit-source":       "key",
		"x-nr-auth-reason":        "unauthorized",
		"x-nr-response-cache":     "hit",
		"x-nr-response-cache-age": "12",
	}
	if len(headers) != len(HeaderNames) {
		t.Fatalf("this test covers %d headers, HeaderNames declares %d", len(headers), len(HeaderNames))
	}
	for _, name := range HeaderNames {
		if _, ok := headers[name]; !ok {
			t.Fatalf("HeaderNames declares %q but this test never sends it", name)
		}
	}

	c := newTestClient(t, jsonHandler(200, headers, map[string]any{"ok": true}))
	res, err := c.Models(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	m := res.Meta
	if m.RequestID != "nrouter-abc123" || m.CostStatus != "exact" || m.Model != "claude-sonnet-4-5" {
		t.Fatalf("string headers not parsed: %+v", m)
	}
	if m.Cost == nil || *m.Cost != 0.00347 {
		t.Fatalf("cost not parsed: %v", m.Cost)
	}
	for name, got := range map[string]*uint64{
		"input": m.InputTokens, "output": m.OutputTokens, "total": m.TotalTokens,
		"cacheRead": m.CacheReadTokens, "cacheWrite": m.CacheWriteTokens,
		"cacheAge": m.ResponseCacheAge,
	} {
		if got == nil {
			t.Fatalf("%s header not parsed", name)
		}
	}
	if m.LimitSource != "key" || m.AuthReason != "unauthorized" || m.ResponseCache != "hit" {
		t.Fatalf("classification headers not parsed: %+v", m)
	}
	if !m.IsPriced() {
		t.Fatal("an exact cost should report IsPriced")
	}
}

// The single most important behaviour in this SDK: unpriced is not free.
func TestUnpricedIsNilNotZero(t *testing.T) {
	c := newTestClient(t, jsonHandler(200, map[string]string{
		"x-nr-request-id":  "nrouter-abc123",
		"x-nr-cost-status": "unpriced",
	}, map[string]any{"ok": true}))
	res, err := c.Models(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res.Meta.Cost != nil {
		t.Fatalf("an absent x-nr-request-cost must stay nil, got %v", *res.Meta.Cost)
	}
	if res.Meta.IsPriced() {
		t.Fatal("unpriced must never report as priced")
	}
}

func TestUnparseableNumericHeaderIsNilNotZero(t *testing.T) {
	c := newTestClient(t, jsonHandler(200, map[string]string{
		"x-nr-input-tokens": "not-a-number",
		"x-nr-request-cost": "also-not",
	}, map[string]any{"ok": true}))
	res, err := c.Models(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res.Meta.InputTokens != nil || res.Meta.Cost != nil {
		t.Fatal("an unparseable numeric header must be nil, never a zero")
	}
}

// --- the error contract -----------------------------------------------------

func TestEachGatewayCodeMapsToItsKind(t *testing.T) {
	cases := map[string]struct {
		status int
		kind   Kind
	}{
		"invalid_request":      {400, KindRequest},
		"guardrail_blocked":    {400, KindGuardrailBlocked},
		"invalid_api_key":      {401, KindAuthentication},
		"insufficient_credits": {402, KindCredit},
		"model_not_found":      {404, KindNotFound},
		"rate_limit_exceeded":  {429, KindRateLimit},
		"tpm_limit_exceeded":   {429, KindRateLimit},
		"credit_check_failed":  {503, KindService},
		"service_unavailable":  {503, KindService},
	}
	if len(cases) != 9 {
		t.Fatalf("the spec fixes nine error codes; this test covers %d", len(cases))
	}
	for code, want := range cases {
		t.Run(code, func(t *testing.T) {
			c := newTestClient(t, jsonHandler(want.status, nil, map[string]any{
				"error": map[string]any{"code": code, "message": "refused"},
			}))
			_, err := c.Models(context.Background())
			var e *Error
			if !errors.As(err, &e) {
				t.Fatalf("got %#v; want *Error", err)
			}
			if e.Kind != want.kind {
				t.Fatalf("code %s classified as %s; want %s", code, e.Kind, want.kind)
			}
			if e.Code != code || e.Status != want.status {
				t.Fatalf("code/status not preserved: %+v", e)
			}
		})
	}
}

// The gateway's MAIN error path sends {"error":{"type","message"}} with no
// code at all, so status dispatch is the ordinary route, not a fallback.
func TestCodelessResponsesAreClassifiedByStatusAndMessage(t *testing.T) {
	cases := []struct {
		name    string
		status  int
		message string
		want    Kind
	}{
		{"400 default", 400, "malformed body", KindRequest},
		{"400 guardrail", 400, "Guardrail rule denied this request", KindGuardrailBlocked},
		{"401", 401, "unauthorized", KindAuthentication},
		{"402 shortfall", 402, "insufficient credit balance", KindCredit},
		{"402 budget", 402, "budget exceeded for this team", KindBudgetExceeded},
		{"404 model", 404, "model gpt-9 not found", KindNotFound},
		{"404 other", 404, "video job not found", KindOther},
		{"429", 429, "slow down", KindRateLimit},
		{"503", 503, "upstream unavailable", KindService},
		{"418 unknown", 418, "teapot", KindOther},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			c := newTestClient(t, jsonHandler(tc.status, nil, map[string]any{
				"error": map[string]any{"type": "gateway_error", "message": tc.message},
			}))
			_, err := c.Models(context.Background())
			var e *Error
			if !errors.As(err, &e) {
				t.Fatalf("got %#v; want *Error", err)
			}
			if e.Kind != tc.want {
				t.Fatalf("%d %q classified as %s; want %s", tc.status, tc.message, e.Kind, tc.want)
			}
			if e.Code != "" {
				t.Fatalf("no code was sent, but Code is %q", e.Code)
			}
		})
	}
}

func TestUnknownCodeIsNeverReclassified(t *testing.T) {
	c := newTestClient(t, jsonHandler(400, nil, map[string]any{
		"error": map[string]any{"code": "some_future_code", "message": "new"},
	}))
	_, err := c.Models(context.Background())
	var e *Error
	if !errors.As(err, &e) || e.Kind != KindOther {
		t.Fatalf("an unknown code must stay KindOther, got %#v", err)
	}
	if e.Code != "some_future_code" {
		t.Fatalf("the unknown code must be preserved, got %q", e.Code)
	}
}

func TestErrorsIsMatchesTheSentinel(t *testing.T) {
	c := newTestClient(t, jsonHandler(429, nil, map[string]any{
		"error": map[string]any{"code": "tpm_limit_exceeded", "message": "tpm"},
	}))
	_, err := c.Models(context.Background())
	if !errors.Is(err, ErrRateLimit) {
		t.Fatalf("errors.Is(err, ErrRateLimit) was false for %#v", err)
	}
	if errors.Is(err, ErrCredit) {
		t.Fatal("a rate limit must not match the credit sentinel")
	}
}

func TestOnlyTransientConditionsAreRetryable(t *testing.T) {
	retryable := map[Kind]bool{
		KindRateLimit: true, KindService: true, KindTransport: true,
		KindRequest: false, KindGuardrailBlocked: false, KindAuthentication: false,
		KindCredit: false, KindBudgetExceeded: false, KindNotFound: false,
		KindOther: false, KindConfiguration: false,
	}
	if len(retryable) != len(sentinels) {
		t.Fatalf("this test covers %d kinds, %d are declared", len(retryable), len(sentinels))
	}
	for kind, want := range retryable {
		if got := (&Error{Kind: kind}).IsRetryable(); got != want {
			t.Fatalf("%s IsRetryable=%v, want %v", kind, got, want)
		}
	}
}

func TestErrorCarriesTheHeadersWorthActingOn(t *testing.T) {
	c := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("x-nr-request-id", "nrouter-xyz")
		w.Header().Set("x-nr-limit-source", "budget")
		w.Header().Set("Retry-After", "30")
		jsonHandler(429, nil, map[string]any{
			"error": map[string]any{"code": "rate_limit_exceeded", "message": "slow"},
		})(w, r)
	})
	_, err := c.Models(context.Background())
	var e *Error
	if !errors.As(err, &e) {
		t.Fatalf("got %#v", err)
	}
	if e.RequestID != "nrouter-xyz" || e.LimitSource != "budget" {
		t.Fatalf("metadata not carried onto the error: %+v", e)
	}
	if e.RetryAfter == nil || *e.RetryAfter != 30 {
		t.Fatalf("Retry-After not parsed: %v", e.RetryAfter)
	}
}

// A bare envelope (a proxy that reshaped it) must still produce a typed error.
func TestBareErrorEnvelopeStillTypes(t *testing.T) {
	c := newTestClient(t, jsonHandler(402, nil, map[string]any{
		"code": "insufficient_credits", "message": "top up",
	}))
	_, err := c.Models(context.Background())
	var e *Error
	if !errors.As(err, &e) || e.Kind != KindCredit {
		t.Fatalf("a bare envelope must still type, got %#v", err)
	}
}

// --- billed-but-empty refusals ---------------------------------------------

func TestNonJSONSuccessIsRefusedNotSilentlyEmpty(t *testing.T) {
	c := newTestClient(t, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "audio/mpeg")
		w.WriteHeader(200)
		_, _ = w.Write([]byte{0xFF, 0xFB, 0x00})
	})
	_, err := c.Post(context.Background(), "/audio/speech", map[string]any{"input": "hi"})
	var e *Error
	if !errors.As(err, &e) || e.Kind != KindTransport {
		t.Fatalf("got %#v; want a transport refusal", err)
	}
	if !strings.Contains(e.Message, "Bytes()") {
		t.Fatalf("the refusal must name the method that works; got %q", e.Message)
	}
}

func TestBytesReturnsBinaryAndMetadata(t *testing.T) {
	c := newTestClient(t, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "audio/mpeg")
		w.Header().Set("x-nr-request-cost", "0.002")
		w.Header().Set("x-nr-cost-status", "exact")
		w.WriteHeader(200)
		_, _ = w.Write([]byte{0xFF, 0xFB, 0x00})
	})
	res, err := c.Bytes(context.Background(), "POST", "/audio/speech", map[string]any{"input": "hi"})
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Body) != 3 {
		t.Fatalf("body was %v", res.Body)
	}
	if res.Meta.Cost == nil || *res.Meta.Cost != 0.002 {
		t.Fatal("Bytes must still report cost metadata")
	}
}

func TestBytesStillTypesAGatewayRefusal(t *testing.T) {
	c := newTestClient(t, jsonHandler(402, nil, map[string]any{
		"error": map[string]any{"code": "insufficient_credits", "message": "top up"},
	}))
	_, err := c.Bytes(context.Background(), "POST", "/audio/speech", map[string]any{"input": "hi"})
	var e *Error
	if !errors.As(err, &e) || e.Kind != KindCredit {
		t.Fatalf("got %#v; want KindCredit", err)
	}
}

func TestUnparseableJSONSuccessIsRefused(t *testing.T) {
	c := newTestClient(t, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"truncated":`))
	})
	_, err := c.Models(context.Background())
	var e *Error
	if !errors.As(err, &e) || e.Kind != KindTransport {
		t.Fatalf("got %#v; want a transport refusal", err)
	}
	if !strings.Contains(e.Message, "billed") {
		t.Fatalf("the refusal should say the request was billed; got %q", e.Message)
	}
}

func TestMultipartSendsTheFileAndFields(t *testing.T) {
	var gotName, gotModel string
	c := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseMultipartForm(1 << 20); err != nil {
			t.Errorf("ParseMultipartForm: %v", err)
		}
		gotModel = r.FormValue("model")
		if fh := r.MultipartForm.File["file"]; len(fh) == 1 {
			gotName = fh[0].Filename
		}
		jsonHandler(200, nil, map[string]any{"text": "hello"})(w, r)
	})
	_, err := c.AudioTranscriptions(context.Background(), []byte("RIFF"), "speech.mp3",
		map[string]string{"model": "whisper-1"})
	if err != nil {
		t.Fatal(err)
	}
	if gotName != "speech.mp3" || gotModel != "whisper-1" {
		t.Fatalf("multipart body wrong: file=%q model=%q", gotName, gotModel)
	}
}

func TestTransportFailureIsTypedAndRetryable(t *testing.T) {
	c, err := New(testKey, WithBaseURL("http://127.0.0.1:1"))
	if err != nil {
		t.Fatal(err)
	}
	_, err = c.Models(context.Background())
	var e *Error
	if !errors.As(err, &e) || e.Kind != KindTransport {
		t.Fatalf("got %#v; want KindTransport", err)
	}
	if !e.IsRetryable() {
		t.Fatal("a transport failure is retryable")
	}
}
