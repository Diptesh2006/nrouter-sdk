// Package nrouter is the Go SDK for the nRouter LLM gateway — one API key for
// models across six provider clouds, on the OpenAI and Anthropic wire formats.
//
// The client speaks the same JSON the gateway serves and hands back the
// `x-nr-*` metadata beside every response, so per-request cost, token counts
// and cache outcome are visible rather than discarded:
//
//	client, err := nrouter.NewFromEnv() // reads NROUTER_API_KEY
//	if err != nil {
//		return err
//	}
//	res, err := client.ChatCompletions(ctx, map[string]any{
//		"model":    "claude-sonnet-4-5",
//		"messages": []any{map[string]any{"role": "user", "content": "Hello!"}},
//	})
//	if err != nil {
//		return err
//	}
//	if res.Meta.Cost != nil {
//		fmt.Printf("cost $%v\n", *res.Meta.Cost)
//	} else {
//		// Unpriced is not free — it is unknown. Never render it as 0.
//		fmt.Printf("unpriced (%s)\n", res.Meta.CostStatus)
//	}
package nrouter

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"mime/multipart"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	// DefaultBaseURL is the gateway's customer surface. A dynamic value:
	// override it with WithBaseURL for stage or a local run.
	DefaultBaseURL = "https://api.nrouter.ai/v1"
	// EnvKey is the one environment variable this SDK reads.
	EnvKey = "NROUTER_API_KEY"
	// KeyPrefix is carried by every customer virtual key.
	KeyPrefix = "sk-nrouter-"
)

// maxErrorBody caps how much of a failed response is parsed. An upstream that
// returns a megabyte of HTML on a 502 should not be read into memory whole
// just to produce a message nobody reads past the first line.
const maxErrorBody = 1 << 20

// The transport deadlines this SDK ships with.
//
// http.DefaultClient — which this client used to be built on — has NO timeout
// of any kind: Timeout is 0 and its transport sets none either, so a gateway
// or provider that accepts the connection and then goes silent hangs the
// calling process forever. Every number below is therefore an explicit
// decision (name it, or you have chosen infinity), and every one is sized
// against the gateway's own budget rather than picked for feel.
//
// The gateway's worst HONEST case before it can send a first byte is roughly
// 410 s: up to three provider attempts, each with a 10 s connect timeout and a
// 120 s between-bytes read timeout, plus at most 20 s of cumulative backoff
// between them. A client deadline BELOW that aborts a request the gateway is
// about to answer — and the customer is billed for it anyway, because the
// provider tokens were already spent. So the bounds here sit comfortably above
// the gateway's worst honest case and comfortably below infinity.
//
// None of these ever retries. Waiting is bounded here; re-sending is not done
// at all — see WithHTTPClient and Error.IsRetryable.
const (
	// DefaultConnectTimeout bounds DNS resolution plus the TCP handshake, and
	// nothing after it. Ten seconds is generous for a connect and short enough
	// that a black-holed gateway address is reported rather than waited on.
	DefaultConnectTimeout = 10 * time.Second

	// DefaultTLSHandshakeTimeout bounds the TLS handshake alone. Separate from
	// the connect timeout because a TCP connect that succeeds into something
	// that never completes a handshake is its own failure mode.
	DefaultTLSHandshakeTimeout = 10 * time.Second

	// DefaultResponseHeaderTimeout bounds the wait between the request being
	// written and the FIRST response header arriving — time-to-headers, not
	// time-to-body.
	//
	// This is the bound that replaces a blunt http.Client.Timeout, and the
	// distinction is the whole design. http.Client.Timeout covers reading the
	// response BODY too, so it severs an SSE stream mid-generation and truncates
	// a long GET /videos/{id}/content download — both of which are already
	// billed. ResponseHeaderTimeout bounds the failure that actually matters (a
	// gateway that accepted the connection and said nothing) without putting any
	// ceiling on how long a working stream or a large download may legitimately
	// run.
	//
	// Ten minutes: above the gateway's ~410 s worst honest time-to-headers with
	// margin, and the same order as the OpenAI and Anthropic clients' own 600 s
	// defaults, so a caller migrating from either is not surprised.
	//
	// Post-header stalls are bounded separately by DefaultBodyIdleTimeout.
	DefaultResponseHeaderTimeout = 600 * time.Second

	// DefaultBodyIdleTimeout bounds every gap between response-body bytes,
	// including SSE and binary downloads, without limiting their total length.
	DefaultBodyIdleTimeout = 120 * time.Second

	// DefaultIdleConnTimeout is how long an idle pooled connection is kept.
	// Named rather than inherited, so the pool's shape is a decision here.
	DefaultIdleConnTimeout = 90 * time.Second

	// DefaultKeepAlive is the TCP keepalive interval. Shorter than the response
	// header timeout deliberately: a connection silently reaped by an
	// intermediary is discovered by the keepalive rather than by a caller
	// waiting out the full header deadline.
	DefaultKeepAlive = 30 * time.Second

	// DefaultMaxIdleConnsPerHost bounds idle connections kept per host. Go's
	// default is 2, so a caller making concurrent requests to one gateway would
	// tear down and re-handshake most of them; a limit is a decision like any
	// other timeout.
	DefaultMaxIdleConnsPerHost = 32
)

// newTransport builds the SDK transport with explicit deadlines.
//
// Parameterized rather than written twice so a test can prove the header
// deadline FIRES without waiting ten minutes, against a transport that is
// identical to the shipped one in every other property. A second builder chain
// is how one client keeps a control the other quietly loses.
func newTransport(connectTimeout, tlsHandshakeTimeout, responseHeaderTimeout time.Duration) *http.Transport {
	return &http.Transport{
		// Proxy and ForceAttemptHTTP2 are carried over from
		// http.DefaultTransport on purpose. A hand-built *http.Transport that
		// omits them silently drops HTTPS_PROXY support and downgrades every
		// call to HTTP/1.1 — a regression hidden inside a timeout fix.
		Proxy: http.ProxyFromEnvironment,
		DialContext: (&net.Dialer{
			Timeout:   connectTimeout,
			KeepAlive: DefaultKeepAlive,
		}).DialContext,
		ForceAttemptHTTP2:     true,
		TLSHandshakeTimeout:   tlsHandshakeTimeout,
		ResponseHeaderTimeout: responseHeaderTimeout,
		IdleConnTimeout:       DefaultIdleConnTimeout,
		ExpectContinueTimeout: time.Second,
		MaxIdleConns:          100,
		MaxIdleConnsPerHost:   DefaultMaxIdleConnsPerHost,
	}
}

// defaultTransport is shared by every client this package builds, so the
// connection pool is shared too. Clients wrap it; nobody mutates it.
var defaultTransport = newTransport(
	DefaultConnectTimeout,
	DefaultTLSHandshakeTimeout,
	DefaultResponseHeaderTimeout,
)

// DefaultHTTPClient returns the HTTP client New uses when WithHTTPClient is
// not supplied: explicit connect, TLS-handshake and response-header deadlines,
// and deliberately NO http.Client.Timeout.
//
// The zero Timeout is a property, not an omission. http.Client.Timeout covers
// the response body, so setting one here would kill SSE streaming and truncate
// GET /videos/{id}/content. Callers who want a whole-request ceiling should set
// one per call with context.WithTimeout — which is per-request, so a streaming
// call can opt out — or pass their own client to WithHTTPClient.
//
// A fresh *http.Client each call, sharing one transport: mutating the returned
// client (adding a Timeout, say) affects only your client, never the pool.
func DefaultHTTPClient() *http.Client {
	return &http.Client{Transport: defaultTransport}
}

// ResolveAPIKey resolves and validates a key: the explicit argument first,
// then the environment.
//
// Validation happens before any request, so a malformed key fails locally
// rather than as a 401 that looks like a revoked credential.
func ResolveAPIKey(explicit string) (string, error) {
	key := explicit
	if key == "" {
		key = os.Getenv(EnvKey)
	}
	if key == "" {
		return "", configErr("no nRouter API key: pass one explicitly or set %s", EnvKey)
	}
	if !strings.HasPrefix(key, KeyPrefix) {
		return "", configErr("nRouter API keys start with %q; got one that does not", KeyPrefix)
	}
	return key, nil
}

// Response pairs a decoded body with the metadata the gateway reported for it.
type Response[T any] struct {
	Body T
	Meta ResponseMeta
}

// Client is a native nRouter HTTP client over the OpenAI wire format.
//
// It implements fmt.Stringer and fmt.GoStringer by hand, NOT by relying on
// the default struct formatting: Go's fmt reflects over unexported fields, so
// a single %+v in a caller's log would print the API key verbatim and leak a
// credential that spends real credits (Rule #5).
type Client struct {
	apiKey          string
	baseURL         string
	http            *http.Client
	bodyIdleTimeout time.Duration
}

// Option configures a Client at construction.
type Option func(*Client)

// WithBaseURL points the client at a different gateway.
func WithBaseURL(baseURL string) Option {
	return func(c *Client) { c.baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/") }
}

// WithHTTPClient overrides the transport — proxy, timeout, connection pool.
//
// It replaces DefaultHTTPClient and its transport-level deadlines. The SDK's
// response-body idle deadline remains in force; change it with
// WithBodyIdleTimeout. Two warnings worth carrying:
//
//   - Setting http.Client.Timeout applies it to the response BODY, which cuts
//     SSE streaming and long downloads mid-transfer, already billed. Prefer a
//     transport-level ResponseHeaderTimeout, or a per-call context deadline.
//   - This SDK does not retry, and a client that wraps this one in a retry
//     loop must not do so blindly. Every attempt at a billed POST is billed
//     again, so a generic `if err.IsRetryable() { retry }` loop around one
//     spends real credits in a tight loop. IsRetryable reports whether an
//     identical retry *could* succeed; it is advisory, never an instruction.
func WithHTTPClient(h *http.Client) Option {
	return func(c *Client) {
		if h != nil {
			c.http = h
		}
	}
}

// WithBodyIdleTimeout changes the gap-between-bytes deadline. It remains in
// force with an injected HTTP client because net/http exposes no equivalent
// transport setting.
func WithBodyIdleTimeout(timeout time.Duration) Option {
	return func(c *Client) { c.bodyIdleTimeout = timeout }
}

// New builds a client with an explicit key, validated up front.
func New(apiKey string, opts ...Option) (*Client, error) {
	key, err := ResolveAPIKey(apiKey)
	if err != nil {
		return nil, err
	}
	c := &Client{
		apiKey: key, baseURL: DefaultBaseURL, http: DefaultHTTPClient(),
		bodyIdleTimeout: DefaultBodyIdleTimeout,
	}
	for _, opt := range opts {
		opt(c)
	}
	if strings.ContainsAny(c.baseURL, "\r\n\t") {
		return nil, configErr("baseURL contains invalid whitespace or control characters")
	}
	parsedURL, err := url.Parse(c.baseURL)
	if err != nil {
		return nil, configErr(fmt.Sprintf("invalid nRouter gateway URL: %v", err))
	}
	if parsedURL.User != nil {
		return nil, configErr("nRouter gateway URL must not contain credentials")
	}
	host := strings.ToLower(parsedURL.Hostname())
	if host == "" {
		return nil, configErr("nRouter gateway URL must include a host")
	}
	isLoopback := host == "localhost" || host == "0.0.0.0" || strings.HasSuffix(host, ".local")
	if ip := net.ParseIP(host); ip != nil && ip.IsLoopback() {
		isLoopback = true
	}
	if parsedURL.Scheme != "https" && !(parsedURL.Scheme == "http" && isLoopback) {
		return nil, configErr("nRouter gateway URL must use HTTPS; HTTP is allowed only for loopback development")
	}
	if c.bodyIdleTimeout <= 0 {
		return nil, configErr("body idle timeout must be positive")
	}
	return c, nil
}

// NewFromEnv builds a client from NROUTER_API_KEY.
func NewFromEnv(opts ...Option) (*Client, error) { return New("", opts...) }

// BaseURL reports where this client sends requests.
func (c *Client) BaseURL() string { return c.baseURL }

// String redacts the key: enough to tell two keys apart in a log, never
// enough to use — the same shape the dashboard shows.
//
// VALUE receiver, deliberately. A pointer receiver puts these methods in
// *Client's method set ONLY, so `fmt.Printf("%+v", *client)` — or a Client
// embedded by value — falls back to reflection and prints the whole key. A
// value receiver is in both method sets and covers both forms.
func (c Client) String() string {
	tail := c.apiKey
	if len(tail) > 4 {
		tail = tail[len(tail)-4:]
	}
	return fmt.Sprintf("nrouter.Client{apiKey:%s...%s, baseURL:%s}", KeyPrefix, tail, c.baseURL)
}

// GoString keeps %#v redacted too; %v and %#v take different paths in fmt.
func (c Client) GoString() string { return c.String() }

// UsesMessagesWire returns true when a model family is served on /v1/messages
// rather than /v1/chat/completions (e.g. Claude / Anthropic family models).
func UsesMessagesWire(model string, provider ...string) bool {
	m := strings.ToLower(model)
	if strings.Contains(m, "claude") ||
		strings.Contains(m, "anthropic") ||
		strings.Contains(m, "haiku") ||
		strings.Contains(m, "sonnet") ||
		strings.Contains(m, "opus") {
		return true
	}
	if len(provider) > 0 && strings.Contains(strings.ToLower(provider[0]), "anthropic") {
		return true
	}
	return false
}

// ChatCompletions posts to /chat/completions.
func (c *Client) ChatCompletions(ctx context.Context, body any) (*Response[map[string]any], error) {
	return c.Post(ctx, "/chat/completions", body)
}

// Completions posts to the legacy /completions endpoint.
func (c *Client) Completions(ctx context.Context, body any) (*Response[map[string]any], error) {
	return c.Post(ctx, "/completions", body)
}

// Embeddings posts to /embeddings.
func (c *Client) Embeddings(ctx context.Context, body any) (*Response[map[string]any], error) {
	return c.Post(ctx, "/embeddings", body)
}

// NormalizeAnthropicMessages extracts system messages into top-level system parameter,
// normalizes stop/stop_sequences, and handles max_completion_tokens for /messages.
func NormalizeAnthropicMessages(body any) any {
	m, ok := body.(map[string]any)
	if !ok {
		return body
	}
	out := make(map[string]any, len(m)+2)
	for k, v := range m {
		out[k] = v
	}

	if rawMsgs, exists := out["messages"]; exists {
		var cleaned []any
		var systemChunks []string

		if existingSys, hasSys := out["system"].(string); hasSys && existingSys != "" {
			systemChunks = append(systemChunks, existingSys)
		}

		if msgSlice, isSlice := rawMsgs.([]any); isSlice {
			for _, item := range msgSlice {
				if turn, isMap := item.(map[string]any); isMap {
					role, _ := turn["role"].(string)
					if strings.EqualFold(role, "system") || strings.EqualFold(role, "developer") {
						if contentStr, isStr := turn["content"].(string); isStr && contentStr != "" {
							systemChunks = append(systemChunks, contentStr)
						} else if contentArr, isArr := turn["content"].([]any); isArr {
							for _, part := range contentArr {
								if partMap, isPartMap := part.(map[string]any); isPartMap {
									if partMap["type"] == "text" {
										if t, isT := partMap["text"].(string); isT && t != "" {
											systemChunks = append(systemChunks, t)
										}
									}
								}
							}
						}
						continue
					}
				}
				cleaned = append(cleaned, item)
			}
			out["messages"] = cleaned
		} else if typedSlice, isTyped := rawMsgs.([]ChatMessage); isTyped {
			for _, turn := range typedSlice {
				role, _ := turn["role"].(string)
				if strings.EqualFold(role, "system") || strings.EqualFold(role, "developer") {
					if contentStr, isStr := turn["content"].(string); isStr && contentStr != "" {
						systemChunks = append(systemChunks, contentStr)
					}
					continue
				}
				cleaned = append(cleaned, turn)
			}
			out["messages"] = cleaned
		}

		if len(systemChunks) > 0 {
			out["system"] = strings.Join(systemChunks, "\n\n")
		}
	}

	if maxComp, hasMaxComp := out["max_completion_tokens"]; hasMaxComp {
		delete(out, "max_completion_tokens")
		if _, hasMax := out["max_tokens"]; !hasMax {
			out["max_tokens"] = maxComp
		}
	}
	if _, hasMax := out["max_tokens"]; !hasMax {
		out["max_tokens"] = 4096
	}

	if stopVal, hasStop := out["stop"]; hasStop {
		delete(out, "stop")
		if _, hasStopSeq := out["stop_sequences"]; !hasStopSeq {
			if s, isStr := stopVal.(string); isStr && s != "" {
				out["stop_sequences"] = []string{s}
			} else if arr, isArr := stopVal.([]string); isArr && len(arr) > 0 {
				out["stop_sequences"] = arr
			} else if arrAny, isArrAny := stopVal.([]any); isArrAny {
				var valid []string
				for _, item := range arrAny {
					if str, isS := item.(string); isS && str != "" {
						valid = append(valid, str)
					}
				}
				if len(valid) > 0 {
					out["stop_sequences"] = valid
				}
			}
		}
	}

	return out
}

// Messages posts to /messages — the Anthropic wire format the gateway also
// serves natively.
func (c *Client) Messages(ctx context.Context, body any) (*Response[map[string]any], error) {
	return c.Post(ctx, "/messages", NormalizeAnthropicMessages(body))
}

// CountTokens posts to /messages/count_tokens.
func (c *Client) CountTokens(ctx context.Context, body any) (*Response[map[string]any], error) {
	return c.Post(ctx, "/messages/count_tokens", body)
}

// Responses posts to /responses.
func (c *Client) Responses(ctx context.Context, body any) (*Response[map[string]any], error) {
	return c.Post(ctx, "/responses", body)
}

// ImagesGenerations posts to /images/generations.
func (c *Client) ImagesGenerations(ctx context.Context, body any) (*Response[map[string]any], error) {
	return c.Post(ctx, "/images/generations", body)
}

// Models gets /models — what this key is allowed to route to.
func (c *Client) Models(ctx context.Context) (*Response[map[string]any], error) {
	return c.Get(ctx, "/models")
}

// Model gets /models/{id}.
func (c *Client) Model(ctx context.Context, id string) (*Response[map[string]any], error) {
	parts := strings.Split(id, "/")
	for i := range parts {
		parts[i] = url.PathEscape(parts[i])
	}
	return c.Get(ctx, "/models/"+strings.Join(parts, "/"))
}

// AudioTranscriptions posts multipart to /audio/transcriptions.
//
// fileName must carry the real extension: upstream providers pick their
// decoder from it, so "audio" is rejected where "speech.mp3" is not.
func (c *Client) AudioTranscriptions(ctx context.Context, file []byte, fileName string, fields map[string]string) (*Response[map[string]any], error) {
	return c.Multipart(ctx, "/audio/transcriptions", file, fileName, fields)
}

// AudioTranslations posts multipart to /audio/translations.
func (c *Client) AudioTranslations(ctx context.Context, file []byte, fileName string, fields map[string]string) (*Response[map[string]any], error) {
	return c.Multipart(ctx, "/audio/translations", file, fileName, fields)
}

// AudioSpeech generates speech and returns its raw encoded audio bytes.
func (c *Client) AudioSpeech(ctx context.Context, body any) (*Response[[]byte], error) {
	return c.Bytes(ctx, http.MethodPost, "/audio/speech", body)
}

// CreateVideo starts a video generation job.
func (c *Client) CreateVideo(ctx context.Context, body any) (*Response[map[string]any], error) {
	return c.Post(ctx, "/videos", body)
}

// RetrieveVideo gets one video generation job without charging it again.
func (c *Client) RetrieveVideo(ctx context.Context, id string) (*Response[map[string]any], error) {
	return c.Get(ctx, "/videos/"+url.PathEscape(id))
}

// DownloadVideoContent returns the generated video's raw bytes.
func (c *Client) DownloadVideoContent(ctx context.Context, id string) (*Response[[]byte], error) {
	return c.Bytes(ctx, http.MethodGet, "/videos/"+url.PathEscape(id)+"/content", nil)
}

// Post sends any JSON POST under the gateway's /v1 root.
func (c *Client) Post(ctx context.Context, path string, body any) (*Response[map[string]any], error) {
	encoded, err := json.Marshal(body)
	if err != nil {
		return nil, configErr("request body is not JSON-encodable: %v", err)
	}
	req, err := c.request(ctx, http.MethodPost, path, bytes.NewReader(encoded))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	return c.sendJSON(req)
}

// Get sends any GET under the gateway's /v1 root.
func (c *Client) Get(ctx context.Context, path string) (*Response[map[string]any], error) {
	req, err := c.request(ctx, http.MethodGet, path, nil)
	if err != nil {
		return nil, err
	}
	return c.sendJSON(req)
}

// Multipart sends a multipart/form-data POST. The gateway requires a binary
// `file` part on the audio endpoints, so the JSON helpers cannot reach them.
func (c *Client) Multipart(ctx context.Context, path string, file []byte, fileName string, fields map[string]string) (*Response[map[string]any], error) {
	// Go's multipart writer escapes quotes and backslashes in a
	// Content-Disposition parameter but NOT line breaks, so a CR or LF in a
	// filename or field name terminates the header and injects whatever
	// follows as further MIME headers. Filenames routinely come from user
	// uploads. Refuse before encoding anything.
	if err := rejectHeaderInjection("file name", fileName); err != nil {
		return nil, err
	}
	var buf bytes.Buffer
	form := multipart.NewWriter(&buf)
	for key, value := range fields {
		if err := rejectHeaderInjection("form field name", key); err != nil {
			return nil, err
		}
		if err := form.WriteField(key, value); err != nil {
			return nil, configErr("could not encode form field %q: %v", key, err)
		}
	}
	part, err := form.CreateFormFile("file", fileName)
	if err != nil {
		return nil, configErr("could not encode file part: %v", err)
	}
	if _, err := part.Write(file); err != nil {
		return nil, configErr("could not write file part: %v", err)
	}
	if err := form.Close(); err != nil {
		return nil, configErr("could not finalize multipart body: %v", err)
	}
	req, err := c.request(ctx, http.MethodPost, path, &buf)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", form.FormDataContentType())
	return c.sendJSON(req)
}

// Bytes returns the raw body plus metadata, for the endpoints that do not
// return JSON: /audio/speech returns audio, /videos/{id}/content returns a
// video, and "stream": true returns SSE. The JSON helpers refuse those rather
// than handing back an empty body for a request you were billed for.
func (c *Client) Bytes(ctx context.Context, method, path string, body any) (*Response[[]byte], error) {
	var reader io.Reader
	var encoded []byte
	if body != nil {
		var err error
		encoded, err = json.Marshal(body)
		if err != nil {
			return nil, configErr("request body is not JSON-encodable: %v", err)
		}
		reader = bytes.NewReader(encoded)
	}
	req, err := c.request(ctx, strings.ToUpper(method), path, reader)
	if err != nil {
		return nil, err
	}
	if encoded != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	res, meta, raw, err := c.do(req)
	if err != nil {
		return nil, err
	}
	if res.StatusCode < 200 || res.StatusCode >= 300 {
		return nil, gatewayError(res, meta, raw)
	}
	return &Response[[]byte]{Body: raw, Meta: meta}, nil
}

func (c *Client) request(ctx context.Context, method, path string, body io.Reader) (*http.Request, error) {
	url := c.baseURL + "/" + strings.TrimLeft(path, "/")
	req, err := http.NewRequestWithContext(ctx, method, url, body)
	if err != nil {
		return nil, configErr("could not build request for %s: %v", url, err)
	}
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	req.Header.Set("Accept", "application/json")
	return req, nil
}

// do performs the request and reads metadata BEFORE the body, so a body-read
// failure still carries the request id that identifies it.
func (c *Client) do(req *http.Request) (*http.Response, ResponseMeta, []byte, error) {
	res, err := c.doHTTP(req)
	if err != nil {
		// A cancelled or expired context is the CALLER's decision, not a
		// network fault. Keeping the cause makes
		// errors.Is(err, context.Canceled) true through this type, so a retry
		// loop cannot mistake "stop" for "try again".
		//
		// No req.Context().Err() branch: MEASURED, http.Client.Do already
		// returns a *url.Error that wraps the context error, so consulting the
		// context again is dead code. A mutation test proved it — deleting the
		// branch changed no result, which is how it was found.
		failure := transportErr("%v", err)
		failure.Cause = err
		return nil, ResponseMeta{}, nil, failure
	}
	defer res.Body.Close()

	meta := MetaFromLookup(func(name string) string { return res.Header.Get(name) })

	// Cap a FAILED response WHILE reading it, not after. An upstream returning
	// a megabyte of HTML — or streaming indefinitely — on a 502 should not be
	// pulled into memory whole just to produce a message nobody reads past the
	// first line. A success is read in full: that is the payload the caller
	// paid for.
	body := io.Reader(res.Body)
	if res.StatusCode < 200 || res.StatusCode >= 300 {
		body = io.LimitReader(res.Body, maxErrorBody)
	}
	raw, err := io.ReadAll(body)
	if err != nil {
		// The request DID reach the gateway and may have been billed. Carry
		// the response context on the struct so a caller can correlate it,
		// rather than burying the request id in a message string.
		failure := transportErr("could not read the response body: %v", err).withResponse(res, meta)
		failure.Cause = err
		return nil, meta, nil, failure
	}
	return res, meta, raw, nil
}

type idleReadCloser struct {
	source    io.ReadCloser
	timeout   time.Duration
	cancel    context.CancelFunc
	closeOnce sync.Once
	timedOut  atomic.Bool
}

// doHTTP gives the response body an SDK-owned between-bytes deadline. The
// request context is intentionally kept alive until Body.Close: cancelling it
// is the only transport-supported way to interrupt a response-body Read
// without racing Read against Close on an arbitrary io.ReadCloser.
func (c *Client) doHTTP(req *http.Request) (*http.Response, error) {
	requestContext, cancel := context.WithCancel(req.Context())
	res, err := c.http.Do(req.Clone(requestContext))
	if err != nil {
		cancel()
		return nil, err
	}
	res.Body = newIdleReadCloser(res.Body, c.bodyIdleTimeout, cancel)
	return res, nil
}

func newIdleReadCloser(source io.ReadCloser, timeout time.Duration, cancel context.CancelFunc) io.ReadCloser {
	return &idleReadCloser{source: source, timeout: timeout, cancel: cancel}
}

func (r *idleReadCloser) Read(target []byte) (int, error) {
	if r.timedOut.Load() {
		return 0, fmt.Errorf("%w: %w: response body remained idle for %s", os.ErrDeadlineExceeded, context.DeadlineExceeded, r.timeout)
	}
	if len(target) == 0 {
		return 0, nil
	}
	fired := make(chan struct{})
	timer := time.AfterFunc(r.timeout, func() {
		r.timedOut.Store(true)
		r.cancel()
		close(fired)
	})
	n, err := r.source.Read(target)
	if !timer.Stop() {
		<-fired
	}
	if r.timedOut.Load() {
		return n, fmt.Errorf("%w: %w: response body remained idle for %s", os.ErrDeadlineExceeded, context.DeadlineExceeded, r.timeout)
	}
	return n, err
}

func (r *idleReadCloser) Close() (err error) {
	r.closeOnce.Do(func() {
		// Cancel first so an early close interrupts a blocked transport read.
		// A fully consumed net/http body has already returned its connection to
		// the idle pool at EOF; the reuse regression test pins that behavior.
		r.cancel()
		err = r.source.Close()
	})
	return err
}

func (c *Client) sendJSON(req *http.Request) (*Response[map[string]any], error) {
	res, meta, raw, err := c.do(req)
	if err != nil {
		return nil, err
	}

	if res.StatusCode < 200 || res.StatusCode >= 300 {
		return nil, gatewayError(res, meta, raw)
	}

	// A 2xx that is not JSON is a REAL RESPONSE the caller was billed for.
	// Parsing it as JSON yields an empty object, so the caller pays and
	// receives nothing while the call reports success. Refuse loudly and name
	// the method that can actually return it.
	//
	// KindConfiguration, NOT KindTransport. The wrong METHOD was called for
	// this endpoint, and no amount of retrying changes that — but every
	// attempt is billed again. A generic `if err.IsRetryable() { retry }` loop
	// around a streaming call would spend real credits in a tight loop.
	contentType := strings.ToLower(res.Header.Get("Content-Type"))
	if !strings.Contains(contentType, "json") {
		return nil, configErr(
			"gateway returned %d with content-type %q, which is not JSON; use Bytes() for "+
				"binary or streaming endpoints (/audio/speech, /videos/{id}/content, or "+
				"\"stream\": true) — the JSON helpers would report success with an empty body",
			res.StatusCode, contentType).withResponse(res, meta)
	}

	// A 2xx whose JSON does not parse is not an empty response — it is a
	// truncated or corrupted one, for a request that was billed. This one IS
	// transient: the same request can return an intact body next time.
	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		return nil, transportErr(
			"gateway returned %d with unparseable JSON (%v); the request was billed but the "+
				"body did not arrive intact", res.StatusCode, err).withResponse(res, meta)
	}
	return &Response[map[string]any]{Body: decoded, Meta: meta}, nil
}

// gatewayError pulls the gateway's stable code and message out of an error
// payload. The gateway nests them under "error"; a bare object is accepted
// too, so a proxy that reshapes the envelope does not turn a typed error into
// a generic one.
func gatewayError(res *http.Response, meta ResponseMeta, raw []byte) *Error {
	var envelope map[string]any
	_ = json.Unmarshal(raw, &envelope)

	node := envelope
	if nested, ok := envelope["error"].(map[string]any); ok {
		node = nested
	}
	message, _ := node["message"].(string)
	if message == "" {
		message = "nRouter request failed"
	}
	code, _ := node["code"].(string)

	err := &Error{
		Kind:        classify(code, message, res.StatusCode),
		Message:     message,
		Code:        code,
		Status:      res.StatusCode,
		RequestID:   meta.RequestID,
		LimitSource: meta.LimitSource,
		AuthReason:  meta.AuthReason,
	}
	err.RetryAfter = parseRetryAfter(res.Header.Get("Retry-After"), time.Now())
	return err
}

// MaxRetryAfterSeconds is the ceiling for backoff (24 hours).
const MaxRetryAfterSeconds uint64 = 86400

// ParseRetryAfter accepts BOTH RFC 9110 forms. Upstreams send the HTTP-date
// form and the gateway relays it unchanged, so a delta-seconds-only parse
// silently yields nil and the caller retries before the provider said to.
//
// `now` is a parameter so the date branch is testable without a clock.
func ParseRetryAfter(raw string, now time.Time) *uint64 {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	if seconds, err := strconv.ParseUint(raw, 10, 64); err == nil {
		if seconds > MaxRetryAfterSeconds {
			seconds = MaxRetryAfterSeconds
		}
		return &seconds
	}
	when, err := http.ParseTime(raw)
	if err != nil {
		return nil
	}
	// A date already in the past means retry now, which is 0 — never a
	// negative wait wrapped around into an enormous unsigned one.
	delta := when.Sub(now)
	if delta <= 0 {
		zero := uint64(0)
		return &zero
	}
	seconds := uint64(delta.Round(time.Second) / time.Second)
	if seconds > MaxRetryAfterSeconds {
		seconds = MaxRetryAfterSeconds
	}
	return &seconds
}

func parseRetryAfter(raw string, now time.Time) *uint64 {
	return ParseRetryAfter(raw, now)
}

// ComputeJitteredBackoff calculates a bounded jittered exponential backoff.
//
// Honors retryAfterSeconds when non-nil and > 0, bounded by maxDelay.
// Attempt is clamped to [0, 30] to prevent arithmetic bitshift overflow.
// Full jitter spreads backoff between 50% and 100% of the computed window.
func ComputeJitteredBackoff(attempt int, baseDelay, maxDelay time.Duration, retryAfterSeconds *uint64) time.Duration {
	if attempt < 0 {
		attempt = 0
	} else if attempt > 30 {
		attempt = 30
	}
	if baseDelay <= 0 {
		baseDelay = 500 * time.Millisecond
	}
	if maxDelay <= 0 {
		maxDelay = 30 * time.Second
	}

	if retryAfterSeconds != nil && *retryAfterSeconds > 0 {
		retryDur := time.Duration(*retryAfterSeconds) * time.Second
		if retryDur > maxDelay {
			retryDur = maxDelay
		}
		factor := 0.5 + 0.5*rand.Float64()
		return time.Duration(float64(retryDur) * factor)
	}

	exp := time.Duration(1 << uint(attempt))
	delay := baseDelay * exp
	if delay > maxDelay || delay < 0 {
		delay = maxDelay
	}
	factor := 0.5 + 0.5*rand.Float64()
	return time.Duration(float64(delay) * factor)
}

// withResponse stamps what the response already told us onto a failure raised
// AFTER the headers arrived. Without it Status stays 0 — documented as "never
// reached the gateway" — on a request that did reach it and may have been
// billed, and the request id survives only inside a message string.
func (e *Error) withResponse(res *http.Response, meta ResponseMeta) *Error {
	if res != nil {
		e.Status = res.StatusCode
	}
	e.RequestID = meta.RequestID
	e.LimitSource = meta.LimitSource
	e.AuthReason = meta.AuthReason
	return e
}

// rejectHeaderInjection refuses a value that would break out of the MIME
// header it is about to be written into.
func rejectHeaderInjection(label, value string) error {
	if strings.ContainsAny(value, "\r\n") {
		return configErr("%s must not contain a carriage return or line feed: %q", label, value)
	}
	return nil
}
