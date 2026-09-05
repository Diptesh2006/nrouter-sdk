//! Managed prompt helpers for the nRouter request fields.

use serde_json::{Map, Value};

use crate::options::{
    build_extra_body, FeatureOptions, PROMPT_TEMPLATE_ID_FIELD, PROMPT_VARIABLES_FIELD,
};
use crate::NRouterError;

pub const PROMPT_WIRE_FIELDS: [&str; 2] = [PROMPT_TEMPLATE_ID_FIELD, PROMPT_VARIABLES_FIELD];
pub const SYSTEM_VARIABLE_NAMES: [&str; 4] = ["org_name", "model", "timestamp", "user_id"];

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct PromptSelection {
    pub template_id: Option<String>,
    pub variables: Option<Map<String, Value>>,
}

pub fn prompt_template(
    template_id: impl Into<String>,
    variables: Option<Map<String, Value>>,
) -> Result<PromptSelection, NRouterError> {
    let trimmed = template_id.into().trim().to_string();
    if trimmed.is_empty() {
        return Err(NRouterError::Configuration(
            "prompt_template requires a template id. Use prompt_variables() to render the assigned prompt."
                .into(),
        ));
    }
    Ok(PromptSelection {
        template_id: Some(trimmed),
        variables,
    })
}

pub fn prompt_variables(variables: Map<String, Value>) -> PromptSelection {
    PromptSelection {
        template_id: None,
        variables: Some(variables),
    }
}

pub fn with_variables(selection: &PromptSelection, more: Map<String, Value>) -> PromptSelection {
    let mut variables = selection.variables.clone().unwrap_or_default();
    variables.extend(more);
    PromptSelection {
        template_id: selection.template_id.clone(),
        variables: Some(variables),
    }
}

pub fn prompt_extra_body(selection: &PromptSelection) -> Result<Map<String, Value>, NRouterError> {
    build_extra_body(&FeatureOptions {
        prompt_template_id: selection.template_id.clone(),
        prompt_variables: selection.variables.clone(),
        ..FeatureOptions::default()
    })
}

pub fn apply_prompt(options: &mut FeatureOptions, selection: &PromptSelection) {
    if let Some(template_id) = &selection.template_id {
        options.prompt_template_id = Some(template_id.clone());
    }
    if let Some(vars) = &selection.variables {
        let mut merged = options.prompt_variables.clone().unwrap_or_default();
        merged.extend(vars.clone());
        options.prompt_variables = Some(merged);
    }
}

pub fn system_variable_conflicts(variables: &Map<String, Value>) -> Vec<&'static str> {
    SYSTEM_VARIABLE_NAMES
        .iter()
        .copied()
        .filter(|name| variables.contains_key(*name))
        .collect()
}

/// Options for client-side prompt template rendering.
#[derive(Debug, Clone, Default)]
pub struct RenderPromptOptions {
    /// If true, returns an error when a template variable is missing.
    pub strict: bool,
    /// System variables that take precedence over caller variables.
    pub system_variables: Option<Map<String, Value>>,
}

/// Safely renders a prompt template by interpolating `{{variable}}` or `{{ variable }}` tokens.
///
/// Security & resiliency features:
/// - Single-pass replacement: prevents recursive variable expansion loops.
/// - Escape-safe: string scanning avoids regex backreference and format-string exploits.
/// - Strict mode: returns `NRouterError::Configuration` on missing variables.
/// - System variables: take precedence over caller variables matching gateway rules.
pub fn render_prompt(
    template: &str,
    variables: Option<&Map<String, Value>>,
    options: Option<RenderPromptOptions>,
) -> Result<String, NRouterError> {
    if template.is_empty() {
        return Ok(String::new());
    }
    let opts = options.unwrap_or_default();
    let mut result = String::with_capacity(template.len());
    let mut missing_keys = Vec::new();
    let mut cursor = 0;

    while let Some(start_idx) = template[cursor..].find("{{") {
        let abs_start = cursor + start_idx;
        result.push_str(&template[cursor..abs_start]);
        cursor = abs_start + 2;

        if let Some(end_idx) = template[cursor..].find("}}") {
            let abs_end = cursor + end_idx;
            let raw_key = &template[cursor..abs_end];
            let trimmed_key = raw_key.trim();

            if trimmed_key.is_empty()
                || !trimmed_key
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
            {
                // Preserve non-variable token syntax
                result.push_str("{{");
                result.push_str(raw_key);
                result.push_str("}}");
            } else {
                let sys_val = opts
                    .system_variables
                    .as_ref()
                    .and_then(|sys| sys.get(trimmed_key));

                if let Some(val) = sys_val {
                    match val {
                        Value::String(s) => result.push_str(s),
                        Value::Null => {}
                        other => result.push_str(&other.to_string()),
                    }
                } else if let Some(val) = variables.and_then(|v| v.get(trimmed_key)) {
                    match val {
                        Value::String(s) => result.push_str(s),
                        Value::Null => {}
                        other => result.push_str(&other.to_string()),
                    }
                } else if opts.strict {
                    missing_keys.push(trimmed_key.to_string());
                    result.push_str("{{");
                    result.push_str(raw_key);
                    result.push_str("}}");
                } else {
                    result.push_str("{{");
                    result.push_str(raw_key);
                    result.push_str("}}");
                }
            }
            cursor = abs_end + 2;
        } else {
            result.push_str("{{");
            break;
        }
    }
    result.push_str(&template[cursor..]);

    if opts.strict && !missing_keys.is_empty() {
        return Err(NRouterError::Configuration(format!(
            "Missing required prompt template variables: {}",
            missing_keys.join(", ")
        )));
    }

    Ok(result)
}
