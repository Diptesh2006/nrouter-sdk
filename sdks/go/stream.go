package nrouter

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

const maxSSELine = 1 << 20

// StreamChunk is one decoded server-sent event. Delta is the portable text
// field across the OpenAI, Anthropic and Responses wire formats; Raw preserves
// the provider-native event for callers that need usage or finish metadata.
type StreamChunk struct {
	Event string
	Delta string
	Raw   map[string]any
}

// Stream incrementally reads one billed streaming response.
//
// Call Next until it returns false, then inspect Err. Close when stopping early
// so the in-flight HTTP body is cancelled instead of continuing unseen.
type Stream struct {
	Meta ResponseMeta

	response *http.Response
	scanner  *bufio.Scanner
	event    string
	data     []string
	chunk    StreamChunk
	err      error
	done     bool
}

// ChatCompletionsStream streams /chat/completions and forces stream=true in a
// copy of body; the caller's map is never mutated.
func (c *Client) ChatCompletionsStream(ctx context.Context, body any) (*Stream, error) {
	return c.Stream(ctx, "/chat/completions", body)
}

// CompletionsStream streams the legacy /completions wire.
func (c *Client) CompletionsStream(ctx context.Context, body any) (*Stream, error) {
	return c.Stream(ctx, "/completions", body)
}

// MessagesStream streams the native Anthropic /messages wire.
func (c *Client) MessagesStream(ctx context.Context, body any) (*Stream, error) {
	return c.Stream(ctx, "/messages", NormalizeAnthropicMessages(body))
}

// ResponsesStream streams the OpenAI /responses wire.
func (c *Client) ResponsesStream(ctx context.Context, body any) (*Stream, error) {
	return c.Stream(ctx, "/responses", body)
}

// Stream opens any JSON POST as SSE under the gateway's /v1 root. It returns
// after response headers arrive, before the body is consumed, so Meta is
// available throughout iteration.
func (c *Client) Stream(ctx context.Context, path string, body any) (*Stream, error) {
	encoded, err := streamingBody(body)
	if err != nil {
		return nil, err
	}
	req, err := c.request(ctx, http.MethodPost, path, bytes.NewReader(encoded))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	res, err := c.doHTTP(req)
	if err != nil {
		failure := transportErr("%v", err)
		failure.Cause = err
		return nil, failure
	}
	meta := MetaFromLookup(func(name string) string { return res.Header.Get(name) })
	if res.StatusCode < 200 || res.StatusCode >= 300 {
		defer res.Body.Close()
		raw, readErr := io.ReadAll(io.LimitReader(res.Body, maxErrorBody))
		if readErr != nil {
			failure := transportErr("could not read the response body: %v", readErr).withResponse(res, meta)
			failure.Cause = readErr
			return nil, failure
		}
		return nil, gatewayError(res, meta, raw)
	}
	contentType := strings.ToLower(res.Header.Get("Content-Type"))
	if !strings.Contains(contentType, "text/event-stream") {
		_ = res.Body.Close()
		return nil, configErr(
			"gateway returned %d with content-type %q, which is not an SSE stream",
			res.StatusCode, contentType).withResponse(res, meta)
	}

	scanner := bufio.NewScanner(res.Body)
	scanner.Buffer(make([]byte, 4096), maxSSELine)
	scanner.Split(scanLinesCRLF)
	return &Stream{Meta: meta, response: res, scanner: scanner}, nil
}

func scanLinesCRLF(data []byte, atEOF bool) (advance int, token []byte, err error) {
	if atEOF && len(data) == 0 {
		return 0, nil, nil
	}
	if i := bytes.IndexAny(data, "\r\n"); i >= 0 {
		if data[i] == '\r' {
			if i+1 < len(data) {
				if data[i+1] == '\n' {
					return i + 2, data[0:i], nil
				}
				return i + 1, data[0:i], nil
			}
			if atEOF {
				return i + 1, data[0:i], nil
			}
			return 0, nil, nil
		}
		return i + 1, data[0:i], nil
	}
	if atEOF {
		return len(data), data, nil
	}
	return 0, nil, nil
}

func streamingBody(body any) ([]byte, error) {
	encoded, err := json.Marshal(body)
	if err != nil {
		return nil, configErr("request body is not JSON-encodable: %v", err)
	}
	var object map[string]any
	if err := json.Unmarshal(encoded, &object); err != nil || object == nil {
		return nil, configErr("streaming request body must encode to a JSON object")
	}
	object["stream"] = true
	encoded, err = json.Marshal(object)
	if err != nil {
		return nil, configErr("request body is not JSON-encodable: %v", err)
	}
	return encoded, nil
}

// Next advances to the next content or metadata frame. It returns false for a
// clean protocol terminator and for a failure; Err distinguishes the two.
func (s *Stream) Next() bool {
	if s.done {
		return false
	}
	for s.scanner.Scan() {
		line := strings.TrimSuffix(s.scanner.Text(), "\r")
		if line == "" {
			if s.dispatch() {
				return true
			}
			if s.done {
				return false
			}
			continue
		}
		if strings.HasPrefix(line, ":") {
			continue
		}
		name, value, found := strings.Cut(line, ":")
		if !found {
			name, value = line, ""
		}
		value = strings.TrimPrefix(value, " ")
		switch name {
		case "event":
			s.event = value
		case "data":
			s.data = append(s.data, value)
		}
	}
	if len(s.data) > 0 {
		if s.dispatch() {
			return true
		}
		if s.done {
			return false
		}
	}
	if err := s.scanner.Err(); err != nil {
		failure := transportErr("the stream failed while being read: %v", err).withResponse(s.response, s.Meta)
		failure.Cause = err
		s.err = failure
	} else if !s.done {
		// Both gateway stream wires have an explicit terminator: [DONE] on the
		// OpenAI-compatible wires and message_stop on Anthropic. A bare EOF is
		// indistinguishable from a cut connection and must not look complete.
		s.err = transportErr("the stream ended before its terminal event").withResponse(s.response, s.Meta)
	}
	s.finish()
	return false
}

// Chunk returns the frame selected by the most recent successful Next call.
func (s *Stream) Chunk() StreamChunk { return s.chunk }

// Err reports a typed in-band gateway error or a transport/read failure.
func (s *Stream) Err() error { return s.err }

// Close stops reading early and releases the response body. It is idempotent.
func (s *Stream) Close() error {
	if s.response == nil || s.response.Body == nil {
		return nil
	}
	s.done = true
	return s.response.Body.Close()
}

func (s *Stream) dispatch() bool {
	if len(s.data) == 0 {
		s.event = ""
		return false
	}
	event := s.event
	data := strings.Join(s.data, "\n")
	s.event = ""
	s.data = s.data[:0]
	trimmed := strings.TrimSpace(data)
	if trimmed == "" {
		return false
	}
	if trimmed == "[DONE]" {
		s.finish()
		return false
	}

	var raw map[string]any
	if err := json.Unmarshal([]byte(trimmed), &raw); err != nil {
		if event == "error" {
			s.err = streamError(event, nil, trimmed, s.response.StatusCode, s.Meta)
			s.finish()
		}
		return false
	}
	if event == "error" || raw["error"] != nil {
		s.err = streamError(event, raw, trimmed, s.response.StatusCode, s.Meta)
		s.finish()
		return false
	}
	if kind, _ := raw["type"].(string); kind == "message_stop" || kind == "response.completed" {
		s.finish()
		return false
	}
	s.chunk = StreamChunk{Event: event, Delta: streamDelta(raw), Raw: raw}
	return true
}

func (s *Stream) finish() {
	s.done = true
	if s.response != nil && s.response.Body != nil {
		_ = s.response.Body.Close()
	}
}

func streamDelta(raw map[string]any) string {
	if delta, ok := raw["delta"].(string); ok {
		return delta
	}
	if delta, ok := raw["delta"].(map[string]any); ok {
		if text, ok := delta["text"].(string); ok {
			return text
		}
	}
	choices, _ := raw["choices"].([]any)
	if len(choices) == 0 {
		return ""
	}
	choice, _ := choices[0].(map[string]any)
	if text, ok := choice["text"].(string); ok {
		return text
	}
	delta, _ := choice["delta"].(map[string]any)
	text, _ := delta["content"].(string)
	return text
}

func streamError(event string, raw map[string]any, fallback string, status int, meta ResponseMeta) *Error {
	message := fallback
	code := ""
	if raw != nil {
		node := raw
		if nested, ok := raw["error"].(map[string]any); ok {
			node = nested
		}
		if value, ok := node["message"].(string); ok && strings.TrimSpace(value) != "" {
			message = value
		}
		if value, ok := node["code"].(string); ok {
			code = value
		} else if value, ok := node["type"].(string); ok && knownErrorCode(value) {
			code = value
		}
	}
	if message == "" {
		message = fmt.Sprintf("gateway sent an unreadable %s stream event", event)
	}
	return &Error{
		Kind:        classify(code, message, status),
		Message:     message,
		Code:        code,
		Status:      status,
		RequestID:   meta.RequestID,
		LimitSource: meta.LimitSource,
		AuthReason:  meta.AuthReason,
	}
}

func knownErrorCode(code string) bool {
	switch code {
	case "invalid_request", "guardrail_blocked", "invalid_api_key", "insufficient_credits",
		"model_not_found", "rate_limit_exceeded", "tpm_limit_exceeded",
		"credit_check_failed", "service_unavailable":
		return true
	default:
		return false
	}
}
