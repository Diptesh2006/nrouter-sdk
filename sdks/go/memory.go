package nrouter

import (
	"fmt"
	"strings"
	"sync"
)

// ChatMessage represents a single message in conversation memory.
type ChatMessage map[string]any

// MemoryStore defines the interface for persistence backends.
type MemoryStore interface {
	Load() ([]ChatMessage, error)
	Save(messages []ChatMessage) error
}

// ArrayStore is an in-memory thread-safe implementation of MemoryStore.
type ArrayStore struct {
	mu       sync.RWMutex
	messages []ChatMessage
}

// NewArrayStore creates a new in-memory store with optional initial messages.
func NewArrayStore(seed ...ChatMessage) *ArrayStore {
	cp := make([]ChatMessage, len(seed))
	copy(cp, seed)
	return &ArrayStore{messages: cp}
}

func (s *ArrayStore) Load() ([]ChatMessage, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	res := make([]ChatMessage, len(s.messages))
	copy(res, s.messages)
	return res, nil
}

func (s *ArrayStore) Save(messages []ChatMessage) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.messages = make([]ChatMessage, len(messages))
	copy(s.messages, messages)
	return nil
}

// Memory manages conversation history using a pluggable store.
type Memory struct {
	mu    sync.Mutex
	store MemoryStore
}

// NewMemory creates a Memory instance with the default ArrayStore or a custom store.
func NewMemory(store ...MemoryStore) *Memory {
	if len(store) > 0 && store[0] != nil {
		return &Memory{store: store[0]}
	}
	return &Memory{store: NewArrayStore()}
}

var tenancyKeys = []string{"organizationid", "orgid", "teamid", "userid", "nrouterorg"}

func normalizeKey(k string) string {
	s := strings.ToLower(k)
	s = strings.ReplaceAll(s, "_", "")
	s = strings.ReplaceAll(s, "-", "")
	return s
}

func validateMessage(msg ChatMessage, ctx string) (ChatMessage, error) {
	for k := range msg {
		norm := normalizeKey(k)
		for _, tk := range tenancyKeys {
			if norm == tk {
				return nil, fmt.Errorf("%s: message contains forbidden tenancy key %q", ctx, k)
			}
		}
	}
	role, ok := msg["role"].(string)
	if !ok || (role != "system" && role != "user" && role != "assistant" && role != "tool" && role != "developer") {
		return nil, fmt.Errorf("%s: message must contain a valid role (system, user, assistant, tool, developer)", ctx)
	}
	content, hasContent := msg["content"]
	toolCalls, hasToolCalls := msg["tool_calls"]
	isToolCallsList := false
	if hasToolCalls && toolCalls != nil {
		if _, ok := toolCalls.([]any); ok {
			isToolCallsList = true
		}
	}
	if !hasContent || content == nil {
		if !isToolCallsList && role != "assistant" {
			return nil, fmt.Errorf("%s: message content must be a string or content parts list", ctx)
		}
	} else {
		switch content.(type) {
		case string, []any, []map[string]any:
			// valid
		default:
			return nil, fmt.Errorf("%s: message content must be a string or content parts list", ctx)
		}
	}
	return msg, nil
}

// SlidingWindow prunes messages to the most recent maxMessages, preserving index 0
// system or developer message if preserveSystem is true.
func SlidingWindow(messages []ChatMessage, maxMessages int, preserveSystem ...bool) []ChatMessage {
	if maxMessages <= 0 {
		return []ChatMessage{}
	}
	if len(messages) <= maxMessages {
		cp := make([]ChatMessage, len(messages))
		copy(cp, messages)
		return cp
	}
	preserve := true
	if len(preserveSystem) > 0 {
		preserve = preserveSystem[0]
	}
	if preserve && len(messages) > 0 {
		role, _ := messages[0]["role"].(string)
		if role == "system" || role == "developer" {
			if maxMessages == 1 {
				return []ChatMessage{messages[len(messages)-1]}
			}
			tailCount := maxMessages - 1
			out := make([]ChatMessage, 0, maxMessages)
			out = append(out, messages[0])
			out = append(out, messages[len(messages)-tailCount:]...)
			return out
		}
	}
	out := make([]ChatMessage, maxMessages)
	copy(out, messages[len(messages)-maxMessages:])
	return out
}

// Add appends a validated message to the conversation memory.
func (m *Memory) Add(msg ChatMessage) error {
	clean, err := validateMessage(msg, "Memory.Add")
	if err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	msgs, err := m.messagesLocked()
	if err != nil {
		return err
	}
	msgs = append(msgs, clean)
	return m.store.Save(msgs)
}

// Messages returns all validated messages loaded from the store, optionally pruned by maxMessages.
func (m *Memory) Messages(maxMessages ...int) ([]ChatMessage, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	msgs, err := m.messagesLocked()
	if err != nil {
		return nil, err
	}
	if len(maxMessages) > 0 && maxMessages[0] > 0 {
		return SlidingWindow(msgs, maxMessages[0]), nil
	}
	return msgs, nil
}

func (m *Memory) messagesLocked() ([]ChatMessage, error) {
	raw, err := m.store.Load()
	if err != nil {
		return nil, err
	}
	out := make([]ChatMessage, 0, len(raw))
	for i, msg := range raw {
		clean, err := validateMessage(msg, fmt.Sprintf("MemoryStore.Load()[%d]", i))
		if err != nil {
			return nil, err
		}
		out = append(out, clean)
	}
	return out, nil
}

// Clear wipes all messages from the store.
func (m *Memory) Clear() error {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.store.Save([]ChatMessage{})
}
