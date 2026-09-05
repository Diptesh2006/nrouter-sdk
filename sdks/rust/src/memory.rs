//! Client-side conversation memory.

use serde_json::{Map, Value};
use std::sync::{Arc, Mutex};

use crate::NRouterError;

pub type ChatMessage = Map<String, Value>;

pub trait MemoryStore: Send + Sync {
    fn load(&self) -> Result<Vec<ChatMessage>, NRouterError>;
    fn save(&self, messages: Vec<ChatMessage>) -> Result<(), NRouterError>;
}

#[derive(Debug, Clone, Default)]
pub struct ArrayStore {
    messages: Arc<Mutex<Vec<ChatMessage>>>,
}

impl ArrayStore {
    pub fn new(seed: Vec<ChatMessage>) -> Self {
        Self {
            messages: Arc::new(Mutex::new(seed)),
        }
    }
}

impl MemoryStore for ArrayStore {
    fn load(&self) -> Result<Vec<ChatMessage>, NRouterError> {
        Ok(self
            .messages
            .lock()
            .map_err(|_| NRouterError::Configuration("memory store lock poisoned".into()))?
            .clone())
    }

    fn save(&self, messages: Vec<ChatMessage>) -> Result<(), NRouterError> {
        *self
            .messages
            .lock()
            .map_err(|_| NRouterError::Configuration("memory store lock poisoned".into()))? =
            messages;
        Ok(())
    }
}

pub struct Memory<S: MemoryStore = ArrayStore> {
    store: S,
    lock: Mutex<()>,
}

impl Memory<ArrayStore> {
    pub fn new() -> Self {
        Self {
            store: ArrayStore::default(),
            lock: Mutex::new(()),
        }
    }
}

impl Default for Memory<ArrayStore> {
    fn default() -> Self {
        Self::new()
    }
}

impl<S: MemoryStore> Memory<S> {
    pub fn with_store(store: S) -> Self {
        Self {
            store,
            lock: Mutex::new(()),
        }
    }

    pub fn add(&self, message: ChatMessage) -> Result<(), NRouterError> {
        let clean = validate_message(message, "add()")?;
        let _guard = self
            .lock
            .lock()
            .map_err(|_| NRouterError::Configuration("memory lock poisoned".into()))?;
        let mut current = self.messages()?;
        current.push(clean);
        self.store.save(current)
    }

    pub fn messages(&self) -> Result<Vec<ChatMessage>, NRouterError> {
        self.store
            .load()?
            .into_iter()
            .enumerate()
            .map(|(i, message)| validate_message(message, &format!("MemoryStore.load()[{i}]")))
            .collect()
    }

    pub fn window(
        &self,
        max_messages: usize,
        preserve_system: bool,
    ) -> Result<Vec<ChatMessage>, NRouterError> {
        let msgs = self.messages()?;
        Ok(sliding_window(&msgs, max_messages, preserve_system))
    }

    pub fn clear(&self) -> Result<(), NRouterError> {
        let _guard = self
            .lock
            .lock()
            .map_err(|_| NRouterError::Configuration("memory lock poisoned".into()))?;
        self.store.save(Vec::new())
    }
}

pub fn create_array_store(seed: Vec<ChatMessage>) -> ArrayStore {
    ArrayStore::new(seed)
}

/// Prune a message slice to the most recent `max_messages`, preserving the index 0
/// system/developer message by default.
pub fn sliding_window(
    messages: &[ChatMessage],
    max_messages: usize,
    preserve_system: bool,
) -> Vec<ChatMessage> {
    if max_messages == 0 {
        return Vec::new();
    }
    if messages.len() <= max_messages {
        return messages.to_vec();
    }
    if preserve_system && !messages.is_empty() {
        let first_role = messages[0]
            .get("role")
            .and_then(Value::as_str)
            .unwrap_or("");
        if first_role == "system" || first_role == "developer" {
            if max_messages == 1 {
                return vec![messages[messages.len() - 1].clone()];
            }
            let tail_count = max_messages - 1;
            let mut out = Vec::with_capacity(max_messages);
            out.push(messages[0].clone());
            out.extend_from_slice(&messages[messages.len() - tail_count..]);
            return out;
        }
    }
    messages[messages.len() - max_messages..].to_vec()
}

const ROLES: [&str; 5] = ["system", "user", "assistant", "tool", "developer"];
const TENANCY_KEYS: [&str; 5] = ["organizationid", "orgid", "teamid", "userid", "nrouterorg"];

fn validate_message(message: ChatMessage, where_: &str) -> Result<ChatMessage, NRouterError> {
    for key in message.keys() {
        if TENANCY_KEYS.contains(&normalize_key(key).as_str()) {
            return Err(NRouterError::Configuration(format!(
                "{where_}: a message must not carry the tenancy field \"{key}\"."
            )));
        }
    }
    let role = message.get("role").and_then(Value::as_str).unwrap_or("");
    if !ROLES.contains(&role) {
        return Err(NRouterError::Configuration(format!(
            "{where_}: role must be one of system, user, assistant, tool, developer."
        )));
    }
    let has_tool_calls = message
        .get("tool_calls")
        .and_then(Value::as_array)
        .is_some_and(|tc| !tc.is_empty());
    match message.get("content") {
        Some(Value::String(_)) | Some(Value::Array(_)) => Ok(message),
        Some(Value::Null) | None if role == "assistant" || has_tool_calls => Ok(message),
        _ => Err(NRouterError::Configuration(format!(
            "{where_}: content must be a string or content-parts array."
        ))),
    }
}

fn normalize_key(key: &str) -> String {
    key.to_ascii_lowercase().replace('_', "")
}
