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
	if !ok || (role != "system" && role != "user" && role != "assistant" && role != "tool") {
		return nil, fmt.Errorf("%s: message must contain a valid role (system, user, assistant, tool)", ctx)
	}
	return msg, nil
}

// Add appends a validated message to the conversation memory.
func (m *Memory) Add(msg ChatMessage) error {
	clean, err := validateMessage(msg, "Memory.Add")
	if err != nil {
		return err
	}
	msgs, err := m.Messages()
	if err != nil {
		return err
	}
	msgs = append(msgs, clean)
	return m.store.Save(msgs)
}

// Messages returns all validated messages loaded from the store.
func (m *Memory) Messages() ([]ChatMessage, error) {
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
	return m.store.Save([]ChatMessage{})
}
