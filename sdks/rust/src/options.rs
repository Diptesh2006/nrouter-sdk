//! nRouter request option helpers.

use serde_json::{Map, Value};

use crate::NRouterError;

pub const PROMPT_TEMPLATE_ID_FIELD: &str = "nrouter_prompt_template_id";
pub const PROMPT_VARIABLES_FIELD: &str = "nrouter_prompt_variables";
pub const CACHE_FIELD: &str = "nrouter_cache";
pub const EXTRA_BODY_FIELDS: [&str; 3] = [
    PROMPT_TEMPLATE_ID_FIELD,
    PROMPT_VARIABLES_FIELD,
    CACHE_FIELD,
];

const TENANCY_KEYS: [&str; 5] = ["organizationid", "orgid", "teamid", "userid", "nrouterorg"];

#[derive(Debug, Clone, Default)]
pub struct FeatureOptions {
    pub prompt_template_id: Option<String>,
    pub prompt_variables: Option<Map<String, Value>>,
    pub guardrail_ids: Vec<String>,
    pub cache: Option<bool>,
}

pub fn build_extra_body(opts: &FeatureOptions) -> Result<Map<String, Value>, NRouterError> {
    if !opts.guardrail_ids.is_empty() {
        return Err(NRouterError::Configuration(
            "guardrail_ids is not supported: guardrails are assigned per key, team, or organization \
             in the nRouter dashboard and already apply automatically to every call."
                .into(),
        ));
    }

    let mut out = Map::new();
    if let Some(template_id) = opts.prompt_template_id.as_deref() {
        if !template_id.is_empty() {
            out.insert(
                PROMPT_TEMPLATE_ID_FIELD.into(),
                Value::String(template_id.into()),
            );
        }
    }
    if let Some(vars) = &opts.prompt_variables {
        if !vars.is_empty() {
            out.insert(PROMPT_VARIABLES_FIELD.into(), Value::Object(vars.clone()));
        }
    }
    if opts.cache == Some(false) {
        out.insert(CACHE_FIELD.into(), Value::Bool(false));
    }
    Ok(out)
}

pub fn vet_extra(extra: &Map<String, Value>) -> Result<(), NRouterError> {
    for key in extra.keys() {
        if TENANCY_KEYS.contains(&normalize_key(key).as_str()) {
            return Err(NRouterError::Configuration(format!(
                "extra must not carry the tenancy field \"{key}\". The gateway resolves \
                 organization, team, and user from the authenticated API key alone."
            )));
        }
        if key == "__proto__" {
            return Err(NRouterError::Configuration(
                "extra must not carry a \"__proto__\" key.".into(),
            ));
        }
    }
    Ok(())
}

fn normalize_key(key: &str) -> String {
    key.to_ascii_lowercase().replace('_', "")
}
