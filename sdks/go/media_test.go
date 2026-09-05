package nrouter

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestValidateAudioFormat(t *testing.T) {
	for _, format := range []string{"mp3", "opus", "aac", "flac", "wav", "pcm", "MP3", "WAV"} {
		if err := ValidateAudioFormat(format); err != nil {
			t.Errorf("expected format %s to be valid, got: %v", format, err)
		}
	}

	invalid := []string{"", "ogg", "m4a", "wma", "avi"}
	for _, format := range invalid {
		if err := ValidateAudioFormat(format); err == nil {
			t.Errorf("expected format %s to fail validation", format)
		}
	}
}

func TestAudioSpeechParamsValidation(t *testing.T) {
	p := AudioSpeechParams{
		Model:          "tts-1",
		Input:          "Hello world",
		Voice:          "alloy",
		ResponseFormat: "mp3",
	}
	if err := p.Validate(); err != nil {
		t.Fatalf("expected valid params, got: %v", err)
	}

	badFormat := p
	badFormat.ResponseFormat = "invalid"
	if err := badFormat.Validate(); err == nil {
		t.Fatalf("expected error on invalid format")
	}

	missingModel := p
	missingModel.Model = ""
	if err := missingModel.Validate(); err == nil {
		t.Fatalf("expected error on missing model")
	}
}

func TestWaitForVideo(t *testing.T) {
	attempts := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		w.Header().Set("Content-Type", "application/json")
		if attempts < 2 {
			w.Write([]byte(`{"id":"vid_123","status":"processing"}`))
		} else {
			w.Write([]byte(`{"id":"vid_123","status":"completed","url":"https://example.com/v.mp4"}`))
		}
	}))
	defer srv.Close()

	c, err := New("sk-nrouter-test", WithBaseURL(srv.URL))
	if err != nil {
		t.Fatalf("New failed: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	resp, err := c.WaitForVideo(ctx, "vid_123", 10*time.Millisecond)
	if err != nil {
		t.Fatalf("WaitForVideo failed: %v", err)
	}
	if resp.Body["status"] != "completed" {
		t.Errorf("expected status completed, got %v", resp.Body["status"])
	}
}
