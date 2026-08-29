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
}

impl Memory<ArrayStore> {
    pub fn new() -> Self {
        Self {
            store: ArrayStore::default(),
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
        Self { store }
    }

    pub fn add(&self, message: ChatMessage) -> Result<(), NRouterError> {
        let clean = validate_message(message, "add()")?;
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

    pub fn clear(&self) -> Result<(), NRouterError> {
        self.store.save(Vec::new())
    }
}

pub fn create_array_store(seed: Vec<ChatMessage>) -> ArrayStore {
    ArrayStore::new(seed)
}

const ROLES: [&str; 3] = ["system", "user", "assistant"];
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
            "{where_}: role must be one of system, user, assistant."
        )));
    }
    match message.get("content") {
        Some(Value::String(_)) | Some(Value::Array(_)) => Ok(message),
        _ => Err(NRouterError::Configuration(format!(
            "{where_}: content must be a string or content-parts array."
        ))),
    }
}

fn normalize_key(key: &str) -> String {
    key.to_ascii_lowercase().replace('_', "")
}
