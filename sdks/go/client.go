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
	"mime/multipart"
	"net/http"
	"os"
	"strconv"
	"strings"
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
	apiKey  string
	baseURL string
	http    *http.Client
}

// Option configures a Client at construction.
type Option func(*Client)

// WithBaseURL points the client at a different gateway.
func WithBaseURL(baseURL string) Option {
	return func(c *Client) { c.baseURL = strings.TrimRight(baseURL, "/") }
}

// WithHTTPClient overrides the transport — proxy, timeout, connection pool.
func WithHTTPClient(h *http.Client) Option {
	return func(c *Client) {
		if h != nil {
			c.http = h
		}
	}
}

// New builds a client with an explicit key, validated up front.
func New(apiKey string, opts ...Option) (*Client, error) {
	key, err := ResolveAPIKey(apiKey)
	if err != nil {
		return nil, err
	}
	c := &Client{apiKey: key, baseURL: DefaultBaseURL, http: http.DefaultClient}
	for _, opt := range opts {
		opt(c)
	}
	return c, nil
}

// NewFromEnv builds a client from NROUTER_API_KEY.
func NewFromEnv(opts ...Option) (*Client, error) { return New("", opts...) }

// BaseURL reports where this client sends requests.
func (c *Client) BaseURL() string { return c.baseURL }

// String redacts the key: enough to tell two keys apart in a log, never
// enough to use — the same shape the dashboard shows.
func (c *Client) String() string {
	tail := c.apiKey
	if len(tail) > 4 {
		tail = tail[len(tail)-4:]
	}
	return fmt.Sprintf("nrouter.Client{apiKey:%s...%s, baseURL:%s}", KeyPrefix, tail, c.baseURL)
}

// GoString keeps %#v redacted too; %v and %#v take different paths in fmt.
func (c *Client) GoString() string { return c.String() }

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

// Messages posts to /messages — the Anthropic wire format the gateway also
// serves natively.
func (c *Client) Messages(ctx context.Context, body any) (*Response[map[string]any], error) {
	return c.Post(ctx, "/messages", body)
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
	return c.Get(ctx, "/models/"+id)
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
	var buf bytes.Buffer
	form := multipart.NewWriter(&buf)
	for key, value := range fields {
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
	res, err := c.http.Do(req)
	if err != nil {
		return nil, ResponseMeta{}, nil, transportErr("%v", err)
	}
	defer res.Body.Close()

	meta := MetaFromLookup(func(name string) string { return res.Header.Get(name) })
	raw, err := io.ReadAll(res.Body)
	if err != nil {
		return nil, meta, nil, transportErr("could not read the response body (request %s): %v", meta.RequestID, err)
	}
	return res, meta, raw, nil
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
	contentType := strings.ToLower(res.Header.Get("Content-Type"))
	if !strings.Contains(contentType, "json") {
		return nil, transportErr(
			"gateway returned %d with content-type %q, which is not JSON; use Bytes() for "+
				"binary or streaming endpoints (/audio/speech, /videos/{id}/content, or "+
				"\"stream\": true) — the JSON helpers would report success with an empty body",
			res.StatusCode, contentType)
	}

	// A 2xx whose JSON does not parse is not an empty response — it is a
	// truncated or corrupted one, for a request that was billed.
	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		return nil, transportErr(
			"gateway returned %d with unparseable JSON (%v); the request was billed but the "+
				"body did not arrive intact", res.StatusCode, err)
	}
	return &Response[map[string]any]{Body: decoded, Meta: meta}, nil
}

// gatewayError pulls the gateway's stable code and message out of an error
// payload. The gateway nests them under "error"; a bare object is accepted
// too, so a proxy that reshapes the envelope does not turn a typed error into
// a generic one.
func gatewayError(res *http.Response, meta ResponseMeta, raw []byte) *Error {
	if len(raw) > maxErrorBody {
		raw = raw[:maxErrorBody]
	}
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
	if after := strings.TrimSpace(res.Header.Get("Retry-After")); after != "" {
		if seconds, parseErr := strconv.ParseUint(after, 10, 64); parseErr == nil {
			err.RetryAfter = &seconds
		}
	}
	return err
}
