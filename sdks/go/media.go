package nrouter

import (
	"context"
	"fmt"
	"strings"
	"time"
)

// ValidAudioFormats contains the audio output formats accepted by /v1/audio/speech.
var ValidAudioFormats = []string{"mp3", "opus", "aac", "flac", "wav", "pcm"}

// ValidateAudioFormat verifies that the given response format is supported by nRouter.
func ValidateAudioFormat(format string) error {
	f := strings.ToLower(strings.TrimSpace(format))
	for _, valid := range ValidAudioFormats {
		if f == valid {
			return nil
		}
	}
	return fmt.Errorf("invalid audio format %q: must be one of %s", format, strings.Join(ValidAudioFormats, ", "))
}

// AudioSpeechParams defines strongly-typed parameters for text-to-speech generation.
type AudioSpeechParams struct {
	Model          string  `json:"model"`
	Input          string  `json:"input"`
	Voice          string  `json:"voice"`
	ResponseFormat string  `json:"response_format,omitempty"`
	Speed          float64 `json:"speed,omitempty"`
}

// Validate checks that required fields are present and valid.
func (p *AudioSpeechParams) Validate() error {
	if strings.TrimSpace(p.Model) == "" {
		return fmt.Errorf("model is required")
	}
	if strings.TrimSpace(p.Input) == "" {
		return fmt.Errorf("input text is required")
	}
	if strings.TrimSpace(p.Voice) == "" {
		return fmt.Errorf("voice is required")
	}
	if p.ResponseFormat != "" {
		if err := ValidateAudioFormat(p.ResponseFormat); err != nil {
			return err
		}
	}
	return nil
}

// WaitForVideo polls RetrieveVideo until the job status is "completed" or "failed",
// or the context is cancelled.
func (c *Client) WaitForVideo(ctx context.Context, id string, pollInterval time.Duration) (*Response[map[string]any], error) {
	if strings.TrimSpace(id) == "" {
		return nil, configErr("video id must not be empty")
	}
	if pollInterval <= 0 {
		pollInterval = 1 * time.Second
	}

	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	for {
		resp, err := c.RetrieveVideo(ctx, id)
		if err != nil {
			return nil, err
		}

		if resp.Body != nil {
			status, _ := resp.Body["status"].(string)
			switch strings.ToLower(status) {
			case "completed", "succeeded":
				return resp, nil
			case "failed", "cancelled":
				return resp, fmt.Errorf("video job %s terminated with status %s", id, status)
			}
		}

		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-ticker.C:
		}
	}
}
