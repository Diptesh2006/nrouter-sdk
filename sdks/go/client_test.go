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
	"time"
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

func TestChatCompletionsStreamYieldsIncrementalTextAndMetadata(t *testing.T) {
	c := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat/completions" {
			t.Fatalf("path = %q", r.URL.Path)
		}
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		if body["stream"] != true {
			t.Fatalf("named streaming helper must force stream=true; got %#v", body)
		}
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("x-nr-request-id", "req_stream")
		w.WriteHeader(http.StatusOK)
		_, _ = fmt.Fprint(w, "data: {\"choices\":[{\"delta\":{\"content\":\"hel\"}}]}\n\n")
		_, _ = fmt.Fprint(w, "data: {\"choices\":[{\"delta\":{\"content\":\"lo\"}}]}\n\n")
		_, _ = fmt.Fprint(w, "data: [DONE]\n\n")
	})

	stream, err := c.ChatCompletionsStream(context.Background(), map[string]any{"model": "m"})
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	if stream.Meta.RequestID != "req_stream" {
		t.Fatalf("metadata must be available before iteration; got %#v", stream.Meta)
	}
	var text strings.Builder
	for stream.Next() {
		text.WriteString(stream.Chunk().Delta)
	}
	if err := stream.Err(); err != nil {
		t.Fatal(err)
	}
	if text.String() != "hello" {
		t.Fatalf("streamed text = %q", text.String())
	}
}

func TestMessagesStreamUnderstandsAnthropicFramesAndTerminator(t *testing.T) {
	c := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/messages" {
			t.Fatalf("path = %q", r.URL.Path)
		}
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = fmt.Fprint(w, "event: content_block_delta\ndata: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"Claude\"}}\n\n")
		_, _ = fmt.Fprint(w, "event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n")
	})

	stream, err := c.MessagesStream(context.Background(), map[string]any{"model": "claude"})
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	if !stream.Next() || stream.Chunk().Delta != "Claude" {
		t.Fatalf("first chunk = %#v, err = %v", stream.Chunk(), stream.Err())
	}
	if stream.Next() {
		t.Fatal("message_stop is terminal, not a content chunk")
	}
	if err := stream.Err(); err != nil {
		t.Fatal(err)
	}
}

func TestStreamTurnsGuardrailErrorEventIntoTypedFailure(t *testing.T) {
	c := newTestClient(t, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("x-nr-request-id", "req_blocked")
		_, _ = fmt.Fprint(w, "event: error\ndata: {\"error\":{\"type\":\"guardrail_blocked\",\"message\":\"the response was withheld by an output guardrail\"}}\n\n")
	})

	stream, err := c.MessagesStream(context.Background(), map[string]any{"model": "claude"})
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	if stream.Next() {
		t.Fatal("an error frame must never be yielded as a successful chunk")
	}
	if !errors.Is(stream.Err(), ErrGuardrailBlocked) {
		t.Fatalf("got %v; want ErrGuardrailBlocked", stream.Err())
	}
	var e *Error
	if !errors.As(stream.Err(), &e) || e.RequestID != "req_blocked" || e.Code != "guardrail_blocked" {
		t.Fatalf("typed stream error lost response context: %#v", stream.Err())
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

func TestAllFifteenHeadersAreRead(t *testing.T) {
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
		"x-nr-budget-warning":     "org soft_budget 80.00/100.00",
		"x-nr-guardrails":         "pass",
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
	if m.LimitSource != "key" || m.AuthReason != "unauthorized" || m.ResponseCache != "hit" || m.BudgetWarning != "org soft_budget 80.00/100.00" || m.Guardrails != "pass" {
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
	if !errors.As(err, &e) || e.Kind != KindConfiguration {
		t.Fatalf("got %#v; want a KindConfiguration refusal", err)
	}
	if !strings.Contains(e.Message, "Bytes()") {
		t.Fatalf("the refusal must name the method that works; got %q", e.Message)
	}
	// PERMANENT. Only calling a different method can succeed, and every
	// attempt is billed — a generic `if IsRetryable { retry }` loop around a
	// streaming call would spend real credits in a tight loop.
	if e.IsRetryable() {
		t.Fatal("calling the wrong method for an endpoint is never retryable")
	}
	if e.Status != 200 {
		t.Fatalf("the response DID arrive; Status must not stay 0, got %d", e.Status)
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

// --- regressions from the gpt-5.6-sol review --------------------------------

// A pointer receiver puts String/GoString in *Client's method set only, so
// formatting a dereferenced Client falls back to reflection over unexported
// fields and prints the whole key. The original test only covered the pointer.
func TestClientValueAlsoNeverPrintsTheKey(t *testing.T) {
	c, err := New(testKey)
	if err != nil {
		t.Fatal(err)
	}
	value := *c
	type embedder struct{ Client }
	for name, subject := range map[string]any{
		"dereferenced": value,
		"embedded":     embedder{Client: value},
	} {
		for _, format := range []string{"%v", "%s", "%+v", "%#v"} {
			rendered := fmt.Sprintf(format, subject)
			if strings.Contains(rendered, testKey) {
				t.Fatalf("%s of a %s Client leaked the api key: %s", format, name, rendered)
			}
		}
	}
}

// The gateway maps Upstream, UpstreamService, Sandbox and SandboxError to 502
// (src/errors.rs) with no code, and every one of them is transient.
func TestCodeless502IsATransientServiceFailure(t *testing.T) {
	c := newTestClient(t, jsonHandler(502, nil, map[string]any{
		"error": map[string]any{"type": "gateway_error", "message": "upstream service failed"},
	}))
	_, err := c.Models(context.Background())
	var e *Error
	if !errors.As(err, &e) || e.Kind != KindService {
		t.Fatalf("got %#v; want KindService", err)
	}
	if !e.IsRetryable() {
		t.Fatal("a transient upstream failure must be retryable")
	}
}

// UpstreamBodyTooLarge shares that 502 and is deterministic: the identical
// request produces the identical oversized response forever.
func TestOversized502IsNotRetryable(t *testing.T) {
	c := newTestClient(t, jsonHandler(502, nil, map[string]any{
		"error": map[string]any{"message": "the upstream response was too large to process"},
	}))
	_, err := c.Models(context.Background())
	var e *Error
	if !errors.As(err, &e) {
		t.Fatalf("got %#v", err)
	}
	if e.Kind != KindOther || e.IsRetryable() {
		t.Fatalf("an oversized upstream response must not be retryable; got %s", e.Kind)
	}
}

func TestContextCancellationIsPreservedAndNotRetryable(t *testing.T) {
	c := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		<-r.Context().Done()
	})
	ctx, cancel := context.WithCancel(context.Background())
	go func() { time.Sleep(20 * time.Millisecond); cancel() }()

	_, err := c.Models(ctx)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("errors.Is(err, context.Canceled) was false for %#v", err)
	}
	var e *Error
	if !errors.As(err, &e) {
		t.Fatalf("got %#v; want *Error", err)
	}
	if e.IsRetryable() {
		t.Fatal("the caller asked to stop; a retry loop must not treat that as try-again")
	}
	// The sentinel still matches, so existing switches keep working.
	if !errors.Is(err, ErrTransport) {
		t.Fatal("the transport sentinel must still match")
	}
}

// Without the read cap, a multi-megabyte error body is parsed whole and its
// message is handed to the caller verbatim.
func TestOversizedErrorBodyIsBoundedWhileReading(t *testing.T) {
	huge := strings.Repeat("A", 3<<20)
	c := newTestClient(t, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(500)
		_, _ = w.Write([]byte(`{"error":{"message":"` + huge + `"}}`))
	})
	_, err := c.Models(context.Background())
	var e *Error
	if !errors.As(err, &e) {
		t.Fatalf("got %#v", err)
	}
	if len(e.Message) > maxErrorBody {
		t.Fatalf("an unbounded error body reached the caller: %d bytes", len(e.Message))
	}
	if e.Status != 500 {
		t.Fatalf("status lost while truncating: %d", e.Status)
	}
}

// The request reached the gateway and may have been billed; the identifiers
// belong on the struct, not buried in a message string.
func TestBodyReadFailureKeepsTheRequestID(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		hj, ok := w.(http.Hijacker)
		if !ok {
			t.Error("test server does not support hijacking")
			return
		}
		conn, buf, err := hj.Hijack()
		if err != nil {
			t.Errorf("hijack: %v", err)
			return
		}
		// Promise 500 bytes, send 5, then drop the connection.
		_, _ = buf.WriteString("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n" +
			"x-nr-request-id: nrouter-truncated\r\nContent-Length: 500\r\n\r\nabcde")
		_ = buf.Flush()
		_ = conn.Close()
	}))
	t.Cleanup(srv.Close)

	c, err := New(testKey, WithBaseURL(srv.URL), WithHTTPClient(srv.Client()))
	if err != nil {
		t.Fatal(err)
	}
	_, err = c.Models(context.Background())
	var e *Error
	if !errors.As(err, &e) || e.Kind != KindTransport {
		t.Fatalf("got %#v; want a transport failure", err)
	}
	if e.RequestID != "nrouter-truncated" {
		t.Fatalf("the request id must survive a body-read failure; got %q", e.RequestID)
	}
}

func TestParseRetryAfterAcceptsBothRFC9110Forms(t *testing.T) {
	now := time.Date(2026, 8, 27, 12, 0, 0, 0, time.UTC)
	cases := []struct {
		name string
		raw  string
		want *uint64
	}{
		{"absent", "", nil},
		{"delta seconds", "30", ptr(uint64(30))},
		{"delta seconds padded", "  45  ", ptr(uint64(45))},
		{"http date in the future", now.Add(90 * time.Second).Format(http.TimeFormat), ptr(uint64(90))},
		{"http date in the past means now", now.Add(-time.Hour).Format(http.TimeFormat), ptr(uint64(0))},
		{"garbage", "soon-ish", nil},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := parseRetryAfter(tc.raw, now)
			switch {
			case tc.want == nil && got != nil:
				t.Fatalf("want nil, got %d", *got)
			case tc.want != nil && got == nil:
				t.Fatalf("want %d, got nil", *tc.want)
			case tc.want != nil && *got != *tc.want:
				t.Fatalf("want %d, got %d", *tc.want, *got)
			}
		})
	}
}

func TestRetryAfterHTTPDateReachesTheError(t *testing.T) {
	c := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Retry-After", time.Now().Add(60*time.Second).UTC().Format(http.TimeFormat))
		jsonHandler(429, nil, map[string]any{
			"error": map[string]any{"code": "rate_limit_exceeded", "message": "slow"},
		})(w, r)
	})
	_, err := c.Models(context.Background())
	var e *Error
	if !errors.As(err, &e) {
		t.Fatalf("got %#v", err)
	}
	if e.RetryAfter == nil {
		t.Fatal("an HTTP-date Retry-After must be parsed, not silently dropped")
	}
	// Second-resolution formatting can shave one second off.
	if *e.RetryAfter < 58 || *e.RetryAfter > 60 {
		t.Fatalf("RetryAfter was %d, want ~60", *e.RetryAfter)
	}
}

func ptr[T any](v T) *T { return &v }

// A failure raised after the headers arrived must carry what they said. Status
// 0 is documented as "never reached the gateway"; leaving it there on a billed
// response destroys the only correlation path the caller has.
func TestPostHeaderFailuresKeepResponseContext(t *testing.T) {
	cases := map[string]http.HandlerFunc{
		"unparseable json": func(w http.ResponseWriter, _ *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("x-nr-request-id", "nrouter-ctx")
			w.WriteHeader(200)
			_, _ = w.Write([]byte(`{"truncated":`))
		},
		"non json": func(w http.ResponseWriter, _ *http.Request) {
			w.Header().Set("Content-Type", "audio/mpeg")
			w.Header().Set("x-nr-request-id", "nrouter-ctx")
			w.WriteHeader(200)
			_, _ = w.Write([]byte{0xFF})
		},
	}
	for name, handler := range cases {
		t.Run(name, func(t *testing.T) {
			c := newTestClient(t, handler)
			_, err := c.Models(context.Background())
			var e *Error
			if !errors.As(err, &e) {
				t.Fatalf("got %#v", err)
			}
			if e.RequestID != "nrouter-ctx" {
				t.Fatalf("request id lost: %q", e.RequestID)
			}
			if e.Status != 200 {
				t.Fatalf("status lost: %d", e.Status)
			}
		})
	}
}

// Go's multipart writer escapes quotes and backslashes in a
// Content-Disposition parameter but NOT line breaks, so a CR or LF terminates
// the header and injects whatever follows. Filenames come from user uploads.
func TestMultipartRefusesHeaderInjection(t *testing.T) {
	reached := false
	c := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		reached = true
		jsonHandler(200, nil, map[string]any{"ok": true})(w, r)
	})
	hostile := []struct {
		name  string
		file  string
		field map[string]string
	}{
		{"filename CRLF", "a.mp3\r\nX-Injected: yes", map[string]string{"model": "whisper-1"}},
		{"filename LF", "a.mp3\nX-Injected: yes", map[string]string{"model": "whisper-1"}},
		{"field name CRLF", "a.mp3", map[string]string{"model\r\nX-Injected: yes": "whisper-1"}},
	}
	for _, tc := range hostile {
		t.Run(tc.name, func(t *testing.T) {
			_, err := c.AudioTranscriptions(context.Background(), []byte("RIFF"), tc.file, tc.field)
			var e *Error
			if !errors.As(err, &e) || e.Kind != KindConfiguration {
				t.Fatalf("got %#v; want a KindConfiguration refusal", err)
			}
			if reached {
				t.Fatal("the hostile request must be refused BEFORE it is sent")
			}
		})
	}
}

// The gateway never bills NaN, an infinity, or a negative amount. Go's
// ParseFloat accepts all three as valid floats, so each one produced a
// non-nil Cost the caller would bill against — a NaN then poisons every sum
// it reaches. Found by the TypeScript SDK's metadata lane, which had to gate
// the same values, and confirmed against strconv here.
func TestNonsenseCostHeadersAreNilNotBilled(t *testing.T) {
	for _, raw := range []string{"NaN", "Inf", "+Inf", "-Inf", "Infinity", "-0.5", "-3", "  "} {
		t.Run(raw, func(t *testing.T) {
			c := newTestClient(t, jsonHandler(200, map[string]string{
				"x-nr-request-cost": raw,
				"x-nr-cost-status":  "exact",
			}, map[string]any{"ok": true}))
			res, err := c.Models(context.Background())
			if err != nil {
				t.Fatal(err)
			}
			if res.Meta.Cost != nil {
				t.Fatalf("cost header %q parsed to %v; a cost that is not a real amount must be nil", raw, *res.Meta.Cost)
			}
			if res.Meta.IsPriced() {
				t.Fatalf("cost header %q reported as priced", raw)
			}
		})
	}
}

// ...and a genuinely measured zero still parses. The guard must reject
// nonsense, not every small number.
func TestARealZeroCostStillParses(t *testing.T) {
	c := newTestClient(t, jsonHandler(200, map[string]string{
		"x-nr-request-cost": "0",
		"x-nr-cost-status":  "exact",
	}, map[string]any{"ok": true}))
	res, err := c.Models(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res.Meta.Cost == nil || *res.Meta.Cost != 0 {
		t.Fatalf("a measured 0 must survive, got %v", res.Meta.Cost)
	}
}

// A token count that cannot be represented exactly is not a count.
func TestOutOfRangeTokenCountIsNil(t *testing.T) {
	c := newTestClient(t, jsonHandler(200, map[string]string{
		"x-nr-input-tokens": "18446744073709551616",
		"x-nr-total-tokens": "-3",
	}, map[string]any{"ok": true}))
	res, err := c.Models(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res.Meta.InputTokens != nil || res.Meta.TotalTokens != nil {
		t.Fatalf("out-of-range counts must be nil: in=%v total=%v", res.Meta.InputTokens, res.Meta.TotalTokens)
	}
}

func TestNamedHelpersCoverEveryRemainingGatewayOperation(t *testing.T) {
	tests := []struct {
		name   string
		method string
		path   string
		binary bool
		call   func(*Client) error
	}{
		{
			name: "audio speech", method: http.MethodPost, path: "/audio/speech", binary: true,
			call: func(c *Client) error {
				_, err := c.AudioSpeech(context.Background(), map[string]any{"model": "tts-1", "input": "hi"})
				return err
			},
		},
		{
			name: "create video", method: http.MethodPost, path: "/videos",
			call: func(c *Client) error {
				_, err := c.CreateVideo(context.Background(), map[string]any{"model": "video-1", "prompt": "ocean"})
				return err
			},
		},
		{
			name: "retrieve video", method: http.MethodGet, path: "/videos/video%2Fone",
			call: func(c *Client) error {
				_, err := c.RetrieveVideo(context.Background(), "video/one")
				return err
			},
		},
		{
			name: "retrieve model", method: http.MethodGet, path: "/models/provider/model%20one",
			call: func(c *Client) error {
				_, err := c.Model(context.Background(), "provider/model one")
				return err
			},
		},
		{
			name: "download video", method: http.MethodGet, path: "/videos/video%2Fone/content", binary: true,
			call: func(c *Client) error {
				_, err := c.DownloadVideoContent(context.Background(), "video/one")
				return err
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			seen := make(chan *http.Request, 1)
			client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
				seen <- r.Clone(r.Context())
				if tt.binary {
					w.Header().Set("Content-Type", "application/octet-stream")
					_, _ = w.Write([]byte("bytes"))
					return
				}
				jsonHandler(200, nil, map[string]any{"ok": true})(w, r)
			})
			if err := tt.call(client); err != nil {
				t.Fatalf("call failed: %v", err)
			}
			req := <-seen
			if req.Method != tt.method || req.URL.EscapedPath() != tt.path {
				t.Fatalf("got %s %s; want %s %s", req.Method, req.URL.EscapedPath(), tt.method, tt.path)
			}
		})
	}
}
